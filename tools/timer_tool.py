"""Timer tool for Hideko.

Schedules a delayed callback that publishes `timer_finished` on the event bus
and queues speech for the next turn. Execution of `execute()` is instant; the
actual delay happens on the scheduler background thread.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from events import EventBus
from tools.registry import Tool, ToolResult
from tools.scheduler import Scheduler

logger = logging.getLogger(__name__)


class TimerTool(Tool):
    """Set a countdown timer that fires on the scheduler thread."""

    name = "set_timer"

    def __init__(
        self,
        scheduler: Scheduler,
        bus: EventBus,
        queue_speech: Callable[[str], None],
    ) -> None:
        self._scheduler = scheduler
        self._bus = bus
        self._queue_speech = queue_speech

    def execute(
        self,
        minutes: float | None = None,
        seconds: float | None = None,
        text: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Schedule a timer.

        `minutes` and/or `seconds` specify the delay (from explicit params).
        If not provided, parses duration from `text`: "5 minutes", "10 seconds",
        etc. Returns immediately.
        """
        # Parse duration from text if not explicitly set via minutes/seconds kwargs
        parsed_minutes = None
        parsed_seconds = None

        if minutes is None and seconds is None and text:
            text_lower = text.lower()
            # Try to extract minutes first (e.g., "5 minutes")
            m_min = re.search(r"(\d+)\s*(minutes?|mins?)", text_lower)
            # Also try seconds (e.g., "10 seconds") - this pattern comes after minutes in the string
            m_sec = None
            if not m_min:
                m_sec = re.search(r"(\d+)\s*seconds?", text_lower)
            else:
                # If both patterns could match, prefer the first one (minutes usually come before seconds in speech)
                m_sec = re.search(r"(?<!\S)(\d+)\s*seconds?\b", text_lower)  # Standalone "X seconds"
            
            if m_min:
                parsed_minutes = float(m_min.group(1))
            elif m_sec:
                parsed_seconds = float(m_sec.group(1))

        # Calculate delay: explicit params take precedence, then parsed values
        delay = 0.0
        if minutes is not None:
            delay += float(minutes) * 60.0
        elif parsed_minutes is not None:
            delay = parsed_minutes * 60.0

        if seconds is not None:
            delay += float(seconds)
        elif parsed_seconds is not None and parsed_minutes is None:
            delay = parsed_seconds

        if delay <= 0.0:
            return ToolResult(ok=False, error="timer duration must be positive")

        def fire() -> None:
            message = text or f"Your timer for {delay:.0f} seconds is up!"
            self._bus.publish("timer_finished", message=message, delay=delay)
            self._queue_speech(message)
            logger.info("timer fired: %s", message)

        job_id = self._scheduler.schedule(fire, delay)
        logger.debug("timer job %s scheduled for %.1fs", job_id, delay)
        return ToolResult(
            ok=True,
            text=f"I've set a timer for {int(delay // 60)} minutes and {int(delay % 60)} seconds.",
        )
