# Hideko — Event-bus refactor task set

This folder contains **5 small, self-contained tasks** for the first architecture refactor. Give a local agent **exactly one task file** and nothing else. Every rule, contract, code skeleton, and verification command is inlined in that file.

> Scope: **event bus + avatar readiness only.** No avatar UI, no tools, no timers, no wake-word changes. Those are later phases. This increment must leave the CLI output byte-for-byte identical and keep all tests green.

---

## Why this phase

`main.py::run()` currently does everything inline (mic → VAD → STT → responder → TTS → playback) and writes to the console through `Status`. There is no channel an avatar, GUI, or tool runner can observe. The first seam to add is an **event bus** so every other future feature can subscribe instead of editing `main.py`.

This is **not** a rewrite. We add a new module, add a thin console subscriber that reproduces today's output, then replace direct prints/status calls in `main.py` with `bus.publish(...)`.

---

## Task graph

| # | Task | Depends on | Files produced / touched |
|---|------|-----------|--------------------------|
| 00 | [Checkpoint & hygiene](00-checkpoint.md) | — | `scratch/`, optional commit |
| 01 | [Event bus core](01-event-bus.md) | 00 | `events.py`, `tests/test_events.py` |
| 02 | [Console & logging subscribers](02-output-subscribers.md) | 01 | `event_outputs.py`, `scripts/event_probe.py`, `tests/test_event_outputs.py` |
| 03 | [Wire the bus into main](03-wire-main.md) | 02 | `main.py`, `tests/test_smoke.py` |
| 04 | [Avatar event contract](04-avatar-contract.md) | 03 | `docs/avatar-events.md`, `scripts/avatar_probe.py` |

Task 03 is the risky one: it changes output plumbing. Verify CLI output before and after with the exact commands in the task.

**Known baseline issue (checked 2026-11-23):** `python -m pytest -q` currently has one failure — `tests/test_model_acquisition.py::test_no_audio_reports_warning_rows` — because `config.yaml` has `llm.enabled: true` and `check_env.py` now probes the KoboldCpp server. Task 00 fixes the test by monkeypatching that check; do not "fix" it by editing `config.yaml`.

---

## Frozen event contract (all tasks must match)

```python
# events.py
ALL = "*"

@dataclass(frozen=True)
class Event:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

class EventBus:
    def subscribe(self, kinds: str | Iterable[str], handler: Callable[[Event], None]) -> None: ...
    def unsubscribe(self, handler: Callable[[Event], None]) -> None: ...
    def publish(self, kind: str, **data: Any) -> None: ...
    def clear(self) -> None: ...  # tests only
```

Event kinds and exact payload keys:

| Kind | Payload | When |
|---|---|---|
| `startup` | `{}` | after logging setup in `HidekoApp.setup()` |
| `calibrating` | `{}` | before VAD calibration |
| `ready` | `{"stt_s": float, "trigger_count": int}` | after responder creation |
| `listening` | `{}` | when the `[listening]` line would be printed |
| `paused` | `{}` | mute toggled on |
| `wake_detected` | `{"text": str, "latency_s": float}` | wake-word phrase matched |
| `thinking` | `{}` | before STT of a real turn |
| `heard` | `{"text": str}` | transcript accepted |
| `speaking` | `{"text": str}` | about to print/synthesize a reply (also used by `--text`) |
| `missed` | `{}` | empty transcript |
| `turn_timing` | `{"stt": float, "resp": float, "tts": float, "play": float, "total": float}` | end of turn |
| `error` | `{"message": str, "exit_code": int}` | `HidekoError` caught |
| `goodbye` | `{}` | before the farewell line |
| `shutdown` | `{}` | in `HidekoApp.shutdown()` |

Unknown kinds must be ignored by subscribers, never raise.

---

## Ground rules for every agent

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj` (now a git repo).
- `python -m pytest -q` must pass offline with **no** mic, speakers, or KoboldCpp server.
- No `print()` in library code (`events.py`, `event_outputs.py`) outside `if __name__ == "__main__":`. Use `logging.getLogger(__name__)`. Scripts may print.
- Type hints + docstrings on all public classes/functions. No bare `except:`, no `except Exception: pass` — log the exception instead.
- **Event handlers must never crash the publisher**: `EventBus.publish` catches and logs handler exceptions, then continues to other handlers.
- Handlers must be fast and non-blocking; they will later run on timers/avatar threads. `EventBus` must be thread-safe (`threading.RLock`) and copy the subscriber list before iterating.
- Do not modify `response_handler.py`, `stt_engine.py`, `tts_engine.py`, `vad.py`, `audio_manager.py`, `memory_store.py`, `llm_fallback.py`, `config.py`, or `config.yaml` in this task set.
- Do not commit without explicit human approval (task 00 explains this).

---

## Explicitly out of scope in this set

- Avatar rendering/GUI, voice barge-in, wake-word optimisation (including the current double-transcription), tool registry, timers, scheduler thread, config schema versioning, and the `sys.exit()`-on-error fix in `main.py`. These are documented as later phases in `plan.md` by task 04 only as a note — do not implement them.

A green test suite **plus identical CLI output** is the definition of done for phase 1.
