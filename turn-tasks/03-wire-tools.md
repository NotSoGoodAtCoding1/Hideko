# Task 03 — Wire tools into turn flow

**Depends on task 02. Touch at most 4 files.** Do not touch `events.py`, `event_outputs.py`, `turn_state.py`, `stt_engine.py`, `tts_engine.py`, `vad.py`, `audio_manager.py`, `memory_store.py`, `llm_fallback.py`, or `config.yaml`.

## Goal

Wire the tool registry and scheduler into the turn loop so a matched trigger can execute a tool after speaking its response. `Response` gains an optional `tool_action` field; triggers can declare `tool: <name>`. No actual tools are registered yet — that is task 04. Without a registered tool, behavior is unchanged.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No new dependencies. `tools.registry` and `tools.scheduler` from task 02.
- `python -m pytest -q` passes offline with no mic/server.
- CLI output byte-for-byte identical when no tool_action is set.
- Type hints + docstrings. No bare `except:`.

## Current state you will modify

`response_handler.py`:
- `Response` dataclass (line 22): `text, trigger, is_fallback, should_exit`.
- `Trigger` dataclass (around line 45): `name, priority, patterns, responses, should_exit, llm_only`.
- `load()` reads trigger fields around line 129–191.
- `respond()` returns `Response(...)` at line 340–345.

`main.py`:
- `HidekoApp.__init__` (line 26), `setup()` (line 45), `run()` (line 112), `shutdown()` (line 238), `main()` (line 276).
- `main()` creates `bus` and `console` at line 287–289.

## Steps

### 1. `response_handler.py` — Response + Trigger + tool field

Add `tool: str | None = None` to `Trigger`:
```python
@dataclass(frozen=True)
class Trigger:
    name: str
    priority: int
    patterns: tuple[str, ...]
    responses: tuple[str, ...]
    should_exit: bool = False
    llm_only: bool = False
    tool: str | None = None
```

In `load()`, after `llm_only = ...`, read the tool key:
```python
            tool = trigger_raw.get("tool")
            if tool is not None and not isinstance(tool, str):
                raise ResponseDataError(
                    f"Trigger '{name}' tool must be a string, got {type(tool).__name__}"
                )
```

Pass into `Trigger(...)`:
```python
            trigger = Trigger(
                name=name,
                priority=priority,
                patterns=tuple(patterns_raw),
                responses=tuple(responses_raw),
                should_exit=should_exit,
                llm_only=llm_only,
                tool=tool,
            )
```

Add `tool_action: str | None = None` to `Response`:
```python
@dataclass(frozen=True)
class Response:
    """A line for Hideko to speak."""
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False
    tool_action: str | None = None
```

In `respond()`, after the best match is selected and **before** the anti-repeat / response-selection block, set `tool_action` on the response that will be returned. The cleanest place: after `best_match = max(...)`, capture `tool_action = trigger.tool`. Then when constructing the final `Response(...)` at line 340, add `tool_action=tool_action`.

