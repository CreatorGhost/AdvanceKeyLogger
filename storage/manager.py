"""
Storage manager with size limits and automatic rotation.

Manages local file storage, tracking total size and auto-deleting
oldest files when capacity is reached.

Usage:
    from storage.manager import StorageManager

    sm = StorageManager(data_dir="./data", max_size_mb=500)
    path = sm.store(b"file contents", "capture_001.png", subdir="screenshots")
    sm.cleanup([str(path)])
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages local file storage with size limits and auto-rotation."""

    def __init__(
        self,
        data_dir: str,
        max_size_mb: int = 500,
        rotation: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.rotation = rotation
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "StorageManager initialized: dir=%s, max=%dMB, rotation=%s",
            self.data_dir,
            max_size_mb,
            rotation,
        )

    def get_total_size(self) -> int:
        """Calculate total size of all files in data directory (bytes)."""
        return sum(f.stat().st_size for f in self.data_dir.rglob("*") if f.is_file())

    def get_usage_percent(self) -> float:
        """Return storage usage as a percentage (0-100)."""
        if self.max_size_bytes == 0:
            return 100.0
        return (self.get_total_size() / self.max_size_bytes) * 100

    def has_space(self, needed_bytes: int = 0) -> bool:
        """Check if there's enough space for new data."""
        return (self.get_total_size() + needed_bytes) < self.max_size_bytes

    def rotate(self) -> int:
        """
        Delete oldest files until under 80% capacity.

        Returns:
            Number of files deleted.
        """
        if not self.rotation:
            logger.debug("Rotation disabled, skipping")
            return 0

        target = int(self.max_size_bytes * 0.8)
        files = sorted(
            [f for f in self.data_dir.rglob("*") if f.is_file()],
            key=lambda f: f.stat().st_mtime,
        )

        deleted = 0
        while self.get_total_size() > target and files:
            oldest = files.pop(0)
            size = oldest.stat().st_size
            oldest.unlink()
            deleted += 1
            logger.info("Rotated out: %s (%d bytes)", oldest.name, size)

        if deleted:
            logger.info(
                "Rotation complete: %d files deleted, usage now %.1f%%",
                deleted,
                self.get_usage_percent(),
            )
        return deleted

    def store(self, data: bytes, filename: str, subdir: str = "") -> Path | None:
        """
        Store data to a file. Auto-rotates if needed.

        Args:
            data: File contents as bytes.
            filename: Name for the file.
            subdir: Optional subdirectory within data_dir.

        Returns:
            Path to the stored file, or None if storage is full.
        """
        if not self.has_space(len(data)):
            if self.rotation:
                self.rotate()
            if not self.has_space(len(data)):
                logger.error("Storage full, cannot store %s (%d bytes)", filename, len(data))
                return None

        target_dir = self.data_dir / subdir if subdir else self.data_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / filename

        filepath.write_bytes(data)
        logger.debug("Stored: %s (%d bytes)", filepath, len(data))
        return filepath

    def list_files(self, subdir: str = "", pattern: str = "*") -> list[Path]:
        """List files in data directory, optionally filtered by glob pattern."""
        search_dir = self.data_dir / subdir if subdir else self.data_dir
        if not search_dir.exists():
            return []
        return sorted(
            [f for f in search_dir.glob(pattern) if f.is_file()],
            key=lambda f: f.stat().st_mtime,
        )

    def cleanup(self, files: list[str]) -> int:
        """
        Delete specific files after successful transport.

        Args:
            files: List of file paths to delete.

        Returns:
            Number of files successfully deleted.
        """
        deleted = 0
        for filepath in files:
            try:
                Path(filepath).unlink()
                deleted += 1
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.error("Failed to delete %s: %s", filepath, e)
        logger.debug("Cleanup: %d/%d files deleted", deleted, len(files))
        return deleted
