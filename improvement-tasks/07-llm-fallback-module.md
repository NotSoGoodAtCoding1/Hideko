# Task 07 — LLM fallback module

**Phase C (LLM). Depends on task 06. Touch at most 2 files.**

## Goal

Create `llm_fallback.py`: an in-process `llama-cpp-python` wrapper that produces a short reply for turns no YAML trigger matched. Importing the module must **never** load the model or require `llama_cpp` to be installed. Offline only. Bounded output length and a timeout.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No network at runtime. No `print()` in library code outside `if __name__ == "__main__":`.
- Type hints + docstrings on all public classes/functions. No bare `except:`.
- Tests must pass offline with no model file: `python -m pytest -q`.
- Do not wire this into `ResponseHandler` — that is task 08.

## Required public API (frozen)

```python
@dataclass(frozen=True)
class LLMReply:
    text: str
    latency_s: float

class LLMBackend:               # protocol-like base
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

## Steps

### `llm_fallback.py`

1. Imports at top: `concurrent.futures` (`ThreadPoolExecutor`, `TimeoutError` as `FuturesTimeout`), `dataclasses`, `logging`, `os`, `time`, `argparse`, `sys`, `typing`. Import `AppConfig` from `config`, `LLMError` from `errors`, `MemoryStore` from `memory_store`. **Do not import `llama_cpp` at module level.**

2. `LLMBackend` — a small base class with `available()` returning `False` and `generate()` raising `NotImplementedError`. Docstring explains it exists so tests can inject a fake.

3. `NullBackend(LLMBackend)` — `available()` always `False`; `generate()` raises `LLMError("LLM backend is disabled")`.

4. `LlamaCppBackend(LLMBackend)`:
   - `__init__(self, config: AppConfig) -> None` stores config and sets `self._model = None`.
   - `available(self) -> bool` returns `self._config.llm.enabled and self._config.llm.model_path.is_file()`.
   - `_load(self) -> None`:
     - If `self._model is not None`, return.
     - If not `available()`, raise `LLMError` with an actionable message: if disabled → `"LLM is disabled (llm.enabled: false)"`; if file missing → `"LLM model not found: <path>. Run: python scripts/download_models.py --llm"`.
     - Lazy import: `from llama_cpp import Llama` inside a `try` that converts `ImportError` into `LLMError("llama-cpp-python is not installed; run: python -m pip install -r requirements.txt")`.
     - `n_threads = self._config.llm.n_threads or max(1, (os.cpu_count() or 4) // 2)`.
     - Construct `Llama(model_path=str(path), n_ctx=cfg.n_ctx, n_threads=n_threads, n_gpu_layers=cfg.n_gpu_layers, verbose=False)`.
     - If construction raises and `cfg.n_gpu_layers != 0`, log a warning and retry once with `n_gpu_layers=0` (CPU fallback). If that also fails, wrap in `LLMError(f"Failed to load LLM model: {e}")`.
     - Wrap only the known exception types (`OSError`, `ValueError`, `RuntimeError`, plus the import error path) — no bare `except:`.
   - `generate(self, prompt: str) -> str`:
     - Call `self._load()`.
     - `out = self._model(prompt, max_tokens=cfg.max_tokens, temperature=cfg.temperature, stop=["\n", "User:", "Hideko:"])`.
     - `text = out["choices"][0]["text"]` (use `.get` defensively), `strip()`.
     - If empty, raise `LLMError("LLM produced an empty reply")`.
     - On `OSError`/`RuntimeError`/`ValueError` from the call, wrap in `LLMError`.
     - Return the text. No printing.

5. `LLMFallback`:
   - `__init__(config, memory=None, backend=None)`: store `self._config`, `self._memory`, and `self._backend = backend if backend is not None else (LlamaCppBackend(config) if config.llm.enabled else NullBackend())`.
   - `available() -> bool` delegates to `self._backend.available()`.
   - `_build_prompt(text: str) -> str`:
     ```
     <system_prompt>

     Known facts about the user:
     - name: Ada
     - likes: cats

     User: <text>
     Hideko:
     ```
     Omit the "Known facts" block entirely when `self._memory is None` or `all()` is empty. Build from `self._config.llm.system_prompt`. Cap the text passed in at 500 characters.
   - `respond(text: str) -> LLMReply`:
     - If not `self.available()`, raise `LLMError("LLM is not available")`.
     - Build the prompt, record `t0 = time.perf_counter()`.
     - Run generation with a soft timeout using a **non-context-managed** pool so the method can return on timeout:
       ```python
           pool = ThreadPoolExecutor(max_workers=1)
           future = pool.submit(self._backend.generate, prompt)
           try:
               reply = future.result(timeout=self._config.llm.timeout_s)
           except FuturesTimeout as exc:
               pool.shutdown(wait=False, cancel_futures=True)
               raise LLMError(
                   f"LLM generation exceeded {self._config.llm.timeout_s:.0f}s"
               ) from exc
           finally:
               # ensure the pool object is released on the success path too
               pass
           pool.shutdown(wait=False)
       ```
       Simplify as needed but keep `wait=False` on the timeout path.
     - `reply = reply.strip()`; if empty raise `LLMError("LLM produced an empty reply")`.
     - Return `LLMReply(text=reply, latency_s=time.perf_counter() - t0)`.
     - Log at DEBUG: `logger.debug("llm: %.2fs -> %s", latency, reply if config.runtime.log_transcripts else "***REDACTED***")`.
     - **Document in the module docstring** that a timed-out in-process inference thread cannot be killed and may still occupy a core until it finishes; this is why `max_tokens` is small.

6. `if __name__ == "__main__":` CLI: `--text TEXT` (required) and optional `--config PATH`. Construct config, `LLMFallback`, call `respond`, print the reply text and `latency`. On `LLMError`, print `LLM error: ...` to stderr and exit 6.

### `tests/test_llm_fallback.py` — new file

Define a `FakeBackend` with `available` flag, `generate` returning a fixed string (or raising), and a `prompts` list recording what it received. Do **not** import `llama_cpp` in tests.

Cover:
- `disabled_by_default` — with the fixture config (`enabled=False`), `LLMFallback(config).available() is False` and `respond()` raises `LLMError`.
- `fake_backend_reply` — config with `llm.enabled=True` via `dataclasses.replace`; inject `FakeBackend`; assert `respond("hello").text` and that `latency_s >= 0`.
- `prompt_includes_memory` — fake memory object with `all()` returning `{"name": "Ada", "likes": "cats"}`; assert the recorded prompt contains `name: Ada` and `likes: cats` and `User: hello`.
- `prompt_omits_memory_block` — memory with `all() == {}`; assert `"Known facts"` not in prompt.
- `backend_error_raises_llmerror` — fake `generate` raises `RuntimeError`; assert `LLMError` is raised.
- `empty_reply_raises` — fake returns `"   "`; assert `LLMError`.
- `timeout` — fake sleeps longer than `timeout_s` (use a very small timeout like 1.0 and a fake that sleeps 1.5; keep test under 3 s). Assert `LLMError` and that the method returns within ~2 s. If this proves flaky on Windows, replace with a monkeypatched `future.result` that raises `FuturesTimeout` and note it.
- `no_model_import` — assert `"llama_cpp" not in sys.modules` after importing `llm_fallback` and constructing `LLMFallback` with `enabled=False`.

## Verification

```powershell
python -m pytest -q
python -m pytest -q tests/test_llm_fallback.py -v
python -c "import sys, llm_fallback; print('llama_cpp' in sys.modules)"
python llm_fallback.py --text "hello" --config config.yaml
```

Expected:

- `pytest` — all pass.
- `python -c ...` — prints `False`.
- `python llm_fallback.py --text "hello"` — since `llm.enabled` is false in `config.yaml`, prints `LLM error: LLM is not available` to stderr and exits 6. This is the expected disabled-state behaviour.
- If the real GGUF model from task 06 is present, temporarily flip `llm.enabled: true` in a **copy** of the config (`--config` a temp file) and run one real generation; report the text and latency. Do not leave `enabled: true` in the project's `config.yaml`.

## Stop and ask the human if

- `llama_cpp` must be imported at module level for your chosen version to work — that breaks the offline-import guarantee, so stop and ask.
- Real generation takes longer than `timeout_s` even for a short prompt — report the numbers rather than silently raising the timeout.
