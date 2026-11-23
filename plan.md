# Hideko MVP Plan

## Overview
A minimal Neuro-sama clone with voice interaction capabilities, running fully locally. This is a proof-of-concept focusing on core TTS/STT functionality and basic conversational responses.

**Implementation:** this plan is broken into 24 self-contained tasks in [`tasks/`](tasks/README.md). Start at [`tasks/README.md`](tasks/README.md).

---

## Core Features (MVP Only)

### 1. Voice Input & Output
- **Speech-to-Text**: Capture microphone input and convert to text
- **Text-to-Speech**: Convert generated responses back to audio
- **Voice Activity Detection**: Detect when the user starts and stops speaking
- **Half-duplex**: Discard microphone input while speaking so the assistant does not transcribe itself

### 2. Basic Conversation Loop
- User speaks → STT converts to text
- System processes text (simple keyword/phrase matching)
- Generate response
- TTS converts response to audio
- Play audio through speakers

### 3. Minimal Personality
- Pre-defined responses for common triggers (e.g., "sing", "dance", "hello")
- Basic fallback responses for unrecognized input
- No complex personality system yet

---

## Technical Reality Check: Latency & Constraints

### Expected Latencies (Local Hardware)
| Operation | Estimated Time | Notes |
|-----------|---------------|-------|
| Microphone capture start | 100-300ms | OS + audio driver overhead |
| Utterance end detection | 700-800ms | Trailing-silence timeout in the VAD |
| STT processing (5 sec utterance) | 1.5-3 seconds | faster-whisper tiny.en, int8, 4-core CPU |
| Response generation (simple) | 1-20ms | Keyword matching is fast |
| TTS processing (10 word response) | 0.5-1.5 seconds | Piper, including ~200ms process spawn |
| Audio playback start | 100-200ms | Buffering required |
| **Total Round Trip** | **3-6 seconds** | Ceiling for MVP acceptance: 10 seconds |

### Hardware Requirements (Minimum)
- CPU: 4+ cores, 3.0GHz+
- RAM: 8GB minimum (16GB recommended)
- Storage: 5GB free space (models themselves are ~160MB)
- Audio: Working microphone + speakers/headphones
- **GPU NOT required** for MVP (STT/TTS/triggers are CPU-based); the optional LLM fallback supports NVIDIA CUDA offload (verified on an RTX 3060)
- Python 3.11.x (3.12+ lacks reliable binary wheels for CTranslate2)

### Known Limitations (MVP Scope)
- ❌ No real-time interaction (noticeable delays)
- ❌ No streaming STT/TTS (must wait for full utterance)
- ❌ No barge-in (cannot interrupt speech)
- ❌ No background processing (single-threaded audio loop)
- ❌ English only by default
- ❌ No music/singing generation
- ❌ No game integration
- ❌ No Discord/external API connections
- ❌ No persistent memory or learning

---

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Microphone    │────▶│  Speech-to-Text  │────▶│   Text          │
│   (Audio Input) │     │  (STT Engine)    │     │   Processor     │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
        ▲                                                 │
        │                                                 ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Audio Output   │◀────│  Text-to-Speech   │◀────│   Response      │
│  (Speakers)     │     │  (TTS Engine)    │     │   Generator     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

VAD sits between the microphone and STT: it decides where an utterance starts and ends.

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal**: Get basic audio loop working with no intelligence

- [ ] Set up project scaffold, venv, and pinned dependencies
- [ ] Download and verify Piper + faster-whisper models
- [ ] Implement typed configuration loader (`config.yaml`)
- [ ] Set up audio capture pipeline (device selection, 16 kHz mono)
- [ ] Implement energy-based VAD and utterance recording
- [ ] Implement STT with faster-whisper (tiny.en, int8, CPU)
- [ ] Implement TTS with Piper (`en_US-amy-medium`)
- [ ] Create basic audio playback system
- [ ] Wire the loop with half-duplex (flush mic input while speaking)
- [ ] Test end-to-end: speak → hear an echo of what you said

**Success Criteria**: Say "hello" and hear "I heard you say: hello" within 10 seconds

---

### Phase 2: Basic Intelligence (Week 2)
**Goal**: Add simple conversational logic

