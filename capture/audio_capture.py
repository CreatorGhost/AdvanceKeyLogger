"""
Audio capture module.

Records audio clips at a configurable interval and saves WAV files to disk.

Backend selection:
  - macOS with pyobjc (AVFoundation) → native AVAudioEngine backend
  - All other platforms / missing pyobjc → sounddevice backend (default)
  - sounddevice requires ``sounddevice`` and ``numpy`` packages.
"""
from __future__ import annotations

import logging
import threading
import time
import wave
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import sounddevice as sd

    SOUNDDEVICE_AVAILABLE = True
except ImportError:  # pragma: no cover
    SOUNDDEVICE_AVAILABLE = False

from capture import register_capture
from capture.base import BaseCapture
from utils.system_info import get_platform

_logger = logging.getLogger(__name__)

_USE_NATIVE_MACOS_AUDIO = False
if get_platform() == "darwin":
    try:
        from capture.macos_audio_backend import AVFoundationAudioBackend, AVFOUNDATION_AVAILABLE

        if AVFOUNDATION_AVAILABLE:
            _USE_NATIVE_MACOS_AUDIO = True
            _logger.debug("Native macOS AVFoundation audio backend available")
    except ImportError:
        pass


@register_capture("audio")
class AudioCapture(BaseCapture):
    """Record audio clips periodically and save as WAV files."""

    def __init__(
        self,
        config: dict[str, Any],
        global_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config, global_config)
        self._use_native_audio = _USE_NATIVE_MACOS_AUDIO
        if not self._use_native_audio and not SOUNDDEVICE_AVAILABLE:
            raise ImportError(
                "sounddevice and numpy are required for audio capture. "
                "Install them with: pip install sounddevice numpy"
            )
        self._native_audio_backend: AVFoundationAudioBackend | None = None  # noqa: F821

        self._duration = int(config.get("duration", 10))
        self._sample_rate = int(config.get("sample_rate", 44100))
        self._channels = int(config.get("channels", 1))
        self._max_count = int(config.get("max_count", 50))
        self._interval = int(config.get("interval", 300))

        data_dir = (
            self.global_config.get("general", {}).get("data_dir")
            if self.global_config
            else None
        )
        self._output_dir = Path(data_dir or "./data") / "audio"
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._counter = 0
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None:
                return
            self._output_dir.mkdir(parents=True, exist_ok=True)
            self._stop_event.clear()
            thread = threading.Thread(target=self._run, daemon=True)
            self._thread = thread
            if self._use_native_audio:
                self._native_audio_backend = AVFoundationAudioBackend(
                    sample_rate=self._sample_rate,
                    channels=self._channels,
                )
            self._running = True
            thread.start()
            backend_name = "native macOS AVFoundation" if self._use_native_audio else "sounddevice"
            self.logger.info("Audio capture started (%s backend)", backend_name)

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._thread is None:
                return
            thread = self._thread
            self._thread = None
        self._stop_event.set()
        thread.join(timeout=self._duration + 5.0)
        if thread.is_alive():
            self.logger.warning(
                "Audio capture thread still alive after join; _stop_event was set"
            )
        self._running = False
        self.logger.info("Audio capture stopped")

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._buffer:
                return []
            items = list(self._buffer)
            self._buffer.clear()
        return items

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._record_clip()
            self._stop_event.wait(self._interval)

    def _record_clip(self) -> Path | None:
        """Record a single audio clip and save it as a WAV file."""
        with self._lock:
            if self._max_count > 0 and self._counter >= self._max_count:
                self.logger.warning(
                    "Audio clip limit reached (%d). Stopping capture.",
                    self._max_count,
                )
                self._running = False
                self._stop_event.set()
                return None
            index = self._counter
            self._counter += 1

        try:
            filename = f"audio_{index:04d}.wav"
            filepath = self._output_dir / filename

            if self._use_native_audio and self._native_audio_backend is not None:
                ok = self._native_audio_backend.record_clip(filepath, self._duration)
                if not ok:
                    self.logger.error("Native audio recording returned no data")
                    return None
            else:
                frames = int(self._duration * self._sample_rate)
                recording = sd.rec(
                    frames,
                    samplerate=self._sample_rate,
                    channels=self._channels,
                    dtype="int16",
                )
                sd.wait()
                self._save_wav(filepath, recording)

            file_size = filepath.stat().st_size
            with self._lock:
                self._buffer.append(
                    {
                        "type": "audio",
                        "path": str(filepath),
                        "timestamp": time.time(),
                        "size": file_size,
                    }
                )
            return filepath
        except Exception as exc:
            self.logger.error("Audio recording failed: %s", exc)
            return None

    def _save_wav(self, filepath: Path, recording: Any) -> None:
        """Write *recording* (numpy int16 array) as a WAV file."""
        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self._sample_rate)
            wf.writeframes(recording.tobytes())
