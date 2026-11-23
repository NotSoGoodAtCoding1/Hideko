# Task 07 — TTS engine (Piper)

**Goal (one sentence).** Create **one file**, `tts_engine.py`, that turns a string into a playable `AudioClip` by calling `piper.exe`, with a small LRU cache so repeated lines are instant.

**You only need this file.** Everything is inlined below. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `tts_engine.py` — **create**, nothing else |
| Depends on | task 02 (Piper binary + voice), task 03 (`AppConfig`) |
| Blocks | task 08 |
| Time budget | ~40 min |

---

## 1. What already exists

```python
from config import AppConfig

cfg.tts.backend        # "exe"
cfg.tts.piper_exe      # pathlib.Path, ABSOLUTE -> models/piper/piper/piper.exe
cfg.tts.voice_model    # pathlib.Path, ABSOLUTE -> models/piper/en_US-amy-medium.onnx
cfg.tts.length_scale   # 1.0
cfg.tts.max_chars      # 300
cfg.tts.timeout_s      # 30
```

`numpy` and `soundfile` are installed. Piper's config file is `en_US-amy-medium.onnx.json` (double extension).

## 2. Contract — copy verbatim

```python
class TTSError(Exception):
    """Raised when the Piper binary/voice is missing or synthesis fails."""

@dataclass(frozen=True)
class AudioClip:
    samples: np.ndarray      # float32, mono, -1.0..1.0
    sample_rate: int
    duration_s: float

class TTSEngine:
    def __init__(self, config: AppConfig) -> None: ...
    def is_available(self) -> bool: ...
    def synthesize(self, text: str) -> AudioClip: ...
    def clear_cache(self) -> None: ...
```

## 3. Write the file — fill the TODOs

```python
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# TODO: TTSError, @dataclass(frozen=True) AudioClip (fields in §2)


class TTSEngine:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._available = (
            cfg.tts.piper_exe.is_file()
            and cfg.tts.voice_model.is_file()
            and cfg.tts.voice_model.with_suffix(".onnx.json").is_file()
        )
        self._cache: OrderedDict[str, AudioClip] = OrderedDict()
        # TODO: nothing else. Do NOT spawn anything here.

    def is_available(self) -> bool:
        return self._available

    def synthesize(self, text: str) -> AudioClip:
        # TODO order:
        #  1. if not self._available: raise TTSError with the EXACT missing path
        #     and hint "Run `python scripts/download_models.py --all`."
        #  2. clean = self._clean(text)   (see §4.2); empty -> TTSError("cannot synthesize empty text")
        #  3. if clean in self._cache: move_to_end, return cached object AS-IS
        #  4. temp file (see §4.3); try/finally unlink it
        #  5. subprocess.run with the EXACT args in §4.1
        #  6. returncode != 0 -> TTSError with stderr tail (§4.4)
        #  7. sf.read + downmix + build AudioClip (§4.5)
        #  8. empty output check (§4.4)
        #  9. cache it (max 32, LRU), log timing (§4.6), return
        ...

    def clear_cache(self) -> None:
        self._cache.clear()

    def _clean(self, text: str) -> str:
        # TODO: strip; collapse whitespace; strip * _ # and backticks;
        # truncate to cfg.tts.max_chars at a WORD boundary with a warning.
        ...
```

## 4. Exact details

### 4.1 Subprocess call (Windows encoding matters)

```python
proc = subprocess.run(
    [
        str(cfg.tts.piper_exe),
        "--model", str(cfg.tts.voice_model),
        "--output_file", str(wav_path),
        "--length_scale", f"{cfg.tts.length_scale:.2f}",
    ],
    input=text.encode("utf-8"),       # BYTES — text=True uses cp1252 on Windows and mangles apostrophes
    capture_output=True,
    timeout=cfg.tts.timeout_s,
    cwd=str(cfg.tts.piper_exe.parent),  # so espeak-ng-data/ resolves
)
```

### 4.2 Text hygiene

- `text.strip()`; empty → `TTSError("cannot synthesize empty text")`.
- Collapse whitespace runs.
- Truncate to `cfg.tts.max_chars` at a word boundary; log a warning.
- Strip `*`, `_`, `#`, backticks. Keep `.,!?;:'-"` (including apostrophes and em-dashes).

### 4.3 Temp file

`tempfile.NamedTemporaryFile(suffix=".wav", delete=False)` in the **system temp dir**. **Close it before** calling Piper (Windows locks open files). `unlink(missing_ok=True)` in a `finally`.

