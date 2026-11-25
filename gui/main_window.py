"""Main application window for Hideko GUI.

This module provides the MainWindow class which is the primary user interface
for the Hideko voice assistant. It displays the conversation history, status,
and provides controls for interacting with the assistant.
"""

from __future__ import annotations

import logging
import numpy as np
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
        self._audio_viz: AudioVisualizer | None = None
        
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
        
        # Create main layout (vertical: conversation row + status bar at bottom)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        main_layout.setSpacing(spacing.md)
        
        # Create horizontal split area: conversation (left) + sidebar (right)
        split_area = QWidget()
        split_layout = QHBoxLayout(split_area)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(spacing.md)
        
        # Create conversation area (left side, takes most space)
        conversation_area = QWidget()
        conversation_layout = QVBoxLayout(conversation_area)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        conversation_layout.setSpacing(spacing.md)
        
        # Create conversation display
        self._conversation_display = ConversationDisplay()
        conversation_layout.addWidget(self._conversation_display, stretch=1)
        
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
        
        conversation_layout.addLayout(indicators_layout)
        
        # Create control panel
        self._control_panel = ControlPanel()
        conversation_layout.addWidget(self._control_panel)
        
        # Add conversation area to split layout
        split_layout.addWidget(conversation_area, stretch=3)
        
        # Create sidebar (right side)
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(spacing.md)
        
        # Add audio visualizer to sidebar
        try:
            from gui.audio_viz import AudioVisualizer
            self._audio_viz = AudioVisualizer()
            self._audio_viz.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed
            )
            sidebar_layout.addWidget(self._audio_viz)
        except ImportError:
            # audio_viz not available yet (will be in task 05)
            self._audio_viz = None
            logger.debug("Audio visualizer not available")
        
        # Add spacer to push sidebar to top
        sidebar_layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        ))
        
        split_layout.addWidget(sidebar, stretch=1)
        
        # Add split area to main layout
        main_layout.addWidget(split_area, stretch=1)
        
        # Create status bar (spans full width at bottom)
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
            text: The status text to display.
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
    
    def update_audio_visualization(self, samples: np.ndarray | None = None, level: float | None = None) -> None:
        """Update the audio visualization.
        
        Args:
            samples: Audio samples for waveform display (optional).
            level: Audio level for VU meter (optional).
        """
        if self._audio_viz is None:
            return
        
        if samples is not None:
            self._audio_viz.update_audio(samples)
        elif level is not None:
            self._audio_viz.set_level(level)
    
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
