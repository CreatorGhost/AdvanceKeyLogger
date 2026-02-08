"""Tests for capture.audio_capture module."""
from __future__ import annotations

import sys
import wave
from pathlib import Path
from unittest import mock

import numpy as np
import pytest


# We need sounddevice mocked before importing AudioCapture.
# Create a fake sounddevice module so the import guard passes.
_fake_sd = mock.MagicMock()
_fake_sd.__name__ = "sounddevice"


@pytest.fixture(autouse=True)
def _patch_sounddevice(monkeypatch):
    """Ensure sounddevice is always mocked for the entire test module."""
    monkeypatch.setitem(sys.modules, "sounddevice", _fake_sd)


def _get_audio_capture_class():
    """Import AudioCapture with sounddevice already mocked."""
    # Force re-evaluation of the SOUNDDEVICE_AVAILABLE flag
    import importlib
    import capture.audio_capture as mod

    mod.SOUNDDEVICE_AVAILABLE = True
    mod.sd = _fake_sd
    mod.np = np
    return mod.AudioCapture


class TestAudioCaptureInit:
    """Test AudioCapture initialisation."""

    def test_init_defaults(self, tmp_path):
        cls = _get_audio_capture_class()
        config = {"enabled": True}
        global_config = {"general": {"data_dir": str(tmp_path)}}
        cap = cls(config, global_config=global_config)
        assert cap._duration == 10
        assert cap._sample_rate == 44100
        assert cap._channels == 1
        assert cap._max_count == 50
        assert cap._interval == 300
        assert cap._output_dir == tmp_path / "audio"

    def test_init_custom_settings(self, tmp_path):
        cls = _get_audio_capture_class()
        config = {
            "enabled": True,
            "duration": 5,
            "sample_rate": 22050,
            "channels": 2,
            "max_count": 10,
            "interval": 60,
        }
        global_config = {"general": {"data_dir": str(tmp_path)}}
        cap = cls(config, global_config=global_config)
        assert cap._duration == 5
        assert cap._sample_rate == 22050
        assert cap._channels == 2
        assert cap._max_count == 10
        assert cap._interval == 60

    def test_init_raises_without_sounddevice(self, tmp_path):
        import capture.audio_capture as mod

        orig = mod.SOUNDDEVICE_AVAILABLE
        mod.SOUNDDEVICE_AVAILABLE = False
        try:
            with pytest.raises(ImportError, match="sounddevice"):
                mod.AudioCapture({"enabled": True}, global_config={"general": {"data_dir": str(tmp_path)}})
        finally:
            mod.SOUNDDEVICE_AVAILABLE = orig


class TestAudioCaptureLifecycle:
    """Test start / stop / collect lifecycle."""

    def test_start_stop(self, tmp_path):
        cls = _get_audio_capture_class()
        config = {"enabled": True, "interval": 9999}
        global_config = {"general": {"data_dir": str(tmp_path)}}
        cap = cls(config, global_config=global_config)

        # Prevent actual recording in the daemon thread
        cap._record_clip = mock.MagicMock(return_value=None)
        cap.start()
        assert cap.is_running
        cap.stop()
        assert not cap.is_running

    def test_collect_empty(self, tmp_path):
        cls = _get_audio_capture_class()
        cap = cls({"enabled": True}, global_config={"general": {"data_dir": str(tmp_path)}})
        assert cap.collect() == []


class TestRecordClip:
    """Test _record_clip helper."""

    def test_record_clip_saves_wav(self, tmp_path):
        cls = _get_audio_capture_class()
        config = {"enabled": True, "duration": 1, "sample_rate": 8000, "channels": 1}
        global_config = {"general": {"data_dir": str(tmp_path)}}
        cap = cls(config, global_config=global_config)

        # Mock sounddevice to produce a numpy array of zeros
        frames = 8000
        fake_recording = np.zeros((frames, 1), dtype="int16")
        _fake_sd.rec.return_value = fake_recording
        _fake_sd.wait.return_value = None

        filepath = cap._record_clip()
        assert filepath is not None
        assert filepath.exists()
        assert filepath.suffix == ".wav"

        # Verify WAV contents
        with wave.open(str(filepath), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 8000
            assert wf.getsampwidth() == 2

        # Check buffer
        items = cap.collect()
        assert len(items) == 1
        assert items[0]["type"] == "audio"
        assert items[0]["path"] == str(filepath)

    def test_max_count_enforcement(self, tmp_path):
        cls = _get_audio_capture_class()
        config = {"enabled": True, "duration": 1, "sample_rate": 8000, "channels": 1, "max_count": 2}
        global_config = {"general": {"data_dir": str(tmp_path)}}
        cap = cls(config, global_config=global_config)

        fake_recording = np.zeros((8000, 1), dtype="int16")
        _fake_sd.rec.return_value = fake_recording
        _fake_sd.wait.return_value = None

        # Record up to max_count
        cap._record_clip()
        cap._record_clip()
        # Third clip should be rejected
        result = cap._record_clip()
        assert result is None
        assert cap._counter == 2