### 4.4 Failure checks

- `proc.returncode != 0` → `TTSError` including `proc.stderr.decode("utf-8", "replace")[-800:]`.
- WAV missing **or** `duration_s < 0.05` → `TTSError("Piper produced empty audio (exit 0)")`. This is the classic Windows failure.

### 4.5 Read the WAV

```python
data, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
if data.ndim > 1:
    data = data.mean(axis=1)
clip = AudioClip(samples=np.ascontiguousarray(data, dtype=np.float32),
                 sample_rate=int(sr), duration_s=len(data) / sr)
```
Read fully **before** unlinking.

### 4.6 Cache and logging

- `OrderedDict[str, AudioClip]`, max 32 entries, LRU eviction on insert. Cached clips returned **as-is** — never mutate `samples` (`Speaker` copies before applying volume).
- `logger.info("tts: %.2fs -> %.2fs audio, %d chars", latency, clip.duration_s, len(text))`. Never log per sentence at DEBUG.

### 4.7 Optional python backend (skip unless you have time)

If `cfg.tts.backend == "python"`, import `piper` lazily and use `PiperVoice.load(...)` + `voice.synthesize(text)`, reading `chunk.audio_float_array` / `chunk.sample_rate`. If `piper` is absent raise `TTSError("backend 'python' requires: pip install piper-tts==1.2.0")`. **Do not add `piper-tts` to `requirements.txt`.** The exe backend is the default and the only one tested here.

### 4.8 CLI (`__main__`)

- `python tts_engine.py --check` → print `piper ok: <path>` / `voice ok: <path> (<n> MB)`, exit 0; missing item → message, exit 3.
- `python tts_engine.py --say "..." [--out out.wav]` → print `synthesized 1.4s at 22050 Hz in 0.83s`. Without `--out`, play via `audio_manager.Speaker` (do **not** call `sd.play` here).
- `python tts_engine.py --say "..." --out out.wav` writes the WAV with `sf.write` instead of playing.

## 5. Rules checklist

- [ ] `__init__` only checks file existence — no subprocess, no model load
- [ ] `is_available()` returns the stored bool
- [ ] Missing exe/voice → `TTSError` with exact path + `download_models.py --all` hint
- [ ] stdin sent as **bytes**, `cwd` set to the Piper folder
- [ ] temp file closed before Piper runs, unlinked in `finally`
- [ ] non-zero exit and empty-output checks present
- [ ] stereo WAV downmixed to mono; native sample rate preserved (no resampling)
- [ ] LRU cache of 32, `clear_cache()` works
- [ ] Text with `'`, `"`, `—`, and emoji does not crash
- [ ] Type hints + docstrings on all public functions/classes
- [ ] No `print()` outside `if __name__ == "__main__":`

## 6. Do NOT

- Do not add `gTTS`, `edge-tts`, `pyttsx3`, Coqui, or any new dependency.
- Do not resample the output — pass `clip.sample_rate` to `Speaker.play` (voice is 22 050 Hz).
- Do not stream synthesis to the speaker. Do not spawn a background thread.
- Do not write the temp WAV into the project folder.
- Do not use a bare `except:` or `except Exception: pass`.

## 7. Verify — run and paste output

```powershell
python tts_engine.py --check
python tts_engine.py --say "Hello, I am Hideko, and this is a test of my voice."
```
Expected: audible speech within ~2 s at 22 050 Hz.

```powershell
python -c "import time; from config import load_config; from tts_engine import TTSEngine; e=TTSEngine(load_config()); t=time.perf_counter(); a=e.synthesize('Testing one two three.'); print('first', round(time.perf_counter()-t,2)); t=time.perf_counter(); b=e.synthesize('Testing one two three.'); print('cached', round(time.perf_counter()-t,4), a.duration_s)"
```
Expected: `first 0.8..1.6` then `cached 0.0...`.

```powershell
python -c "from config import load_config; from tts_engine import TTSEngine, TTSError; import dataclasses; c=load_config(); bad=dataclasses.replace(c.tts, piper_exe=c.root/'nope.exe'); e=TTSEngine(dataclasses.replace(c, tts=bad)); e.synthesize('hi')"
```
Expected: `TTSError: Piper binary not found at ...nope.exe. Run: python scripts/download_models.py --all` — **not** `FileNotFoundError`.

```powershell
python -m pytest -q
```
Expected: still passes (formal tests for this module arrive in task 20).

## 8. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 08.
