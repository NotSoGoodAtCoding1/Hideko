# Task 16 — Wire the CLI into `main.py`

**Goal (one sentence).** Modify **only `main.py`** so it uses `cli.parse_args()` / `Status` / `KeyListener`, adds `--list-devices`, `--calibrate`, `--no-tts`, `--no-greet`, `--mute-key`, and per-turn status lines.

**You only need this file.** Every edit is shown as before/after. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `main.py` — **modify only** |
| Depends on | tasks 08, 11, 14, 15 |
| Blocks | task 22 |
| Time budget | ~50 min |

`cli.py` from task 15 already provides `CliOptions`, `parse_args()`, `KeyListener`, and `Status`. Do not modify it.

---

## 1. Imports and constructor

```python
# before
import argparse
...
from audio_manager import AudioError, Microphone, Speaker

# after
from cli import CliOptions, KeyListener, Status, parse_args
from audio_manager import AudioError, Microphone, Speaker, list_devices
```
Delete the local `parse_args()` function from `main.py` entirely (task 15 owns it now).

```python
# before
def __init__(self, config: AppConfig, args: argparse.Namespace) -> None:
    self.config = config
    self.args = args

# after
def __init__(self, config: AppConfig, opts: CliOptions) -> None:
    self.config = config
    self.opts = opts
    self.keys = KeyListener()
    self.status = Status()
    self._paused = False
    self._listening_shown = False
    self.tts: TTSEngine | None = None
```
Rename **every** `self.args.` in the file to `self.opts.` (`self.args.debug` → `self.opts.debug`, `self.args.log_file` → `self.opts.log_file`).

## 2. `setup()` changes

- Step 4 — skip TTS entirely when `--no-tts` (this is what lets the app run with **no Piper installed**):

```python
if not self.opts.no_tts:
    self.tts = TTSEngine(config)
    if not self.tts.is_available():
        raise TTSError("Piper binary/voice missing. Run: python scripts/download_models.py --all")
```

- Step 9 — greeting condition becomes:

```python
if config.runtime.greet_on_start and not self.opts.no_greet and self.tts is not None:
    ...
```

## 3. `main()` — handle the early-exit flags BEFORE constructing `HidekoApp`

Put these right after `opts = parse_args(argv)` and **before** `load_config()` where possible:

```python
if opts.list_devices:
    for d in list_devices():
        print(f"{d.index:3}  {d.name}  in={d.max_input_channels} out={d.max_output_channels} sr={d.default_samplerate}")
    return 0
```
`--list-devices` must **not** load Whisper or Piper and must work with no models downloaded.

```python
if opts.calibrate:
    cfg = load_config(opts.config)
    mic = Microphone(cfg)
    try:
        threshold = UtteranceRecorder(cfg).calibrate(mic)
        print(f"VAD threshold: {threshold:.1f} dBFS")
    finally:
        mic.close()
    return 0
```
(May be placed after config loading.) No STT/TTS construction here.

For the `--text` branch: choose the responder by `cfg.runtime.echo_mode` (task 11 logic — either `EchoResponder` or `ResponseHandler`), and if `opts.no_tts`, print the response but skip synthesis/playback.

Use `opts.turns` (not `args.turns`) for the override, and `opts.log_file` / `opts.debug` for logging.

## 4. `run()` — loop additions

At the **top of each loop iteration**, before `read_block()`:

```python
key = self.keys.poll()
if key == "q":
    break
if key == self.opts.mute_key and self.opts.mute_key.lower() != "none":
    self._paused = not self._paused
    self._listening_shown = False
    if self._paused:
        self.status.paused()
    else:
        self.status.listening()
        self._listening_shown = True
if self._paused:
    self.mic.flush(self.config.audio.block_ms)
    continue
if not self._listening_shown:
    self.status.listening()
    self._listening_shown = True
```

**Do not print `[listening]` while paused.** Print it once on entering idle, not on every 32 ms block.

### Per-turn status flow (replace the raw `print()` calls from task 08)

```python
self.status.thinking()                 # right before stt.transcribe(...)
...
self.status.heard(transcript.text)     # replaces print(f"You:    ...")
...
self.status.say(response.text)         # replaces print(f"Hideko: ...")
...
self.status.speaking()                 # right before speaker.play(...)
...
self.status.timing(t1-t0, t2-t1, t3-t2, t4-t3)
```

`--no-tts`: skip `synthesize` + `play`, set `tts`/`play` timings to `0.0`, still print the response. If the turn produced no audio, print a short `[resp 0.00s]` line instead of the full timing line. This must not require Piper.

## 5. Rules checklist

- [ ] local `argparse` and local `parse_args()` deleted from `main.py`
- [ ] `HidekoApp` takes `CliOptions` as its second argument; no `self.args` remains
- [ ] `--help` lists all 10 flags (inherited from `cli.build_parser()`)
- [ ] `--list-devices` works with no models, no mic opened
- [ ] `--calibrate` opens mic, prints threshold, closes mic, exits 0
- [ ] `--text --no-tts` works with no models and no mic
- [ ] `--no-tts` skips `TTSEngine` construction in `setup()`
- [ ] `--turns` overrides `runtime.max_turns` (0 = unlimited)
- [ ] `--no-greet` skips the startup line
- [ ] mute toggles on a single keypress (no Enter), `q` quits with code 0
- [ ] `[listening]` printed once per idle transition, never while paused
- [ ] timing line after every spoken turn
- [ ] no colour codes, no background thread

## 6. Do NOT

- Do not modify `cli.py`, `response_handler.py`, or any engine module.
- Do not add `click`, `typer`, `rich`, or `colorama`.
- Do not make key handling a background thread.
- Do not support remapping keys beyond `--mute-key`.
- Do not print `trigger=` to the console.

## 7. Verify — run and paste output

```powershell
python main.py --help
```
Expected: all 10 flags listed with one-line help text.

```powershell
python main.py --list-devices
echo $LASTEXITCODE
```
Expected: device table, exit 0, no model loading.

```powershell
python main.py --text "hello" --no-tts
```
Expected: `Hideko: Hello! I am Hideko.` and exit 0, with **no audio device opened** and no Piper present.

```powershell
python main.py --turns 2 --no-tts
```
Expected: two exchanges, `[listening]` between them, exit 0.

Mute test: `python main.py` — say "hello", press `m`, say "hello" again (nothing happens), press `m`, say "hello" (responds). Press `q` to quit. Paste the console transcript.

```powershell
python -m pytest -q
```
Expected: still passes (integration tests arrive in task 22).

## 8. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 17.
