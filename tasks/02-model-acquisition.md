# Task 02 — Model & dependency acquisition

**Phase:** 0 (foundation) · **Depends on:** 01 · **Blocks:** 06, 07 · **Effort:** 45–90 min

## Goal

Write two scripts:

1. `scripts/download_models.py` — downloads the Piper binary, one Piper voice, and the faster-whisper model. Idempotent, resumable-ish, prints sizes.
2. `scripts/check_env.py` — prints a pass/fail table of everything the app needs at runtime, with a non-zero exit code on failure.

After this task the machine can synthesize and transcribe **with no internet access**. That is the whole point: the MVP must never fail because a model download failed at runtime.

## Read first

- [`../plan.md`](../plan.md) — "Model Selection Strategy", "Risk Mitigation" (row: *Model downloads fail*).
- [`README.md`](README.md) — Ground rules.

## Files you will create

```
scripts/download_models.py
scripts/check_env.py
```

Files you may create (generated, not committed):

```
models/piper/piper/piper.exe
models/piper/piper/espeak-ng-data/...
models/piper/en_US-amy-medium.onnx
models/piper/en_US-amy-medium.onnx.json
models/whisper/... (ctranslate2 model files)
```

## Artifacts to download

| Artifact | URL | Approx. size | Lands at |
|----------|-----|--------------|----------|
| Piper Windows binary | `https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip` | ~14 MB | extracted to `models/piper/` |
| Piper voice (Amy, US English, medium) | `https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx` | ~63 MB | `models/piper/en_US-amy-medium.onnx` |
| Piper voice config | same URL + `.json` | ~4 KB | `models/piper/en_US-amy-medium.onnx.json` |
| Whisper `tiny.en` (CTranslate2) | via `faster_whisper.WhisperModel("tiny.en", download_root=...)` | ~75 MB | `models/whisper/` |

The Piper zip extracts to a `piper/` subfolder containing `piper.exe`, `espeak-ng-data/`, and DLLs. **Do not move `piper.exe` out of that folder** — it locates `espeak-ng-data` relative to itself.

## `scripts/download_models.py` — requirements

```
usage: download_models.py [-h] [--all] [--piper] [--voice] [--stt] [--force]
```

- Default (no args) behaves like `--all`.
- `--force` re-downloads even if the target already exists.
- Skip a step when the target exists **and** is larger than a minimum sane size (Piper exe > 1 MB, voice > 10 MB, whisper folder > 10 MB).
- Download to `<target>.part` and `os.replace()` into place only after the size check passes. This prevents a half-written file from looking complete.
- Follow redirects (HuggingFace redirects to a CDN). Send a `User-Agent` header; HF returns 403 for the default `Python-urllib` agent.
- Print progress every ~2 MB as a single line, e.g. `en_US-amy-medium.onnx  24.1/63.0 MB`.
- End with a summary table and exit code 0. On any failure print the failing URL, the HTTP status, and exit code 1.
- Do **not** silently swallow errors, and do **not** require `requests` (use `urllib.request` so `requirements.txt` stays unchanged).

Reference download helper (use this shape; adapt names):

```python
import urllib.request

def download(url: str, dest: Path, min_bytes: int) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "hideko-mvp/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {dest.name} {done/1e6:.1f}/{total/1e6:.1f} MB", end="")
    print()
    if tmp.stat().st_size < min_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{url} produced {tmp} bytes, expected >= {min_bytes}")
    os.replace(tmp, dest)
```

For the Whisper model, do not hand-roll the download:

```python
from faster_whisper import WhisperModel
WhisperModel("tiny.en", device="cpu", compute_type="int8", download_root=str(WHISPER_DIR))
```

This triggers the HF download into `models/whisper/` on first construction. It prints its own progress.

## `scripts/check_env.py` — requirements

Prints a table with columns `check | status | detail` and returns exit code 0 only if every **required** row passes.

Required rows:

