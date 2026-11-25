# Hideko — a local, offline voice assistant

Speak into your microphone; she answers out loud. Everything runs locally: no cloud, no API keys. STT, TTS and trigger matching run on CPU; the optional LLM persona uses a local KoboldCpp server you start yourself. An optional PySide6 desktop window (`--gui`) can run alongside the console.

**Not real-time.** Each turn takes 3–6 seconds. English only by default. Persistent memory via `memory/facts.json`. Optional local LLM fallback when no trigger matches, plus an optional wake-word gate (`hideko` / `hey hideko`).

---

## Status / at-a-glance

| | |
|---|---|
| STT | faster-whisper `tiny.en`, int8, CPU |
| TTS | Piper `en_US-amy-medium`, CPU |
| Conversation | 16 keyword/phrase triggers in `responses/triggers.yaml` |
| Memory | local JSON facts, learned from explicit phrases (`my name is Ada`) |
| LLM fallback | KoboldCpp over loopback HTTP; enabled in `config.yaml`; hybrid persona (conversational turns only) |
| Wake word | optional transcript gate (`hideko`, `hey hideko`); disabled by default |
| GUI | optional PySide6 6.7 desktop window: conversation, status/timing, VU meter + waveform, mute, tray |
| Event bus | thread-safe pub/sub; console and GUI subscribers; avatar contract in [`docs/avatar-events.md`](docs/avatar-events.md) |
| Turn state machine | idle / listening / thinking / speaking / paused / waiting_for_wake_word |
| Tool registry | registry + background scheduler; `set_timer` tool available |
| Network at runtime | none (loopback to a user-started local KoboldCpp process when LLM is enabled) |
| GPU | not required for core features; KoboldCpp decides GPU use |
| Measured turn latency | **observed; no target set for this sprint** (see [`logs/benchmark.md`](logs/benchmark.md)) |
| Tested on | Windows 11, Python 3.11, 12 logical cores, 16 GB RAM |
| Test suite | 194 passed, 9 skipped on the reference machine (E2E and one manual GUI test are skipped by default) |

---

## Requirements

- Windows 10/11 (Linux/macOS likely work; untested — say so)
- Python **3.11.x** (3.12+ unsupported; one line why: binary wheels for `ctranslate2`)
- 4+ cores, 8 GB RAM minimum, 16 GB recommended
- 5 GB free disk (core models ≈ 160 MB; optional GGUF model for KoboldCpp ≈ 0.5 GB; PySide6 ≈ 0.3 GB if you install the GUI; rest is venv headroom)
- Working microphone + speakers/headphones
- **Headphones strongly recommended** — see feedback loop in Troubleshooting
- **No GPU required** for core features. STT, TTS and trigger matching run on CPU. If you enable the optional LLM, KoboldCpp decides GPU use.
- Optional: `KoboldCpp.exe` started by you before using `llm.enabled` (AGPL-3.0), plus an already-downloaded GGUF model.
- Optional: PySide6 6.7.0 (LGPL) for the desktop GUI, installed from `requirements-gui.txt`.

---

## Install

```powershell
cd hideko
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# Optional: desktop GUI
python -m pip install -r requirements-gui.txt
python scripts\download_models.py --all
# Optional: download a GGUF model for KoboldCpp (only needed if you use `llm.enabled`)
python scripts\download_models.py --llm
# Optional: start KoboldCpp yourself, then leave it running
.\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048
python scripts\check_env.py
python main.py            # console
# or
python main.py --gui      # console + desktop window
```

If the CUDA build does not start on your machine, try `.\tools\koboldcpp\koboldcpp-nocuda.exe` with the same model/port arguments. If your CPU lacks AVX2, try `--noavx2`; on very old PCs, use the KoboldCpp `oldpc` build.

`config.yaml` currently ships with `llm.enabled: true`. Either start KoboldCpp before launching Hideko, or set `llm.enabled: false` to run without it. Without a reachable server, Hideko logs the failure and falls back to canned/YAML replies; `check_env.py` will report the KoboldCpp check as `FAILED`.

Expected `check_env.py` output with `llm.enabled: false`:

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

Start KoboldCpp before launching Hideko:

```powershell
.\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048
```

Fallbacks if that build does not work on your machine: `koboldcpp-nocuda.exe` (same args, no CUDA), add `--noavx2` for CPUs without AVX2, or use the KoboldCpp `oldpc` build for very old PCs.

