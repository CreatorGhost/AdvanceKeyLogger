# Capture Plugins

The capture system uses a **plugin architecture** with auto-discovery. All plugins inherit from [`BaseCapture`](../capture/base.py) and self-register via the `@register_capture` decorator.

**How to study this pattern:** Start with [`capture/base.py`](../capture/base.py) to understand the abstract interface (`start()`, `stop()`, `collect()`), then look at how [`capture/__init__.py`](../capture/__init__.py) manages the registry and auto-imports plugins.

## Keyboard Capture
- **Source:** [`capture/keyboard_capture.py`](../capture/keyboard_capture.py), [`capture/macos_keyboard_backend.py`](../capture/macos_keyboard_backend.py)
- **Concepts:** OS-level keyboard hooks, thread-safe ring buffer, special key handling, backend selection pattern
- **Backends:**
  - **macOS native (CGEventTap):** Uses `pyobjc-framework-Quartz` for direct access to macOS Core Graphics event taps
  - **pynput (cross-platform):** Default backend using `pynput.keyboard.Listener`
- **Config:** `capture.keyboard.enabled`, `include_key_up`, `max_buffer`, `biometrics_enabled`
- **Output:** `{"type": "keystroke", "data": "a", "timestamp": 1700000000.0}`

## Mouse Capture
- **Source:** [`capture/mouse_capture.py`](../capture/mouse_capture.py), [`capture/macos_mouse_backend.py`](../capture/macos_mouse_backend.py)
- **Backends:**
  - **macOS native (CGEventTap):** Higher precision coordinates
  - **pynput (cross-platform):** Default backend
- **Config:** `capture.mouse.enabled`, `track_movement`
- **Output:** `{"type": "mouse_click", "data": {"x": 500, "y": 300, "button": "left"}, ...}`

## Screenshot Capture
- **Source:** [`capture/screenshot_capture.py`](../capture/screenshot_capture.py), [`capture/macos_screenshot_backend.py`](../capture/macos_screenshot_backend.py)
- **Backends:**
  - **macOS native (Quartz CoreGraphics):** Retina/HiDPI support
  - **PIL ImageGrab (cross-platform):** Default backend
- **Config:** `capture.screenshot.enabled`, `quality`, `format`, `max_count`

## Clipboard Capture
- **Source:** [`capture/clipboard_capture.py`](../capture/clipboard_capture.py), [`capture/macos_clipboard_backend.py`](../capture/macos_clipboard_backend.py)
- **Backends:**
  - **macOS native (NSPasteboard):** Efficient change detection via `changeCount`
  - **pyperclip (cross-platform):** Default backend
- **Config:** `capture.clipboard.enabled`, `poll_interval`, `max_length`

## Window Capture
- **Source:** [`capture/window_capture.py`](../capture/window_capture.py), [`capture/macos_window_backend.py`](../capture/macos_window_backend.py)
- **Backends:** macOS NSWorkspace, Linux xdotool, Windows ctypes
- **Config:** `capture.window.enabled`, `poll_interval`

## Audio Recording
- **Source:** [`capture/audio_capture.py`](../capture/audio_capture.py), [`capture/macos_audio_backend.py`](../capture/macos_audio_backend.py)
- **Backends:**
  - **macOS native (AVFoundation):** Core Audio integration
  - **sounddevice (cross-platform):** Default PortAudio backend
- **Config:** `capture.audio.enabled`, `duration`, `sample_rate`, `channels`, `max_count`, `interval`

## Adding a New Capture Plugin

1. Create `capture/your_capture.py`
2. Inherit from `BaseCapture`
3. Decorate with `@register_capture("your_name")`
4. Implement `start()`, `stop()`, `collect()`
5. Add config section under `capture.your_name` in YAML
6. Add module name to the auto-import list in `capture/__init__.py`