| Check | Pass condition |
|-------|----------------|
| Python 3.11 | `sys.version_info[:2] == (3, 11)` |
| numpy 1.x | version starts with `1.` |
| imports | `sounddevice`, `soundfile`, `faster_whisper`, `yaml` all import |
| PortAudio | `sounddevice.get_portaudio_version()` starts with `PortAudio` |
| Piper binary | `models/piper/piper/piper.exe` exists, > 1 MB |
| Piper espeak data | `models/piper/piper/espeak-ng-data/` exists and is non-empty |
| Piper voice | `models/piper/en_US-amy-medium.onnx` exists, > 10 MB |
| Voice config | `models/piper/en_US-amy-medium.onnx.json` exists |
| Whisper model | `models/whisper/` contains at least one `model.bin` (search recursively — faster-whisper nests it under `models--Systran--faster-whisper-tiny.en/snapshots/<hash>/`) |
| Input device | at least one device with `max_input_channels >= 1` |
| Output device | at least one device with `max_output_channels >= 1` |

The last two rows are **warnings, not failures**, if `--no-audio` is passed (needed for CI and for agents on headless machines). Without the flag they are failures.

Never call `sd.query_devices()` at import time; only inside `main()`.

## Verification

Run in order. Paste all output.

```powershell
python scripts\download_models.py --all
python scripts\check_env.py
.\models\piper\piper\piper.exe --help
```

Expected:

- Download ends with a summary listing all four artifacts and their sizes.
- `check_env.py` prints all rows `OK` and exits 0 (`echo $LASTEXITCODE` → `0`).
- `piper.exe --help` prints usage text (proves the binary runs and the DLLs are present).

Then prove the voice actually synthesizes (this is the real test):

```powershell
"Hello, I am Hideko." | .\models\piper\piper\piper.exe --model .\models\piper\en_US-amy-medium.onnx --output_file .\models\piper\smoke.wav
python -c "import soundfile as sf; d, sr = sf.read(r'models\piper\smoke.wav'); print(len(d), sr)"
```

Expected: a line like `22050 22050` (≈1 second of audio at 22.05 kHz). A `0 22050` result means Piper received no text — see pitfalls.

Then delete the artifact:

```powershell
Remove-Item .\models\piper\smoke.wav
```

## Done criteria

- [ ] `download_models.py --all` is idempotent: a second run skips everything and exits 0.
- [ ] `check_env.py` exits 0 on this machine.
- [ ] `piper.exe --help` runs.
- [ ] The `smoke.wav` round-trip produced non-zero samples.
- [ ] `python -m pytest -q` still prints `6 passed`.
- [ ] `requirements.txt` unchanged (this task adds no Python dependency).

## Common pitfalls

| Symptom | Cause / fix |
|---------|-------------|
| HF returns `403 Forbidden` | Missing `User-Agent` header. |
| Download "succeeds" but the file is 0 bytes | You checked `Content-Length` but never verified the file on disk. Use the `min_bytes` check. |
| `piper.exe` exits 0 but writes a 0-byte WAV | Text was passed on stdin but the pipe was closed before writing, or `--output_file` points to a non-existent directory. |
| `piper.exe` prints `Failed to load espeak-ng-data` | The exe was moved out of `models/piper/piper/`. Re-extract; never relocate just the exe. |
| `check_env.py` fails on "Whisper model" | `WhisperModel(...)` was never constructed. Run `--stt` first. |
| `ctranslate2` import error after downloading | numpy 2.x got installed. Reinstall `numpy==1.26.4`. |
| Antivirus blocks `piper.exe` | Add the `models/` folder to exclusions; report it, do not disable AV. |

## Do NOT

- Do not download the model inside `stt_engine.py` or `tts_engine.py`. Those modules assume files exist and raise a typed error otherwise.
- Do not add `requests`, `huggingface_hub`, or `tqdm` to `requirements.txt`.
- Do not commit anything under `models/` (except `.gitkeep`).
- Do not pick a different Piper voice without asking. `en_US-amy-medium` is the agreed voice.
- Do not use the `piper-tts` Python package here; task 07 uses the binary by default.