How routing works: triggers with `llm_only: true` (greeting, joke, compliment, etc.) are written by the LLM when it is available, with their YAML responses as fallback. Unmatched input also tries the LLM. Commands, goodbye, help and facts stay canned (`llm_only: false`).

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

The same turn appears in the desktop window when you launch with `--gui`.

**Things to say:** `hello`, `tell me a joke`, `can you sing`, `what is your name`, `help`, `goodbye`, `set a timer for 2 minutes`.

---

## Controls

| Key / flag | Effect |
|------------|--------|
| `m` / `--mute-key KEY` | mute / unmute the microphone (CLI; use `--mute-key none` to disable) |
| `q` | quit (CLI) |
| `Ctrl+C` | quit |
| `--gui` | launch the optional PySide6 desktop window alongside the console |
| `--text "..."` | one-shot without the mic |
| `--text "set a timer for 2 minutes"` | test timer tool without mic |
| `--no-tts` | print replies without audio |
| `--no-greet` | skip the startup greeting |
| `--list-devices` | show audio devices |
| `--calibrate` | run VAD calibration, print the threshold, exit |
| `--turns N` | stop after N exchanges |
| `--debug` | verbose logging |
| `--log-file PATH` | override `logging.file` for this run |
| `--config PATH` | use a different config file |
| `--facts` | print remembered facts |
| `--forget` | delete all remembered facts |

The GUI adds a Mute button, a Listen button (placeholder), and a tray menu with Show / Hide / Mute / Quit.

---

## Configuration

Key settings you might change (see `config.yaml` for full details):

| Key | Default | What it does |
|-----|---------|--------------|
| `audio.input_device` | null | Microphone name substring or index; null = default |
| `audio.output_device` | null | Speaker name substring or index; null = default |
| `audio.playback_volume` | 1.0 | Volume 0.0–1.5 (values >1.0 may clip) |
| `vad.energy_threshold_db` | -40.0 | Sensitivity: lower = more sensitive (e.g. -50); ignored when `calibrate: true` |
| `vad.calibrate` | true | Measure ambient noise at startup |
| `vad.calibration_ms` | 1000 | Calibration duration |
| `vad.silence_ms` | 450 | Trailing silence that ends an utterance (lower = faster turns, but cuts off pauses) |
| `vad.min_speech_ms` | 200 | Speech needed before an utterance starts |
| `vad.max_utterance_s` | 15 | Hard cap; longer speech is truncated and processed |
| `vad.pre_roll_ms` | 300 | Audio kept before speech onset (avoids a clipped first syllable) |
| `vad.post_playback_flush_ms` | 150 | Discard audio after playback to avoid transcribing our own voice (lower = faster response) |
| `stt.model_size` | tiny.en | Model: `tiny.en` (fast) or `base.en` (2× slower, more accurate) |
| `stt.beam_size` | 1 | 1 = greedy/fastest; 5 = slightly better, ~2× slower |
| `stt.cpu_threads` | null | CPU threads for STT; null = half of logical cores |
| `stt.min_avg_logprob` | -1.0 | Segments below this are treated as noise |
| `stt.max_audio_s` | 30 | Refuse longer input instead of silently truncating |
| `tts.length_scale` | 1.0 | Speech speed: >1.0 = slower, <1.0 = faster |
| `tts.max_chars` | 300 | Longer text is truncated before synthesis |
| `memory.enabled` | true | Enable persistent memory via JSON file |
| `memory.file` | memory/facts.json | Path to facts file (relative to config.yaml) |
| `memory.max_facts` | 100 | Oldest facts are evicted first |
| `memory.max_value_chars` | 120 | Cap each stored value |
| `llm.enabled` | true in `config.yaml` (code default false) | Enable optional LLM persona (KoboldCpp must already be running on loopback) |
| `llm.base_url` | `http://127.0.0.1:5001` | KoboldCpp loopback base URL |
| `llm.endpoint` | `/v1/chat/completions` | OpenAI-compatible chat endpoint |
| `llm.model` | `qwen2.5-0.5b-instruct-q4_k_m.gguf` | Model name sent to the API |
| `llm.persona_file` | `persona/hideko.yaml` | Persona/character card read into the system prompt |
| `llm.temperature` | 0.7 | Creativity: 0.0 = deterministic, 2.0 = creative |
| `llm.max_tokens` | 80 | Maximum LLM response length (keep small — long replies time out) |
| `llm.timeout_s` | 15 | HTTP timeout for LLM requests |
| `wake_word.enabled` | false | Gate commands behind a wake phrase |
| `wake_word.phrases` | `hideko`, `hey hideko` | Case-insensitive phrases checked against the transcript |
| `wake_word.listen_mode_timeout_s` | 10.0 | Seconds to stay in listen mode after a wake word |
| `wake_word.threshold_db` | -35.0 | Validated config value; not used by the current transcript-based detector |
| `wake_word.min_wake_duration_ms` | 800 | Validated config value; not used by the current transcript-based detector |
| `runtime.max_turns` | 0 | Unlimited; set to N to stop after N exchanges |
| `runtime.half_duplex` | true | Discard mic input while speaking (prevents feedback) |
| `runtime.greet_on_start` | true | Speak the startup greeting |
| `runtime.log_transcripts` | true | false = never write recognized text to the log file |
| `runtime.echo_mode` | false | true = skip response matching and echo the transcript |
| `logging.level` | INFO | DEBUG, INFO, WARNING, ERROR |
| `logging.file` | logs/hideko.log | Log file path |

