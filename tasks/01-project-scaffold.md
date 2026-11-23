# Task 01 — Project scaffold & toolchain

**Phase:** 0 (foundation) · **Depends on:** nothing · **Blocks:** everything · **Effort:** 30–60 min

## Goal

Create the Python 3.11 virtual environment, the pinned dependency list, the folder skeleton, `.gitignore`, and a smoke test that proves all binary dependencies import correctly on this machine.

Nothing in this task produces application logic. If you write a class named `Microphone` here, you have done it wrong.

## Read first

- [`../plan.md`](../plan.md) — sections "File Structure (MVP)" and "Hardware Requirements".
- [`README.md`](README.md) — Ground rules.

## Files you will create

```
requirements.txt
.gitignore
tests/__init__.py
tests/test_smoke.py
pytest.ini
logs/.gitkeep
models/piper/.gitkeep
models/whisper/.gitkeep
responses/.gitkeep
scripts/.gitkeep
tests/fixtures/.gitkeep
```

Do **not** create `main.py`, `config.py`, or any engine module yet. Later tasks own those.

## Step 1 — Verify Python 3.11 is installed

```powershell
py -0p
```

Expected: a list containing a 3.11 line, e.g. `-V:3.11  C:\Users\...\Python311\python.exe`.

If 3.11 is missing, **stop** and report it. Do not fall back to 3.12 or 3.13: `ctranslate2` (used by `faster-whisper`) and the `piper` binary tooling have the fewest wheel problems on 3.11.

## Step 2 — Create and activate the venv

From the project root (`C:\Users\Ilya\Documents\new_prj`):

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Expected: prompt is prefixed with `(.venv)` and `python --version` prints `Python 3.11.x`.

> If `Activate.ps1` is blocked by policy even after the `Set-ExecutionPolicy` line, use `.\.venv\Scripts\python.exe` explicitly for every command instead of activating. Do not disable machine-wide execution policy.

## Step 3 — Create `requirements.txt`

Exact content (versions are pinned on purpose; do not "upgrade to latest"):

```
numpy==1.26.4
sounddevice==0.4.6
soundfile==0.12.1
faster-whisper==1.0.3
PyYAML==6.0.1
pytest==8.2.0
```

Why these pins:

- `numpy==1.26.4` — `ctranslate2` 4.x is built against NumPy 1.x. NumPy 2.x raises `_ARRAY_API not found` at import time.
- `sounddevice==0.4.6` — bundles PortAudio DLL in the wheel, so no separate PortAudio install is needed on Windows.
- `soundfile==0.12.1` — bundles `libsndfile`, so no separate DLL hunt.
- `faster-whisper==1.0.3` — pulls matching `ctranslate2` and `tokenizers` wheels.
- `pytest` — required from task 17, installed now so the smoke test works.

Install:

```powershell
python -m pip install -r requirements.txt
```

Expected last line: `Successfully installed ... ctranslate2-4.x ... faster-whisper-1.0.3 ... sounddevice-0.4.6 ...`

### If installation fails

| Error | Fix |
|-------|-----|
| `Could not find a version that satisfies the requirement ctranslate2` | Wrong Python version. Confirm 3.11: `python --version`. |
| `error: Microsoft Visual C++ 14.0 or greater is required` | You are on the wrong Python or a source-only wheel. Re-check 3.11 and that `pip --version` points inside `.venv`. |
| `ERROR: Failed building wheel for av` | `av` ships wheels for 3.11. If it still builds from source, run `python -m pip install --only-binary=:all: -r requirements.txt`. |
| Proxy/SSL errors | Report them. Do not add `--trusted-host`. |

## Step 4 — Create the folder skeleton

```powershell
New-Item -ItemType Directory -Force -Path logs, models\piper, models\whisper, responses, scripts, tests\fixtures | Out-Null
New-Item -ItemType File -Force -Path logs\.gitkeep, models\piper\.gitkeep, models\whisper\.gitkeep, responses\.gitkeep, scripts\.gitkeep, tests\fixtures\.gitkeep | Out-Null
New-Item -ItemType File -Force -Path tests\__init__.py | Out-Null
```

