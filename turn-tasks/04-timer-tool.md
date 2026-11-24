# Task 04 — Timer tool + tests

**Depends on task 03. Touch at most 5 files.** Do not touch `main.py`, `response_handler.py`, `turn_state.py`, or `config.yaml` (except adding triggers to YAML).

## Goal

Implement a real `TimerTool` that proves the registry+scheduler+turn-flow infrastructure: user says "set a timer for X minutes/seconds", the trigger matches with `tool: set_timer`, the tool schedules a background callback, and when it fires it publishes `timer_finished` and queues speech for the next turn. Add triggers and validator support for the `tool` key.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No new dependencies. Uses `tools.registry.Tool`, `ToolResult`, `tools.scheduler.Scheduler`, `events.EventBus`.
- No `print()` in library code outside `__main__`.
- `python -m pytest -q` passes offline. Timer tests use monkeypatched time / fake scheduler — no real 5-minute waits.
- Trigger YAML additions must pass `scripts/validate_responses.py`.

## Exact code to create — `tools/timer_tool.py`

```python
"""Timer tool for Hideko.

Schedules a delayed callback that publishes `timer_finished` on the event bus
and queues speech for the next turn. Execution of `execute()` is instant; the
actual delay happens on the scheduler background thread.
"""
from __future__ import annotations

import logging
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

        `minutes` and/or `seconds` specify the delay. `text` is the optional
        spoken message when the timer fires. Returns immediately.
        """
        delay = 0.0
        if minutes is not None:
            delay += float(minutes) * 60.0
        if seconds is not None:
            delay += float(seconds)
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
```

## Wire the timer tool into main.py

**`main()`** — after `scheduler.start()`, create and register the timer tool. `HidekoApp` needs a `_queue_speech` method:

```python
    def _queue_speech(self, text: str) -> None:
        """Thread-safe: queue text to be spoken at the start of the next loop."""
        with self._speech_lock:
            self._pending_speech.append(text)
```

In `main()`, after creating registry/scheduler:
```python
    timer_tool = TimerTool(scheduler, bus, app._queue_speech)  # app created below — reorder
```

Problem: `app` is created after. Fix: create app first, then register:
```python
    app = HidekoApp(config, opts, bus=bus, registry=registry, scheduler=scheduler)
    timer_tool = TimerTool(scheduler, bus, app._queue_speech)
    registry.register(timer_tool)
```

**`responses/triggers.yaml`** — add a timer trigger. Pick a sensible spot, e.g. after `stop`:
```yaml
  - name: set_timer
    priority: 90
    should_exit: false
    tool: set_timer
    patterns:
      - set a timer
      - set timer
      - start timer
      - timer
      - countdown
    responses:
      - "I will set the timer."
```

Keep every existing trigger unchanged.

**`scripts/validate_responses.py`** — allow `tool` key:
```python
        extra_keys = actual_keys - required_keys - {"should_exit", "llm_only", "tool"}
```
And add validation:
```python
        if "tool" in trigger and not isinstance(trigger["tool"], str):
            failures.append(f"{path}:{line_num}: tool must be a string")
```

## Tests — create `tests/test_timer_tool.py`

- `test_timer_tool_name` — `TimerTool(...).name == "set_timer"`.
- `test_timer_tool_minutes_only` — execute with `minutes=1`; assert `ok=True`, text contains "minute"; scheduler has 1 pending job.
- `test_timer_tool_seconds_only` — execute with `seconds=30`; assert ok.
- `test_timer_tool_both` — `minutes=1, seconds=30` → delay 90s.
- `test_timer_tool_no_duration` — execute with no args → `ok=False`, error about positive duration.
- `test_timer_tool_zero_duration` — `minutes=0` → `ok=False`.
- `test_timer_fires_and_queues_speech` — monkeypatch `time.monotonic` or use a tiny delay (0.05s), execute, start scheduler, wait for job to fire (threading.Event in callback), assert `timer_finished` published and speech queued. Then stop scheduler.
- `test_trigger_has_tool_key` — construct `ResponseHandler` with real config, find the `set_timer` trigger, assert `.tool == "set_timer"`.
- `test_validator_accepts_tool_key` — run validator against real `responses/triggers.yaml`, assert no failures mentioning `tool`.

For the firing test, keep under 2 seconds:
```python
def test_timer_fires_quickly(monkeypatch):
    fired = threading.Event()
    messages = []
    scheduler = Scheduler(EventBus())
    def fire():
        messages.append("fired")
        fired.set()
    job_id = scheduler.schedule(fire, 0.05)
    scheduler.start()
    assert fired.wait(timeout=2.0)
    scheduler.stop()
    assert fired.is_set()
```

## Verification

```powershell
python -m pytest -q
python -m pytest -q tests/test_timer_tool.py tests/test_tools.py -v
python scripts\validate_responses.py
python main.py --text "set a timer" --no-tts
```

Expected:

- All tests pass.
- `validate_responses.py` exits 0, `OK: 16 triggers` (was 15, +1 timer).
- `main.py --text "set a timer" --no-tts` → speaks canned response "I will set the timer.", `response.tool_action == "set_timer"`, registry executes timer tool and schedules a job. No crash.
- No timer actually waits 5 minutes in tests.

## Stop and ask the human if

- You want the timer to actually speak when it fires (requires interrupting TTS playback) — v1 queues it for next turn; interrupting is phase 3.
- You want different trigger phrases for the timer — adjust patterns and tell me.
- `validate_responses.py` structure differs from the snippet — show it and ask.
