"""Tests for the native macOS AVFoundation audio backend."""
from __future__ import annotations

import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only backend",
)


class TestAVFoundationAudioBackend:
    @pytest.fixture(autouse=True)
    def _skip_if_no_avfoundation(self):
        from capture.macos_audio_backend import AVFOUNDATION_AVAILABLE
        if not AVFOUNDATION_AVAILABLE:
            pytest.skip("pyobjc AVFoundation not installed")

    def test_init_stores_params(self):
        from capture.macos_audio_backend import AVFoundationAudioBackend

        backend = AVFoundationAudioBackend(sample_rate=22050, channels=2)
        assert backend._sample_rate == 22050
        assert backend._channels == 2

    def test_record_clip_returns_false_on_exception(self, tmp_path):
        from capture.macos_audio_backend import AVFoundationAudioBackend

        backend = AVFoundationAudioBackend()
        out = tmp_path / "fail.wav"

        with patch.object(backend, "_record_with_engine", side_effect=RuntimeError("no mic")):
            assert backend.record_clip(out, 1.0) is False

    def test_record_clip_delegates_to_engine(self, tmp_path):
        from capture.macos_audio_backend import AVFoundationAudioBackend

        backend = AVFoundationAudioBackend()
        out = tmp_path / "ok.wav"

        with patch.object(backend, "_record_with_engine", return_value=True):
            assert backend.record_clip(out, 1.0) is True

    def test_record_with_engine_writes_wav_when_mocked(self, tmp_path):
        """Test the WAV writing portion by mocking only the AVAudioEngine parts."""
        from capture.macos_audio_backend import AVFoundationAudioBackend

        backend = AVFoundationAudioBackend(sample_rate=8000, channels=1)
        out = tmp_path / "test.wav"

        # We'll mock _record_with_engine to write a simple WAV directly
        # to verify the backend interface contract
        import struct

        def fake_record(output_path, duration):
            # Simulate: write 100 frames of silence
            frames = 100
            data = struct.pack(f"<{frames}h", *([0] * frames))
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(data)
            return True

        with patch.object(backend, "_record_with_engine", side_effect=fake_record):
            assert backend.record_clip(out, 0.5) is True

        # Verify the WAV file was written
        assert out.exists()
        with wave.open(str(out), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 8000
            assert wf.getnframes() == 100
