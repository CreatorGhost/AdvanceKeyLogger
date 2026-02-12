/*
 * minifilter.c — Windows filesystem minifilter driver stub.
 *
 * Implements a minifilter that intercepts directory query operations
 * (IRP_MJ_DIRECTORY_CONTROL) to hide files and directories matching
 * configured prefixes.  Communicates with userspace Python via a
 * FilterCommunicationPort.
 *
 * BUILD REQUIREMENTS:
 *   - Visual Studio 2022+
 *   - Windows Driver Kit (WDK) 10+
 *   - Build via WDK project or `msbuild` command line
 *
 * This is a complete structural implementation.  It compiles with WDK
 * but requires driver signing for deployment on production systems.
 * For development, enable test-signing: bcdedit /set testsigning on
 *
 * EDUCATIONAL PURPOSE ONLY.
 */

#include <fltKernel.h>
#include <dontuse.h>
#include <suppress.h>
#include <ntddk.h>
#include <ntstrsafe.h>

#pragma prefast(disable:__WARNING_ENCODE_MEMBER_FUNCTION_POINTER, \
    "Not valid for kernel mode drivers")

/* ── Configuration ──────────────────────────────────────────────── */

#define MINIFILTER_TAG       'dHsM'
#define COMM_PORT_NAME       L"\\HideFilterPort"
#define MAX_HIDDEN_PREFIXES  32
#define MAX_PREFIX_LEN       260

/* ── Global state ───────────────────────────────────────────────── */

typedef struct _GLOBAL_DATA {
    PFLT_FILTER       FilterHandle;
    PFLT_PORT         ServerPort;
    PFLT_PORT         ClientPort;
    WCHAR             HiddenPrefixes[MAX_HIDDEN_PREFIXES][MAX_PREFIX_LEN];
    LONG              HiddenPrefixCount;
    FAST_MUTEX        Lock;
} GLOBAL_DATA, *PGLOBAL_DATA;

static GLOBAL_DATA g_Data;

/* ── Communication message structure ────────────────────────────── */

typedef enum _COMMAND_TYPE {
    CMD_HIDE_PREFIX  = 1,
    CMD_CLEAR_ALL    = 2,
    CMD_GET_STATUS   = 3,
} COMMAND_TYPE;

typedef struct _COMMAND_MSG {
    COMMAND_TYPE  Command;
    WCHAR         Prefix[MAX_PREFIX_LEN];
} COMMAND_MSG, *PCOMMAND_MSG;

typedef struct _STATUS_REPLY {
    LONG   HiddenCount;
    LONG   Active;
} STATUS_REPLY, *PSTATUS_REPLY;

/* ── Forward declarations ───────────────────────────────────────── */

DRIVER_INITIALIZE DriverEntry;
NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath);

NTSTATUS FilterUnload(
    _In_ FLT_FILTER_UNLOAD_FLAGS Flags);

NTSTATUS InstanceSetup(
    _In_ PCFLT_RELATED_OBJECTS    FltObjects,
    _In_ FLT_INSTANCE_SETUP_FLAGS Flags,
    _In_ DEVICE_TYPE              VolumeDeviceType,
    _In_ FLT_FILESYSTEM_TYPE      VolumeFilesystemType);

FLT_POSTOP_CALLBACK_STATUS PostDirectoryControl(
    _Inout_ PFLT_CALLBACK_DATA    Data,
    _In_    PCFLT_RELATED_OBJECTS FltObjects,
    _In_opt_ PVOID                CompletionContext,
    _In_    FLT_POST_OPERATION_FLAGS Flags);

/* Communication callbacks */
NTSTATUS CommConnect(
    _In_  PFLT_PORT         ClientPort,
    _In_  PVOID             ServerPortCookie,
    _In_reads_bytes_(SizeOfContext) PVOID ConnectionContext,
    _In_  ULONG             SizeOfContext,
    _Outptr_ PVOID          *ConnectionCookie);

VOID CommDisconnect(_In_opt_ PVOID ConnectionCookie);

