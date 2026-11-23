# Hotfix — Known Issues Remediation

**Standalone hotfix. No dependencies. Touch at most 7 files.**

## Goal

Fix the four known issues recorded at the bottom of `README.md`. These were explicitly **not** in this sprint but are small, isolated fixes that improve correctness and code quality without affecting core functionality.

Expected impact: Zero functional changes, zero regressions, improved observability and reliability.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Do not change any functional behavior outside the fixes listed.
- No new dependencies except optionally `psutil` for RSS (see Fix 4).
- No network at runtime.
- Tests must pass offline with no mic: `python -m pytest -q`.
- No `print()` in library code outside `if __name__ == "__main__":`.

---

## Known Issues Breakdown

| # | Summary | File | Lines | Severity |
|---|---------|------|-------|----------|
| 1 | `HidekoError` with < 3 consecutive errors exits 0 | `main.py` | Inside `run()` | Bug |
| 2 | Unused variable `t0` | `scripts/benchmark.py` | 282 | Code Quality |
| 3 | Unused imports (`Path`, `random`) | `response_handler.py` | Module level, `__main__` | Code Quality |
| 4 | RSS reports 0.0 MB throughout | `scripts/soak.py` | RSS measurement | Bug |

---

## Current State (Exact)

### Issue 1: `main.py:run()` — Silent Error Exit

In `main.py`, the `HidekoApp.run()` method contains a try/except block that catches `HidekoError`. The existing logic:

```python
        try:
            # ... loop body ...
        except HidekoError as e:
            consecutive_errors += 1
            logger.error(f"Error in turn {turn}: {e}")
            if consecutive_errors >= 3:
                logger.error("3 consecutive errors, shutting down")
                sys.exit(getattr(e, "exit_code", 1))
            # BUG: With < 3 consecutive errors, loop exits and main() returns 0
```

**Problem:** A single `HidekoError` causes the loop to exit, but `main()` returns exit code `0` (success), masking the error.

### Issue 2: `scripts/benchmark.py` line 282 — Unused Variable

```python
            t0 = perf_counter()
            warmup()
```

**Problem:** `t0` is assigned but never referenced. This is dead code.

### Issue 3: `response_handler.py` — Unused Imports

At module level:
```python
from pathlib import Path
```

Inside `if __name__ == "__main__":`:
```python
import random
```

**Problem:** Both imports are unused. `Path` is not referenced anywhere in the module. `random` is not used in the `__main__` block.

### Issue 4: `scripts/soak.py` — Broken RSS Measurement

The soak test uses Unix-only `resource.getrusage()` to measure RSS:
```python
import resource
rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
```

**Problem:** On Windows, the `resource` module exists but `ru_maxrss` returns `0`. This causes `logs/soak.md` to report `0.0 MB` throughout, making the PASS result meaningless.

---

## Steps

### Fix 1: Non-Zero Exit on Any `HidekoError`

In `main.py`, locate the `except HidekoError` block inside `HidekoApp.run()`. Replace:

```python
        except HidekoError as e:
            consecutive_errors += 1
            logger.error(f"Error in turn {turn}: {e}")
            if consecutive_errors >= 3:
                logger.error("3 consecutive errors, shutting down")
                sys.exit(getattr(e, "exit_code", 1))
            # Falls through
```

With:
```python
        except HidekoError as e:
            consecutive_errors += 1
            logger.error(f"Error in turn {turn}: {e}")
            exit_code = getattr(e, "exit_code", 1)
            if consecutive_errors >= 3:
                logger.error("3 consecutive errors, shutting down")
            sys.exit(exit_code)
```

**Rationale:** Ensures any `HidekoError` that breaks out of the loop results in a non-zero exit code. Preserves consecutive error counting for logging.

### Fix 2: Remove Unused Variable

In `scripts/benchmark.py`, delete line 282:
```python
            t0 = perf_counter()
```

If `perf_counter` is now unused in that scope, also remove its import from the top of the file.

### Fix 3: Remove Unused Imports

In `response_handler.py`:

1. Delete the module-level import:
   ```python
   from pathlib import Path
   ```

2. Delete the import inside `if __name__ == "__main__":`:
   ```python
   import random
   ```

Verify clean import:
```powershell
python -W error -c "import response_handler"
```

### Fix 4: Fix RSS Measurement

**CHOICE REQUIRED — Pick ONE:**

**Option A: Add `psutil` (Recommended)**

1. Add to `requirements.txt`:
   ```
   psutil==5.9.8
   ```

