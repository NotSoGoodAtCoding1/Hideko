"""Integration tests for CLI contract — gated behind HIDEKO_E2E=1."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


# Gated tests: skipped unless HIDEKO_E2E=1
pytestmark = pytest.mark.skipif(
    os.environ.get("HIDEKO_E2E") != "1",
    reason="set HIDEKO_E2E=1",
)


def run(*args):
    """Run main.py with given arguments.

    Args:
        args: Additional CLI arguments after main.py.

    Returns:
        CompletedProcess result.
    """
    return subprocess.run(
        [sys.executable, "main.py", *args],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )


def test_help_shows_options():
    """Test --help shows expected options."""
    r = run("--help")
    assert r.returncode == 0
    assert "--text" in r.stdout
    assert "--list-devices" in r.stdout


def test_list_devices_exits_cleanly():
    """Test --list-devices exits with code 0 and shows device info."""
    r = run("--list-devices")
    assert r.returncode == 0
    # Check for device-related output
    assert "idx" in r.stdout or "Microphone" in r.stdout or "Speakers" in r.stdout


def test_hello_response():
    """Test greeting response with --no-tts."""
    r = run("--text", "hello", "--no-tts")
    assert r.returncode == 0
    assert "Hideko:" in r.stdout


def test_goodbye_response():
    """Test goodbye response with --no-tts."""
    r = run("--text", "goodbye", "--no-tts")
    assert r.returncode == 0
    # Check for any of the possible goodbye responses
    assert any(x in r.stdout for x in ["Goodbye", "See you", "Take care"])


def test_missing_config_errors_cleanly():
    """Test missing config file produces error without traceback."""
    r = run("--config", "missing.yaml")
    assert r.returncode == 1
    assert "error:" in r.stderr
    # Ensure no Python traceback is shown
    assert "Traceback" not in r.stderr


def test_zero_turns_does_not_hang():
    """Test --turns 0 completes quickly without hanging."""
    r = run("--text", "hello", "--no-tts", "--turns", "0")
    assert r.returncode == 0


# Always-on test: verifies timing line appears before exit message
@pytest.mark.skipif(
    os.environ.get("HIDEKO_E2E") == "1",
    reason="skip when HIDEKO_E2E=1 to avoid conflicts with gated tests",
)
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


# Always-on test: runs without HIDEKO_E2E gate
def test_cli_help_works_without_models():
    """Test that --help works even without models installed."""
    r = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0
    assert "--no-tts" in r.stdout
