# Task 02 — HTTP backend + config

**Depends on task 01. Touch at most 8 files.** Do not modify `response_handler.py` or `responses/*.yaml`.

## Goal

Replace the in-process `llama-cpp-python` backend with a small loopback HTTP client that talks to KoboldCpp. Remove the dead dependency and make `check_env.py` verify the server instead of a local wheel. All tests must still pass **without** a running server.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No new third-party dependency — use `urllib.request` from the standard library.
- `llm.enabled` stays `false` by default; tests use a fake backend, never real HTTP.
- No `print()` in library code outside `__main__`; log with `logging.getLogger(__name__)`.
- Type hints + docstrings on all public classes/functions. No bare `except:`.
- Config keys must be updated in **all four** places: `config.yaml`, `_DEFAULTS`, both known-key sets in `config.py`, and `tests/conftest.py`.

## Current state you will replace

`llm_fallback.py` currently contains `_prepare_native_library_dirs`, `LlamaCppBackend`, `NullBackend`, and `LLMFallback`. `_prepare_native_library_dirs`, the `llama_cpp` import, and all DLL/PATH handling must be **deleted**. `LLMBackend.generate` currently takes `prompt: str`.

`config.py` currently has:
```python
@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    model_path: Path
    temperature: float
    max_tokens: int
    context_window: int
    n_threads: int | None
    n_gpu_layers: int
    timeout_s: float
    system_prompt: str
```
and `_DEFAULTS["llm"]` with `model_path`, `n_threads`, `n_gpu_layers`, `context_window`, etc. Two known-key sets list `{"enabled", "model_path", "temperature", "max_tokens", "context_window", "n_threads", "n_gpu_layers", "timeout_s", "system_prompt"}`.

`requirements.txt` currently ends with `llama-cpp-python==0.3.36`.

`scripts/check_env.py` has `check_llm_model()` (checks a local GGUF file) and `check_llama_import()` (checks `llama_cpp` import). Both must be replaced by a single server check.

## Steps

### 1. `config.py` — new `LLMConfig`

Replace the dataclass with:
```python
@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    base_url: str
    endpoint: str
    model: str
    temperature: float
    max_tokens: int
    timeout_s: float
    system_prompt: str
    persona_file: Path
```

Replace `_DEFAULTS["llm"]` with:
```python
    "llm": {
        "enabled": False,
        "base_url": "http://127.0.0.1:5001",
        "endpoint": "/v1/chat/completions",
        "model": "local",
        "temperature": 0.7,
        "max_tokens": 80,
        "timeout_s": 15.0,
        "system_prompt": (
            "You are Hideko, a brief friendly voice assistant. "
            "Answer in one or two short sentences. "
            "Never claim to have internet access."
        ),
        "persona_file": "persona/hideko.yaml",
    },
```

Replace the `llm` key set in **both** `_get_known_keys()` and `_check_unknown_keys()`:
```python
        "llm": {
            "enabled", "base_url", "endpoint", "model", "temperature",
            "max_tokens", "timeout_s", "system_prompt", "persona_file",
        },
```

Replace `_validate_llm()` with:
```python
def _validate_llm(config: dict[str, Any], path: str = "llm") -> None:
    """Validate the llm section."""
    base_url = config.get("base_url", _DEFAULTS["llm"]["base_url"])
    if not isinstance(base_url, str) or not base_url.startswith(("http://127.0.0.1", "http://localhost")):
        raise ConfigError(f"{path}.base_url must be a loopback http URL, got {base_url!r}")
    endpoint = config.get("endpoint", _DEFAULTS["llm"]["endpoint"])
    if not isinstance(endpoint, str) or not endpoint.startswith("/"):
        raise ConfigError(f"{path}.endpoint must start with '/', got {endpoint!r}")
    model = config.get("model", _DEFAULTS["llm"]["model"])
    if not isinstance(model, str) or not model.strip():
        raise ConfigError(f"{path}.model must be a non-empty string")
    temperature = config.get("temperature", _DEFAULTS["llm"]["temperature"])
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not (0.0 <= temperature <= 1.5):
        raise ConfigError(f"{path}.temperature must be between 0.0 and 1.5, got {temperature}")
    max_tokens = config.get("max_tokens", _DEFAULTS["llm"]["max_tokens"])
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not (8 <= max_tokens <= 256):
        raise ConfigError(f"{path}.max_tokens must be an int between 8 and 256, got {max_tokens}")
    timeout_s = config.get("timeout_s", _DEFAULTS["llm"]["timeout_s"])
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not (1.0 <= timeout_s <= 120.0):
        raise ConfigError(f"{path}.timeout_s must be between 1 and 120 seconds, got {timeout_s}")
    system_prompt = config.get("system_prompt", _DEFAULTS["llm"]["system_prompt"])
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ConfigError(f"{path}.system_prompt must be a non-empty string")
```
Resolve `persona_file` against `config_path.parent` in `build_llm()` exactly like `responses` paths, and pass every new field to `LLMConfig(...)`. Remove all references to the deleted fields.

