# Hideko GUI — Task Breakdown

This folder contains **self-contained tasks** to convert Hideko from CLI-only to having a GUI interface. Each task is written so an agent can finish it by reading exactly one file. Tasks build upon the existing event bus architecture.

> **Design philosophy:** The GUI is a **view** that subscribes to the existing event bus. The core audio loop in `main.py` remains unchanged. The GUI must work alongside the CLI, not replace it.

---

## How to use this folder

1. Give an agent **exactly one task file** and **nothing else** — not this README, not `../plan.md`, not other task files.
2. The agent reads its one file, implements, runs the **Verification** commands, and pastes the real output.
3. If verification fails, the agent fixes it. It must **not** start the next task.
4. One task = one commit.
5. Never give an agent two tasks at once.

---

## Task graph

| # | Task | Depends on | Produces | Blocks |
|---|------|------------|----------|--------|
| 01 | [GUI framework selection & requirements](01-gui-framework.md) | — | `requirements-gui.txt`, decision doc | 02 |
| 02 | [GUI module scaffold](02-gui-scaffold.md) | 01 | `gui/__init__.py`, `gui/app.py`, `gui/styles.py` | 03 |
| 03 | [Event bus GUI subscriber](03-gui-event-subscriber.md) | 02 | `gui/event_handler.py`, event-to-GUI mapping | 04 |
| 04 | [Main window layout](04-main-window.md) | 03 | `gui/main_window.py` with conversation display | 05 |
| 05 | [Audio visualization](05-audio-visualization.md) | 04 | `gui/audio_viz.py` (VU meter, waveform) | 06 |
| 06 | [Settings panel](06-settings-panel.md) | 04 | `gui/settings_panel.py` | 07 |
| 07 | [System tray integration](07-system-tray.md) | 04 | `gui/tray.py` | 08 |
| 08 | [CLI-GUI integration](08-cli-gui-integration.md) | 07 | `main.py` changes, `--gui` flag | 09 |
| 09 | [GUI wiring & testing](09-gui-testing.md) | 08 | `tests/test_gui.py`, manual verification | — |

---

## Architecture decisions (frozen before tasks start)

### GUI Framework: PySide6 (Qt for Python)

**Rationale:**
- **Native look and feel** on Windows (primary platform)
- **Mature and stable** with excellent documentation
- **Good audio visualization** support via QCustomPlot or custom QPainter
- **Thread-safe** signal/slot mechanism aligns with event bus
- **Already used** in similar projects, familiar patterns
- **LGPL license** — compatible with project goals
- **No GPU dependency** — pure CPU rendering

**Alternatives considered and rejected:**
- **tkinter**: Too basic, poor styling, no modern widgets
- **Kivy**: Heavy, non-native look, complex deployment
- **Dear PyGui**: Excellent for tools, but not for traditional desktop apps
- **Web (Flask/FastAPI)**: Requires browser, adds unnecessary complexity
- **Streamlit**: Not suitable for always-on desktop applications

### Integration Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                        Event Bus (existing)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Console     │  │ Logging     │  │ GUI Event Handler   │  │
│  │ Subscriber  │  │ Subscriber  │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   GUI Modules   │
                    │  - Main Window │
                    │  - Audio Viz   │
                    │  - Settings    │
                    │  - System Tray │
                    └─────────────────┘
```

**Key principles:**
1. **No changes to core modules** (`audio_manager.py`, `stt_engine.py`, `tts_engine.py`, `response_handler.py`, `config.py`) — they remain CLI-agnostic
2. **Event-driven**: GUI reacts to events, never calls into core directly
3. **Optional**: `--gui` flag enables GUI; without it, pure CLI behavior
4. **Non-blocking**: GUI runs in its own thread or process
5. **Graceful degradation**: If Qt fails to import, fall back to CLI with warning

### Directory structure for GUI

```
gui/
├── __init__.py           # Public API: launch_gui(), GUIApp
├── app.py                # Main Qt application wrapper
├── main_window.py        # Primary window with conversation
├── audio_viz.py          # VU meter, waveform display
├── settings_panel.py     # Configuration UI
├── tray.py               # System tray icon
├── event_handler.py      # Event bus subscriber → GUI updates
├── styles.py             # Colors, fonts, spacing constants
└── resources/            # Icons, assets (gitignored or tracked)
```

### Event mapping (GUI requirements)

The GUI needs to react to these existing events:

| Event Kind | GUI Action |
|------------|------------|
| `startup` | Show main window, initialize UI state |
| `calibrating` | Show calibration status |
| `ready` | Enable UI controls, show ready state |
| `listening` | Show listening indicator, start VU meter |
| `paused` | Show paused state, update tray icon |
| `wake_detected` | Show wake word notification |
| `thinking` | Show thinking spinner |
| `heard` | Add user message to conversation display |
| `speaking` | Add assistant message, show speaking indicator |
| `missed` | Show "didn't catch that" briefly |
| `turn_timing` | Update performance metrics display |
| `error` | Show error message in GUI |
| `goodbye` | Prepare for shutdown |
| `shutdown` | Close GUI cleanly |

Additional GUI-specific events may be added for:
- User clicking microphone mute button
- User changing settings
- Window minimize/maximize
- Tray icon interactions

---

## Ground rules for every agent

- **OS**: Windows 10/11, PowerShell. All commands in tasks are PowerShell.
- **Python**: 3.11.x only.
- **Project root**: `C:\Users\Ilya\Documents\new_prj`
- **No GPU required for GUI**: All rendering on CPU
- **Thread safety**: GUI updates must happen on the Qt main thread
- **Type hints** on every public function. **Docstring** on every public class/function.
- **No `print()` in GUI library code** — use Qt's logging or the existing `logging` module
- **No bare `except:`** and no `except Exception: pass`
- **Style consistency**: Follow existing code style in the project
- **No network at runtime** — GUI must work offline (icons may be embedded or downloaded at install time)

### Additional GUI-specific rules

- **No blocking the event loop**: Long operations must be in worker threads
- **Responsive UI**: Audio visualization must update at least 10 FPS
- **Accessible**: Use proper Qt accessibility APIs where available
- **HiDPI aware**: Must look good on high-DPI displays
- **Configurable**: All GUI settings should be in config, not hardcoded

---

## Dependencies

The GUI requires these additional packages in `requirements-gui.txt`:

```
PySide6==6.7.0
```

Optional for enhanced audio visualization:
```
pyqtgraph==0.13.3
```

---

## Frozen contracts

These signatures will be used across GUI tasks. Do not change them without approval.

```python
# gui/__init__.py
def launch_gui(config: AppConfig, bus: EventBus) -> "GUIApp | None":
    """Launch the GUI application. Returns None if GUI cannot start."""
    ...