## Step 5 — Create `.gitignore`

```
# Python
.venv/
__pycache__/
*.py[cod]
.pytest_cache/

# Models (large, downloaded by scripts/download_models.py)
models/piper/*
!models/piper/.gitkeep
models/whisper/*
!models/whisper/.gitkeep

# Runtime output
logs/*
!logs/.gitkeep
*.wav
!tests/fixtures/*.wav

# OS / editor
Thumbs.db
desktop.ini
.vscode/
.idea/
```

## Step 6 — Create `pytest.ini`

```ini
[pytest]
testpaths = tests
addopts = -q
markers =
    slow: takes more than 5 seconds or needs real audio hardware
    e2e: end-to-end test requiring microphone and speakers
```

## Step 7 — Create `tests/test_smoke.py`

This test must pass on a machine with **no microphone and no speakers**. It only checks imports and versions.

```python
"""Environment smoke test: proves binary dependencies import on this machine."""
from __future__ import annotations

import sys

import numpy as np
import sounddevice
import soundfile
import yaml


def test_python_version_is_311() -> None:
    assert sys.version_info[:2] == (3, 11), f"expected 3.11, got {sys.version}"


def test_numpy_is_1x() -> None:
    assert np.__version__.startswith("1."), f"numpy {np.__version__} breaks ctranslate2"


def test_sounddevice_reports_portaudio() -> None:
    # Returns a string like "PortAudio V19.7.0-devel, revision 19.7.0".
    # Raises if the PortAudio DLL is missing from the wheel.
    assert sounddevice.get_portaudio_version().startswith("PortAudio")


def test_soundfile_has_libsndfile() -> None:
    # available_formats() calls into libsndfile, so it proves the DLL loaded.
    assert "WAV" in soundfile.available_formats()


def test_faster_whisper_imports() -> None:
    from faster_whisper import WhisperModel  # noqa: F401

    import ctranslate2

    assert ctranslate2.__version__


def test_yaml_roundtrip(tmp_path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("a: 1\n", encoding="utf-8")
    assert yaml.safe_load(p.read_text(encoding="utf-8")) == {"a": 1}
```

## Verification

Run all three. Paste the output in your report.

```powershell
python --version
python -c "import numpy, sounddevice, soundfile, yaml, faster_whisper; print('imports ok')"
python -m pytest -q
```

Expected:

```
Python 3.11.9
imports ok
6 passed
```

`python -c "import sounddevice; print(sounddevice.query_devices())"` is **not** part of verification — it fails on CI-like machines without audio, and task 04 handles devices properly.

## Done criteria

- [ ] `.venv` exists and `python --version` inside it reports 3.11.x.
- [ ] `requirements.txt` matches the exact content above.
- [ ] All six directories exist and contain their `.gitkeep`.
- [ ] `python -m pytest -q` prints `6 passed`.
- [ ] `git status` (if a repo exists) shows no `models/` or `logs/` content staged.

## Common pitfalls

- **Activating the venv but running a global `python`.** Verify with `python -c "import sys; print(sys.prefix)"` — it must end with `.venv`.
- **`pip install` from a different shell** (e.g. cmd) and then testing in PowerShell. Same venv, same shell.
- **Creating `tests/` without `__init__.py`** and then importing `tests.helpers` in task 17. Create it now.
- **Deleting `models/*/.gitkeep`** when task 02 downloads models — the folder must survive a `git clean`.

## Do NOT

- Do not install `torch`, `openai-whisper`, `TTS` (Coqui), or `piper-tts`. STT is `faster-whisper`; TTS is the `piper.exe` binary downloaded in task 02.
- Do not add a `pyproject.toml`, Poetry, or uv. `requirements.txt` + venv is the whole toolchain.
- Do not create a `src/` layout. Modules live flat at the project root.
- Do not write application code.
