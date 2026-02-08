"""
Native macOS audio capture backend using AVFoundation via pyobjc.

Records audio from the default input device using AVAudioEngine +
AVAudioFile, which provides tighter integration with macOS Core Audio
than the PortAudio-based ``sounddevice`` library.

Falls back gracefully when pyobjc is not installed (see AVFOUNDATION_AVAILABLE).
"""
from __future__ import annotations

import logging
import struct
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

AVFOUNDATION_AVAILABLE = False
try:
    import AVFoundation
    from AVFoundation import (
        AVAudioEngine,
        AVAudioCommonFormat,
    )

    AVFOUNDATION_AVAILABLE = True
except ImportError:
    pass


class AVFoundationAudioBackend:
    """Record audio clips using AVAudioEngine (macOS native)."""

    def __init__(
        self,
        sample_rate: int = 44100,
        channels: int = 1,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels

    def record_clip(self, output_path: Path, duration: float) -> bool:
        """Record *duration* seconds of audio and save as WAV.

        Args:
            output_path: Destination WAV file path.
            duration: Recording length in seconds.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        try:
            return self._record_with_engine(output_path, duration)
        except Exception as exc:
            logger.error("AVFoundation recording failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_with_engine(self, output_path: Path, duration: float) -> bool:
        """Use AVAudioEngine to capture from the default input node."""
        import threading
        import time

        engine = AVAudioEngine.alloc().init()
        input_node = engine.inputNode()
        hw_format = input_node.inputFormatForBus_(0)

        # Request int16 PCM at our desired sample rate / channels
        record_format = AVFoundation.AVAudioFormat.alloc().initWithCommonFormat_sampleRate_channels_interleaved_(
            AVAudioCommonFormat.AVAudioPCMFormatInt16,
            float(self._sample_rate),
            self._channels,
            True,
        )

        collected_buffers: list[bytes] = []
        done_event = threading.Event()

        def tap_block(buffer, when):
            # Extract int16 data from the buffer
            frame_count = buffer.frameLength()
            if frame_count == 0:
                return
            channel_data = buffer.int16ChannelData()
            if channel_data is None:
                return
            ptr = channel_data[0]
            raw = bytes(struct.pack(f"<{frame_count}h", *[ptr[i] for i in range(frame_count)]))
            collected_buffers.append(raw)

        # Install tap
        input_node.installTapOnBus_bufferSize_format_block_(
            0,
            4096,
            record_format,
            tap_block,
        )

        engine.startAndReturnError_(None)
        time.sleep(duration)
        engine.stop()
        input_node.removeTapOnBus_(0)

        if not collected_buffers:
            logger.warning("AVFoundation: no audio buffers captured")
            return False

        # Write WAV
        all_data = b"".join(collected_buffers)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self._sample_rate)
            wf.writeframes(all_data)

        return True
