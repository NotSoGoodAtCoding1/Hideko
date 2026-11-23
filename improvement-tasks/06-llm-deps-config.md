# Task 06 — LLM dependency, config & model acquisition

**Phase C (LLM). Depends on task 05. Touch at most 8 files.**

## Goal

Add the `llama-cpp-python` dependency, an `llm:` config section, an `LLMError`, and a downloader entry for one small GGUF model. **No LLM inference code in this task** — that is task 07. The LLM must stay **disabled by default**.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Runtime must stay offline. Network use only in `scripts/download_models.py`.
- Heavy dependencies and GPU are now allowed (this relaxes the MVP's CPU-only rule). Python **3.11 is still preferred**.
- Pin the exact `llama-cpp-python` version you install in `requirements.txt`.
- No `print()` in library code. Tests offline: `python -m pytest -q`.
- When adding a config section, update all four places (`config.yaml`, `_DEFAULTS`, both known-key listings, `tests/conftest.py`).

## Current state (exact)

`requirements.txt`:
```
numpy==1.26.4
sounddevice==0.4.6
soundfile==0.12.1
faster-whisper==1.0.3
PyYAML==6.0.1
pytest==8.2.0
```

`errors.py` ends with `MemoryError` (exit code 5) from task 04.

`config.py` now has `MemoryConfig` and `AppConfig.memory` (task 04). Follow the same pattern for `LLMConfig`.

`config.yaml` now ends with a `memory:` section followed by `logging:`. Put the new `llm:` section before `logging:`.

`scripts/download_models.py` already downloads Piper and Whisper; read it first and follow its existing style (argparse flags, `--all`, size checks, `--force`). Do not rewrite the whole script.

`scripts/check_env.py` prints a table of checks with `OK` / `FAILED` rows; read it and add one row in the same style.

## Steps

### 1. Choose and pin the dependency

Run:
```powershell
python -m pip index versions llama-cpp-python
```
Pick the newest version that offers a Windows CPython 3.11 wheel. Install it:
```powershell
python -m pip install "llama-cpp-python==<VERSION>"
```
Verify:
```powershell
python -c "import llama_cpp; print(llama_cpp.__version__)"
```
Add the exact pinned line to `requirements.txt`, e.g. `llama-cpp-python==0.3.x`. Add a short comment line above it explaining that a CUDA build can be substituted for GPU offload.

**Python-version gate (only if the 3.11 install fails):**
1. Do **not** bump Python yet. First record the exact pip error.
2. If and only if the error is "no matching distribution" for cp311, consider 3.12 in a **separate** venv and verify all of:
   ```powershell
   py -3.12 -m venv .venv312
   .\.venv312\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python -c "import ctranslate2, faster_whisper; print('ok')"
   python -m pytest -q
   ```
3. If **any** of those fail, revert to the 3.11 venv and **stop — ask the human**. Do not change the Python pin on your own.
4. If all pass, note the required version change in your final report for task 09 to document. Do not edit README here.

### 2. `config.py` — add `LLMConfig`

```python
@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    model_path: Path
    n_ctx: int
    n_threads: int
    n_gpu_layers: int
    max_tokens: int
    temperature: float
    timeout_s: float
    system_prompt: str
```

Add `llm: LLMConfig` to `AppConfig` before `memory` (or after `memory` — keep `source` last).

`_DEFAULTS["llm"]`:
```python
    "llm": {
        "enabled": False,
        "model_path": "models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "n_ctx": 1024,
        "n_threads": 0,
        "n_gpu_layers": -1,
        "max_tokens": 80,
        "temperature": 0.2,
        "timeout_s": 15.0,
        "system_prompt": (
            "You are Hideko, a brief friendly voice assistant. "
            "Answer in one or two short sentences. "
            "Never claim to have internet access."
        ),
    },
```

Add `"llm"` to `known_sections` and add its key set to both `_get_known_keys()` and `_check_unknown_keys()`:
```python
        "llm": {"enabled", "model_path", "n_ctx", "n_threads", "n_gpu_layers",
                "max_tokens", "temperature", "timeout_s", "system_prompt"},
```

Validation `_validate_llm`:
```python
def _validate_llm(config: dict[str, Any], path: str = "llm") -> None:
    """Validate the llm section."""
    n_ctx = config.get("n_ctx", _DEFAULTS["llm"]["n_ctx"])
    if not isinstance(n_ctx, int) or isinstance(n_ctx, bool) or not (128 <= n_ctx <= 8192):
        raise ConfigError(f"{path}.n_ctx must be an int between 128 and 8192, got {n_ctx}")
    n_threads = config.get("n_threads", _DEFAULTS["llm"]["n_threads"])
    if not isinstance(n_threads, int) or isinstance(n_threads, bool) or not (0 <= n_threads <= 64):
        raise ConfigError(f"{path}.n_threads must be an int between 0 and 64, got {n_threads}")
    n_gpu_layers = config.get("n_gpu_layers", _DEFAULTS["llm"]["n_gpu_layers"])
    if not isinstance(n_gpu_layers, int) or isinstance(n_gpu_layers, bool) or not (-1 <= n_gpu_layers <= 100):
        raise ConfigError(f"{path}.n_gpu_layers must be -1 or an int between 0 and 100, got {n_gpu_layers}")
    max_tokens = config.get("max_tokens", _DEFAULTS["llm"]["max_tokens"])
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not (8 <= max_tokens <= 256):
        raise ConfigError(f"{path}.max_tokens must be an int between 8 and 256, got {max_tokens}")
    temperature = config.get("temperature", _DEFAULTS["llm"]["temperature"])
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not (0.0 <= temperature <= 1.5):
        raise ConfigError(f"{path}.temperature must be between 0.0 and 1.5, got {temperature}")
    timeout_s = config.get("timeout_s", _DEFAULTS["llm"]["timeout_s"])
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not (1.0 <= timeout_s <= 120.0):
        raise ConfigError(f"{path}.timeout_s must be between 1 and 120 seconds, got {timeout_s}")
    system_prompt = config.get("system_prompt", _DEFAULTS["llm"]["system_prompt"])
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ConfigError(f"{path}.system_prompt must be a non-empty string")
```

`build_llm()` — resolve `model_path` against `config_path.parent` exactly like `build_tts()` does, and use `_validate_bool` for `enabled`. Do **not** require the model file to exist at config load time (so `--text` and tests work with `enabled: false`).

```python
    def build_llm() -> LLMConfig:
        llm_section = get_value(raw_config, "llm", {})
        if not isinstance(llm_section, dict):
            raise ConfigError(f"llm must be a mapping (dict), got {type(llm_section).__name__}")
        _validate_llm(llm_section)
        model_path = Path(get_value(llm_section, "model_path", _DEFAULTS["llm"]["model_path"]))
        if not model_path.is_absolute():
            model_path = config_path.parent / model_path
        return LLMConfig(
            enabled=_validate_bool(get_value(llm_section, "enabled", _DEFAULTS["llm"]["enabled"]), "enabled", "llm"),
            model_path=model_path,
            n_ctx=get_value(llm_section, "n_ctx", _DEFAULTS["llm"]["n_ctx"]),
            n_threads=get_value(llm_section, "n_threads", _DEFAULTS["llm"]["n_threads"]),
            n_gpu_layers=get_value(llm_section, "n_gpu_layers", _DEFAULTS["llm"]["n_gpu_layers"]),
            max_tokens=get_value(llm_section, "max_tokens", _DEFAULTS["llm"]["max_tokens"]),
            temperature=get_value(llm_section, "temperature", _DEFAULTS["llm"]["temperature"]),
            timeout_s=get_value(llm_section, "timeout_s", _DEFAULTS["llm"]["timeout_s"]),
            system_prompt=get_value(llm_section, "system_prompt", _DEFAULTS["llm"]["system_prompt"]),
        )
```
Call it and pass `llm=llm` to `AppConfig(...)`.

### 3. `config.yaml`

```yaml
llm:
  enabled: false             # opt-in; only used when no YAML trigger matches
  model_path: models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf
  n_ctx: 1024
  n_threads: 0               # 0 = use half the logical cores
  n_gpu_layers: -1           # -1 = offload all layers if a CUDA build is available
  max_tokens: 80             # short replies keep latency bounded
  temperature: 0.2
  timeout_s: 15
  system_prompt: "You are Hideko, a brief friendly voice assistant. Answer in one or two short sentences. Never claim to have internet access."
```

### 4. `errors.py`

```python
class LLMError(HidekoError):
    """LLM disabled, model missing, or generation failed."""
    exit_code = 6
```

### 5. `tests/conftest.py`

Add the `llm` section to the `config` fixture mirroring the YAML above (with `enabled: False` and `model_path: models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf`).

Add tests to `tests/test_config.py`:
- `test_llm_defaults` — `load_config().llm.enabled is False`, `n_gpu_layers == -1`, `max_tokens == 80`.
- `test_llm_validation` — invalid `n_ctx`, `n_threads`, `n_gpu_layers`, `max_tokens`, `temperature`, `timeout_s`, `system_prompt` each raise `ConfigError`.
- `test_llm_model_path_resolved` — `config.llm.model_path` is absolute and ends with the GGUF filename.

### 6. `scripts/download_models.py`

Read the file, then add an LLM downloader following its existing pattern:

- URL: `https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf`
- Destination: `models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf` (create the directory)
- Add flag `--llm` and include it in `--all`.
- After download, check file size `> 300 * 1024 * 1024`; fail with an actionable message if smaller.
- Print the licence note from the model card in your final report; do not guess it. Task 09 records it in README.
- Do not hard-code a checksum unless the model card provides one; if it does, verify it.

Run:
```powershell
python scripts/download_models.py --llm
```
If the network is unavailable, report that and continue with config/tests; task 07 tests use a mocked backend and do not need the real model.

### 7. `scripts/check_env.py`

Read the file and add one row in the same style:
- When `config.llm.enabled` is False: `LLM (disabled)` with status `-` and detail `skipped`.
- When enabled: `OK` if `config.llm.model_path.is_file()` and size `> 300 MB`, otherwise `FAILED` with detail pointing to `python scripts/download_models.py --llm`.
Do not make the disabled row fail the overall check.

## Verification

```powershell
python -m pytest -q
python config.py --check
python -c "import llama_cpp; print(llama_cpp.__version__)"
python scripts/check_env.py
```

Expected:

- `pytest` — all pass.
- `python config.py --check` — JSON contains an `"llm"` object with `"enabled": false` and an absolute `"model_path"`.
- `python -c "import llama_cpp; ..."` — prints a version string, no import error.
- `python scripts/check_env.py` — shows `LLM (disabled)` as skipped and still ends with all required checks passing.

## Stop and ask the human if

- No `llama-cpp-python` wheel works on Python 3.11 **and** Python 3.12 breaks `ctranslate2`/`faster-whisper` — stop before changing any version pin.
- The model download fails or the licence cannot be determined — report it; task 09 must not invent a licence.
