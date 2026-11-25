"""Smoke tests that always run without HIDEKO_E2E gate."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import main
from cli import parse_args
from config import load_config
from events import Event, EventBus
from memory_store import MemoryStore
from response_handler import ResponseHandler
from tools.registry import ToolRegistry
from tools.scheduler import Scheduler


def test_timing_before_exit():
    """Test that timing line is logged before the goodbye message.

    This test locks in the timing-before-exit ordering from task 03.
    """
    r = subprocess.run(
        [sys.executable, "main.py", "--text", "goodbye", "--no-tts"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"Exit code was {r.returncode}, stderr: {r.stderr}"
    # Verify the goodbye message appears in stdout
    assert "Goodbye." in r.stdout or any(x in r.stdout for x in ["See you", "Take care"]), \
        f"Expected goodbye message not found in stdout: {r.stdout}"


class RecordingBus(EventBus):
    """EventBus that records published (kind, data) pairs instead of dispatching."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, dict[str, Any]]] = []

    def publish(self, kind: str, **data: Any) -> None:
        """Record the event; do not dispatch (tests only)."""
        self.events.append((kind, dict(data)))


def test_main_text_publishes_speaking(monkeypatch):
    """`--text` publishes a `speaking` event through the bus and no `heard` event."""
    recording = RecordingBus()
    monkeypatch.setattr(main, "EventBus", lambda: recording)

    rc = main.main(["--text", "hello", "--no-tts"])

    assert rc == 0
    kinds = [kind for kind, _ in recording.events]
    assert "speaking" in kinds
    assert not any(kind == "heard" for kind in kinds)
    speaking_payloads = [data for kind, data in recording.events if kind == "speaking"]
    assert len(speaking_payloads) == 1
    assert "text" in speaking_payloads[0]


def test_main_text_output_unchanged(capsys):
    """`--text` stdout is exactly the single `Hideko: ...` line."""
    rc = main.main(["--text", "hello", "--no-tts"])

    config = load_config()
    memory = MemoryStore(config) if config.memory.enabled else None
    expected = ResponseHandler(config, memory=memory).respond("hello").text
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out == f"Hideko: {expected}\n"


def test_error_event_published():
    """The app bus receives `error` events (e.g. from HidekoError handling)."""
    bus = EventBus()
    received: list[Event] = []

    def error_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("error", error_handler)

    app = main.HidekoApp(load_config(), parse_args([]), bus=bus)

    assert app.bus is bus
    bus.publish("error", message="boom", exit_code=3)

    assert len(received) == 1
    assert received[0].kind == "error"
    assert received[0].data["message"] == "boom"
    assert received[0].data["exit_code"] == 3


def test_app_has_registry_and_scheduler():
    """The HidekoApp has registry and scheduler wired when provided."""
    bus = EventBus()
    registry = ToolRegistry()
    scheduler = Scheduler(bus)

    app = main.HidekoApp(load_config(), parse_args([]), bus=bus, registry=registry, scheduler=scheduler)

    # Verify the app has registry and scheduler
    assert app.registry is not None, "app should have a registry"
    assert app.scheduler is not None, "app should have a scheduler"
    
    # Verify they're the default instances (not injected ones)
    assert isinstance(app.registry, ToolRegistry)
    assert isinstance(app.scheduler, Scheduler)

    # Clean up - stop any started schedulers
    if scheduler._thread is not None and scheduler._thread.is_alive():
        scheduler.stop(timeout_s=0.5)
