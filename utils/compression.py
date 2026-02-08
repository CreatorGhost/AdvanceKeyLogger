"""
Data compression utilities (ZIP and GZIP).

Usage:
    from utils.compression import zip_files, gzip_data, gunzip_data

    # Compress multiple files into a ZIP
    archive_bytes = zip_files(["file1.png", "file2.png"])

    # Compress raw bytes with gzip
    compressed = gzip_data(b"some data here")
    original = gunzip_data(compressed)
"""
from __future__ import annotations

import gzip
import io
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def zip_files(file_paths: list[str], output_path: str | None = None) -> bytes:
    """
    Compress multiple files into a ZIP archive.

    Args:
        file_paths: List of file paths to include in the archive.
        output_path: Optional path to save the ZIP file on disk.

    Returns:
        The ZIP archive as bytes.
    """
    buffer = io.BytesIO()
    included = 0

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filepath in file_paths:
            path = Path(filepath)
            if path.exists() and path.is_file():
                zf.write(str(path), arcname=path.name)
                included += 1
            else:
                logger.warning("File not found, skipping: %s", filepath)

    data = buffer.getvalue()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(data)

    original_size = sum(
        Path(f).stat().st_size for f in file_paths if Path(f).exists() and Path(f).is_file()
    )
    if original_size > 0:
        ratio = (1 - len(data) / original_size) * 100
        logger.info(
            "Compressed %d files: %d -> %d bytes (%.1f%% reduction)",
            included,
            original_size,
            len(data),
            ratio,
        )

    return data


def zip_data(data: bytes, filename: str = "data.bin") -> bytes:
    """
    Compress raw bytes into a ZIP archive with a single entry.

    Args:
        data: The bytes to compress.
        filename: Name for the file inside the archive.

    Returns:
        The ZIP archive as bytes.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, data)
    return buffer.getvalue()


def unzip_data(archive: bytes) -> dict[str, bytes]:
    """
    Extract all files from a ZIP archive.

    Args:
        archive: ZIP archive as bytes.

    Returns:
        Dict mapping filename -> file contents.
    """
    result = {}
    with zipfile.ZipFile(io.BytesIO(archive), "r") as zf:
        for name in zf.namelist():
            result[name] = zf.read(name)
    return result


def gzip_data(data: bytes, compresslevel: int = 9) -> bytes:
    """
    Compress bytes using gzip.

    Args:
        data: Bytes to compress.
        compresslevel: Compression level 1-9 (9 = maximum compression).

    Returns:
        Compressed bytes.
    """
    compressed = gzip.compress(data, compresslevel=compresslevel)
    if len(data) > 0:
        logger.debug(
            "Gzip: %d -> %d bytes (%.1f%% reduction)",
            len(data),
            len(compressed),
            (1 - len(compressed) / len(data)) * 100,
        )
    return compressed


def gunzip_data(data: bytes) -> bytes:
    """Decompress gzip bytes."""
    return gzip.decompress(data)
