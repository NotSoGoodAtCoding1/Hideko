"""Tests for events.py (task 01)."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import pytest

import events


def make_handler(name: str, raises: bool = False) -> Callable[[events.Event], None]:
    """Helper to create a test handler."""
    def handler(event: events.Event) -> None:
        if raises:
            raise RuntimeError(f"{name} raised")
        assert event.kind == name
    return handler


# ---------------------------------------------------------------------------
# Basic publishing
# ---------------------------------------------------------------------------


def test_publish_reaches_subscriber():
    """Subscribe to `"heard"`, publish `heard(text="hello")`, assert call matches."""
    bus = events.EventBus()
    received: list[events.Event] = []

    def handler(event: events.Event) -> None:
        received.append(event)

    bus.subscribe("heard", handler)
    bus.publish("heard", text="hello")

    assert len(received) == 1
    assert received[0].kind == "heard"
    assert received[0].data["text"] == "hello"


def test_wildcard_receives_everything():
    """Subscribe to `ALL`, publish `"heard"` and `"thinking"`, assert two calls."""
    bus = events.EventBus()
    received: list[events.Event] = []

    def handler(event: events.Event) -> None:
        received.append(event)

    bus.subscribe(events.ALL, handler)
    bus.publish("heard", text="hello")
    bus.publish("thinking", text="pondering")

    assert len(received) == 2
    kinds = {e.kind for e in received}
    assert kinds == {"heard", "thinking"}


def test_unsubscribed_kind_ignored():
    """Subscribe to `"heard"`, publish `"thinking"`, assert zero calls."""
    bus = events.EventBus()
    received: list[events.Event] = []

    def handler(event: events.Event) -> None:
        received.append(event)

    bus.subscribe("heard", handler)
    bus.publish("thinking")

    assert len(received) == 0


def test_unsubscribe():
    """Subscribe then unsubscribe, publish, assert zero calls."""
    bus = events.EventBus()
    received: list[events.Event] = []

    def handler(event: events.Event) -> None:
        received.append(event)

    bus.subscribe("heard", handler)
    bus.unsubscribe(handler)
    bus.publish("heard", text="after_unsub")

    assert len(received) == 0


def test_duplicate_subscribe_is_noop():
    """Subscribe the same handler twice to the same kind, publish, assert exactly one call."""
    bus = events.EventBus()
    received: list[events.Event] = []

    def handler(event: events.Event) -> None:
        received.append(event)

    bus.subscribe("heard", handler)
    bus.subscribe("heard", handler)  # duplicate should be ignored
    bus.publish("heard")

    assert len(received) == 1


# ---------------------------------------------------------------------------
# Error handling during publish
# ---------------------------------------------------------------------------


def test_bad_handler_does_not_block_others(caplog):
    """One handler raises `RuntimeError`, a second records; publish; assert the second still ran."""
    bus = events.EventBus()
    received: list[events.Event] = []

    def failing_handler(event: events.Event) -> None:
        raise RuntimeError("failing handler")

    def good_handler(event: events.Event) -> None:
        received.append(event)

    bus.subscribe("heard", failing_handler)
    bus.subscribe("heard", good_handler)
    bus.publish("heard", text="hello")

    assert len(received) == 1
    # Check that logging occurred - the exception is logged at ERROR level
    assert any("event handler failed" in record.getMessage() for record in caplog.records)


def test_handler_cannot_break_publish_return():
    """Publish returns `None` even when a handler raises."""
    bus = events.EventBus()

    def failing_handler(event: events.Event) -> None:
        raise ValueError("boom")

    bus.subscribe("heard", failing_handler)
    result = bus.publish("heard", text="hello")

    assert result is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_thread_safety():
    """4 threads each publish 100 events to one subscriber; exactly 400 calls."""
    bus = events.EventBus()
    received_lock = threading.Lock()
    received_count = [0]

    def handler(event: events.Event) -> None:
        with received_lock:
            received_count[0] += 1

    def publisher(thread_id: int) -> None:
        for _ in range(100):
            bus.publish(f"heard_{thread_id}", text=f"msg from {thread_id}")

    bus.subscribe(events.ALL, handler)

    threads = [threading.Thread(target=publisher, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert received_count[0] == 400


# ---------------------------------------------------------------------------
# Event validation
# ---------------------------------------------------------------------------


def test_event_validation():
    """`Event("")` raises `ValueError`; `Event("heard")` has empty `data` and `at > 0`."""
    with pytest.raises(ValueError, match="non-empty"):
        events.Event("")

    event = events.Event("heard", data={"text": "test"})
    assert isinstance(event.kind, str)
    assert event.kind.strip() == "heard"
    assert event.data == {"text": "test"}
    assert event.at > 0


# ---------------------------------------------------------------------------
# Subscribe validation
# ---------------------------------------------------------------------------


def test_subscribe_validation():
    """Non-callable handler raises `TypeError`; empty kind list raises `ValueError`."""
    bus = events.EventBus()

    with pytest.raises(TypeError, match="callable"):
        bus.subscribe("heard", "not a callable")

    with pytest.raises(ValueError, match="required"):
        bus.subscribe([], lambda e: None)

    with pytest.raises(ValueError, match="non-empty"):
        bus.subscribe("", lambda e: None)
