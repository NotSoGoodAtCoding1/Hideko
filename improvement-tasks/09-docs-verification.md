# Task 09 — Docs & final verification

**Wrap-up. Depends on tasks 01–08. Touch at most 4 files. No behaviour changes.**

## Goal

Update `README.md` and `plan.md` so they honestly describe the improved project, and run the full verification suite. Record observed timings; **do not** add a latency pass/fail target.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No code behaviour changes in this task. If you find a bug, report it — do not fix it here.
- Be honest: mark anything untested or unavailable as such. Do not invent numbers or licences.

## Inputs you must read first

- `logs/benchmark.md` — the real numbers produced in task 03.
- `logs/soak.md` — note its RSS values are still `0.0 MB`; do not present them as proof of memory stability.
- Your final reports from tasks 04–08 (model licence, installed `llama-cpp-python` version, whether the real GGUF generation was exercised, whether Python was changed).
- `config.yaml` — the final key set.

## Steps

### 1. `README.md`

Update these sections (keep the existing structure and tone):

- **Status / at-a-glance** — add rows for `Memory` (`local JSON facts, learned from explicit phrases`) and `LLM fallback` (`llama-cpp-python, optional, only when no trigger matches`). Change the latency row to `observed; no target set for this sprint` and reference `logs/benchmark.md`.
- **Requirements** — GPU is now **optional but recommended for the LLM**; add that `llama-cpp-python` is a heavy dependency; keep the Python 3.11 note and add `3.12 only if the llama-cpp wheel requires it and ctranslate2 still works`.
- **Install** — add an optional step after `download_models.py --all`:
  ```powershell
  python scripts\download_models.py --llm
  ```
  with one sentence: only needed if you enable `llm.enabled`, and the model is ~400+ MB.
- **Controls** — add `--facts` (print remembered facts) and `--forget` (delete them).
- **Configuration** — add rows for `vad.silence_ms` (now `450`), `vad.post_playback_flush_ms` (now `150`), `stt.cpu_threads` (`null` = half the logical cores), `memory.enabled`, `memory.file`, `llm.enabled` (default `false`), `llm.model_path`, `llm.n_gpu_layers` (`-1` = offload all layers if a CUDA build is available), and `llm.max_tokens`.
- **Measured performance** — replace `n/a` cells with the real figures from `logs/benchmark.md`; add a sentence: `No latency pass/fail target was set for this sprint; verdicts are informational.` If a row is still `n/a`, leave it `n/a` and say why.
- **Known limitations** — add: the LLM only runs on unmatched input and is slower than a YAML reply; the bundled 0.5B model gives simple answers; fact extraction understands only a fixed set of phrases; GPU offload needs a CUDA-enabled `llama-cpp-python` build.
- **Troubleshooting** — add rows for: `LLM error: model not found` → run `download_models.py --llm`; `import llama_cpp fails` → reinstall pinned `llama-cpp-python` wheel; `facts file corrupt` → Hideko starts empty; run `python main.py --forget`.
- **Architecture** — add `memory_store.py`, `llm_fallback.py`, `memory/facts.json`, `models/llm/`.
- **Development** — add `python main.py --facts`, `python memory_store.py --facts`, and the optional LLM verification command.
- **Credits & licences** — record: `llama-cpp-python` (MIT); the exact GGUF model and its licence **as determined in task 06** (do not guess); note that the `en_US-amy-medium` Piper voice details are unchanged from the MVP line. If the licence was not determined, write `licence not verified — check the model card` and say so in your report.

Keep the transcript example and the existing `hello` / `tell me a joke` / `goodbye` examples accurate.

### 2. `plan.md`

Append a new section at the end titled `## Post-MVP improvement phase`:

- State the locked decisions in a short bullet list: cheap latency wins, no latency target; disk facts; local LLM fallback only via `llama-cpp-python`; Windows-only; offline at runtime; GPU/heavy deps allowed; Python 3.11 with a conditional 3.12 path.
- List what changed by phase: A (VAD/flush timings, `stt.cpu_threads`, timing visibility), B (`MemoryStore`, `--facts`/`--forget`, name-aware greetings), C (`llm_fallback.py`, fallback-only wiring, GGUF downloader).
- Add an explicit `Still out of scope` line: games, streaming STT/TTS, barge-in, Discord/Twitch, avatar, music generation, LLM on every turn.
- Link `improvement-tasks/README.md`.
- Do not rewrite the MVP sections above it.

### 3. `logs/benchmark.md` and `logs/soak.md`

- Do not fabricate data. If task 03 produced real numbers, leave `benchmark.md` as generated. If it is still all `n/a`, append a note: `Benchmark not completed in this sprint — models or time unavailable.`
- In `soak.md`, append one line: `Note: RSS readings in this run are 0.0 MB, so they do not prove memory stability. Re-run with a longer soak before relying on this result.` Do not change the PASS/FAIL line.

### 4. Final verification

Run and paste real output:

```powershell
python -m pytest -q
python config.py --check
python scripts/check_env.py
python scripts/validate_responses.py
python scripts/benchmark.py --repeat 3
python main.py --facts
python main.py --text "hello" --no-tts
python main.py --text "my name is Ada" --no-tts
python main.py --facts
python main.py --text "hello" --no-tts
python main.py --forget
python main.py --facts
```

Expected:

- `pytest` — all pass.
- `config.py --check` — no error; JSON includes `vad.silence_ms = 450`, `stt.cpu_threads`, `memory`, and `llm` sections.
- `check_env.py` — all required checks OK, `LLM (disabled)` skipped.
- `validate_responses.py` — exits 0.
- `benchmark.py` — produces `logs/benchmark.md` with real STT/TTS numbers if models are present; exit code 0 or 1 only from a real budget breach, which you must report verbatim.
- `--facts` starts `(no facts)`; after `"my name is Ada"` it shows `name: Ada`; the following `hello` says `Hello Ada. I am Hideko.`; `--forget` clears it and final `--facts` is `(no facts)`.
- Leave the workspace clean: no temporary config with `llm.enabled: true`, no leftover `.tmp` memory file, no untracked test audio.

## Stop and ask the human if

- The real benchmark breaches a budget by >150% — report the numbers and ask whether to retune or accept.
- The model licence could not be determined — ask rather than writing a guess.
- Python was changed to 3.12 in task 06 — ask for confirmation before finalising the README requirement line.
