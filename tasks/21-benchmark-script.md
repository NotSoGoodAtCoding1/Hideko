# Task 21 — Benchmark script

**Goal (one sentence).** Create **one file**, `scripts/benchmark.py`, that measures STT/TTS/response latency on real CPU hardware and writes `logs/benchmark.md`.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `scripts/benchmark.py` — **create**, nothing else |
| Depends on | tasks 06, 07, 10, 14 |
| Blocks | task 24 |
| Time budget | ~60 min |

Do not write `soak_test.py` or `test_integration.py` — tasks 22 and 23 own those. The output file `logs/benchmark.md` is gitignored; it is a generated artifact, not a source file.

---

## 1. CLI

```
usage: benchmark.py [--wav PATH] [--text TEXT] [--repeat N]
                    [--out PATH] [--skip-stt] [--skip-tts]
```
Defaults: `--text "Hello, I am Hideko, and this is a benchmark sentence."`, `--repeat 3`, `--out logs/benchmark.md`. **`--repeat` minimum is 2** so a median is meaningful. The first run is always reported as **cold** and excluded from the median.

## 2. Metrics

Report median and max of `repeat` runs, plus the cold first run separately.

| Metric | How |
|--------|-----|
| STT cold | `STTEngine.warmup()` wall time (model load included) |
| STT warm | `transcribe()` on a 5 s clip |
| STT on 10 s | the same clip doubled |
| TTS cold | first `synthesize()` (subprocess spawn) |
| TTS warm | cached-miss `synthesize()` of distinct sentences |
| TTS cached | repeat of an already-synthesized sentence |
| Response | `ResponseHandler.respond()` over 1000 calls |
| Text turn end-to-end | responder + TTS, no playback |

## 3. Source audio

- `--wav PATH`: load with `soundfile`; require 16 kHz mono. Other rates/channels → clean error, no silent resampling.
- Otherwise generate a synthetic 5 s signal: a 220 Hz tone with an amplitude envelope. **Warn** that STT numbers on synthetic audio are valid for timing only, not accuracy.
- If `models/` is missing (or construction raises `HidekoError`), print `SKIP stt` / `SKIP tts` and emit the report with those rows marked `n/a` — never crash.

## 4. Output file — exact shape

```markdown
# Hideko benchmark — 2026-11-20 14:02
CPU: 4 logical cores | Python 3.11.9 | tiny.en int8 | amy-medium

| Metric | median | max | budget | verdict |
|--------|--------|-----|--------|---------|
| STT cold (load + 5 s) | 4.21 s | 4.21 s | — | — |
| STT warm (5 s audio) | 2.10 s | 2.34 s | 3.0 s | PASS |
| STT on 10 s audio | 4.05 s | 4.40 s | 6.0 s | PASS |
| TTS cold | 1.62 s | 1.62 s | — | — |
| TTS warm (10 words) | 0.94 s | 1.10 s | 1.5 s | PASS |
| TTS cached | 0.00 s | 0.01 s | — | — |
| Response matching | 0.4 ms | 0.9 ms | 20 ms | PASS |
| Text turn end-to-end | 3.05 s | 3.30 s | 10 s | PASS |
```
Header: use `datetime.now()` for the timestamp, `os.cpu_count()`, `platform.python_version()`, and the model names from config. Use `statistics.median`.

Print the same table to stdout. Exit **1** if any measured value exceeds its budget by more than 50% (soft failure — the plan's 10 s ceiling is the hard limit). `n/a` rows are ignored for the verdict.

## 5. Rules checklist

- [ ] CLI flags exact; `--repeat < 2` rejected
- [ ] cold run reported separately and excluded from median
- [ ] all 8 metrics present, each with a budget and PASS/FAIL verdict (`—` for informational rows)
- [ ] `--skip-stt` / `--skip-tts` and missing models produce `n/a` rows, exit 0
- [ ] synthetic-audio warning printed
- [ ] writes only to `logs/` (create parent dirs)
- [ ] exit 1 only on >150% budget breach
- [ ] Type hints + docstrings on all public functions

## 6. Do NOT

- Do not add `pytest-benchmark`, `psutil`, or `matplotlib`.
- Do not run this inside the unit test suite.
- Do not measure playback latency with a stopwatch (no audio device).
- Do not commit `logs/*.md`.
- Do not tune thresholds to make numbers look better — report what you measure.

## 7. Verify — run and paste output

```powershell
python scripts\benchmark.py --repeat 2 --out logs\benchmark.md
Get-Content logs\benchmark.md
```
Expected: a table with real numbers. Paste it.

```powershell
python scripts\benchmark.py --skip-stt --skip-tts --out logs\benchmark.md
```
Expected: `n/a` rows, exit 0.

```powershell
python -m pytest -q
```
Expected: all tests pass.

## 8. Report

Report: files changed, pasted verification output (including the full benchmark table), anything unfinished. Do not start task 22.
