"""Output adapters for Hideko events.

ConsoleSubscriber deliberately prints: it is the boundary where events become
terminal text, replacing the old direct Status calls in main.py. No other
library module prints outside its __main__ block.
"""
from __future__ import annotations

import logging
from typing import Any

from cli import Status
from events import Event

logger = logging.getLogger(__name__)


class ConsoleSubscriber:
    """Turn events into the exact console lines Hideko already produces."""

    def __init__(self, status: Status | None = None) -> None:
        self.status = status if status is not None else Status()

    def handle(self, event: Event) -> None:
        """Emit one event to the console."""
        kind = event.kind
        data: dict[str, Any] = event.data
        if kind == "listening":
            self.status.listening()
        elif kind == "paused":
            self.status.paused()
        elif kind == "thinking":
            self.status.thinking()
        elif kind == "heard":
            self.status.heard(str(data.get("text", "")))
        elif kind == "speaking":
            self.status.say(str(data.get("text", "")))
        elif kind == "calibrating":
            print("Stay quiet for 1 second — calibrating...")
        elif kind == "wake_detected":
            print(f"  [wake word detected in {float(data.get('latency_s', 0.0)):.1f}s]")
        elif kind == "missed":
            print("  (didn't catch that)")
        elif kind == "turn_timing":
            print(
                f"  [stt {float(data.get('stt', 0.0)):.1f}s "
                f"| resp {float(data.get('resp', 0.0)):.2f}s "
                f"| tts {float(data.get('tts', 0.0)):.2f}s "
                f"| play {float(data.get('play', 0.0)):.2f}s "
                f"| total {float(data.get('total', 0.0)):.1f}s]"
            )
        elif kind == "error":
            print(f"  ({data.get('message', '')})")
        elif kind == "goodbye":
            print("\nGoodbye.")
        # startup / ready / shutdown and unknown kinds are intentionally silent.


class LoggingSubscriber:
    """Log every event at DEBUG, redacting transcripts when asked."""

    def __init__(self, log_transcripts: bool = True) -> None:
        self._log_transcripts = log_transcripts

    def handle(self, event: Event) -> None:
        """Write one DEBUG log line for the event."""
        data = dict(event.data)
        if not self._log_transcripts and "text" in data:
            data["text"] = "***REDACTED***"
        logger.debug("event %s %s", event.kind, data)