### 2. `config.yaml` — replace the whole `llm:` block

```yaml
llm:
  enabled: false             # opt-in; KoboldCpp must already be running
  base_url: http://127.0.0.1:5001   # loopback only, no cloud
  endpoint: /v1/chat/completions    # KoboldCpp OpenAI-compatible endpoint
  model: local               # ignored by KoboldCpp but required by the API
  temperature: 0.7
  max_tokens: 80             # short replies keep LLM turns bounded
  timeout_s: 15
  system_prompt: "You are Hideko, a brief friendly voice assistant. Answer in one or two short sentences. Never claim to have internet access."
  persona_file: persona/hideko.yaml
```
Delete `model_path`, `context_window`, `n_threads`, `n_gpu_layers`.

### 3. `llm_fallback.py` — rewrite the backend

Delete `_DLL_DIR_HANDLES`, `_prepare_native_library_dirs`, `import os`, `import sysconfig`, `Path`, `re`, and `LlamaCppBackend`. Keep `LLMReply`, `LLMBackend`, `NullBackend`, `LLMFallback`, `LLMError` usage, the ThreadPoolExecutor timeout, and memory injection.

New imports needed: `json`, `urllib.request`, `urllib.error`, `logging`, `time`, `dataclasses`, `argparse`, `sys`, `concurrent.futures`, `pathlib.Path`, `typing.Any`.

Implement:

```python
class LLMBackend:
    """Protocol-like base; generate() receives chat messages."""
    def available(self) -> bool: return False
    def generate(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

class NullBackend(LLMBackend):
    def available(self) -> bool: return False
    def generate(self, messages: list[dict[str, str]]) -> str:
        raise LLMError("LLM backend is disabled")
```

`KoboldHttpBackend(LLMBackend)`:
- `__init__(self, config: AppConfig)` stores config.
- `available(self) -> bool` returns `self._config.llm.enabled` (no model file check).
- `generate(self, messages: list[dict[str, str]]) -> str`:
  - Build URL as `cfg.base_url.rstrip("/") + cfg.endpoint`.
  - Body: `{"model": cfg.model, "messages": messages, "max_tokens": cfg.max_tokens, "temperature": cfg.temperature, "stream": False}`.
  - `req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")`.
  - `with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp: payload = json.loads(resp.read().decode("utf-8"))`.
  - Text: `payload["choices"][0]["message"]["content"]`; if that key is missing, accept `choices[0]["text"]` as a fallback for older Kobold builds. `strip()`.
  - Empty text → `LLMError("LLM produced an empty reply")`.
  - Convert `urllib.error.URLError`, `TimeoutError`, `OSError`, `json.JSONDecodeError`, `KeyError`, `IndexError` into `LLMError` with an actionable message mentioning `base_url` and "Is KoboldCpp running?".
  - **Never** log the full prompt at INFO; use DEBUG and respect `config.runtime.log_transcripts` as before.

`LLMFallback`:
- `__init__(config, memory=None, backend=None)` — backend defaults to `KoboldHttpBackend(config)` if enabled else `NullBackend()`.
- `_build_prompt` becomes `_build_messages(text, intent) -> list[dict[str, str]]`:
  - Read `cfg.persona_file` (resolve relative to `config.source.parent`); if it parses as YAML with a `personality` / `description` field, append those strings to the system content; if missing/invalid, log a warning and use only `cfg.system_prompt`.
  - Append memory facts from `self._memory.all()` as `- key: value` lines under `Known facts about the user:` (omit when empty).
  - Append `f"User intent: {intent}"` when `intent` is not None.
  - Return `[{"role": "system", "content": ...}, {"role": "user", "content": text[:500]}]`.
