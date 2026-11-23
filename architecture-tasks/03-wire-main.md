# Task 03 — Wire the bus into main

**Depends on task 02. Touch at most 2 files.** This is the risky task: it changes output plumbing. Preserve every printed line exactly.

## Goal

Replace direct `Status` calls and `print()` calls in `main.py` with `bus.publish(...)`. One shared `EventBus` serves both the mic loop and the `--text` one-shot path. Add a `ConsoleSubscriber` so the terminal output is unchanged.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- **Capture the baseline output before editing** (see below) and diff it after. Byte-for-byte identical is required for all `--text` commands.
- Do **not** change behaviour elsewhere: wake-word logic, memory, responder, TTS, playback, error handling (`sys.exit` stays), timing values, exit codes.
- Do not touch `config.yaml`, `config.py`, `response_handler.py`, `llm_fallback.py`.
- `python -m pytest -q` must pass with no mic/server.

## Step 0 — capture baseline (do this first)

```powershell
python main.py --text "hello" --no-tts | Out-File -Encoding utf8 baseline_hello.txt
python main.py --text "goodbye" --no-tts | Out-File -Encoding utf8 baseline_goodbye.txt
python main.py --help | Out-File -Encoding utf8 baseline_help.txt
```
Keep these three files until the end; delete them after verification. Do not commit them.

## Step 1 — imports

Add to the import block in `main.py`:
```python
from event_outputs import ConsoleSubscriber
from events import ALL, EventBus
```
Keep `Status` imported from `cli` — the console subscriber needs an instance.

## Step 2 — `HidekoApp.__init__`

Change the signature and first assignments:
```python
    def __init__(
        self,
        config: AppConfig,
        opts: CliOptions,
        bus: EventBus | None = None,
        status: Status | None = None,
    ) -> None:
        self.config = config
        self.opts = opts
        self.bus = bus if bus is not None else EventBus()
        self.status = status if status is not None else Status()
        self.keys = KeyListener()
        ...  # all remaining assignments unchanged
```
`self.status` stays for backwards compatibility but the app must no longer call its methods directly.

## Step 3 — `HidekoApp.setup()`

- After `logger.info("Hideko MVP — Ctrl+C to stop")` add:
  ```python
          self.bus.publish("startup")
  ```
- Replace the calibration print with an event:
  ```python
          if self.config.vad.calibrate:
              self.bus.publish("calibrating")
              self.recorder.calibrate(self.mic)
  ```
- After the responder branch, add:
  ```python
          self.bus.publish(
              "ready",
              stt_s=secs,
              trigger_count=getattr(self.responder, "trigger_count", 0),
          )
  ```
  Note: `secs` is the value from `self.stt.warmup()` already stored in `setup()`.
