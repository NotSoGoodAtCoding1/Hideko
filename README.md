# Hideko — a local, offline voice assistant MVP

Speak into your microphone; she answers out loud. Everything runs locally: no cloud, no API keys. STT/TTS/triggers run on CPU; the optional LLM persona uses a local KoboldCpp server you start yourself.

**Not real-time.** Each turn takes 3–6 seconds. English only by default. Persistent memory via `memory/facts.json`. Optional local LLM fallback when no trigger matches.

---

## Status / at-a-glance

| | |
|---|---|
| STT | faster-whisper `tiny.en`, int8, CPU |
| TTS | Piper `en_US-amy-medium`, CPU |
| Conversation | keyword/phrase matching, ~15 triggers |
| Memory | local JSON facts, learned from explicit phrases (`my name is Ada`) |
| LLM fallback | KoboldCpp over loopback HTTP, optional, hybrid persona (conversational turns only) |
| Network at runtime | none (loopback to a user-started local KoboldCpp process when LLM is enabled) |
| GPU | not required for core features; KoboldCpp decides GPU use |
| Measured turn latency | **observed; no target set for this sprint** (see [`logs/benchmark.md`](logs/benchmark.md)) |
| Tested on | Windows 11, Python 3.11, 4-core CPU, 16 GB RAM |

---

## Requirements

- Windows 10/11 (Linux/macOS likely work; untested — say so)
- Python **3.11.x** (3.12+ unsupported; one line why: binary wheels for `ctranslate2`)
- 4+ cores, 8 GB RAM minimum, 16 GB recommended
- 5 GB free disk (core models ≈ 160 MB; optional GGUF model for KoboldCpp ≈ 0.5 GB; rest is venv headroom)
- Working microphone + speakers/headphones
- **Headphones strongly recommended** — see feedback loop in Troubleshooting
- **No GPU required** for core features. STT, TTS and trigger matching run on CPU. If you enable the optional LLM, KoboldCpp decides GPU use.
- Optional: `KoboldCpp.exe` started by you before enabling `llm.enabled` (AGPL-3.0), plus an already-downloaded GGUF model.

---

## Install

```powershell
cd hideko
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts\download_models.py --all
# Optional: download a GGUF model for KoboldCpp (only needed if you enable `llm.enabled`)
python scripts\download_models.py --llm
# Optional: start KoboldCpp yourself, then leave it running
.\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048
python scripts\check_env.py
python main.py
```

If the CUDA build does not start on your machine, try `.\tools\koboldcpp\koboldcpp-nocuda.exe` with the same model/port arguments. If your CPU lacks AVX2, try `--noavx2`; on very old PCs, use the KoboldCpp `oldpc` build.

Expected `check_env.py` output (all required checks OK with `llm.enabled: false`):

```
============================================================
Hideko MVP - Environment Check
============================================================
check                status   detail
------------------------------------------------------------
Python 3.11          OK       Python 3.11
numpy 1.x            OK       numpy 1.26.4
imports              OK       sounddevice, soundfile, faster_whisper, yaml
PortAudio            OK       PortAudio V19.7.0-devel
Piper binary         OK       0.51 MB
Piper espeak data    OK       17.99 MB
Piper voice          OK       63.20 MB
Voice config         OK       4882 bytes
Voice compatibility  OK       piper_version 1.0.0, single-codepoint phonemes
Whisper model        OK       1 file(s), 75.54 MB
KoboldCpp server     SKIPPED  LLM disabled in config
Input device         OK       8 device(s) found
Output device        OK       17 device(s) found
============================================================
All required checks passed.
```

Note: If `imports` shows FAILED with "No module named 'requests'", install it: `python -m pip install requests`. This is a dependency of faster-whisper.

---

## Optional LLM (KoboldCpp)

The optional LLM persona is handled by **KoboldCpp**, started manually by you as a separate local process. Hideko connects over loopback HTTP only (`http://127.0.0.1:5001/v1` by default) and degrades to canned/YAML replies when KoboldCpp is unreachable.

- **Not shipped / not bundled**: download KoboldCpp yourself and place it under `tools/koboldcpp/` (gitignored), or run it from wherever you installed it.
- **Licence**: KoboldCpp is **AGPL-3.0**. This project is personal and not distributed, so using a local AGPL server is acceptable here.
- **No cloud**: Hideko only talks to loopback. Do not point `llm.base_url` at an external host.

Start KoboldCpp before enabling `llm.enabled`:

```powershell
.\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048
```

Fallbacks if that build does not work on your machine: `koboldcpp-nocuda.exe` (same args, no CUDA), add `--noavx2` for CPUs without AVX2, or use the KoboldCpp `oldpc` build for very old PCs.

