"""Tests for TurnController and TurnState."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from random import choice

import pytest

from events import Event, EventBus
from turn_state import TurnController, TurnState


def test_initial_state_is_idle() -> None:
    """New controller starts in IDLE state."""
    bus = EventBus()
    controller = TurnController(bus)
    assert controller.state == TurnState.IDLE


def test_transition_publishes_event() -> None:
    """Transition publishes turn_state_changed event with correct payload."""
    bus = EventBus()
    controller = TurnController(bus)

    # Subscribe to the event - handlers receive Event objects
    received_events = []

    def handler(event: Event) -> None:
        received_events.append((event.kind, event.data))

    bus.subscribe("turn_state_changed", handler)

    # Trigger transition
    controller.transition(TurnState.LISTENING)

    assert len(received_events) == 1
    event_kind, data = received_events[0]
    assert event_kind == "turn_state_changed"
    assert data["from_state"] == "idle"
    assert data["to_state"] == "listening"


def test_transition_changes_state() -> None:
    """State property reflects new state after transition."""
    bus = EventBus()
    controller = TurnController(bus)

    # Initial state should be IDLE
    assert controller.state == TurnState.IDLE

    # Transition to LISTENING
    controller.transition(TurnState.LISTENING)

    # State should now be LISTENING
    assert controller.state == TurnState.LISTENING


def test_is_speaking_is_listening_is_paused() -> None:
    """Helper methods return True only for their respective states."""
    bus = EventBus()
    controller = TurnController(bus)

    # Start from IDLE - all should be False
    assert not controller.is_speaking()
    assert not controller.is_listening()
    assert not controller.is_paused()

    # Transition to each state and verify
    for new_state in [TurnState.SPEAKING, TurnState.LISTENING, TurnState.PAUSED]:
        controller.transition(new_state)
        
        if new_state == TurnState.SPEAKING:
            assert controller.is_speaking(), "Expected is_speaking() to be True"
            assert not controller.is_listening(), "Expected is_listening() to be False"
            assert not controller.is_paused(), "Expected is_paused() to be False"
        elif new_state == TurnState.LISTENING:
            assert not controller.is_speaking(), "Expected is_speaking() to be False"
            assert controller.is_listening(), "Expected is_listening() to be True"
            assert not controller.is_paused(), "Expected is_paused() to be False"
        elif new_state == TurnState.PAUSED:
            assert not controller.is_speaking(), "Expected is_speaking() to be False"
            assert not controller.is_listening(), "Expected is_listening() to be False"
            assert controller.is_paused(), "Expected is_paused() to be True"


def test_unknown_event_data_passed_through() -> None:
    """Additional event data (e.g., text) is passed through in the payload."""
    bus = EventBus()
    controller = TurnController(bus)

    received_events = []

    def handler(event: Event) -> None:
        received_events.append((event.kind, event.data))

    bus.subscribe("turn_state_changed", handler)

    # Transition with extra data
    controller.transition(TurnState.SPEAKING, text="hello")

    assert len(received_events) == 1
    event_kind, data = received_events[0]
    assert event_kind == "turn_state_changed"
    assert data["from_state"] == "idle"
    assert data["to_state"] == "speaking"
    assert data["text"] == "hello"


def test_thread_safety() -> None:
    """Multiple threads calling transition concurrently do not corrupt state."""
    bus = EventBus()
    controller = TurnController(bus)

    received_events = []
    lock = threading.Lock()

    def handler(event: Event) -> None:
        with lock:
            received_events.append((event.kind, event.data))

    # Subscribe before starting threads
    bus.subscribe("turn_state_changed", handler)

    def worker():
        for _ in range(100):
            state = choice(list(TurnState))
            controller.transition(state)

    # Start 4 threads, each calling transition 100 times
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(worker) for _ in range(4)]
        for future in futures:
            future.result()

    # Should have exactly 400 events (4 threads * 100 transitions each)
    assert len(received_events) == 400, f"Expected 400 events, got {len(received_events)}"