NTSTATUS CommMessage(
    _In_  PVOID  PortCookie,
    _In_reads_bytes_(InputBufferLength) PVOID InputBuffer,
    _In_  ULONG  InputBufferLength,
    _Out_writes_bytes_to_(OutputBufferLength, *ReturnOutputBufferLength)
          PVOID  OutputBuffer,
    _In_  ULONG  OutputBufferLength,
    _Out_ PULONG ReturnOutputBufferLength);

/* ── Helper: check if a filename should be hidden ───────────────── */

static BOOLEAN ShouldHideFile(PCUNICODE_STRING FileName)
{
    LONG i;
    LONG count;
    UNICODE_STRING prefix;

    ExAcquireFastMutex(&g_Data.Lock);
    count = g_Data.HiddenPrefixCount;

    for (i = 0; i < count; i++) {
        RtlInitUnicodeString(&prefix, g_Data.HiddenPrefixes[i]);
        if (FileName->Length >= prefix.Length) {
            if (RtlPrefixUnicodeString(&prefix, FileName, TRUE)) {
                ExReleaseFastMutex(&g_Data.Lock);
                return TRUE;
            }
        }
    }

    ExReleaseFastMutex(&g_Data.Lock);
    return FALSE;
}

/* ── Minifilter registration structures ─────────────────────────── */

static const FLT_OPERATION_REGISTRATION Callbacks[] = {
    {
        IRP_MJ_DIRECTORY_CONTROL,
        0,
        NULL,                      /* no pre-op */
        PostDirectoryControl       /* post-op: filter results */
    },
    { IRP_MJ_OPERATION_END }
};

static const FLT_CONTEXT_REGISTRATION ContextRegistration[] = {
    { FLT_CONTEXT_END }
};

static const FLT_REGISTRATION FilterRegistration = {
    sizeof(FLT_REGISTRATION),
    FLT_REGISTRATION_VERSION,
    0,                          /* Flags */
    ContextRegistration,
    Callbacks,
    FilterUnload,
    InstanceSetup,
    NULL,                       /* InstanceQueryTeardown */
    NULL,                       /* InstanceTeardownStart */
    NULL,                       /* InstanceTeardownComplete */
    NULL, NULL, NULL            /* unused */
};

/* ── Post-operation callback: filter directory entries ───────────── */

FLT_POSTOP_CALLBACK_STATUS PostDirectoryControl(
    _Inout_ PFLT_CALLBACK_DATA    Data,
    _In_    PCFLT_RELATED_OBJECTS FltObjects,
    _In_opt_ PVOID                CompletionContext,
    _In_    FLT_POST_OPERATION_FLAGS Flags)
{
    PFLT_PARAMETERS params;
    PFILE_BOTH_DIR_INFORMATION dirInfo, prevInfo;
    PVOID buffer;
    ULONG bufferLength;
    UNICODE_STRING fileName;

    UNREFERENCED_PARAMETER(FltObjects);
    UNREFERENCED_PARAMETER(CompletionContext);

    /* Guard: do not touch I/O structures while the instance is draining */
    if (Flags & FLTFL_POST_OPERATION_DRAINING)
        return FLT_POSTOP_FINISHED_PROCESSING;

    if (!NT_SUCCESS(Data->IoStatus.Status))
        return FLT_POSTOP_FINISHED_PROCESSING;

    if (Data->Iopb->MinorFunction != IRP_MN_QUERY_DIRECTORY)
        return FLT_POSTOP_FINISHED_PROCESSING;

    params = &Data->Iopb->Parameters;

    /* Only handle FileBothDirectoryInformation for now */
    if (params->DirectoryControl.QueryDirectory.FileInformationClass
        != FileBothDirectoryInformation)
        return FLT_POSTOP_FINISHED_PROCESSING;

    buffer = params->DirectoryControl.QueryDirectory.DirectoryBuffer;
    bufferLength = (ULONG)Data->IoStatus.Information;

    if (!buffer || bufferLength == 0)
        return FLT_POSTOP_FINISHED_PROCESSING;

    /* Walk the linked list of directory entries */
    dirInfo = (PFILE_BOTH_DIR_INFORMATION)buffer;
    prevInfo = NULL;

    do {
        fileName.Buffer = dirInfo->FileName;
        fileName.Length = (USHORT)dirInfo->FileNameLength;
        fileName.MaximumLength = fileName.Length;

        if (ShouldHideFile(&fileName)) {
            /* Remove this entry from the linked list */
            if (prevInfo != NULL) {
                if (dirInfo->NextEntryOffset != 0) {
                    prevInfo->NextEntryOffset +=
                        dirInfo->NextEntryOffset;
                } else {
                    prevInfo->NextEntryOffset = 0;
                }
            } else {
                /* First entry — shift buffer forward */
                if (dirInfo->NextEntryOffset != 0) {
                    ULONG offset = dirInfo->NextEntryOffset;
                    RtlMoveMemory(buffer,
                        (PUCHAR)buffer + offset,
                        bufferLength - offset);
                    Data->IoStatus.Information -= offset;
                    /* Keep bufferLength in sync so subsequent
                     * iterations use the correct buffer size   */
                    bufferLength = (ULONG)Data->IoStatus.Information;
                    /* Reset to start of buffer for re-check */
                    dirInfo = (PFILE_BOTH_DIR_INFORMATION)buffer;
                    prevInfo = NULL;
                    continue;  /* re-check at same position */
                } else {
                    /* Only entry and it's hidden — return empty */
                    Data->IoStatus.Status = STATUS_NO_MORE_FILES;
                    Data->IoStatus.Information = 0;
                    return FLT_POSTOP_FINISHED_PROCESSING;
                }
            }
        } else {
            prevInfo = dirInfo;
        }

        if (dirInfo->NextEntryOffset == 0)
            break;

        dirInfo = (PFILE_BOTH_DIR_INFORMATION)(
            (PUCHAR)dirInfo + dirInfo->NextEntryOffset);

    } while (TRUE);

    return FLT_POSTOP_FINISHED_PROCESSING;
}

