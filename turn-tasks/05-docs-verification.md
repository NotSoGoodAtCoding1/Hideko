# Task 05 — Docs & final verification

**Wrap-up. Depends on tasks 01–04. Touch at most 4 files. No behaviour changes.**

## Goal

Document the turn state machine, tool registry, and timer tool; run the full verification suite. Record observed behavior honestly; do not add latency targets.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No application code changes in this task. If you find a bug, report it — do not fix it here.
- Be honest about v1 limitations: timer speech is delivered on the next user utterance because `mic.read_block()` blocks; no tool-calling from the LLM yet.

## Step 1 — `README.md`

Update these sections:

- **Status / at-a-glance**: add a row `Tool registry | registry + background scheduler; timer tool available`. Add `Turn state machine | idle/listening/thinking/speaking/paused/waiting_for_wake_word`.
- **Install**: no change (no new deps).
- **Configuration**: add rows for `runtime.tools_enabled` if added, and document the `tool:` key in `responses/triggers.yaml`. Add `set_timer` trigger example: `Say "set a timer for 5 minutes" — triggers the timer tool (speaks confirmation; fires via background scheduler)`.
- **Controls**: add that `--text "set a timer for 2 minutes"` tests the timer tool without a mic.
- **Architecture**: add `turn_state.py`, `tools/registry.py`, `tools/scheduler.py`, `tools/timer_tool.py`.
- **Known limitations**: add:
  - Timer speech is delivered on the next user utterance because `mic.read_block()` blocks; the timer event itself fires on time.
  - Only the `set_timer` tool is built in; add tools by subclassing `Tool` and registering.
  - Tools are invoked by YAML trigger config, not by the LLM.
- **Troubleshooting**: add `Tool %s failed` → check `logs/hideko.log`; `unknown tool` → trigger `tool:` key matches a registered tool name.

## Step 2 — `plan.md`

Append a section after "KoboldCpp backend phase":

```
## Turn state machine & tool registry phase

### Decisions
- Turn state extracted into TurnController/TurnState (idle, listening, thinking, speaking, paused, waiting_for_wake_word); transitions publish bus events.
- Tool registry + background scheduler under tools/; tools execute after their trigger's response is spoken.
- First tool: set_timer (background callback fires timer_finished event + queues speech).
- Tools are configured via YAML trigger `tool:` key, not LLM tool-calling (v1).
- v1 limitation: mic.read_block() blocks, so timer speech waits for the next utterance.
```

Add `Still out of scope`: avatar GUI, wake-word optimization, barge-in, LLM tool-calling, config schema versioning.

## Step 3 — Final verification

Run with **no** KoboldCpp server, no mic:

```powershell
python -m pytest -q
python config.py --check
python scripts\check_env.py
python scripts\validate_responses.py
python main.py --text "hello" --no-tts
python main.py --text "goodbye" --no-tts
python main.py --text "set a timer for 2 minutes" --no-tts
python main.py --facts
python -m pytest tests/test_turn_state.py tests/test_tools.py tests/test_timer_tool.py -v
```

Expected:

- `pytest` — all pass (all previous tests plus new turn/tool/timer tests).
- `config.py --check` — no error.
- `check_env.py` — all required checks pass; `KoboldCpp API` skipped if disabled.
- `validate_responses.py` — exits 0, reports 16 triggers.
- The three `--text` commands produce canned replies with no connection errors; the timer command additionally schedules a background job (no crash).
- `--facts` prints facts or `(no facts)`.
- The three targeted test files pass verbosely.

## Stop and ask the human if

- A test fails — show the failure; do not force a pass.
- You find an application bug during this pass — report it; do not fix it here.
- You want to commit the work — ask before committing; report the exact `git status --short` first.
