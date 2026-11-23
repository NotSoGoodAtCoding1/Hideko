# Task 03 — Timing visibility & benchmark fix

**Phase A (latency). Depends on tasks 01 and 02. Touch at most 4 files.**

## Goal

Make the per-stage timing data actually usable for before/after comparison, and fix the benchmark's broken response-matching budget comparison so its `PASS` verdict means something. **No pass/fail latency target was set** — add no new thresholds and change no budget numbers.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Do not change any timing budget value (`3.0 s`, `6.0 s`, `1.5 s`, `20 ms`, `10 s`).
- Do not change response selection, TTS, or playback logic.
- Tests must pass offline: `python -m pytest -q`.

## Current state (exact)

`main.py::HidekoApp.run` lines 121–149:
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

                if self.opts.no_tts:
                    print(f"Hideko: {response.text}")
                    self.status.timing(0.0, t2 - t1, 0.0, 0.0)
                else:
                    self.status.say(response.text)
                    clip = self.tts.synthesize(response.text)
                    t3 = perf_counter()
                    self.speaker.play(clip.samples, clip.sample_rate)
                    t4 = perf_counter()

                    if response.should_exit:
                        print("\nGoodbye.")
                        break

                    print(f"  [stt {t1-t0:.1f}s | resp {t2-t1:.2f}s | tts {t3-t2:.1f}s | play {t4-t3:.1f}s | total {t4-t0:.1f}s]")
                turn += 1
```

Problems to fix:
1. The timing line is skipped entirely when `response.should_exit` is true (the `break` happens first).
2. The `--no-tts` path prints through `Status.timing` with zeros but writes nothing to the log file.
3. There is no structured `timing ...` record in `logs/hideko.log`, so before/after runs are hard to compare.

`scripts/benchmark.py` — two occurrences of the ms→seconds conversion bug:
```python
            verdict = self._verdict(self.response_median_ms / 1000.0, 20.0)  # line 118
```
```python
            (self.response_median_ms / 1000.0, 20.0),                        # line 146, in has_soft_failure()
```
`_verdict(value, budget)` compares `value > budget * 1.5`; with the conversion, `0.0 ms` is compared against `20.0` **seconds**, so the check can essentially never fail. `import platform` currently sits in the `if __name__ == "__main__":` block at line 401, but `platform.python_version()` is used at line 364 — works only when executed as a script.

## Steps

### `main.py`

1. Replace lines 134–149 with a single shared timing block:
   ```python
                   if self.opts.no_tts:
                       print(f"Hideko: {response.text}")
                       t3 = t2
                       t4 = t2
                   else:
                       self.status.say(response.text)
                       clip = self.tts.synthesize(response.text)
                       t3 = perf_counter()
                       self.speaker.play(clip.samples, clip.sample_rate)
                       t4 = perf_counter()

                   print(
                       f"  [stt {t1-t0:.1f}s | resp {t2-t1:.2f}s | tts {t3-t2:.1f}s "
                       f"| play {t4-t3:.1f}s | total {t4-t0:.1f}s]"
                   )
                   logger.info(
                       "timing stt=%.2f resp=%.3f tts=%.2f play=%.2f total=%.2f",
                       t1 - t0, t2 - t1, t3 - t2, t4 - t3, t4 - t0,
                   )

                   if response.should_exit:
                       print("\nGoodbye.")
                       break
                   turn += 1
   ```
   `t3 = t2; t4 = t2` in the no-`--no-tts` branch makes `tts` and `play` read `0.00s`, which is honest. Keep the existing `turn += 1` and the half-duplex flush / RSS logging that follow unchanged.

2. Leave `Status.timing` in `cli.py` untouched — it may be used elsewhere; do not delete it.

### `scripts/benchmark.py`

3. Move `import platform` from the `if __name__ == "__main__":` block into the top-level import group (near `import os`). Remove the duplicate import at the bottom.

4. Replace **both** `self.response_median_ms / 1000.0` occurrences with `self.response_median_ms`. The budget is already in milliseconds (`20.0`), so the comparison must also be in milliseconds. Do not change `20.0`, `_verdict`, or any other budget.

5. In the generated markdown, append one informational line after the table (do not add a new verdict column):
   ```python
   *No latency target was set for this sprint; verdicts are informational.*
   ```
   Put it inside the existing f-string `markdown_content`, after `{data_rows}`.

## Verification

```powershell
python -m pytest -q
python main.py --text "goodbye" --no-tts
python -m pytest -q tests/test_integration.py
python scripts/benchmark.py --repeat 3
```

Expected:

- `pytest` — all pass.
- `python main.py --text "goodbye" --no-tts` — prints `Hideko: Goodbye...`, then a `[stt ... | resp ... | tts 0.0s | play 0.0s | total ...]` line, then `Goodbye.` (timing before the farewell). Note: the `--text` branch does not use `HidekoApp.run`, so also do one mic run `python main.py --turns 2 --no-greet --no-tts` if a mic is available, and confirm the timing line appears.
- `logs/hideko.log` contains lines beginning `timing stt=` (check with `Select-String -Path logs\hideko.log -Pattern 'timing stt=' | Select-Object -Last 3`).
- `python scripts/benchmark.py --repeat 3` — exits 0 (or 1 only if a real budget is breached by >150%, which is not a test failure), and rewrites `logs/benchmark.md`. The `Response matching` row shows a realistic value in ms with a `PASS` verdict. If STT/TTS rows are `n/a`, first run `python scripts/download_models.py --all`; if they are still `n/a`, report that instead of inventing numbers.
- The new `*No latency target...*` line appears in `logs/benchmark.md`.

Paste the resulting `logs/benchmark.md` content. **Do not assert any latency threshold.** Also add a short test in `tests/test_integration.py` (or `tests/test_smoke.py`) that runs `main(["--text", "goodbye", "--no-tts"])` and asserts exit code 0 and that `Goodbye.` appears in captured stdout; this locks in the timing-before-exit ordering.

## Stop and ask the human if

- The benchmark exits 1 because a >150% budget breach is reported, or
- A test asserts an exact timing-line format from before and now fails — show the diff and ask which format to keep.
