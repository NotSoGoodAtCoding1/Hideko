# Hideko MVP — Task Breakdown

This folder splits [`../plan.md`](../plan.md) into **24 small, self-contained tasks**. Each task is written so a small model (even < 14B parameters) can finish it **by reading exactly one file**.

> All task numbers are stable. Tasks 05–24 use the uniform small-agent format; tasks 01–04 were kept as originally written. The later tasks were split so each touches **one concern and at most two files**.

## How to use this folder

1. Give an agent **exactly one task file** and **nothing else** — not this README, not `plan.md`, not other task files. Every contract, code skeleton, rule, and verification command is **inlined** in the task file. Small agents lose track when asked to read five documents; do not make them.
2. The agent reads its one file, implements, runs the **Verification** commands, and pastes the real output.
3. If verification fails, the agent fixes it. It must **not** start the next task.
4. One task = one commit (if git is available) or one reviewable change set.
5. Never give an agent two tasks at once. Never let an agent "improve" modules owned by another task.

### What changed from the old 16-task set

The old tasks 12, 13, 14, and 15 were too broad for a small agent: one touched 8 files, one demanded 7 test files, one mixed three unrelated deliverables. They were split. The old `main.py` was edited by four different tasks; now each `main.py` edit is a separate task with its before/after shown inline.

**Old → new mapping** (use this to resolve any stale number inside tasks 01–04):

| Old | New |
|-----|-----|
| 06 | 06 |
| 07 | 07 |
| 08 | 08 |
| 09 | 09 |
| 10 | 10 |
| 11 | 11 |
| 12 | 12 (errors), 13 (logging), 14 (main robustness) |
| 13 | 15 (cli.py), 16 (main wiring) |
| 14 | 17 (fixtures+config), 18 (VAD), 19 (handler+STT), 20 (TTS+audio) |
| 15 | 21 (benchmark), 22 (soak), 23 (integration) |
| 16 | 24 |

## Ground rules for every agent

- **OS**: Windows 10/11, PowerShell. All commands in the tasks are PowerShell.
- **Python**: 3.11.x only. Do not use 3.12+ (binary wheel availability for `ctranslate2`).
- **Project root**: `C:\Users\Ilya\Documents\new_prj` (the folder containing this `tasks/` folder). All paths in code are resolved relative to this folder, never to the current working directory.
- **No GPU.** Everything runs on CPU with `int8` quantization.
- **No network at runtime.** Network is only used by `scripts/download_models.py` (task 02).
- **No new dependencies** without adding a pinned line to `requirements.txt` in the same change.
- **Type hints** on every public function. **Docstring** on every public class/function.
- **No `print()` in library code** (`audio_manager.py`, `vad.py`, `stt_engine.py`, `tts_engine.py`, `response_handler.py`, `config.py`) outside their `if __name__ == "__main__":` blocks. Use `logging.getLogger(__name__)` inside functions. Only `main.py`, `cli.py`, scripts, and `__main__` blocks may write to the console.
- **No bare `except:`** and no `except Exception: pass`. Log and re-raise as a typed error.
- **Never break imports on machines without a microphone.** Importing any module must never open an audio device. Device access happens only when a class is instantiated or a function is called.
- **Tests must pass offline** with no mic and no speakers: `python -m pytest -q`.

## Task graph

Phases 0–1 are the "dumb loop" milestone: speak → hear a fixed echo. Phase 2 adds real responses. Phase 3 makes it presentable.

| # | Task | Phase | Depends on | Produces |
|---|------|-------|------------|----------|
| 01 | [Project scaffold & toolchain](01-project-scaffold.md) | 0 | — | venv, `requirements.txt`, dirs, smoke test |
| 02 | [Model & dependency acquisition](02-model-acquisition.md) | 0 | 01 | `scripts/download_models.py`, `scripts/check_env.py` |
| 03 | [Config loader](03-config-loader.md) | 1 | 01 | `config.yaml`, `config.py` |
| 04 | [Audio manager](04-audio-manager.md) | 1 | 01, 03 | `audio_manager.py` |
| 05 | [VAD & utterance recorder](05-vad-utterance.md) | 1 | 03, 04 | `vad.py` |
| 06 | [STT engine](06-stt-engine.md) | 1 | 02, 03 | `stt_engine.py` |
| 07 | [TTS engine](07-tts-engine.md) | 1 | 02, 03 | `tts_engine.py` |
| 08 | [Main loop: happy path](08-main-loop.md) | 1 | 03, 04, 05, 06, 07 | `main.py`, `response_handler.py` (`Response` + `EchoResponder`) |
| 09 | [Response data files](09-response-data.md) | 2 | 01 | `responses/triggers.yaml`, `responses/fallbacks.yaml`, validator |
| 10 | [Response handler](10-response-handler.md) | 2 | 03, 08, 09 | `response_handler.py` (`Trigger`, `ResponseHandler`) |
| 11 | [Conversation state & wiring](11-wire-responses.md) | 2 | 08, 10 | state lines in `response_handler.py`, responder choice in `main.py` |
| 12 | [Error hierarchy & migration](12-error-hierarchy.md) | 3 | 03–11 | `errors.py` + one-line class-base migrations |
| 13 | [Logging setup](13-logging-setup.md) | 3 | 03, 12 | `logging_setup.py` |
| 14 | [Main robustness wiring](14-main-robustness.md) | 3 | 08, 12, 13 | exit codes, 3-strike rule, RSS logging in `main.py` |
| 15 | [CLI module](15-cli-module.md) | 3 | 03 | `cli.py` (`CliOptions`, parser, `KeyListener`, `Status`) |
| 16 | [CLI wiring](16-cli-wiring.md) | 3 | 08, 11, 14, 15 | all CLI flags + mute/status in `main.py` |
| 17 | [Unit tests: fixtures + config](17-unit-tests-config.md) | 3 | 03 | `tests/conftest.py`, `tests/test_config.py` |
| 18 | [Unit tests: VAD](18-unit-tests-vad.md) | 3 | 05, 17 | `tests/test_vad.py` |
| 19 | [Unit tests: handler + STT](19-unit-tests-response-and-stt.md) | 3 | 06, 10, 11, 17 | `tests/test_response_handler.py`, `tests/test_stt_engine.py` |
| 20 | [Unit tests: TTS + audio](20-unit-tests-tts-audio.md) | 3 | 04, 07, 17 | `tests/test_tts_engine.py`, `tests/test_audio_manager.py` |
| 21 | [Benchmark script](21-benchmark-script.md) | 3 | 06, 07, 10, 14 | `scripts/benchmark.py`, `logs/benchmark.md` |
| 22 | [Soak test script](22-soak-test.md) | 3 | 07, 10, 14, 21 | `scripts/soak_test.py`, `logs/soak.md` |
| 23 | [Integration tests](23-integration-tests.md) | 3 | 14, 16 | `tests/test_integration.py` |
| 24 | [README & docs](24-docs.md) | 3 | all | `README.md` |

