# Task 14 — Robustness wiring in `main.py`

**Goal (one sentence).** Modify **only `main.py`** so it uses the new logging setup, maps exceptions to exit codes via `exc.exit_code`, counts 3 consecutive failures, and logs RSS every 20 turns.

**You only need this file.** Every edit is shown as before/after. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `main.py` — **modify only** |
| Depends on | tasks 08, 12, 13 |
| Blocks | task 15, task 21, task 22 |
| Time budget | ~35 min |

Everything created in tasks 12 and 13 already exists:

```python
from errors import HidekoError
from logging_setup import setup_logging, memory_rss_mb
exc.exit_code    # 1 config, 2 audio, 3 model, 4 response data
```

`HidekoError.exit_code` defaults to 1; subclasses set their own. No `except Exception` is allowed anywhere except narrow, documented cases.

---

## 1. Add two imports and one CLI flag

```python
# imports
import dataclasses
from errors import HidekoError
from logging_setup import memory_rss_mb, setup_logging

# in parse_args(), add:
p.add_argument("--log-file", type=Path, default=None, help="override logging.file")
```
(`from pathlib import Path` is needed.)

## 2. `setup()` — replace the `logging.basicConfig(...)` line

```python
# before (task 08):
logging.basicConfig(level=..., format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

# after:
setup_logging(self.config.logging, debug=self.args.debug, log_file=self.args.log_file)
```

Keep the rest of `setup()` order exactly as task 08 defined it. Also add near the top of `setup()`:

```python
self._consecutive_errors = 0
self._start_rss = memory_rss_mb()
```

## 3. `run()` — replace the per-turn error handler

Task 08 had:

```python
except (AudioError, STTError, TTSError):
    print("  (audio error, continuing)")
    continue
```

Replace with:

```python
except HidekoError as exc:
    print(f"  ({exc})")
    logger.exception("turn failed: %s", exc)
    self._consecutive_errors += 1
    if self._consecutive_errors >= 3:
        return exc.exit_code
    continue
```

Reset `self._consecutive_errors = 0` after any successful turn (right after the timing line, before the half-duplex flush is fine).

## 4. `run()` — memory logging every 20 turns

After incrementing `turn`, when `turn % 20 == 0`:

```python
rss = memory_rss_mb() or -1
logger.info("memory: %.0f MB RSS, %d objects", rss, len(gc.get_objects()))
gc.collect()
if self._start_rss is not None and rss != -1 and rss - self._start_rss > 300:
    logger.warning("RSS grew >300 MB since start (%.0f -> %.0f MB)", self._start_rss, rss)
```

Add `import gc`. Do **not** spawn a supervisor, watchdog, or auto-restart process — a manual restart is the documented behaviour.

## 5. `main()` — replace the whole function

```python
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        if args.turns is not None:
            config = dataclasses.replace(
                config,
                runtime=dataclasses.replace(config.runtime, max_turns=args.turns),
            )
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    # --text branch: no mic, no VAD, no STT, no logging file required.
    # Wrap it in the SAME error handling as the normal path — a missing model
    # must produce one line and exit 3, never a traceback.
    if args.text is not None:
        try:
            # Keep task 08's existing one-shot implementation here (it builds
            # TTSEngine, so a bad voice_model raises TTSError with the hint).
            ...
        except HidekoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return exc.exit_code

    app = HidekoApp(config, args)
    try:
        app.setup()
        return app.run()
    except HidekoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        app.shutdown()
```

Keep task 08's `--text` implementation; just make sure a setup failure in the normal path prints **one line to stderr, never a traceback**. `raise SystemExit(main())` must remain in `__main__`.

Exception-to-code mapping now comes from `exc.exit_code`, so the old hardcoded `if isinstance(...)` table in task 08 can be deleted.

## 6. Rules checklist

- [ ] `setup_logging()` called at the very start of `setup()`
- [ ] `--log-file` flag added to the local parser
- [ ] per-turn `except HidekoError` with 3-strike rule
- [ ] counter reset after a successful turn
- [ ] top-level `main()` catches `HidekoError` and `KeyboardInterrupt`, prints one line, returns code
- [ ] memory logged every 20 turns with `gc.collect()` and >300 MB warning
- [ ] no supervisor / auto-restart / watchdog
- [ ] no broad `except Exception` added
- [ ] `finally: app.shutdown()` retained
- [ ] Type hints + docstrings on all public functions/classes

## 7. Do NOT

- Do not modify `errors.py`, `logging_setup.py`, or any engine module.
- Do not add `psutil`, `loguru`, or any new dependency.
- Do not swallow exceptions beyond the documented 3-strike rule.
- Do not log full transcripts when `runtime.log_transcripts` is false.
- Do not add a `--no-tts` / `--list-devices` / mute key — those arrive in tasks 15–16.

## 8. Verify — run and paste output

```powershell
@"
audio:
  sample_rate: 8000
"@ | Set-Content -Encoding utf8 bad.yaml
python main.py --config bad.yaml
echo $LASTEXITCODE
Remove-Item bad.yaml
```
Expected: `error: audio.sample_rate must be 16000 ...` and `1`. **No traceback.**

```powershell
python -c "import shutil; shutil.copy('config.yaml','tmp_bad.yaml')"
# edit tmp_bad.yaml: set tts.voice_model to models/piper/nope.onnx
python main.py --config tmp_bad.yaml --text "hi"
echo $LASTEXITCODE
Remove-Item tmp_bad.yaml
```
Expected: exit `3`, one-line message mentioning `download_models.py`.

```powershell
python main.py --text "hello" --debug
Get-Content .\logs\hideko.log -Tail 5
```
Expected: file exists, contains DEBUG lines, console shows at least one DEBUG line.

```powershell
python -m pytest -q
```
Expected: still passes.

## 9. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 15.
