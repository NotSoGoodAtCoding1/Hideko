# Task 03 — Event Bus GUI Subscriber

**Phase:** GUI Integration · **Depends on:** task 02 · **Blocks:** task 04 · **Effort:** 45-60 min

---

## Goal

Create the event bus subscriber that bridges the existing event bus to the GUI. This component listens to events and updates the GUI accordingly.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `gui/event_handler.py` — **create only this** |
| Depends on | task 02 (GUI scaffold exists) |
| Blocks | task 04 |
| Time budget | ~50 min |

> **Important:** You may read `events.py` and `event_outputs.py` to understand the event bus, but do not modify them. The contract is frozen from architecture-tasks.

---

## Background: Event Bus Contract

From `events.py` (do not modify, just read):

```python
ALL = "*"

@dataclass(frozen=True)
class Event:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

class EventBus:
    def subscribe(self, kinds: str | Iterable[str], handler: Callable[[Event], None]) -> None: ...
    def unsubscribe(self, handler: Callable[[Event], None]) -> None: ...
    def publish(self, kind: str, **data: Any) -> None: ...
    def clear(self) -> None: ...
```

Event kinds we must handle:

| Kind | Payload | When |
|------|---------|------|
| `startup` | `{}` | After logging setup |
| `calibrating` | `{}` | Before VAD calibration |
| `ready` | `{"stt_s": float, "trigger_count": int}` | After responder creation |
| `listening` | `{}` | When listening starts |
| `paused` | `{}` | Mute toggled on |
| `wake_detected` | `{"text": str, "latency_s": float}` | Wake word matched |
| `thinking` | `{}` | Before STT |
| `heard` | `{"text": str}` | Transcript accepted |
| `speaking` | `{"text": str}` | About to speak |
| `missed` | `{}` | Empty transcript |
| `turn_timing` | `{"stt": float, "resp": float, "tts": float, "play": float, "total": float}` | End of turn |
| `error` | `{"message": str, "exit_code": int}` | HidekoError caught |
| `goodbye` | `{}` | Before farewell |
| `shutdown` | `{}` | In shutdown |

---

## Step 1 — Verify dependencies

```powershell
# Verify GUI scaffold exists
python -c "from gui import launch_gui; from gui.app import GUIApp; print('GUI scaffold OK')"

# Verify events module exists and can be imported
python -c "from events import EventBus, Event; print('events module OK')"

# Verify config module exists
python -c "from config import AppConfig; print('config module OK')"
```

All must succeed. If any fail, stop and report.

---

## Step 2 — Create `gui/event_handler.py`

This module provides the bridge between the event bus and GUI. It subscribes to events and calls methods on the GUI components.

```python
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


# Type alias for event handlers
EventHandler = Callable[[Event], None]


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
            self._is_main_thread = lambda: (
                QThread.currentThread() == self._QThread.currentThread()
            )
        except ImportError:
            self._is_main_thread = lambda: True
        
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
            
            # Set up timer for periodic event processing
            self._processing_timer = QTimer()
            self._processing_timer.setInterval(16)  # ~60 FPS
            self._processing_timer.timeout.connect(self._process_pending)
            self._processing_timer.start()
            
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
    
    def _process_pending(self) -> None:
        """Process any pending events from the queue."""
        while self._pending_events:
            event = self._pending_events.pop(0)
            self._process_event(event)
    
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
        # Show main window if not already visible
        if not self.app.is_visible:
            self.app.show()
    
    def _handle_calibrating(self, event: GUIEvent) -> None:
        """Handle calibrating event."""
        logger.debug("GUI: calibrating event received")
        # Future: show calibration progress in GUI
        # For now, this is a placeholder
    
    def _handle_ready(self, event: GUIEvent) -> None:
        """Handle ready event."""
        stt_s = event.data.get("stt_s", 0.0)
        trigger_count = event.data.get("trigger_count", 0)
        logger.info("GUI: ready - STT warmup %.1fs, %d triggers loaded", 
                    stt_s, trigger_count)
        # Future: update status to show ready state with timing info
    
    def _handle_listening(self, event: GUIEvent) -> None:
        """Handle listening event."""
        logger.debug("GUI: listening event received")
        # This will be implemented in task 04 when MainWindow exists
        # For now, just log it
    
    def _handle_paused(self, event: GUIEvent) -> None:
        """Handle paused event."""
        logger.debug("GUI: paused event received")
        # Future: show paused state in GUI
    
    def _handle_wake_detected(self, event: GUIEvent) -> None:
        """Handle wake_detected event."""
        text = event.data.get("text", "")
        latency = event.data.get("latency_s", 0.0)
        logger.debug("GUI: wake word detected - text: %s, latency: %.1fs", 
                     text, latency)
        # Future: show wake word notification briefly
    
    def _handle_thinking(self, event: GUIEvent) -> None:
        """Handle thinking event."""
        logger.debug("GUI: thinking event received")
        # Future: show thinking indicator (spinner, etc.)
    
    def _handle_heard(self, event: GUIEvent) -> None:
        """Handle heard event."""
        text = event.data.get("text", "")
        logger.debug("GUI: heard event - text: %s", text)
        # This will be implemented in task 04
        # For now, just log it
    
    def _handle_speaking(self, event: GUIEvent) -> None:
        """Handle speaking event."""
        text = event.data.get("text", "")
        logger.debug("GUI: speaking event - text: %s", text)
        # This will be implemented in task 04
    
    def _handle_missed(self, event: GUIEvent) -> None:
        """Handle missed event (empty transcript)."""
        logger.debug("GUI: missed event received")
        # Future: show "didn't catch that" briefly
    
    def _handle_turn_timing(self, event: GUIEvent) -> None:
        """Handle turn_timing event."""
        stt = event.data.get("stt", 0.0)
        resp = event.data.get("resp", 0.0)
        tts = event.data.get("tts", 0.0)
        play = event.data.get("play", 0.0)
        total = event.data.get("total", 0.0)
        logger.debug("GUI: timing - STT:%.1fs Resp:%.2fs TTS:%.1fs Play:%.1fs Total:%.1fs",
                     stt, resp, tts, play, total)
        # Future: update performance metrics display
    
    def _handle_error(self, event: GUIEvent) -> None:
        """Handle error event."""
        message = event.data.get("message", "Unknown error")
        exit_code = event.data.get("exit_code", 1)
        logger.error("GUI: error event - message: %s, exit_code: %d", 
                     message, exit_code)
        # Future: show error in GUI
    
    def _handle_goodbye(self, event: GUIEvent) -> None:
        """Handle goodbye event."""
        logger.debug("GUI: goodbye event received")
        # Future: show farewell message
    
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
```

