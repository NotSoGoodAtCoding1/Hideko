"""Tests for tools.registry and tools.scheduler."""

import heapq
import threading
import time
from uuid import uuid4

import pytest

import events

from tools.registry import Tool, ToolRegistry, ToolResult
from tools.scheduler import Scheduler


class DummyTool(Tool):
    """Dummy tool for testing."""

    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(ok=True, text=f"Dummy executed with {kwargs}")


def test_tool_result_ok():
    """ToolResult can be constructed with ok=True."""
    result = ToolResult(ok=True, text="Hello")
    assert result.ok is True
    assert result.text == "Hello"
    assert result.error is None


def test_tool_result_error():
    """ToolResult can be constructed with ok=False and error."""
    result = ToolResult(ok=False, error="Something went wrong")
    assert result.ok is False
    assert result.error == "Something went wrong"
    assert result.text is None


def test_register_and_get():
    """Register a tool, get it back by name."""
    registry = ToolRegistry()
    tool = DummyTool("test_tool")
    registry.register(tool)

    assert registry.get("test_tool") is not None
    assert registry.get("missing") is None


def test_register_replaces():
    """Re-registering the same name replaces the tool."""
    registry = ToolRegistry()
    first = DummyTool("replacable")
    second = DummyTool("replacable")  # Same name, different instance
    registry.register(first)
    registry.register(second)

    retrieved = registry.get("replacable")
    assert retrieved is second


def test_execute_unknown_tool():
    """Executing an unknown tool returns ok=False with error message."""
    registry = ToolRegistry()
    result = registry.execute("no_such_tool")

    assert result.ok is False
    assert "unknown tool" in result.error.lower()


def test_execute_tool_raises_returns_error():
    """If a tool's execute raises, registry returns ok=False and never propagates."""

    class FailingTool(Tool):
        name = "failing"

        def execute(self, **kwargs) -> ToolResult:
            raise ValueError("Crash!")

    registry = ToolRegistry()
    registry.register(FailingTool())

    result = registry.execute("failing")

    assert result.ok is False
    assert "crash" in result.error.lower()


def test_names_sorted():
    """names() returns sorted list of registered tool names."""
    registry = ToolRegistry()
    b_tool = DummyTool("b")
    a_tool = DummyTool("a")
    c_tool = DummyTool("c")

    registry.register(b_tool)
    registry.register(a_tool)
    registry.register(c_tool)

    assert registry.names() == ["a", "b", "c"]


def test_scheduler_start_stop_idempotent():
    """Starting twice, stopping once; thread alive after start, not after stop."""

    class DummyBus:
        def publish(self, *args):
            pass

    scheduler = Scheduler(DummyBus())

    assert scheduler._thread is None

    # Start first time
    scheduler.start()
    assert scheduler._thread is not None
    assert scheduler._thread.is_alive()

    # Start second time (idempotent)
    scheduler.start()
    # Thread should still be the same one, still alive

    # Stop
    scheduler.stop(timeout_s=0.5)

    assert scheduler._thread is None or not scheduler._thread.is_alive()


def test_scheduler_fires_callback():
    """Schedule a callback after 0.05s; wait on event; assert fired within 1s."""

    class DummyBus:
        def publish(self, *args):
            pass

    fired = threading.Event()
    scheduler = Scheduler(DummyBus())

    with scheduler:
        job_id = scheduler.schedule(fired.set, delay_seconds=0.05)

        # Wait for the event (with timeout to fail if something is wrong)
        assert fired.wait(timeout=1.0) is True, "Callback did not fire within 1s"

    # Clean shutdown
    scheduler.stop(timeout_s=0.5)


def test_scheduler_cancel_pending():
    """Schedule a job with long delay, cancel it, fire remaining jobs."""

    class DummyBus:
        def publish(self, *args):
            pass

    fired = threading.Event()
    scheduler = Scheduler(DummyBus())

    with scheduler:
        # Schedule two jobs that both set the fired event
        job1 = scheduler.schedule(fired.set, delay_seconds=0.1)
        job2 = scheduler.schedule(fired.set, delay_seconds=0.5)  # Also sets fired

        # Cancel the first one
        assert scheduler.cancel(job1) is True
        assert scheduler.cancel(job1) is False  # Already cancelled

        # Wait for the second job to fire (and set fired)
        assert fired.wait(timeout=2.0) is True

    scheduler.stop(timeout_s=0.5)


def test_scheduler_callback_exception_isolated():
    """One callback raises; a second scheduled callback still runs."""

    class DummyBus:
        def publish(self, *args):
            pass

    results = []

    def failing_cb() -> None:
        raise RuntimeError("Boom!")

    def success_cb() -> None:
        results.append("ok")

    scheduler = Scheduler(DummyBus())

    with scheduler:
        # Schedule two jobs
        job1 = scheduler.schedule(failing_cb, delay_seconds=0.1)
        job2 = scheduler.schedule(success_cb, delay_seconds=0.2)

        # Wait for both to have been attempted
        time.sleep(0.5)

    scheduler.stop(timeout_s=0.5)

    # The second callback should still have run despite the first failing
    assert results == ["ok"]
