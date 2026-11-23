# Task 18 — Unit tests: VAD

**Goal (one sentence).** Create `tests/test_vad.py` with 10 offline tests for `vad.py`.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `tests/test_vad.py` — **create**, nothing else |
| Depends on | tasks 05, 17 (`config`, `silent_block`, `speech_block` fixtures) |
| Blocks | task 24 |
| Time budget | ~35 min |

**Hard rule:** no microphone, no hardware, no model. All audio is generated in memory with NumPy.

---

## 1. APIs under test (exact)

```python
from vad import VAD, UtteranceRecorder

VAD(sample_rate: int, frame_ms: int, threshold_db: float)
    .level_db(frame: np.ndarray) -> float     # RMS in dBFS
    .is_speech(frame: np.ndarray) -> bool
    .threshold_db -> float  (settable)

UtteranceRecorder(config: AppConfig, vad: VAD | None = None)
    .calibrate(mic) -> float          # NOT tested here (needs a mic)
    .process_block(block: np.ndarray) -> np.ndarray | None
    .reset() -> None
    .state -> str   # "idle" | "speech" | "trailing"
    .stats -> dict
```

Config fields used: `cfg.vad.silence_ms`, `.min_speech_ms`, `.max_utterance_s`, `.pre_roll_ms`, `.energy_threshold_db`, `cfg.audio.sample_rate`, `cfg.audio.blocksize`.

## 2. Helper

```python
def feed(rec, blocks):
    """Yield every non-None utterance produced by the sequence of blocks."""
    out = []
    for b in blocks:
        u = rec.process_block(b)
        if u is not None:
            out.append(u)
    return out

def seconds_of_silence(n_blocks, n=512):
    return [np.zeros(n, dtype=np.float32) for _ in range(n_blocks)]

def seconds_of_speech(n_blocks, rng, n=512, amp=0.2):
    return [(amp * rng.standard_normal(n)).astype(np.float32) for _ in range(n_blocks)]
```
At 16 kHz / 32 ms, one block = 512 samples. 1 second ≈ 31 blocks.

## 3. The 10 tests

1. `level_db(zeros) < -100`.
2. `level_db(ones) ≈ 0.0` (within 0.1).
3. `is_speech` True above threshold, False below (construct `VAD(16000, 32, -40.0)` and test a loud vs silent frame).
4. 1 s silence → no utterance.
5. 1 s speech + 1 s silence → exactly one utterance.
6. That utterance's duration ≈ 1 s ± 0.15 s (trailing silence trimmed).
7. A 50 ms tap (≈2 speech blocks) → no utterance (`min_speech_ms=250`).
8. Speech longer than `max_utterance_s` → emitted and capped. Use a small cap:
   ```python
   import dataclasses
   short = dataclasses.replace(config.vad, max_utterance_s=0.5)
   rec = UtteranceRecorder(dataclasses.replace(config, vad=short))
   ```
   Feed ~1.5 s of speech; assert the emitted length ≈ 0.5 s (± 0.1).
9. **Pre-roll**: with 300 ms of silence before speech, the emitted utterance's first 100 ms is **not all zeros**. (Speech onset must not be clipped.)
10. `reset()` during speech → the next block does not emit the old buffer; state is `"idle"` and no utterance appears until a fresh phrase completes.

## 4. Rules checklist

- [ ] 10 tests, all passing offline
- [ ] Uses `config`, `silent_block`, `speech_block` fixtures from `conftest.py`
- [ ] No real `Microphone` instantiated (do not call `calibrate()`)
- [ ] Audio generated in memory; no WAV files written
- [ ] Deterministic RNG (`np.random.default_rng(0)`)
- [ ] No `time.sleep()`; no hardware; no model
- [ ] Type hints on helper functions

## 5. Do NOT

- Do not modify `vad.py`. If a test cannot pass, report the bug instead of weakening the assertion.
- Do not test `calibrate()` here (that needs a fake mic and is intentionally out of scope).
- Do not add `pytest-mock`, `hypothesis`, or `freezegun`.
- Do not use `xfail`/`skip`.

## 6. Verify — run and paste output

```powershell
python -m pytest tests/test_vad.py -q
```
Expected: 10 passed, under 1 second.

```powershell
python -m pytest -q
```
Expected: all tests pass.

## 7. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 19.
