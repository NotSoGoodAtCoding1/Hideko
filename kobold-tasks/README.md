# Hideko — KoboldCpp backend handoff

This folder turns the agreed architecture change into **5 small, self-contained tasks**. Give a local agent **exactly one task file** and nothing else. Every rule, contract, snippet, and verification command is inlined in that file.

> This is a **personal, non-shipped project**. We are deliberately relaxing the original "clean pip install / CPU-only / no external process" constraints to avoid the `llama-cpp-python` wheel and CUDA debugging. Loopback HTTP is allowed; cloud/network services are still not.

---

## Locked decisions (do not re-litigate)

| Topic | Decision |
|---|---|
| LLM backend | **KoboldCpp** running as a separate local process, OpenAI-compatible API at `http://127.0.0.1:5001/v1` |
| Who starts it | **The user**, manually. Hideko only connects; if unreachable, degrade to YAML replies. |
| LLM role | **Hybrid persona**: the LLM writes conversational replies; YAML triggers still own commands, goodbye, help, identity/facts triggers |
| Persona | A character card at `persona/hideko.yaml`, read by Hideko and sent as the system message; optionally imported into the KoboldCpp UI |
| Memory | Keep `MemoryStore` / `memory/facts.json`; facts are injected into the LLM system prompt; `--facts` / `--forget` stay |
| Default config | `llm.enabled: false`; hidden behind opt-in as before |
| Dependency | **Remove** `llama-cpp-python` from `requirements.txt`; no in-process model loading |
| Licence note | KoboldCpp is **AGPL-3.0**. Acceptable here because this project is not shipped; do not claim otherwise in docs. |
| Platform | Windows 10/11, PowerShell |

---

## Task graph

| # | Task | Depends on | Files produced / touched | Status |
|---|------|-----------|--------------------------|--------|
| 01 | [KoboldCpp server & character card](01-koboldcpp-server.md) | — | `tools/koboldcpp/`, `persona/hideko.yaml` | Done (artifacts present; live server not verified in this pass) |
| 02 | [HTTP backend + config](02-http-backend.md) | 01 | `llm_fallback.py`, `config.py`, `config.yaml`, `errors.py`, `requirements.txt`, `scripts/check_env.py`, `tests/test_llm_fallback.py`, `tests/conftest.py`, `tests/test_config.py` | Done (offline tests/config checks pass) |
| 03 | [Trigger intent tags](03-trigger-intents.md) | 02 | `response_handler.py`, `responses/triggers.yaml`, `scripts/validate_responses.py`, `tests/test_response_handler.py` | Done (`validate_responses.py` reports 15 triggers; tests pass) |
| 04 | [Hybrid routing](04-hybrid-routing.md) | 03 | `response_handler.py`, `tests/test_response_handler.py` | Done (response handler tests pass; CLI smoke checks pass) |
| 05 | [Config/docs/final verification](05-config-docs.md) | all | `README.md`, `plan.md`, `improvement-tasks/README.md`, `kobold-tasks/README.md` | Done (docs updated; offline verification recorded below) |

Order matters: 02 changes the backend contract that 03 and 04 rely on.

---

## Ground rules for every agent

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- `python -m pytest -q` must pass offline with **no** KoboldCpp server running. Tests must use fakes, never real HTTP.
- No `print()` in library code outside `if __name__ == "__main__":`. Use `logging.getLogger(__name__)`.
- Type hints + docstrings on public classes/functions. No bare `except:`, no `except Exception: pass`.
- Runtime makes **only loopback HTTP** requests; no cloud, no external hosts.
- When adding/removing a config key, update **all four** places: `config.yaml`, `_DEFAULTS`, both known-key sets in `config.py`, and `tests/conftest.py`.
- `ResponseHandler.respond(self, text: str) -> Response` is frozen. New parameters may be added to `__init__` as **optional keywords only**.

---

## Frozen contracts