- [ ] Implement keyword/phrase matching system (word-boundary literal matching)
- [ ] Create response database for common triggers (YAML, validated by a script)
- [ ] Add fallback responses for unknown input
- [ ] Implement basic conversation state (greeting, goodbye)
- [ ] Test with varied inputs

**Success Criteria**: Recognizes "hello", "sing", "dance" and responds appropriately

---

### Phase 3: Polish & Optimization (Week 3)
**Goal**: Improve user experience within constraints

- [ ] Add visual feedback (status lines: listening / thinking / speaking, plus per-stage timing)
- [ ] Add a mute key (keyboard) since there is no GUI
- [ ] Add simple error handling (mic not found, no audio output, missing models) with typed errors and exit codes
- [ ] Extend the configuration file (volume, sensitivity, model paths, turn limit)
- [ ] Add unit tests, a benchmark, and a soak test
- [ ] Document known limitations clearly

**Success Criteria**: Feels usable despite delays; clear documentation of what works/doesn't

---

## Model Selection Strategy

### Speech-to-Text
- **Chosen**: faster-whisper `tiny.en` (CTranslate2, `int8`, CPU)
- **Why**: same Whisper models at ~4x the CPU speed of `openai-whisper`, roughly half the RAM, no PyTorch dependency
- **Upgrade path**: `base.en` via `stt.model_size` (more accurate, ~2x slower)
- **Not used**: `openai-whisper` (too slow on CPU), Vosk (noticeably less accurate)

### Text-to-Speech
- **Chosen**: Piper (`piper.exe` + `en_US-amy-medium` voice)
- **Why**: fully offline, one binary plus one voice file, no Python build dependencies, ~1s per sentence on CPU
- **Not used**: Coqui TTS (project unmaintained since 2024, requires Python <3.12, painful Windows build), Edge-TTS (a cloud service, contradicts the local-only requirement)

All models are fetched once by `scripts/download_models.py`. There is no network access at runtime.

---

## File Structure (MVP)

```
hideko/                      # repository root
├── main.py                  # Entry point, audio loop orchestration
├── cli.py                   # Argument parsing, status lines, mute key
├── config.py                # Typed config loader
├── config.yaml              # Configuration (models, paths, thresholds)
├── audio_manager.py         # Microphone/speaker management
├── vad.py                   # Energy VAD + utterance recorder
├── stt_engine.py            # Speech-to-text wrapper (faster-whisper)
├── tts_engine.py            # Text-to-speech wrapper (Piper)
├── response_handler.py      # Keyword matching & response generation
├── errors.py                # Exception hierarchy + exit codes
├── logging_setup.py         # Console + rotating file logging
├── responses/               # Response database
│   ├── triggers.yaml
│   └── fallbacks.yaml
├── models/                  # Downloaded, gitignored
│   ├── piper/               # piper.exe + en_US-amy-medium.onnx(.json)
│   └── whisper/             # faster-whisper tiny.en
├── scripts/
│   ├── download_models.py
│   ├── check_env.py
│   ├── validate_responses.py
│   ├── benchmark.py
│   └── soak_test.py
├── tests/                   # Offline unit tests + gated e2e
├── logs/                    # Runtime logs (gitignored)
├── tasks/                   # Task breakdown for implementation
├── requirements.txt
├── README.md
└── plan.md
```

---

## Testing Strategy

### Unit Tests
- STT engine: Verify filtering of silence, hallucinations, and short input (models mocked)
- TTS engine: Verify cache, truncation, and error paths (subprocess mocked)
- Response handler: Verify word-boundary matching, priority, fallbacks, anti-repeat
- VAD: Verify utterance boundaries on synthetic audio
- Config: Verify validation and path resolution

### Integration Tests
- Full loop test: Speak phrase → verify response plays (gated behind `HIDEKO_E2E=1`)
- CLI contract: `--help`, `--list-devices`, `--text`, bad config exit codes
- Error handling: Test with no mic, no speakers, invalid config

### Performance Benchmarks
- Measure STT latency on 5-second utterances
- Measure TTS generation time for various lengths
- Run a soak test and track RSS growth
- Document minimum hardware requirements based on testing

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| STT too slow | Poor user experience | faster-whisper tiny.en + int8, warm the model at startup, document latency expectations |
| TTS quality poor | Annoying audio output | Piper medium voice; voice is swappable via one config path |
| Audio conflicts | Mic/speaker feedback | Half-duplex with input flush, mute key, headphones recommended in README |
| Memory issues | App crashes on long sessions | Log RSS every 20 turns, cap the TTS cache, document manual restart |
| Model downloads fail | Can't start app | Dedicated download script with size checks, `check_env.py` preflight, actionable errors |

