"""
Image metadata scrubber for stealth mode.

Strips EXIF, PIL software tags, and other identifying metadata from
screenshots before they are saved to disk. Also provides hash-based
filenames to replace identifiable patterns like ``screenshot_0001.png``.

Research notes (Feb 2026):
  - PIL ``Image.new()`` + ``putdata()`` strips ALL metadata (EXIF, ICC, comments)
  - PIL JPEG default quality is 75; we must preserve the original quality setting
  - Palette-mode images (mode 'P') need ``putpalette()`` after ``putdata()``

Usage::

    from stealth.image_scrubber import ImageScrubber

    scrubber = ImageScrubber()
    scrubber.strip_metadata(image)               # in-place PIL Image
    filename = scrubber.generate_filename("png")  # hash-based name
"""
from __future__ import annotations

import hashlib
import itertools
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class ImageScrubber:
    """Strips identifying metadata from captured images.

    Parameters
    ----------
    config : dict
        Optional configuration (currently unused, reserved for future options).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._counter = itertools.count()

    def strip_metadata(self, image: Any) -> Any:
        """Remove all metadata from a PIL Image object.

        Creates a new image with only pixel data — no EXIF, no software tags,
        no ICC profiles, no comments. Returns the cleaned image.

        Parameters
        ----------
        image : PIL.Image.Image
            The image to strip metadata from.

        Returns
        -------
        PIL.Image.Image
            A new image with identical pixels but no metadata.
        """
        try:
            from PIL import Image

            if not isinstance(image, Image.Image):
                return image

            # Create a clean image with only pixel data
            cleaned = Image.new(image.mode, image.size)
            cleaned.putdata(list(image.getdata()))

            # Preserve palette for mode 'P' images
            if "P" in image.mode:
                palette = image.getpalette()
                if palette:
                    cleaned.putpalette(palette)

            return cleaned
        except ImportError:
            return image
        except Exception as exc:
            logger.debug("Image metadata strip failed: %s", exc)
            return image

    def strip_and_save(
        self,
        image: Any,
        path: str,
        format: str = "JPEG",
        quality: int = 70,
    ) -> bool:
        """Strip metadata and save the image in one step.

        Parameters
        ----------
        image : PIL.Image.Image
            The image to process.
        path : str
            Output file path.
        format : str
            Image format (JPEG, PNG).
        quality : int
            JPEG quality (1-100). Ignored for PNG.

        Returns
        -------
        bool
            True if saved successfully.
        """
        try:
            cleaned = self.strip_metadata(image)
            save_kwargs: dict[str, Any] = {"format": format}
            if format.upper() in ("JPEG", "JPG"):
                save_kwargs["quality"] = quality
                # Explicitly disable EXIF writing
                save_kwargs["exif"] = b""
            cleaned.save(path, **save_kwargs)
            return True
        except Exception as exc:
            logger.debug("Image scrub+save failed: %s", exc)
            return False

    def generate_filename(self, extension: str = "jpg") -> str:
        """Generate a hash-based filename that doesn't reveal purpose.

        Returns something like ``a3f8b2c1.jpg`` instead of ``screenshot_0042.png``.
        """
        count = next(self._counter)
        seed = f"{time.time_ns()}-{os.getpid()}-{count}"
        h = hashlib.sha256(seed.encode()).hexdigest()[:10]
        return f"{h}.{extension.lstrip('.')}"

    @staticmethod
    def clean_existing_file(path: str) -> bool:
        """Re-save an existing image file without metadata.

        Reads the file, strips metadata, and overwrites.
        """
        try:
            from PIL import Image

            with Image.open(path) as img:
                fmt = img.format or "JPEG"

                cleaned = Image.new(img.mode, img.size)
                cleaned.putdata(list(img.getdata()))
                if "P" in img.mode:
                    palette = img.getpalette()
                    if palette:
                        cleaned.putpalette(palette)

            save_kwargs: dict[str, Any] = {"format": fmt}
            if fmt.upper() in ("JPEG", "JPG"):
                save_kwargs["quality"] = 85
                save_kwargs["exif"] = b""
            cleaned.save(path, **save_kwargs)
            return True
        except Exception:
            return False
