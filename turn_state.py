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

from events import Event, EventBus

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
        
        # Build event data dict
        data: dict[str, Any] = {
            "from_state": old_state.value,
            "to_state": new_state.value,
            **event_data,
        }
        
        # Publish outside the lock; EventBus is itself thread-safe.
        self._bus.publish("turn_state_changed", **data)
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
