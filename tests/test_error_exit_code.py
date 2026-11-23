"""Tests for error handling exit codes."""
import subprocess
import sys
from pathlib import Path


def test_single_hideko_error_exits_nonzero(tmp_path):
    """A single HidekoError must produce a non-zero exit code."""
    broken_config = tmp_path / "broken.yaml"
    broken_config.write_text("this: is: invalid: yaml: [[[")

    result = subprocess.run(
        [sys.executable, "main.py", "--config", str(broken_config)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode != 0, (
        f"HidekoError should exit non-zero, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
