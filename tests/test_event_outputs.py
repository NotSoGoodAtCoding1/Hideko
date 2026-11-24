"""Tests for event_outputs.py (task 02)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from event_outputs import ConsoleSubscriber, LoggingSubscriber
from events import EventBus


def test_console_output_matches_known_strings(capsys):
    """Assert console output matches the exact strings from cli.py/main.py."""
    bus = EventBus()
    subscriber = ConsoleSubscriber()

    # listening
    bus.subscribe("listening", subscriber.handle)
    bus.publish("listening")
    assert "[listening]\n" == capsys.readouterr().out
    
    # paused  
    bus.subscribe("paused", subscriber.handle)
    bus.publish("paused")
    assert "[paused — press m to resume]\n" == capsys.readouterr().out
    
    # thinking (with \r at end - cursor returns to line start)
    bus.subscribe("thinking", subscriber.handle)
    bus.publish("thinking")
    assert "  ...thinking\r" == capsys.readouterr().out
    
    # heard
    bus.subscribe("heard", subscriber.handle)
    bus.publish("heard", text="hello")
    assert "You:    hello\n" == capsys.readouterr().out
    
    # speaking
    bus.subscribe("speaking", subscriber.handle)
    bus.publish("speaking", text="Hello! I am Hideko.")
    assert "Hideko: Hello! I am Hideko.\n" == capsys.readouterr().out
    
    # calibrating
    bus.subscribe("calibrating", subscriber.handle)
    bus.publish("calibrating")
    assert "Stay quiet for 1 second — calibrating...\n" == capsys.readouterr().out
    
    # wake_detected
    bus.subscribe("wake_detected", subscriber.handle)
    bus.publish("wake_detected", latency_s=1.4)
    assert "  [wake word detected in 1.4s]\n" == capsys.readouterr().out
    
    # missed
    bus.subscribe("missed", subscriber.handle)
    bus.publish("missed")
    assert "  (didn't catch that)\n" == capsys.readouterr().out
    
    # turn_timing
    bus.subscribe("turn_timing", subscriber.handle)
    bus.publish("turn_timing", stt=1.91, resp=0.0, tts=0.93, play=1.21, total=4.05)
    assert "  [stt 1.9s | resp 0.00s | tts 0.93s | play 1.21s | total 4.0s]\n" == capsys.readouterr().out
    
    # error
    bus.subscribe("error", subscriber.handle)
    bus.publish("error", message="timeout")
    assert "  (timeout)\n" == capsys.readouterr().out
    
    # goodbye
    bus.subscribe("goodbye", subscriber.handle)
    bus.publish("goodbye")
    assert "\nGoodbye.\n" == capsys.readouterr().out


def test_ready_and_unknown_are_silent(capsys):
    """`ready`, `startup`, `shutdown`, `"wat"` produce no stdout."""
    bus = EventBus()
    subscriber = ConsoleSubscriber()
    for kind in ("ready", "startup", "shutdown", "wat"):
        bus.subscribe(kind, subscriber.handle)
        bus.publish(kind, foo="bar")

    captured = capsys.readouterr()
    assert captured.out == ""


def test_missing_data_does_not_raise(capsys):
    """Publish `heard` and `turn_timing` with no payload; no exception."""
    bus = EventBus()
    subscriber = ConsoleSubscriber()

    bus.subscribe("heard", subscriber.handle)
    bus.subscribe("turn_timing", subscriber.handle)

    bus.publish("heard")  # no data
    bus.publish("turn_timing")  # no data

    captured = capsys.readouterr()
    assert "You:    " in captured.out
    assert "stt 0.0s" in captured.out


def test_logging_subscriber_redacts(caplog):
    """With `log_transcripts=False`, `heard(text="secret")` shows `***REDACTED***`."""
    bus = EventBus()
    subscriber = LoggingSubscriber(log_transcripts=False)

    # Configure logging to capture DEBUG messages
    caplog.set_level(logging.DEBUG)
    
    bus.subscribe("heard", subscriber.handle)
    bus.publish("heard", text="secret")

    assert "***REDACTED***" in caplog.text
    assert "secret" not in caplog.text


def test_logging_subscriber_keeps_text(caplog):
    """With `log_transcripts=True`, the original text is kept."""
    bus = EventBus()
    subscriber = LoggingSubscriber(log_transcripts=True)

    # Configure logging to capture DEBUG messages
    caplog.set_level(logging.DEBUG)
    
    bus.subscribe("heard", subscriber.handle)
    bus.publish("heard", text="secret")

    assert "secret" in caplog.text
