# Task 03 — Config loader

**Phase:** 1 · **Depends on:** 01 · **Blocks:** 04, 05, 06, 07, 10 · **Effort:** 45–75 min

## Goal

Create `config.yaml` (the single source of tunables) and `config.py` (a typed, validated loader). Every other module takes an `AppConfig` and reads only from it — no module may hardcode a sample rate, path, or threshold.

The plan deferred config to Week 3. That was a mistake: tasks 04–08 need these values on day one. Config lands now.

## Read first

- [`../plan.md`](../plan.md) — "File Structure (MVP)" and "Phase 3 → basic configuration file".
- [`README.md`](README.md) — the frozen `load_config` signature.

## Files you will create

```
config.yaml
config.py
```

## Step 1 — Create `config.yaml` with exactly this content

```yaml
# Hideko MVP configuration.
# Paths are relative to the project root (the folder containing this file),
# never to the current working directory.

audio:
  input_device: null          # null = system default; or device name substring, or integer index
  output_device: null         # null = system default; or device name substring, or integer index
  sample_rate: 16000          # capture rate. MUST stay 16000 for Whisper. Do not change.
  channels: 1                 # capture is mono. Stereo input is downmixed automatically.
  block_ms: 32                # 512 frames @ 16 kHz. Must be 10-100.
  playback_volume: 1.0        # 0.0 - 1.5. Values > 1.0 may clip.

vad:
  energy_threshold_db: -40.0  # dBFS. Ignored when calibrate: true.
  calibrate: true             # measure ambient noise for calibration_ms at startup
  calibration_ms: 1000
  silence_ms: 700             # trailing silence that ends an utterance
  min_speech_ms: 250          # speech needed before an utterance is considered started
  max_utterance_s: 15         # hard cap; longer speech is truncated and processed
  pre_roll_ms: 300            # audio kept from before speech onset (avoids clipped first syllable)
  post_playback_flush_ms: 300 # audio discarded after playback to avoid transcribing our own voice

stt:
  model_size: tiny.en         # tiny.en (~75 MB) or base.en (~145 MB, more accurate, ~2x slower)
  device: cpu
  compute_type: int8
  language: en
  beam_size: 1                # 1 = greedy, fastest. 5 = slightly better, ~2x slower.
  download_root: models/whisper
  min_avg_logprob: -1.0       # segments below this are treated as noise
  max_audio_s: 30             # refuse longer input instead of silently truncating

tts:
  backend: exe                # "exe" = piper.exe subprocess (default), "python" = piper-tts package
  piper_exe: models/piper/piper/piper.exe
  voice_model: models/piper/en_US-amy-medium.onnx
  length_scale: 1.0           # >1.0 = slower speech, <1.0 = faster
  max_chars: 300              # longer text is truncated before synthesis
  timeout_s: 30

responses:
  triggers_file: responses/triggers.yaml
  fallbacks_file: responses/fallbacks.yaml

runtime:
  half_duplex: true           # discard mic input while speaking (prevents feedback loops)
  max_turns: 0                # 0 = unlimited
  log_transcripts: true       # false = never write recognized text to the log file
  greet_on_start: true
  echo_mode: false            # true = skip response matching, echo the transcript (phase 1 behaviour)

logging:
  level: INFO                 # DEBUG, INFO, WARNING, ERROR
  file: logs/hideko.log
  max_bytes: 1048576          # 1 MB per file
  backup_count: 3
```

## Step 2 — Create `config.py`

### Required public API

```python
class ConfigError(Exception):
    """Raised when config.yaml is missing, malformed, or has an invalid value."""

@dataclass(frozen=True)
class AudioConfig:
    input_device: int | str | None
    output_device: int | str | None
    sample_rate: int
    channels: int
    block_ms: int
    playback_volume: float

    @property
    def blocksize(self) -> int: ...   # sample_rate * block_ms // 1000

@dataclass(frozen=True)
class VADConfig:
    energy_threshold_db: float
    calibrate: bool
    calibration_ms: int
    silence_ms: int
    min_speech_ms: int
    max_utterance_s: float
    pre_roll_ms: int
    post_playback_flush_ms: int

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

@dataclass(frozen=True)
class TTSConfig:
    backend: str
    piper_exe: Path
    voice_model: Path
    length_scale: float
    max_chars: int
    timeout_s: float

@dataclass(frozen=True)
class ResponsesConfig:
    triggers_file: Path
    fallbacks_file: Path

@dataclass(frozen=True)
class RuntimeConfig:
    half_duplex: bool
    max_turns: int
    log_transcripts: bool
    greet_on_start: bool
    echo_mode: bool

@dataclass(frozen=True)
class LoggingConfig:
    level: str
    file: Path
    max_bytes: int
    backup_count: int

@dataclass(frozen=True)
class AppConfig:
    root: Path
    audio: AudioConfig
    vad: VADConfig
    stt: STTConfig
    tts: TTSConfig
    responses: ResponsesConfig
    runtime: RuntimeConfig
    logging: LoggingConfig
    source: Path            # the config.yaml that produced this object

def load_config(path: str | Path = "config.yaml") -> AppConfig: ...
```

