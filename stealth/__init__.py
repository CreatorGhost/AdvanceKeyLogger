"""
Stealth Mode package — minimise the application's observable footprint.

Provides eleven subsystems coordinated by :class:`StealthManager`:

**Original (v1):**
- **ProcessMasker** — process/thread name concealment
- **FileSystemCloak** — file path aliasing, hiding, timestamp preservation
- **LogController** — log suppression, ring buffer, sanitisation
- **ResourceProfiler** — CPU/memory/IO stealth profiling with jitter
- **DetectionAwareness** — monitor/debugger/AV/VM detection and response
- **NetworkNormalizer** — traffic pattern normalisation

**Enhanced (v2):**
- **CrashGuard** — safe exception handling, traceback path scrubbing
- **MemoryCloak** — sys.modules renaming, __file__/__doc__ scrubbing
- **ImageScrubber** — screenshot EXIF/metadata stripping
- **EnvSanitizer** — environment variable cleanup, /proc/environ scrubbing
- **TransportBridge** — wire normaliser to transports, decoy traffic

Quick start::

    from stealth import StealthManager

    sm = StealthManager(config.get("stealth", {}))
    sm.activate()
"""
from stealth.core import StealthManager

__all__ = ["StealthManager"]
