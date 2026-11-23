# Task 08 — Main loop: happy path (echo milestone)

**Goal (one sentence).** Create `main.py` — the only module that owns a `while` loop — and a minimal `response_handler.py` containing only `Response` + `EchoResponder`. Wire mic → VAD → STT → responder → TTS → speaker with half-duplex. Milestone: say "hello", hear *"I heard you say: hello"*.

**You only need this file.** All signatures, imports, and code are inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `main.py` (create), `response_handler.py` (create) — **nothing else** |
| Depends on | tasks 03, 04, 05, 06, 07 |
| Blocks | task 09 onward |
| Time budget | ~60 min |

**Deliberately out of scope here** (later tasks own these, do not implement them now): real response matching, `ResponseHandler`, `ConversationState`, `errors.py`, `logging_setup.py`, `cli.py`, mute key, status class, 3-strike error counter. This task builds the smallest working loop.

---

## 1. What already exists — exact APIs you may call

```python
from config import AppConfig, load_config, ConfigError
from audio_manager import AudioError, Microphone, Speaker
from stt_engine import STTEngine, STTError, Transcript
from tts_engine import TTSEngine, TTSError
from vad import UtteranceRecorder

cfg.audio.sample_rate                  # 16000
cfg.vad.post_playback_flush_ms         # 300
cfg.runtime.half_duplex                # bool
cfg.runtime.max_turns                  # 0 = unlimited
cfg.runtime.log_transcripts            # bool
cfg.runtime.greet_on_start             # bool
cfg.vad.calibrate                      # bool

recorder.calibrate(mic) -> float       # choose threshold (prints its own log line)
recorder.process_block(block) -> np.ndarray | None
recorder.reset() -> None
mic.read_block() -> np.ndarray         # float32 mono, blocksize samples
mic.flush(ms: int) -> None
mic.close() -> None
speaker.play(samples, sample_rate) -> None   # BLOCKING
speaker.close() -> None
stt.warmup() -> float
stt.transcribe(audio, sample_rate) -> Transcript   # .text
tts.is_available() -> bool
tts.synthesize(text) -> AudioClip              # .samples, .sample_rate
```

## 2. Contract — create these exact signatures

```python
# main.py
class HidekoApp:
    def __init__(self, config: AppConfig, args: argparse.Namespace) -> None: ...
    def setup(self) -> None: ...      # heavy init
    def run(self) -> int: ...         # the loop; returns exit code
    def shutdown(self) -> None: ...   # idempotent

def parse_args(argv: list[str] | None = None) -> argparse.Namespace: ...
def main(argv: list[str] | None = None) -> int: ...

# response_handler.py
@dataclass(frozen=True)
class Response:
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False

class EchoResponder:
    def __init__(self, config: AppConfig) -> None: ...
    def respond(self, text: str) -> Response: ...
    def reset(self) -> None: ...
```

> Task 15 creates `cli.py` and task 16 moves `parse_args` there; keep it as one small function here so it is easy to delete. Task 11 will replace `EchoResponder` with `ResponseHandler` behind `cfg.runtime.echo_mode` — put a `# TODO(task 11)` comment at that line.

## 3. Create `response_handler.py` — copy this exactly

```python
from __future__ import annotations

from dataclasses import dataclass

from config import AppConfig


@dataclass(frozen=True)
class Response:
    """A line for Hideko to speak."""
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False


class EchoResponder:
    """Phase-1 stand-in: repeats what it heard. Replaced in task 11."""

    def __init__(self, config: AppConfig) -> None:
        self._count = 0

    def respond(self, text: str) -> Response:
        self._count += 1
        return Response(text=f"I heard you say: {text}", trigger="echo",
                        is_fallback=True, should_exit=False)

    def reset(self) -> None:
        self._count = 0
```

Do **not** add `Trigger`, `ResponseHandler`, any YAML loading, or state. This file will be extended by tasks 10 and 11.

## 4. Create `main.py` — fill the TODOs in this skeleton

