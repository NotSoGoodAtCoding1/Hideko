# Task 04 — Main Window Layout

**Phase:** GUI Components · **Depends on:** task 03 · **Blocks:** task 05, 06, 07 · **Effort:** 60-90 min

---

## Goal

Create the main application window with conversation display, status bar, and control buttons. This is the primary user interface for Hideko.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `gui/main_window.py` — **create only this** |
| Depends on | task 03 (event handler exists) |
| Blocks | task 05, 06, 07 |
| Time budget | ~75 min |

---

## Step 1 — Verify dependencies

```powershell
# Verify GUI scaffold and event handler exist
python -c "from gui import launch_gui; from gui.app import GUIApp; from gui.event_handler import GUIEventHandler; print('Dependencies OK')"

# Verify PySide6 can create widgets
python -c "from PySide6.QtWidgets import QMainWindow, QLabel, QVBoxLayout; print('Qt widgets OK')"

# Verify styles module exists
python -c "from gui.styles import Style; print('Styles OK')"
```

All must succeed. If any fail, stop and report.

---

## Step 2 — Create `gui/main_window.py`

This is the primary window that displays the conversation and provides user controls.

```python
"""Main application window for Hideko GUI.

This module provides the MainWindow class which is the primary user interface
for the Hideko voice assistant. It displays the conversation history, status,
and provides controls for interacting with the assistant.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import AppConfig
    from gui.app import GUIApp
    from PySide6.QtWidgets import QWidget, QVBoxLayout
    from PySide6.QtGui import QCloseEvent

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QPushButton,
    QFrame,
    QSizePolicy,
    QSpacerItem,
)
from PySide6.QtGui import QFont, QPalette, QColor

from gui.styles import Style, Sizes, Spacing

logger = logging.getLogger(__name__)


class ConversationDisplay(QTextBrowser):
    """Widget for displaying conversation history.
    
    This is a read-only text display that shows the conversation between
    the user and Hideko.
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the conversation display.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self) -> None:
        """Initialize the UI."""
        sizes = Style.sizes
        spacing = Style.spacing
        colors = Style.colors
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Set margins
        self.setContentsMargins(
            spacing.md, spacing.md, spacing.md, spacing.md
        )
        
        # Set read-only
        self.setReadOnly(True)
        
        # Set background and text colors
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, 
                        QColor(*colors.background_secondary))
        palette.setColor(QPalette.ColorRole.Text, 
                        QColor(*colors.text))
        self.setPalette(palette)
        
        # Set font
        font = QFont(Style.fonts.family, Style.fonts.size_medium)
        self.setFont(font)
        
        # Set vertical scrollbar policy
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Initial content
        self.append("<i>Hideko is starting up...</i>")
    
    def add_user_message(self, text: str) -> None:
        """Add a user message to the conversation.
        
        Args:
            text: The user's message text.
        """
        self.append(f"<b>You:</b> {text}")
        self._scroll_to_bottom()
    
    def add_assistant_message(self, text: str) -> None:
        """Add an assistant message to the conversation.
        
        Args:
            text: The assistant's message text.
        """
        self.append(f"<b>Hideko:</b> {text}")
        self._scroll_to_bottom()
    
    def add_system_message(self, text: str) -> None:
        """Add a system message to the conversation.
        
        Args:
            text: The system message text.
        """
        self.append(f"<i><font color='gray'>{text}</font></i>")
        self._scroll_to_bottom()
    
    def _scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the display."""
        self.ensureCursorVisible()


class StatusBar(QFrame):
    """Status bar widget for displaying application status.
    
    Shows current status, timing information, and other status indicators.
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the status bar.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self._status_label = QLabel("Ready")
        self._timing_label = QLabel("")
        self._init_ui()
    
    def _init_ui(self) -> None:
        """Initialize the UI."""
        spacing = Style.spacing
        colors = Style.colors
        
        # Set frame style
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFrameShadow(QFrame.Shadow.Plain)
        
        # Set background color
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, 
                        QColor(*colors.background_secondary))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(spacing.md, spacing.sm, spacing.md, spacing.sm)
        layout.setSpacing(spacing.md)
        
        # Add status label
        self._status_label.setStyleSheet("QLabel { color: rgb(%d, %d, %d); }" % 
                                         colors.text)
        layout.addWidget(self._status_label)
        
        # Add spacer
        layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        ))
        
        # Add timing label
        self._timing_label.setStyleSheet("QLabel { color: rgb(%d, %d, %d); }" % 
                                         colors.text_secondary)
        layout.addWidget(self._timing_label)
    
    def set_status(self, text: str) -> None:
        """Set the status text.
        
        Args:
            text: The status text to display.
        """
        self._status_label.setText(text)
    
    def set_timing(self, stt: float, resp: float, tts: float, play: float) -> None:
        """Set the timing information.
        
        Args:
            stt: Speech-to-text time in seconds.
            resp: Response generation time in seconds.
            tts: Text-to-speech time in seconds.
            play: Audio playback time in seconds.
        """
        total = stt + resp + tts + play
        self._timing_label.setText(
            f"STT: {stt:.1f}s | Resp: {resp:.2f}s | TTS: {tts:.1f}s | Play: {play:.1f}s | Total: {total:.1f}s"
        )
    
    def clear_timing(self) -> None:
        """Clear the timing display."""
        self._timing_label.setText("")


class ControlPanel(QFrame):
    """Control panel with action buttons.
    
    Provides buttons for controlling the application (mute, listen, etc.).
    """
    
    # Signal for mute button clicks
    mute_clicked = Signal(bool)
    listen_clicked = Signal()
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the control panel.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self._mute_button: QPushButton | None = None
        self._listen_button: QPushButton | None = None
        self._muted = False
        self._init_ui()
    
    def _init_ui(self) -> None:
        """Initialize the UI."""
        spacing = Style.spacing
        sizes = Style.sizes
        colors = Style.colors
        
        # Set frame style
        self.setFrameShape(QFrame.Shape.NoFrame)
        
        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(spacing.md, spacing.sm, spacing.md, spacing.sm)
        layout.setSpacing(spacing.md)
        
        # Create mute button
        self._mute_button = QPushButton("Mute")
        self._mute_button.setFixedHeight(sizes.button_height)
        self._mute_button.setStyleSheet(
            f"""QPushButton {{
                background-color: rgb({colors.primary[0]}, {colors.primary[1]}, {colors.primary[2]});
                color: white;
                border: none;
                border-radius: 4px;
                padding: {spacing.sm}px {spacing.md}px;
            }}
            QPushButton:hover {{
                background-color: rgb({colors.primary_hover[0]}, {colors.primary_hover[1]}, {colors.primary_hover[2]});
            }}
            QPushButton:pressed {{
                background-color: rgb({colors.primary_pressed[0]}, {colors.primary_pressed[1]}, {colors.primary_pressed[2]});
            }}
            """
        )
        self._mute_button.clicked.connect(self._on_mute_clicked)
        layout.addWidget(self._mute_button)
        
        # Create listen button
        self._listen_button = QPushButton("Listen")
        self._listen_button.setFixedHeight(sizes.button_height)
        self._listen_button.setStyleSheet(
            f"""QPushButton {{
                background-color: rgb({colors.primary[0]}, {colors.primary[1]}, {colors.primary[2]});
                color: white;
                border: none;
                border-radius: 4px;
                padding: {spacing.sm}px {spacing.md}px;
            }}
            QPushButton:hover {{
                background-color: rgb({colors.primary_hover[0]}, {colors.primary_hover[1]}, {colors.primary_hover[2]});
            }}
            QPushButton:pressed {{
                background-color: rgb({colors.primary_pressed[0]}, {colors.primary_pressed[1]}, {colors.primary_pressed[2]});
            }}
            """
        )
        self._listen_button.clicked.connect(self._on_listen_clicked)
        layout.addWidget(self._listen_button)
        
        # Add spacer
        layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        ))
    
    def _on_mute_clicked(self) -> None:
        """Handle mute button click."""
        self._muted = not self._muted
        if self._mute_button:
            self._mute_button.setText("Unmute" if self._muted else "Mute")
        self.mute_clicked.emit(self._muted)
    
    def _on_listen_clicked(self) -> None:
        """Handle listen button click."""
        self.listen_clicked.emit()
    
    def set_muted(self, muted: bool) -> None:
        """Set the mute state.
        
        Args:
            muted: True if muted, False otherwise.
        """
        self._muted = muted
        if self._mute_button:
            self._mute_button.setText("Unmute" if muted else "Mute")


class MainWindow(QMainWindow):
    """Main application window for Hideko.
    
    This is the primary window that displays the conversation history,
    status information, and provides user controls.
    """
    
    def __init__(self, config: AppConfig, app: GUIApp) -> None:
        """Initialize the main window.
        
        Args:
            config: The application configuration.
            app: The GUI application instance.
        """
        super().__init__()
        self.config = config
        self.app = app
        
        self._conversation_display: ConversationDisplay | None = None
        self._status_bar: StatusBar | None = None
        self._control_panel: ControlPanel | None = None
        self._listening_indicator: QLabel | None = None
        self._speaking_indicator: QLabel | None = None
        
        self._init_ui()
        self._setup_connections()
        
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        sizes = Style.sizes
        spacing = Style.spacing
        colors = Style.colors
        
        # Set window properties
        self.setWindowTitle("Hideko")
        self.setMinimumSize(sizes.window_min_width, sizes.window_min_height)
        self.resize(sizes.window_default_width, sizes.window_default_height)
        
        # Create central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        main_layout.setSpacing(spacing.md)
        
        # Create conversation display
        self._conversation_display = ConversationDisplay()
        main_layout.addWidget(self._conversation_display, stretch=1)
        
        # Create indicators row
        indicators_layout = QHBoxLayout()
        indicators_layout.setSpacing(spacing.md)
        
        # Listening indicator
        self._listening_indicator = QLabel("")
        self._listening_indicator.setStyleSheet(
            """QLabel {
                min-width: 16px;
                min-height: 16px;
                border-radius: 8px;
                background-color: rgb(200, 200, 200);
            }"""
        )
        indicators_layout.addWidget(self._listening_indicator)
        
        # Speaking indicator
        self._speaking_indicator = QLabel("")
        self._speaking_indicator.setStyleSheet(
            """QLabel {
                min-width: 16px;
                min-height: 16px;
                border-radius: 8px;
                background-color: rgb(200, 200, 200);
            }"""
        )
        indicators_layout.addWidget(self._speaking_indicator)
        
        # Add spacer
        indicators_layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        ))
        
        main_layout.addLayout(indicators_layout)
        
        # Create control panel
        self._control_panel = ControlPanel()
        main_layout.addWidget(self._control_panel)
        
        # Create status bar
        self._status_bar = StatusBar()
        main_layout.addWidget(self._status_bar)
        
        # Apply stylesheet
        self._apply_stylesheet()
        
    def _apply_stylesheet(self) -> None:
        """Apply the global stylesheet to the window."""
        self.setStyleSheet(Style.qss())
    
    def _setup_connections(self) -> None:
        """Set up signal connections."""
        if self._control_panel:
            self._control_panel.mute_clicked.connect(self._on_mute_clicked)
            self._control_panel.listen_clicked.connect(self._on_listen_clicked)
    
    def _on_mute_clicked(self, muted: bool) -> None:
        """Handle mute button click.
        
        Args:
            muted: True if muted, False otherwise.
        """
        logger.info("Mute clicked: %s", "muted" if muted else "unmuted")
        # This will be connected to actual mute functionality in later tasks
    
    def _on_listen_clicked(self) -> None:
        """Handle listen button click."""
        logger.info("Listen button clicked")
        # This will be connected to actual listen functionality in later tasks
    
    def add_user_message(self, text: str) -> None:
        """Add a user message to the conversation display.
        
        Args:
            text: The message text.
        """
        if self._conversation_display:
            self._conversation_display.add_user_message(text)
    
    def add_assistant_message(self, text: str) -> None:
        """Add an assistant message to the conversation display.
        
        Args:
            text: The message text.
        """
        if self._conversation_display:
            self._conversation_display.add_assistant_message(text)
    
    def add_system_message(self, text: str) -> None:
        """Add a system message to the conversation display.
        
        Args:
            text: The message text.
        """
        if self._conversation_display:
            self._conversation_display.add_system_message(text)
    
    def set_status(self, text: str) -> None:
        """Set the status bar text.
        
        Args:
            text: The status text.
        """
        if self._status_bar:
            self._status_bar.set_status(text)
    
    def set_listening(self, active: bool) -> None:
        """Set the listening indicator state.
        
        Args:
            active: True if currently listening, False otherwise.
        """
        if self._listening_indicator:
            if active:
                self._listening_indicator.setStyleSheet(
                    """QLabel {
                        min-width: 16px;
                        min-height: 16px;
                        border-radius: 8px;
                        background-color: rgb(0, 200, 0);
                    }"""
                )
            else:
                self._listening_indicator.setStyleSheet(
                    """QLabel {
                        min-width: 16px;
                        min-height: 16px;
                        border-radius: 8px;
                        background-color: rgb(200, 200, 200);
                    }"""
                )
    
    def set_speaking(self, active: bool) -> None:
        """Set the speaking indicator state.
        
        Args:
            active: True if currently speaking, False otherwise.
        """
        if self._speaking_indicator:
            if active:
                self._speaking_indicator.setStyleSheet(
                    """QLabel {
                        min-width: 16px;
                        min-height: 16px;
                        border-radius: 8px;
                        background-color: rgb(0, 150, 255);
                    }"""
                )
            else:
                self._speaking_indicator.setStyleSheet(
                    """QLabel {
                        min-width: 16px;
                        min-height: 16px;
                        border-radius: 8px;
                        background-color: rgb(200, 200, 200);
                    }"""
                )
    
    def set_timing(self, stt: float, resp: float, tts: float, play: float) -> None:
        """Set the timing display.
        
        Args:
            stt: Speech-to-text time in seconds.
            resp: Response generation time in seconds.
            tts: Text-to-speech time in seconds.
            play: Audio playback time in seconds.
        """
        if self._status_bar:
            self._status_bar.set_timing(stt, resp, tts, play)
    
    def clear_timing(self) -> None:
        """Clear the timing display."""
        if self._status_bar:
            self._status_bar.clear_timing()
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event.
        
        Args:
            event: The close event.
        """
        logger.info("Main window close event")
        # Hide instead of close if we want to keep running
        # For now, just accept the close
        event.accept()
        
        # Notify the app that the window is closed
        self.app._visible = False
```

