"""
Native macOS screenshot backend using Quartz CoreGraphics.

Captures the display using ``CGWindowListCreateImage`` which properly
handles Retina / HiDPI displays and is faster than PIL's ImageGrab on
macOS.

Falls back gracefully when pyobjc is not installed (see QUARTZ_AVAILABLE).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

QUARTZ_AVAILABLE = False
try:
    from Quartz import (
        CGRectInfinite,
        CGWindowListCreateImage,
        kCGWindowImageDefault,
        kCGWindowListOptionOnScreenOnly,
    )
    from Quartz import CGImageGetBitsPerPixel  # noqa: F401 — availability check
    import Quartz

    QUARTZ_AVAILABLE = True
except ImportError:
    pass

# CoreImage / CoreFoundation helpers for saving to PNG/JPEG.
_CI_AVAILABLE = False
try:
    from Foundation import NSBitmapImageRep, NSData
    from AppKit import NSImage, NSPNGFileType, NSJPEGFileType

    _CI_AVAILABLE = True
except ImportError:
    pass

# Fallback: use CoreGraphics destination for writing if AppKit is missing.
_CG_DEST_AVAILABLE = False
try:
    from Quartz import (
        CGImageDestinationCreateWithURL,
        CGImageDestinationAddImage,
        CGImageDestinationFinalize,
    )
    from CoreFoundation import CFURLCreateWithFileSystemPath, kCFStringEncodingUTF8, kCFURLPOSIXPathStyle

    _CG_DEST_AVAILABLE = True
except ImportError:
    pass


class QuartzScreenshotBackend:
    """Native macOS screenshot capture using Quartz CoreGraphics."""

    def capture(self, output_path: Path, fmt: str = "png", quality: int = 80) -> bool:
        """Capture the full screen and save to *output_path*.

        Args:
            output_path: Where to write the image file.
            fmt: Image format — ``"png"`` or ``"jpg"``/``"jpeg"``.
            quality: JPEG quality (0-100). Ignored for PNG.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        try:
            cg_image = CGWindowListCreateImage(
                CGRectInfinite,
                kCGWindowListOptionOnScreenOnly,
                0,  # kCGNullWindowID — capture everything
                kCGWindowImageDefault,
            )
            if cg_image is None:
                logger.error("CGWindowListCreateImage returned None")
                return False

            return self._save_image(cg_image, output_path, fmt, quality)

        except Exception as exc:
            logger.error("Native screenshot failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Saving helpers — try AppKit first, then CGImageDestination
    # ------------------------------------------------------------------

    @staticmethod
    def _save_image(cg_image, output_path: Path, fmt: str, quality: int) -> bool:
        """Save a CGImage to disk.  Tries AppKit, then CGImageDestination."""
        if _CI_AVAILABLE:
            return _save_via_appkit(cg_image, output_path, fmt, quality)
        if _CG_DEST_AVAILABLE:
            return _save_via_cgdest(cg_image, output_path, fmt, quality)

        logger.error(
            "Cannot save screenshot — neither AppKit nor "
            "CGImageDestination helpers are available."
        )
        return False


# ------------------------------------------------------------------
# AppKit-based saving (preferred — more common in pyobjc installs)
# ------------------------------------------------------------------

def _save_via_appkit(cg_image, output_path: Path, fmt: str, quality: int) -> bool:
    """Save *cg_image* using NSBitmapImageRep (AppKit)."""
    try:
        ns_image = NSImage.alloc().initWithCGImage_size_(cg_image, (0, 0))
        tiff_data = ns_image.TIFFRepresentation()
        bitmap = NSBitmapImageRep.imageRepWithData_(tiff_data)

        if fmt in {"jpg", "jpeg"}:
            file_type = NSJPEGFileType
            props = {
                # NSImageCompressionFactor key
                "NSImageCompressionFactor": quality / 100.0,
            }
        else:
            file_type = NSPNGFileType
            props = {}

        data = bitmap.representationUsingType_properties_(file_type, props)
        data.writeToFile_atomically_(str(output_path), True)
        return True
    except Exception as exc:
        logger.error("AppKit save failed: %s", exc)
        return False


# ------------------------------------------------------------------
# CGImageDestination-based saving (fallback)
# ------------------------------------------------------------------

def _save_via_cgdest(cg_image, output_path: Path, fmt: str, quality: int) -> bool:
    """Save *cg_image* using CGImageDestination (CoreGraphics)."""
    try:
        uti = "public.png"
        options: dict[str, Any] = {}
        if fmt in {"jpg", "jpeg"}:
            uti = "public.jpeg"
            options["kCGImageDestinationLossyCompressionQuality"] = quality / 100.0

        url = CFURLCreateWithFileSystemPath(
            None, str(output_path), kCFURLPOSIXPathStyle, False
        )
        dest = CGImageDestinationCreateWithURL(url, uti, 1, None)
        if dest is None:
            logger.error("CGImageDestinationCreateWithURL returned None")
            return False

        CGImageDestinationAddImage(dest, cg_image, options or None)
        ok = CGImageDestinationFinalize(dest)
        return bool(ok)
    except Exception as exc:
        logger.error("CGImageDestination save failed: %s", exc)
        return False