**How to change the voice:** Edit `config.yaml`, set `audio.output_device` to your speaker name or index from `--list-devices`.

**How to enable wake word:** Set `wake_word.enabled: true`. Hideko transcribes each utterance and only enters command mode when the transcript contains one of `wake_word.phrases`; it stays in listen mode for `listen_mode_timeout_s`. This is transcript-based, not a dedicated wake-word model, so every utterance still costs an STT pass.

**How to add a trigger:** Edit `responses/triggers.yaml`. Add a new trigger block with `name`, `priority`, `patterns` (list of phrases), and `responses` (list of replies). Set `llm_only: true` to make a matched trigger conversational (LLM-written, with canned responses as fallback); omit it or set `false` to keep canned replies.

**How to add a tool:** Create a class subclassing `Tool` in `tools/`, implement `execute(**kwargs)`, register it with the `ToolRegistry`, and wire it via a YAML trigger's `tool:` key (e.g., `set_timer` has `tool: set_timer`). The `tool:` key invokes the tool after the trigger's response is spoken; tools can schedule background actions and queue speech.

**Trigger example:** The `set_timer` trigger uses `tool: set_timer`. When you say "set a timer for 5 minutes", the response handler matches the trigger, speaks "I will set the timer.", then executes `set_timer` with `text="set a timer for 5 minutes"`. The tool parses the duration, schedules a background job via `Scheduler`, and when the timer fires it publishes `timer_finished` and queues speech.

---

## Desktop GUI (optional)

```powershell
python -m pip install -r requirements-gui.txt
python main.py --gui
```

The window shows the conversation transcript, status and timing, listening/speaking indicators, a VU meter and waveform, a Mute button, and a system tray icon with Show / Hide / Mute / Quit. It subscribes to the same event bus as the console, so both outputs stay in sync.

Implementation notes:

- The GUI is optional. If PySide6 is missing or launch fails, Hideko logs a warning and continues with the CLI.
- Qt runs in the same process and thread as the audio loop. `main.py` pumps Qt events with `processEvents()` around blocking operations (mic reads, STT, TTS, playback), so there is no separate Qt thread. Long native calls can still briefly stall repainting.
- `gui/settings_panel.py` contains Audio / VAD / Model / Appearance tabs and a `SettingsDialog`, but it is not wired into the main window yet. The Listen button is also a placeholder; the Mute button and tray work.

---

## Event bus and extensibility

`events.py` provides a thread-safe `EventBus` with wildcard subscriptions and per-handler error isolation. `event_outputs.py` contains the console subscriber; `gui/event_handler.py` bridges the same events to Qt widgets. Event kinds include `startup`, `calibrating`, `ready`, `listening`, `paused`, `wake_detected`, `thinking`, `heard`, `speaking`, `turn_timing`, `missed`, `error`, `goodbye`, `shutdown`, plus `turn_state_changed` from `TurnController`.

Subscribe to everything:

```python
from events import ALL, EventBus

bus = EventBus()
bus.subscribe(ALL, my_handler)
```

Handlers must be fast and non-blocking; a failing handler is logged and skipped, never propagated. The full payload contract, state mapping and threading rules are in [`docs/avatar-events.md`](docs/avatar-events.md).

---

## Measured performance

