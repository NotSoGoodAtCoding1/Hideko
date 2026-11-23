# Task 20 — Unit tests: TTS + audio manager

**Goal (one sentence).** Create `tests/test_tts_engine.py` (8 cases) and `tests/test_audio_manager.py` (8 cases).

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `tests/test_tts_engine.py`, `tests/test_audio_manager.py` — **create**, nothing else |
| Depends on | tasks 04, 07, 17 (`config`, `fake_devices` fixtures) |
| Blocks | task 24 |
| Time budget | ~60 min |

**Hard rule:** no Piper process, no audio device, no model. Everything is monkeypatched.

---

## Part A — `tests/test_tts_engine.py` (8 cases)

`tts_engine.py` uses `import subprocess` and `import soundfile as sf`, so patch:

```python
monkeypatch.setattr("tts_engine.subprocess.run", fake_run)
monkeypatch.setattr("tts_engine.sf.read", lambda *a, **k: (np.zeros(22050, np.float32), 22050))
```

A reusable fake that writes the requested output WAV:

```python
import soundfile as sf

def fake_run(cmd, **kw):
    out = cmd[cmd.index("--output_file") + 1]
    sf.write(out, np.zeros(22050, dtype=np.float32), 22050)
    return SimpleNamespace(returncode=0, stderr=b"")
```

Set `config.tts.piper_exe` / `.voice_model` to `tmp_path` files that actually exist (create them with `touch()`) and create the `.onnx.json` sibling, so `is_available()` is True. Use `dataclasses.replace` to build the config.

Cases:

1. Missing exe → `is_available()` False; `synthesize()` raises `TTSError` with the download hint.
2. Empty/whitespace text → `TTSError`.
3. Text longer than `max_chars` → subprocess receives **truncated** text: set `max_chars=20` via `dataclasses.replace`, inspect `fake_run`'s recorded `kwargs["input"]`, assert `len(decoded) <= 20` and it ends on a word boundary.
4. Cache: two identical calls → `subprocess.run` called **once**.
5. Non-zero return code → `TTSError` containing the stderr tail.
6. Piper "succeeds" but writes 0 frames → `TTSError("... empty audio ...")`.
7. Stereo WAV output → downmixed to 1-D (patch `sf.read` to return shape `(n, 2)`; assert `samples.ndim == 1`).
8. Returned `AudioClip.sample_rate == 22050`, `duration_s ≈ frames / rate`.

## Part B — `tests/test_audio_manager.py` (8 cases)

Uses the `fake_devices` fixture from `conftest.py` (default device tuple `(1, 0)` → input 1, output 0). Import:

```python
from audio_manager import AudioDevice, AudioError, Speaker, find_input_device, find_output_device, list_devices
```

Cases:

1. `list_devices()` maps dicts to `AudioDevice` with correct flags (`is_default_input` True only for index 1, `is_default_output` True only for index 0).
2. `find_input_device(None)` → `1` (the default input).
3. `find_input_device(1)` → `1`.
4. `find_input_device("usb")` → `1` (case-insensitive substring).
5. `find_input_device("nope")` → `AudioError` whose message lists available devices.
6. `find_input_device("headset")` with **two** matching devices → `AudioError` mentioning ambiguity. In this test, override `fake_devices` by adding a second dict whose name contains "headset", then patch `sd.query_devices` again.
7. `find_output_device(1)` → `AudioError` (device 1 has `max_output_channels: 0`).
8. `Speaker.play` with `playback_volume=0.5` passes half-amplitude data to `sd.play` and clips at ±1.0. Patch `sd.play` to capture the array and `sd.wait` to a no-op. Patch `audio_manager.sd.play` if the module imported `sounddevice as sd` (check the import style).

```python
played = []
monkeypatch.setattr("audio_manager.sd.play", lambda data, **kw: played.append(data.copy()))
monkeypatch.setattr("audio_manager.sd.wait", lambda *a, **k: None)
speaker = Speaker(dataclasses.replace(config.audio, playback_volume=0.5) ... )
# build config via dataclasses.replace(config, audio=dataclasses.replace(config.audio, playback_volume=0.5))
```
Feed a `np.array([1.0, -1.0, 0.5])`; assert captured ≈ `[0.5, -0.5, 0.25]`. Feed `[2.0]`; assert clipped to `1.0`.

## Rules checklist

- [ ] 8 + 8 tests, all passing offline
- [ ] No real Piper subprocess, no `sd.play` to a real device, no WAV fixtures committed
- [ ] All paths under `tmp_path`
- [ ] Patch the names the modules actually use (check import style)
- [ ] Deterministic arrays; no `time.sleep()`, no `xfail`/`skip`
- [ ] Type hints on helpers

## Do NOT

- Do not modify `tts_engine.py`, `audio_manager.py`, or any application module. Report bugs instead.
- Do not add `pytest-mock`, `hypothesis`, or `freezegun`.
- Do not write output into the project folder — all WAVs go to `tmp_path` / system temp.

## Verify — run and paste output

```powershell
python -m pytest tests/test_tts_engine.py tests/test_audio_manager.py -q
```
Expected: 16 passed, under 2 seconds.

```powershell
python -m pytest -q
```
Expected: all tests pass.

## Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 21.
