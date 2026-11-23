# Hideko — Post-MVP Improvement Tasks

This folder turns the agreed improvement scope into **9 small, self-contained tasks**. Each task is written so a small model (even <14B parameters) can finish it **by reading exactly one file** — the task file. Do not make an agent read this README, `plan.md`, or another task file.

> The MVP is **done and working**. This is a follow-on sprint, not a rewrite. Do not restructure the audio loop, do not add streaming, and do not add game/Discord/avatar features.

---

## Decisions locked by the human (do not re-litigate these)

| Topic | Decision |
|---|---|
| Headline goal | **Reduce latency** |
| How | **Cheap wins only** — config/default/tuning changes, no architecture change to the loop |
| Baseline | **No separate baseline phase.** No latency pass/fail number. Record the timings the app already prints. |
| Smarter responses | **Local LLM**, but **fallback only**: YAML triggers always win; the LLM runs only when nothing matches |
| LLM runtime | **llama-cpp-python** (in-process, GGUF, offline) |
| Persistent memory | **Facts on disk**, survives restarts, stays local |
| Platform | **Windows 10/11, PowerShell only** |
| Runtime network | **None.** Offline at runtime is mandatory. |
| Python | 3.11 preferred. 3.12+ **only** if no `llama-cpp-python` wheel exists, and only after verifying `ctranslate2`/`faster-whisper` still work. |
| Hardware | GPU allowed and heavy dependencies allowed — a relaxed change from the MVP's CPU-only rule |
| Effort | ~1 week, small sprint. Order if time gets tight: **latency → memory → LLM**. |
| Explicitly out of scope | Games, streaming STT/TTS, barge-in, Discord, avatar/emotions, music generation, LLM on every turn |

---

## How to use this folder

1. Give an agent **exactly one task file**, nothing else. Every rule, snippet, contract, and verification command is inlined there.
2. The agent implements, runs **Verification**, and pastes real output.
3. If verification fails, the agent fixes it. It must not start the next task.
4. One task = one reviewable change set.
5. Never give an agent two tasks at once. Never let an agent "improve" modules owned by another task.

---

## Task graph

| # | Task | Phase | Depends on | Files produced / touched |
|---|------|-------|------------|--------------------------|
| 01 | [VAD & flush timing defaults](01-vad-latency-timings.md) | A — latency | — | `config.yaml`, `config.py`, `tests/conftest.py`, `tests/test_config.py` |
| 02 | [STT CPU-thread tuning](02-stt-thread-tuning.md) | A — latency | 01 | `config.yaml`, `config.py`, `stt_engine.py`, tests |
| 03 | [Timing visibility & benchmark fix](03-timing-visibility.md) | A — latency | 01, 02 | `main.py`, `scripts/benchmark.py`, `logs/benchmark.md` |
| 04 | [Disk-backed memory store](04-memory-store.md) | B — memory | 03 | `memory_store.py`, `config.py`, `errors.py`, `config.yaml`, tests |
| 05 | [Memory wiring & CLI](05-memory-wiring.md) | B — memory | 04 | `main.py`, `response_handler.py`, `cli.py`, tests |
| 06 | [LLM dependency, config & model](06-llm-deps-config.md) | C — LLM | 05 | `requirements.txt`, `config.py`, `config.yaml`, `errors.py`, `scripts/download_models.py`, `scripts/check_env.py` |
| 07 | [LLM fallback module](07-llm-fallback-module.md) | C — LLM | 06 | `llm_fallback.py`, `tests/test_llm_fallback.py` |
| 08 | [Wire LLM as fallback only](08-llm-wire.md) | C — LLM | 05, 07 | `response_handler.py`, `main.py`, `tests/test_response_handler.py` |
| 09 | [Docs & final verification](09-docs-verification.md) | wrap-up | all | `README.md`, `plan.md`, `logs/benchmark.md`, `logs/soak.md` |

Task 01 → 02 → 03 are the latency phase. Stop after 03 and report before starting 04 if the human wants to review. The same applies after 05.

---

## Ground rules for every agent