From [`logs/benchmark.md`](logs/benchmark.md) (2026-11-22, 12 logical cores, Python 3.11.9, `tiny.en` int8, `en_US-amy-medium.onnx`):

| Metric | median | max | budget | verdict |
|--------|--------|-----|--------|---------|
| STT cold (load + 5 s) | 22.48 s | 22.48 s | - | - |
| STT warm (5 s audio) | 0.26 s | 0.31 s | 3.0 s | PASS |
| STT on 10 s audio | 0.38 s | 0.56 s | 6.0 s | PASS |
| TTS cold | 0.76 s | 0.76 s | - | - |
| TTS warm (10 words) | 0.54 s | 0.54 s | 1.5 s | PASS |
| TTS cached | 0.55 s | 0.55 s | - | - |
| Response matching | 0.0 ms | 0.1 ms | 20 ms | PASS |
| Text turn end-to-end | 0.00 s | 0.45 s | 10 s | PASS |

*No latency pass/fail target was set for this sprint; verdicts are informational.* The cold STT number is model load on this machine; warm turns are what you see during a session. Your machine will differ.

---

## Known limitations

- 3–6 s per turn; not suitable for real-time conversation
- No streaming STT/TTS — she waits, thinks, then speaks
- No barge-in: you cannot interrupt her
- 16 hand-written triggers; anything else gets a fallback (or optional LLM if enabled)
- Persistent memory via JSON file; fact extraction understands only a fixed set of phrases
- English-only by default
- LLM replies require the user to start KoboldCpp first; `config.yaml` enables the LLM by default, so set `llm.enabled: false` if you do not want it
- Loopback HTTP only — no cloud
- KoboldCpp is AGPL-3.0 (fine for a personal, non-shipped project)
- Single-threaded audio loop; the tool scheduler and LLM client use background threads
- Laptop speakers can cause feedback; use headphones
- **Timer speech**: the timer fires on a background thread, but speech is delivered on the next user utterance because `mic.read_block()` blocks in the audio loop
- **Tools**: only `set_timer` is built in; add tools by subclassing `Tool`, implementing `execute()`, and registering with `ToolRegistry`
- **Tool invocation**: tools are invoked by a YAML trigger's `tool:` key, not by LLM tool-calling
- **GUI**: optional and basic — conversation/status/indicators/VU/waveform/mute/tray work; the settings dialog is not wired in and the Listen button is a placeholder
- **Wake word**: transcript-substring detection, not a dedicated wake-word model; `threshold_db` and `min_wake_duration_ms` are validated but not enforced by the current detector
- **Events**: subscribers run synchronously in the publisher's thread and must return quickly; there are no barge-in/cancel events yet

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `check_env.py` fails on PortAudio | Reinstall `sounddevice`; confirm venv is activated |
| No device / `PaErrorCode -9996` | Run `python main.py --list-devices`; set `audio.input_device` to a name substring in `config.yaml` |
| She never hears me | Lower `vad.energy_threshold_db` (e.g. `-50`), check Windows mic level, run `python main.py --calibrate` or `python vad.py --test` |
| She hears herself | Use headphones; ensure `runtime.half_duplex: true` in `config.yaml` |
| Transcription wrong | Try `stt.model_size: base.en` (2× slower, more accurate) |
| Speech too fast | Set `tts.length_scale: 1.15` in `config.yaml` |
| First reply takes ~20 s | STT model load; warm afterwards. Run `python stt_engine.py --warmup` |
| Piper writes 0-byte file | Re-download: `python scripts\download_models.py --piper --force` |
| `ModuleNotFoundError` | Activate venv: `.\.venv\Scripts\Activate.ps1`, then run again |
| `--gui` warns "GUI not available" | Install the optional dependency: `python -m pip install -r requirements-gui.txt` |
| GUI opens empty or shows "Not responding" | Make sure you launched through `main.py`; long native calls can still stall repaint. Check `logs/hideko.log` for GUI errors |
| KoboldCpp API FAILED in `check_env.py` | Start KoboldCpp on port 5001 and check `llm.base_url`, or set `llm.enabled: false` |
| LLM reply falls back to canned/YAML | Confirm KoboldCpp is running, `llm.enabled: true`, and `llm.base_url` points to loopback |
| Wake word never triggers | Set `wake_word.enabled: true`, use one of `wake_word.phrases`, and check the transcript in the log; detection depends on STT accuracy |
| facts file corrupt | Hideko starts empty; run `python main.py --forget` to clear |
| Memory grows over hours | Restart; `logs/hideko.log` shows RSS every 20 turns |
| `Tool %s failed` | Check `logs/hideko.log` for the full stack trace |
| unknown tool error | The `tool:` key in `triggers.yaml` must match a registered tool name (e.g., `set_timer`) |

