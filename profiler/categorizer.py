"""
Rule-based application categorization.
"""
from __future__ import annotations

from typing import Iterable


_DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "work": ["Visual Studio Code", "IntelliJ", "Terminal", "Xcode", "Figma"],
    "communication": ["Slack", "Discord", "Microsoft Teams", "Zoom", "Mail"],
    "browser": ["Google Chrome", "Firefox", "Safari", "Microsoft Edge"],
    "entertainment": ["Spotify", "YouTube", "Netflix"],
    "uncategorized": ["*"],
}


class AppCategorizer:
    """Categorize applications by window title and app name heuristics."""

    def __init__(self, categories: dict[str, list[str]] | None = None) -> None:
        self._categories = categories or _DEFAULT_CATEGORIES
        self._keywords = {
            category: [kw.lower().strip() for kw in keywords if kw and kw != "*"]
            for category, keywords in self._categories.items()
        }
        if "uncategorized" in self._categories:
            self._fallback_category = "uncategorized"
        elif "other" in self._categories:
            self._fallback_category = "other"
        else:
            self._fallback_category = "uncategorized"

    def extract_app_name(self, window_title: str) -> str:
        title = (window_title or "").strip()
        if not title:
            return "Unknown"
        separators = [" - ", " — ", " – ", " | ", " :: "]
        for sep in separators:
            if sep in title:
                parts = [part.strip() for part in title.split(sep) if part.strip()]
                if len(parts) >= 2:
                    return parts[-1]
        return title

    def categorize(self, app_name: str, window_title: str | None = None) -> str:
        name = (app_name or "").lower()
        title = (window_title or "").lower()

        # Entertainment overrides when browsing entertainment in a browser window.
        entertainment_keywords = self._keywords.get("entertainment", [])
        if self._contains(title, entertainment_keywords):
            return "entertainment"

        for category, keywords in self._keywords.items():
            if category == self._fallback_category:
                continue
            if self._contains(name, keywords) or self._contains(title, keywords):
                return category

        browser_keywords = self._keywords.get("browser", [])
        if self._contains(name, browser_keywords):
            return "browser"

        return self._fallback_category

    @staticmethod
    def _contains(text: str, keywords: Iterable[str]) -> bool:
        for kw in keywords:
            if kw and kw in text:
                return True
        return False
