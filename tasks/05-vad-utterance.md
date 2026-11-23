# Task 05 — VAD & utterance recorder

**Goal (one sentence).** Create **one file**, `vad.py`, containing an energy-based voice activity detector plus a state machine that turns a stream of 32 ms blocks into exactly one complete utterance array per spoken phrase.

**You only need this file.** Every fact, signature, and command is inlined below. Do **not** open `README.md`, `plan.md`, or any other task file. This module is what makes the loop hands-free, and it is the task most likely to be "improved" into something broken — the acceptance criteria below are strict.

| | |
|---|---|
| Files you touch | `vad.py` — **create**, nothing else |
| Depends on | tasks 03 (`AppConfig`), 04 (`Microphone`) |
| Blocks | task 08 |
| Time budget | ~60 min |

**Design decision — do not change:** pure-NumPy energy VAD. No `webrtcvad` (needs a C compiler on Windows), no `silero-vad` (pulls torch, ~2 GB). The plan's VAD requirement is satisfied by dBFS thresholding + calibration + silence timeout.

---

## 1. What already exists — use these exact names

```python
from config import AppConfig
from audio_manager import Microphone

cfg.vad.energy_threshold_db       # -40.0 dBFS (used only when calibrate is False)
cfg.vad.calibrate                 # bool
cfg.vad.calibration_ms            # 1000
cfg.vad.silence_ms                # 700  (trailing silence that ends an utterance)
cfg.vad.min_speech_ms             # 250
cfg.vad.max_utterance_s           # 15
cfg.vad.pre_roll_ms               # 300
cfg.vad.post_playback_flush_ms    # 300 (used by main.py, not here)

cfg.audio.sample_rate             # 16000
cfg.audio.block_ms                # 32
cfg.audio.blocksize               # 512 samples

mic.read_block() -> np.ndarray    # float32 mono, length cfg.audio.blocksize
```

`numpy` and the standard library only. `Microphone` is never opened by this module.

## 2. Contract — copy verbatim, do not rename anything

```python
class VAD:
    def __init__(self, sample_rate: int, frame_ms: int, threshold_db: float) -> None: ...
    def level_db(self, frame: np.ndarray) -> float: ...      # RMS in dBFS
    def is_speech(self, frame: np.ndarray) -> bool: ...
    @property
    def threshold_db(self) -> float: ...
    @threshold_db.setter
    def threshold_db(self, value: float) -> None: ...

class UtteranceRecorder:
    def __init__(self, config: AppConfig, vad: VAD | None = None) -> None: ...
    def calibrate(self, mic: Microphone) -> float: ...       # returns the threshold it chose
    def process_block(self, block: np.ndarray) -> np.ndarray | None: ...  # full utterance or None
    def reset(self) -> None: ...
    @property
    def state(self) -> str: ...    # "idle" | "speech" | "trailing"
    @property
    def stats(self) -> dict[str, float | int]: ...  # blocks_seen, utterances, last_utterance_s
```

## 3. Write the file — fill the TODOs in this skeleton

```python
from __future__ import annotations

import logging
from collections import deque

import numpy as np

from config import AppConfig

logger = logging.getLogger(__name__)


class VAD:
    """Energy-based voice activity detector using RMS in dBFS."""

    def __init__(self, sample_rate: int, frame_ms: int, threshold_db: float) -> None:
        self._sample_rate = sample_rate
        self._frame_ms = frame_ms
        self._threshold_db = threshold_db
        # TODO: nothing else

    def level_db(self, frame: np.ndarray) -> float:
        # TODO: exact math in §4.1
        ...

    def is_speech(self, frame: np.ndarray) -> bool:
        # TODO: level_db(frame) >= self._threshold_db
        ...

    @property
    def threshold_db(self) -> float:
        return self._threshold_db

    @threshold_db.setter
    def threshold_db(self, value: float) -> None:
        self._threshold_db = value


class UtteranceRecorder:
    """Turns a stream of blocks into one complete utterance per spoken phrase."""

    def __init__(self, config: AppConfig, vad: VAD | None = None) -> None:
        self._config = config
        self._vad = vad or VAD(config.audio.sample_rate, config.audio.block_ms,
                               config.vad.energy_threshold_db)
        self._state = "idle"
        self._pre_roll: deque[np.ndarray] = deque(maxlen=self._pre_roll_blocks())
        self._buffer: list[np.ndarray] = []
        self._speech_run_ms = 0
        self._silence_run_ms = 0
        # TODO: stats counters (blocks_seen, utterances, last_utterance_s)

    def _pre_roll_blocks(self) -> int:
        # TODO: max(1, pre_roll_ms // block_ms)
        ...

    def calibrate(self, mic: Microphone) -> float:
        # TODO: exact steps in §4.2
        ...

    def process_block(self, block: np.ndarray) -> np.ndarray | None:
        # TODO: state machine in §4.3. Never raises on silent input.
        ...

    def reset(self) -> None:
        # TODO: clear state, buffers, and all counters; state = "idle"
        ...

    @property
    def state(self) -> str:
        return self._state

    @property
    def stats(self) -> dict[str, float | int]:
        # TODO: return blocks_seen, utterances, last_utterance_s
        ...
```

## 4. Exact details

### 4.1 Signal math (use exactly this)

```python
rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)) + 1e-12))
level_db = 20.0 * np.log10(rms + 1e-12)    # 0 dBFS = full scale, silence ≈ -120
```

