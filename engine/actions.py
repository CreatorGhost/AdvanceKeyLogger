"""
Action dispatcher for rule engine.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from engine.rule_parser import Action
from transport import create_transport_for_method

logger = logging.getLogger(__name__)


class ActionDispatcher:
    """Dispatch rule actions to capture modules or transports."""

    def __init__(
        self,
        captures: list[Any],
        config: dict[str, Any],
        set_interval: Callable[[float], None] | None = None,
    ) -> None:
        self._captures = captures
        self._config = config
        self._set_interval = set_interval

    def dispatch(self, action: Action, event: dict[str, Any]) -> None:
        action_type = action.type
        params = action.params or {}
        delay_ms = int(params.get("delay_ms", 0))
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        if action_type == "take_screenshot":
            self._take_screenshot()
        elif action_type == "set_capture_interval":
            self._set_capture_interval(params)
        elif action_type == "pause_capture":
            self._pause_capture(params)
        elif action_type == "resume_capture":
            self._resume_capture(params)
        elif action_type == "notify":
            self._notify(params, event)
        elif action_type == "log":
            logger.info("Rule action log: %s", params.get("message", ""))
        else:
            logger.warning("Unknown action type: %s", action_type)

    def _take_screenshot(self) -> None:
        for cap in self._captures:
            if hasattr(cap, "take_screenshot"):
                try:
                    cap.take_screenshot()
                    return
                except Exception as exc:
                    logger.warning("take_screenshot failed: %s", exc)

    def _set_capture_interval(self, params: dict[str, Any]) -> None:
        if not self._set_interval:
            logger.warning("No interval setter configured for set_capture_interval")
            return
        value = float(params.get("value", 0))
        if value > 0:
            self._set_interval(value)

    def _pause_capture(self, params: dict[str, Any]) -> None:
        self._set_capture_state(params, pause=True)

    def _resume_capture(self, params: dict[str, Any]) -> None:
        self._set_capture_state(params, pause=False)

    def _set_capture_state(self, params: dict[str, Any], pause: bool) -> None:
        modules = params.get("modules", [])
        if not modules:
            targets = self._captures
        else:
            targets = [c for c in self._captures if getattr(c, "capture_name", None) in modules]

        for cap in targets:
            try:
                if pause and getattr(cap, "is_running", False):
                    cap.stop()
                elif not pause and not getattr(cap, "is_running", False):
                    cap.start()
            except Exception as exc:
                logger.warning("Failed to update capture state: %s", exc)

    def _notify(self, params: dict[str, Any], event: dict[str, Any]) -> None:
        channel = params.get("channel")
        message_template = params.get("message", "")
        if not message_template:
            return
        message = _format_message(message_template, event)

        try:
            if channel:
                transport = create_transport_for_method(self._config, channel)
            else:
                transport = create_transport_for_method(
                    self._config, self._config.get("transport", {}).get("method", "email")
                )
        except Exception as exc:
            logger.warning("Failed to create transport for notify: %s", exc)
            return

        if transport is None:
            logger.warning("create_transport_for_method returned None for channel=%s", channel)
            return

        metadata = {
            "content_type": "text/plain",
            "subject": params.get("subject", "Rule notification"),
            "caption": params.get("subject", "Rule notification"),
            "filename": params.get("filename", "notification.txt"),
        }
        try:
            transport.connect()
            transport.send(message.encode("utf-8"), metadata)
        except Exception as exc:
            logger.warning("Notify send failed: %s", exc)
        finally:
            try:
                transport.disconnect()
            except Exception:
                pass


def _format_message(template: str, event: dict[str, Any]) -> str:
    context = {}
    context.update(event)
    if isinstance(event.get("context"), dict):
        context.update(event.get("context", {}))
    try:
        return template.format(**context)
    except Exception:
        return template
