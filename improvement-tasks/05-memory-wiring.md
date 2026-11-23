# Task 05 — Memory wiring & CLI

**Phase B (memory). Depends on task 04. Touch at most 4 files.**

## Goal

Connect `MemoryStore` to the main loop and the responder so facts are learned from speech text and used in greetings. Add `--facts` and `--forget` CLI commands. **No LLM in this task.**

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- `Response.respond(text: str) -> Response` and all frozen contracts in `improvement-tasks/README.md` remain unchanged. `ResponseHandler.__init__` may gain **optional keyword arguments only**.
- Default behaviour with no memory (or no stored name) must stay byte-for-byte identical to today.
- No `print()` in library code. Tests offline: `python -m pytest -q`.

## Current state (exact)

`main.py` imports (lines 12–20) include:
```python
from response_handler import EchoResponder, ResponseHandler, Response
```
`HidekoApp.__init__` sets `self.stt`, `self.tts`, `self.speaker`, `self.mic`, `self.recorder`, `self.responder` to `None`.

`HidekoApp.setup()` responder choice (lines 74–80):
```python
        if self.config.runtime.echo_mode:
            self.responder = EchoResponder(self.config)
            logger.info("responder: EchoResponder (echo_mode)")
        else:
            self.responder = ResponseHandler(self.config)
            logger.info("responder: ResponseHandler (%d triggers)", self.responder.trigger_count)
```

`HidekoApp.run()` transcript handling (lines 121–133):
```python
                t0 = perf_counter()
                self.status.thinking()
                transcript = self.stt.transcribe(utterance, self.config.audio.sample_rate)
                t1 = perf_counter()
                if not transcript.text:
                    print("  (didn't catch that)")
                    self.recorder.reset()
                    continue

                self.status.heard(transcript.text)
                response = self.responder.respond(transcript.text)
                t2 = perf_counter()
```

`main()` `--text` branch (lines 223–239):
```python
    if opts.text is not None:
        try:
            # Choose responder based on echo_mode (task 11 logic)
            if config.runtime.echo_mode:
                responder = EchoResponder(config)
            else:
                responder = ResponseHandler(config)
            response = responder.respond(opts.text)
            print(f"Hideko: {response.text}")
            if not opts.no_tts:
                clip = TTSEngine(config).synthesize(response.text)
                Speaker(config).play(clip.samples, clip.sample_rate)
        except HidekoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return exc.exit_code
        return 0
```

`main()` early-exit flags: `--list-devices`, then config load, then `--calibrate`, then `--text`.

`cli.py`:
```python
@dataclasses.dataclass(frozen=True)
class CliOptions:
    config: Path
    text: str | None
    turns: int | None
    debug: bool
    no_tts: bool
    no_greet: bool
    list_devices: bool
    calibrate: bool
    log_file: Path | None
    mute_key: str
```
`parse_args()` constructs `CliOptions(...)` with all fields.

`response_handler.py`:
```python
    def __init__(self, config: AppConfig, rng: random.Random | None = None) -> None:
        self._config = config
        self._rng = rng if rng is not None else random.Random()
        ...
        self.load()
```
Inside `respond()`, after `best_match` is chosen:
```python
        trigger_name = trigger.name
        was_greeted = self.state.greeted
        was_goodbye = self.state.goodbye_seen

        if trigger_name == "greeting" and was_greeted:
            chosen = self._rng.choice(_STATE_LINES["greeting_again"])
        elif trigger_name == "goodbye" and was_goodbye:
            chosen = _STATE_LINES["after_goodbye"][0]
```

## Steps

### 1. `cli.py`

- Add `facts: bool` and `forget: bool` to `CliOptions`.
- Add parser arguments:
  ```python
      parser.add_argument("--facts", action="store_true", default=False,
                          help="Print remembered facts and exit")
      parser.add_argument("--forget", action="store_true", default=False,
                          help="Delete all remembered facts and exit")
  ```
- Pass `facts=args.facts, forget=args.forget` into `CliOptions(...)` in `parse_args()`.

### 2. `main.py`

- Import `MemoryStore` from `memory_store`.
- In `HidekoApp.__init__`, add `self.memory: MemoryStore | None = None` next to `self.responder`.
- In `HidekoApp.setup()`, after the `UtteranceRecorder` is created and before VAD calibration:
  ```python
          if self.config.memory.enabled:
              self.memory = MemoryStore(self.config)
              logger.info("memory: %d fact(s) loaded", len(self.memory.all()))
  ```
- Change the responder branch to pass memory:
  ```python
              self.responder = ResponseHandler(self.config, memory=self.memory)
  ```
