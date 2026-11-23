# Task 01 — VAD & flush timing defaults

**Phase A (latency). No dependencies. Touch at most 4 files.**

## Goal

Reduce per-turn dead time by tightening three existing VAD timing defaults. This is a **config/default change only** — do not modify any VAD logic.

Expected saving: ~250 ms from the trailing-silence wait, ~50 ms from the speech-onset wait, ~150 ms from the post-playback mic flush. No latency pass/fail target was set by the human: record observed timings, do not assert a threshold.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Do not edit `vad.py`. Do not edit `main.py`. Do not change `pre_roll_ms` or `calibrate`.
- Type hints and docstrings on anything new.
- Tests must pass with no microphone: `python -m pytest -q`.

## Current state (exact)

`config.yaml` lines 17–21:
```yaml
vad:
  energy_threshold_db: -40.0  # dBFS. Ignored when calibrate: true.
  calibrate: true             # measure ambient noise for calibration_ms at startup
  calibration_ms: 1000
  silence_ms: 700             # trailing silence that ends an utterance
  min_speech_ms: 250          # speech needed before an utterance is considered started
  max_utterance_s: 15         # hard cap; longer speech is truncated and processed
  pre_roll_ms: 300            # audio kept from before speech onset (avoids clipped first syllable)
  post_playback_flush_ms: 300 # audio discarded after playback to avoid transcribing our own voice
```

`config.py` `_DEFAULTS["vad"]` lines 115–124 has the same numbers.

`config.py::_validate_vad` (lines 279–298) already checks:
```python
    silence_ms = config.get("silence_ms", _DEFAULTS["vad"]["silence_ms"])
    if silence_ms < 100:
        raise ConfigError(f"{path}.silence_ms must be at least 100, got {silence_ms}")

    min_speech_ms = config.get("min_speech_ms", _DEFAULTS["vad"]["min_speech_ms"])
    if min_speech_ms < 50:
        raise ConfigError(f"{path}.min_speech_ms must be at least 50, got {min_speech_ms}")

    max_utterance_s = config.get("max_utterance_s", _DEFAULTS["vad"]["max_utterance_s"])
    if not (1.0 <= max_utterance_s <= 60.0):
        raise ConfigError(f"{path}.max_utterance_s must be between 1 and 60, got {max_utterance_s}")

    pre_roll_ms = config.get("pre_roll_ms", _DEFAULTS["vad"]["pre_roll_ms"])
    if pre_roll_ms < min_speech_ms:
        raise ConfigError(
            f"{path}.pre_roll_ms ({pre_roll_ms}) must be >= {path}.min_speech_ms ({min_speech_ms}) "
            "(the utterance onset would be clipped; pre-roll must cover the speech-detection window)"
        )
```

`tests/conftest.py` lines 19–23 contains the `vad` part of the `config` fixture with the old numbers.

## Steps

1. **`config.yaml`** — change exactly three values:
   - `silence_ms: 700` → `silence_ms: 450`
   - `min_speech_ms: 250` → `min_speech_ms: 200`
   - `post_playback_flush_ms: 300` → `post_playback_flush_ms: 150`

   Keep every other line identical. Update the inline comments so they stay accurate, e.g. `silence_ms: 450  # trailing silence that ends an utterance (lower = faster turns, but cuts off pauses)`.

2. **`config.py`** — in `_DEFAULTS["vad"]`, mirror the three new numbers:
   ```python
       "vad": {
           "energy_threshold_db": -40.0,
           "calibrate": True,
           "calibration_ms": 1000,
           "silence_ms": 450,
           "min_speech_ms": 200,
           "max_utterance_s": 15.0,
           "pre_roll_ms": 300,
           "post_playback_flush_ms": 150,
       },
   ```

3. **`config.py::_validate_vad`** — append this validation (do not remove existing checks):
   ```python
       flush_ms = config.get("post_playback_flush_ms", _DEFAULTS["vad"]["post_playback_flush_ms"])
       if not isinstance(flush_ms, int) or not (0 <= flush_ms <= 2000):
           raise ConfigError(
               f"{path}.post_playback_flush_ms must be an int between 0 and 2000, got {flush_ms}"
           )
   ```
   The existing `pre_roll_ms >= min_speech_ms` invariant still holds (300 ≥ 200). Do not weaken it.

4. **`tests/conftest.py`** — in the `config` fixture, set `silence_ms: 450`, `min_speech_ms: 200`, `post_playback_flush_ms: 150`. Leave all other fixture values unchanged.

5. **`tests/test_config.py`** — add tests:
   - `test_vad_defaults_are_tuned` — `load_config()` returns `silence_ms == 450`, `min_speech_ms == 200`, `post_playback_flush_ms == 150`, `pre_roll_ms == 300`.
   - `test_post_playback_flush_rejects_bad_values` — parametrize `-1`, `2001`, `1.5`, `"150"`; each raises `ConfigError`.
   - `test_pre_roll_invariant_still_enforced` — config with `pre_roll_ms: 100` and `min_speech_ms: 200` raises `ConfigError`.
   Use the existing fixture/helper style in that file; do not rewrite unrelated tests.

## Verification

Run all of these and paste the real output.

```powershell
python -m pytest -q
python config.py --check
python vad.py --selftest
python main.py --turns 3 --no-greet --no-tts
```

Expected:

- `python -m pytest -q` — all tests pass (same count as before plus your 2–3 new ones, no failures).
- `python config.py --check` — prints JSON containing `"silence_ms": 450`, `"min_speech_ms": 200`, `"post_playback_flush_ms": 150`, `"pre_roll_ms": 300`.
- `python vad.py --selftest` — exits 0 and prints a line like `selftest ok: 1 utterance(s), 1.63 s`.
- `python main.py --turns 3 --no-greet --no-tts` — starts without VAD errors, prints `[listening]`, `You: ...`, `Hideko: ...` lines and timing lines; no exception, exit code 0. If no mic is available, note that and rely on the three other commands.

Record (do not assert) the timing lines you observe, e.g. `[stt 1.9s | resp 0.00s | tts 0.0s | play 0.0s | total 1.9s]`. There is **no pass/fail latency threshold** for this sprint.

## Stop and ask the human if

- The VAD selftest emits 0 or 2+ utterances after the change, or
- Live speech gets clipped at the first syllable (would mean the `pre_roll_ms >= min_speech_ms` invariant was broken), or
- Any existing test fails for a reason unrelated to the three changed values.
