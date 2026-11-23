# Task 19 — Unit tests: response handler + STT

**Goal (one sentence).** Create `tests/test_response_handler.py` (12 cases) and `tests/test_stt_engine.py` (8 cases).

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `tests/test_response_handler.py`, `tests/test_stt_engine.py` — **create**, nothing else |
| Depends on | tasks 10, 11, 06, 17 (`config` fixture) |
| Blocks | task 24 |
| Time budget | ~60 min |

**Hard rule:** no models loaded, no mic, no speakers, no network. Every STT test patches `WhisperModel`.

---

## Part A — `tests/test_response_handler.py` (12 cases)

Uses `ResponseHandler(config, rng=random.Random(0))`. `config.responses.*` from the fixture points at `tmp_path/responses/`, so write small YAML files there in each test (or use a helper). Do **not** use the real project YAML files.

Helper:

```python
def write_data(tmp_path, triggers=None, fallbacks=None):
    import yaml
    (tmp_path / "responses").mkdir(exist_ok=True)
    if triggers is not None:
        (tmp_path / "responses" / "triggers.yaml").write_text(
            yaml.safe_dump({"version": 1, "triggers": triggers}), encoding="utf-8")
    if fallbacks is not None:
        (tmp_path / "responses" / "fallbacks.yaml").write_text(
            yaml.safe_dump({"version": 1, "fallbacks": fallbacks}), encoding="utf-8")
```

Minimal trigger dict: `{"name": "greeting", "priority": 100, "patterns": ["hello"], "responses": ["Hello!", "Hi there."]}`.

Cases:

1. `"hello"` → `trigger == "greeting"`, `is_fallback is False`.
2. `"this is a which machine"` → fallback (**word boundary**: `hi` must not match inside these words).
3. `"good morning"` → greeting, not a shorter competing trigger.
4. Priority: synthetic `low` (priority 10, pattern `"test"`) and `high` (priority 90, same pattern) → `high` wins.
5. Longest pattern at equal priority: `"sing a song"` beats `"sing"`.
6. `""` → fallback.
7. `"qwzxv"` → fallback.
8. A trigger with `should_exit: True` → `should_exit is True`.
9. Six consecutive `"hello"` calls → no two adjacent responses identical.
10. `rng=random.Random(0)` → two handlers produce identical sequences.
11. Second `"hello"` in one session → text is from the `greeting_again` set; `state.greeted is True`; `state.turn_count == 2`.
12. Malformed trigger (missing `responses`) → `ResponseDataError` whose message names the trigger.

Also add `import dataclasses` if you need a second config rooted at a different `tmp_path` — usually not necessary.

## Part B — `tests/test_stt_engine.py` (8 cases)

Fake model shape (copy):

```python
from types import SimpleNamespace

class FakeSegment:
    def __init__(self, text, avg_logprob=-0.2, no_speech_prob=0.01):
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob

class FakeModel:
    segments = []
    def __init__(self, *a, **k):
        self.calls = 0
    def transcribe(self, audio, **kw):
        self.calls += 1
        return iter(self.segments), SimpleNamespace(
            language="en", language_probability=0.99, duration=1.0)
```

Patch the constructor with `monkeypatch.setattr("stt_engine.WhisperModel", FakeModel)`. Remember `transcribe` returns `(generator, info)`.

Cases:

1. 0.2 s audio → empty text, `latency_s < 0.05`, **model never constructed** (assert the fake class was not instantiated — patch with a factory that records calls).
2. All-zero 2 s audio → empty text, no model call.
3. 44.1 kHz input → `STTError`.
4. Fake model returning `["Hello", "there"]` → `"Hello there"`.
5. Fake segment `avg_logprob=-1.5, no_speech_prob=0.9` → dropped (empty text).
6. Text `"Thank you."` on 1.2 s audio → dropped by hallucination filter.
7. Text `"you you you you you"` → dropped.
8. `WhisperModel` raising `OSError` → `STTError` mentioning `download_models.py`.

For case 1, a clean pattern is:

```python
made = []
def factory(*a, **k):
    made.append(1)
    return FakeModel()
monkeypatch.setattr("stt_engine.WhisperModel", factory)
e = STTEngine(config)
t = e.transcribe(np.zeros(3200, dtype=np.float32))
assert t.text == "" and not made
```

Patch the name the module actually uses — `stt_engine.WhisperModel` (the module does `from faster_whisper import WhisperModel` inside `_ensure_model()`). If the import is local to the method, patch `faster_whisper.WhisperModel` instead; check the module's import style first.

## Rules checklist

- [ ] 12 + 8 tests, all passing offline
- [ ] No real model ever loaded; `WhisperModel` patched in every STT test
- [ ] No real YAML files; all response data written under `tmp_path`
- [ ] RNGs seeded; no global `random`
- [ ] No `time.sleep()`, no `xfail`/`skip`, no new dependencies
- [ ] Type hints on helpers

## Do NOT

- Do not modify `response_handler.py`, `stt_engine.py`, or any application module. Report bugs instead.
- Do not download models or use `HIDEKO_E2E`.
- Do not use the project's real `responses/*.yaml`.

## Verify — run and paste output

```powershell
python -m pytest tests/test_response_handler.py tests/test_stt_engine.py -q
```
Expected: 20 passed, under 2 seconds.

```powershell
python -m pytest -q
```
Expected: all tests pass.

## Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 20.
