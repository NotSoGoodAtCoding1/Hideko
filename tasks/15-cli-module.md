# Task 15 — CLI module (`cli.py`)

**Goal (one sentence).** Create **one file**, `cli.py`, holding argument parsing, a non-blocking key listener, and status-line formatting. No other file changes.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `cli.py` — **create**, nothing else |
| Depends on | task 03 (`AppConfig`, not directly used here) |
| Blocks | task 16 |
| Time budget | ~40 min |

Do not modify `main.py` — task 16 does the wiring.

---

## 1. Contract — copy verbatim

```python
@dataclass(frozen=True)
class CliOptions:
    config: Path
    text: str | None
    turns: int | None
    debug: bool
    no_tts: bool
    no_greet: bool
    list_devices: bool
    calibrate: bool
    log_file: Path | None
    mute_key: str

def build_parser() -> argparse.ArgumentParser: ...
def parse_args(argv: list[str] | None = None) -> CliOptions: ...

class KeyListener:
    """Non-blocking single-key reader (Windows only; no-op elsewhere)."""
    def poll(self) -> str | None: ...   # lowercase key or None
    @property
    def supported(self) -> bool: ...

class Status:
    """Console status lines with consistent formatting and flushing."""
    def listening(self) -> None: ...
    def thinking(self) -> None: ...
    def speaking(self) -> None: ...
    def paused(self) -> None: ...
    def heard(self, text: str) -> None: ...
    def say(self, text: str) -> None: ...
    def timing(self, stt: float, resp: float, tts: float, play: float) -> None: ...
```

## 2. Flags (`build_parser`)

| Flag | Behaviour |
|------|-----------|
| `--config PATH` | default `config.yaml` |
| `--text "..."` | one-shot: skip mic + VAD, run responder + TTS, exit |
| `--turns N` | stop after N exchanges (overrides `runtime.max_turns`) |
| `--no-tts` | print responses but do not synthesize or play |
| `--no-greet` | skip the startup greeting |
| `--list-devices` | print the device table and exit 0 |
| `--calibrate` | print the calibration result and exit 0 |
| `--debug` | console log level DEBUG |
| `--log-file PATH` | override `logging.file` |
| `--mute-key KEY` | default `m`; the literal `none` disables it |

`parse_args()` builds the parser, parses, and returns `CliOptions(...)` with `Path` values for `config` and `log_file`. Import `Path` from `pathlib`.

## 3. `KeyListener`

- Windows: `import msvcrt` (guarded by `try/except ImportError`). `poll()`:
  - `if not msvcrt.kbhit(): return None`
  - `ch = msvcrt.getwch()`
  - if `ch in ("\x00", "\xe0")`: consume the next byte with `msvcrt.getwch()` and return `None`
  - return `ch.lower()`
- Non-Windows: `supported` is `False`, `poll()` always returns `None`.
- **Never block. Never read from stdin** (no `input()`). `poll()` is called ~30×/second (once per 32 ms block), so it must be cheap.

## 4. `Status` — exact output strings

| Method | Prints |
|--------|--------|
| `listening()` | `[listening]` |
| `thinking()` | `  ...thinking` followed by a carriage return (`\r`, no newline) so the timing line overwrites it |
| `speaking()` | `[speaking]` |
| `paused()` | `[paused — press m to resume]` (use the configured key in task 16; here the literal `m` is fine) |
| `heard(text)` | `You:    {text}` |
| `say(text)` | `Hideko: {text}` |
| `timing(stt, resp, tts, play)` | `  [stt 1.9s | resp 0.00s | tts 0.9s | play 1.2s | total 4.0s]` — `total` = sum of the four |

Every `print()` uses `flush=True`. **No ANSI colour codes** — Windows terminals, redirected output, and tests all break with them.

## 5. Rules checklist

- [ ] `CliOptions` frozen dataclass with the 10 exact fields
- [ ] `build_parser()` / `parse_args()` signatures exact
- [ ] All 10 flags present with one-line `help=` text
- [ ] `KeyListener` non-blocking, Windows-aware, handles special-key prefix bytes
- [ ] `Status` strings exactly as tabled; every print flushed
- [ ] No colour escapes; no `input()`; no background thread
- [ ] Type hints + docstrings on all public functions/classes

## 6. Do NOT

- Do not add `click`, `typer`, `rich`, or `colorama`.
- Do not add a GUI, tray icon, or web UI.
- Do not make key handling a background thread.
- Do not support remapping keys beyond `--mute-key`.
- Do not modify `main.py` or any other module.

## 7. Verify — run and paste output

```powershell
python -c "from cli import parse_args; o=parse_args([]); print(o); o2=parse_args(['--text','hi','--turns','2','--no-tts','--mute-key','k']); print(o2)"
```
Expected: two `CliOptions(...)` values; the second has `text='hi'`, `turns=2`, `no_tts=True`, `mute_key='k'`, defaults elsewhere.

```powershell
python -c "from cli import KeyListener, Status; k=KeyListener(); print('supported', k.supported, 'poll', k.poll()); Status().timing(1.9, 0.0, 0.9, 1.2)"
```
Expected: `supported ... poll None` and a timing line with `total 4.0s`.

```powershell
python -m pytest -q
```
Expected: still passes.

## 8. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 16.