- Leave the startup greeting synthesis/playback exactly as it is (no event — publishing `speaking` here would add a console line that doesn't exist today).

## Step 4 — `HidekoApp.run()` replacements

Replace each old line with the corresponding event. Do not change surrounding control flow.

| Old line | New line |
|---|---|
| `self.status.paused()` | `self.bus.publish("paused")` |
| `self.status.listening()` (all four occurrences: resume, first-turn, wake-timeout) | `self.bus.publish("listening")` |
| `print(f"  [wake word detected in {t1-t0:.1f}s]")` | `self.bus.publish("wake_detected", text=transcript.text, latency_s=t1 - t0)` |
| `self.status.thinking()` | `self.bus.publish("thinking")` |
| `print("  (didn't catch that)")` | `self.bus.publish("missed")` |
| `self.status.heard(transcript.text)` | `self.bus.publish("heard", text=transcript.text)` |
| `print(f"Hideko: {response.text}")` (no-TTTS branch) | `self.bus.publish("speaking", text=response.text)` |
| `self.status.say(response.text)` (TTS branch) | `self.bus.publish("speaking", text=response.text)` |
| `print(f"  [stt ... total ...]")` | `self.bus.publish("turn_timing", stt=t1 - t0, resp=t2 - t1, tts=t3 - t2, play=t4 - t3, total=t4 - t0)` |
| `print("\nGoodbye.")` | `self.bus.publish("goodbye")` |
| `print(f"  ({exc})")` in `except HidekoError` | `self.bus.publish("error", message=str(exc), exit_code=getattr(exc, "exit_code", 1))` |

Keep the existing `logger.info("timing stt=...")` line unchanged — do not delete it and do not publish it separately.

Keep `turn += 1`, the half-duplex flush, RSS logging, and `sys.exit(...)` exactly as they are.

## Step 5 — `HidekoApp.shutdown()`

After the `if self._closed: return` / `self._closed = True` lines, add:
```python
        self.bus.publish("shutdown")
```
Leave the speaker/mic close logic unchanged.

## Step 6 — `main()`

After `opts = parse_args(argv)` (and before the early-exit flags), add:
```python
    bus = EventBus()
    console = ConsoleSubscriber(Status())
    bus.subscribe(ALL, console.handle)
```

In the `--text` branch, replace:
```python
            print(f"Hideko: {response.text}")
```
with:
```python
            bus.publish("speaking", text=response.text)
```
Leave the `error: ...` stderr print in that branch unchanged.

Replace:
```python
    app = HidekoApp(config, opts)
```
with:
```python
    app = HidekoApp(config, opts, bus=bus)
```

Do not add events to `--list-devices`, `--calibrate`, `--facts`, or `--forget` — those are CLI utilities, not conversation turns.

## Step 7 — tests

In `tests/test_smoke.py`, add:

- `test_main_text_publishes_speaking` — define a `RecordingBus(EventBus)` that appends `(kind, dict(data))`; monkeypatch `main.EventBus` to it; call `main(["--text", "hello", "--no-tts"])`; assert exit code 0 and that events contain `("speaking", {"text": ...})`; assert no `heard` event (text mode must not print `You:`).
- `test_main_text_output_unchanged` — capture stdout for `main(["--text", "hello", "--no-tts"])` and assert it equals `f"Hideko: {expected}\n"` where `expected` comes from `ResponseHandler(load_config()).respond("hello").text` (compute once in the test, do not hardcode a random variant).
- `test_error_event_published` — construct `HidekoApp` with a fake responder whose `respond` raises `HidekoError`, or simpler: unit-test the replacement by publishing through the app bus directly; at minimum assert `EventBus.publish("error", ...)` reaches a recording subscriber. Keep this test offline and simple.

Do not modify existing smoke tests; add to them.

## Verification

```powershell
python -m pytest -q
python main.py --text "hello" --no-tts | Out-File -Encoding utf8 after_hello.txt
python main.py --text "goodbye" --no-tts | Out-File -Encoding utf8 after_goodbye.txt
python main.py --help | Out-File -Encoding utf8 after_help.txt
Compare-Object (Get-Content baseline_hello.txt) (Get-Content after_hello.txt)
Compare-Object (Get-Content baseline_goodbye.txt) (Get-Content after_goodbye.txt)
Compare-Object (Get-Content baseline_help.txt) (Get-Content after_help.txt)
python scripts\event_probe.py
Remove-Item baseline_*.txt, after_*.txt
```

Expected:

- `pytest` — all pass.
- All three `Compare-Object` commands produce **no output** (identical files).
- `event_probe.py` output matches task 02's expected output.
- `python main.py --facts` still prints facts directly (unchanged).
- No stray `baseline_*.txt` / `after_*.txt` left behind.

If a mic is available, also run `python main.py --turns 2 --no-greet --no-tts` and confirm `[listening]`, `You: ...`, `Hideko: ...`, and the timing line still appear in the same order.

## Stop and ask the human if

- Any `Compare-Object` shows a diff you cannot explain with the event mapping above — stop and show it.
- An existing test depends on `HidekoApp.status` being actively used — report it; do not change the test's frozen expectations without asking.
- You are tempted to fix the `sys.exit()` error handler — that is explicitly out of scope for this task.