## Shared module contracts

These signatures are **frozen**. A task may not change them; if a change is truly required, stop and ask the human.

```python
# config.py
def load_config(path: str | Path = "config.yaml") -> AppConfig: ...

# audio_manager.py
def list_devices() -> list[AudioDevice]: ...
class Microphone:            # context manager
    def __init__(self, config: AppConfig) -> None: ...
    def read_block(self) -> np.ndarray: ...      # float32, mono, config.audio.sample_rate
    def flush(self, ms: int) -> None: ...
    def close(self) -> None: ...
class Speaker:
    def __init__(self, config: AppConfig) -> None: ...
    def play(self, samples: np.ndarray, sample_rate: int) -> None: ...  # blocking
    def stop(self) -> None: ...
    def close(self) -> None: ...

# vad.py
class UtteranceRecorder:
    def __init__(self, config: AppConfig, vad: VAD | None = None) -> None: ...
    def calibrate(self, mic: "Microphone") -> float: ...          # returns threshold dBFS
    def process_block(self, block: np.ndarray) -> np.ndarray | None: ...  # full utterance or None
    def reset(self) -> None: ...

# stt_engine.py
@dataclass
class Transcript:
    text: str
    language: str | None
    duration_s: float
    latency_s: float
    avg_logprob: float | None
class STTEngine:
    def __init__(self, config: AppConfig) -> None: ...
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript: ...

# tts_engine.py
@dataclass
class AudioClip:
    samples: np.ndarray      # float32 mono, -1.0..1.0
    sample_rate: int
    duration_s: float
class TTSEngine:
    def __init__(self, config: AppConfig) -> None: ...
    def synthesize(self, text: str) -> AudioClip: ...

# response_handler.py
@dataclass
class Response:
    text: str
    trigger: str            # trigger name, or "fallback"
    is_fallback: bool
    should_exit: bool = False
class ResponseHandler:
    def __init__(self, config: AppConfig, rng: random.Random | None = None) -> None: ...
    def respond(self, text: str) -> Response: ...
    def reset(self) -> None: ...
```

`EchoResponder` (task 08) is a temporary stand-in with the same `respond(text) -> Response` method so that task 11 can swap it in.

## Data flow (what each task plugs into)

```
mic --float32 16k blocks--> UtteranceRecorder --> np.ndarray utterance
      --> STTEngine.transcribe() --> Transcript.text
      --> ResponseHandler.respond() --> Response.text
      --> TTSEngine.synthesize() --> AudioClip
      --> Speaker.play()
```

## Latency budget (target hardware: 4 cores @ 3.0 GHz, 8 GB RAM)

| Stage | Budget | Notes |
|-------|--------|-------|
| Utterance end detection | ≤ 0.8 s | `vad.silence_ms` = 700 |
| STT (5 s utterance, tiny.en int8) | 1.5–3 s | measured in task 21 |
| Response generation | < 20 ms | pure Python matching |
| TTS (10 words, amy-medium) | 0.5–1.5 s | subprocess spawn is ~200 ms |
| Playback start | ≤ 0.2 s | `sd.play` + `sd.wait` |
| **Total** | **3–6 s** | hard ceiling for acceptance: 10 s |

## Definition of Done (applies to every task)

- [ ] The task's **Verification** commands were run and their real output pasted in the report.
- [ ] `python -m pytest -q` still passes (from task 17 onward; before that, the smoke test passes).
- [ ] No file outside the task's **Files you touch** list was modified.
- [ ] No new dependency without a `requirements.txt` update.
- [ ] Public functions have type hints; public classes/functions have docstrings.
- [ ] The agent reported: files changed, verification output, and anything it could not finish.

## Troubleshooting index

| Symptom | Where to look |
|---------|---------------|
| `ModuleNotFoundError: sounddevice` | 01 |
| `OSError: PortAudio library not found` | 01, 04 |
| `Invalid device` / `PaErrorCode -9996` | 04 |
| Piper writes a 0-byte WAV | 07 |
| Piper complains about `espeak-ng-data` | 02, 07 |
| STT returns `"Thank you."` for silence | 06 |
| `ctranslate2` / `numpy` version conflict | 01 |
| Model download 403 from HuggingFace | 02 |
| Feedback loop / Hideko transcribes herself | 08, 16 |
| Response never matches "hello" | 09, 10 |
| Every log line appears twice | 13 |
| Wrong exit code on a bad config | 14 |
| `--no-tts` still fails on missing Piper | 16 |
