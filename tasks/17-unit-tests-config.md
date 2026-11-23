# Task 17 — Unit tests: fixtures + config

**Goal (one sentence).** Create `tests/conftest.py` and `tests/test_config.py` with the shared fixtures and 12 config tests.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `tests/conftest.py` (create), `tests/test_config.py` (create) — nothing else |
| Depends on | task 03 |
| Blocks | tasks 18–20 |
| Time budget | ~45 min |

`tests/__init__.py` already exists from task 01. `pytest` is installed.

**Hard rule:** `python -m pytest -q` must pass with no mic, no speakers, no models, and no network. No test may write outside `tmp_path`.

---

## 1. `tests/conftest.py` — copy this, then add the fixtures below

```python
import numpy as np
import pytest
import yaml

from config import load_config


@pytest.fixture
def config(tmp_path):
    """A complete, valid AppConfig rooted in tmp_path."""
    data = {
        "audio": {
            "input_device": None, "output_device": None,
            "sample_rate": 16000, "channels": 1, "block_ms": 32,
            "playback_volume": 1.0,
        },
        "vad": {
            "energy_threshold_db": -40.0, "calibrate": False,
            "calibration_ms": 1000, "silence_ms": 700, "min_speech_ms": 250,
            "max_utterance_s": 15, "pre_roll_ms": 300,
            "post_playback_flush_ms": 300,
        },
        "stt": {
            "model_size": "tiny.en", "device": "cpu", "compute_type": "int8",
            "language": "en", "beam_size": 1, "download_root": "models/whisper",
            "min_avg_logprob": -1.0, "max_audio_s": 30,
        },
        "tts": {
            "backend": "exe", "piper_exe": "models/piper/piper/piper.exe",
            "voice_model": "models/piper/en_US-amy-medium.onnx",
            "length_scale": 1.0, "max_chars": 300, "timeout_s": 30,
        },
        "responses": {
            "triggers_file": "responses/triggers.yaml",
            "fallbacks_file": "responses/fallbacks.yaml",
        },
        "runtime": {
            "half_duplex": True, "max_turns": 0, "log_transcripts": True,
            "greet_on_start": True, "echo_mode": False,
        },
        "logging": {
            "level": "INFO", "file": "logs/hideko.log",
            "max_bytes": 1048576, "backup_count": 3,
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    (tmp_path / "responses").mkdir(exist_ok=True)
    return load_config(p)


@pytest.fixture
def silent_block():
    return lambda n=512: np.zeros(n, dtype=np.float32)


@pytest.fixture
def speech_block():
    rng = np.random.default_rng(0)
    return lambda n=512: (0.2 * rng.standard_normal(n)).astype(np.float32)


@pytest.fixture
def fake_devices(monkeypatch):
    devices = [
        {"name": "Speakers (Realtek)", "max_input_channels": 0,
         "max_output_channels": 2, "default_samplerate": 48000.0},
        {"name": "Microphone (USB)", "max_input_channels": 2,
         "max_output_channels": 0, "default_samplerate": 44100.0},
        {"name": "Headset Mic", "max_input_channels": 1,
         "max_output_channels": 1, "default_samplerate": 16000.0},
    ]
    import sounddevice as sd
    monkeypatch.setattr(sd, "query_devices", lambda *a, **k: devices)
    monkeypatch.setattr(sd, "default", type("D", (), {"device": (1, 0)})(), raising=False)
    return devices
```

Notes:
- The `config` fixture must include **every** section, or `load_config` fills defaults and your paths silently point at the real project folder.
- Never use the real `config.yaml` in tests — a user's `input_device: "Yeti"` would leak into assertions.
- If `sd.default` is a module-level object that cannot be replaced, use `monkeypatch.setattr(sd.default, "device", (1, 0))` instead.

## 2. `tests/test_config.py` — 12 cases

Write a helper `write(tmp_path, data)` that writes YAML to `tmp_path/"config.yaml"` and returns `load_config(path)`, plus a helper for raw text. Import `ConfigError` from `config`, `pytest`, `yaml`, `logging` as needed.

1. Valid file → `AppConfig` with `sample_rate == 16000`.
2. All path fields (`stt.download_root`, `tts.piper_exe`, `tts.voice_model`, `responses.*`, `logging.file`) are absolute and start with `str(tmp_path)`.
3. `audio.blocksize == 512` for `sample_rate=16000, block_ms=32`.
4. Missing file → `ConfigError` mentioning the path.
5. Empty file → `ConfigError` whose message contains "empty".
6. YAML syntax error (e.g. `"audio: [\n  bad: : :"`) → `ConfigError` including a line number.
7. Top-level list (`- a\n- b`) → `ConfigError`.
8. `audio.sample_rate: 44100` → `ConfigError` mentioning 16000.
9. `audio.block_ms: 5` and `audio.block_ms: 500` → `ConfigError` (parametrize).
10. `tts.backend: "gtts"` → `ConfigError`.
11. Unknown key `audio.volume_levle` → `caplog` contains a warning naming the key AND load succeeds.
12. `input_device: "null"` → `None`; `log_transcripts: "true"` (string) → `ConfigError` (parametrize or two asserts).

## 3. Rules checklist

- [ ] 12 tests in `test_config.py` (parametrize counts as multiple)
- [ ] `config` fixture contains every config section
- [ ] All fixtures use only `tmp_path`; no real project paths, no hardware, no network
- [ ] No `time.sleep()`, no model loading, no `pytest-mock`
- [ ] Type hints on helper functions; docstrings on fixtures

## 4. Do NOT

- Do not modify `config.py` or any application module. If a test cannot pass, the module has a bug — report it, do not hide it.
- Do not add `pytest-mock`, `pytest-cov`, `hypothesis`, or `freezegun`.
- Do not use `xfail` or `skip` to get green.
- Do not write WAV fixtures — generate arrays in memory.

## 5. Verify — run and paste output

```powershell
python -m pytest tests/test_config.py -q
```
Expected: 12 passed (or more with parametrization), under 1 second.

```powershell
python -m pytest -q
```
Expected: all tests pass (future modules add more in tasks 18–20).

## 6. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 18.
