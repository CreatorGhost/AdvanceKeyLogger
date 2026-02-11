"""
Session Recorder — coordinates capture modules into a unified recording session.

Event-driven capture strategy:
  * Screenshot on mouse click
  * Screenshot on window focus change
  * Screenshot on keyboard idle timeout (no keystrokes for N seconds)
  * All keyboard/mouse/window events recorded with timestamps

The recorder does NOT run its own capture threads — it hooks into the existing
capture modules via their buffers and the EventBus publish/subscribe system.
It's designed to be called from the main loop each cycle.

Usage::

    from recording.session_recorder import SessionRecorder
    from recording.session_store import SessionStore

    store = SessionStore("./data/sessions.db")
    recorder = SessionRecorder(config, store, screenshot_capture)
    recorder.start_session()

    # In main loop:
    for event in collected_events:
        recorder.record_event(event)

    recorder.stop_session()
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from recording.session_store import SessionStore

logger = logging.getLogger(__name__)


class SessionRecorder:
    """Coordinate capture modules into a unified recording session.

    Config keys (under ``recording``):
      * ``enabled`` (bool, default False)
      * ``frames_dir`` (str, default ``./data/sessions/frames``)
      * ``idle_screenshot_seconds`` (float, default 5) — take screenshot after
        this many seconds of keyboard idle
      * ``max_frames_per_session`` (int, default 500)
      * ``screenshot_quality`` (int, default 70) — JPEG quality for frames
      * ``max_session_duration`` (float, default 3600) — auto-stop after 1 hour
      * ``auto_start`` (bool, default True) — start recording on launch
    """

    def __init__(
        self,
        config: dict[str, Any],
        store: SessionStore,
        screenshot_capture: Any = None,
    ) -> None:
        cfg = config.get("recording", {})
        self._enabled = bool(cfg.get("enabled", False))
        self._idle_threshold = float(cfg.get("idle_screenshot_seconds", 5.0))
        self._max_frames = int(cfg.get("max_frames_per_session", 500))
        self._max_duration = float(cfg.get("max_session_duration", 3600))
        self._quality = int(cfg.get("screenshot_quality", 70))
        self._auto_start = bool(cfg.get("auto_start", True))

        self._frames_dir = Path(cfg.get("frames_dir", "./data/sessions/frames"))
        self._frames_dir.mkdir(parents=True, exist_ok=True)

        self._store = store
        self._screenshot = screenshot_capture  # ScreenshotCapture instance

        # State
        self._session_id: str | None = None
        self._session_start: float = 0.0
        self._frame_count = 0
        self._event_buffer: list[tuple[str, float, str, str]] = []
        self._last_keystroke_time = 0.0
        self._last_window: str = ""
        self._idle_screenshot_taken = False
        self._flush_interval = 2.0  # flush events to DB every 2 seconds
        self._last_flush = 0.0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._session_id is not None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def start_session(self, metadata: dict[str, Any] | None = None) -> str | None:
        """Start a new recording session.  Returns session ID or None if disabled."""
        if not self._enabled:
            return None
        if self._session_id is not None:
            logger.warning("Session already active: %s", self._session_id)
            return self._session_id

        self._session_id = self._store.create_session(metadata)
        self._session_start = time.time()
        self._frame_count = 0
        self._event_buffer = []
        self._last_keystroke_time = time.time()
        self._last_window = ""
        self._idle_screenshot_taken = False
        self._last_flush = time.time()

        # Take an initial screenshot
        self._take_frame("session_start")

        logger.info("Recording session started: %s", self._session_id)
        return self._session_id

    def stop_session(self) -> None:
        """Stop the current recording session."""
        if self._session_id is None:
            return

        # Flush remaining events
        self._flush_events()

        # Take a final screenshot
        self._take_frame("session_stop")

        self._store.stop_session(self._session_id)
        logger.info("Recording session stopped: %s", self._session_id)
        self._session_id = None

    # ------------------------------------------------------------------
    # Event recording — called from main loop
    # ------------------------------------------------------------------

    def record_event(self, event: dict[str, Any]) -> None:
        """Record a capture event into the current session.

        Determines whether to trigger a screenshot based on the event type.
        Called from the main loop for each collected event.
        """
        if self._session_id is None:
            return

        event_type = event.get("type", "unknown")
        timestamp = event.get("timestamp", time.time())
        offset = timestamp - self._session_start
        if offset < 0:
            offset = 0.0

        data = event.get("data", "")
        data_str = json.dumps(data) if isinstance(data, dict) else str(data)

        # Buffer the event (always, even if we're about to auto-stop)
        self._event_buffer.append((self._session_id, offset, event_type, data_str))

        # Auto-stop check — AFTER buffering the triggering event so it
        # is persisted rather than silently dropped.
        elapsed = time.time() - self._session_start
        if elapsed > self._max_duration:
            logger.info("Session auto-stopped after %.0fs", elapsed)
            self._flush_events()
            self.stop_session()
            return

        # Screenshot triggers
        if event_type == "mouse_click":
            self._take_frame("click")
            self._idle_screenshot_taken = False

        elif event_type == "window":
            window_title = str(data)
            if window_title != self._last_window:
                self._last_window = window_title
                self._take_frame("window_change")
                self._idle_screenshot_taken = False

        elif event_type == "keystroke":
            self._last_keystroke_time = time.time()
            self._idle_screenshot_taken = False

        # Periodic flush
        now = time.time()
        if now - self._last_flush >= self._flush_interval:
            self._flush_events()
            self._last_flush = now

    def check_idle(self) -> None:
        """Called from main loop to check for keyboard idle timeout.

        If no keystrokes for ``idle_screenshot_seconds``, takes a screenshot
        to capture the current screen state.
        """
        if self._session_id is None:
            return
        if self._idle_screenshot_taken:
            return

        now = time.time()
        idle_duration = now - self._last_keystroke_time
        if idle_duration >= self._idle_threshold:
            self._take_frame("idle")
            self._idle_screenshot_taken = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _take_frame(self, trigger: str) -> None:
        """Take a screenshot and record it as a session frame."""
        if self._session_id is None:
            return
        if self._frame_count >= self._max_frames:
            return

        offset = time.time() - self._session_start

        # Use the screenshot capture module if available
        if self._screenshot is not None:
            try:
                # Save directly to the session frames directory
                filename = f"{self._session_id}_{self._frame_count:04d}.jpg"
                filepath = self._frames_dir / filename

                if hasattr(self._screenshot, "_use_native") and self._screenshot._use_native:
                    backend = self._screenshot._native_backend
                    if backend is not None:
                        backend.capture(filepath, "jpg", self._quality)
                    else:
                        self._pil_capture(filepath)
                else:
                    self._pil_capture(filepath)

                if filepath.exists():
                    file_size = filepath.stat().st_size
                    # Get image dimensions
                    width, height = 0, 0
                    try:
                        from PIL import Image
                        with Image.open(filepath) as img:
                            width, height = img.size
                    except Exception:
                        pass

                    self._store.add_frame(
                        session_id=self._session_id,
                        offset_sec=offset,
                        file_path=str(filepath),
                        file_size=file_size,
                        width=width,
                        height=height,
                        trigger=trigger,
                    )
                    self._frame_count += 1
            except Exception as exc:
                logger.debug("Frame capture failed: %s", exc)
        else:
            # No screenshot module — try PIL directly
            try:
                filename = f"{self._session_id}_{self._frame_count:04d}.jpg"
                filepath = self._frames_dir / filename
                self._pil_capture(filepath)
                if filepath.exists():
                    width, height = 0, 0
                    try:
                        from PIL import Image
                        with Image.open(filepath) as img:
                            width, height = img.size
                    except Exception:
                        pass
                    self._store.add_frame(
                        session_id=self._session_id,
                        offset_sec=offset,
                        file_path=str(filepath),
                        file_size=filepath.stat().st_size,
                        width=width,
                        height=height,
                        trigger=trigger,
                    )
                    self._frame_count += 1
            except Exception as exc:
                logger.debug("PIL frame capture failed: %s", exc)

    def _pil_capture(self, filepath: Path) -> None:
        """Take a screenshot using PIL and save as JPEG."""
        from PIL import ImageGrab
        image = ImageGrab.grab()
        image.save(str(filepath), "JPEG", quality=self._quality)

    def _flush_events(self) -> None:
        """Write buffered events to the database.

        The buffer is only cleared on successful write so that events
        are preserved for retry if ``add_events_batch`` raises.
        """
        if not self._event_buffer:
            return
        try:
            self._store.add_events_batch(self._event_buffer)
            self._event_buffer = []  # only clear after successful write
        except Exception as exc:
            logger.warning("Failed to flush session events: %s", exc)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return current recorder status for dashboard display."""
        return {
            "enabled": self._enabled,
            "recording": self.is_recording,
            "session_id": self._session_id,
            "frame_count": self._frame_count,
            "elapsed": time.time() - self._session_start if self._session_id else 0,
            "max_duration": self._max_duration,
            "max_frames": self._max_frames,
        }