---

## Step 3 — Update `gui/app.py` to use MainWindow

We need to update the `_create_main_window` method to actually create a MainWindow:

**Replace the `_create_main_window` method in `gui/app.py` with**:

```python
def _create_main_window(self) -> None:
    """Create the main window instance."""
    try:
        from gui.main_window import MainWindow
        self._main_window = MainWindow(self.config, self)
    except ImportError as e:
        logger.error("Failed to import MainWindow: %s", e)
        self._main_window = None
```

---

## Step 4 — Update `gui/event_handler.py` to use MainWindow methods

Now we need to update the event handler to call the MainWindow methods when events are received. This connects the event bus to the actual UI updates.

**Update these methods in `gui/event_handler.py`**:

```python
def _handle_heard(self, event: GUIEvent) -> None:
    """Handle heard event."""
    text = event.data.get("text", "")
    logger.debug("GUI: heard event - text: %s", text)
    
    # Add to conversation display
    if self.app._main_window is not None:
        self.app._main_window.add_user_message(text)

def _handle_speaking(self, event: GUIEvent) -> None:
    """Handle speaking event."""
    text = event.data.get("text", "")
    logger.debug("GUI: speaking event - text: %s", text)
    
    # Add to conversation display
    if self.app._main_window is not None:
        self.app._main_window.add_assistant_message(text)
    
    # Set speaking indicator
    if self.app._main_window is not None:
        self.app._main_window.set_speaking(True)

def _handle_listening(self, event: GUIEvent) -> None:
    """Handle listening event."""
    logger.debug("GUI: listening event received")
    
    # Set listening indicator
    if self.app._main_window is not None:
        self.app._main_window.set_listening(True)
        self.app._main_window.set_status("Listening...")

def _handle_thinking(self, event: GUIEvent) -> None:
    """Handle thinking event."""
    logger.debug("GUI: thinking event received")
    
    # Update status
    if self.app._main_window is not None:
        self.app._main_window.set_status("Thinking...")
        self.app._main_window.set_listening(False)

def _handle_ready(self, event: GUIEvent) -> None:
    """Handle ready event."""
    stt_s = event.data.get("stt_s", 0.0)
    trigger_count = event.data.get("trigger_count", 0)
    logger.info("GUI: ready - STT warmup %.1fs, %d triggers loaded", 
                stt_s, trigger_count)
    
    # Update status
    if self.app._main_window is not None:
        self.app._main_window.set_status(f"Ready ({trigger_count} triggers)")

def _handle_paused(self, event: GUIEvent) -> None:
    """Handle paused event."""
    logger.debug("GUI: paused event received")
    
    # Update status and indicators
    if self.app._main_window is not None:
        self.app._main_window.set_status("Paused")
        self.app._main_window.set_listening(False)
        self.app._main_window.set_speaking(False)

def _handle_turn_timing(self, event: GUIEvent) -> None:
    """Handle turn_timing event."""
    stt = event.data.get("stt", 0.0)
    resp = event.data.get("resp", 0.0)
    tts = event.data.get("tts", 0.0)
    play = event.data.get("play", 0.0)
    total = event.data.get("total", 0.0)
    logger.debug("GUI: timing - STT:%.1fs Resp:%.2fs TTS:%.1fs Play:%.1fs Total:%.1fs",
                 stt, resp, tts, play, total)
    
    # Update timing display
    if self.app._main_window is not None:
        self.app._main_window.set_timing(stt, resp, tts, play)

def _handle_error(self, event: GUIEvent) -> None:
    """Handle error event."""
    message = event.data.get("message", "Unknown error")
    exit_code = event.data.get("exit_code", 1)
    logger.error("GUI: error event - message: %s, exit_code: %d", 
                 message, exit_code)
    
    # Show error in conversation
    if self.app._main_window is not None:
        self.app._main_window.add_assistant_message(f"Error: {message}")
        self.app._main_window.set_status(f"Error (code: {exit_code})")

def _handle_missed(self, event: GUIEvent) -> None:
    """Handle missed event (empty transcript)."""
    logger.debug("GUI: missed event received")
    
    # Show missed message
    if self.app._main_window is not None:
        self.app._main_window.add_system_message("Didn't catch that. Please try again.")
        self.app._main_window.set_listening(False)

def _handle_startup(self, event: GUIEvent) -> None:
    """Handle startup event."""
    logger.debug("GUI: startup event received")
    
    # Update status
    if self.app._main_window is not None:
        self.app._main_window.set_status("Starting up...")

def _handle_goodbye(self, event: GUIEvent) -> None:
    """Handle goodbye event."""
    logger.debug("GUI: goodbye event received")
    
    # Update status
    if self.app._main_window is not None:
        self.app._main_window.set_status("Goodbye!")

def _handle_shutdown(self, event: GUIEvent) -> None:
    """Handle shutdown event."""
    logger.info("GUI: shutdown event received")
    
    # Clear indicators
    if self.app._main_window is not None:
        self.app._main_window.set_listening(False)
        self.app._main_window.set_speaking(False)
        self.app._main_window.clear_timing()
    
    # Continue with normal shutdown
    self.unsubscribe()
    self.app.close()

def _handle_calibrating(self, event: GUIEvent) -> None:
    """Handle calibrating event."""
    logger.debug("GUI: calibrating event received")
    
    # Update status
    if self.app._main_window is not None:
        self.app._main_window.set_status("Calibrating microphone...")

def _handle_wake_detected(self, event: GUIEvent) -> None:
    """Handle wake_detected event."""
    text = event.data.get("text", "")
    latency = event.data.get("latency_s", 0.0)
    logger.debug("GUI: wake word detected - text: %s, latency: %.1fs", 
                 text, latency)
    
    # Show wake word notification
    if self.app._main_window is not None:
        self.app._main_window.add_system_message(f"Wake word detected: {text}")
```

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify file exists
Test-Path gui/main_window.py

