# Task 06 — STT engine (faster-whisper)

**Goal (one sentence).** Create **one file**, `stt_engine.py`, that loads a Whisper model once and turns a 16 kHz `float32` array into a `Transcript`. Two things matter more than accuracy: **never crash on silence**, and **never return Whisper's silence hallucinations** ("Thank you.", "Subtitles by...").

**You only need this file.** Every fact, signature, and command is inlined below. Do **not** open `README.md`, `plan.md`, or any other task file. Do not go looking for hidden conventions.

| | |
|---|---|
| Files you touch | `stt_engine.py` — **create**, nothing else |
| Depends on | task 02 (models downloaded), task 03 (`AppConfig`) |
| Blocks | task 08 |
| Time budget | ~40 min |

---

## 1. What already exists (use these exact names)

```python
from config import AppConfig

cfg.stt.model_size        # "tiny.en"
cfg.stt.device            # "cpu"
cfg.stt.compute_type      # "int8"
cfg.stt.download_root     # pathlib.Path, ABSOLUTE (already resolved by config.py)
cfg.stt.language          # "en"
cfg.stt.beam_size         # 1
cfg.stt.max_audio_s       # 30
cfg.stt.min_avg_logprob   # -1.0
cfg.runtime.log_transcripts  # bool
```

`faster_whisper`, `numpy`, and `soundfile` are installed. `models/whisper/` was populated by task 02.

## 2. Contract — copy verbatim, do not rename anything

```python
class STTError(Exception):
    """Raised when the model cannot be loaded or transcription fails fatally."""

@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    duration_s: float
    latency_s: float
    avg_logprob: float | None

class STTEngine:
    def __init__(self, config: AppConfig) -> None: ...
    def warmup(self) -> float: ...
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript: ...
```

## 3. Write the file — fill the TODOs in this skeleton

```python
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

_HALLUCINATIONS = frozenset({
    "thank you", "thanks for watching", "thank you for watching",
    "subtitles by the amara org community", "subscribe", "please subscribe",
    "bye", "you", "the end", "okay", "hmm", "uh", "mm",
    "продолжение следует", "субтитры сделал dimatorzok",
})

# TODO: class STTError, @dataclass(frozen=True) Transcript (fields in §2)


class STTEngine:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._model = None                 # type: ignore[assignment]
        # TODO: nothing else. Model load is LAZY.

    def _ensure_model(self) -> None:
        # TODO: if self._model is None, construct it with the exact call in §4.1.
        # Wrap OSError / ValueError / RuntimeError in STTError with the hint
        # "Run `python scripts/download_models.py --stt`."
        ...

    def warmup(self) -> float:
        # TODO: t0 = perf_counter(); self._ensure_model();
        # transcribe 1 s of float32 zeros directly (bypass short-input guards
        # if necessary); return elapsed seconds. Log "stt ready in X.Xs".
        ...

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript:
        # TODO, in this exact order:
        #  1. np.asarray(audio, dtype=np.float32).reshape(-1)
        #  2. sample_rate != 16000 -> STTError("STT expects 16 kHz audio, got ... Resample before calling.")
        #  3. duration < 0.30 -> return empty Transcript WITHOUT touching the model
        #  4. duration > max_audio_s -> STTError
        #  5. np.max(np.abs(audio)) < 1e-4 -> empty Transcript, no model
        #  6. self._ensure_model(); t0 = perf_counter()
        #  7. model.transcribe(...) with the EXACT kwargs in §4.2
        #  8. materialise the segment generator with a list comprehension
        #  9. filter, join, normalise, hallucination-filter (§4.3)
        # 10. build Transcript, log INFO timing (§4.4), return
        ...
```

## 4. Exact details (do not improvise)

### 4.1 Model construction

```python
from faster_whisper import WhisperModel
self._model = WhisperModel(
    cfg.stt.model_size,
    device=cfg.stt.device,
    compute_type=cfg.stt.compute_type,
    download_root=str(cfg.stt.download_root),
    cpu_threads=max(1, (os.cpu_count() or 4) // 2),
)
```

### 4.2 Transcription call