- In `HidekoApp.run()`, after `self.status.heard(transcript.text)` and before `response = ...`:
  ```python
                  if self.memory is not None and self.memory.observe(transcript.text):
                      self.memory.save()
  ```
- In `main()`, immediately after config loading / `--turns` override and before `--calibrate`, add early exits:
  ```python
      if opts.facts:
          if not config.memory.enabled:
              print("(memory disabled)")
              return 0
          facts = MemoryStore(config).all()
          if facts:
              for key, value in sorted(facts.items()):
                  print(f"{key}: {value}")
          else:
              print("(no facts)")
          return 0

      if opts.forget:
          if not config.memory.enabled:
              print("(memory disabled)")
              return 0
          MemoryStore(config).clear()
          print("memory cleared")
          return 0
  ```
- In the `--text` branch, replace the responder construction with:
  ```python
              memory = MemoryStore(config) if config.memory.enabled else None
              if config.runtime.echo_mode:
                  responder = EchoResponder(config)
              else:
                  responder = ResponseHandler(config, memory=memory)
              if memory is not None and memory.observe(opts.text):
                  memory.save()
              response = responder.respond(opts.text)
  ```
  Keep the rest of the branch unchanged.

### 3. `response_handler.py`

- Import `MemoryStore` from `memory_store` (module-level import is safe: `memory_store` does not import `response_handler`).
- Change `__init__` to:
  ```python
      def __init__(
          self,
          config: AppConfig,
          rng: random.Random | None = None,
          memory: MemoryStore | None = None,
      ) -> None:
          self._config = config
          self._rng = rng if rng is not None else random.Random()
          self._memory = memory
          ...  # rest unchanged
  ```
  All existing calls `ResponseHandler(config)` keep working.
- In `respond()`, in the state-dependent override block, **before** the existing `if trigger_name == "greeting" and was_greeted:` line, insert:
  ```python
          if trigger_name == "greeting" and self._memory is not None:
              name = self._memory.get("name")
              if name:
                  chosen = (
                      f"Hello {name}. I am Hideko."
                      if not was_greeted
                      else f"Hello again, {name}."
                  )
  ```
  Then keep the existing `if/elif` unchanged — but change them to `elif` so they do not overwrite the name-aware line:
  ```python
          elif trigger_name == "greeting" and was_greeted:
              chosen = self._rng.choice(_STATE_LINES["greeting_again"])
          elif trigger_name == "goodbye" and was_goodbye:
              chosen = _STATE_LINES["after_goodbye"][0]
  ```
  With `self._memory is None` or no name stored, behaviour is exactly as before.

### 4. `tests/test_memory_wiring.py` — new file

Cover:
- `greeting_uses_name` — build `ResponseHandler(config, memory=fake)` where `fake.get("name")` returns `"Ada"`; assert `respond("hello").text == "Hello Ada. I am Hideko."` and a second greeting starts with `"Hello again, Ada."`.
- `greeting_without_memory_unchanged` — `ResponseHandler(config).respond("hello")` returns one of the original `_STATE_LINES`/trigger responses (assert it is in `trigger.responses`, do not assert a random exact string).
- `cli_flags_parse` — `parse_args(["--facts"]).facts is True`, `parse_args(["--forget"]).forget is True`.
- `text_branch_observes` — monkeypatch `main.MemoryStore` with a fake recording `observe` and `save` calls; call `main(["--text", "my name is Ada", "--no-tts"])`; assert exit code 0, `observe` called with `"my name is Ada"`, and `save` called once.
- `facts_and_forget_commands` — use a temp config (`--config` pointing at the fixture's config path) and assert `main(["--config", str(path), "--facts"])` prints `(no facts)` and returns 0, and `--forget` prints `memory cleared` and returns 0.

## Verification

```powershell
python -m pytest -q
python main.py --help
python main.py --facts
python main.py --text "my name is Ada" --no-tts
python main.py --facts
python main.py --text "hello" --no-tts
python main.py --forget
python main.py --facts
```

Expected:

- `pytest` — all pass.
- `--help` lists `--facts` and `--forget`.
- First `--facts` → `(no facts)` (ignore pre-existing user data if this machine already has facts; report what you saw).
- `--text "my name is Ada" --no-tts` → `Hideko: ...` normal response.
- Second `--facts` → contains `name: Ada`.
- `--text "hello" --no-tts` → `Hideko: Hello Ada. I am Hideko.` (first greeting in this process).
- `--forget` → `memory cleared`; final `--facts` → `(no facts)`.
- Leave the memory file empty at the end so later tasks start clean.

## Stop and ask the human if

- The greeting rewrite conflicts with an existing test you cannot resolve without changing frozen expectations, or
- You think memory should affect responses other than greetings — that is out of scope for this task.