---

## Architecture

```
main.py              loop, half-duplex, CLI wiring, Qt event pumping
cli.py               argument parsing, status lines, key handling
config.py            typed config loader
events.py            thread-safe event bus (wildcard + error isolation)
event_outputs.py     console subscriber for bus events
turn_state.py        TurnController / TurnState; publishes turn_state_changed
audio_manager.py     devices, Microphone, Speaker
vad.py               energy VAD + utterance recorder
stt_engine.py        faster-whisper wrapper
tts_engine.py        Piper wrapper + cache
response_handler.py  matching, fallbacks, conversation state
memory_store.py      persistent JSON fact storage
llm_fallback.py      loopback HTTP client for KoboldCpp (not an in-process model loader)
persona/hideko.yaml  persona/character card sent as the system prompt
responses/*.yaml     trigger database + fallbacks
tools/registry.py    named tool registry; thread-safe, returns ToolResult
tools/scheduler.py   background delayed-callback scheduler daemon thread
tools/timer_tool.py  set_timer: parses duration, schedules fire, publishes timer_finished + queues speech
gui/__init__.py      launch_gui(); returns None when PySide6 is unavailable
gui/app.py           GUIApp: Qt app lifecycle, tray, window, event wiring
gui/main_window.py   conversation display, status bar, indicators, controls
gui/event_handler.py event bus -> Qt bridge
gui/audio_viz.py     VU meters + waveform display
gui/tray.py          system tray icon and menu
gui/styles.py        colors, fonts, spacing, stylesheet
gui/settings_panel.py settings tabs/dialog (not wired into the window yet)
docs/avatar-events.md event contract for avatar/UI subscribers
docs/gui-framework-decision.md PySide6 decision record
models/              downloaded models (gitignored)
  ├── whisper/       faster-whisper tiny.en
  ├── piper/         piper.exe + en_US-amy-medium.onnx
  └── llm/           optional GGUF model used by KoboldCpp
tools/koboldcpp/     local KoboldCpp binaries (external, gitignored)
scripts/             download, check, validate, benchmark, soak, event/avatar probes, CUDA setup
tests/               offline unit tests (GUI tests skip when PySide6 is absent)
memory/facts.json    persistent facts file (created on first run)
logs/                hideko.log, benchmark.md, soak.md (gitignored)
```

---

## Development

```powershell
python -m pytest -q
$env:HIDEKO_E2E="1"; python -m pytest -q; Remove-Item Env:HIDEKO_E2E
python scripts\benchmark.py
python scripts\validate_responses.py
python scripts\check_env.py
python scripts\soak_test.py --minutes 5
python scripts\event_probe.py
python scripts\avatar_probe.py
python main.py --gui
# Check facts persistence
python main.py --facts
python main.py --text "my name is Ada" --no-tts
python main.py --facts
python main.py --forget
python main.py --facts
# Optional LLM verification (requires KoboldCpp running and llm.enabled: true in config)
python llm_fallback.py --text "hello there" --config config.yaml
```

On the reference machine the offline suite currently reports 194 passed, 9 skipped. The skipped tests are 8 audio/end-to-end tests that need real hardware and `HIDEKO_E2E=1`, plus one manual GUI verification test.

---

## Credits & licences

- faster-whisper (MIT), Whisper models (MIT, OpenAI)
- Piper (MIT) and the `en_US-amy-medium` voice — **Piper 1.0 compatible revision e7229f7d33a10e145e109b886d661984201ac3c4**
- KoboldCpp (AGPL-3.0), used locally and not shipped
- Qwen2.5-0.5B-Instruct GGUF model — **Apache-2.0** (verified from the Hugging Face model card)
- Qwen2.5-Coder-7B-Instruct GGUF model (optional) — **Apache-2.0** (verified from the Hugging Face model card)
- PySide6 / Qt for Python (LGPL), optional desktop GUI
- NumPy (BSD), sounddevice (MIT), soundfile (BSD), PyYAML (MIT)
- No affiliation with Neuro-sama or Vedal