---

## First conversation — literal transcript

```
Hideko MVP — Ctrl+C to stop
Stay quiet for 1 second — calibrating...
VAD calibrated: noise p95 = -58.2 dBFS, threshold = -50.2 dBFS
STT ready in 1.8s
Hideko: Hello. I am Hideko. I am listening.

[listening]
You:    hello
Hideko: Hello! I am Hideko.
  [stt 1.9s | resp 0.00s | tts 0.9s | play 1.2s | total 4.0s]
```

**Things to say:** `hello`, `tell me a joke`, `can you sing`, `what is your name`, `help`, `goodbye`.

---

## Controls

| Key / flag | Effect |
|------------|--------|
| `m` | mute / unmute the microphone |
| `q` | quit |
| `Ctrl+C` | quit |
| `--text "..."` | one-shot without the mic |
| `--no-tts` | print replies without audio |
| `--list-devices` | show audio devices |
| `--turns N` | stop after N exchanges |
| `--debug` | verbose logging |
| `--facts` | print remembered facts |
| `--forget` | delete all remembered facts |

---

## Configuration

Key settings you might change (see `config.yaml` for full details):

| Key | Default | What it does |
|-----|---------|--------------|
| `audio.input_device` | null | Microphone name substring or index; null = default |
| `audio.output_device` | null | Speaker name substring or index; null = default |
| `audio.playback_volume` | 1.0 | Volume 0.0–1.5 (values >1.0 may clip) |
| `vad.energy_threshold_db` | -40.0 | Sensitivity: lower = more sensitive (e.g. -50) |
| `vad.silence_ms` | 450 | Trailing silence that ends an utterance (lower = faster turns, but cuts off pauses) |
| `vad.post_playback_flush_ms` | 150 | Discard audio after playback to avoid transcribing our own voice (lower = faster response) |
| `stt.model_size` | tiny.en | Model: `tiny.en` (fast) or `base.en` (2× slower, more accurate) |
| `stt.cpu_threads` | null | CPU threads for STT; null = half of logical cores |
| `memory.enabled` | true | Enable persistent memory via JSON file |
| `memory.file` | memory/facts.json | Path to facts file (relative to config.yaml) |
| `llm.enabled` | false | Enable optional LLM persona (KoboldCpp must already be running on loopback) |
| `llm.base_url` | `http://127.0.0.1:5001` | KoboldCpp loopback base URL |
| `llm.endpoint` | `/v1/chat/completions` | OpenAI-compatible chat endpoint |
| `llm.model` | `local` | Model name sent to the API (ignored by KoboldCpp but required by the API shape) |
| `llm.persona_file` | `persona/hideko.yaml` | Persona/character card read into the system prompt |
| `llm.temperature` | 0.7 | Creativity: 0.0 = deterministic, 2.0 = creative |
| `llm.max_tokens` | 80 | Maximum LLM response length (keep small — long replies time out) |
| `llm.timeout_s` | 15 | HTTP timeout for LLM requests |
| `tts.length_scale` | 1.0 | Speech speed: >1.0 = slower, <1.0 = faster |
| `runtime.max_turns` | 0 | Unlimited; set to N to stop after N exchanges |
| `runtime.half_duplex` | true | Discard mic input while speaking (prevents feedback) |
| `logging.level` | INFO | DEBUG, INFO, WARNING, ERROR |

**How to change the voice:** Edit `config.yaml`, set `audio.output_device` to your speaker name or index from `--list-devices`.

**How to add a trigger:** Edit `responses/triggers.yaml`. Add a new trigger block with `name`, `priority`, `patterns` (list of phrases), and `responses` (list of replies). Set `llm_only: true` to make a matched trigger conversational (LLM-written, with canned responses as fallback); omit it or set `false` to keep canned replies.

---

## Measured performance

| Metric | median | max | budget | verdict |
|--------|--------|-----|--------|---------|
| STT cold (load + 5 s) | 1.71 s | 1.71 s | - | - |
| STT warm (5 s audio) | 0.27 s | 0.33 s | 3.0 s | PASS |
| STT on 10 s audio | 0.27 s | 0.60 s | 6.0 s | PASS |
| TTS cold | 0.85 s | 0.85 s | - | - |
| TTS warm (10 words) | 0.77 s | 0.90 s | 1.5 s | PASS |
| TTS cached | 0.59 s | 0.59 s | - | - |
| Response matching | 0.0 ms | 0.1 ms | 20 ms | PASS |
| Text turn end-to-end | 0.00 s | 0.57 s | 10 s | PASS |

