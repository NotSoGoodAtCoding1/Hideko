# Hideko — Turn State Machine & Tool Registry task set

This folder contains **6 small, self-contained tasks** for the next architecture phase. Give a local agent **exactly one task file** and nothing else. Every rule, contract, code skeleton, and verification command is inlined in that file.

> Scope: turn state machine, tool registry + background scheduler, and a real timer tool to test the infrastructure. No avatar UI, no wake-word changes, no streaming. This increment must leave CLI output byte-for-byte identical when no tools are configured, and keep all tests green.

---

## Why this phase

`main.py::run()` is now ~120 lines of inline loop logic with state tracked across scattered booleans (`_paused`, `_listening_shown`, `_wake_word_detected`). Tools like timers need (a) a stable state to hook into and (b) a background scheduler that can fire while the voice loop is blocked on `mic.read_block()` or `speaker.play()`. This phase adds both seams.

This is **not** a rewrite. We extract state into a `TurnController`, add a `tools/` package, then wire them into the existing loop one call at a time.

---

## Task graph

| # | Task | Depends on | Files produced / touched |
|---|------|-----------|--------------------------|
| 00 | [Checkpoint & hygiene](00-checkpoint.md) | — | commit, `.gitignore`, scratch cleanup |
| 01 | [Turn state machine](01-turn-state-machine.md) | 00 | `turn_state.py`, `tests/test_turn_state.py` |
| 02 | [Tool registry & scheduler](02-tool-registry-scheduler.md) | 01 | `tools/registry.py`, `tools/scheduler.py`, `tests/test_tools.py` |
| 03 | [Wire tools into turn flow](03-wire-tools.md) | 02 | `main.py`, `response.py` (tool_action field), `responses/triggers.yaml` |
| 04 | [Timer tool + tests](04-timer-tool.md) | 03 | `tools/timer_tool.py`, `tests/test_timer_tool.py`, triggers YAML |
| 05 | [Docs & final verification](05-docs-verification.md) | all | `README.md`, `plan.md`, full suite |

Tasks 01 → 02 → 03 must be done in order. Task 04 depends on 03. Task 05 wraps up.

---

## Frozen contracts

```python
# turn_state.py   (new, task 01)
from enum import Enum
class TurnState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PAUSED = "paused"
    WAITING_FOR_WAKE_WORD = "waiting_for_wake_word"

class TurnController:
    def __init__(self, bus: EventBus) -> None: ...
    @property
    def state(self) -> TurnState: ...
    def transition(self, new_state: TurnState, **event_data: Any) -> None: ...
    def is_speaking(self) -> bool: ...
    def is_listening(self) -> bool: ...
```
`transition()` publishes a `turn_state_changed` event with `from`, `to`, and any extra `event_data`.

```python
# tools/registry.py   (new, task 02)
class ToolResult:
    ok: bool
    text: str | None          # text to speak, if any
    error: str | None
class Tool:
    name: str
    def execute(self, **kwargs) -> ToolResult: ...
class ToolRegistry:
    def register(self, tool: Tool) -> None: ...
    def get(self, name: str) -> Tool | None: ...
    def execute(self, name: str, **kwargs) -> ToolResult: ...

# tools/scheduler.py   (new, task 02)
class Scheduler:
    def __init__(self, bus: EventBus) -> None: ...
    def start(self) -> None: ...              # starts background thread
    def stop(self) -> None: ...               # stops thread, waits
    def schedule(self, callback: Callable[[], None], delay_seconds: float) -> str: ...  # returns job id
    def cancel(self, job_id: str) -> bool: ...
    def pending(self) -> list[str]: ...       # job ids not yet fired
```

```python
# response_handler.py — Response gains one field (task 03)
@dataclass(frozen=True)
class Response:
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False
    tool_action: str | None = None        # NEW: name of tool to execute after speaking
```

`ResponseHandler.respond()` is frozen. Triggers may carry a `tool:` key (task 04 adds examples).

---

## Ground rules for every agent

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj` (now a git repo).
- `python -m pytest -q` must pass offline with **no** mic, speakers, or KoboldCpp server.
- No `print()` in library code outside `if __name__ == "__main__":`. Use `logging.getLogger(__name__)`.
- Type hints + docstrings on all public classes/functions. No bare `except:`, no `except Exception: pass` — log the exception instead.
- `Scheduler` callbacks must never crash the background thread: wrap callback body in try/except, log, continue.
- Do not modify `events.py`, `event_outputs.py`, `stt_engine.py`, `tts_engine.py`, `vad.py`, `audio_manager.py`, `memory_store.py`, `llm_fallback.py`, `config.py`, or `errors.py` in this task set.
- Importing `tools.scheduler` must never start a thread. Threads start only on `Scheduler.start()`.
- Do not commit without explicit human approval (task 00 explains).

---

## Explicitly out of scope in this set

- Avatar rendering/GUI, wake-word optimization, barge-in/interrupt, tool-calling from the LLM (LLM still just returns text; tools are invoked by YAML trigger config), config schema versioning, and the `sys.exit()`-on-error fix. These are later phases.
