# Task 04 — Hybrid routing

**Depends on task 03. Touch at most 2 files.** Do not modify `llm_fallback.py`, `config.yaml`, or `responses/*.yaml`.

## Goal

Make `ResponseHandler` use the LLM for conversational turns (`llm_only: true`) and unmatched input, while commands, goodbye, help, and fact triggers keep their instant canned responses. Any LLM failure must degrade to the existing canned/YAML response.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- `Response.respond(text: str) -> Response` stays frozen.
- `EchoResponder` is untouched.
- No `print()` in library code; log with `logger.warning` on LLM failure.
- Tests use a fake LLM; no server, no HTTP, no model load: `python -m pytest -q`.

## Current state (exact)

`response_handler.py` imports `LLMError, LLMFallback` from `llm_fallback` (added earlier). `ResponseHandler.__init__` already creates `self._llm` when `config.llm.enabled` is true; `LLMFallback.respond` now accepts `(text, intent=None)` (task 02).

In `respond()`:
```python
        if not matches:
            return self._try_llm_or_fallback(text)
```
```python
        # Pick the best match by score key (max)
        best_match = max(matches, key=lambda x: x[2])
        trigger, pattern, _ = best_match

        logger.debug(f"match: {normalized!r} -> {trigger.name} (priority {trigger.priority}, pattern {pattern!r})")

        # Response selection with anti-repeat
        responses = list(trigger.responses)
```
The existing `_try_llm_or_fallback` method:
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
                return Response(text=reply.text, trigger="llm", is_fallback=True, should_exit=False)
        return self._fallback_response()
```

`Trigger` now has `llm_only: bool = False` (task 03).

## Steps

### 1. `response_handler.py`

Import `LLMError` from `errors` if it is not already imported (it may currently come via `llm_fallback`; import it directly from `errors` to be explicit).

Replace `_try_llm_or_fallback` with `_try_llm`:
```python
    def _try_llm(self, text: str, intent: str | None = None) -> Response | None:
        """Return an LLM-authored Response, or None if unavailable/failed.

        Returning None lets the caller fall back to canned responses.
        """
        if self._llm is None or not self._llm.available():
            return None
        try:
            reply = self._llm.respond(text, intent=intent)
        except LLMError as exc:
            logger.warning("LLM failed, using canned response: %s", exc)
            return None
        self.state.turn_count += 1
        self.state.last_trigger = intent or "llm"
        self._last_global = reply.text
        return Response(
            text=reply.text,
            trigger=intent or "llm",
            is_fallback=intent is None,
            should_exit=False,
        )
```

Replace the no-match branch in `respond()`:
```python
        if not matches:
            llm_response = self._try_llm(text)
            if llm_response is not None:
                return llm_response
            return self._fallback_response()
```

Immediately after `logger.debug(...)` for the best match (before "Response selection with anti-repeat"), insert:
```python
        if trigger.llm_only:
            llm_response = self._try_llm(text, intent=trigger.name)
            if llm_response is not None:
                return llm_response
```
This is the only new routing branch. Everything below it (anti-repeat, state-dependent greeting lines, state updates, `should_exit`) remains unchanged and is reached only when the LLM did not answer.

Add a short comment above the branch:
```python
        # Hybrid persona: conversational intents are written by the LLM.
        # Commands/goodbye/help/facts (llm_only: false) stay canned below.
```

Do **not** add fuzzy matching, do **not** call the LLM when `normalized` is empty, and do **not** change `EchoResponder`.

### 2. `tests/test_response_handler.py`

Existing fakes likely define `respond(self, text)`. Update every fake LLM in this file to accept the new keyword:
```python
    def respond(self, text: str, intent: str | None = None) -> LLMReply:
        self.calls.append((text, intent))
        ...
```
Fix any assertions that used `fake.calls == [text]` to use tuples.

Append these tests:
- `test_conversational_trigger_uses_llm` — `ResponseHandler(config, llm=FakeLLM(reply="Witty line."))`; `respond("tell me a joke")`; assert `response.text == "Witty line."`, `response.trigger == "joke"`, `response.is_fallback is False`, and the fake recorded `("tell me a joke", "joke")`.
- `test_conversational_trigger_falls_back_to_canned` — fake raises `LLMError("offline")`; assert the text is one of the `joke` trigger's canned responses and `response.trigger == "joke"`.
- `test_command_trigger_never_calls_llm` — `respond("goodbye")` with a fake; assert `fake.calls == []`, `response.should_exit is True`, and the text is a canned goodbye.
- `test_help_and_name_never_call_llm` — parametrize `["help", "what is your name"]`; assert `fake.calls == []` and a canned response.
- `test_unmatched_uses_llm` — `respond("quantum bananas")`; assert `response.trigger == "llm"`, `response.is_fallback is True`, and intent recorded as `None`.
- `test_unmatched_falls_back_when_llm_fails` — fake raises; assert `response.trigger == "fallback"`.
- `test_empty_input_skips_llm` — `respond("   ")`; assert no LLM call.
- `test_llm_reply_updates_state` — after an LLM reply, `state.last_trigger` and `turn_count` are correct.
- `test_greeting_state_bypassed_for_llm` — second `respond("hello")` with LLM enabled does not use `_STATE_LINES["greeting_again"]` (the LLM wrote it).

Do not modify unrelated tests.

## Verification

```powershell
python -m pytest -q
python -m pytest -q tests/test_response_handler.py -v
python main.py --text "hello" --no-tts
python main.py --text "goodbye" --no-tts
python main.py --text "quantum bananas" --no-tts
```

Expected (with the default `llm.enabled: false`, so **no** server needed):

- `pytest` — all pass.
- `hello` → canned greeting (fast, no LLM).
- `goodbye` → canned farewell with `should_exit`.
- `quantum bananas` → YAML fallback.
- No command prints an LLM/connection error.

Then, if KoboldCpp is running, use a **temp config** with `llm.enabled: true` and confirm:
- `hello` → LLM-authored reply (persona), `trigger=hello` in DEBUG logs.
- `goodbye` → still the canned farewell.
- `quantum bananas` → LLM-authored reply, `trigger=llm`.
- Stop the server and repeat one unmatched turn: it must degrade to the YAML fallback without crashing.

Delete the temp config afterwards; do not leave `config.yaml` enabled.

## Stop and ask the human if

- A command trigger seems misclassified (e.g. you think `name` should be LLM-driven) — ask rather than reclassifying.
- An existing test asserts the old `trigger == "llm"` shape and you cannot update it without changing unrelated expectations.
- The LLM reply contains `should_exit` wording — the code must never let an LLM reply terminate the app; report if you see otherwise.
