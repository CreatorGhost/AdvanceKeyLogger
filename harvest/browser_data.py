"""
Browser data extraction — cookies, history, bookmarks, autofill, downloads.

Extracts browsing intelligence from:
  - Google Chrome / Chromium-based browsers
  - Mozilla Firefox
  - Apple Safari (macOS only)

Usage::

    from harvest.browser_data import BrowserDataHarvester

    harvester = BrowserDataHarvester()
    data = harvester.harvest_all()
    # Returns cookies, history entries, bookmarks, form data
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


def _safe_query_db(db_path: str, query: str, max_rows: int = 5000) -> list[dict[str, Any]]:
    """Safely copy and query a SQLite database (handles locked DBs)."""
    if not os.path.isfile(db_path):
        return []

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()

    try:
        shutil.copy2(db_path, tmp.name)
        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query)
        rows = [dict(row) for row in cursor.fetchmany(max_rows)]
        conn.close()
        return rows
    except Exception as exc:
        logger.debug("DB query failed for %s: %s", db_path, exc)
        return []
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


class BrowserDataHarvester:
    """Extracts browsing data (non-credential) from installed browsers.

    Parameters
    ----------
    config : dict, optional
        Configuration. Supports ``max_history`` (default 5000),
        ``max_cookies`` (default 2000), ``max_bookmarks`` (default 2000).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._platform = _get_platform()
        self._max_history: int = int(cfg.get("max_history", 5000))
        self._max_cookies: int = int(cfg.get("max_cookies", 2000))
        self._max_bookmarks: int = int(cfg.get("max_bookmarks", 2000))

    def harvest_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for method in [
            self._harvest_chrome_history,
            self._harvest_chrome_cookies,
            self._harvest_chrome_downloads,
            self._harvest_chrome_autofill,
            self._harvest_chrome_bookmarks,
            self._harvest_firefox_history,
            self._harvest_firefox_cookies,
            self._harvest_firefox_bookmarks,
        ]:
            try:
                results.extend(method())
            except Exception as exc:
                logger.debug("%s failed: %s", method.__name__, exc)

        return results

    # ── Chrome profile paths ─────────────────────────────────────────

    def _chrome_base_paths(self) -> dict[str, str]:
        if self._platform == "darwin":
            return {
                "chrome": os.path.expanduser("~/Library/Application Support/Google/Chrome"),
                "edge": os.path.expanduser("~/Library/Application Support/Microsoft Edge"),
                "brave": os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser"),
            }
        elif self._platform == "linux":
            return {
                "chrome": os.path.expanduser("~/.config/google-chrome"),
                "chromium": os.path.expanduser("~/.config/chromium"),
                "edge": os.path.expanduser("~/.config/microsoft-edge"),
                "brave": os.path.expanduser("~/.config/BraveSoftware/Brave-Browser"),
            }
        elif self._platform == "windows":
            local = os.environ.get("LOCALAPPDATA", "")
            return {
                "chrome": os.path.join(local, "Google", "Chrome", "User Data"),
                "edge": os.path.join(local, "Microsoft", "Edge", "User Data"),
                "brave": os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
            }
        return {}

    def _find_chrome_dbs(self, db_name: str) -> list[tuple[str, str]]:
        """Find all instances of a Chrome DB across all browsers and profiles.

        Returns list of (browser_name, db_path).
        """
        found = []
        for browser, base in self._chrome_base_paths().items():
            if not os.path.isdir(base):
                continue
            for entry in os.listdir(base):
                db_path = os.path.join(base, entry, db_name)
                if os.path.isfile(db_path):
                    found.append((browser, db_path))
        return found

    # ── Chrome History ───────────────────────────────────────────────

    def _harvest_chrome_history(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for browser, db_path in self._find_chrome_dbs("History"):
            rows = _safe_query_db(
                db_path,
                f"SELECT url, title, visit_count, last_visit_time FROM urls "
                f"ORDER BY last_visit_time DESC LIMIT {self._max_history}",
            )
            for row in rows:
                row["browser"] = browser
                row["data_type"] = "history"
                # Convert Chrome timestamp (microseconds since 1601-01-01)
                if row.get("last_visit_time"):
                    row["last_visit_time"] = _chrome_time_to_epoch(row["last_visit_time"])
                results.append(row)
        return results

    # ── Chrome Cookies ───────────────────────────────────────────────

    def _harvest_chrome_cookies(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for browser, db_path in self._find_chrome_dbs("Cookies"):
            rows = _safe_query_db(
                db_path,
                f"SELECT host_key, name, path, expires_utc, is_secure, is_httponly, "
                f"last_access_utc FROM cookies "
                f"ORDER BY last_access_utc DESC LIMIT {self._max_cookies}",
            )
            for row in rows:
                row["browser"] = browser
                row["data_type"] = "cookie"
                # Note: cookie values are encrypted on Chrome 80+ (same as passwords)
                # We store metadata; values require the same DPAPI/Keychain key
                if row.get("expires_utc"):
                    row["expires_utc"] = _chrome_time_to_epoch(row["expires_utc"])
                if row.get("last_access_utc"):
                    row["last_access_utc"] = _chrome_time_to_epoch(row["last_access_utc"])
                results.append(row)
        return results

    # ── Chrome Downloads ─────────────────────────────────────────────

    def _harvest_chrome_downloads(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for browser, db_path in self._find_chrome_dbs("History"):
            rows = _safe_query_db(
                db_path,
                "SELECT tab_url, target_path, total_bytes, start_time, end_time, "
                "mime_type FROM downloads ORDER BY start_time DESC LIMIT 500",
            )
            for row in rows:
                row["browser"] = browser
                row["data_type"] = "download"
                if row.get("start_time"):
                    row["start_time"] = _chrome_time_to_epoch(row["start_time"])
                if row.get("end_time"):
                    row["end_time"] = _chrome_time_to_epoch(row["end_time"])
                results.append(row)
        return results

    # ── Chrome Autofill ──────────────────────────────────────────────

    def _harvest_chrome_autofill(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for browser, db_path in self._find_chrome_dbs("Web Data"):
            rows = _safe_query_db(
                db_path,
                "SELECT name, value, count, date_last_used FROM autofill "
                "ORDER BY date_last_used DESC LIMIT 2000",
            )
            for row in rows:
                row["browser"] = browser
                row["data_type"] = "autofill"
                # Note: autofill.date_last_used is stored as Unix epoch seconds
                # (NOT Chrome microsecond timestamp), so no conversion needed.
                if row.get("date_last_used"):
                    row["date_last_used"] = int(row["date_last_used"])
                results.append(row)
        return results

    # ── Chrome Bookmarks ─────────────────────────────────────────────

    def _harvest_chrome_bookmarks(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for browser, base in self._chrome_base_paths().items():
            if not os.path.isdir(base):
                continue
            for entry in os.listdir(base):
                bm_path = os.path.join(base, entry, "Bookmarks")
                if not os.path.isfile(bm_path):
                    continue
                try:
                    with open(bm_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    bookmarks = self._flatten_chrome_bookmarks(data.get("roots", {}))
                    for bm in bookmarks[:self._max_bookmarks]:
                        bm["browser"] = browser
                        bm["data_type"] = "bookmark"
                        results.append(bm)
                except Exception:
                    pass
        return results

    def _flatten_chrome_bookmarks(self, node: dict, depth: int = 0) -> list[dict[str, Any]]:
        """Recursively flatten Chrome bookmark tree."""
        bookmarks: list[dict[str, Any]] = []
        if depth > 20:  # prevent infinite recursion
            return bookmarks

        if isinstance(node, dict):
            if node.get("type") == "url":
                bookmarks.append({
                    "name": node.get("name", ""),
                    "url": node.get("url", ""),
                    "date_added": node.get("date_added", ""),
                })
            children = node.get("children", [])
            if isinstance(children, list):
                for child in children:
                    bookmarks.extend(self._flatten_chrome_bookmarks(child, depth + 1))
            # Process roots
            for key in ("bookmark_bar", "other", "synced"):
                if key in node:
                    bookmarks.extend(self._flatten_chrome_bookmarks(node[key], depth + 1))

        return bookmarks

    # ── Firefox History ──────────────────────────────────────────────

    def _firefox_profile_dirs(self) -> list[str]:
        if self._platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        elif self._platform == "linux":
            base = os.path.expanduser("~/.mozilla/firefox")
        elif self._platform == "windows":
            base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
        else:
            return []

        if not os.path.isdir(base):
            return []

        return [
            os.path.join(base, d)
            for d in os.listdir(base)
            if os.path.isdir(os.path.join(base, d))
        ]

    def _harvest_firefox_history(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for profile in self._firefox_profile_dirs():
            db_path = os.path.join(profile, "places.sqlite")
            rows = _safe_query_db(
                db_path,
                f"SELECT url, title, visit_count, last_visit_date FROM moz_places "
                f"WHERE visit_count > 0 ORDER BY last_visit_date DESC LIMIT {self._max_history}",
            )
            for row in rows:
                row["browser"] = "firefox"
                row["data_type"] = "history"
                # Firefox timestamps are in microseconds since epoch
                if row.get("last_visit_date"):
                    row["last_visit_date"] = row["last_visit_date"] / 1_000_000
                results.append(row)
        return results

    # ── Firefox Cookies ──────────────────────────────────────────────

    def _harvest_firefox_cookies(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for profile in self._firefox_profile_dirs():
            db_path = os.path.join(profile, "cookies.sqlite")
            rows = _safe_query_db(
                db_path,
                f"SELECT host, name, path, value, expiry, isSecure, isHttpOnly, "
                f"lastAccessed FROM moz_cookies "
                f"ORDER BY lastAccessed DESC LIMIT {self._max_cookies}",
            )
            for row in rows:
                row["browser"] = "firefox"
                row["data_type"] = "cookie"
                # Firefox cookie values are NOT encrypted (unlike Chrome)
                results.append(row)
        return results

    # ── Firefox Bookmarks ────────────────────────────────────────────

    def _harvest_firefox_bookmarks(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for profile in self._firefox_profile_dirs():
            db_path = os.path.join(profile, "places.sqlite")
            rows = _safe_query_db(
                db_path,
                f"SELECT b.title, p.url FROM moz_bookmarks b "
                f"JOIN moz_places p ON b.fk = p.id "
                f"WHERE p.url IS NOT NULL AND p.url != '' "
                f"ORDER BY b.dateAdded DESC LIMIT {self._max_bookmarks}",
            )
            for row in rows:
                row["browser"] = "firefox"
                row["data_type"] = "bookmark"
                results.append(row)
        return results


# ── Chrome timestamp conversion ──────────────────────────────────────

def _chrome_time_to_epoch(chrome_ts: int) -> float:
    """Convert Chrome timestamp (microseconds since 1601-01-01) to Unix epoch."""
    if chrome_ts == 0:
        return 0.0
    # Chrome epoch offset: difference between 1601-01-01 and 1970-01-01 in microseconds
    epoch_offset = 11644473600 * 1_000_000
    return (chrome_ts - epoch_offset) / 1_000_000