---

## Success Metrics (MVP)

1. **Functional**: Complete audio loop works end-to-end
2. **Latency**: Total response time under 10 seconds for typical utterances
3. **Reliability**: No crashes during 30-minute continuous use
4. **Usability**: Clear instructions, easy setup (< 15 minutes)
5. **Documentation**: Honest about limitations, no false promises

---

## What's NOT in Scope (Explicitly Out of MVP)

- ❌ Singing/music generation
- ❌ Real-time streaming audio
- ❌ Barge-in / interrupt while speaking
- ❌ Background operation
- ❌ Discord/Twitch integration
- ❌ Game logic or mini-games
- ❌ Persistent memory/learning
- ❌ Multiple voices or character switching
- ❌ Visual avatar/animations
- ❌ Complex personality/emotions
- ❌ LLM-based dialogue
- ❌ External APIs or cloud services (including cloud TTS)

---

## Next Steps After MVP

Once core loop is stable, consider:
1. Streaming STT/TTS for reduced latency
2. Simple music generation (pre-recorded clips)
3. Basic game integration (simple clicker/choice games)
4. Discord bot wrapper
5. Avatar/animations (separate project)

---

## Timeline Summary

| Week | Focus | Deliverable |
|------|-------|-------------|
| 1 | Audio pipeline | Speak → hear response (dumb echo) |
| 2 | Basic intelligence | Recognize commands, respond appropriately |
| 3 | Polish & docs | Usable MVP with clear limitations documented |

**Total**: 3 weeks for functional MVP

Task-level breakdown (what to build, in what order, with verification steps): [`tasks/README.md`](tasks/README.md).

---

## Final Reality Check

This is a **proof of concept**, not a production-ready chatbot. Expect:
- Noticeable delays (3-6 seconds per interaction, 10 second ceiling)
- Occasional transcription errors
- Limited vocabulary and responses
- No "personality" beyond keyword matching
- Single-threaded, blocking audio processing

**But**: It will demonstrate that local-only voice interaction is possible with open-source tools, which is the MVP goal.

---

## Post-MVP improvement phase

### Locked decisions

- **Latency philosophy**: cheap latency wins; no latency pass/fail target set for this sprint (verdicts are informational only)
- **Memory**: disk-based JSON facts (`memory/facts.json`), learned from explicit phrases like "my name is Ada"
- **LLM fallback**: optional local LLM via `llama-cpp-python`, runs only when no YAML trigger matches, graceful degradation on errors
- **Platform**: Windows-only for now (Linux/macOS untested)
- **Offline at runtime**: no network access during conversation
- **Heavy deps allowed**: GPU offload and large models permitted if user enables them
- **Python version**: 3.11.x default; 3.12 only if `llama-cpp-python` wheel requires it and `ctranslate2` still works

### What changed by phase

**Phase A (VAD/flush timings, `stt.cpu_threads`, timing visibility)**
- Added `vad.silence_ms: 450` and `vad.post_playback_flush_ms: 150` for faster response times
- Added `stt.cpu_threads` config (null = half logical cores)
- Made per-stage timing visible in CLI output

**Phase B (`MemoryStore`, `--facts`/`--forget`, name-aware greetings)**
- Implemented `memory_store.py` with JSON persistence and eviction policy
- Added `--facts` and `--forget` CLI flags for debugging
- Greetings now use remembered name when available

**Phase C (`llm_fallback.py`, fallback-only wiring, GGUF downloader)**
- Created `llm_fallback.py` with graceful error handling
- Wired LLM to run only when no trigger matches (invariant)
- Empty/hallucinated input never reaches LLM
- Added `scripts/download_models.py --llm` for the default model and `--llm-coder` for the larger one

### Model choices and licences

