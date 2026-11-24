# Avatar Event Contract

This document describes the event contract that an avatar (or any future UI) can subscribe to in order to react to Hideko's conversational state. It is intentionally minimal: **no GUI implementation, no new dependencies, no rendering code**. This is a drop-in spec for phase 2.

> **Note:** This contract is for a personal, non-shipped project. No avatar code is implemented yet.

## How to Subscribe

```python
from events import ALL, EventBus
from my_avatar_renderer import AvatarRenderer  # Your custom subscriber

bus = EventBus()
avatar = AvatarRenderer()
bus.subscribe(ALL, avatar.on_event)
```

Subscribe once; the `handler(event)` function will be called synchronously for each published event. Keep the handler fast and non-blocking (see "Threading rules" below).

## State Table

Below is a suggested mapping of event kinds to avatar states. The state names are illustrative; adapt them to your rendering pipeline.

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

### Event Payloads (exact keys and types)

All payloads are simple dictionaries. Unknown keys are ignored by subscribers.

| Event | Keys | Types / Notes |
|---|---|---|
| `startup` | — | no payload |
| `calibrating` | — | no payload; emitted once before VAD calibration |
| `ready` | `stt_s: float`, `trigger_count: int` | STT warmup duration (seconds) and responder trigger count |
| `listening` | — | no payload; may be emitted multiple times per turn |
| `paused` | — | no payload; mute/resume toggle |
| `wake_detected` | `text: str`, `latency_s: float` | Transcript of wake word phrase and detection latency (s) |
| `thinking` | — | no payload; STT in progress |
| `heard` | `text: str` | Transcribed user utterance |
| `speaking` | `text: str` | Text to be spoken by TTS |
| `turn_timing` | `stt: float`, `resp: float`, `tts: float`, `play: float`, `total: float` | Timings in seconds: STT, responder, TTS synthesis, playback, total turn duration |
| `missed` | — | no payload; speech too short or silence |
| `error` | `message: str`, `exit_code: int` | Error message and exit code (if any) |
| `goodbye` | — | no payload; end-of-session marker |
| `shutdown` | — | no payload; final cleanup event |

## Threading Rules

Handlers must follow these constraints to remain responsive and safe on Windows:

1. **Fast return**: Handlers should execute in <1 ms. Do not block on I/O, disk, network, or rendering calls.
2. **No `sys.exit()`**: Never call `sys.exit()` or raise uncaught exceptions from within a handler; this would crash the entire app.
3. **No recursive publishing**: Do not call `bus.publish(...)` from within your handler unless you have an explicit guard flag. This prevents infinite loops.
4. **Render off-thread**: If your avatar has its own animation/game loop, push state updates to that loop rather than rendering directly in the handler.
5. **Thread safety**: The `EventBus` is internally thread-safe (uses a `threading.RLock`), so publishes from timer/avatar threads are serialized safely. In a single-threaded voice loop (current design) this is fine anyway; if you later add a background timer thread, ensure subscribers are idempotent or protect shared state with locks.

Current implementation: the voice loop runs on the main thread, so handlers execute synchronously in the event order of each turn. There is no monotonic sequence number on events; use `event.at` (Unix timestamp) if you need global ordering across turns.

## Known Gaps

The following behaviors are intentional omissions that may affect avatar design:

- **Startup greeting missing**: The startup greeting ("Hello. I am Hideko. I am listening.") is synthesized and played in `HidekoApp.setup()` **without** emitting a `speaking` event. This preserves the original console output behavior. An avatar will miss this one utterance until phase 2 adds an explicit "greet_speaking" event or modifies the setup path.
- **Text mode is partial**: In `--text` one-shot mode, only `speaking` is emitted; there is no `heard` (user said nothing) and no `listening`. This matches current console output but is not a full turn.
- **No cancellation/barge-in**: If the user speaks while Hideko is speaking or thinking, no event signals barge-in yet. Future events: `barge_in`, `canceled`.
- **Event order within a turn is synchronous**, but there is no monotonic sequence number; use `event.at` for global ordering if needed.
- **`startup`/`ready`/`shutdown` payloads are minimal**: `ready` includes `stt_s` and `trigger_count`, but no text payload for face/mood beyond the state names themselves.

## Subscribe Example (Full)

```python
from events import ALL, EventBus, Event

class SimpleAvatar:
    def __init__(self):
        self.state = "offline"
    
    def on_event(self, event: Event) -> None:
        # Fast path: no blocking, no sys.exit, no recursion
        new_state = {
            "startup": "booting",
            "calibrating": "calibrating",
            "ready": "idle",
            "listening": "listening",
            "paused": "muted",
            "wake_detected": "attentive",
            "thinking": "thinking",
            "speaking": "speaking",
            "missed": "confused",
            "error": "error",
            "goodbye": "farewell",
            "shutdown": "offline",
        }.get(event.kind, "idle")
        
        if new_state != self.state:
            print(f"[avatar] {self.state} -> {new_state}")
            self.state = new_state
        
        # Handle text payload
        if "text" in event.data:
            print(f"[avatar] says: '{event.data['text']}'")

if __name__ == "__main__":
    bus = EventBus()
    avatar = SimpleAvatar()
    bus.subscribe(ALL, avatar.on_event)
    
    # Fire a demo turn
    bus.publish("startup")
    bus.publish("calibrating")
    bus.publish("ready", stt_s=1.2, trigger_count=10)
    bus.publish("listening")
    bus.publish("heard", text="tell me a joke")
    bus.publish("speaking", text="Why did the robot cross the road?")
    bus.publish("turn_timing", stt=0.8, resp=0.5, tts=1.1, play=2.4, total=4.8)
    bus.publish("shutdown")
```
