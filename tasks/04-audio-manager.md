# Task 04 — Audio manager

**Phase:** 1 · **Depends on:** 01, 03 · **Blocks:** 05, 08 · **Effort:** 1.5–2 h

## Goal

Create `audio_manager.py`: device discovery, a `Microphone` class that yields fixed-size float32 blocks at 16 kHz, and a `Speaker` class that plays a float32 clip and blocks until it finishes.

This module is the only place in the codebase allowed to call `sounddevice`. Everything else receives numpy arrays.

## Read first

- [`03-config-loader.md`](03-config-loader.md) — `AudioConfig` fields you will consume.
- [`README.md`](README.md) — frozen `Microphone` / `Speaker` signatures.

## Files you will create

```
audio_manager.py
```

## Required public API

```python
class AudioError(Exception):
    """Raised for missing devices, PortAudio failures, and stream errors."""

@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_default_input: bool
    is_default_output: bool

def list_devices() -> list[AudioDevice]: ...
def find_input_device(spec: int | str | None) -> int: ...    # returns a device index
def find_output_device(spec: int | str | None) -> int: ...

class Microphone:
    def __init__(self, config: AppConfig) -> None: ...
    def __enter__(self) -> "Microphone": ...
    def __exit__(self, *exc: object) -> None: ...
    def read_block(self) -> np.ndarray: ...    # shape (blocksize,), float32, mono
    def flush(self, ms: int) -> None: ...      # read and discard `ms` of audio
    def close(self) -> None: ...

class Speaker:
    def __init__(self, config: AppConfig) -> None: ...
    def __enter__(self) -> "Speaker": ...
    def __exit__(self, *exc: object) -> None: ...
    def play(self, samples: np.ndarray, sample_rate: int) -> None: ...   # blocking
    def stop(self) -> None: ...
    @property
    def is_playing(self) -> bool: ...
    def close(self) -> None: ...
```

## Behaviour rules

### Device lookup

- `spec is None` → return the system default (`sd.default.device[0]` for input, `[1]` for output). If the default is `-1`, raise `AudioError` telling the user to set `audio.input_device` / `audio.output_device` explicitly.
- `spec` is an `int` → validate `0 <= spec < len(devices)`, and that the device has ≥1 channel in the required direction. Otherwise `AudioError` listing valid indices.
- `spec` is a `str` → case-insensitive **substring** match against device names. Zero matches → `AudioError` with the full device list. More than one match → `AudioError` listing the candidates and asking for a more specific string (do not silently pick the first).
- `sd.query_devices()` can raise `sd.PortAudioError` (e.g. no audio subsystem). Wrap it in `AudioError` with the hint: *"No audio devices found. Is a microphone/speaker connected and enabled in Windows sound settings?"*

### Microphone

- Open an `sd.InputStream` in `__init__` with:
  `samplerate=config.audio.sample_rate`, `channels=config.audio.channels`,
  `dtype="float32"`, `blocksize=config.audio.blocksize`, `device=<resolved index>`.
- `read_block()` calls `stream.read(blocksize)`, receives shape `(blocksize, channels)`, downmixes with `.mean(axis=1)` when `channels > 1`, and returns a contiguous `float32` 1-D array.
- Wrap `sd.PortAudioError` in `AudioError` including the PortAudio message.
- `flush(ms)` reads `ceil(ms / block_ms)` blocks and throws them away. It must not raise if the stream already closed.
- `close()` is idempotent (`if self._stream is not None: ...; self._stream = None`).
- Never call `sd.stop()` in `Microphone`.

### Speaker

- `play()`:
  1. Convert input to `float32` 1-D (`np.asarray(samples, dtype=np.float32).reshape(-1)`).
  2. Apply `config.audio.playback_volume` and `np.clip(..., -1.0, 1.0)`.
  3. `sd.play(data, samplerate=sample_rate, device=<resolved index>, blocking=False)` then `sd.wait()`.
  4. Set `_playing = True` before `sd.play` and `False` in a `finally` block.
- Empty input (`len(samples) == 0`) is a no-op, not an error.
- `stop()` calls `sd.stop()` and clears `_playing`.
- Wrap PortAudio errors in `AudioError`.
- Resampling is **not** this module's job. The caller passes the correct `sample_rate` (Piper voices are 22.05 kHz).