```python
from __future__ import annotations

import argparse
import logging
import sys
from time import perf_counter

import numpy as np

from audio_manager import AudioError, Microphone, Speaker
from config import AppConfig, ConfigError, load_config
from response_handler import EchoResponder, Response
from stt_engine import STTEngine, STTError
from tts_engine import TTSEngine, TTSError
from vad import UtteranceRecorder

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Hideko MVP — local voice assistant")
    # TODO: --config (default "config.yaml"), --text TEXT, --turns int, --debug
    return p.parse_args(argv)


class HidekoApp:
    def __init__(self, config: AppConfig, args: argparse.Namespace) -> None:
        self.config = config
        self.args = args
        self._closed = False
        self.stt: STTEngine | None = None
        self.tts: TTSEngine | None = None
        self.speaker: Speaker | None = None
        self.mic: Microphone | None = None
        self.recorder: UtteranceRecorder | None = None
        self.responder: EchoResponder | None = None

    def setup(self) -> None:
        # TODO, IN THIS EXACT ORDER (§5.1):
        #  1. logging.basicConfig(...) console only
        #  2. print/l logging "Hideko MVP — Ctrl+C to stop"
        #  3. self.stt = STTEngine(config); log "STT ready in X.Xs" from warmup()
        #  4. self.tts = TTSEngine(config); if not available -> raise a fatal
        #     error mentioning download_models.py
        #  5. self.speaker = Speaker(config); self.mic = Microphone(config)
        #  6. self.recorder = UtteranceRecorder(config)
        #  7. if config.vad.calibrate: print "Stay quiet for 1 second — calibrating..."
        #     BEFORE calling recorder.calibrate(self.mic)
        #  8. self.responder = EchoResponder(config)   # TODO(task 11)
        #  9. if config.runtime.greet_on_start: synthesize+play greeting once
        ...

    def run(self) -> int:
        # TODO: the loop from §5.2, verbatim in structure.
        # Wrap `while` in try/finally: self.shutdown().
        # Catch KeyboardInterrupt: print(); return 0.
        ...

    def shutdown(self) -> None:
        # TODO: idempotent via self._closed. Close speaker then mic.
        # GUARD BOTH WITH `if ... is not None`: a later task calls this in a
        # `finally` even when setup() failed before the devices were created.
        # Never call sd.stop() directly — Speaker.close()/stop() owns that.
        ...


def main(argv: list[str] | None = None) -> int:
    # TODO (§5.3): parse args; load config; map setup exceptions to exit codes;
    # --text branch must NOT construct Microphone/UtteranceRecorder/STT.
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

## 5. Exact details

### 5.1 `setup()` order (order matters)

1. `logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")`.
2. Log the banner: `Hideko MVP — Ctrl+C to stop`.
3. `self.stt = STTEngine(config)` → `secs = self.stt.warmup()` → log `STT ready in %.1fs`.
4. `self.tts = TTSEngine(config)`; if `not self.tts.is_available()` raise `TTSError("... Run: python scripts/download_models.py --all")`.
5. `self.speaker = Speaker(config)`; `self.mic = Microphone(config)`.
6. `self.recorder = UtteranceRecorder(config)`.
7. If `config.vad.calibrate`: **print** `Stay quiet for 1 second — calibrating...` first, then `self.recorder.calibrate(self.mic)`.
8. `self.responder = EchoResponder(config)` with the `# TODO(task 11)` comment.
9. If `config.runtime.greet_on_start`: `clip = self.tts.synthesize("Hello. I am Hideko. I am listening.")`; `self.speaker.play(clip.samples, clip.sample_rate)`.

### 5.2 `run()` loop — implement this exactly