```python
# response_handler.py — unchanged public signature
@dataclass(frozen=True)
class Response:
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False
class ResponseHandler:
    def respond(self, text: str) -> Response: ...

# memory_store.py — unchanged
class MemoryStore:
    def all(self) -> dict[str, str]: ...
    def get(self, key: str) -> str | None: ...
    def observe(self, text: str) -> list[Fact]: ...

# llm_fallback.py — NEW contract (task 02)
@dataclass(frozen=True)
class LLMReply:
    text: str
    latency_s: float
class LLMBackend:               # protocol-like base
    def available(self) -> bool: ...
    def generate(self, messages: list[dict[str, str]]) -> str: ...
class KoboldHttpBackend(LLMBackend): ...
class NullBackend(LLMBackend): ...
class LLMFallback:
    def __init__(self, config: AppConfig, memory: MemoryStore | None = None,
                 backend: LLMBackend | None = None) -> None: ...
    def available(self) -> bool: ...
    def respond(self, text: str, intent: str | None = None) -> LLMReply: ...

# response_handler.py — Trigger gains one optional field (task 03)
@dataclass(frozen=True)
class Trigger:
    name: str
    priority: int
    patterns: tuple[str, ...]
    responses: tuple[str, ...]
    should_exit: bool = False
    llm_only: bool = False        # NEW: route matched turns through the LLM
```

`LLMBackend.generate` changes from `prompt: str` to `messages: list[dict[str, str]]` — this is intentional so the persona/character can be a system message.

---

## Routing rules (frozen; implemented in task 04)

1. Empty / hallucinated input → YAML fallback, **never** the LLM.
2. Best matching trigger has `llm_only: true` and LLM available → LLM writes the reply, using the trigger name as `intent`; canned responses are the fallback if the LLM fails.
3. No trigger matched and LLM available → LLM writes the reply (`trigger="llm"`), YAML fallback if it fails.
4. `llm_only: false` triggers (commands, goodbye, help, identity/weather facts) always use canned responses — including `should_exit`.
5. On any LLM error, degrade to the existing YAML response; never raise to the user.

---

## Out of scope

Games, Discord, streaming STT/TTS, barge-in, avatar, music, LLM on every turn, shipping/packaging the project, fixing the old CUDA wheel path.

The old in-process CUDA work is recorded in `../debug-tasks/01-cuda-wheel-debug.md` and is superseded by this approach. Keep `debug-tasks/` as historical context; do not resume it.

## Status

### Tasks completed
- **01–04**: Implementation artifacts/tests present in the workspace; offline verification passed.
- **05**: Documentation updated and offline verification recorded in this pass.

### KoboldCpp launch command
- **Not verified in this pass** (no live KoboldCpp server was started/observed during task 05 verification). Documented/expected command from the project docs:
  ```powershell
  .\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048
  ```
- `tools/koboldcpp/koboldcpp.exe` and `tools/koboldcpp/koboldcpp-nocuda.exe` are present in the workspace; `persona/hideko.yaml` is present.

### Real HTTP generation observed
- **No.** No real KoboldCpp HTTP generation was observed during this task 05 verification pass. Checks were run with `llm.enabled: false` / no server dependency.

### Verification evidence (offline / no KoboldCpp server)
- `python -m pytest -q` — 139 passed, 8 skipped.
- `python config.py --check` — `llm.enabled: false`; LLM config exposes `base_url`, `endpoint`, `model`, `persona_file`; no `model_path`/`n_gpu_layers`/`context_window`.
- `python scripts\check_env.py` — required KoboldCpp/model/audio checks passed for this config; output included `KoboldCpp server     SKIPPED  LLM disabled in config`. Note: environment reported `numpy 1.x FAILED (got 2.4.6)` (pre-existing environment issue, not changed by this task).
- `python scripts\validate_responses.py` — `OK: 15 triggers, 53 patterns, 33 responses, 8 fallbacks`.
- `python main.py --text "hello" --no-tts` → canned/personalized greeting.
- `python main.py --text "tell me a joke" --no-tts` → canned joke reply.
- `python main.py --text "goodbye" --no-tts` → canned farewell.
- `python main.py --facts` → `name: Ada` (left unchanged).
- `python -m pip show llama-cpp-python` — package not found.
- No `config_llm_smoke.yaml` / temp smoke config files found.

### Remaining limitations
- LLM replies require the user to start KoboldCpp manually before enabling `llm.enabled`; without it, Hideko degrades to canned/YAML replies.
- Real end-to-end KoboldCpp HTTP generation is **not verified** in this pass; run a temp-config smoke test with a running KoboldCpp server to confirm.
- Loopback HTTP only — no cloud.
- KoboldCpp is AGPL-3.0; acceptable for this personal, non-shipped project.
