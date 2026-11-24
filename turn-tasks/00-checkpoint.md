# Task 00 — Checkpoint & hygiene

**Setup task. No dependencies. No application code changes.**

## Goal

Commit the completed event-bus work so the tool/state refactor starts from a clean, reviewable checkpoint. Repo has uncommitted changes from the previous phase.

## Current state (verified 2026-11-24)

```
 M main.py
 M tests/test_smoke.py
?? docs/
?? event_outputs.py
?? tests/test_event_outputs.py
```

Suite is green: **151 passed, 8 skipped, 0 failed**.

Root also has `scratch/` with one-off debug scripts from earlier phases — those are already out of root, good.

## Steps

1. Review what will be committed:
   ```powershell
   git status --short
   git diff --stat
   ```

2. Commit the event-bus work with a clear message:
   ```powershell
   git add -A
   git commit -m "feat: event bus wiring for console output and extensibility"
   ```

3. Verify:
   ```powershell
   git status --short      # expect clean (or only untracked scratch/)
   git log --oneline -3    # expect new commit on top
   python -m pytest -q     # expect 151 passed, 8 skipped
   ```

## Verification

- `git log --oneline -1` shows the new commit.
- `python -m pytest -q` passes (151 passed, 8 skipped).
- No uncommitted changes to tracked files remain.

## Stop and ask the human if

- `git status` shows unexpected changes you cannot explain — report them and stop.
- A test fails after the commit — restore and stop.
