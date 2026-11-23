# Task 05 — Config/docs & final verification

**Wrap-up. Depends on tasks 01–04. Touch at most 4 files. No behaviour changes.**

## Goal

Bring the documentation in line with the KoboldCpp architecture and run the full verification suite. **Do not change application behaviour here** — if you find a bug, report it.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- `llm.enabled` must remain `false` in `config.yaml`.
- Be honest: KoboldCpp must be started by the user; no LLM results should be claimed unless you actually observed them.
- KoboldCpp is **AGPL-3.0**; state that, and state that this project is not shipped so the licence is acceptable here.
- Do not resume the old CUDA debug task; mark it superseded.

## Steps

### 1. `README.md`

Update these sections (keep the existing structure):

- **Status / at-a-glance**: change the `LLM fallback` row to `KoboldCpp over loopback HTTP, optional, hybrid persona (conversational turns only)`; change `GPU` row to `not required for core features; KoboldCpp decides GPU use`.
- **Requirements**: remove the `llama-cpp-python` / CUDA wheel notes; add `Optional: KoboldCpp.exe started by you before enabling llm.enabled (AGPL-3.0), plus an already-downloaded GGUF model`.
- **Install**: replace the `pip install -r requirements.txt --extra-index-url .../whl/cpu` line with plain `python -m pip install -r requirements.txt` (the dependency is gone). Add after the model download step:
  ```powershell
  # Optional: start KoboldCpp yourself, then leave it running
  .\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048
  ```
  Mention `koboldcpp-nocuda.exe`, `--noavx2`, and the `oldpc` build as fallbacks (from task 01).
- **Configuration**: replace `llm.model_path` / `llm.n_gpu_layers` rows with `llm.base_url` (`http://127.0.0.1:5001`), `llm.endpoint` (`/v1/chat/completions`), `llm.model` (`local`), `llm.persona_file` (`persona/hideko.yaml`), and keep `llm.enabled`, `max_tokens`, `timeout_s`, `temperature`.
- **How to add a trigger**: mention `llm_only: true` makes a trigger conversational (LLM-written), while omitting it keeps canned replies.
- **Architecture**: add `persona/hideko.yaml`, `tools/koboldcpp/` (external, gitignored), and note `llm_fallback.py` is now an HTTP client, not an in-process model loader.
- **Known limitations**: add `LLM replies require the user to start KoboldCpp first; without it Hideko falls back to canned/YAML replies`; `loopback HTTP only — no cloud`; `KoboldCpp is AGPL-3.0 (fine for a personal, non-shipped project)`; remove all previous `CUDA wheel / llama-cpp-python` limitations.
- **Troubleshooting**: add `KoboldCpp API FAILED in check_env.py` → start KoboldCpp on port 5001 and check `config.yaml` `llm.base_url`; remove the `llama_cpp fails` row.
- **Credits & licences**: replace the `llama-cpp-python (MIT)` line with `KoboldCpp (AGPL-3.0), used locally and not shipped`; keep both Qwen model licences as Apache-2.0 and the Piper voice line unchanged.

Do not invent latency numbers. Keep the "no target set" note.

### 2. `plan.md`

Append a new section after "Post-MVP improvement phase" (do not rewrite existing sections):

```
## KoboldCpp backend phase

### Decisions
- Replaced the in-process llama-cpp-python backend with a loopback HTTP client (http://127.0.0.1:5001/v1).
- KoboldCpp is started manually by the user; Hideko degrades to canned responses when it is unreachable.
- Hybrid persona: llm_only triggers and unmatched input get LLM-written replies; commands/goodbye/help/facts stay canned.
- Persona lives in persona/hideko.yaml; memory stays in memory/facts.json and is injected into prompts.
- Personal, non-shipped project: AGPL-3.0 dependency acceptable; no packaging work.
- The earlier CUDA wheel debugging (debug-tasks/01) is superseded, kept as history only.
```

Add a short list of what changed per task 01–05 and a `Still out of scope` line identical to the previous one (games, streaming, barge-in, Discord, avatar, music, LLM on every turn).

### 3. `improvement-tasks/README.md`

In the "Post-review corrections" section, add a single line at the end:
```
Superseded: the in-process LLM path described above has been replaced by the KoboldCpp HTTP backend. See kobold-tasks/README.md. debug-tasks/01 remains as historical context only.
```
Do not rewrite the rest of that file.

### 4. `kobold-tasks/README.md`

Append a `## Status` section with: which tasks were completed, the exact KoboldCpp launch command that worked, whether a real HTTP generation was observed, and any remaining limitations. Mark each task row in the graph as done if verification passed.

## Verification

Run with **no** KoboldCpp server unless the user explicitly has one running:

```powershell
python -m pytest -q
python config.py --check
python scripts\check_env.py
python scripts\validate_responses.py
python main.py --text "hello" --no-tts
python main.py --text "tell me a joke" --no-tts
python main.py --text "goodbye" --no-tts
python main.py --facts
python -m pip show llama-cpp-python
```

Expected:

- `pytest` — all pass.
- `config.py --check` — `llm.enabled: false`, no `model_path`/`n_gpu_layers`/`context_window` keys, `persona_file` present and absolute.
- `check_env.py` — `KoboldCpp API  -   disabled (llm.enabled: false)` and all required checks pass.
- `validate_responses.py` — exits 0, reports `OK: 15 triggers`.
- The three `--text` commands produce canned replies (no server needed) and no connection errors.
- `--facts` prints `(no facts)` or existing user facts (do not clear them without asking).
- `pip show llama-cpp-python` — not found.
- No `config_llm_smoke.yaml` or other temp config left behind.

If KoboldCpp **is** running, additionally use a temp config with `llm.enabled: true` and confirm a real persona-styled reply for `hello`, then delete the temp config.

## Stop and ask the human if

- You cannot verify a real HTTP generation and the docs would otherwise imply it works — mark it as unverified instead.
- You find an application bug during this pass — report it; do not fix it here.
- The licence note feels legally significant — say "KoboldCpp is AGPL-3.0; this project is not distributed", nothing stronger.
