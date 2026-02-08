"""Audit logging for E2E server."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any


def get_audit_logger(config: dict[str, Any]) -> logging.Logger:
    logger = logging.getLogger("e2e_audit")
    if logger.handlers:
        return logger

    log_path = Path(str(config.get("audit_log_path", "./server_data/audit.log"))).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(str(log_path))
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