Also, in `_try_llm()`, the returned `Response` gets `tool_action=None` (LLM doesn't call tools in v1) — already the case since it's not passed.

Implementation detail: track `tool_action` through the selection:
```python
        # Pick the best match by score key (max)
        best_match = max(matches, key=lambda x: x[2])
        trigger, pattern, _ = best_match
        tool_action = trigger.tool        # <-- add

        logger.debug(...)

        # Hybrid persona...
        if trigger.llm_only:
            llm_response = self._try_llm(text, intent=trigger.name)
            if llm_response is not None:
                return llm_response
```

Then in the final `Response(...)` construction (line 340):
```python
        return Response(
            text=chosen,
            trigger=trigger.name,
            is_fallback=False,
            should_exit=trigger.should_exit,
            tool_action=tool_action,      # <-- add
        )
```

### 2. `main.py` — imports, registry, scheduler, tool execution

**Imports** (add after existing imports):
```python
import threading

from turn_state import TurnController, TurnState
from tools.registry import ToolRegistry
from tools.scheduler import Scheduler
```
`TurnController`/`TurnState` are from task 01; add them if not already present.

**`main()`** — after `scheduler` creation... Actually `main()` currently creates `bus` and `console`. Add registry + scheduler and start the scheduler:
```python
    opts = parse_args(argv)

    # Set up event bus and console subscriber for all output
    bus = EventBus()
    console = ConsoleSubscriber(Status())
    bus.subscribe(ALL, console.handle)

    # Tool registry and background scheduler
    registry = ToolRegistry()
    scheduler = Scheduler(bus)
    scheduler.start()
```

**`HidekoApp.__init__`** — add parameters and fields:
```python
    def __init__(
        self,
        config: AppConfig,
        opts: CliOptions,
        bus: EventBus | None = None,
        status: Status | None = None,
        turn: TurnController | None = None,
        registry: ToolRegistry | None = None,
        scheduler: Scheduler | None = None,
    ) -> None:
        self.config = config
        self.opts = opts
        self.bus = bus if bus is not None else EventBus()
        self.status = status if status is not None else Status()
        self.keys = KeyListener()
        self.turn = turn if turn is not None else TurnController(self.bus)
        self.registry = registry if registry is not None else ToolRegistry()
        self.scheduler = scheduler if scheduler is not None else Scheduler(self.bus)
        self._closed = False
        self._paused = False
        self._listening_shown = False
        self._wake_word_detected = False
        self._wake_word_timeout = 0.0
        self._pending_speech: list[str] = []
        self._speech_lock = threading.Lock()
```

**`HidekoApp.setup()`** — after `self.bus.publish("ready", ...)`:
```python
        self.turn.transition(TurnState.IDLE)
        self.scheduler.start()  # idempotent; main() already started it
```

**`HidekoApp.run()`** — changes:

(a) After the `if self._paused: ... continue` block and **before** `block = self.mic.read_block()`, add pending-speech delivery:
```python
                # Speak any pending tool results (e.g. timer finished) before listening.
                # NOTE: mic.read_block() blocks, so pending speech is delivered on
                # the next audio block. Timer speech may be delayed until the user
                # speaks again — acceptable for v1.
                with self._speech_lock:
                    pending = list(self._pending_speech)
                    self._pending_speech.clear()
                if pending and not self.turn.is_speaking():
                    self.turn.transition(TurnState.SPEAKING)
                    for text in pending:
                        self.bus.publish("speaking", text=text)
                        clip = self.tts.synthesize(text)
                        self.speaker.play(clip.samples, clip.sample_rate)
                    self.turn.transition(TurnState.IDLE)
```

(b) Wake word section — add state transitions:
- Not a wake word: add `self.turn.transition(TurnState.WAITING_FOR_WAKE_WORD)` before `continue`.
- Wake word detected: after `self.bus.publish("wake_detected", ...)`, add `self.turn.transition(TurnState.LISTENING)`.

(c) First-listening guard — add state transition (keep existing print guard for output identity):
```python
                if not self._listening_shown:
                    self.bus.publish("listening")
                    self._listening_shown = True
                self.turn.transition(TurnState.LISTENING)
```

(d) Thinking — after `self.bus.publish("thinking")`:
```python
                self.turn.transition(TurnState.THINKING)
```

(e) Speaking branches — after each `self.bus.publish("speaking", ...)`:
```python
                    self.turn.transition(TurnState.SPEAKING)
```

(f) After turn_timing publish and logging, add tool execution before `should_exit` check? No — should_exit should break first. Add **after** the `should_exit` break-check and **before** `turn += 1`:
```python
                if response.should_exit:
                    self.bus.publish("goodbye")
                    self.turn.transition(TurnState.IDLE)
                    break

                # Execute tool action if the matched trigger requested one
                if response.tool_action:
                    result = self.registry.execute(
                        response.tool_action,
                        text=transcript.text,
                        response_text=response.text,
                    )
                    if result.ok and result.text:
                        with self._speech_lock:
                            self._pending_speech.append(result.text)
                    elif not result.ok:
                        logger.warning(
                            "tool %s failed: %s", response.tool_action, result.error
                        )

                turn += 1
```

(g) `shutdown()` — stop scheduler:
```python
    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.bus.publish("shutdown")
        if self.scheduler is not None:
            self.scheduler.stop()
        ...
```

(h) `main()` — pass registry and scheduler to HidekoApp:
```python
    app = HidekoApp(config, opts, bus=bus, registry=registry, scheduler=scheduler)
```

### 3. Tests — add to `tests/test_smoke.py`

- `test_tool_action_unknown_tool_returns_error` — monkeypatch `main.ToolRegistry.execute` to return `ToolResult(ok=False, error="unknown")`; call `main(["--text", "hello", "--no-tts"])` with a trigger that has `tool_action`. Simpler: directly construct `ResponseHandler` with a trigger that has `tool="no_such_tool"` and assert `response.tool_action == "no_such_tool"`. Then call `registry.execute("no_such_tool")` and assert `ok=False`.
- `test_pending_speech_delivered` — construct `HidekoApp` with a real registry/scheduler, append to `app._pending_speech`, monkeypatch `app.tts` and `app.speaker` to fakes, call the pending-speech block logic... This is fiddly. Alternative: unit-test `TurnController` + `Scheduler` + `Registry` in `tests/test_tools.py` (task 02 already covers them). For smoke, just assert `main(["--text", "hello", "--no-tts"])` still returns 0 and output unchanged (existing test covers this).

Keep smoke tests minimal: existing 4 tests + assert registry is wired:
- `test_app_has_registry_and_scheduler` — construct `HidekoApp(load_config(), parse_args([]), bus=bus)`; assert `app.registry is not None` and `app.scheduler is not None`.

## Verification

```powershell
python -m pytest -q
python main.py --text "hello" --no-tts
python main.py --text "goodbye" --no-tts
python scripts\event_probe.py
```

Expected:

- All tests pass.
- `--text "hello"` → `Hideko: ...` exactly as before (no tool configured, no tool_action).
- `--text "goodbye"` → farewell exactly as before.
- `event_probe.py` output unchanged from task 02.

## Stop and ask the human if

- `Response` being `frozen=True` makes adding `tool_action` awkward for your style — it's fine with a default; keep it.
- You want tool execution to happen before TTS instead of after — speak after is safer (user hears response first). Keep after.
- You want pending speech to interrupt TTS — explicitly out of scope for v1.