- `respond(self, text: str, intent: str | None = None) -> LLMReply` — pass intent through; keep the existing timeout pool and non-ASCII stripping.
- CLI `--text` still works; on `LLMError` print to stderr and exit 6.

Module docstring must state: no model is loaded in-process; a KoboldCpp server must be running; offline means loopback only.

### 4. `requirements.txt`

Delete the `llama-cpp-python==0.3.36` line. Leave the other five pins untouched. Do not add `requests` — `urllib` is in the stdlib.

### 5. `scripts/check_env.py`

Delete `check_llm_model()` and `check_llama_import()` and their table rows. Add:

```python
def check_llm_server() -> tuple[str, str]:
    """Verify the optional KoboldCpp loopback server when the LLM is enabled."""
    import json
    import urllib.request

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from config import load_config

        llm = load_config().llm
    except Exception as exc:
        return "FAILED", f"Cannot read llm config: {exc}"
    if not llm.enabled:
        return "-", "disabled (llm.enabled: false)"
    url = llm.base_url.rstrip("/") + llm.endpoint
    try:
        payload = json.dumps({
            "model": llm.model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 4,
            "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            json.loads(resp.read().decode("utf-8"))
        return "OK", url
    except Exception as exc:
        return "FAILED", f"{url} unreachable ({exc}); start KoboldCpp"
```
Add `("KoboldCpp API", check_llm_server)` to `checks`. Remove `MIN_LLM_BYTES` and `LLM_DIR` if now unused.

### 6. Tests

- `tests/conftest.py` — replace the `llm` fixture block with the new keys (`base_url`, `endpoint`, `model`, `temperature`, `max_tokens`, `timeout_s`, `system_prompt`, `persona_file`).
- `tests/test_config.py` — rewrite the LLM tests for the new fields:
  - defaults: `enabled is False`, `base_url == "http://127.0.0.1:5001"`, `endpoint == "/v1/chat/completions"`, `max_tokens == 80`, `persona_file` absolute and ending in `persona/hideko.yaml`.
  - validation: reject non-loopback URLs (`https://...`, `http://example.com`), endpoints not starting with `/`, bad `max_tokens`, bad `temperature`, bad `timeout_s`.
  - remove/replace tests for deleted fields (`model_path`, `n_gpu_layers`, `context_window`).
- `tests/test_llm_fallback.py` — replace `FakeBackend.generate(prompt)` with `generate(messages)`; assert the system message contains persona text when `persona_file` exists and falls back when missing. Add a test that a `urllib.error.URLError` from `urlopen` becomes `LLMError` (monkeypatch `llm_fallback.urllib.request.urlopen`). Keep the existing timeout, empty-reply, non-ASCII stripping, disabled, and "no import at module load" tests; the last one now asserts `llama_cpp` is not imported anywhere.
- Add `tests/test_check_env.py` coverage only if a file already exists for it; do not create a broad new suite. Assert `check_llm_server()` returns `"-"` when disabled and `"FAILED"` with a bogus loopback port when enabled (monkeypatch config load if needed).

## Verification

With **no** KoboldCpp server running:
```powershell
python -m pytest -q
python config.py --check
python scripts\check_env.py
python -m pip show llama-cpp-python
python -c "import llm_fallback; print('import ok')"
```

Expected:
- `pytest` — all pass.
- `config.py --check` — JSON `llm` object has the new keys and no `model_path`/`n_gpu_layers`/`context_window`; `"enabled": false`.
- `check_env.py` — `KoboldCpp API  -   disabled (llm.enabled: false)`, all required checks pass.
- `pip show llama-cpp-python` — not found.
- `python -c "import llm_fallback"` — succeeds without importing `urllib` errors or `llama_cpp`.

Then, **if the user has KoboldCpp running**, do one real check via a temp config with `llm.enabled: true`:
```powershell
python scripts\check_env.py   # KoboldCpp API row should be OK
python llm_fallback.py --text "hello" --config <temp-config>
```
Do not leave a temp config behind; do not change `config.yaml` to `true`.

## Stop and ask the human if

- An existing test asserts a removed config field and you cannot update it without changing unrelated behaviour.
- The character card contains fields you do not recognise — follow the fields in task 01 only.
- `check_env.py` would make a real network request when `llm.enabled: false` — that must never happen.
