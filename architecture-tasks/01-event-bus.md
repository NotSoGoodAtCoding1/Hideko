# Task 01 — Event bus core

**Depends on task 00. Touch at most 2 files.** Do not touch `main.py` or `cli.py`.

## Goal

Create `events.py`: a tiny, thread-safe event bus with no dependencies on the rest of the app. Nothing publishes to it yet — that is task 03. Tests only.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Standard library only (`dataclasses`, `time`, `threading`, `logging`, `typing`, `collections.abc`).
- No `print()` anywhere in `events.py`. Log with `logging.getLogger(__name__)`.
- Type hints + docstrings on all public classes/functions. No bare `except:`.
- `python -m pytest -q` must pass with no mic/server.

## Exact code to create

Create `events.py` with this content (you may add docstrings, but keep signatures and behaviour identical):

```python
"""Minimal thread-safe event bus for Hideko.

Other modules publish events here; consumers (console, avatar, tools) subscribe.
Handlers must be fast and non-blocking — they may later be called from timer or
renderer threads. A failing handler is logged and skipped; it never stops the
publisher or the other handlers.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

ALL = "*"


@dataclass(frozen=True)
class Event:
    """One immutable-ish event; `data` is a plain dict for easy unpacking."""

    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("Event.kind must be a non-empty string")


class EventBus:
    """Publish/subscribe bus with wildcard support and error isolation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handlers: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(
        self,
        kinds: str | Iterable[str],
        handler: Callable[[Event], None],
    ) -> None:
        """Register `handler` for one kind, several kinds, or ALL ("*")."""
        if not callable(handler):
            raise TypeError("handler must be callable")
        keys = [ALL] if isinstance(kinds, str) and kinds == ALL else (
            [kinds] if isinstance(kinds, str) else list(kinds)
        )
        if not keys:
            raise ValueError("at least one event kind is required")
        with self._lock:
            for key in keys:
                if not isinstance(key, str) or not key:
                    raise ValueError("event kinds must be non-empty strings")
                listeners = self._handlers.setdefault(key, [])
                if handler not in listeners:
                    listeners.append(handler)

    def unsubscribe(self, handler: Callable[[Event], None]) -> None:
        """Remove `handler` from every kind it was registered on."""
        with self._lock:
            for listeners in self._handlers.values():
                if handler in listeners:
                    listeners.remove(handler)

    def publish(self, kind: str, **data: Any) -> None:
        """Publish an event. Handler failures are logged, never propagated."""
        event = Event(kind=kind, data=data)
        with self._lock:
            listeners = list(self._handlers.get(ALL, [])) + list(
                self._handlers.get(kind, [])
            )
        for handler in listeners:
            try:
                handler(event)
            except Exception as exc:  # deliberately broad: a subscriber must not kill the voice loop
                logger.exception("event handler failed for %r: %s", kind, exc)

    def clear(self) -> None:
        """Remove all subscribers. Intended for tests only."""
        with self._lock:
            self._handlers.clear()
```

## Tests — create `tests/test_events.py`

Cover:

- `test_publish_reaches_subscriber` — subscribe to `"heard"`, publish `heard(text="hello")`, assert one call with `event.kind == "heard"` and `event.data["text"] == "hello"`.
- `test_wildcard_receives_everything` — subscribe to `ALL`, publish `"heard"` and `"thinking"`, assert two calls.
- `test_unsubscribed_kind_ignored` — subscribe to `"heard"`, publish `"thinking"`, assert zero calls.
- `test_unsubscribe` — subscribe then unsubscribe, publish, assert zero calls.
- `test_duplicate_subscribe_is_noop` — subscribe the same handler twice to the same kind, publish, assert exactly one call.
- `test_bad_handler_does_not_block_others` — one handler raises `RuntimeError`, a second records; publish; assert the second still ran and `caplog` contains `event handler failed`.
- `test_handler_cannot_break_publish_return` — publish returns `None` even when a handler raises.
- `test_thread_safety` — 4 threads each publish 100 events to one subscriber; use a `threading.Lock` in the recorder; assert exactly 400 calls. Keep under 5 seconds.
- `test_event_validation` — `Event("")` raises `ValueError`; `Event("heard")` has empty `data` and `at > 0`.
- `test_subscribe_validation` — non-callable handler raises `TypeError`; empty kind list raises `ValueError`.

Do not use `sleep`; use `threading.Thread.join()` in the thread test.

## Verification

```powershell
python -m pytest -q
python -m pytest -q tests/test_events.py -v
python -c "import events; print(events.ALL); b=events.EventBus(); b.subscribe('x', lambda e: print(e.kind)); b.publish('x')"
```

Expected:

- All tests pass.
- The one-liner prints `*` then `x` (the lambda printing here is in a script, not library code — allowed).

## Stop and ask the human if

- You think `Event` should be fully immutable — keep the frozen dataclass as specified and ask; do not change the contract silently.
- A test needs a sleep longer than 5 seconds — simplify it and report instead.
