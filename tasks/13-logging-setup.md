# Task 13 — Logging setup

**Goal (one sentence).** Create **one file**, `logging_setup.py`, with an idempotent `setup_logging()` and a Windows RSS helper. No other file changes.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `logging_setup.py` — **create**, nothing else |
| Depends on | task 03 (`LoggingConfig`), task 12 (errors hierarchy — not strictly needed here) |
| Blocks | task 14 |
| Time budget | ~25 min |

Do not modify `main.py` — task 14 calls these functions.

---

## 1. Contract — copy verbatim

```python
def setup_logging(config: LoggingConfig, *, debug: bool = False,
                  log_file: Path | None = None) -> None: ...
def memory_rss_mb() -> float | None: ...
```

Available config fields:

```python
cfg.logging.level         # "INFO" / "DEBUG" / "WARNING" / ...
cfg.logging.file          # pathlib.Path (absolute), e.g. logs/hideko.log
cfg.logging.max_bytes     # 1048576
cfg.logging.backup_count  # 3
```

## 2. `setup_logging()` — implement exactly

1. Root logger level: `logging.DEBUG` if `debug` else `getattr(logging, config.level)`.
2. **Console handler** → `sys.stderr`, level `DEBUG` if `debug` else `logging.WARNING`. Status lines are printed by `main.py`; the console should otherwise stay quiet.
3. **File handler** → `logging.handlers.RotatingFileHandler(
   log_file or config.file, maxBytes=config.max_bytes,
   backupCount=config.backup_count, encoding="utf-8")`, at the **root level** (not WARNING). Create parent dirs with `mkdir(parents=True, exist_ok=True)`.
4. Format: `"%(asctime)s %(levelname)-7s %(name)s: %(message)s"`, `datefmt="%H:%M:%S"`. Apply to both handlers.
5. Silence noisy third parties: set level `logging.WARNING` for `faster_whisper`, `ctranslate2`, `urllib3`, `numba`.
6. **Idempotent**: before adding handlers, remove and close all existing handlers on the root logger. Tests call this twice; without this step every log line appears twice.

## 3. `memory_rss_mb()` — implement exactly

```python
import ctypes
from ctypes import wintypes

class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
```

Call `ctypes.windll.kernel32.GetCurrentProcess()` then `ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), ctypes.sizeof(pmc))`. Set `pmc.cb = ctypes.sizeof(pmc)` before the call. Return `pmc.WorkingSetSize / 1e6`.

Wrap **everything** (including the `ctypes.windll` attribute access) in:

```python
try:
    ...
except (OSError, AttributeError):
    return None
```

On non-Windows this returns `None`. No new dependency (`psutil` is banned).

## 4. Rules checklist

- [ ] `setup_logging(config, *, debug=False, log_file=None)` signature exact
- [ ] Console → stderr at WARNING (or DEBUG with `--debug`)
- [ ] File handler at root level, rotating at `max_bytes` with `backup_count` backups
- [ ] Parent dirs created; UTF-8 encoding
- [ ] Third-party loggers set to WARNING
- [ ] Existing handlers removed **and closed** before adding new ones
- [ ] `memory_rss_mb()` returns MB as float on Windows, `None` elsewhere
- [ ] `except (OSError, AttributeError)` covers the `windll` access itself
- [ ] Type hints + docstrings on both public functions
- [ ] No `print()` outside `__main__`

## 5. Do NOT

- Do not add `loguru`, `structlog`, `colorama`, or `psutil`.
- Do not put the `ctypes.windll` access outside the `try` block.
- Do not change any existing module.
- Do not use a bare `except:` or `except Exception: pass`.

## 6. Verify — run and paste output

```powershell
python -c "from config import load_config; from logging_setup import setup_logging; c=load_config(); setup_logging(c.logging); setup_logging(c.logging); print('idempotent ok')"
```
Expected: `idempotent ok`, no duplicate-handler warnings, no doubled log lines.

```powershell
python -c "from logging_setup import memory_rss_mb; print(memory_rss_mb())"
```
Expected: a float in the tens/hundreds of MB (or `None` on non-Windows).

```powershell
python -m pytest -q
```
Expected: still passes.

## 7. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 14.
