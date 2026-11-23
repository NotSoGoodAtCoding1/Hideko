# Task 03 — Trigger intent tags

**Depends on task 02. Touch at most 4 files.** Do not modify `llm_fallback.py`, `main.py`, or `config.yaml`.

## Goal

Add an optional `llm_only` flag to triggers. Conversational triggers get `llm_only: true` so task 04 can route them through the LLM; command/goodbye/fact triggers stay canned. Existing YAML without the flag must continue to work with `llm_only` defaulting to `false`.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- `Response.respond(text: str) -> Response` is frozen; this task only adds a field to `Trigger` and to the YAML.
- No behaviour change yet — task 04 consumes the flag. Do not add routing logic here.
- `python -m pytest -q` must pass.

## Current state (exact)

`response_handler.py`:
```python
@dataclass(frozen=True)
class Trigger:
    name: str
    priority: int
    patterns: tuple[str, ...]
    responses: tuple[str, ...]
    should_exit: bool = False
```
In `ResponseHandler.load()`:
```python
            should_exit = trigger_raw.get("should_exit", False)
```
```python
            trigger = Trigger(
                name=name,
                priority=priority,
                patterns=tuple(patterns_raw),
                responses=tuple(responses_raw),
                should_exit=should_exit,
            )
```

`scripts/validate_responses.py`:
```python
        required_keys = {"name", "priority", "patterns", "responses"}
        actual_keys = set(trigger.keys())
        missing_keys = required_keys - actual_keys
        extra_keys = actual_keys - required_keys - {"should_exit"}
```

`responses/triggers.yaml` has 15 triggers: `greeting`, `how_are_you`, `name`, `sing`, `dance`, `joke`, `thank_you`, `goodbye`, `stop`, `help`, `compliment`, `insult`, `weather`, `real`, `meaning_of_life`.

## Steps

### 1. `response_handler.py`

Add the field to `Trigger`:
```python
    should_exit: bool = False
    llm_only: bool = False
```

In `load()`, right after the `should_exit` line, add strict validation:
```python
            llm_only = trigger_raw.get("llm_only", False)
            if not isinstance(llm_only, bool):
                raise ResponseDataError(
                    f"Trigger '{name}' llm_only must be a boolean, got {type(llm_only).__name__}"
                )
```

Pass it into the constructor:
```python
                should_exit=should_exit,
                llm_only=llm_only,
```

Add a docstring note on `llm_only`: "When true, matched turns are written by the LLM; canned responses are the fallback."

Do not change `respond()` in this task.

### 2. `responses/triggers.yaml`

Add `llm_only: true` to these 8 conversational triggers:
`greeting`, `how_are_you`, `sing`, `dance`, `joke`, `thank_you`, `compliment`, `insult`.

Add `llm_only: false` (explicit) to these 7 command/fact triggers:
`name`, `goodbye`, `stop`, `help`, `weather`, `real`, `meaning_of_life`.

Place the key next to `priority` and `should_exit`, e.g.:
```yaml
  - name: greeting
    priority: 100
    should_exit: false
    llm_only: true
    patterns:
      - hello
      ...
```
Keep every other line — names, priorities, patterns, responses — unchanged.

### 3. `scripts/validate_responses.py`

Replace:
```python
        extra_keys = actual_keys - required_keys - {"should_exit"}
```
with:
```python
        extra_keys = actual_keys - required_keys - {"should_exit", "llm_only"}
```

Add validation near the `should_exit` checks:
```python
        if "llm_only" in trigger and not isinstance(trigger["llm_only"], bool):
            failures.append(f"{path}:{line_num}: llm_only must be a boolean")
```

If the script prints a summary of trigger counts, add a count of `llm_only` triggers; otherwise skip.

### 4. `tests/test_response_handler.py`

Append:
- `test_llm_only_defaults_false` — write a temp triggers YAML with one trigger that has no `llm_only`; `ResponseHandler(config)._triggers[0].llm_only is False`.
- `test_llm_only_loaded_from_yaml` — temp trigger with `llm_only: true`; assert the parsed `Trigger.llm_only is True`.
- `test_llm_only_rejects_non_bool` — temp trigger with `llm_only: "true"`; `ResponseDataError` is raised and the message contains `llm_only`.
- `test_project_triggers_tagged` — using the real `responses/triggers.yaml`, assert the 8 names above have `llm_only is True` and the 7 others `is False`.
- `test_validator_accepts_llm_only` — run `validate_responses.py` logic (import the module the way existing tests do) against the real file and assert no failures mentioning `llm_only`.

Do not modify existing tests.

## Verification

```powershell
python -m pytest -q
python scripts\validate_responses.py
python -c "from config import load_config; from response_handler import ResponseHandler; h=ResponseHandler(load_config()); print(h.trigger_count, sum(t.llm_only for t in h._triggers))"
python main.py --text "hello" --no-tts
python main.py --text "goodbye" --no-tts
```

Expected:

- `pytest` — all pass.
- `validate_responses.py` — exits 0, still reports `OK: 15 triggers`.
- The one-liner prints `15 8`.
- Both `main.py --text` commands behave exactly as before (no routing change yet): `hello` gets a canned greeting, `goodbye` gets a canned farewell.

## Stop and ask the human if

- You disagree with which triggers are conversational — do not reclassify on your own; ask.
- The validator's allowed-key logic differs from the snippet above in a way that needs a broader change — show it and stop.
