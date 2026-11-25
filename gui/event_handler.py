"""Event bus subscriber for GUI updates.

This module provides the GUIEventHandler class which subscribes to the
application event bus and translates events into GUI updates.

All event handling happens on the Qt main thread to ensure thread safety.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from config import AppConfig
    from events import Event, EventBus
    from gui.app import GUIApp

logger = logging.getLogger(__name__)


# Type alias for event handlers (using string annotation to avoid forward reference issues)
EventHandler = Callable[["Event"], None]


@dataclass(frozen=True)
class GUIEvent:
    """Represents a GUI update request from an event.
    
    This is used to queue updates that need to happen on the main thread.
    """
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


class GUIEventHandler:
    """Subscribes to event bus and updates GUI.
    
    This class bridges the core application's event bus with the GUI.
    It ensures all GUI updates happen on the Qt main thread.
    
    The handler subscribes to all relevant events and translates them
    into method calls on the GUIApp or its components.
    """
    
    # Mapping of event kinds to handler methods
    # These are called when the corresponding event is received
    EVENT_HANDLERS = {
        "startup": "_handle_startup",
        "calibrating": "_handle_calibrating",
        "ready": "_handle_ready",
        "listening": "_handle_listening",
        "paused": "_handle_paused",
        "wake_detected": "_handle_wake_detected",
        "thinking": "_handle_thinking",
        "heard": "_handle_heard",
        "speaking": "_handle_speaking",
        "missed": "_handle_missed",
        "turn_timing": "_handle_turn_timing",
        "error": "_handle_error",
        "goodbye": "_handle_goodbye",
        "shutdown": "_handle_shutdown",
    }
    
    def __init__(self, app: GUIApp, bus: EventBus) -> None:
        """Initialize the GUI event handler.
        
        Args:
            app: The GUI application instance.
            bus: The event bus to subscribe to.
        """
        self.app = app
        self.bus = bus
        self._handler_id: int | None = None
        self._pending_events: list[GUIEvent] = []
        
        # Try to import Qt to check if we're on the main thread
        try:
            from PySide6.QtCore import QThread
            self._QThread = QThread
        except ImportError:
            self._QThread = None
        
        # Connect to Qt's main thread processing
        self._setup_qt_integration()
        
    def _setup_qt_integration(self) -> None:
        """Set up Qt-specific integration for cross-thread updates."""
        try:
            from PySide6.QtCore import QObject, Signal, Slot, QTimer
            
            # Create a QObject to receive events from other threads
            class EventRelay(QObject):
                event_received = Signal(GUIEvent)
                
                def __init__(self, handler: GUIEventHandler) -> None:
                    super().__init__()
                    self.handler = handler
                    self.event_received.connect(self.handler._process_event)
            
            self._relay = EventRelay(self)
            
            # Set up timer for fallback queue processing (started on demand).
            self._processing_timer = QTimer()
            self._processing_timer.setInterval(16)  # ~60 FPS
            self._processing_timer.timeout.connect(self._process_pending)
            
        except ImportError:
            # Qt not available, events will be processed synchronously
            self._relay = None
            self._processing_timer = None
            logger.debug("Qt not available, using synchronous event processing")
    
    def subscribe(self) -> None:
        """Subscribe to all relevant events on the bus.
        
        This registers the handler to receive events from the bus.
        """
        if self._handler_id is not None:
            # Already subscribed
            return
        
        self._handler_id = id(self)
        self.bus.subscribe(
            list(self.EVENT_HANDLERS.keys()),
            self._on_event
        )
        logger.info("GUI event handler subscribed to %d event types", 
                    len(self.EVENT_HANDLERS))
    
    def unsubscribe(self) -> None:
        """Unsubscribe from the event bus.
        
        This removes the handler from receiving events.
        """
        if self._handler_id is None:
            return
        
        try:
            self.bus.unsubscribe(self._on_event)
        except Exception as e:
            logger.warning("Error unsubscribing from event bus: %s", e)
        
        self._handler_id = None
        logger.info("GUI event handler unsubscribed")
    
    def _on_event(self, event: Event) -> None:
        """Handle an incoming event.
        
        This is called by the event bus when an event is published.
        It may be called from any thread, so we queue the update.
        
        Args:
            event: The event to handle.
        """
        # Create a GUI event for processing
        gui_event = GUIEvent(kind=event.kind, data=event.data)
        
        # If we're on the Qt main thread, process immediately
        # Otherwise, queue for later
        if self._relay is not None:
            # Use Qt's signal/slot for thread-safe delivery
            try:
                self._relay.event_received.emit(gui_event)
            except Exception as e:
                logger.warning("Failed to emit event via Qt signal: %s", e)
                # Fall back to queue
                self._queue_event(gui_event)
        else:
            # No Qt, process synchronously
            self._process_event(gui_event)
    
    def _queue_event(self, event: GUIEvent) -> None:
        """Queue an event for processing.
        
        Args:
            event: The event to queue.
        """
        self._pending_events.append(event)
        if self._processing_timer is not None and not self._processing_timer.isActive():
            self._processing_timer.start()
    
    def _process_pending(self) -> None:
        """Process any pending events from the queue."""
        while self._pending_events:
            event = self._pending_events.pop(0)
            self._process_event(event)
        if self._processing_timer is not None and not self._pending_events:
            self._processing_timer.stop()
    
    def _process_event(self, event: GUIEvent) -> None:
        """Process a GUI event.
        
        This calls the appropriate handler method based on the event kind.
        
        Args:
            event: The event to process.
        """
        handler_name = self.EVENT_HANDLERS.get(event.kind)
        if handler_name is None:
            logger.debug("No handler for event kind: %s", event.kind)
            return
        
        try:
            handler = getattr(self, handler_name, None)
            if handler is not None:
                handler(event)
            else:
                logger.warning("Handler method %s not found", handler_name)
        except Exception as e:
            logger.error("Error handling event %s: %s", event.kind, e)
    
    # Event handler methods
    
    def _handle_startup(self, event: GUIEvent) -> None:
        """Handle startup event."""
        logger.debug("GUI: startup event received")
        
        # Update status
        if self.app._main_window is not None:
            self.app._main_window.set_status("Starting up...")
        
        # Show main window if not already visible
        if not self.app.is_visible:
            self.app.show()
    
    def _handle_calibrating(self, event: GUIEvent) -> None:
        """Handle calibrating event."""
        logger.debug("GUI: calibrating event received")
        
        # Update status
        if self.app._main_window is not None:
            self.app._main_window.set_status("Calibrating microphone...")
    
    def _handle_ready(self, event: GUIEvent) -> None:
        """Handle ready event."""
        stt_s = event.data.get("stt_s", 0.0)
        trigger_count = event.data.get("trigger_count", 0)
        logger.info("GUI: ready - STT warmup %.1fs, %d triggers loaded", 
                    stt_s, trigger_count)
        
        # Update status
        if self.app._main_window is not None:
            self.app._main_window.set_status(f"Ready ({trigger_count} triggers)")

    def _handle_listening(self, event: GUIEvent) -> None:
        """Handle listening event."""
        logger.debug("GUI: listening event received")
        
        # Set listening indicator
        if self.app._main_window is not None:
            self.app._main_window.set_listening(True)
            self.app._main_window.set_status("Listening...")
            self.app._main_window.set_muted(False)
        
        # Update tray icon
        if self.app._tray is not None:
            self.app._tray.set_listening(True)
            self.app._tray.set_speaking(False)
            self.app._tray.set_muted(False)
    
    def _handle_paused(self, event: GUIEvent) -> None:
        """Handle paused event."""
        logger.debug("GUI: paused event received")
        
        # Update status and indicators
        if self.app._main_window is not None:
            self.app._main_window.set_status("Paused")
            self.app._main_window.set_listening(False)
            self.app._main_window.set_speaking(False)
            self.app._main_window.set_muted(True)
        
        # Update tray
        if self.app._tray is not None:
            self.app._tray.set_listening(False)
            self.app._tray.set_speaking(False)
            self.app._tray.set_muted(True)
    
    def _handle_wake_detected(self, event: GUIEvent) -> None:
        """Handle wake_detected event."""
        text = event.data.get("text", "")
        latency = event.data.get("latency_s", 0.0)
        logger.debug("GUI: wake word detected - text: %s, latency: %.1fs", 
                     text, latency)
        
        # Show wake word notification
        if self.app._main_window is not None:
            self.app._main_window.add_system_message(f"Wake word detected: {text}")
    
    def _handle_thinking(self, event: GUIEvent) -> None:
        """Handle thinking event."""
        logger.debug("GUI: thinking event received")
        
        # Update status
        if self.app._main_window is not None:
            self.app._main_window.set_status("Thinking...")
            self.app._main_window.set_listening(False)
    
    def _handle_heard(self, event: GUIEvent) -> None:
        """Handle heard event."""
        text = event.data.get("text", "")
        logger.debug("GUI: heard event - text: %s", text)
        
        # Add user message to conversation display
        if self.app._main_window is not None:
            self.app._main_window.add_user_message(text)
    
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
            self.app._main_window.add_system_message(f"Error: {message}")
            self.app._main_window.set_status(f"Error (code: {exit_code})")
    
    def _handle_goodbye(self, event: GUIEvent) -> None:
        """Handle goodbye event."""
        logger.debug("GUI: goodbye event received")
        
        # Update status
        if self.app._main_window is not None:
            self.app._main_window.set_status("Goodbye!")
    
    def _handle_shutdown(self, event: GUIEvent) -> None:
        """Handle shutdown event."""
        logger.info("GUI: shutdown event received")
        # Close the GUI
        self.unsubscribe()
        self.app.close()
    
    def cleanup(self) -> None:
        """Clean up resources.
        
        Call this when the application is shutting down.
        """
        self.unsubscribe()
        
        if self._processing_timer is not None:
            self._processing_timer.stop()
            self._processing_timer = None
        
        self._pending_events.clear()
        
        logger.info("GUI event handler cleaned up")
