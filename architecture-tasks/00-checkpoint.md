# Task 00 — Checkpoint & hygiene

**Setup task. No dependencies. No application code changes.**

## Goal

Make the current working state safe to refactor. The repo is a git repo with uncommitted changes and several one-off debug scripts at root. Do not lose anything.

## Current state (verified)

```
 M config.yaml
 M llm_fallback.py
 M memory/facts.json
?? test_results.md
?? test_results_gpu.md
```

Root-level one-off scripts present: `cleanup.py`, `debug_file.py`, `debug_file2.py`, `debug_file3.py`, `debug_file4.py`, `fix_endpoint_test.py`, `fix_file.py`, `verify_file.py`, `test_wav.py`.

`llm.enabled` is currently `true` in `config.yaml`; the agreed default is `false` (task 03 in this set does not change config — leave it alone here).

## Steps

1. Inspect and report:
   ```powershell
   git status --short
   git log --oneline -5
   git diff --stat
   ```

2. Create `scratch\` and move the one-off scripts into it, preserving history in one place:
   ```powershell
   New-Item -ItemType Directory -Force scratch | Out-Null
   Move-Item cleanup.py, debug_file.py, debug_file2.py, debug_file3.py, debug_file4.py, fix_endpoint_test.py, fix_file.py, verify_file.py, test_wav.py scratch\ -ErrorAction SilentlyContinue
   ```
   Do **not** move `test_results.md` or `test_results_gpu.md` — those are useful performance notes; report them instead.

3. **Fix one known baseline test failure** before proceeding. `config.yaml` currently has `llm.enabled: true`, so `check_env.py` probes the KoboldCpp server. `tests/test_model_acquisition.py::test_no_audio_reports_warning_rows` monkeypatches every other check but not this one, so it fails with `KoboldCpp server FAILED ... timed out`. Do **not** change `config.yaml` (the user may be actively using the server). Instead, in that test add one line beside the other `monkeypatch.setattr(ce, ...)` calls:
   ```python
       monkeypatch.setattr(ce, "check_llm_server", lambda: ("-", "disabled"))
   ```
   This keeps the test independent of whether the user's server is running — which is the whole point of the test.

4. Verify nothing broke:
   ```powershell
   python -m pytest -q
   python config.py --check
   ```
   Expected: tests pass, config loads. Leave `llm.enabled: true` as-is; do not flip it in this task set.

4. **Do not commit.** Committing changes other people's work needs approval. Instead report:
   - `git status --short` after the move
   - whether `tests` still pass
   - the exact command the human can run to commit if they want:
     ```
     git add -A
     git commit -m "checkpoint before event bus refactor"
     ```

## Verification

- `tests/test_model_acquisition.py::test_no_audio_reports_warning_rows` now passes without a running KoboldCpp server.
- `scratch\` exists and contains the nine listed scripts.
- No `.py` one-off scripts remain at root (other than the real modules and `main.py`).
- `python -m pytest -q` passes.
- No commit was created.

## Stop and ask the human if

- `git status` shows unexpected changes you cannot explain — report them and stop.
- A test fails after moving the scripts — restore the files and stop.
- The human wants a commit — then ask exactly which message to use before running `git commit`.
