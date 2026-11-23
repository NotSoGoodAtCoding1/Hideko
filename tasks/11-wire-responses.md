# Task 11 — Conversation state & response wiring

**Goal (one sentence).** Two small edits: (A) add `ConversationState` and two state-dependent line sets to `response_handler.py`; (B) in `main.py`, choose the responder by `runtime.echo_mode` and print `Goodbye.` on exit.

**You only need this file.** Both edits are shown as exact before/after. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `response_handler.py` (modify), `main.py` (modify) — **nothing else** |
| Depends on | tasks 08, 10 |
| Blocks | task 15, task 16 |
| Time budget | ~35 min |

**Milestone:** "hello" → greeting; "tell me a joke" → a joke; "goodbye" → goodbye + clean exit 0.

---

## Part A — `response_handler.py`

### A.1 Add this dataclass (below `Trigger`)

```python
@dataclass
class ConversationState:
    turn_count: int = 0
    greeted: bool = False
    goodbye_seen: bool = False
    last_trigger: str | None = None
```

### A.2 Add this module-level constant

```python
_STATE_LINES = {
    "greeting_again": (
        "We already said hello. I am still here, though.",
        "Hello again. You really like greetings.",
        "Hi once more. What would you like to do?",
    ),
    "after_goodbye": (
        "I already said goodbye. I am still here if you need me.",
    ),
}
```

These live in code, **not** YAML — pattern matching cannot detect "already greeted".

### A.3 `ResponseHandler` changes

- In `__init__`, after `self.load()`: `self.state = ConversationState()`.
- In `reset()`: also `self.state = ConversationState()` (fresh session, not per turn).
- In `respond()`, update state **before** returning, in this exact order:

  1. `turn_count += 1`
  2. `last_trigger = trigger.name` (or `"fallback"`)
  3. `greeted = True` when the matched trigger is `greeting`
  4. `goodbye_seen = True` when `should_exit` is true

**State-dependent overrides — capture the old value BEFORE updating:**

```python
was_greeted = self.state.greeted
was_goodbye = self.state.goodbye_seen
# ... match and pick a normal response ...
if trigger_name == "greeting" and was_greeted:
    text = self._rng.choice(_STATE_LINES["greeting_again"])
    # keep trigger="greeting", is_fallback=False
if trigger_name == "goodbye" and was_goodbye:
    text = _STATE_LINES["after_goodbye"][0]
    # still should_exit=True
# ...THEN update the state fields listed above...
```

If you check `greeted` **after** setting it, the first "hello" incorrectly says "we already said hello". This is the main trap in this task.

The anti-repeat bookkeeping (`_last_by_trigger`, `_last_global`) from task 10 still applies to these overridden lines.

State-dependent lines must not go through YAML. Do not add a `greeting_again` trigger.

## Part B — `main.py`

### B.1 Replace the `TODO(task 11)` in `setup()`

```python
# before (task 08):
self.responder = EchoResponder(config)   # TODO(task 11)

# after:
if config.runtime.echo_mode:
    self.responder = EchoResponder(config)
    logger.info("responder: EchoResponder (echo_mode)")
else:
    self.responder = ResponseHandler(config)
    logger.info("responder: ResponseHandler (%d triggers)", self.responder.trigger_count)
```

Update the import line to `from response_handler import EchoResponder, ResponseHandler`. `ResponseHandler` is constructed **once at startup**, never inside the loop.

### B.2 Exit handling — add right after the existing `should_exit` check in `run()`

```python
if response.should_exit:
    print("\nGoodbye.")
    break
```
Return exit code 0. `runtime.max_turns` still counts exchanges; leave that logic alone.

### B.3 Startup greeting

`greet_on_start` already plays "Hello. I am Hideko. I am listening." It must **not** set `state.greeted` — do not route it through `ResponseHandler`. Leave task 08's code as-is.

### B.4 Status lines

Keep the task-08 format. Do **not** print `trigger=` to the console (it stays in the DEBUG log).

```
You:    hello
Hideko: Hello! I am Hideko.
  [stt 1.9s | resp 0.00s | tts 0.9s | play 1.2s | total 4.0s]
```

## 5. Rules checklist

- [ ] `ConversationState` dataclass added with the 4 exact fields
- [ ] `_STATE_LINES` added with both keys and exact strings
- [ ] `was_greeted` / `was_goodbye` captured **before** state mutation
- [ ] `state` updated inside `respond()`, not in `main.py`
- [ ] `reset()` installs a fresh `ConversationState()`
- [ ] responder chosen once in `setup()` from `runtime.echo_mode`
- [ ] `should_exit` prints `Goodbye.` and breaks with code 0
- [ ] startup greeting does not set `greeted`
- [ ] `Response` and `EchoResponder` still unchanged
- [ ] Type hints + docstrings on all public functions/classes

## 6. Do NOT

- Do not add dialogue history, memory across runs, or a "context window".
- Do not call an LLM.
- Do not add new YAML files for state.
- Do not change `Response` or `EchoResponder`.
- Do not remove `echo_mode` — it is the phase-1 fallback used by tests.
- Do not add per-turn `random.seed()` calls.

## 7. Verify — run and paste output

```powershell
python main.py --text "hello"
python main.py --text "tell me a joke"
python main.py --text "goodbye"
```
Expected: three distinct responses; the third prints `Goodbye.` and exits 0.

Echo mode still works: temporarily set `runtime.echo_mode: true` in `config.yaml`, run `python main.py --text "hello"`, confirm `I heard you say: hello`, then **set it back to `false`**.

```powershell
python main.py --turns 3
```
Say "hello" → "tell me a joke" → "goodbye". Expected: greeting, joke, goodbye, exit 0. Paste the transcript.

```powershell
python -c "from config import load_config; from response_handler import ResponseHandler; h=ResponseHandler(load_config()); print(h.respond('hello').text); print(h.respond('hello').text); print(h.state.turn_count, h.state.greeted)"
```
Expected: two **different** lines (second from `greeting_again`), then `2 True`.

```powershell
python -m pytest -q
```
Expected: still passes (formal tests arrive in task 18).

## 8. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 12.
