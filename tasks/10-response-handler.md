# Task 10 — Response handler (matching, selection, fallback)

**Goal (one sentence).** Add `Trigger`, `ResponseDataError`, and `ResponseHandler` to the **existing** `response_handler.py` (created in task 08). It loads the two YAML files, matches a transcript against patterns, and returns a `Response` or a fallback.

**You only need this file.** All rules are inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `response_handler.py` — **modify only** |
| Depends on | tasks 03, 08, 09 |
| Blocks | task 11, task 18 |
| Time budget | ~60 min |

**Do not modify `Response` or `EchoResponder`.** They must stay byte-identical to task 08. Do not add `ConversationState` or `_STATE_LINES` — that is task 11.

---

## 1. What already exists in `response_handler.py`

```python
@dataclass(frozen=True)
class Response:
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False

class EchoResponder:
    def __init__(self, config: AppConfig) -> None: ...
    def respond(self, text: str) -> Response: ...
    def reset(self) -> None: ...
```

Available config fields:

```python
cfg.responses.triggers_file   # pathlib.Path, absolute
cfg.responses.fallbacks_file  # pathlib.Path, absolute
```

## 2. Contract — add these exact signatures

```python
class ResponseDataError(Exception):
    """Raised when a responses YAML file is missing or malformed."""

@dataclass(frozen=True)
class Trigger:
    name: str
    priority: int
    patterns: tuple[str, ...]
    responses: tuple[str, ...]
    should_exit: bool = False

class ResponseHandler:
    def __init__(self, config: AppConfig, rng: random.Random | None = None) -> None: ...
    def load(self) -> None: ...
    def respond(self, text: str) -> Response: ...
    def reset(self) -> None: ...
    @property
    def trigger_count(self) -> int: ...
```

`rng` exists so tests can seed it (`random.Random(0)`). Always use `self._rng`, never the global `random` module.

## 3. Skeleton — add these parts below the existing `EchoResponder`

```python
import random
import re
import unicodedata
from collections import OrderedDict  # if you use an ordered structure

import yaml

# ... Response and EchoResponder stay here, unchanged ...

def normalize(text: str) -> str:
    # Exact code in §4.1
    ...

class ResponseHandler:
    def __init__(self, config: AppConfig, rng: random.Random | None = None) -> None:
        self._config = config
        self._rng = rng if rng is not None else random.Random()
        self._triggers: list[Trigger] = []
        self._compiled: list[tuple[Trigger, str, re.Pattern[str], int]] = []
        self._fallbacks: list[str] = []
        self._last_by_trigger: dict[str, str] = {}
        self._last_global: str | None = None
        self.load()          # FAIL FAST at startup, not on first utterance

    def load(self) -> None:
        # §5. Read both files, validate, build Trigger objects, compile regexes once.
        ...

    def respond(self, text: str) -> Response:
        # §4.2–4.5 in order. NEVER raises for ordinary input; always returns Response.
        ...

    def reset(self) -> None:
        self._last_by_trigger.clear()
        self._last_global = None

    @property
    def trigger_count(self) -> int:
        return len(self._triggers)
```

## 4. Matching — implement exactly

### 4.1 Normalisation

```python
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w\s']", " ", text)   # punctuation -> space; keep letters/digits/_/'
    text = re.sub(r"\s+", " ", text).strip()
    return text
```
`"Hello, Hideko!"` → `"hello hideko"`. `"What's up?"` → `"what's up"`. Empty after normalisation → fallback.

### 4.2 Pattern compilation (once, in `load()`)

```python
rx = re.compile(rf"\b{re.escape(pattern)}\b", re.IGNORECASE)
```
Store `(trigger, pattern, rx, word_count)` tuples, where `word_count = len(pattern.split())`.

**Word boundaries are mandatory** — `hi` must not match "this" or "which". `re.escape` is mandatory — a stray `.` must not act as a wildcard. Preserve file order for deterministic tie-breaks (use a list, not a set).

### 4.3 Scoring

For every compiled pattern that matches the normalised text, build key:

```
(trigger.priority, word_count, -pattern_index)
```

Pick the **maximum** key (tuple comparison). Tie-break by trigger order in file, then pattern order — never by set/dict iteration order. Rationale: priority first, then longest pattern ("good morning" beats "morning"), then earlier in file.

