# Task 02 — Console & logging subscribers

**Depends on task 01. Touch at most 3 files.** Do not touch `main.py`.

## Goal

Create `event_outputs.py` with subscribers that turn events into **exactly the console output Hideko produces today**, plus a debug logger subscriber. Add a probe script so the output can be verified without a mic.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Import `Event` from `events` and `Status` from `cli` in `event_outputs.py`.
- No `print()` in `event_outputs.py` outside `if __name__ == "__main__":` — **except** through `Status` methods or explicit `print` calls inside `ConsoleSubscriber.handle`, which is a deliberate output adapter. Document that exception in the module docstring. (Library code elsewhere must not print.)
- Type hints + docstrings. No bare `except:`.
- `python -m pytest -q` passes offline.

## Current console strings (must be preserved exactly)

From `cli.py::Status` and `main.py`:

| Trigger | Exact output |
|---|---|
| `listening` | `Status.listening()` → `[listening]` |
| `paused` | `Status.paused()` → `[paused — press m to resume]` |
| `thinking` | `Status.thinking()` → `  ...thinking\r` with `end=""` |
| `heard(text)` | `Status.heard(text)` → `You:    {text}` |
| `speaking(text)` | `Status.say(text)` → `Hideko: {text}` |
| `calibrating` | `print("Stay quiet for 1 second — calibrating...")` |
| `wake_detected(latency_s)` | `print(f"  [wake word detected in {latency_s:.1f}s]")` |
| `missed` | `print("  (didn't catch that)")` |
| `turn_timing(...)` | `print(f"  [stt {stt:.1f}s | resp {resp:.2f}s | tts {tts:.2f}s | play {play:.2f}s | total {total:.1f}s]")` |
| `error(message)` | `print(f"  ({message})")` |
| `goodbye` | `print("\nGoodbye.")` |
| `startup`, `ready`, `shutdown` | no console output (main already logs them) |
| unknown kinds | ignore |

## Exact code to create

`event_outputs.py`:

```python
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
```

Create `scripts/event_probe.py` (a script, so printing is allowed):

```python
#!/usr/bin/env python
"""Emit a realistic sequence of events through the console subscriber."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_outputs import ConsoleSubscriber  # noqa: E402
from events import ALL, EventBus  # noqa: E402

if __name__ == "__main__":
    bus = EventBus()
    bus.subscribe(ALL, ConsoleSubscriber().handle)
    bus.publish("calibrating")
    bus.publish("ready", stt_s=1.8, trigger_count=15)
    bus.publish("listening")
    bus.publish("thinking")
    bus.publish("heard", text="hello")
    bus.publish("speaking", text="Hello! I am Hideko.")
    bus.publish("turn_timing", stt=1.91, resp=0.0, tts=0.93, play=1.21, total=4.05)
    bus.publish("missed")
    bus.publish("wake_detected", text="hey hideko", latency_s=1.4)
    bus.publish("goodbye")
```

## Tests — create `tests/test_event_outputs.py`

- Parametrize over the table above: publish each event through `ConsoleSubscriber` with a `capsys` fixture and assert the exact stdout string. For `thinking`, assert `"\r" in out` and `out.endswith("  ...thinking")`.
- `test_ready_and_unknown_are_silent` — `ready`, `startup`, `shutdown`, `"wat"` produce no stdout.
- `test_missing_data_does_not_raise` — publish `heard` and `turn_timing` with no payload; no exception, output contains `You:    ` and `stt 0.0s`.
- `test_logging_subscriber_redacts` — with `log_transcripts=False`, publish `heard(text="secret")`; `caplog.text` contains `***REDACTED***` and not `secret`.
- `test_logging_subscriber_keeps_text` — with `True`, `caplog.text` contains `secret`.

## Verification

```powershell
python -m pytest -q
python scripts\event_probe.py
```

Expected:

- All tests pass.
- `event_probe.py` prints, in order:
  ```
  Stay quiet for 1 second — calibrating...
  [listening]
    ...thinkingYou:    hello
  Hideko: Hello! I am Hideko.
    [stt 1.9s | resp 0.00s | tts 0.93s | play 1.21s | total 4.0s]
    (didn't catch that)
    [wake word detected in 1.4s]

  Goodbye.
  ```
  (The `...thinking` line has no trailing newline, so `You:` follows it immediately — that matches current behaviour.)

## Stop and ask the human if

- An existing test asserts a console line you cannot reproduce exactly — show the diff and ask which format wins.
- You believe `ConsoleSubscriber` printing violates the no-print rule — it is the deliberate adapter; keep it and note it in your report.
