# Task 12 — Error hierarchy & migration

**Goal (one sentence).** Create `errors.py` with one exception hierarchy and change **only the class declaration line** in five existing modules to import their exception from it. No behaviour changes.

**You only need this file.** All edits are shown exactly. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `errors.py` (create) + `config.py`, `audio_manager.py`, `stt_engine.py`, `tts_engine.py`, `response_handler.py` (**one line each**) |
| Depends on | tasks 03–11 (all modules exist) |
| Blocks | task 14 |
| Time budget | ~20 min |

This is a mechanical task. Do not add logging, exit-code handling, or memory checks — task 14 owns those.

---

## 1. Create `errors.py` — copy verbatim

```python
"""Exception hierarchy for expected, user-actionable Hideko failures."""

class HidekoError(Exception):
    """Base class for all expected, user-actionable Hideko failures."""
    exit_code: int = 1

class ConfigError(HidekoError):
    """Bad configuration."""
    exit_code = 1

class AudioError(HidekoError):
    """No microphone/speaker, device busy, or PortAudio failure."""
    exit_code = 2

class ModelError(HidekoError):
    """A model binary or data file is missing."""
    exit_code = 3

class STTError(ModelError):
    """Speech-to-text failure."""

class TTSError(ModelError):
    """Text-to-speech failure."""

class ResponseDataError(HidekoError):
    """Broken responses/*.yaml."""
    exit_code = 4
```

`errors.py` imports **nothing** from the project (no circular imports). No new dependency.

Exit code table (must stay consistent with task 14 and the final README):

| Code | Meaning |
|------|---------|
| 0 | normal / Ctrl+C / goodbye |
| 1 | config |
| 2 | audio |
| 3 | model (missing Piper/Whisper files) |
| 4 | response data |

## 2. Migrate the five modules — one line each

For each module, **delete** the old `class XError(Exception):` block and **replace** it with a re-export import at the top of the file. This keeps `audio_manager.AudioError` etc. resolving for existing callers.

| File | Old declaration | Replacement |
|------|-----------------|-------------|
| `config.py` | `class ConfigError(Exception): ...` | `from errors import ConfigError` |
| `audio_manager.py` | `class AudioError(Exception): ...` | `from errors import AudioError` |
| `stt_engine.py` | `class STTError(Exception): ...` | `from errors import STTError` |
| `tts_engine.py` | `class TTSError(Exception): ...` | `from errors import TTSError` |
| `response_handler.py` | `class ResponseDataError(Exception): ...` | `from errors import ResponseDataError` |

Keep every existing docstring-bearing `raise XError("...")` message **exactly** as it is. Only the class definition moves.

Example for `audio_manager.py`:

```python
# before
class AudioError(Exception):
    """Raised for missing devices, PortAudio failures, and stream errors."""

# after (at top of file, with the other imports)
from errors import AudioError
```

If you want to preserve the docstring, you may add one line under the import: `AudioError.__doc__ = "Raised for missing devices, PortAudio failures, and stream errors."` — optional, not required.

## 3. Rules checklist

- [ ] `errors.py` exists with all seven classes and the `exit_code` values above
- [ ] Each of the five modules imports (not redefines) its exception
- [ ] No module defines an exception class twice
- [ ] No exception message text changed
- [ ] `errors.py` has no project imports
- [ ] All existing code still imports the same names from the same modules

## 4. Do NOT

- Do not change `main.py` in this task (task 14 owns that).
- Do not change exception messages — task verification depends on them.
- Do not add a bare `except:` or `except Exception: pass`.
- Do not move any other classes between modules.

## 5. Verify — run and paste output

```powershell
python -c "from errors import HidekoError, ConfigError, AudioError, ModelError, STTError, TTSError, ResponseDataError as R; print([c.exit_code for c in (ConfigError, AudioError, STTError, TTSError, R)]); print(issubclass(STTError, ModelError))"
```
Expected: `[1, 2, 3, 3, 4]` and `True`.

```powershell
python -c "import config, audio_manager, stt_engine, tts_engine, response_handler; print(config.ConfigError.__module__, audio_manager.AudioError.__module__, stt_engine.STTError.__module__, tts_engine.TTSError.__module__, response_handler.ResponseDataError.__module__)"
```
Expected: `errors errors errors errors errors` — proving no duplicate definitions remain.

```powershell
python main.py --text "hello"
```
Expected: still prints `Hideko: I heard you say: hello` and exits 0. Do **not** add `--no-tts` here — that flag arrives in task 16.

```powershell
python -m pytest -q
```
Expected: still passes.

## 6. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 13.
