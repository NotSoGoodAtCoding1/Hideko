# Task 07 — System Tray Integration

**Phase:** GUI Components · **Depends on:** task 04 · **Blocks:** task 08 · **Effort:** 30-45 min

---

## Goal

Create a system tray icon for Hideko that allows users to control the application from the system tray. This provides a convenient way to access the application without keeping the main window open.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `gui/tray.py` — **create only this** |
| Depends on | task 04 (MainWindow exists) |
| Blocks | task 08 |
| Time budget | ~40 min |

---

## Step 1 — Verify dependencies

```powershell
# Verify GUI modules
python -c "from gui.main_window import MainWindow; from gui.app import GUIApp; print('GUI modules OK')"

# Verify PySide6 has QSystemTrayIcon
python -c "from PySide6.QtWidgets import QSystemTrayIcon; from PySide6.QtGui import QIcon; print('Qt tray imports OK')"
```

All must succeed. If any fail, stop and report.

---

## Step 2 — Create `gui/tray.py`

This module provides system tray icon functionality for Hideko.

```python
"""System tray icon for Hideko GUI.

This module provides the SystemTray class which creates and manages
a system tray icon for Hideko with a context menu for controlling
the application.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app import GUIApp

from PySide6.QtCore import Qt, QObject, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QSystemTrayIcon,
    QMenu,
    QAction,
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from gui.styles import Style

logger = logging.getLogger(__name__)


class SystemTray(QObject):
    """System tray icon for Hideko.
    
    Provides a tray icon with a context menu for controlling the application.
    The icon changes based on the application state (idle, listening, speaking).
    """
    
    # Signals
    show_requested = Signal()
    hide_requested = Signal()
    mute_toggled = Signal(bool)
    quit_requested = Signal()
    
    def __init__(self, app: GUIApp) -> None:
        """Initialize the system tray icon.
        
        Args:
            app: The GUI application instance.
        """
        super().__init__()
        self.app = app
        
        # State
        self._muted = False
        self._listening = False
        self._speaking = False
        
        # Create icon
        self._icon = self._create_icon()
        
        # Create tray icon
        self._tray_icon = QSystemTrayIcon(self._icon)
        self._tray_icon.setToolTip("Hideko - Local Voice Assistant")
        
        # Create menu
        self._create_menu()
        
        # Connect signals
        self._tray_icon.activated.connect(self._on_tray_activated)
        
        # Set the tray icon
        self._tray_icon.setIcon(self._icon)
        
        # Show the tray icon
        self._tray_icon.show()
        
        logger.info("System tray icon created")
    
    def _create_icon(self) -> QIcon:
        """Create the default icon.
        
        Creates a simple icon with the letter H for Hideko.
        In a production app, this would be replaced with a proper icon file.
        
        Returns:
            A QIcon instance.
        """
        # Create a simple icon programmatically
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a circle background
        colors = Style.colors
        bg_color = QColor(*colors.primary)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(4, 4, 56, 56)
        
        # Draw H letter
        text_color = QColor(255, 255, 255)
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        painter.drawText(18, 45, "H")
        
        painter.end()
        
        return QIcon(pixmap)
    
    def _create_listening_icon(self) -> QIcon:
        """Create an icon for listening state.
        
        Returns:
            A QIcon instance with a listening indicator.
        """
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a circle background with different color
        colors = Style.colors
        bg_color = QColor(0, 180, 0)  # Green for listening
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(4, 4, 56, 56)
        
        # Draw H letter
        text_color = QColor(255, 255, 255)
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        painter.drawText(18, 45, "H")
        
        # Draw listening indicator (small circle)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(45, 10, 14, 14)
        
        painter.end()
        
        return QIcon(pixmap)
    
    def _create_speaking_icon(self) -> QIcon:
        """Create an icon for speaking state.
        
        Returns:
            A QIcon instance with a speaking indicator.
        """
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a circle background with different color
        bg_color = QColor(0, 150, 255)  # Blue for speaking
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(4, 4, 56, 56)
        
        # Draw H letter
        text_color = QColor(255, 255, 255)
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        painter.drawText(18, 45, "H")
        
        # Draw speaking indicator (sound waves)
        painter.setPen(QColor(255, 255, 255))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(3):
            painter.drawArc(48 - i * 5, 15, 10 + i * 5, 10 + i * 5, 45 * 16, 90 * 16)
        
        painter.end()
        
        return QIcon(pixmap)
    
    def _create_muted_icon(self) -> QIcon:
        """Create an icon for muted state.
        
        Returns:
            A QIcon instance with a muted indicator.
        """
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a circle background with muted color
        bg_color = QColor(128, 128, 128)  # Gray for muted
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(4, 4, 56, 56)
        
        # Draw H letter
        text_color = QColor(255, 255, 255)
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        painter.drawText(18, 45, "H")
        
        # Draw mute indicator (slash)
        painter.setPen(QColor(255, 255, 255))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(20, 20, 44, 44)
        
        painter.end()
        
        return QIcon(pixmap)
    
    def _create_menu(self) -> None:
        """Create the context menu for the tray icon."""
        menu = QMenu()
        
        # Show action
        show_action = QAction("Show", menu)
        show_action.triggered.connect(lambda: self.show_requested.emit())
        menu.addAction(show_action)
        
        # Hide action
        hide_action = QAction("Hide", menu)
        hide_action.triggered.connect(lambda: self.hide_requested.emit())
        menu.addAction(hide_action)
        
        # Separator
        menu.addSeparator()
        
        # Mute action
        self._mute_action = QAction("Mute", menu)
        self._mute_action.setCheckable(True)
        self._mute_action.setChecked(self._muted)
        self._mute_action.triggered.connect(self._on_mute_triggered)
        menu.addAction(self._mute_action)
        
        # Separator
        menu.addSeparator()
        
        # Quit action
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(lambda: self.quit_requested.emit())
        menu.addAction(quit_action)
        
        self._tray_icon.setContextMenu(menu)
    
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon activation.
        
        Args:
            reason: The activation reason.
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click - toggle window
            if self.app.is_visible:
                self.hide_requested.emit()
            else:
                self.show_requested.emit()
    
    def _on_mute_triggered(self, checked: bool) -> None:
        """Handle mute action triggered.
        
        Args:
            checked: Whether mute is now checked.
        """
        self._muted = checked
        self._update_icon()
        self.mute_toggled.emit(checked)
    
    def set_muted(self, muted: bool) -> None:
        """Set the muted state.
        
        Args:
            muted: True if muted, False otherwise.
        """
        self._muted = muted
        if self._mute_action:
            self._mute_action.setChecked(muted)
        self._update_icon()
    
    def set_listening(self, listening: bool) -> None:
        """Set the listening state.
        
        Args:
            listening: True if currently listening, False otherwise.
        """
        self._listening = listening
        self._update_icon()
    
    def set_speaking(self, speaking: bool) -> None:
        """Set the speaking state.
        
        Args:
            speaking: True if currently speaking, False otherwise.
        """
        self._speaking = speaking
        self._update_icon()
    
    def _update_icon(self) -> None:
        """Update the tray icon based on current state."""
        if self._muted:
            icon = self._create_muted_icon()
        elif self._speaking:
            icon = self._create_speaking_icon()
        elif self._listening:
            icon = self._create_listening_icon()
        else:
            icon = self._create_icon()
        
        self._tray_icon.setIcon(icon)
    
    def show(self) -> None:
        """Show the tray icon."""
        self._tray_icon.show()
    
    def hide(self) -> None:
        """Hide the tray icon."""
        self._tray_icon.hide()
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self._tray_icon.hide()
        self._tray_icon.deleteLater()
        logger.info("System tray icon cleaned up")


# Global tray instance
_tray_instance: SystemTray | None = None


def get_tray(app: GUIApp) -> SystemTray:
    """Get or create the system tray instance.
    
    Args:
        app: The GUI application instance.
    
    Returns:
        The system tray instance.
    """
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = SystemTray(app)
    return _tray_instance


def destroy_tray() -> None:
    """Destroy the system tray instance."""
    global _tray_instance
    if _tray_instance is not None:
        _tray_instance.cleanup()
        _tray_instance = None
```