- **OS / shell**: Windows 10/11, PowerShell. Commands below are PowerShell.
- **Project root**: `C:\Users\Ilya\Documents\new_prj`. All paths in code resolve relative to this folder, never to the current working directory.
- **Tests must pass offline with no mic and no speakers**: `python -m pytest -q`.
- **No network at runtime.** Network use is limited to `scripts/download_models.py`.
- **Type hints on every public function; docstring on every public class/function.**
- **No `print()` in library code** (`config.py`, `stt_engine.py`, `response_handler.py`, `memory_store.py`, `llm_fallback.py`, etc.) outside `if __name__ == "__main__":`. Use `logging.getLogger(__name__)`. Only `main.py`, `cli.py`, scripts, and `__main__` blocks write to the console.
- **No bare `except:`**, no `except Exception: pass`. Log and re-raise as a typed error.
- **Importing a module must never open an audio device or load a model.** Lazy-load inside the constructor/method.
- **New dependencies must be pinned in `requirements.txt` in the same change.**
- When adding a config key, update **all four** places: `config.yaml`, `_DEFAULTS` in `config.py`, the two known-key sets in `config.py`, and the `config` fixture in `tests/conftest.py`.
- Exit codes: `0` normal, `1` config, `2` audio, `3` model, `4` response data, `5` memory, `6` LLM.

---

## Frozen existing contracts (do not change these signatures)

```python
# config.py
def load_config(path: str | Path = "config.yaml") -> AppConfig: ...

# audio_manager.py
def list_devices() -> list[AudioDevice]: ...
class Microphone:            # context manager
    def __init__(self, config: AppConfig) -> None: ...
    def read_block(self) -> np.ndarray: ...
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
    def calibrate(self, mic: Microphone) -> float: ...
    def process_block(self, block: np.ndarray) -> np.ndarray | None: ...
    def reset(self) -> None: ...

# stt_engine.py
class STTEngine:
    def __init__(self, config: AppConfig) -> None: ...
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript: ...

# tts_engine.py
class TTSEngine:
    def __init__(self, config: AppConfig) -> None: ...
    def synthesize(self, text: str) -> AudioClip: ...

# response_handler.py
@dataclass(frozen=True)
class Response:
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False
class EchoResponder:
    def respond(self, text: str) -> Response: ...
```

`ResponseHandler.respond(self, text: str) -> Response` is frozen. Its `__init__` may **gain optional keyword arguments only** (`memory`, `llm`) — existing call sites with one positional argument must keep working.

## New contracts (frozen once introduced)

```python
# memory_store.py   (task 04)
@dataclass(frozen=True)
class Fact:
    key: str
    value: str
    updated_at: float
class MemoryStore:
    def __init__(self, config: AppConfig) -> None: ...
    def load(self) -> None: ...
    def save(self) -> None: ...
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def all(self) -> dict[str, str]: ...
    def observe(self, text: str) -> list[Fact]: ...
    def clear(self) -> None: ...

# llm_fallback.py   (task 07)
@dataclass(frozen=True)
class LLMReply:
    text: str
    latency_s: float
class LLMBackend:               # protocol-like; available() + generate()
    def available(self) -> bool: ...
    def generate(self, prompt: str) -> str: ...
class LlamaCppBackend(LLMBackend): ...
class NullBackend(LLMBackend): ...
class LLMFallback:
    def __init__(self, config: AppConfig, memory: MemoryStore | None = None,
                 backend: LLMBackend | None = None) -> None: ...
    def available(self) -> bool: ...
    def respond(self, text: str) -> LLMReply: ...
```

---

## Known issues found during review — NOT in this sprint

These are recorded for a later sprint; agents must **not** fix them here:

- `main.py:run()` — a `HidekoError` caught inside `run()` ends the loop; with fewer than 3 consecutive errors the function falls through and `main()` exits `0`. Error handling deserves its own task.
- `benchmark.py` line 282 assigns `t0` but never uses it before calling `warmup()`.
- `response_handler.py` has an unused `Path` import and a redundant `import random` inside `main()`.
- `logs/soak.md` reports `0.0 MB` RSS throughout, so its PASS result is not meaningful yet.

Task 03 explicitly *does* fix the benchmark's ms-vs-seconds budget comparison because that verification is needed for this sprint.