```
turn = 0
while True:
    if config.runtime.max_turns and turn >= config.runtime.max_turns: break
    block = mic.read_block()
    utterance = recorder.process_block(block)
    if utterance is None: continue
    if len(utterance) < 0.30 * sample_rate: continue      # ignore coughs/clicks

    t0 = perf_counter()
    transcript = stt.transcribe(utterance, sample_rate)
    t1 = perf_counter()
    if not transcript.text:
        print("  (didn't catch that)"); recorder.reset(); continue

    print(f"You:    {transcript.text}")
    response = responder.respond(transcript.text)
    t2 = perf_counter()
    print(f"Hideko: {response.text}")

    clip = tts.synthesize(response.text)
    t3 = perf_counter()
    speaker.play(clip.samples, clip.sample_rate)
    t4 = perf_counter()

    print(f"  [stt {t1-t0:.1f}s | resp {t2-t1:.2f}s | tts {t3-t2:.1f}s | play {t4-t3:.1f}s | total {t4-t0:.1f}s]")

    if config.runtime.half_duplex:
        recorder.reset()
        mic.flush(config.vad.post_playback_flush_ms)
    turn += 1
    if response.should_exit: break
return 0
```

**Half-duplex is mandatory.** `Speaker.play()` blocks while the OS mic buffer keeps filling. Without `recorder.reset()` **then** `mic.flush(...)`, the next `read_block()` returns Hideko's own voice and she transcribes herself forever. No threads, no second stream.

Inside the loop, catch `(AudioError, STTError, TTSError)` per turn: print `  (audio error, continuing)`, log it, `continue`. A single bad utterance must not kill the app. (The 3-strike counter arrives in task 14 — skip it here.)

### 5.3 `main()` and `setup()` failures

- `--text TEXT` one-shot: skip mic, VAD, STT, and `setup()` entirely. Load config, build `EchoResponder`, synthesize + play the reply, print the timing line, return 0. Must work with **no microphone attached**.
- `--turns N` overrides `config.runtime.max_turns` for this run (store back into the config object via `dataclasses.replace` or a local variable — do not mutate a frozen dataclass in place).
- `--debug` sets DEBUG logging.
- Around `setup()` only, catch `ConfigError → 1`, `AudioError → 2`, `STTError/TTSError → 3`, print one actionable line to stderr (never a traceback), return the code.
- Wrap in `try/finally: app.shutdown()` so devices always close. `shutdown()` must be idempotent (`_closed` flag) or you get "PortAudio: Stream is stopped" spam.

## 6. Rules checklist

- [ ] `main.py` is the **only** module with a `while` loop
- [ ] `main.py` and `__main__` blocks are the only places that print
- [ ] `--text` opens no microphone/VAD/STT
- [ ] `--turns 1` completes one exchange and exits 0
- [ ] after playback: `recorder.reset()` then `mic.flush(...)`, gated on `half_duplex`
- [ ] "stay quiet" prompt printed **before** calibration
- [ ] Ctrl+C caught, clean exit 0, no traceback
- [ ] `shutdown()` in `finally`, idempotent
- [ ] per-turn errors logged and continued
- [ ] `response_handler.py` contains `Response` + `EchoResponder` and **nothing else**
- [ ] Type hints + docstrings on all public functions/classes

## 7. Do NOT

- Do not add threads, `asyncio`, queues, or a producer/consumer pipeline.
- Do not implement barge-in / interrupt-while-speaking.
- Do not put response-matching logic in `main.py`.
- Do not print from engine modules to compensate for missing status lines.
- Do not add a GUI, tray icon, or web server.
- Do not change `EchoResponder`'s method signatures — task 11 depends on them.
- Do not start task 09 or any later task in this task.

## 8. Verify — run and paste output

```powershell
python main.py --text "hello there"
```
Expected: `Hideko: I heard you say: hello there`, a timing line, audible speech, no mic opened.

```powershell
python main.py --turns 1
```
Say "hello". Expected: `You: hello` / `Hideko: I heard you say: hello`, clean exit 0.

Half-duplex check (the one people skip): say "hello" once, then **stay silent 10 s**. Expected: exactly one exchange. Two `Hideko:` lines means the flush is missing.

Ctrl+C check: run `python main.py`, press Ctrl+C while listening. Expected: immediate clean exit, no traceback, no PortAudio spam.

```powershell
python -m pytest -q
```
Expected: still passes.

## 9. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 09.