---

## Step 3 — Integrate tray icon into GUIApp

Now we need to integrate the system tray into the GUIApp class.

**Modify `gui/app.py`**:

Add tray instance to the GUIApp class:

**Add to `__init__` method** (after `self._main_window = None`):

```python
# Add this line
self._tray: SystemTray | None = None
```

**Add a method to create the tray**:

```python
def _create_tray(self) -> None:
    """Create the system tray icon."""
    try:
        from gui.tray import SystemTray
        self._tray = SystemTray(self)
        
        # Connect tray signals to app methods
        if self._tray:
            self._tray.show_requested.connect(self.show)
            self._tray.hide_requested.connect(self.hide)
            self._tray.mute_toggled.connect(self._on_tray_mute_toggled)
            self._tray.quit_requested.connect(self._on_tray_quit)
    except ImportError:
        logger.debug("System tray not available")
        self._tray = None

def _on_tray_mute_toggled(self, muted: bool) -> None:
    """Handle mute toggled from tray.
    
    Args:
        muted: Whether mute is now active.
    """
    logger.info("Tray mute toggled: %s", "muted" if muted else "unmuted")
    # This will be connected to actual mute functionality in later tasks

def _on_tray_quit(self) -> None:
    """Handle quit request from tray."""
    logger.info("Tray quit requested")
    self.close()
```

**Update `show` method**:

```python
def show(self) -> None:
    """Show the main GUI window."""
    if self._closed:
        logger.warning("Cannot show GUI: already closed")
        return
        
    if self._main_window is None:
        self._create_main_window()
        
    # Create tray icon if it doesn't exist
    if self._tray is None:
        self._create_tray()
    
    if self._main_window is not None:
        self._main_window.show()
        self._visible = True
        logger.info("GUI shown")
```

**Update `close` method**:

```python
def close(self) -> None:
    """Close the GUI application."""
    if self._closed:
        return
        
    logger.info("Closing GUI...")
    
    # Unsubscribe from events first
    self.unsubscribe_from_events()
    
    if self._main_window is not None:
        self._main_window.close()
        self._main_window = None
    
    # Clean up event handler
    if self._event_handler is not None:
        self._event_handler.cleanup()
        self._event_handler = None
    
    # Clean up tray
    if self._tray is not None:
        self._tray.cleanup()
        self._tray = None
    
    self._visible = False
    self._closed = True
    
    logger.info("GUI closed")
```

---

## Step 4 — Update event handler to connect to tray

We need to update the event handler to also update the tray icon state.

**Modify `gui/event_handler.py`**:

Update these methods to also update tray state:

```python
def _handle_listening(self, event: GUIEvent) -> None:
    """Handle listening event."""
    logger.debug("GUI: listening event received")
    
    # Set listening indicator
    if self.app._main_window is not None:
        self.app._main_window.set_listening(True)
        self.app._main_window.set_status("Listening...")
    
    # Update tray icon
    if self.app._tray is not None:
        self.app._tray.set_listening(True)
        self.app._tray.set_speaking(False)

def _handle_speaking(self, event: GUIEvent) -> None:
    """Handle speaking event."""
    text = event.data.get("text", "")
    logger.debug("GUI: speaking event - text: %s", text)
    
    # Add to conversation display
    if self.app._main_window is not None:
        self.app._main_window.add_assistant_message(text)
        self.app._main_window.set_speaking(True)
    
    # Update tray icon
    if self.app._tray is not None:
        self.app._tray.set_speaking(True)
        self.app._tray.set_listening(False)

def _handle_paused(self, event: GUIEvent) -> None:
    """Handle paused event."""
    logger.debug("GUI: paused event received")
    
    # Update status and indicators
    if self.app._main_window is not None:
        self.app._main_window.set_status("Paused")
        self.app._main_window.set_listening(False)
        self.app._main_window.set_speaking(False)
    
    # Update tray
    if self.app._tray is not None:
        self.app._tray.set_listening(False)
        self.app._tray.set_speaking(False)

def _handle_missed(self, event: GUIEvent) -> None:
    """Handle missed event (empty transcript)."""
    logger.debug("GUI: missed event received")
    
    # Show missed message
    if self.app._main_window is not None:
        self.app._main_window.add_system_message("Didn't catch that. Please try again.")
        self.app._main_window.set_listening(False)
    
    # Update tray
    if self.app._tray is not None:
        self.app._tray.set_listening(False)
```

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify file exists
Test-Path gui/tray.py

# Verify imports work
python -c "from gui.tray import SystemTray, get_tray, destroy_tray; print('tray imports OK')"

# Verify MainWindow and GUIApp still import correctly
python -c "from gui.main_window import MainWindow; from gui.app import GUIApp; print('GUI modules import OK')"

# Test tray icon creation (won't show without Qt event loop)
python -c "
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
from gui.tray import SystemTray

# Create a minimal GUIApp mock
import dataclasses
from events import EventBus

@dataclasses.dataclass
class MockGUIApp:
    is_visible: bool = False
    
config = dataclasses.dataclass(type('Config', (), {}))()
bus = EventBus()
mock_app = MockGUIApp()

# Create tray
tray = SystemTray(mock_app)

print('SystemTray created:', tray is not None)
print('Tray icon visible:', tray._tray_icon.isVisible())
"
```

---

## Done criteria

- [ ] `gui/tray.py` exists with exact content
- [ ] `gui/app.py` updated with tray integration
- [ ] `gui/event_handler.py` updated to connect to tray
- [ ] All imports work without errors
- [ ] Tray icon can be created and shows in system tray
- [ ] No other files were modified
- [ ] Tray icon changes state based on application events

---

## Common pitfalls

- **System tray not supported**: Some platforms may not support system tray icons
- **Icon visibility**: Tray icon may not appear without a running Qt event loop
- **Signal connections**: Make sure all signals are properly connected
- **Thread safety**: Tray icon updates must be on Qt main thread
- **Multiple instances**: Only one system tray icon should exist

---

## Do NOT

- Do not modify core modules
- Do not create other GUI files
- Do not add platform-specific code (Qt handles this automatically)
- Do not start task 08

---

## Report

Report: files created/modified, pasted verification output, any issues encountered, anything unfinished.