2. In `scripts/soak.py`, add at the top:
   ```python
   import psutil
   ```

3. Replace the RSS measurement function with:
   ```python
   def _get_rss_mb() -> float:
       """Return current process RSS in megabytes."""
       return psutil.Process().memory_info().rss / (1024 * 1024)
   ```

4. Replace all existing RSS measurement calls with `_get_rss_mb()`.

**Option B: Document Platform Limitation**

1. In `scripts/soak.py`, replace the RSS measurement with:
   ```python
   import sys
   
   def _get_rss_mb() -> float:
       """Return RSS in MB. Returns 0.0 on unsupported platforms."""
       if sys.platform.startswith('linux'):
           import resource
           return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
       # Windows/macOS: resource module doesn't provide RSS
       return 0.0
   ```

2. Add to the top of `logs/soak.md`:
   ```markdown
   > **Platform Note:** RSS measurement is not available on Windows. Values show as 0.0 MB.
   ```

**Human must decide:** Option A adds a dependency but provides accurate data on all platforms. Option B maintains zero new dependencies but RSS remains 0.0 MB on Windows.

---

## Verification

```powershell
# 1. Core test suite
python -m pytest -q

# 2. Import checks (no warnings)
python -W error -c "import response_handler; print('response_handler: OK')"
python -W error -c "import scripts.benchmark; print('benchmark: OK')"

# 3. Error exit code (must be non-zero)
python main.py --config nonexistent.yaml 2>$null
Write-Host "Error exit code: $LASTEXITCODE"

# 4. Benchmark runs without unused variable issues
python scripts/benchmark.py --repeat 1

# 5. Soak test and RSS check
python scripts/soak.py --turns 5
Get-Content logs\soak.md | Select-String -Pattern "MB" | Select-Object -Last 5
```

### Expected Output:

1. **`python -m pytest -q`**
   ```
   ... passed
   ```
   All existing tests pass. No failures.

2. **Import checks**
   ```
   response_handler: OK
   benchmark: OK
   ```
   No warnings emitted.

3. **Error exit code**
   ```
   Error exit code: 1
   ```
   Previously would have been `0`. Must be non-zero.

4. **Benchmark**
   ```
   Benchmark complete.
   ```
   Runs to completion without warnings.

5. **RSS values**
   - **Option A:** Non-zero values like `145.2 MB`, `150.1 MB`
   - **Option B:** Values remain `0.0 MB` but with the platform note visible

---

## Tests to Add

### New file: `tests/test_error_exit_code.py`

```python
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
```

### New file: `tests/test_clean_imports.py`

```python
"""Tests to verify no unused imports in critical modules."""


def test_response_handler_imports():
    """response_handler must import cleanly with no unused import warnings."""
    import response_handler
    assert response_handler is not None


def test_benchmark_imports():
    """benchmark must import cleanly with no unused import warnings."""
    import scripts.benchmark
    assert scripts.benchmark is not None
```

### If Option A chosen: Add to `tests/test_soak.py` or new file

```python
"""Tests for RSS measurement."""
import pytest


def test_rss_measurement_returns_positive():
    """RSS measurement must return positive value on supported platforms."""
    from scripts.soak import _get_rss_mb
    rss = _get_rss_mb()
    assert rss > 0.0, f"RSS should be positive, got {rss} MB"
```

---

## Stop and Ask the Human If

- The `except HidekoError` block in `main.py` uses a different structure than described (e.g., nested try/except, different variable names).
- Line 282 in `benchmark.py` contains different code than `t0 = perf_counter()` (line numbers may have shifted).
- The `Path` import in `response_handler.py` is actually used by code you didn't see (unlikely but verify).
- The `random` import in `response_handler.py`'s `__main__` block is actually used.
- You need to choose between **Option A** and **Option B** for the RSS fix — ask which is preferred.
- The soak script is located somewhere other than `scripts/soak.py` (confirm actual path).
- Any existing test fails after applying these changes.

---

## Files Touched

| File | Change | Lines |
|------|--------|-------|
| `main.py` | Fix error exit code | ~5 |
| `scripts/benchmark.py` | Remove unused `t0` | 1 |
| `response_handler.py` | Remove unused imports | 2 |
| `requirements.txt` | Add `psutil==5.9.8` (Option A) | 1 |
| `scripts/soak.py` | Fix RSS measurement | ~5-10 |
| `logs/soak.md` | Updated values or note | 1 |
| `tests/test_error_exit_code.py` | New test | ~20 |
| `tests/test_clean_imports.py` | New test | ~15 |