### CLI smoke test (`__main__`)

```
python audio_manager.py --list          # print the device table
python audio_manager.py --test          # record 3 s, play it back, print RMS
python audio_manager.py --test --seconds 5
```

- `--list` output columns: `idx | in | out | rate | default | name`.
- `--test` loads `config.yaml`, opens `Microphone`, records `seconds`, prints `recorded 3.0 s, peak 0.42, rms 0.03`, then plays it through `Speaker`. If peak is `< 0.001`, print a warning: *"Captured silence — check the Windows input device and microphone level."*
- Exit codes: `0` ok, `2` `AudioError` (print the message, no traceback).

## Reference snippet (the parts agents usually get wrong)

```python
import sounddevice as sd

devices = sd.query_devices()                      # list of dicts
default_in, default_out = sd.default.device       # (-1, -1) if unset

stream = sd.InputStream(
    samplerate=16000, channels=1, dtype="float32",
    blocksize=512, device=index,
)
stream.start()
block, overflowed = stream.read(512)              # block.shape == (512, 1)
mono = block[:, 0] if block.ndim == 2 else block
```

`stream.read()` raises `sd.PortAudioError` (a subclass of `Exception`, not `OSError`) — catch it explicitly.

## Verification

```powershell
python audio_manager.py --list
```

Expected: at least one row with `in>=1` and one with `out>=1`.

```powershell
python audio_manager.py --test --seconds 3
```

Expected: `recorded 3.0 s, peak ...` then audible playback of your own voice. If you are on a machine with no mic, this command is allowed to fail with exit code 2 and a clear message — say so in your report.

```powershell
python -c "import audio_manager; print(audio_manager.list_devices()[:2])"
python -m pytest -q
```

Expected: importing the module does **not** open a device and does **not** print anything. Tests still pass.

Bad-device handling check:

```powershell
python -c "from config import load_config; from audio_manager import find_input_device, AudioError; c=load_config(); find_input_device('definitely-not-a-device')"
```

Expected: `AudioError: no input device matches 'definitely-not-a-device'. Available input devices: ...` — no raw PortAudio dump.

## Done criteria

- [ ] `--list` prints a readable table including default markers.
- [ ] `--test` records and plays back real audio.
- [ ] Importing `audio_manager` has zero side effects (no device open, no output).
- [ ] `AudioError` is raised (never `PortAudioError`) for every failure path.
- [ ] `close()` can be called twice without raising.
- [ ] `python -m pytest -q` still passes.

## Common pitfalls

| Symptom | Cause / fix |
|---------|-------------|
| `PaErrorCode -9996: Invalid device` | Device index came from a different host API, or the device was unplugged. Re-run `--list`. |
| `PaErrorCode -9997: Invalid sample rate` | The chosen input device does not support 16 kHz. Add a clear error; do **not** silently change the rate (Whisper needs 16 kHz). |
| `PaErrorCode -9999: Unanticipated host error` on Windows | Usually another app has the mic in exclusive mode, or the device is disabled. Report the raw message. |
| `read_block()` returns shape `(512,)` sometimes and `(512,1)` other times | You used `dtype="float32"` but `channels` from config inconsistently. Always reshape to `(-1,)`. |
| Playback is garbled/slow | You passed 22 050 samples to a stream opened at 16 000. `play()` must take an explicit `sample_rate` and pass it to `sd.play`. |
| `sd.play` returns immediately and the mic records while Hideko talks | You used `blocking=True` incorrectly or skipped `sd.wait()`. `play()` must block. |
| Recording your own speaker output | Expected with laptop speakers. Task 08 handles half-duplex; task 24 recommends headphones. |

## Do NOT

- Do not import `pyaudio`, `pydub`, `librosa`, `webrtcvad`, or `soundcard`.
- Do not resample, denoise, normalize, or apply gain curves. Volume scaling only.
- Do not spawn threads or use `asyncio`.
- Do not read `config.yaml` directly — take an `AppConfig`.
- Do not print device lists at import time.
- Do not catch `Exception` around stream code; catch `sd.PortAudioError` and `OSError` specifically.