### Behaviour rules

1. **Root discovery.** `PROJECT_ROOT = Path(__file__).resolve().parent`. A relative `path` argument is resolved against `PROJECT_ROOT`, not `os.getcwd()`.
2. **Path resolution.** Every path-valued field (`download_root`, `piper_exe`, `voice_model`, `triggers_file`, `fallbacks_file`, `logging.file`) is resolved against `config_path.parent` and stored as an absolute `Path`.
3. **Defaults.** Missing sections/keys fall back to the values in `config.yaml` above (declare them as dataclass defaults; do not duplicate the YAML as a second literal if you can avoid it — a small `_DEFAULTS` dict is acceptable).
4. **Unknown keys** produce a `logging.warning` naming the key path (e.g. `audio.volume_levle`). Unknown keys are not fatal — this keeps old config files working.
5. **Validation** raises `ConfigError` with an actionable message for:
   - file missing / unreadable / empty
   - YAML syntax error (include line and column from `yaml.YAMLError`)
   - top-level value not a mapping
   - `audio.sample_rate != 16000` → error (Whisper requires 16 kHz; say so)
   - `audio.block_ms` outside `[10, 100]`
   - `audio.channels != 1`
   - `playback_volume` outside `[0.0, 1.5]`
   - `vad.silence_ms < 100` or `vad.min_speech_ms < 50`
   - `vad.max_utterance_s` outside `[1, 60]`
   - `vad.pre_roll_ms < vad.min_speech_ms` → error (the utterance onset would be clipped; pre-roll must cover the speech-detection window)
   - `stt.model_size` not in `{tiny, tiny.en, base, base.en, small, small.en}`
   - `stt.compute_type` not in `{int8, int8_float32, float32}`
   - `tts.backend` not in `{exe, python}`
   - `tts.length_scale` outside `[0.5, 2.0]`
   - `logging.level` not a valid level name
   - a bool field receiving a non-bool (YAML `yes`/`no` is fine; the string `"true"` is not)
6. **`tts.backend == "exe"` does not check that the exe exists.** Existence is task 07's job, so config loading works before models are downloaded.
7. `__main__` block: `python config.py --check` prints the resolved config as JSON (convert `Path` → `str`) and exits 0, or prints `CONFIG ERROR: <message>` to stderr and exits 1. `python config.py --check --path other.yaml` uses another file.

### Reference skeleton

```python
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent


class ConfigError(Exception):
    ...


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping, got {type(value).__name__}")
    return value
```

Use a small `_get(section: dict, key: str, default, where: str)` helper so the error messages always include the full key path (`stt.model_size`), never just `model_size`.

## Verification

```powershell
python config.py --check
```

Expected: a JSON dump containing `"sample_rate": 16000`, absolute paths for `piper_exe` and `voice_model`, and exit code 0.

Now prove validation works. Create a deliberately broken copy and confirm a clean error (no traceback):

```powershell
@"
audio:
  sample_rate: 44100
"@ | Set-Content -Encoding utf8 bad.yaml
python config.py --check --path bad.yaml
echo $LASTEXITCODE
Remove-Item bad.yaml
```

Expected: `CONFIG ERROR: audio.sample_rate must be 16000 ...` and exit code `1`.

```powershell
python -m pytest -q
```

Expected: still `6 passed` (no tests added in this task).

## Done criteria

- [ ] `config.yaml` matches the content above byte-for-byte in keys and values.
- [ ] `load_config()` returns `AppConfig` with every path absolute.
- [ ] `python config.py --check` exits 0 and prints JSON.
- [ ] A broken config produces one clear line on stderr, not a traceback, and exit code 1.
- [ ] Running `python config.py --check` from a different directory (e.g. `cd C:\`) still finds `config.yaml` in the project root.
- [ ] `python -m pytest -q` still passes.

## Common pitfalls

- **`Path("models/whisper")` stays relative.** It will break the moment `main.py` is launched from another folder. Resolve against `config_path.parent`.
- **`dataclass(frozen=True)` with a mutable default** (`field(default_factory=...)`) — use `default_factory` for anything non-scalar.
- **YAML `null` vs the string `"null"`.** `input_device: null` becomes `None`; `input_device: "null"` becomes the string `"null"`. Accept only `None`, `int`, or `str`, and treat the literal string `"null"` as `None` for convenience.
- **`yaml.safe_load` returns `None` for an empty file** — raise `ConfigError("config.yaml is empty")`, do not `TypeError` later.
- **Booleans from YAML 1.1** (`yes`, `on`) are already `bool` after `safe_load`. Do not call `bool("false")` — that is `True`.
- **Validating `logging.level`** with `getattr(logging, level)` accepts `logging.INFO` (an int). Check `isinstance(level, str)` first.

## Do NOT

- Do not use `pydantic`, `dynaconf`, `omegaconf`, or `python-dotenv`.
- Do not read environment variables. One config file, no hidden layers.
- Do not make config mutable at runtime (no `config.audio.sample_rate = ...`).
- Do not create `config.py` as a package or a folder.
- Do not add a `Config` class that wraps the dataclasses — `AppConfig` is the wrapper.
