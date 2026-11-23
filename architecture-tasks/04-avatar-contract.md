# Task 04 — Avatar event contract

**Depends on task 03. Touch at most 2 files. No GUI implementation.**

## Goal

Document the event contract an avatar (or any future UI) will consume, and provide a tiny runnable probe that demonstrates a subscriber maintaining avatar state. This is the deliverable that makes the next phase a drop-in.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- No GUI library, no new dependency, no avatar rendering. The probe prints state transitions only.
- Do not modify `main.py`, `events.py`, `event_outputs.py`, or any config file.
- `python -m pytest -q` still passes.

## Step 1 — `docs/avatar-events.md`

Create the folder and file. It must contain:

1. **How to subscribe** — a minimal code sample using `EventBus.subscribe(ALL, handler)`.
2. **State table** mapping events to a suggested avatar state:
   | Event | Suggested state |
   |---|---|
   | `startup` | booting |
   | `calibrating` | calibrating |
   | `ready` | idle |
   | `listening` | listening |
   | `paused` | muted |
   | `wake_detected` | attentive |
   | `thinking` | thinking |
   | `heard` | (display transcript; stay thinking) |
   | `speaking` | speaking |
   | `turn_timing` | (telemetry; no state change) |
   | `missed` | confused/idle |
   | `error` | error |
   | `goodbye` | farewell |
   | `shutdown` | offline |
3. **Exact payload keys** copied from `architecture-tasks/README.md` (the frozen contract). Include the `turn_timing` fields and their types.
4. **Threading rules** (important): handlers may be called from the voice thread or a future timer thread; they must return quickly, must not block on I/O or rendering, must not call `sys.exit`, and must not publish the same event kind recursively without a guard. Put rendering on the avatar's own thread/loop.
5. **Known gaps** — honest list:
   - `startup` / `ready` / `shutdown` are emitted but contain no text for a face to display beyond the counts.
   - The startup greeting in `HidekoApp.setup()` is synthesized and played **without** a `speaking` event (to preserve today's console output); an avatar will miss that one utterance until phase 2.
   - `--text` one-shot mode emits only `speaking`, not `heard`/`listening`.
   - No cancellation/barge-in events yet.
   - Event order is synchronous within a turn but there is no monotonic sequence number; use `event.at` for ordering if needed.
6. A note that this contract is for a personal, non-shipped project and that no avatar code is implemented yet.

## Step 2 — `scripts/avatar_probe.py`

Create a runnable demo (scripts may print):

```python
#!/usr/bin/env python
"""Demonstrate an avatar-style subscriber without any GUI."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from events import ALL, Event, EventBus  # noqa: E402

STATE_BY_KIND = {
    "startup": "booting",
    "calibrating": "calibrating",
    "ready": "idle",
    "listening": "listening",
    "paused": "muted",
    "wake_detected": "attentive",
    "thinking": "thinking",
    "heard": "thinking",
    "speaking": "speaking",
    "missed": "confused",
    "error": "error",
    "goodbye": "farewell",
    "shutdown": "offline",
}


class AvatarState:
    """Minimal stand-in for an avatar renderer."""

    def __init__(self) -> None:
        self.state = "offline"
        self.last_text = ""

    def handle(self, event: Event) -> None:
        """Update state from one event; no blocking work here."""
        new_state = STATE_BY_KIND.get(event.kind)
        if new_state is not None and new_state != self.state:
            print(f"[avatar] {self.state} -> {new_state}")
            self.state = new_state
        if "text" in event.data:
            self.last_text = str(event.data["text"])
            print(f"[avatar] text: {self.last_text}")


if __name__ == "__main__":
    avatar = AvatarState()
    bus = EventBus()
    bus.subscribe(ALL, avatar.handle)
    demo = [
        ("startup", {}),
        ("calibrating", {}),
        ("ready", {"stt_s": 1.8, "trigger_count": 15}),
        ("listening", {}),
        ("wake_detected", {"text": "hey hideko", "latency_s": 1.4}),
        ("thinking", {}),
        ("heard", {"text": "tell me a joke"}),
        ("speaking", {"text": "Why did the robot cross the road?"}),
        ("turn_timing", {"stt": 1.2, "resp": 0.6, "tts": 0.9, "play": 1.1, "total": 3.8}),
        ("goodbye", {}),
        ("shutdown", {}),
    ]
    for kind, data in demo:
        bus.publish(kind, **data)
    print(f"[avatar] final state: {avatar.state}")
```

## Verification

```powershell
python -m pytest -q
python scripts\avatar_probe.py
python -c "from pathlib import Path; p=Path('docs/avatar-events.md'); t=p.read_text(encoding='utf-8'); print(len(t), 'chars'); assert 'Threading rules' in t and 'turn_timing' in t"
```

Expected:

- `pytest` — all pass.
- `avatar_probe.py` prints state transitions ending with `[avatar] final state: offline`.
- The doc contains the threading rules and the `turn_timing` payload.

## Stop and ask the human if

- You believe an avatar needs an event kind not in the frozen list — do not add it; write it under "Known gaps" and ask.
- You are tempted to implement a GUI — explicitly out of scope.