# Verify imports work
python -c "from gui.main_window import MainWindow, ConversationDisplay, StatusBar, ControlPanel; print('main_window imports OK')"

# Verify GUI can be created (without showing)
python -c "
from gui.app import GUIApp
from events import EventBus

# Create a minimal config
import dataclasses
@dataclasses.dataclass
class MinimalConfig:
    pass

bus = EventBus()
config = MinimalConfig()

# Try to create GUIApp (won't show without Qt event loop)
try:
    from gui import launch_gui
    gui_app = launch_gui(config, bus)
    print('GUIApp created:', gui_app is not None)
    if gui_app:
        print('GUIApp type:', type(gui_app).__name__)
        # Don't call show() as we don't have a running Qt event loop
except Exception as e:
    print('Error:', e)
"
```

---

## Done criteria

- [ ] `gui/main_window.py` exists with exact content
- [ ] `gui/app.py` updated with MainWindow integration
- [ ] `gui/event_handler.py` updated with MainWindow connections
- [ ] All imports work without errors
- [ ] No other files were modified
- [ ] MainWindow can be instantiated
- [ ] Event handler methods are connected to MainWindow

---

## Common pitfalls

- **Qt not initialized**: Creating QWidget instances without QApplication fails
- **Thread safety**: Don't create Qt widgets from non-main threads
- **Circular imports**: Be careful with import order
- **Missing TYPE_CHECKING**: Type hints with TYPE_CHECKING must be handled correctly
- **Style issues**: Qt style sheets may not apply correctly if selectors are wrong

---

## Do NOT

- Do not modify core modules (`main.py`, `audio_manager.py`, etc.)
- Do not create other GUI files (audio_viz, settings, tray are later tasks)
- Do not add any actual functionality beyond the UI structure
- Do not start task 05

---

## Report

Report: files created/modified, pasted verification output, any issues encountered, anything unfinished.
