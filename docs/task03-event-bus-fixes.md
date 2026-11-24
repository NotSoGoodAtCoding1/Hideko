# Change Log — Event-bus refactor fixes (task 03 + task 04 doc correction)

- **Date:** 2026-11-24
- **Source tasks:** `architecture-tasks/03-wire-main.md`, `architecture-tasks/04-avatar-contract.md`
- **Audit context:** Full audit of the `architecture-tasks` set against the implementation. Findings and fixes applied during this session.

## Background

After auditing all five tasks in `architecture-tasks/`, task 03 ("Wire the bus into main") was found
to be incompletely and incorrectly implemented, despite the suite passing. Task 04's avatar contract
doc contained a contradiction. Fixes were applied and verified.

## Fixes applied — `main.py` (task 03)

### `HidekoApp.setup()`

1. **`startup` event placement** — moved `self.bus.publish("startup")` to immediately after
   `logger.info("Hideko MVP — Ctrl+C to stop")` (per task spec: "after logging setup in `HidekoApp.setup()`").
   It had previously been published later, after the startup greeting.
2. **`ready` event (was missing entirely)** — added after the responder branch:
   ```python
   self.bus.publish(
       "ready",
       stt_s=secs,
       trigger_count=getattr(self.responder, "trigger_count", 0),
   )
   ```
3. **`calibrating` duplicate output** — removed the leftover `print("Stay quiet for 1 second — calibrating...")`;
   the event alone drives the console line via `ConsoleSubscriber`.

### `HidekoApp.run()`

4. **`thinking`** — replaced `self.status.thinking()` with `self.bus.publish("thinking")`.
5. **`heard`** — replaced `self.status.heard(transcript.text)` with
   `self.bus.publish("heard", text=transcript.text)`.
6. **`listening`** — replaced all three remaining direct `self.status.listening()` calls (resume-after-unmute,
   wake-word listen-mode timeout, first-turn) with `self.bus.publish("listening")`.
7. **`speaking` duplicate output** — no-TTS branch no longer keeps the direct `print(f"Hideko: {response.text}")`;
   TTS branch no longer keeps the direct `self.status.say(response.text)`. The `bus.publish("speaking", ...)`
   alone emits through the `ConsoleSubscriber`.
8. **`turn_timing` duplicate output** — removed the leftover direct `print(f"  [stt ... total ...")`.
9. **`goodbye` duplicate output** — removed the leftover `print("\nGoodbye.")`.
10. **`error` duplicate output** — removed the leftover `print(f"  ({exc})")`; the `bus.publish("error", ...)`
    alone emits through the `ConsoleSubscriber`.

### `main()`

11. Moved bus + `ConsoleSubscriber` setup to immediately after `parse_args(argv)` and before the early-exit
    flags (`--list-devices`, etc.), as required by task 03.

## Fixes applied — `docs/avatar-events.md` (task 04)

12. Corrected the thread-safety statement: the `EventBus` **is** internally thread-safe (uses
    `threading.RLock`); it no longer claims it is not.

## Tests added — `tests/test_smoke.py` (task 03, step 7)

1. `test_main_text_publishes_speaking` — uses a `RecordingBus(EventBus)` monkeypatched into `main`,
   asserts exit code 0, a `speaking` event with text is published, and no `heard` event is published.
2. `test_main_text_output_unchanged` — runs `main(["--text", "hello", "--no-tts"])` and asserts stdout is
   exactly `f"Hideko: {expected}\n"`, where `expected` comes from a `ResponseHandler` (with memory, matching
   main's setup) answering `"hello"`.
3. `test_error_event_published` — publishes through a bus wired into a `HidekoApp` and asserts the `error`
   handler receives kind `error` with the expected payload.

The pre-existing `test_timing_before_exit` was kept unchanged.

## Verification after fixes

- `python -m pytest -q` → **151 passed, 8 skipped, 0 failed** (was 148 passed before the new smoke tests).
- `python -m pytest tests/test_smoke.py -v` → **4 passed** (1 pre-existing + 3 new).
- `python -c "import events; ..."` event-bus one-liner → OK (`*`, then dispatched kind).
- `python scripts/event_probe.py` → expected event sequence.
- `python scripts/avatar_probe.py` → ends with `[avatar] final state: offline`.
- `python -m pytest tests/test_model_acquisition.py` → **17 passed** (task-00 baseline fix intact).

## Remaining known deviations (not fixed in this session)

- Task 02 test style: console-string tests implemented as one sequential test instead of a parametrized
  table test.
- Task 01 test style: thread-safety test uses wildcard subscription with per-thread kinds; event-validation
  test passes explicit data instead of checking the empty-default case.
- Task 03 verification baselines (`baseline_*.txt` / `after_*.txt`) were never produced/committed; no stray
  files remain.