/* ── Communication port callbacks ───────────────────────────────── */

NTSTATUS CommConnect(
    _In_  PFLT_PORT ClientPort,
    _In_  PVOID     ServerPortCookie,
    _In_reads_bytes_(SizeOfContext) PVOID ConnectionContext,
    _In_  ULONG     SizeOfContext,
    _Outptr_ PVOID  *ConnectionCookie)
{
    UNREFERENCED_PARAMETER(ServerPortCookie);
    UNREFERENCED_PARAMETER(ConnectionContext);
    UNREFERENCED_PARAMETER(SizeOfContext);
    UNREFERENCED_PARAMETER(ConnectionCookie);

    InterlockedExchangePointer(&g_Data.ClientPort, ClientPort);
    return STATUS_SUCCESS;
}

VOID CommDisconnect(_In_opt_ PVOID ConnectionCookie)
{
    PFLT_PORT oldPort;

    UNREFERENCED_PARAMETER(ConnectionCookie);

    oldPort = (PFLT_PORT)InterlockedExchangePointer(&g_Data.ClientPort, NULL);
    if (oldPort) {
        FltCloseClientPort(g_Data.FilterHandle, &oldPort);
    }
}

NTSTATUS CommMessage(
    _In_  PVOID  PortCookie,
    _In_reads_bytes_(InputBufferLength) PVOID InputBuffer,
    _In_  ULONG  InputBufferLength,
    _Out_writes_bytes_to_(OutputBufferLength, *ReturnOutputBufferLength)
          PVOID  OutputBuffer,
    _In_  ULONG  OutputBufferLength,
    _Out_ PULONG ReturnOutputBufferLength)
{
    PCOMMAND_MSG msg;

    UNREFERENCED_PARAMETER(PortCookie);

    *ReturnOutputBufferLength = 0;

    if (InputBufferLength < sizeof(COMMAND_MSG))
        return STATUS_INVALID_PARAMETER;

    msg = (PCOMMAND_MSG)InputBuffer;

    switch (msg->Command) {
    case CMD_HIDE_PREFIX:
        ExAcquireFastMutex(&g_Data.Lock);
        if (g_Data.HiddenPrefixCount < MAX_HIDDEN_PREFIXES) {
            RtlStringCchCopyW(
                g_Data.HiddenPrefixes[g_Data.HiddenPrefixCount],
                MAX_PREFIX_LEN,
                msg->Prefix);
            g_Data.HiddenPrefixCount++;
        }
        ExReleaseFastMutex(&g_Data.Lock);
        break;

    case CMD_CLEAR_ALL:
        ExAcquireFastMutex(&g_Data.Lock);
        g_Data.HiddenPrefixCount = 0;
        ExReleaseFastMutex(&g_Data.Lock);
        break;

    case CMD_GET_STATUS:
        if (OutputBufferLength >= sizeof(STATUS_REPLY)) {
            PSTATUS_REPLY reply = (PSTATUS_REPLY)OutputBuffer;
            ExAcquireFastMutex(&g_Data.Lock);
            reply->HiddenCount = g_Data.HiddenPrefixCount;
            ExReleaseFastMutex(&g_Data.Lock);
            reply->Active = 1;
            *ReturnOutputBufferLength = sizeof(STATUS_REPLY);
        }
        break;

    default:
        return STATUS_INVALID_PARAMETER;
    }

    return STATUS_SUCCESS;
}

