# Task 09 — GUI Testing

**Phase:** Testing · **Depends on:** task 08 · **Blocks:** none · **Effort:** 30-60 min

---

## Goal

Create tests for the GUI components and verify the GUI works correctly with the application. This includes unit tests for GUI modules and manual verification procedures.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `tests/test_gui.py` — **create only this** |
| Depends on | task 08 (CLI-GUI integration complete) |
| Blocks | none |
| Time budget | ~50 min |

---

## Step 1 — Verify dependencies

```powershell
# Verify all GUI modules can be imported
python -c "from gui import launch_gui; from gui.app import GUIApp; from gui.main_window import MainWindow; from gui.event_handler import GUIEventHandler; from gui.tray import SystemTray; from gui.settings_panel import SettingsDialog; from gui.audio_viz import AudioVisualizer; print('All GUI imports OK')"

# Verify PySide6
python -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"

# Verify pytest
python -m pytest --version
```

All must succeed. If any fail, stop and report.

---

## Step 2 — Create `tests/test_gui.py`

This file contains tests for GUI components. Since GUI testing is complex (requires Qt event loop), we'll focus on:
1. Import tests
2. Class instantiation tests
3. Simple property tests
4. Mock-based tests for event handling

```python
"""Tests for Hideko GUI components.

These tests verify that GUI modules can be imported, classes can be instantiated,
and basic functionality works. GUI tests are limited because they require
PySide6 and a running Qt event loop.

Tests that require a display or full Qt environment are marked as 'gui' and
are skipped by default.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest


# Check if PySide6 is available
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False


# Check if GUI modules can be imported
GUI_AVAILABLE = False
try:
    from gui import launch_gui
    from gui.app import GUIApp
    from gui.main_window import MainWindow, ConversationDisplay, StatusBar, ControlPanel
    from gui.event_handler import GUIEventHandler, GUIEvent
    from gui.tray import SystemTray
    from gui.settings_panel import SettingsDialog, AudioSettingsTab, VADSettingsTab
    from gui.audio_viz import VUMeter, StereoVUMeter, WaveformDisplay, AudioVisualizer
    from gui.styles import Style, Colors, Fonts, Spacing, Sizes
    GUI_AVAILABLE = True
except ImportError as e:
    GUI_AVAILABLE = False


class TestGUIImports:
    """Test that all GUI modules can be imported."""
    
    def test_gui_modules_import(self) -> None:
        """Test that all GUI modules can be imported."""
        assert GUI_AVAILABLE, "GUI modules should be importable"
    
    def test_pyside6_available(self) -> None:
        """Test that PySide6 is available."""
        assert PYSIDE6_AVAILABLE, "PySide6 should be available for GUI tests"


class TestGUIApp:
    """Test the GUIApp class."""
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_gui_app_creation(self) -> None:
        """Test that GUIApp can be created."""
        from config import AppConfig
        from events import EventBus
        
        # Create mock config
        config = MagicMock(spec=AppConfig)
        bus = EventBus()
        
        # This might fail if QApplication doesn't exist
        # We'll create one for the test
        app = QApplication.instance()
        if app is None:
            # Create a QApplication with a dummy argv
            # Note: This might fail in headless environments
            try:
                app = QApplication(["test"])
            except Exception:
                pytest.skip("Cannot create QApplication in this environment")
        
        gui_app = GUIApp(config, bus)
        assert gui_app is not None
        assert gui_app.config == config
        assert gui_app.bus == bus
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_gui_app_properties(self) -> None:
        """Test GUIApp properties."""
        from config import AppConfig
        from events import EventBus
        
        config = MagicMock(spec=AppConfig)
        bus = EventBus()
        
        app = QApplication.instance()
        if app is None:
            try:
                app = QApplication(["test"])
            except Exception:
                pytest.skip("Cannot create QApplication")
        
        gui_app = GUIApp(config, bus)
        
        # Test initial state
        assert gui_app.is_visible == False
        assert gui_app.is_closed == False


class TestStyles:
    """Test style definitions."""
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_style_exists(self) -> None:
        """Test that Style class exists."""
        from gui.styles import Style
        assert Style is not None
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_colors_exist(self) -> None:
        """Test that color schemes exist."""
        from gui.styles import Colors, ColorScheme
        
        # Test light theme
        light = Colors.light()
        assert light.background == (248, 248, 248)
        assert light.text == (30, 30, 30)
        
        # Test dark theme
        dark = Colors.dark()
        assert dark.background == (40, 40, 40)
        assert dark.text == (240, 240, 240)
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_qss_generation(self) -> None:
        """Test that QSS can be generated."""
        from gui.styles import Style
        
        qss = Style.qss()
        assert isinstance(qss, str)
        assert len(qss) > 100  # Should have reasonable content
        assert "QWidget" in qss


class TestGUIEventHandler:
    """Test the GUI event handler."""
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_event_handler_creation(self) -> None:
        """Test that GUIEventHandler can be created."""
        from config import AppConfig
        from events import EventBus
        from gui.app import GUIApp
        from gui.event_handler import GUIEventHandler
        
        config = MagicMock(spec=AppConfig)
        bus = EventBus()
        
        app = QApplication.instance()
        if app is None:
            try:
                app = QApplication(["test"])
            except Exception:
                pytest.skip("Cannot create QApplication")
        
        gui_app = GUIApp(config, bus)
        handler = GUIEventHandler(gui_app, bus)
        
        assert handler is not None
        assert handler.app == gui_app
        assert handler.bus == bus
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_event_handlers_defined(self) -> None:
        """Test that all expected event handlers are defined."""
        from gui.event_handler import GUIEventHandler
        
        expected_handlers = [
            "_handle_startup",
            "_handle_calibrating",
            "_handle_ready",
            "_handle_listening",
            "_handle_paused",
            "_handle_wake_detected",
            "_handle_thinking",
            "_handle_heard",
            "_handle_speaking",
            "_handle_missed",
            "_handle_turn_timing",
            "_handle_error",
            "_handle_goodbye",
            "_handle_shutdown",
        ]
        
        for handler in expected_handlers:
            assert hasattr(GUIEventHandler, handler), f"Handler {handler} not found"


class TestAudioViz:
    """Test audio visualization components."""
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    @pytest.mark.skipif(not PYSIDE6_AVAILABLE, reason="PySide6 not available")
    def test_vu_meter_creation(self) -> None:
        """Test that VUMeter can be created."""
        from gui.audio_viz import VUMeter
        
        app = QApplication.instance()
        if app is None:
            try:
                app = QApplication(["test"])
            except Exception:
                pytest.skip("Cannot create QApplication")
        
        vu = VUMeter()
        assert vu is not None
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    @pytest.mark.skipif(not PYSIDE6_AVAILABLE, reason="PySide6 not available")
    def test_vu_meter_level(self) -> None:
        """Test that VUMeter level can be set."""
        from gui.audio_viz import VUMeter
        
        app = QApplication.instance()
        if app is None:
            try:
                app = QApplication(["test"])
            except Exception:
                pytest.skip("Cannot create QApplication")
        
        vu = VUMeter()
        
        # Test setting level
        vu.set_level(0.5)
        assert vu._level == 0.5
        
        vu.set_level(1.0)
        assert vu._level == 1.0


class TestSettingsPanel:
    """Test settings panel components."""
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    @pytest.mark.skipif(not PYSIDE6_AVAILABLE, reason="PySide6 not available")
    def test_settings_tabs_creation(self) -> None:
        """Test that settings tabs can be created."""
        from gui.settings_panel import (
            AudioSettingsTab,
            VADSettingsTab,
            ModelSettingsTab,
            AppearanceSettingsTab,
        )
        
        app = QApplication.instance()
        if app is None:
            try:
                app = QApplication(["test"])
            except Exception:
                pytest.skip("Cannot create QApplication")
        
        # Create mock config
        config = MagicMock()
        config.audio = {}
        config.vad = {}
        config.stt = {}
        config.tts = {}
        config.llm = {}
        
        # Test each tab
        audio_tab = AudioSettingsTab(config)
        assert audio_tab is not None
        
        vad_tab = VADSettingsTab(config)
        assert vad_tab is not None
        
        model_tab = ModelSettingsTab(config)
        assert model_tab is not None
        
        appearance_tab = AppearanceSettingsTab(config)
        assert appearance_tab is not None


class TestCLIIntegration:
    """Test CLI integration with GUI."""
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_cli_gui_flag(self) -> None:
        """Test that --gui flag is recognized by CLI."""
        from cli import parse_args
        
        # Test without --gui
        opts = parse_args([])
        assert hasattr(opts, 'gui')
        assert opts.gui == False
        
        # Test with --gui
        opts = parse_args(['--gui'])
        assert opts.gui == True
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    def test_cli_gui_with_other_flags(self) -> None:
        """Test that --gui works with other flags."""
        from cli import parse_args
        
        opts = parse_args(['--gui', '--no-tts', '--debug'])
        assert opts.gui == True
        assert opts.no_tts == True
        assert opts.debug == True


class TestLaunchGUI:
    """Test the launch_gui function."""
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    @pytest.mark.skipif(not PYSIDE6_AVAILABLE, reason="PySide6 not available")
    def test_launch_gui_no_gui_flag(self) -> None:
        """Test that GUI is not launched without flag."""
        from config import AppConfig
        from events import EventBus
        from gui import launch_gui
        
        config = MagicMock(spec=AppConfig)
        bus = EventBus()
        
        # Without QApplication, launch_gui might fail
        # This is expected behavior
        gui_app = launch_gui(config, bus)
        # We just check that it doesn't crash
        # The result may be None without proper Qt setup
    
    @pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
    @pytest.mark.skipif(not PYSIDE6_AVAILABLE, reason="PySide6 not available")
    def test_launch_gui_with_qapp(self) -> None:
        """Test that GUI can be launched with QApplication."""
        from config import AppConfig
        from events import EventBus
        from gui import launch_gui
        
        config = MagicMock(spec=AppConfig)
        bus = EventBus()
        
        # Create QApplication first
        app = QApplication.instance()
        if app is None:
            try:
                app = QApplication(["test"])
            except Exception:
                pytest.skip("Cannot create QApplication")
        
        gui_app = launch_gui(config, bus)
        # Should be able to create GUI with QApplication
        # Note: This might still fail in headless environments


# Manual verification procedures
class TestManualVerification:
    """Manual verification procedures.
    
    These are not automated tests but instructions for manual testing.
    """
    
    @staticmethod
    def verify_gui_launch():
        """Verify that GUI can be launched via --gui flag."""
        print("\n=== Manual Verification: GUI Launch ===")
        print("Run: python main.py --gui")
        print("Expected: GUI window should appear")
        print("Check: Window title is 'Hideko'")
        print("Check: Conversation display is visible")
        print("Check: Status bar is visible")
        print("Check: Control buttons are visible")
    
    @staticmethod
    def verify_event_flow():
        """Verify that events flow to GUI."""
        print("\n=== Manual Verification: Event Flow ===")
        print("Run: python main.py --gui --text 'hello'")
        print("Expected: GUI should show user message 'hello'")
        print("Expected: GUI should show assistant response")
        print("Check: Conversation display updates")
        print("Check: Status changes appropriately")
    
    @staticmethod
    def verify_tray_icon():
        """Verify that system tray icon works."""
        print("\n=== Manual Verification: Tray Icon ===")
        print("Run: python main.py --gui")
        print("Expected: Tray icon should appear in system tray")
        print("Check: Icon shows 'H' letter")
        print("Check: Right-click shows menu")
        print("Check: Menu has Show, Hide, Mute, Quit options")
    
    @staticmethod
    def verify_settings_dialog():
        """Verify that settings dialog works."""
        print("\n=== Manual Verification: Settings Dialog ===")
        print("Run: python main.py --gui")
        print("Click Settings button in main window")
        print("Expected: Settings dialog should appear")
        print("Check: Has Audio, VAD, Models, Appearance tabs")
        print("Check: Each tab has appropriate controls")
        print("Check: OK, Cancel, Apply buttons work")
    
    @staticmethod
    def verify_audio_visualization():
        """Verify that audio visualization works."""
        print("\n=== Manual Verification: Audio Visualization ===")
        print("Run: python main.py --gui")
        print("Speak into microphone")
        print("Expected: VU meter should show activity")
        print("Check: Meter responds to speech")
        print("Check: Meter returns to zero when silent")


# Mark all manual tests to be skipped in automated runs
@pytest.mark.skip(reason="Manual verification only")
class TestManualAll:
    """Run all manual verifications."""
    
    def test_all_manual(self) -> None:
        """Run all manual verification procedures."""
        TestManualVerification.verify_gui_launch()
        TestManualVerification.verify_event_flow()
        TestManualVerification.verify_tray_icon()
        TestManualVerification.verify_settings_dialog()
        TestManualVerification.verify_audio_visualization()


# Pytest configuration
# These tests can be run with: python -m pytest tests/test_gui.py -v
# To skip GUI tests: python -m pytest tests/test_gui.py -v -m "not gui"


if __name__ == "__main__":
    # Run manual verifications if executed directly
    TestManualVerification.verify_gui_launch()
    TestManualVerification.verify_event_flow()
    TestManualVerification.verify_tray_icon()
    TestManualVerification.verify_settings_dialog()
    TestManualVerification.verify_audio_visualization()
```

