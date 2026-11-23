# Task 24 — README & documentation

**Goal (one sentence).** Write a `README.md` a stranger can follow from a bare Windows machine to a working conversation in **under 15 minutes**, and that is brutally honest about what does not work.

**You only need this file.** Everything is inlined. Do **not** open `plan.md` or any task file — except `logs/benchmark.md`, which you must read for real numbers.

| | |
|---|---|
| Files you touch | `README.md` (create) — optional `docs/TROUBLESHOOTING.md`, `docs/ARCHITECTURE.md` only if README exceeds ~300 lines |
| Depends on | all previous tasks; `logs/benchmark.md` from task 21 |
| Blocks | release |
| Time budget | ~60 min |

The plan's success metric is explicit: *"Usability: clear instructions, easy setup (< 15 minutes)"* and *"Documentation: honest about limitations, no false promises"*. This task is graded against those two lines.

---

## 1. Required structure — keep this order

### 1. Title + one-paragraph description

> Hideko — a local, offline voice assistant MVP. Speak into your microphone; she answers out loud. Everything runs on your CPU: no cloud, no API keys, no GPU.

State up front: **not real-time** (3–6 s per turn), **English only** by default, **no memory between runs**.

### 2. Status / at-a-glance table

| | |
|---|---|
| STT | faster-whisper `tiny.en`, int8, CPU |
| TTS | Piper `en_US-amy-medium`, CPU |
| Conversation | keyword/phrase matching, ~15 triggers |
| Network at runtime | none |
| GPU | not required |
| Measured turn latency | **X s median** (from `logs/benchmark.md`) |
| Tested on | Windows 11, Python 3.11, 4-core CPU, 16 GB RAM |

Fill in **real** numbers. If you only tested one machine, say so.

### 3. Requirements

- Windows 10/11 (Linux/macOS likely work; untested — say so)
- Python **3.11.x** (3.12+ unsupported; one line why: binary wheels for `ctranslate2`)
- 4+ cores, 8 GB RAM minimum, 16 GB recommended
- 5 GB free disk (models ≈ 160 MB; rest is venv headroom)
- Working microphone + speakers/headphones
- **Headphones strongly recommended** — see feedback loop in Troubleshooting

### 4. Install (numbered, copy-pasteable, PowerShell)

```powershell
cd hideko
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts\download_models.py --all
python scripts\check_env.py
python main.py
```
Include the expected all-`OK` output of `check_env.py` and the exact download sizes so nobody thinks it hung. Do **not** use a placeholder `git clone <repo>`; say "cd into the project folder".

### 5. First conversation — literal transcript

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
Then a "things to say" list: `hello`, `tell me a joke`, `can you sing`, `what is your name`, `help`, `goodbye`.

### 6. Controls table

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

Copy the exact flag spellings from `python main.py --help`, not from memory.

### 7. Configuration

A table of keys users actually change, with defaults and one-line explanations: `audio.input_device`, `audio.output_device`, `audio.playback_volume`, `vad.energy_threshold_db`, `vad.silence_ms`, `stt.model_size`, `tts.length_scale`, `runtime.max_turns`, `runtime.half_duplex`, `logging.level`. Do **not** document every key — point at `config.yaml`, which is commented. Add short "How to change the voice" and "How to add a trigger" recipes.

### 8. Measured performance

Paste the real table from `logs/benchmark.md`. One sentence: *"These numbers are from <CPU model>, <RAM>. Your machine will differ."*

### 9. Known limitations (be blunt)

- 3–6 s per turn; not suitable for real-time conversation
- No streaming STT/TTS — she waits, thinks, then speaks
- No barge-in: you cannot interrupt her
- ~15 hand-written triggers; anything else gets a fallback
- No memory between runs, no learning
- English-only by default
- No singing, music, games, Discord/Twitch, avatar, or emotions
- Single-threaded, blocking loop
- Laptop speakers can cause feedback; use headphones

### 10. Troubleshooting — at least these rows, each with a FIX

| Symptom | Fix |
|---------|-----|
| `check_env.py` fails on PortAudio | Reinstall `sounddevice`; confirm venv |
| No device / `PaErrorCode -9996` | `python main.py --list-devices`; set `audio.input_device` to a name substring |
| She never hears me | Lower `vad.energy_threshold_db` (e.g. `-50`), check Windows mic level, `python vad.py --test` |
| She hears herself | Headphones; ensure `runtime.half_duplex: true` |
| Transcription wrong | Try `stt.model_size: base.en` (2× slower, more accurate) |
| Speech too fast | `tts.length_scale: 1.15` |
| First reply takes 10 s | Model load; warm afterwards. `python stt_engine.py --warmup` |
| Piper writes 0-byte file | `python scripts/download_models.py --piper --force` |
| `ModuleNotFoundError` | Activate venv: `python -c "import sys; print(sys.prefix)"` |
| Memory grows over hours | Restart; `logs/hideko.log` shows RSS every 20 turns |

### 11. Architecture

The plan's ASCII diagram (mic → VAD → STT → matcher → TTS → speaker) plus a file map:

```
main.py              loop, half-duplex, CLI wiring
cli.py               argument parsing, status lines, key handling
config.py            typed config loader
audio_manager.py     devices, Microphone, Speaker
vad.py               energy VAD + utterance recorder
stt_engine.py        faster-whisper wrapper
tts_engine.py        Piper wrapper + cache
response_handler.py  matching, fallbacks, conversation state
responses/*.yaml     trigger database
scripts/             download, check, validate, benchmark, soak
tests/               offline unit tests
```

### 12. Development

```powershell
python -m pytest -q
$env:HIDEKO_E2E="1"; python -m pytest -q; Remove-Item Env:HIDEKO_E2E
python scripts\benchmark.py
python scripts\validate_responses.py
```

### 13. Credits & licences

- faster-whisper (MIT), Whisper models (MIT, OpenAI)
- Piper (MIT) and the `en_US-amy-medium` voice — **check the voice's model card licence** and name it explicitly; do not claim MIT if it is not
- No affiliation with Neuro-sama or Vedal

## 2. Rules checklist

- [ ] A person with no context can install and talk to Hideko using only the README
- [ ] Every command works verbatim; every file path mentioned exists
- [ ] All measured numbers come from `logs/benchmark.md`, not the plan's estimates
- [ ] Limitations section blunt and complete; every troubleshooting row has a fix
- [ ] No claim the MVP cannot back up (no LLM, no cloud, no memory, no real-time)
- [ ] No mention of internal task numbers or `tasks/`
- [ ] No badges, logo, roadmap, screenshots, or GIFs

## 3. Honesty check

Grep the README for `real-time`, `fast`, `instant`, `AI`, `GPT`, `neural network`. Every occurrence must be qualified or removed. Also verify every flag mentioned is in `python main.py --help`.

## 4. Verify — run and paste output

Follow your own README on a clean shell, in order, without skipping. Paste the console output of the install + first-conversation steps.

```powershell
python -m pytest -q
python scripts\validate_responses.py
python scripts\check_env.py
python main.py --text "hello" --no-tts
```
All must succeed. Link check every path; flag check every flag.

## 5. Report

Report: files changed, pasted verification output, anything unfinished. This is the last task.
