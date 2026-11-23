# Task 04 — Disk-backed memory store

**Phase B (memory). Depends on task 03. Touch at most 6 files.**

## Goal

Add `memory_store.py`: a small, offline, JSON-backed store for facts Hideko learns from the user. No LLM and no network in this task. The store must never crash the app on a missing or corrupt file.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No network at runtime. No `print()` in library code outside `if __name__ == "__main__":`.
- Type hints + docstrings on all public classes/functions. No bare `except:`.
- Tests must pass offline with no mic: `python -m pytest -q`.
- When adding a config section, update **all four** places: `config.yaml`, `_DEFAULTS`, both known-key listings in `config.py`, and `tests/conftest.py`.

## Current state (exact)

`config.py`:
```python
@dataclass(frozen=True)
class AppConfig:
    root: Path
    audio: AudioConfig
    vad: VADConfig
    stt: STTConfig
    tts: TTSConfig
    responses: ResponsesConfig
    runtime: RuntimeConfig
    logging: LoggingConfig
    source: Path  # the config.yaml that produced this object
```
Known sections in `_check_unknown_keys()` (~line 210):
```python
    known_sections = {
        "audio", "vad", "stt", "tts", "responses", "runtime", "logging"
    }
```
`build_*` functions are nested inside `load_config()`; the final block is:
```python
    audio = build_audio()
    vad = build_vad()
    stt = build_stt()
    tts = build_tts()
    responses = build_responses()
    runtime = build_runtime()
    logging_conf = build_logging()

    return AppConfig(
        root=PROJECT_ROOT,
        audio=audio,
        vad=vad,
        stt=stt,
        tts=tts,
        responses=responses,
        runtime=runtime,
        logging=logging_conf,
        source=config_path,
    )
```

`errors.py` ends with:
```python
class ResponseDataError(HidekoError):
    """Broken responses/*.yaml."""
    exit_code = 4
```

`config.yaml` has no `memory:` section. `tests/conftest.py` `config` fixture has no memory section.

## Steps

### 1. `config.py` — add the `MemoryConfig`

```python
@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool
    file: Path
    max_facts: int
    max_value_chars: int
```

Add `memory: MemoryConfig` to `AppConfig` immediately before `source`.

Add to `_DEFAULTS`:
```python
    "memory": {
        "enabled": True,
        "file": "memory/facts.json",
        "max_facts": 100,
        "max_value_chars": 120,
    },
```

Add `"memory"` to `known_sections` in `_check_unknown_keys()` and add this to its `section_keys` dict:
```python
        "memory": {"enabled", "file", "max_facts", "max_value_chars"},
```
Also add the same set to `_get_known_keys()` (there is a `section_type == "memory"` branch to add).

Add validation:
```python
def _validate_memory(config: dict[str, Any], path: str = "memory") -> None:
    """Validate the memory section."""
    max_facts = config.get("max_facts", _DEFAULTS["memory"]["max_facts"])
    if not isinstance(max_facts, int) or isinstance(max_facts, bool) or not (1 <= max_facts <= 1000):
        raise ConfigError(f"{path}.max_facts must be an int between 1 and 1000, got {max_facts}")

    max_value_chars = config.get("max_value_chars", _DEFAULTS["memory"]["max_value_chars"])
    if not isinstance(max_value_chars, int) or isinstance(max_value_chars, bool) or not (10 <= max_value_chars <= 500):
        raise ConfigError(f"{path}.max_value_chars must be an int between 10 and 500, got {max_value_chars}")
```