If several triggers match and one has `should_exit`, it wins **only** if its priority is highest — do not special-case exit.

### 4.4 Response selection (anti-repeat)

- Keep `self._last_by_trigger: dict[str, str]`.
- Choose uniformly from the trigger's responses **excluding** the previous one for that trigger — unless the list has one entry.
- Use `self._rng.choice(...)`.
- If the chosen response equals `self._last_global` and there are ≥2 options, pick another (cross-trigger repetition sounds broken).

### 4.5 Fallback

- Load `fallbacks.yaml`. If missing/empty, use hardcoded `"I did not catch that."` and log a warning.
- Same anti-repeat rule across fallbacks.
- Return `Response(text=..., trigger="fallback", is_fallback=True, should_exit=False)`.

### 4.6 `respond()` contract

- Never raises for ordinary input (empty string, very long string, emoji-only). Always returns a `Response`.
- `ResponseDataError` only from `load()`.
- Log at DEBUG: `match: "hello there" -> greeting (priority 100, pattern "hello")`.
- Truncate input to the first **500 characters** before normalising (a runaway transcript must not create a 10 MB regex subject).
- Update `_last_by_trigger[trigger.name]` and `_last_global` before returning.

## 5. Loading rules (`load()`)

- Read both files with `encoding="utf-8"`, `yaml.safe_load`.
- Validate: `version == 1`; `triggers` is a list; each trigger has the 4 required keys; `patterns` non-empty. Raise `ResponseDataError` with the file path **and** the offending trigger `name` (or index when the name is missing).
- Compile patterns at load time, never per call.
- `.get("should_exit", False)` for the optional key — reading it with `[...]` gives the fatal `KeyError: 'should_exit'`.
- Do **not** lowercase the stored responses — only patterns and input.

## 6. CLI (`__main__`) — test without a microphone

```
python response_handler.py --text "hello there" [--seed 0]
python response_handler.py --interactive [--seed 0]
```
`--interactive` reads stdin lines until EOF and prints a block per line:
```
in:  hello there
out: Hello! I am Hideko.
     trigger=greeting fallback=False exit=False
```

## 7. Rules checklist

- [ ] `Response` and `EchoResponder` byte-identical to task 08
- [ ] `hi` does not match inside "this", "which", "machine"
- [ ] `good morning` beats `morning` (priority, then word count)
- [ ] Unknown/empty/emoji-only input always returns a fallback, never raises
- [ ] Adjacent responses never identical when alternatives exist
- [ ] `load()` raises `ResponseDataError` (not `KeyError`) on malformed trigger
- [ ] Patterns compiled in `load()`, not in `respond()`
- [ ] `__init__` calls `load()` immediately
- [ ] `trigger_count` returns the real count
- [ ] Type hints + docstrings on all public functions/classes; `print()` only in `__main__`

## 8. Do NOT

- Do not add `fuzzywuzzy`, `rapidfuzz`, `spacy`, `nltk`, embeddings, or any new dependency.
- Do not implement conversation memory beyond the anti-repeat dict. Task 11 owns state.
- Do not put response text in Python source except the one hardcoded fallback.
- Do not reload YAML on every call.
- Do not lowercase the stored responses.
- Do not change the `Response` fields.
- Do not add `ConversationState` or `_STATE_LINES` (task 11).

## 9. Verify — run and paste output

```powershell
python response_handler.py --text "hello"
python response_handler.py --text "this is a which"
python response_handler.py --text "can you sing a song"
python response_handler.py --text "goodbye"
python response_handler.py --text "qwzxv"
```
Expected triggers, in order: `greeting`, `fallback` (**critical**: "this"/"which" must not match `hi`), `sing`, `goodbye exit=True`, `fallback`.

```powershell
python response_handler.py --text "tell me a joke" --seed 0
python response_handler.py --text "tell me a joke" --seed 0
```
Expected: identical output both times.

```powershell
python -c "from config import load_config; from response_handler import ResponseHandler; import random; h=ResponseHandler(load_config(), rng=random.Random(1)); print([h.respond('hello').text for _ in range(6)])"
```
Expected: no two adjacent identical strings.

```powershell
python -m pytest -q
```
Expected: still passes (formal tests arrive in task 18).

## 10. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 11.