- `is_speech` returns `level_db >= threshold_db`.
- Frames shorter than 2 samples are treated as silence.
- Compute RMS in **`float64`** to avoid overflow with float32 squares.

### 4.2 Calibration — `calibrate(mic)`

1. Read `calibration_ms / block_ms` blocks from the mic (minimum 10 blocks).
2. Compute `level_db` for each.
3. `noise = np.percentile(levels, 95)` — the 95th percentile, **not** the mean, so a cough does not drag the threshold up.
4. `threshold = max(noise + 8.0, -55.0)`; clamp to `[-70.0, -20.0]`.
5. Set `self._vad.threshold_db = threshold`, log it at INFO, return it.

If `cfg.vad.calibrate` is `False`, `calibrate()` must not be called; `process_block` uses `cfg.vad.energy_threshold_db` unchanged.

Log both numbers exactly: `VAD calibrated: noise p95 = -58.2 dBFS, threshold = -50.2 dBFS`. This single line solves 90% of "it never hears me" reports.

### 4.3 State machine — the core of the task

Three states: `idle` → `speech` → `trailing` → (`idle` + emit).

```
idle:
  keep a pre-roll deque of the last pre_roll_ms of blocks (including the current one)
  if block is speech:
      count consecutive speech blocks
      if speech_ms >= min_speech_ms:
          state = speech
          buffer = list(pre_roll)   # already contains the onset: pre_roll_ms > min_speech_ms
  else:
      reset the consecutive-speech counter, keep filling pre-roll

speech:
  append every block (speech or not)
  if block is not speech:  silence_run += block_ms
  else:                    silence_run = 0
  if silence_run >= silence_ms:             emit; state = trailing (one block later -> idle)
  if buffered_ms >= max_utterance_s*1000:   emit truncated; state = trailing

trailing:
  clear buffers, state = idle, return None
```

**Emission details**

- Return `np.concatenate(buffer).astype(np.float32)` with trailing silence **trimmed** to at most `silence_ms`.
- Reset all counters after emitting.
- Never emit an utterance shorter than `min_speech_ms` (guard against a door slam).
- `process_block` must be **O(1) amortised** — use `collections.deque(maxlen=N)` for pre-roll, not `np.concatenate` on every block.
- Blocks must all be the same length; if a different length arrives, log a warning **once** and process it anyway (do not crash).

`reset()` clears state and buffers; `main.py` calls it after playback in half-duplex mode.

### 4.4 CLI smoke test (`__main__`)

```
python vad.py --test                      # live mic, prints transitions and utterance durations
python vad.py --test --record out.wav     # also writes each utterance as a WAV
python vad.py --selftest                  # synthetic, no hardware required
```

`--test` output looks like:

```
threshold: -49.8 dBFS
[idle] listening...
[speech] start
[trailing] 1.42 s utterance, 31280 samples
[emit] wrote out_001.wav
```

`--selftest` must work with **no microphone**: feed 1 s of `np.zeros`, 1 s of `0.05 * np.random.randn`, 1 s of zeros through `process_block` at 32 ms blocks and assert exactly one utterance with duration ≈ 1 s. Exit 0 on success, 1 on failure. This is the CI path.

## 5. Common pitfalls

| Symptom | Cause / fix |
|---------|-------------|
| Every block is "speech" | Threshold too low (e.g. `-80`) or calibration read while speaking. Default `noise + 8 dB` with `-55` floor. |
| Never detects speech | Threshold too high, or mic muted at OS level. Log `level_db` per block at DEBUG. |
| Utterances are 32 ms long | You emit on the first speech block instead of waiting for `min_speech_ms` and the silence timeout. |
| Two utterances per sentence | `silence_ms` too short for natural pauses. 700 ms is the agreed value. |
| Utterance has 1 s of silence at the end | You appended the full trailing run. Trim to `silence_ms`. |
| First word missing | Pre-roll deque not included in the buffer at speech onset. |
| CPU spins at 100% | You used a `while True` loop inside `vad.py`. This module never owns a loop; `main.py` does. |
| `np.square(float32)` overflow warnings | Compute in `float64`. |

## 6. Rules checklist

- [ ] `--selftest` passes with no audio hardware
- [ ] Live `--test`: one utterance per phrase, none for silence, none for a single tap
- [ ] A 20 s monologue is cut at `max_utterance_s` and emitted (not dropped)
- [ ] First syllable not clipped (pre-roll) — say "sssix", check WAV starts with audible `s`
- [ ] Calibration line logged with both numbers
- [ ] `process_block` returns `None` in the common case and never raises on silent input
- [ ] Type hints + docstrings on all public functions/classes
- [ ] `print()` only inside `if __name__ == "__main__":`

## 7. Do NOT

- Do not add a dependency. `numpy` and the stdlib only.
- Do not open a microphone inside `UtteranceRecorder.__init__`.
- Do not implement streaming/partial transcription.
- Do not implement adaptive thresholding that drifts during a session (a loud TV would permanently deafen it).
- Do not use a `while` loop or `time.sleep` anywhere in this module.
- Do not change the `process_block` return type to a tuple.

## 8. Verify — run and paste output

```powershell
python vad.py --selftest
```
Expected: `selftest ok: 1 utterance, 1.02 s` and exit 0.

```powershell
python vad.py --test
```
Expected: say "hello" — one `[emit]` line with a duration between 0.4 and 3 s. Then stay silent for 10 s — **no** `[emit]` lines. Paste the transcript.

```powershell
python -m pytest -q
```
Expected: still passes (formal VAD tests arrive in task 18).

## 9. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 06.