Add a nested `build_memory()` beside the other `build_*` functions:
```python
    def build_memory() -> MemoryConfig:
        memory_section = get_value(raw_config, "memory", {})
        if not isinstance(memory_section, dict):
            raise ConfigError(f"memory must be a mapping (dict), got {type(memory_section).__name__}")
        _validate_memory(memory_section)
        memory_file = Path(get_value(memory_section, "file", _DEFAULTS["memory"]["file"]))
        if not memory_file.is_absolute():
            memory_file = config_path.parent / memory_file
        return MemoryConfig(
            enabled=_validate_bool(
                get_value(memory_section, "enabled", _DEFAULTS["memory"]["enabled"]),
                "enabled", "memory",
            ),
            file=memory_file,
            max_facts=get_value(memory_section, "max_facts", _DEFAULTS["memory"]["max_facts"]),
            max_value_chars=get_value(memory_section, "max_value_chars", _DEFAULTS["memory"]["max_value_chars"]),
        )
```

Call `memory = build_memory()` before the `return` and pass `memory=memory,` to `AppConfig(...)`.

**Check for other direct `AppConfig(...)` constructions**: run `python -m pytest -q` — any direct construction now needs a `memory=` argument. Prefer `load_config()` in tests. Do not change frozen signatures of existing fields.

### 2. `config.yaml` — append this section before `logging:`

```yaml
memory:
  enabled: true              # store learned facts locally; no network
  file: memory/facts.json    # relative to config.yaml
  max_facts: 100             # oldest facts are evicted first
  max_value_chars: 120       # cap each stored value
```

### 3. `errors.py` — append:

```python
class MemoryError(HidekoError):
    """Memory file could not be read/written."""
    exit_code = 5
```

### 4. `tests/conftest.py` — add to the `config` fixture:

```python
        "memory": {
            "enabled": True, "file": "memory/facts.json",
            "max_facts": 100, "max_value_chars": 120,
        },
```
Because `load_config()` resolves relative paths against the temp config file, `config.memory.file` will be `tmp_path / "memory/facts.json"` — tests can use it without touching the real project folder.

### 5. `memory_store.py` — create this module

Required public API (frozen):
```python
@dataclass(frozen=True)
class Fact:
    key: str
    value: str
    updated_at: float
class MemoryStore:
    def __init__(self, config: AppConfig) -> None: ...
    def load(self) -> None: ...
    def save(self) -> None: ...
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def all(self) -> dict[str, str]: ...
    def observe(self, text: str) -> list[Fact]: ...
    def clear(self) -> None: ...
```

Implementation requirements:

- Imports: `json`, `logging`, `re`, `time`, `dataclasses`, `pathlib`, `argparse`, `sys`, `typing.Any`, `numpy` not needed. Import `AppConfig` from `config` and `MemoryError` from `errors`.
- `__init__` stores config, sets `self._facts: dict[str, Fact] = {}`, then calls `self.load()`.
- Disabled behaviour: when `config.memory.enabled` is False, `set`/`delete`/`observe`/`clear` are no-ops (`observe` returns `[]`), `get` returns `None`, `all` returns `{}`, `save` returns without writing.
- File format:
  ```json
  {"version": 1, "facts": {"name": {"value": "Ada", "updated_at": 1730000000.0}}}
  ```