---

## Step 3 — Update `gui/app.py` to integrate the event handler

We need to modify `gui/app.py` to integrate the event handler. Open `gui/app.py` and make these changes:

**Add import at the top** (after the TYPE_CHECKING block):

```python
# Add this after the TYPE_CHECKING block (around line 13)
from gui.event_handler import GUIEventHandler
```

**Add to `__init__` method** (before `self._init_components()` call):

```python
# Add this in __init__ method, before _init_components()
# Initialize event handler (but don't subscribe yet)
self._event_handler: GUIEventHandler | None = None
```

**Add new method after `_init_components`**:

```python
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
    self.bus.subscribe("startup", lambda e: self._ensure_qapp())

def unsubscribe_from_events(self) -> None:
    """Unsubscribe from events."""
    if self._event_handler is not None:
        self._event_handler.unsubscribe()
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
    
    self._visible = False
    self._closed = True
    
    logger.info("GUI closed")
```

---

## Step 4 — Update `gui/__init__.py` to initialize event handler

Modify the `launch_gui` function to subscribe to events after creation:

**Replace the existing `launch_gui` function with**:

```python
def launch_gui(config: AppConfig, bus: EventBus) -> GUIApp | None:
    """Launch the GUI application.
    
    Args:
        config: The application configuration.
        bus: The event bus to subscribe to.
        
    Returns:
        The GUIApp instance if launched successfully, None otherwise.
        Returns None if PySide6 is not available or GUI cannot be initialized.
    """
    try:
        from PySide6.QtWidgets import QApplication
        
        # Check if QApplication already exists
        app_instance = QApplication.instance()
        if app_instance is None:
            # Create a new QApplication with empty argv
            import sys
            app_instance = QApplication(sys.argv)
        
        from gui.app import GUIApp
        
        gui_app = GUIApp(config, bus)
        
        # Subscribe to events
        gui_app.subscribe_to_events()
        
        return gui_app
        
    except ImportError as e:
        logger.warning("GUI not available: PySide6 not installed. Error: %s", e)
        return None
    except Exception as e:
        logger.error("Failed to launch GUI: %s", e)
        return None
```

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify file exists
Test-Path gui/event_handler.py

# Verify imports work
python -c "from gui.event_handler import GUIEventHandler, GUIEvent; print('event_handler imports OK')"

# Verify modified files import correctly
python -c "from gui import launch_gui; print('gui/__init__.py OK')"
python -c "from gui.app import GUIApp; print('gui/app.py OK')"

# Verify event handler can be instantiated (may fail without proper config)
python -c "
from events import EventBus
from gui.app import GUIApp
from config import AppConfig
from gui.event_handler import GUIEventHandler

# Create a minimal config
import dataclasses
@dataclasses.dataclass
class MinimalConfig:
    pass

bus = EventBus()
config = MinimalConfig()

# We can't fully test without Qt, but we can test the class exists
print('GUIEventHandler class exists:', GUIEventHandler is not None)
print('EventBus exists:', EventBus is not None)
"
```

---

## Done criteria

- [ ] `gui/event_handler.py` exists with exact content
- [ ] `gui/app.py` modified with event handler integration
- [ ] `gui/__init__.py` modified to subscribe to events
- [ ] All imports work without errors
- [ ] No other files were modified
- [ ] Event handler subscribes to all 12 event types

---

## Common pitfalls

- **Circular imports**: Don't create import loops between GUI modules
- **Thread safety**: Remember all GUI updates must be on Qt main thread
- **Missing attributes**: Ensure all event handler methods exist and are callable
- **Event bus not available**: Verify events module exists before starting

---

## Do NOT

- Do not modify `events.py` or `event_outputs.py`
- Do not modify core modules (`main.py`, `audio_manager.py`, etc.)
- Do not create MainWindow or other GUI components yet (those are task 04)
- Do not start task 04

---

## Report

Report: files created/modified, pasted verification output, any issues encountered, anything unfinished.
