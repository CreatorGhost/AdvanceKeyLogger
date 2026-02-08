"""
Centralized logging configuration.

Usage:
    from utils.logger_setup import setup_logging

    setup_logging(log_level="DEBUG", log_file="./logs/app.log")

    # Then in any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Something happened")
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> None:
    """
    Configure logging for the entire application.

    Args:
        log_level: Minimum level to log (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file. None means console only.
        max_bytes: Max size per log file before rotation (default 5 MB).
        backup_count: Number of rotated log files to keep.
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ("urllib3", "PIL", "pynput"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