- `load()`: if the file does not exist, return silently. On `OSError` or `json.JSONDecodeError`, or if the root is not a dict / `version != 1` / `facts` is not a dict, log a warning (`logger.warning`) and start empty — never raise. Skip individual malformed entries with a debug log.
- `save()`: create `file.parent` with `mkdir(parents=True, exist_ok=True)`; write to `file.with_name(file.name + ".tmp")` with `json.dumps(..., indent=2, sort_keys=True) + "\n"`; then `tmp.replace(file)` for atomicity. Wrap `OSError` into `MemoryError(f"Cannot write memory file {path}: {e}")`.
- `set(key, value)`: normalize `key = key.strip().lower()`, `value = re.sub(r"\s+", " ", value).strip()`. Reject empty key/value by returning. Cap value at `config.memory.max_value_chars`. Store `Fact(key, value, time.time())`. Afterwards, while `len(self._facts) > config.memory.max_facts`, remove the entry with the smallest `updated_at`. **Do not auto-save** — the caller decides when to persist.
- `get`, `delete`, `all` are straightforward dict operations; `all()` returns a plain `{key: value}` mapping.
- `clear()`: clear the dict and unlink the file if present (`missing_ok=True`); swallow only `OSError` with a warning log.
- `observe(text) -> list[Fact]`: case-insensitive extraction. Use this exact pattern table:
  ```python
  _OBSERVE_PATTERNS: tuple[tuple[str, str], ...] = (
      (r"\bmy name is\s+([A-Za-z][\w'\- ]{0,59})", "name"),
      (r"\bcall me\s+([A-Za-z][\w'\- ]{0,59})", "name"),
      (r"\bi like\s+([A-Za-z][\w'\- ]{0,59})", "likes"),
      (r"\bi love\s+([A-Za-z][\w'\- ]{0,59})", "likes"),
      (r"\bi (?:hate|dislike)\s+([A-Za-z][\w'\- ]{0,59})", "dislikes"),
      (r"\bmy favou?rite\s+([\w'\- ]{1,40}?)\s+is\s+([A-Za-z][\w'\- ]{0,59})", "favorite"),
      (r"\bremember that\s+([\w'\- ]{1,40}?)\s+is\s+([A-Za-z][\w'\- ]{0,59})", "note"),
  )
  ```
  For each pattern, `re.search(pattern, text, re.IGNORECASE)`. For two-group patterns the stored value is `f"{group1.strip()}: {group2.strip()}"`. Clean every captured value with:
  ```python
  value = re.split(r"\s+and\b|\s*,|\s+but\b", value, maxsplit=1)[0]
  value = re.sub(r"\s+", " ", value).strip(" '\"")
  ```
  Skip empty values. Call `self.set(key, value)` and append the resulting `Fact` to the returned list (look it up with `self.get(key)` after `set` to build the `Fact`). Multiple patterns may match one sentence; all are stored.
- Add an `if __name__ == "__main__":` CLI with `--facts` (print `key: value` lines, or `(no facts)`) and `--clear` (call `clear()` and print `memory cleared`). This is the only place printing is allowed.

### 6. `tests/test_memory_store.py` — new file

Cover:
- `roundtrip` — `set("name", "Ada")`, `save()`, construct a second `MemoryStore(config)`, assert `get("name") == "Ada"`.
- `observe` — `"My name is Ada and I like cats"` stores `name=Ada`, `likes=cats`; `"I hate spiders"` stores `dislikes=spiders`; `"my favorite color is blue"` stores `favorite="color: blue"`; `"remember that the sky is blue"` stores `note="the sky: blue"`.
- `observe_returns_facts` — returned list has one `Fact` per stored item, with non-empty `value`.
- `eviction` — config with `max_facts=2`; set three keys with distinct `updated_at` (monkeypatch `time.time` if needed); assert only 2 remain and the oldest was removed.
- `corrupt_file` — write `{not json` to `config.memory.file`; constructing `MemoryStore` must not raise and `all() == {}`.
- `disabled` — config with `enabled=False`; `set`/`observe` do nothing, `save()` writes no file.
- `validation` — `max_facts: 0`, `max_facts: 1001`, `max_value_chars: 5` each raise `ConfigError` from `load_config`.

## Verification

```powershell
python -m pytest -q
python config.py --check
python memory_store.py --facts
python -m pytest -q tests/test_memory_store.py -v
```

Expected:

- `pytest` — all pass, including the new tests.
- `python config.py --check` — JSON contains a `"memory"` object with `"enabled": true`, `"file": "...memory\\facts.json"`, `"max_facts": 100`, `"max_value_chars": 120`.
- `python memory_store.py --facts` — prints `(no facts)` on a clean run (or existing `key: value` lines, which is fine).
- `tests/test_memory_store.py -v` — every test passes.

## Stop and ask the human if

- Any existing test fails because of the new `AppConfig` field and the fix is not just adding `memory=` to a constructor, or
- You believe fact extraction needs to understand more phrase forms than the seven listed — do not invent new ones, ask.