---

## Post-review corrections applied to the finished work

Agents reported all tests green, but the model setup was never verified end-to-end. Corrections made directly in the workspace:

- The `0.5B` model is now actually downloaded (`models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf`, 491 MB). It was missing; `download_models.py` crashed with `WinError 2` because it called `.stat()` before checking `is_file()`. Fixed.
- Both models are supported: `--llm` fetches the 0.5B default, `--llm-coder` fetches the optional 7B Coder model (~4.4 GB). Change `llm.model_path` to swap.
- Licences **verified from Hugging Face model cards**: both `Qwen2.5-0.5B-Instruct-GGUF` and `Qwen2.5-Coder-7B-Instruct-GGUF` are **Apache-2.0**. The earlier README claim that this was verified in task 06 was false.
- `llm.max_tokens` reduced from 512 to 80, `timeout_s` set to 15, `n_gpu_layers` defaults to `-1` (offload all layers). `config.py` now accepts `-1` and lists every `llm.*` key as known.
- `llama-cpp-python` was pinned but never installed; the real LLM path therefore fell back to YAML. `scripts/check_env.py` now checks the `llama_cpp` import when `llm.enabled: true`, so this class of failure is visible. PyPI only ships an sdist — install a prebuilt wheel: `.../whl/cpu` (CPU) or `.../whl/cu125` (CUDA). Final pin: `llama-cpp-python==0.3.36` (`0.3.12` has no wheel; the CPU index has no 0.3.37 wheel).
- **CUDA offload now works — the `0xc000001d` crash is resolved (2026-11-23).** Root cause: the prebuilt CUDA wheel's `llama_cpp/lib/ggml-cpu.dll` is compiled with AVX-512, so on a CPU without AVX-512 (Ryzen 5 5600 = Zen 3) every model load faults in `ggml_backend_cpu_init`, even with `n_gpu_layers: 0`. The 0.3.36 CPU wheel's `ggml-cpu.dll` is baseline x86-64; swapping it into the same-release CUDA wheel keeps `ggml-cuda.dll` intact and restores GPU offload. `scripts/setup_llama_cuda.py` automates the install/repair and `scripts/llm_cuda_probe.py -1` verifies it. Verified: `llama-cpp-python==0.3.36` (cu125) + `nvidia-cuda-runtime-cu12==12.5.82` + `nvidia-cublas-cu12==12.5.3.2` on RTX 3060 / driver 610.47. 0.5B: ~264 tok/s on GPU vs ~85 tok/s on CPU; 7B Coder: ~4.5 GB VRAM, ~48 tok/s, coherent code answers.
- `llm.n_gpu_layers` now defaults to `-1` in both `config.yaml` and `config.py`; the CPU wheel ignores it, so behaviour is unchanged there. `llm.enabled` remains `false` and YAML triggers still win.
- `llm_fallback.py` now registers bundled CUDA/NVIDIA DLL directories on Windows before importing `llama_cpp`, retains the DLL-directory handles, and strips non-ASCII characters from generated replies (Qwen appends emoji that broke cp1251 consoles and English TTS). `main.py` reconfigures stdout/stderr with `errors="replace"`.
- Verified end-to-end with `llm.enabled: true`: `what is the capital of France` → `France's capital is Paris. Is there anything else you'd like to know? Let me know!`
- `llm_fallback.py` now wraps GPU-load failures in `LLMError` and retries with `n_gpu_layers=0` instead of leaking `OSError`/`RuntimeError`.

**Lesson for future agents:** tests use mocked backends and `llm.enabled: false`, so a green suite does not prove the LLM works. Always do one real generation with `llm.enabled: true` and the configured model path.

GPU/CUDA offload debugging is tracked in [`../debug-tasks/01-cuda-wheel-debug.md`](../debug-tasks/01-cuda-wheel-debug.md). It is **resolved**: see the corrected Result section there. The default install stays on the CPU wheel; GPU offload is opt-in via `python scripts/setup_llama_cuda.py`.

Superseded: the in-process LLM path described above has been replaced by the KoboldCpp HTTP backend. See kobold-tasks/README.md. debug-tasks/01 remains as historical context only.