- **Default**: `Qwen2.5-0.5B-Instruct-GGUF`, `q4_k_m` (~0.5 GB) — fast, general-purpose chat
- **Optional**: `Qwen2.5-Coder-7B-Instruct-GGUF`, `q4_k_m` (~4.4 GB) — code-tuned. **Verified on GPU** on 2026-11-23: 4,168 MiB weights + 56 MiB KV + 304 MiB compute (~4.5 GB VRAM), ~48 tok/s, coherent code answers. Too slow on CPU for a voice turn.
- Both are **Apache-2.0**, verified from their Hugging Face model cards (the earlier claim that this had been verified during task 06 was incorrect; it was verified during post-review correction)
- `llm.max_tokens` is 80 and `llm.n_gpu_layers` defaults to `-1` (offload all layers; the CPU wheel ignores it)
- Verified setups:
  - CPU: `llama-cpp-python==0.3.36` from `https://abetlen.github.io/llama-cpp-python/whl/cpu` — 0.5B at ~85 tok/s
  - GPU: `llama-cpp-python==0.3.36` from `https://abetlen.github.io/llama-cpp-python/whl/cu125`, `nvidia-cuda-runtime-cu12==12.5.82`, `nvidia-cublas-cu12==12.5.3.2`, plus the CPU wheel's `ggml-cpu.dll` (see `scripts/setup_llama_cuda.py`) — 0.5B at ~264 tok/s
  - The stock CUDA wheel's `ggml-cpu.dll` is compiled with AVX-512 and faults with `0xc000001d` on CPUs without AVX-512 (e.g. Ryzen 5 5600); swapping in the same-release CPU build of that one DLL fixes it
- Real generation was confirmed end-to-end: `what is the capital of France` → `France's capital is Paris. ...` with the LLM enabled, on both CPU and GPU

### Still out of scope

- Games, streaming STT/TTS, barge-in, Discord/Twitch, avatar, music generation, LLM on every turn

---

## KoboldCpp backend phase

### Decisions
- Replaced the in-process llama-cpp-python backend with a loopback HTTP client (http://127.0.0.1:5001/v1).
- KoboldCpp is started manually by the user; Hideko degrades to canned responses when it is unreachable.
- Hybrid persona: llm_only triggers and unmatched input get LLM-written replies; commands/goodbye/help/facts stay canned.
- Persona lives in persona/hideko.yaml; memory stays in memory/facts.json and is injected into prompts.
- Personal, non-shipped project: AGPL-3.0 dependency acceptable; no packaging work.
- The earlier CUDA wheel debugging (debug-tasks/01) is superseded, kept as history only.

### What changed by task
- **01 — KoboldCpp server & character card**: added `persona/hideko.yaml` and a local `tools/koboldcpp/` workflow for running KoboldCpp manually; no in-process model loading.
- **02 — HTTP backend + config**: replaced the llama-cpp backend with `KoboldHttpBackend`/loopback HTTP config (`base_url`, `endpoint`, `model`, `persona_file`), removed the in-process dependency path, and updated config/env checks.
- **03 — Trigger intent tags**: added `Trigger.llm_only` and tagged triggers so conversational intents can be routed to the LLM while commands/facts stay canned.
- **04 — Hybrid routing**: `ResponseHandler` routes `llm_only` matches and unmatched input through the LLM with canned/YAML fallback on any `LLMError`; command/goodbye/help/fact triggers remain canned.
- **05 — Config/docs & final verification**: aligned docs with the KoboldCpp architecture and recorded verification results.

### Still out of scope

- Games, streaming STT/TTS, barge-in, Discord, avatar, music generation, LLM on every turn

---

## Next Steps After MVP

Once core loop is stable, consider:
1. Streaming STT/TTS for reduced latency
2. Simple music generation (pre-recorded clips)
3. Basic game integration (simple clicker/choice games)
4. Discord bot wrapper
5. Avatar/animations (separate project)

---

## Timeline Summary

| Week | Focus | Deliverable |
|------|-------|-------------|
| 1 | Audio pipeline | Speak → hear response (dumb echo) |
| 2 | Basic intelligence | Recognize commands, respond appropriately |
| 3 | Polish & docs | Usable MVP with clear limitations documented |

**Total**: 3 weeks for functional MVP

Task-level breakdown (what to build, in what order, with verification steps): [`tasks/README.md`](tasks/README.md).

---

## Improvement Tasks

See [`improvement-tasks/README.md`](improvement-tasks/README.md) for the next phase of enhancements.