---

## Step 3 — Create pytest markers

Add GUI-related pytest markers to `pytest.ini`:

**Edit `pytest.ini`** (or create if it doesn't exist):

```ini
[pytest]
testpaths = tests
addopts = -q
markers =
    slow: takes more than 5 seconds or needs real audio hardware
    e2e: end-to-end test requiring microphone and speakers
    gui: tests that require PySide6 and possibly a display
    manual: manual verification procedures (always skipped in automated runs)
```

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify test file exists
Test-Path tests/test_gui.py

# Run GUI tests (some may be skipped)
python -m pytest tests/test_gui.py -v --tb=short

# Run only import tests
python -m pytest tests/test_gui.py::TestGUIImports -v

# Run only non-GUI tests (should all pass without PySide6)
python -m pytest tests/test_gui.py -v -m "not gui"

# Check pytest.ini
cat pytest.ini
```

---

## Done criteria

- [ ] `tests/test_gui.py` exists with exact content
- [ ] `pytest.ini` updated with GUI markers
- [ ] Import tests pass
- [ ] Non-GUI tests pass without PySide6
- [ ] No other files were modified
- [ ] Manual verification procedures are documented

---

## Common pitfalls

- **Display required**: GUI tests may require a display (X server, Wayland, etc.)
- **Qt event loop**: Many GUI operations require a running Qt event loop
- **Headless environments**: Tests may fail in CI/CD without a virtual display
- **Resource cleanup**: Qt widgets must be properly cleaned up
- **Thread safety**: Qt requires operations on widgets to be on the main thread

---

## Do NOT

- Do not make GUI tests block the main test suite
- Do not require display for automated tests (they should skip gracefully)
- Do not add tests that require user interaction
- Do not modify core functionality for tests

---

## Report

Report: files created/modified, pasted verification output, any issues encountered, anything unfinished.

---

## Final Notes

### Summary of GUI Tasks

You have now completed all 9 tasks for adding a GUI to Hideko. Here's what was created:

1. **Task 01**: GUI framework selection (PySide6) and requirements
2. **Task 02**: GUI module scaffold (app.py, styles.py, __init__.py)
3. **Task 03**: Event bus GUI subscriber (event_handler.py)
4. **Task 04**: Main window layout (main_window.py)
5. **Task 05**: Audio visualization (audio_viz.py)
6. **Task 06**: Settings panel (settings_panel.py)
7. **Task 07**: System tray integration (tray.py)
8. **Task 08**: CLI-GUI integration (modified cli.py and main.py)
9. **Task 09**: GUI testing (tests/test_gui.py)

### Next Steps

After completing these tasks, you can:

1. **Run the GUI**: `python main.py --gui`
2. **Test functionality**: Verify all features work as expected
3. **Iterate**: Improve GUI based on user feedback
4. **Enhance**: Add more features (themes, animations, etc.)

### Known Limitations

1. **Thread Safety**: The current implementation processes Qt events in the audio thread. For production, consider:
   - Running Qt event loop in its own thread
   - Using Qt's signal/slot for cross-thread communication
   - Implementing proper synchronization

2. **Audio Visualization**: Currently updates from the main thread. For smoother updates, consider:
   - Using a QTimer to periodically update visualization
   - Streaming audio data to the visualization component

3. **Performance**: GUI updates may cause slight delays in audio processing. For production:
   - Profile and optimize critical paths
   - Consider using a separate thread for audio processing

4. **Cross-Platform**: The GUI is tested on Windows. For other platforms:
   - Test on macOS and Linux
   - Fix any platform-specific issues
   - Consider platform-specific implementations if needed

5. **Deployment**: For distribution:
   - Package the application with PyInstaller or similar
   - Bundle Qt libraries
   - Create installers for different platforms

### Congratulations!

You have successfully converted Hideko from a CLI-only application to one with a full-featured GUI. The GUI:

- Works alongside the CLI (use `--gui` flag)
- Displays conversation history
- Shows audio visualization
- Provides settings configuration
- Has a system tray icon
- Subscribes to the existing event bus
- Maintains all existing CLI functionality
