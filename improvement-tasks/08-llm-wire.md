# Task 08 — Wire LLM as fallback only

**Phase C (LLM). Depends on tasks 05 and 07. Touch at most 2 files.**

## Goal

Make `ResponseHandler` ask the optional local LLM **only when no YAML trigger matched**. A matched trigger must never call the LLM — that is the decision that protects the cheap latency path. Any LLM failure degrades to the existing YAML fallback.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- `Response.respond(text: str) -> Response` is frozen. `ResponseHandler.__init__` may gain optional keyword arguments only; `ResponseHandler(config)` must keep working.
- No new latency threshold. No `print()` in library code. Tests offline: `python -m pytest -q`.
- Do not change `main.py` — memory is already passed in task 05 and `ResponseHandler` builds its own LLM when enabled.

## Current state (exact)

`response_handler.py` imports include:
```python
from config import AppConfig
from errors import ResponseDataError
```

`ResponseHandler.__init__` (task 05 version):
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
        self._triggers: list[Trigger] = []
        ...
        self.load()
```

`ResponseHandler.respond()` currently begins:
```python
        # Truncate input to prevent runaway regex subjects
        text = text[:500]

        # Normalize
        normalized = normalize(text)

        # Empty after normalization -> fallback
        if not normalized:
            return self._fallback_response()

        # Find all matching triggers with their patterns
        matches: list[tuple[Trigger, str, int]] = []
        ...
        if not matches:
            return self._fallback_response()
```

State object:
```python
@dataclass
class ConversationState:
    turn_count: int = 0
    greeted: bool = False
    goodbye_seen: bool = False
    last_trigger: str | None = None
```

`_fallback_response()` updates `self._last_global` and returns `Response(text=..., trigger="fallback", is_fallback=True, should_exit=False)`.

## Steps

### 1. `response_handler.py`

- Add imports:
  ```python
  from llm_fallback import LLMError, LLMFallback
  ```
  (`llm_fallback` imports `config`, `errors`, `memory_store` only — no cycle.)

- Extend `__init__` with one optional argument and store it:
  ```python
      def __init__(
          self,
          config: AppConfig,
          rng: random.Random | None = None,
          memory: MemoryStore | None = None,
          llm: LLMFallback | None = None,
      ) -> None:
          self._config = config
          self._rng = rng if rng is not None else random.Random()
          self._memory = memory
          self._llm = (
              llm
              if llm is not None
              else (LLMFallback(config, memory=memory) if config.llm.enabled else None)
          )
          self._triggers: list[Trigger] = []
          ...  # rest unchanged
  ```
  With `llm.enabled: false` (the default) nothing is constructed and behaviour is unchanged.

- Replace the no-match return in `respond()`:
  ```python
          if not matches:
              return self._try_llm_or_fallback(text)
  ```
  Leave the `if not normalized: return self._fallback_response()` line alone — empty/hallucinated input should not reach the LLM.

- Add this private method to `ResponseHandler` (place it just above `_fallback_response`):
  ```python
      def _try_llm_or_fallback(self, text: str) -> Response:
          """Ask the optional local LLM, degrading to a YAML fallback on any failure."""
          if self._llm is not None and self._llm.available():
              try:
                  reply = self._llm.respond(text)
              except LLMError as exc:
                  logger.warning("LLM fallback failed, using YAML fallback: %s", exc)
              else:
                  self.state.turn_count += 1
                  self.state.last_trigger = "llm"
                  self._last_global = reply.text
                  return Response(
                      text=reply.text,
                      trigger="llm",
                      is_fallback=True,
                      should_exit=False,
                  )
          return self._fallback_response()
  ```
  Do not catch anything broader than `LLMError`; `LLMFallback.respond` already wraps backend failures into `LLMError`.

- Update the module docstring or add a comment near `_try_llm_or_fallback` stating the invariant: **the LLM is called only when no trigger matched**.

### 2. `tests/test_response_handler.py`

Append these tests using the existing fixtures and style. Define a small fake:
```python
class FakeLLM:
    def __init__(self, reply: str = "A thoughtful answer.", error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.reply = reply
        self.error = error
    def available(self) -> bool:
        return True
    def respond(self, text: str) -> LLMReply:
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return LLMReply(text=self.reply, latency_s=0.01)
```
Import `LLMError`, `LLMReply` from `llm_fallback`.

Cover:
- `llm_not_called_on_trigger_match` — `handler = ResponseHandler(config, llm=FakeLLM())`; `respond("hello")`; assert `fake.calls == []` and `response.trigger != "llm"`.
- `llm_used_when_no_trigger_matches` — `respond("quantum bananas")`; assert `response.text == "A thoughtful answer."`, `response.trigger == "llm"`, `response.is_fallback is True`, `fake.calls == ["quantum bananas"]`.
- `llm_error_degrades_to_yaml_fallback` — fake with `error=LLMError("timeout")`; assert `response.trigger == "fallback"` and the text is one of `responses/fallbacks.yaml` lines.
- `llm_disabled_config_never_constructs` — fixture config has `llm.enabled=False`; `ResponseHandler(config).respond("quantum bananas")` must return `trigger == "fallback"` and must not attempt to import/construct a real backend.
- `empty_input_skips_llm` — `respond("   ")` with a fake; assert `fake.calls == []`.
- `llm_reply_updates_state` — after an LLM reply, `handler.state.last_trigger == "llm"` and `turn_count == 1`.

Do not modify existing tests. Do not assert a random exact fallback string — assert membership in the fallback list.

## Verification

```powershell
python -m pytest -q
python -m pytest -q tests/test_response_handler.py -v
python main.py --text "hello" --no-tts
python main.py --text "what is the meaning of life" --no-tts
```

Expected:

- `pytest` — all pass.
- With the default `llm.enabled: false`, both `main.py --text` commands behave exactly as before: `hello` hits the YAML `greeting` trigger, and the second gets a YAML fallback or the `meaning_of_life` trigger. The second command must **not** load a model or print an LLM error.
- Optionally, with a temp config that sets `llm.enabled: true` and the GGUF model present, rerun the second command and confirm a generated one/two-sentence reply appears with `trigger=llm` in debug logs. Restore the original `config.yaml` afterwards.

## Stop and ask the human if

- An existing test assumes every fallback has `trigger == "fallback"` and now fails for the LLM path — show the test and ask before editing it.
- You think the LLM should also handle near-miss trigger matches (e.g. typos) — that is out of scope; ask rather than implementing fuzzy matching.
