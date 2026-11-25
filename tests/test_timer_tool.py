"""Tests for TimerTool."""
import threading
from pathlib import Path

import pytest

from events import EventBus
from tools.scheduler import Scheduler
from tools.timer_tool import TimerTool

# Test data files
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRIGGERS_PATH = PROJECT_ROOT / "responses" / "triggers.yaml"


@pytest.fixture
def scheduler():
    """Provide a fresh Scheduler with started background thread."""
    bus = EventBus()
    scheduler = Scheduler(bus)
    scheduler.start()
    yield scheduler
    scheduler.stop()


class DummyScheduler:
    """Mock scheduler for tests that don't need the real one."""
    def __init__(self):
        self._jobs = []
        self._lock = threading.Lock()

    def schedule(self, callback, delay):
        """Schedule a job - just records it for testing."""
        with self._lock:
            import uuid
            job_id = uuid.uuid4().hex
            self._jobs.append((job_id, delay, callback))
        return job_id


def test_timer_tool_name(scheduler):
    """TimerTool.name must be 'set_timer'."""
    bus = EventBus()
    tool = TimerTool(scheduler, bus, lambda x: None)
    assert tool.name == "set_timer"


def test_timer_tool_minutes_only():
    """Execute with minutes=1; assert ok=True, text contains 'minute'."""
    bus = EventBus()
    scheduler = DummyScheduler()

    def queue_speech(text):
        pass

    tool = TimerTool(scheduler, bus, queue_speech)
    result = tool.execute(minutes=1)

    assert result.ok is True
    assert "minute" in result.text.lower()


def test_timer_tool_seconds_only():
    """Execute with seconds=30; assert ok."""
    bus = EventBus()
    scheduler = DummyScheduler()

    def queue_speech(text):
        pass

    tool = TimerTool(scheduler, bus, queue_speech)
    result = tool.execute(seconds=30)
    assert result.ok is True
    assert "30" in result.text


def test_timer_tool_both():
    """Execute with minutes=1, seconds=30; delay should be 90s."""
    bus = EventBus()
    scheduler = DummyScheduler()

    def queue_speech(text):
        pass

    tool = TimerTool(scheduler, bus, queue_speech)
    result = tool.execute(minutes=1, seconds=30)
    assert result.ok is True
    assert "1 minutes" in result.text
    assert "30 seconds" in result.text


def test_timer_tool_no_duration():
    """Execute with no args; assert ok=False, error about positive duration."""
    bus = EventBus()
    scheduler = DummyScheduler()

    def queue_speech(text):
        pass

    tool = TimerTool(scheduler, bus, queue_speech)
    result = tool.execute()
    assert result.ok is False
    assert "positive" in result.error.lower()


def test_timer_tool_zero_duration():
    """Execute with minutes=0; assert ok=False."""
    bus = EventBus()
    scheduler = DummyScheduler()

    def queue_speech(text):
        pass

    tool = TimerTool(scheduler, bus, queue_speech)
    result = tool.execute(minutes=0)
    assert result.ok is False
    assert "positive" in result.error.lower()


def test_timer_parsing_from_text():
    """Parse duration from user text like 'set a timer for 5 minutes'."""
    bus = EventBus()
    scheduler = DummyScheduler()

    def queue_speech(text):
        pass

    tool = TimerTool(scheduler, bus, queue_speech)
    
    # Test parsing "5 minutes"
    result = tool.execute(text="set a timer for 5 minutes")
    assert result.ok is True
    assert "5 minutes" in result.text
    
    # Test parsing "10 seconds"  
    result = tool.execute(text="timer for 10 seconds")
    assert result.ok is True
    assert "10 seconds" in result.text


def test_trigger_has_tool_key():
    """Load triggers.yaml and verify set_timer trigger has tool: 'set_timer'."""
    import yaml

    with open(TRIGGERS_PATH, "r") as f:
        data = yaml.safe_load(f)

    triggers = data.get("triggers", [])
    timer_trigger = None

    for t in triggers:
        if t.get("name") == "set_timer":
            timer_trigger = t
            break

    assert timer_trigger is not None, "set_timer trigger not found in triggers.yaml"
    assert timer_trigger["tool"] == "set_timer", f"Expected tool='set_timer', got {timer_trigger['tool']}"


def test_validator_accepts_tool_key():
    """Run validator on triggers.yaml; no failures for 'tool' key."""
    import subprocess

    result = subprocess.run(
        ["python", "scripts/validate_responses.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Validator failed:\n{result.stdout}\n{result.stderr}"
    assert "tool" not in result.stdout.lower(), "Validator mentioned 'tool' as an issue"