```python
segments, info = self._model.transcribe(
    audio,
    language=cfg.stt.language,
    beam_size=cfg.stt.beam_size,
    vad_filter=False,                   # our VAD already trimmed the audio
    condition_on_previous_text=False,   # REQUIRED — stops hallucination snowballing
    temperature=0.0,
)
text = " ".join(s.text.strip() for s in segments)   # segments IS A GENERATOR
```

Forgetting to iterate the generator is the #1 bug in this task: `text` comes back empty.

### 4.3 Filtering (apply in this order)

1. Collapse internal whitespace, strip.
2. Drop a segment when `s.avg_logprob < cfg.stt.min_avg_logprob` **and** `getattr(s, "no_speech_prob", 0) > 0.6`.
3. If joined text has < 2 characters → return empty.
4. Normalise for the hallucination check: `text.lower()`, strip punctuation `.,!?…-–—` and quotes, collapse whitespace. If the normalised form is in `_HALLUCINATIONS` **and** audio duration < 2 s → return empty. (A real 1 s "thank you" is plausible; a 1 s "Subtitles by the Amara org community" is not. The duration guard keeps false drops rare — leave a comment saying so.)
5. If the text is a single token repeated 4+ times (`"you you you you"`) → return empty.

### 4.4 Logging

`logger.info("stt: %.2fs for %.2fs audio -> %s", latency, duration, text)` — skip the text when `cfg.runtime.log_transcripts` is false.

`latency_s` = wall clock around the `transcribe` call, via `time.perf_counter()`.

### 4.5 Empty transcript helper

Return `Transcript(text="", language=None, duration_s=duration, latency_s=0.0, avg_logprob=None)`.

## 5. Rules checklist

- [ ] `__init__` stores config and sets `_model = None` — **no model load in `__init__`**
- [ ] `_ensure_model()` loads once, on first use
- [ ] `warmup()` loads the model and runs one silent transcription; returns elapsed seconds
- [ ] < 0.30 s input returns empty **without calling `_ensure_model()`**
- [ ] digital silence returns empty without calling the model
- [ ] `sample_rate != 16000` raises `STTError` (no silent resampling)
- [ ] `vad_filter=False` and `condition_on_previous_text=False` are present
- [ ] segment generator is materialised
- [ ] model-load failures become `STTError` naming `download_models.py --stt`
- [ ] `latency_s` measured with `perf_counter`
- [ ] `__main__` supports `--file PATH`, `--mic SECONDS`, `--warmup`; exit 0 ok / 3 `STTError`
- [ ] `--file` rejects non-16 kHz / non-mono WAVs with the actual rate/channels (no resampling)
- [ ] Type hints on every public function; docstrings on every public class/function
- [ ] No `print()` anywhere except inside `if __name__ == "__main__":`

## 6. Do NOT

- Do not install `openai-whisper`, `torch`, `transformers`, `whisper.cpp`, or any new dependency.
- Do not resample inside this module.
- Do not add streaming / partial / `without_timestamps` tricks.
- Do not cache transcripts. Do not translate (`task="translate"`).
- Do not change `beam_size` from config.
- Do not use a bare `except:` or `except Exception: pass`.

## 7. Verify — run these and paste the real output

```powershell
python stt_engine.py --warmup
```
Expected: `model loaded in ~1.8s; warm transcription ~0.6s`, exit 0, under ~15 s.

```powershell
python -c "import numpy as np; from config import load_config; from stt_engine import STTEngine; e=STTEngine(load_config()); t=e.transcribe(np.zeros(16000*2, dtype=np.float32)); print(repr(t.text), t.latency_s)"
```
Expected: `'' 0.0...` — empty, near-zero latency, **no "Thank you."**

```powershell
python stt_engine.py --mic 5
```
Say "hello, this is a test". Expected: `text: "Hello, this is a test."` (punctuation may differ).

```powershell
python -m pytest -q
```
Expected: still passes (formal tests for this module arrive in task 19).

## 8. Report

When done, report: (1) files changed, (2) the pasted output of all four verification commands, (3) anything you could not finish. Do not start task 07.