*No latency pass/fail target was set for this sprint; verdicts are informational.* See [`logs/benchmark.md`](logs/benchmark.md) for full details.

*These numbers are from a 12-core CPU, 16 GB RAM. Your machine will differ.*

---

## Known limitations

- 3–6 s per turn; not suitable for real-time conversation
- No streaming STT/TTS — she waits, thinks, then speaks
- No barge-in: you cannot interrupt her
- ~15 hand-written triggers; anything else gets a fallback (or optional LLM if enabled)
- Persistent memory via JSON file; fact extraction understands only a fixed set of phrases
- English-only by default
- LLM replies require the user to start KoboldCpp first; without it Hideko falls back to canned/YAML replies
- Loopback HTTP only — no cloud
- KoboldCpp is AGPL-3.0 (fine for a personal, non-shipped project)
- `llm.enabled` stays `false` by default: conversational `llm_only` triggers and unmatched input use the LLM only when enabled
- Single-threaded, blocking loop
- Laptop speakers can cause feedback; use headphones

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `check_env.py` fails on PortAudio | Reinstall `sounddevice`; confirm venv is activated |
| No device / `PaErrorCode -9996` | Run `python main.py --list-devices`; set `audio.input_device` to a name substring in `config.yaml` |
| She never hears me | Lower `vad.energy_threshold_db` (e.g. `-50`), check Windows mic level, run `python vad.py --test` |
| She hears herself | Use headphones; ensure `runtime.half_duplex: true` in `config.yaml` |
| Transcription wrong | Try `stt.model_size: base.en` (2× slower, more accurate) |
| Speech too fast | Set `tts.length_scale: 1.15` in `config.yaml` |
| First reply takes 10 s | Model load; warm afterwards. Run `python stt_engine.py --warmup` |
| Piper writes 0-byte file | Re-download: `python scripts\download_models.py --piper --force` |
| `ModuleNotFoundError` | Activate venv: `.\.venv\Scripts\Activate.ps1`, then run again |
| KoboldCpp API FAILED in `check_env.py` | Start KoboldCpp on port 5001 and check `config.yaml` `llm.base_url` |
| LLM reply falls back to canned/YAML | Confirm KoboldCpp is running, `llm.enabled: true`, and `llm.base_url` points to loopback |
| facts file corrupt | Hideko starts empty; run `python main.py --forget` to clear |
| Memory grows over hours | Restart; `logs/hideko.log` shows RSS every 20 turns |

---

## Architecture

```
main.py              loop, half-duplex, CLI wiring
cli.py               argument parsing, status lines, key handling
config.py            typed config loader
audio_manager.py     devices, Microphone, Speaker
vad.py               energy VAD + utterance recorder
stt_engine.py        faster-whisper wrapper
tts_engine.py        Piper wrapper + cache
response_handler.py  matching, fallbacks, conversation state
memory_store.py      persistent JSON fact storage
llm_fallback.py      loopback HTTP client for KoboldCpp (not an in-process model loader)
persona/hideko.yaml  persona/character card sent as the system prompt
responses/*.yaml     trigger database
models/              downloaded models (gitignored)
  ├── whisper/       faster-whisper tiny.en
  ├── piper/         piper.exe + en_US-amy-medium.onnx
  └── llm/           optional GGUF model used by KoboldCpp
tools/koboldcpp/     local KoboldCpp binaries (external, gitignored)
scripts/             download, check, validate, benchmark, soak
tests/               offline unit tests
memory/facts.json    persistent facts file (created on first run)
```

---

## Development

```powershell
python -m pytest -q
$env:HIDEKO_E2E="1"; python -m pytest -q; Remove-Item Env:HIDEKO_E2E
python scripts\benchmark.py
python scripts\validate_responses.py
# Check facts persistence
python main.py --facts
python main.py --text "my name is Ada" --no-tts
python main.py --facts
python main.py --forget
python main.py --facts
# Optional LLM verification (requires KoboldCpp running and llm.enabled: true in config)
python llm_fallback.py --text "hello there" --config config.yaml
```

---

## Credits & licences

- faster-whisper (MIT), Whisper models (MIT, OpenAI)
- Piper (MIT) and the `en_US-amy-medium` voice — **Piper 1.0 compatible revision e7229f7d33a10e145e109b886d661984201ac3c4**
- KoboldCpp (AGPL-3.0), used locally and not shipped
- Qwen2.5-0.5B-Instruct GGUF model — **Apache-2.0** (verified from the Hugging Face model card)
- Qwen2.5-Coder-7B-Instruct GGUF model (optional) — **Apache-2.0** (verified from the Hugging Face model card)
- No affiliation with Neuro-sama or Vedal
