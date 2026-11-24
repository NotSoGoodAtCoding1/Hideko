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
