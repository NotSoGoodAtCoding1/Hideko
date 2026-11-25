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
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction

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
        
        # Create icons once and reuse on state changes.
        self._icons = {
            "idle": self._create_icon(),
            "listening": self._create_listening_icon(),
            "speaking": self._create_speaking_icon(),
            "muted": self._create_muted_icon(),
        }

        # Create tray icon
        self._tray_icon = QSystemTrayIcon(self._icons["idle"])
        self._tray_icon.setToolTip("Hideko - Local Voice Assistant")
        
        # Create menu
        self._create_menu()
        
        # Connect signals
        self._tray_icon.activated.connect(self._on_tray_activated)
        
        # Set the tray icon
        self._tray_icon.setIcon(self._icons["idle"])
        
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
            key = "muted"
        elif self._speaking:
            key = "speaking"
        elif self._listening:
            key = "listening"
        else:
            key = "idle"
        self._tray_icon.setIcon(self._icons[key])
    
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
