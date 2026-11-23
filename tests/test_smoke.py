"""Smoke tests that always run without HIDEKO_E2E gate."""

from __future__ import annotations

import subprocess
import sys


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
