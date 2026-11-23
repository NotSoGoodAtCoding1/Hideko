# Task 23 — Integration tests (CLI contract)

**Goal (one sentence).** Create **one file**, `tests/test_integration.py`, with subprocess-level CLI checks — gated behind `HIDEKO_E2E=1` except for one always-on parser test.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `tests/test_integration.py` — **create**, nothing else |
| Depends on | tasks 14, 16 |
| Blocks | task 24 |
| Time budget | ~30 min |

---

## 1. Gate

```python
import os
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("HIDEKO_E2E") != "1",
                       reason="set HIDEKO_E2E=1"),
]
```

Register the `e2e` marker in `pytest.ini` / `pyproject.toml` **only if it already exists** — do not create config files in this task. If pytest warns about an unknown mark, that is acceptable; do not suppress it with a new config file.

## 2. Subprocess helper

```python
def run(*args):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
```
Always pass `timeout`. Assert on `returncode` and a **substring**, never on full output. No microphone, no playback — use `--no-tts`.

## 3. Gated cases (6)

1. `--help` → exit 0, stdout contains `--text` and `--list-devices`.
2. `--list-devices` → exit 0, stdout contains `idx` or `Microphone`/`Speakers`.
3. `--text "hello" --no-tts` → exit 0, stdout contains `Hideko:`.
4. `--text "goodbye" --no-tts` → exit 0, stdout contains `Goodbye`.
5. `--config missing.yaml` → exit 1, stderr contains `error:` and **no** `Traceback`.
6. `--text "hello" --no-tts --turns 0` → exit 0 (does not hang).

## 4. Non-gated case (always runs in CI without models)

```python
def test_cli_help_works_without_models():
    r = subprocess.run([sys.executable, "main.py", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert "--no-tts" in r.stdout
```
This one must be placed **before** the module-level `pytestmark` applies, or use `@pytest.mark.e2e`-free placement (e.g. in a separate module-level section with the mark overridden). Simplest: put the always-on test in its own file region by defining `pytestmark` after it, or mark it explicitly with nothing and set `pytestmark` only on the gated class. Either approach is fine — just ensure it runs in the default suite.

## 5. Rules checklist

- [ ] 6 gated cases + 1 always-on case
- [ ] `HIDEKO_E2E` gate correct; default run skips the 6, not fails
- [ ] every subprocess call has a timeout
- [ ] no microphone, no playback, no models required
- [ ] assertions are substring + returncode only
- [ ] Type hints on the helper

## 6. Do NOT

- Do not add `pytest-xdist` or any new dependency.
- Do not run playback or load Whisper/Piper in these tests.
- Do not assert on exact timing numbers or full output.

## 7. Verify — run and paste output

```powershell
python -m pytest -q
```
Expected: all unit tests pass; the 6 e2e tests are **skipped**, not failed.

```powershell
$env:HIDEKO_E2E="1"
python -m pytest tests\test_integration.py -q
Remove-Item Env:HIDEKO_E2E
```
Expected: `6 passed` (plus the always-on test if collected).

## 8. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 24.
