# Task 22 — Soak test script

**Goal (one sentence).** Create **one file**, `scripts/soak_test.py`, that runs repeated response + synthesis without audio and fails if RSS grows more than 300 MB.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `scripts/soak_test.py` — **create**, nothing else |
| Depends on | tasks 07, 10, 14, 21 (`memory_rss_mb()` from `logging_setup`) |
| Blocks | task 24 |
| Time budget | ~35 min |

---

## 1. CLI

```
usage: soak_test.py [--minutes 5] [--interval 10] [--out logs/soak.md]
```
Defaults: 5 minutes, 10-second log interval, `logs/soak.md`. Must support `--minutes 0.1` for a ~6-second smoke test.

## 2. Loop

Until the deadline:

1. Pick a random line from `responses/triggers.yaml` patterns (read the YAML once at startup with `yaml.safe_load`); call `ResponseHandler.respond(...)`.
2. `TTSEngine.synthesize(reply.text)` — **no playback, no mic**. The LRU cache caps at 32 entries; do not keep every `AudioClip` in a list (that would look like a leak).
3. Every `interval` seconds log `t=120s rss=312MB turns=88` (use `memory_rss_mb()` rounded).
4. At the end compare first and last RSS. **Fail (exit 1) if growth > 300 MB.**
5. Write `logs/soak.md` with min/max/median RSS and total turns. Also print the result to stdout:
   `PASS: rss growth 3 MB over 0.1 min, 12 turns` (or `FAIL: ...`).

Use `time.monotonic()` for the deadline. Do **not** call `time.sleep()` for long periods — the loop should keep turning and sampling.

## 3. Rules checklist

- [ ] CLI flags exact; `--minutes 0.1` completes in ~6 s
- [ ] No microphone, no playback, no audio device opened
- [ ] RSS sampled with `memory_rss_mb()`; handles `None` (non-Windows) without crashing
- [ ] growth > 300 MB → exit 1
- [ ] `logs/soak.md` has min/max/median RSS + turn count
- [ ] Writes only under `logs/`
- [ ] Type hints + docstrings on all public functions

## 4. Do NOT

- Do not add `psutil` or any new dependency.
- Do not keep every generated clip in memory.
- Do not spawn a supervisor or background process.
- Do not commit `logs/soak.md`.

## 5. Verify — run and paste output

```powershell
python scripts\soak_test.py --minutes 0.1
```
Expected: `PASS: rss growth <n> MB over 0.1 min, <n> turns`, exit 0.

```powershell
python -m pytest -q
```
Expected: all tests pass.

## 6. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 23.
