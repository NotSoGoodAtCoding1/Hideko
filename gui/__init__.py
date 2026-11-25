"""Hideko GUI module.

This module provides an optional GUI interface for Hideko that runs
alongside the CLI, subscribing to the same event bus.

The GUI is optional: if PySide6 is not installed, launch_gui() returns None.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from config import AppConfig
    from events import EventBus
    from gui.app import GUIApp

logger = logging.getLogger(__name__)


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
            # We'll use sys.argv but filter out GUI-specific args
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
