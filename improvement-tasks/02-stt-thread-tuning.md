# Task 02 — STT CPU-thread tuning

**Phase A (latency). Depends on task 01. Touch at most 6 files.**

## Goal

Make the number of CTranslate2 CPU threads configurable so it can be tuned without editing source. Default behaviour stays **exactly** the same (`null` ⇒ half the logical cores). Do not change the model, `beam_size`, `compute_type`, or any other decode parameter.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- `beam_size: 1` is already the fastest setting — do not change it. `condition_on_previous_text=False`, `vad_filter=False`, and `temperature=0.0` are already set in `stt_engine.py` — do not change them.
- No latency pass/fail number. Record observed timings only.
- Tests must pass offline with no mic: `python -m pytest -q`.
- When adding the config key, update **all four** places: `config.yaml`, `_DEFAULTS`, both known-key sets in `config.py`, and `tests/conftest.py`.

## Current state (exact)

`stt_engine.py::_ensure_model` lines 56–72:
```python
    def _ensure_model(self) -> None:
        """Load the Whisper model if not already loaded."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._config.stt.model_size,
                    device=self._config.stt.device,
                    compute_type=self._config.stt.compute_type,
                    download_root=str(self._config.stt.download_root),
                    cpu_threads=max(1, (os.cpu_count() or 4) // 2),
                )
            except (OSError, ValueError, RuntimeError) as e:
                raise STTError(
                    f"Failed to load STT model: {e}. Run `python scripts/download_models.py --stt`."
                ) from e
```

`config.py` relevant pieces:
```python
@dataclass(frozen=True)
class STTConfig:
    model_size: str
    device: str
    compute_type: str
    language: str | None
    beam_size: int
    download_root: Path
    min_avg_logprob: float
    max_audio_s: float
```
```python
    "stt": {
        "model_size": "tiny.en",
        "device": "cpu",
        "compute_type": "int8",
        "language": "en",
        "beam_size": 1,
        "download_root": "models/whisper",
        "min_avg_logprob": -1.0,
        "max_audio_s": 30.0,
    },
```
The key lists appear twice: `_get_known_keys()` (~line 186) and `_check_unknown_keys()` (~line 218). `_validate_stt()` (~line 301) validates `model_size` and `compute_type`. `build_stt()` (~line 428) constructs `STTConfig(...)`.

`config.yaml` `stt:` block lines 23–31; `tests/conftest.py` `stt` fixture lines 24–28.

## Steps

1. **`config.py`** — add `cpu_threads: int | None` to `STTConfig`, placed right after `beam_size: int`.

2. **`config.py`** — add `"cpu_threads": None,` to `_DEFAULTS["stt"]` after `"beam_size": 1,`.

3. **`config.py`** — add `"cpu_threads"` to the `stt` key set in **both** `_get_known_keys()` and `_check_unknown_keys()`. Missing either one causes an "Unknown key: stt.cpu_threads" warning.

4. **`config.py::_validate_stt`** — append:
   ```python
       cpu_threads = config.get("cpu_threads", _DEFAULTS["stt"]["cpu_threads"])
       if cpu_threads is not None and (
           not isinstance(cpu_threads, int) or not (1 <= cpu_threads <= 64)
       ):
           raise ConfigError(
               f"{path}.cpu_threads must be null or an int between 1 and 64, got {cpu_threads}"
           )
   ```
   Note: `bool` is a subclass of `int` in Python. Explicitly reject `True`/`False` with `isinstance(cpu_threads, bool)` if you want strictness; add a test for it either way.

5. **`config.py::build_stt`** — add to the `STTConfig(...)` constructor:
   ```python
           cpu_threads=get_value(stt_section, "cpu_threads", _DEFAULTS["stt"]["cpu_threads"]),
   ```

6. **`config.yaml`** — in the `stt:` block, after `beam_size`, add:
   ```yaml
   cpu_threads: null          # null = half of logical cores (old behaviour); 1-64 to override
   ```

7. **`stt_engine.py::_ensure_model`** — replace the `cpu_threads=...` argument with:
   ```python
                   cpu_threads=(
                       self._config.stt.cpu_threads
                       if self._config.stt.cpu_threads is not None
                       else max(1, (os.cpu_count() or 4) // 2)
                   ),
   ```
   Keep `import os` at the top. Do not touch anything else in this method.

8. **`tests/conftest.py`** — add `cpu_threads: None,` to the `stt` part of the `config` fixture.

9. **`tests/test_config.py`** — add:
   - `test_stt_cpu_threads_defaults_to_null` — `load_config().stt.cpu_threads is None`.
   - `test_stt_cpu_threads_validation` — values `-1`, `0`, `65`, `2.5`, `"4"` each raise `ConfigError`; `1`, `8`, `64`, `None` are accepted.
   - `test_stt_cpu_threads_loads_from_yaml` — a temp config with `cpu_threads: 8` loads as `8`.

10. **`tests/test_stt_engine.py`** — add one mocked test: monkeypatch `faster_whisper.WhisperModel` with a fake that records kwargs, build a config with `cpu_threads = 8` (use `dataclasses.replace` on the fixture), call `engine._ensure_model()`, and assert the fake received `cpu_threads == 8`. Add a second assertion that with `cpu_threads = None` the fake receives `max(1, (os.cpu_count() or 4) // 2)`. Do not load a real model.

## Verification

```powershell
python -m pytest -q
python config.py --check
python stt_engine.py --warmup
python main.py --turns 3 --no-greet --no-tts
```

Expected:

- `pytest` — all pass.
- `python config.py --check` — JSON contains `"cpu_threads": null`.
- `python stt_engine.py --warmup` — exits 0, prints `model loaded in ~X.Xs; warm transcription ready`.
- `python main.py --turns 3 --no-greet --no-tts` — normal startup, timing lines printed, exit 0.

Record the `stt` timings you observe. **No threshold.** Optionally try one manual run with `cpu_threads: 8` in a temporary config and note what you saw, then restore `null`.

## Stop and ask the human if

- `WhisperModel` fails to construct with the new argument on the installed `faster-whisper==1.0.3`, or
- Any existing STT test fails after the change.