class GUIApp:
    """Main GUI application controller."""
    def __init__(self, config: AppConfig, bus: EventBus) -> None: ...
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def close(self) -> None: ...
    @property
    def is_visible(self) -> bool: ...
```

```python
# gui/event_handler.py
class GUIEventHandler:
    """Subscribes to event bus and updates GUI."""
    def __init__(self, app: GUIApp, bus: EventBus) -> None: ...
    def subscribe(self) -> None: ...
    def unsubscribe(self) -> None: ...
```

```python
# gui/main_window.py
class MainWindow:
    """Primary application window."""
    def __init__(self, config: AppConfig, app: GUIApp) -> None: ...
    def add_user_message(self, text: str) -> None: ...
    def add_assistant_message(self, text: str) -> None: ...
    def set_status(self, status: str) -> None: ...
    def set_listening(self, active: bool) -> None: ...
    def set_speaking(self, active: bool) -> None: ...
    def closeEvent(self, event) -> None: ...
```

```python
# gui/audio_viz.py
class AudioVisualizer:
    """Visualizes audio input/output levels."""
    def __init__(self, parent: QWidget | None = None) -> None: ...
    def update_level(self, level: float) -> None: ...  # level: 0.0 to 1.0
    def update_spectrum(self, data: list[float]) -> None: ...
```

```python
# gui/settings_panel.py
class SettingsPanel:
    """Configuration UI panel."""
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None: ...
    def save_settings(self) -> AppConfig: ...
```

```python
# gui/tray.py
class SystemTray:
    """System tray icon with menu."""
    def __init__(self, app: GUIApp) -> None: ...
    def show(self) -> None: ...
    def hide(self) -> None: ...
```

---

## Definition of Done (applies to every task)

- [ ] The task's **Verification** commands were run and their real output pasted in the report.
- [ ] `python -m pytest -q` still passes (GUI tests may be skipped without Qt).
- [ ] No file outside the task's **Files you touch** list was modified.
- [ ] No new dependency without a `requirements-gui.txt` update (or `requirements.txt` if approved).
- [ ] Public functions have type hints; public classes/functions have docstrings.
- [ ] The agent reported: files changed, verification output, and anything it could not finish.
- [ ] GUI works on Windows 10/11 with PySide6.

---

## UI Design Specifications

### Main Window

```
┌─────────────────────────────────────────────────────────────┐
│  Hideko                     [-] [□] [X]                      │
├─────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                                 ┌──────────┐              │ │
│  │   Conversation History        │ Settings │              │ │
│  │                                 │  Button  │              │ │
│  │ ┌─────────────────────────────┐└──────────┘              │ │
│  │ │ You: hello                  │    ┌────────────┐         │ │
│  │ └─────────────────────────────┘    │            │         │ │
│  │ ┌─────────────────────────────┐    │  VU Meter  │         │ │
│  │ │ Hideko: Hello! I'm Hideko.  │    │            │         │ │
│  │ └─────────────────────────────┘    │            │         │ │
│  │                                     └────────────┘         │ │
│  │                                                            │ │
│  │                     ┌─────────────────────┐               │ │
│  │                     │ [Mute] [Listen]     │               │ │
│  │                     └─────────────────────┘               │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Status: Ready         Timing: STT 1.9s | TTS 0.9s        │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Settings Panel

- Audio Devices (input/output selection)
- Volume levels (mic, output)
- VAD sensitivity
- Model selection (STT, TTS)
- Theme (light/dark/system)
- Language
- Hotkeys
- Always on top
- Start minimized
- Minimize to tray

### System Tray

- Icon: Hideko avatar
- Menu items:
  - Show
  - Mute/Unmute
  - Settings
  - Quit

---

## Performance targets

| Metric | Target |
|--------|--------|
| GUI startup time | < 2 seconds |
| Window show/hide | < 100ms |
| Audio visualization FPS | >= 10 |
| Memory overhead | < 50 MB |
| CPU usage (idle) | < 5% |

---

## Troubleshooting index

| Symptom | Where to look |
|---------|---------------|
| `ModuleNotFoundError: PySide6` | Task 01 |
| GUI window doesn't appear | Task 02, Task 04 |
| No audio visualization | Task 05 |
| Settings don't persist | Task 06 |
| Tray icon missing | Task 07 |
| GUI freezes during audio | Task 03 (threading) |
| High CPU usage | Task 05 (visualization) |
