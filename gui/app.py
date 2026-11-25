"""GUI application controller for Hideko.

This module provides the GUIApp class which manages the Qt application
lifecycle and coordinates between the event bus and GUI components.

The GUI runs alongside the audio processing loop in main.py. Qt events
are processed via process_events() calls inserted around blocking
operations in the audio thread, which keeps the window responsive and
prevents Windows from flagging it as "Not responding".
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import AppConfig
    from events import EventBus
    from gui.main_window import MainWindow
    from PySide6.QtWidgets import QApplication

from gui.event_handler import GUIEventHandler

logger = logging.getLogger(__name__)


class GUIApp:
    """Main GUI application controller.
    
    This class wraps the Qt application and manages GUI components.
    It provides methods to show, hide, and close the GUI.
    
    Qt events are processed via process_events() calls from the audio
    loop in main.py, inserted around blocking operations (STT, TTS,
    microphone reads). This keeps the window responsive and prevents
    Windows from flagging it as "Not responding" during idle periods.
    """
    
    def __init__(self, config: AppConfig, bus: EventBus) -> None:
        """Initialize the GUI application.
        
        Args:
            config: The application configuration.
            bus: The event bus to subscribe to.
        """
        self.config = config
        self.bus = bus
        self._visible = False
        self._closed = False
        
        # Qt application instance - we may share with existing or create new
        self._qapp: QApplication | None = None
        
        # GUI components (lazy initialized)
        self._main_window: MainWindow | None = None
        
        # System tray icon
        self._tray: SystemTray | None = None
        
        # Event handler
        self._event_handler: GUIEventHandler | None = None
        
        # Ensure we have a QApplication instance
        self._ensure_qapp()
        
        # Initialize components
        self._init_components()
    
    def _ensure_qapp(self) -> None:
        """Ensure a QApplication instance exists."""
        from PySide6.QtWidgets import QApplication
        
        app_instance = QApplication.instance()
        if app_instance is None:
            self._qapp = QApplication(sys.argv)
        else:
            self._qapp = app_instance

    def _on_startup_event(self, _event) -> None:
        """Ensure a QApplication exists when startup is published."""
        self._ensure_qapp()
    
    def _init_components(self) -> None:
        """Initialize GUI components (lazy loading)."""
        # Don't import MainWindow here to avoid circular imports
        # Components are created on-demand in show()
        pass
    
    def _init_event_handler(self) -> None:
        """Initialize the event handler."""
        self._event_handler = GUIEventHandler(self, self.bus)
    
    def subscribe_to_events(self) -> None:
        """Subscribe to events on the bus.
        
        Call this after the GUI is fully initialized.
        """
        if self._event_handler is None:
            self._init_event_handler()
        
        if self._event_handler is not None:
            self._event_handler.subscribe()
        
        # Also subscribe to the bus for periodic updates
        self.bus.subscribe("startup", self._on_startup_event)
    
    def unsubscribe_from_events(self) -> None:
        """Unsubscribe from events."""
        if self._event_handler is not None:
            self._event_handler.unsubscribe()
        self.bus.unsubscribe(self._on_startup_event)
    
    @property
    def qapp(self) -> QApplication | None:
        """Get the QApplication instance."""
        return self._qapp
    
    @property
    def is_visible(self) -> bool:
        """Check if the GUI is currently visible."""
        return self._visible
    
    @property
    def is_closed(self) -> bool:
        """Check if the GUI has been closed."""
        return self._closed
    
    def show(self) -> None:
        """Show the main GUI window.
        
        Creates the main window if it doesn't exist, then shows it.
        Forces Qt to process pending events so the window contents are
        laid out and painted immediately (fixes empty-window-on-launch).
        """
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
            # Force Qt to process pending show/paint events so the
            # window contents are visible immediately rather than
            # waiting for the next process_events() call in the audio loop.
            if self._qapp is not None:
                self._qapp.processEvents()
            self._visible = True
            logger.info("GUI shown")
    
    def hide(self) -> None:
        """Hide the main GUI window."""
        if self._main_window is not None:
            self._main_window.hide()
            self._visible = False
            logger.info("GUI hidden")
    
    def close(self) -> None:
        """Close the GUI application.
        
        Closes all windows and prepares for shutdown.
        """
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
    
    def _create_main_window(self) -> None:
        """Create the main window instance."""
        # Import here to avoid circular dependencies
        # Task 04 will create the actual MainWindow class
        try:
            from gui.main_window import MainWindow
            self._main_window = MainWindow(self.config, self)
            
            # Connect main window mute signal to handler
            if self._main_window is not None and hasattr(self._main_window, 'mute_clicked'):
                self._main_window.mute_clicked.connect(self._on_mute_toggled)
        except ImportError:
            # MainWindow not yet created - this is expected before task 04
            logger.debug("MainWindow not yet available")
            self._main_window = None
    
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
    
    def _on_mute_toggled(self, muted: bool) -> None:
        """Handle mute toggled from any GUI source (tray or main window).
        
        Args:
            muted: Whether mute is now active.
        """
        logger.info("Mute toggled: %s", "muted" if muted else "unmuted")
        # Publish event to bus for HidekoApp to handle
        self.bus.publish("mute_toggle", muted=muted)
        
        # Update tray icon state
        if self._tray is not None:
            self._tray.set_muted(muted)
        
        # Update main window mute button state
        if self._main_window is not None:
            self._main_window.set_muted(muted)
    
    def _on_tray_mute_toggled(self, muted: bool) -> None:
        """Handle mute toggled from tray. Forwards to main handler.
        
        Args:
            muted: Whether mute is now active.
        """
        self._on_mute_toggled(muted)
    
    def _on_tray_quit(self) -> None:
        """Handle quit request from tray."""
        logger.info("Tray quit requested")
        self.close()
    
    def exec(self) -> int:
        """Execute the Qt event loop.
        
        This blocks until the application exits.
        
        Returns:
            The exit code.
        """
        if self._qapp is None:
            logger.error("No QApplication instance")
            return 1
            
        return self._qapp.exec()
    
    def process_events(self) -> None:
        """Process pending Qt events without blocking.
        
        Call this periodically from the main loop to keep the GUI
        responsive and prevent Windows from flagging the window as
        "Not responding" during long blocking operations.
        """
        if self._qapp is not None:
            self._qapp.processEvents()

    def update_audio_visualization(self, samples) -> None:
        """Forward audio samples to the main window's visualizer.
        
        Args:
            samples: Raw audio samples from the microphone (numpy array).
        """
        if self._main_window is None or not self._visible:
            return
        self._main_window.update_audio_visualization(samples=samples)
