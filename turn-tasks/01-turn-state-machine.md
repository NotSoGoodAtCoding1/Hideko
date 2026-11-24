# Task 01 — Turn state machine

**Depends on task 00. Touch at most 3 files.** Do not touch `response_handler.py`, `cli.py`, `events.py`, or `event_outputs.py`.

## Goal

Extract the inline loop state from `main.py::run()` into a `TurnController` class with an explicit `TurnState` enum. State changes publish `turn_state_changed` events on the bus so future tools/avatar can observe state without parsing console output. CLI output must remain byte-for-byte identical.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Standard library only (`enum`, `dataclasses`, `threading`, `typing`, `time`).
- No `print()` in `turn_state.py`. Log with `logging.getLogger(__name__)`.
- `python -m pytest -q` passes offline with no mic/server.

## Exact code to create — `turn_state.py`

```python
"""Turn state machine for Hideko's main loop.

Centralizes the conversational state that was previously tracked across
scattered booleans in main.py (paused, listening_shown, wake_word_detected).
State transitions publish bus events so tools and avatar subscribers can
react without parsing console output.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from events import EventBus

logger = logging.getLogger(__name__)


class TurnState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PAUSED = "paused"
    WAITING_FOR_WAKE_WORD = "waiting_for_wake_word"


@dataclass(frozen=True)
class TurnStateChanged:
    """Immutable record of a state transition."""
    from_state: str
    to_state: str
    at: float = field(default_factory=time.time)


class TurnController:
    """Tracks Hideko's conversational state and publishes transitions."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._lock = threading.RLock()
        self._state = TurnState.IDLE

    @property
    def state(self) -> TurnState:
        """Current turn state."""
        with self._lock:
            return self._state

    def transition(self, new_state: TurnState, **event_data: Any) -> None:
        """Transition to a new state and publish an event.

        Publishing happens outside the lock so a slow subscriber cannot block
        state mutations. The event carries the previous and new state plus any
        caller-supplied data.
        """
        with self._lock:
            old_state = self._state
            self._state = new_state
            event = TurnStateChanged(
                from_state=old_state.value,
                to_state=new_state.value,
                **event_data,
            )
        # Publish outside the lock; EventBus is itself thread-safe.
        self._bus.publish("turn_state_changed", **event.__dict__)
        logger.debug("turn state %s -> %s", old_state.value, new_state.value)

    def is_speaking(self) -> bool:
        """True if currently in the SPEAKING state."""
        return self.state == TurnState.SPEAKING

    def is_listening(self) -> bool:
        """True if currently in the LISTENING state."""
        return self.state == TurnState.LISTENING

    def is_paused(self) -> bool:
        """True if currently in the PAUSED state."""
        return self.state == TurnState.PAUSED
```

## Tests — create `tests/test_turn_state.py`

- `test_initial_state_is_idle` — `TurnController(bus).state == TurnState.IDLE`.
- `test_transition_publishes_event` — subscribe to `turn_state_changed`, call `transition(TurnState.LISTENING)`, assert event kind and payload `from_state="idle"`, `to_state="listening"`.
- `test_transition_changes_state` — after transition, `.state` reflects new state.
- `test_is_speaking_is_listening_is_paused` — transition to each state, assert the corresponding property and that others are False.
- `test_unknown_event_data_passed_through` — `transition(TurnState.SPEAKING, text="hello")` publishes `text="hello"` in payload.
- `test_thread_safety` — 4 threads each call `transition` 100 times to random states; use a lock in a recording subscriber; assert exactly 400 events received. Keep under 5 seconds, no `sleep`.

## Steps to wire into main.py

**Import:** add `from turn_state import TurnController, TurnState` to `main.py`.

**`HidekoApp.__init__`:** change signature to `(self, config, opts, bus=None, status=None, turn=None)` and add:
```python
        self.turn = turn if turn is not None else TurnController(self.bus)
```

**`HidekoApp.setup()`:** after `self.bus.publish("ready", ...)` add:
```python
        self.turn.transition(TurnState.IDLE)
```

**`HidekoApp.run()` replacements** (replace exact lines, keep control flow identical):

| Location | Old | New |
|---|---|---|
| mute on | `self.bus.publish("paused")` | `self.bus.publish("paused")\n                        self.turn.transition(TurnState.PAUSED)` |
| mute off | `self.bus.publish("listening")` | `self.bus.publish("listening")\n                        self.turn.transition(TurnState.LISTENING)` |
| paused flush continue | `if self._paused:` block | unchanged, but after `continue` the state is PAUSED |
| read block / first listening | `if not self._listening_shown:\n                    self.bus.publish("listening")` | `self.turn.transition(TurnState.LISTENING)` (remove the `_listening_shown` guard for this publish — publish on every transition into listening) |
| wake word timeout | `self.bus.publish("listening")` | `self.bus.publish("listening")\n                        self.turn.transition(TurnState.LISTENING)` |
| wake word detected | after `self.bus.publish("wake_detected", ...)` | `self.turn.transition(TurnState.WAITING_FOR_WAKE_WORD)` before the `continue`? No — when wake word IS detected we exit wake mode, so transition to LISTENING. When NOT wake word, transition to WAITING_FOR_WAKE_WORD. |
| not wake word | `# Not a wake word, loop back...` + `continue` | add `self.turn.transition(TurnState.WAITING_FOR_WAKE_WORD)` before continue |
| thinking | `self.bus.publish("thinking")` | `self.bus.publish("thinking")\n                self.turn.transition(TurnState.THINKING)` |
| speaking | both `self.bus.publish("speaking", ...)` branches | add `self.turn.transition(TurnState.SPEAKING)` after publish |
| goodbye | `self.bus.publish("goodbye")` | add `self.turn.transition(TurnState.IDLE)` before break |
| turn end | after half-duplex flush | `self.turn.transition(TurnState.IDLE)` |
| error exit | `sys.exit(...)` | `self.turn.transition(TurnState.IDLE)` before sys.exit? Optional — app is ending. Leave as-is; add IDLE transition before break/exit for cleanliness. |

**Remove now-redundant fields:** `self._listening_shown` can be removed since state drives it; `self._paused` can be replaced by `self.turn.is_paused()`. Keep them if removal risks breaking tests — mark as "optional cleanup".

**`main()`:** change `app = HidekoApp(config, opts, bus=bus)` to `app = HidekoApp(config, opts, bus=bus, turn=turn)`? No — `turn` is created inside `__init__` by default. Just pass bus as before.

## Verification

```powershell
python -m pytest -q
python -m pytest -q tests/test_turn_state.py -v
python main.py --text "hello" --no-tts
python main.py --text "goodbye" --no-tts
```

Expected:

- All tests pass.
- `--text "hello"` → `Hideko: ...` exactly as before.
- `--text "goodbye"` → farewell exactly as before.

## Stop and ask the human if

- Removing `_listening_shown`/`_paused` breaks an existing test — keep them and report.
- You're unsure where to place the wake-word WAITING_FOR_WAKE_WORD transition — show the diff and ask.
