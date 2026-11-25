# GUI Tasks - Implementation Checklist

This file provides a quick overview of all GUI tasks and their status.

## Task Overview

| # | Task | File | Status | Dependencies |
|---|------|------|--------|--------------|
| 01 | GUI Framework Selection & Requirements | `01-gui-framework.md` | ⬜ Not Started | — |
| 02 | GUI Module Scaffold | `02-gui-scaffold.md` | ⬜ Not Started | 01 |
| 03 | Event Bus GUI Subscriber | `03-gui-event-subscriber.md` | ⬜ Not Started | 02 |
| 04 | Main Window Layout | `04-main-window.md` | ⬜ Not Started | 03 |
| 05 | Audio Visualization | `05-audio-visualization.md` | ⬜ Not Started | 04 |
| 06 | Settings Panel | `06-settings-panel.md` | ⬜ Not Started | 04 |
| 07 | System Tray Integration | `07-system-tray.md` | ⬜ Not Started | 04 |
| 08 | CLI-GUI Integration | `08-cli-gui-integration.md` | ⬜ Not Started | 07 |
| 09 | GUI Testing | `09-gui-testing.md` | ⬜ Not Started | 08 |

## Files to be Created

### Task Files (already created)
- `gui-tasks/README.md` - Main README for GUI tasks
- `gui-tasks/01-gui-framework.md` - Task 01 instructions
- `gui-tasks/02-gui-scaffold.md` - Task 02 instructions
- `gui-tasks/03-gui-event-subscriber.md` - Task 03 instructions
- `gui-tasks/04-main-window.md` - Task 04 instructions
- `gui-tasks/05-audio-visualization.md` - Task 05 instructions
- `gui-tasks/06-settings-panel.md` - Task 06 instructions
- `gui-tasks/07-system-tray.md` - Task 07 instructions
- `gui-tasks/08-cli-gui-integration.md` - Task 08 instructions
- `gui-tasks/09-gui-testing.md` - Task 09 instructions

### Files to Create During Implementation

#### Task 01
- `requirements-gui.txt`
- `docs/gui-framework-decision.md`

#### Task 02
- `gui/__init__.py`
- `gui/app.py`
- `gui/styles.py`

#### Task 03
- `gui/event_handler.py`
- Modify: `gui/app.py`
- Modify: `gui/__init__.py`

#### Task 04
- `gui/main_window.py`
- Modify: `gui/app.py`
- Modify: `gui/event_handler.py`

#### Task 05
- `gui/audio_viz.py`
- Modify: `gui/main_window.py`

#### Task 06
- `gui/settings_panel.py`
- Modify: `gui/main_window.py`

#### Task 07
- `gui/tray.py`
- Modify: `gui/app.py`
- Modify: `gui/event_handler.py`

#### Task 08
- Modify: `cli.py`
- Modify: `main.py`

#### Task 09
- `tests/test_gui.py`
- Modify: `pytest.ini`

## Implementation Order

```
Task 01 → Task 02 → Task 03 → Task 04 → Task 05 → Task 06 → Task 07 → Task 08 → Task 09
                ↓
          (All tasks must be done in order)
```

## Quick Start

To begin implementing the GUI:

1. Read `gui-tasks/README.md` to understand the overall plan
2. Start with Task 01: `gui-tasks/01-gui-framework.md`
3. Follow the instructions in each task file
4. Verify each task before moving to the next
5. Commit changes after each task

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                        Hideko Application                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │    CLI          │     │      GUI         │               │
│  │  (existing)     │     │   (new)          │               │
│  └────────┬────────┘     └────────┬────────┘               │
│           │                       │                         │
│           ▼                       ▼                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Event Bus                         │    │
│  │              (existing, enhanced)                    │    │
│  └─────────────────────────────────────────────────────┘    │
│           │                                         │            │
│           ▼                                         ▼            │
│  ┌─────────────────┐     ┌───────────────────────────┐    │
│  │  Core Modules   │     │     GUI Components        │    │
│  │  (unchanged)    │     │                           │    │
│  │ - audio_manager │     │ - MainWindow             │    │
│  │ - stt_engine    │     │ - AudioVisualizer        │    │
│  │ - tts_engine    │     │ - SettingsPanel          │    │
│  │ - response...   │     │ - SystemTray             │    │
│  │ - main.py       │     │ - EventHandler           │    │
│  └─────────────────┘     └───────────────────────────┘    │
│                                                           │
└─────────────────────────────────────────────────────────────┘
```

## Key Principles

1. **Non-Breaking**: GUI is optional; CLI continues to work without it
2. **Event-Driven**: GUI subscribes to existing event bus
3. **Separation of Concerns**: GUI code is isolated in `gui/` directory
4. **Thread Safety**: All GUI updates happen on Qt main thread
5. **Progressive Enhancement**: Each task adds one feature without breaking existing ones

## Testing Commands

After completing all tasks, verify with:

```bash
# Test CLI still works
python main.py --help

# Test GUI can be launched
python main.py --gui

# Test with text input
python main.py --gui --text "hello"

# Run all tests
python -m pytest -q

# Run GUI tests specifically
python -m pytest tests/test_gui.py -v
```

## Success Criteria

✅ All tasks completed
✅ GUI can be launched with `--gui` flag
✅ CLI still works without `--gui` flag
✅ All existing tests still pass
✅ GUI displays conversation history
✅ GUI shows audio visualization
✅ GUI has settings dialog
✅ GUI has system tray icon
✅ Events flow correctly to GUI

## Notes

- Tasks must be completed in order
- Each task has its own verification steps
- Do not start the next task until the current one is verified
- GUI requires PySide6 to be installed
- Qt event loop must be processed for GUI to work