/* ── InstanceSetup ──────────────────────────────────────────────── */

NTSTATUS InstanceSetup(
    _In_ PCFLT_RELATED_OBJECTS    FltObjects,
    _In_ FLT_INSTANCE_SETUP_FLAGS Flags,
    _In_ DEVICE_TYPE              VolumeDeviceType,
    _In_ FLT_FILESYSTEM_TYPE      VolumeFilesystemType)
{
    UNREFERENCED_PARAMETER(FltObjects);
    UNREFERENCED_PARAMETER(Flags);
    UNREFERENCED_PARAMETER(VolumeDeviceType);

    /* Only attach to NTFS volumes */
    if (VolumeFilesystemType != FLT_FSTYPE_NTFS)
        return STATUS_FLT_DO_NOT_ATTACH;

    return STATUS_SUCCESS;
}

/* ── FilterUnload ───────────────────────────────────────────────── */

NTSTATUS FilterUnload(_In_ FLT_FILTER_UNLOAD_FLAGS Flags)
{
    UNREFERENCED_PARAMETER(Flags);

    if (g_Data.ServerPort) {
        FltCloseCommunicationPort(g_Data.ServerPort);
        g_Data.ServerPort = NULL;
    }

    if (g_Data.FilterHandle) {
        FltUnregisterFilter(g_Data.FilterHandle);
        g_Data.FilterHandle = NULL;
    }

    return STATUS_SUCCESS;
}

/* ── DriverEntry ────────────────────────────────────────────────── */

NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath)
{
    NTSTATUS status;
    UNICODE_STRING portName;
    PSECURITY_DESCRIPTOR sd = NULL;
    OBJECT_ATTRIBUTES oa;

    UNREFERENCED_PARAMETER(RegistryPath);

    /* Initialize global state */
    RtlZeroMemory(&g_Data, sizeof(g_Data));
    ExInitializeFastMutex(&g_Data.Lock);

    /* Register the minifilter */
    status = FltRegisterFilter(DriverObject,
                               &FilterRegistration,
                               &g_Data.FilterHandle);
    if (!NT_SUCCESS(status))
        return status;

    /* Create communication port */
    RtlInitUnicodeString(&portName, COMM_PORT_NAME);

    status = FltBuildDefaultSecurityDescriptor(&sd,
                FLT_PORT_ALL_ACCESS);
    if (!NT_SUCCESS(status)) {
        FltUnregisterFilter(g_Data.FilterHandle);
        return status;
    }

    InitializeObjectAttributes(&oa, &portName,
        OBJ_CASE_INSENSITIVE | OBJ_KERNEL_HANDLE,
        NULL, sd);

    status = FltCreateCommunicationPort(
        g_Data.FilterHandle,
        &g_Data.ServerPort,
        &oa,
        NULL,
        CommConnect,
        CommDisconnect,
        CommMessage,
        1);             /* max connections */

    FltFreeSecurityDescriptor(sd);

    if (!NT_SUCCESS(status)) {
        FltUnregisterFilter(g_Data.FilterHandle);
        return status;
    }

    /* Start filtering */
    status = FltStartFiltering(g_Data.FilterHandle);
    if (!NT_SUCCESS(status)) {
        FltCloseCommunicationPort(g_Data.ServerPort);
        FltUnregisterFilter(g_Data.FilterHandle);
        return status;
    }

    return STATUS_SUCCESS;
}
