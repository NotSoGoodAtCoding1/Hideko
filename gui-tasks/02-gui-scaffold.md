# Task 02 — GUI Module Scaffold

**Phase:** GUI Foundation · **Depends on:** task 01 · **Blocks:** task 03 · **Effort:** 30-45 min

---

## Goal

Create the GUI module structure with the core application class, styles, and public API. This provides the foundation that all other GUI components will build upon.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `gui/__init__.py`, `gui/app.py`, `gui/styles.py` — **create only these** |
| Depends on | task 01 (PySide6 installed, `requirements-gui.txt` exists) |
| Blocks | task 03 |
| Time budget | ~40 min |

---

## Step 1 — Verify PySide6 is available

```powershell
python -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"
```

If this fails, **stop** — task 01 must be completed first.

---

## Step 2 — Create directory structure

```powershell
New-Item -ItemType Directory -Force -Path gui | Out-Null
```

---

## Step 3 — Create `gui/__init__.py`

This is the public API of the GUI module. Other modules import from here.

```python
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
        return gui_app
        
    except ImportError as e:
        logger.warning("GUI not available: PySide6 not installed. Error: %s", e)
        return None
    except Exception as e:
        logger.error("Failed to launch GUI: %s", e)
        return None
```

---

## Step 4 — Create `gui/app.py`

This is the main GUI application controller. It manages the Qt application lifecycle and provides the interface between the core app and GUI components.

```python
"""GUI application controller for Hideko.

This module provides the GUIApp class which manages the Qt application
lifecycle and coordinates between the event bus and GUI components.
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

logger = logging.getLogger(__name__)


class GUIApp:
    """Main GUI application controller.
    
    This class wraps the Qt application and manages GUI components.
    It provides methods to show, hide, and close the GUI.
    
    The GUI runs in its own Qt event loop, which is separate from the
    audio processing loop in main.py.
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
        
    def _init_components(self) -> None:
        """Initialize GUI components (lazy loading)."""
        # Don't import MainWindow here to avoid circular imports
        # Components are created on-demand in show()
        pass
    
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
        """
        if self._closed:
            logger.warning("Cannot show GUI: already closed")
            return
            
        if self._main_window is None:
            self._create_main_window()
            
        if self._main_window is not None:
            self._main_window.show()
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
        
        if self._main_window is not None:
            self._main_window.close()
            self._main_window = None
            
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
        except ImportError:
            # MainWindow not yet created - this is expected before task 04
            logger.debug("MainWindow not yet available")
            self._main_window = None
    
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
        
        Call this periodically from the main loop to keep the GUI responsive.
        """
        if self._qapp is not None:
            self._qapp.processEvents()
```

---

## Step 5 — Create `gui/styles.py`

This module contains all style constants, colors, and fonts used throughout the GUI.

```python
"""Style definitions for Hideko GUI.

This module contains all colors, fonts, spacing, and other style constants
used throughout the GUI. Centralizing styles here makes it easy to:
- Maintain consistent appearance
- Switch between light/dark themes
- Customize the look and feel
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class ColorScheme(Enum):
    """Color scheme options."""
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class Colors(NamedTuple):
    """RGB color values (0-255)."""
    background: tuple[int, int, int]
    background_secondary: tuple[int, int, int]
    text: tuple[int, int, int]
    text_secondary: tuple[int, int, int]
    primary: tuple[int, int, int]
    primary_hover: tuple[int, int, int]
    primary_pressed: tuple[int, int, int]
    success: tuple[int, int, int]
    warning: tuple[int, int, int]
    error: tuple[int, int, int]
    border: tuple[int, int, int]
    
    @classmethod
    def light(cls) -> Colors:
        """Light theme colors."""
        return cls(
            background=(248, 248, 248),
            background_secondary=(240, 240, 240),
            text=(30, 30, 30),
            text_secondary=(100, 100, 100),
            primary=(0, 120, 215),
            primary_hover=(0, 140, 235),
            primary_pressed=(0, 100, 195),
            success=(0, 180, 0),
            warning=(255, 165, 0),
            error=(220, 50, 50),
            border=(200, 200, 200),
        )
    
    @classmethod
    def dark(cls) -> Colors:
        """Dark theme colors."""
        return cls(
            background=(40, 40, 40),
            background_secondary=(55, 55, 55),
            text=(240, 240, 240),
            text_secondary=(180, 180, 180),
            primary=(0, 140, 255),
            primary_hover=(0, 160, 255),
            primary_pressed=(0, 120, 235),
            success=(0, 200, 0),
            warning=(255, 180, 0),
            error=(255, 80, 80),
            border=(70, 70, 70),
        )


class Fonts(NamedTuple):
    """Font definitions."""
    family: str
    size_small: int
    size_medium: int
    size_large: int
    size_title: int
    
    @classmethod
    def default(cls) -> Fonts:
        """Default font settings."""
        return cls(
            family="Segoe UI",
            size_small=10,
            size_medium=12,
            size_large=14,
            size_title=18,
        )


class Spacing(NamedTuple):
    """Spacing constants in pixels."""
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32
    
    @classmethod
    def default(cls) -> Spacing:
        """Default spacing values."""
        return cls()


class Sizes(NamedTuple):
    """Size constants in pixels."""
    window_min_width: int = 600
    window_min_height: int = 400
    window_default_width: int = 800
    window_default_height: int = 600
    sidebar_width: int = 200
    audio_viz_width: int = 150
    button_height: int = 36
    input_height: int = 36
    icon_size: int = 24
    icon_small: int = 16
    
    @classmethod
    def default(cls) -> Sizes:
        """Default size values."""
        return cls()


class Style:
    """Main style configuration.
    
    This class provides access to the current style settings and allows
    switching between themes.
    """
    
    _current_scheme: ColorScheme = ColorScheme.SYSTEM
    _current_colors: Colors = Colors.light()
    _fonts: Fonts = Fonts.default()
    _spacing: Spacing = Spacing.default()
    _sizes: Sizes = Sizes.default()
    
    @classmethod
    def set_scheme(cls, scheme: ColorScheme) -> None:
        """Set the color scheme.
        
        Args:
            scheme: The color scheme to use.
        """
        cls._current_scheme = scheme
        
        if scheme == ColorScheme.SYSTEM:
            # Detect system theme (simplified - always use light for now)
            # Task 06 will implement proper system theme detection
            cls._current_colors = Colors.light()
        elif scheme == ColorScheme.DARK:
            cls._current_colors = Colors.dark()
        else:
            cls._current_colors = Colors.light()
    
    @classmethod
    @property
    def colors(cls) -> Colors:
        """Get the current color scheme."""
        return cls._current_colors
    
    @classmethod
    @property
    def fonts(cls) -> Fonts:
        """Get the font settings."""
        return cls._fonts
    
    @classmethod
    @property
    def spacing(cls) -> Spacing:
        """Get the spacing constants."""
        return cls._spacing
    
    @classmethod
    @property
    def sizes(cls) -> Sizes:
        """Get the size constants."""
        return cls._sizes
    
    @classmethod
    def qss(cls) -> str:
        """Generate QSS (Qt Style Sheet) string for the current style.
        
        Returns:
            A QSS string that can be applied to widgets.
        """
        c = cls.colors
        f = cls.fonts
        
        return f"""
        /* Base colors */
        QWidget {{ 
            background-color: rgb({c.background[0]}, {c.background[1]}, {c.background[2]});
            color: rgb({c.text[0]}, {c.text[1]}, {c.text[2]});
            font-family: '{f.family}';
            font-size: {f.size_medium}px;
        }}
        
        /* Primary buttons */
        QPushButton {{ 
            background-color: rgb({c.primary[0]}, {c.primary[1]}, {c.primary[2]});
            color: white;
            border: none;
            border-radius: 4px;
            padding: {cls.spacing.sm}px {cls.spacing.md}px;
            font-size: {f.size_medium}px;
        }}
        
        QPushButton:hover {{ 
            background-color: rgb({c.primary_hover[0]}, {c.primary_hover[1]}, {c.primary_hover[2]});
        }}
        
        QPushButton:pressed {{ 
            background-color: rgb({c.primary_pressed[0]}, {c.primary_pressed[1]}, {c.primary_pressed[2]});
        }}
        
        /* Conversation area */
        QTextEdit, QTextBrowser {{ 
            background-color: rgb({c.background_secondary[0]}, {c.background_secondary[1]}, {c.background_secondary[2]});
            color: rgb({c.text[0]}, {c.text[1]}, {c.text[2]});
            border: 1px solid rgb({c.border[0]}, {c.border[1]}, {c.border[2]});
            border-radius: 4px;
            padding: {cls.spacing.sm}px;
        }}
        
        /* Input field */
        QLineEdit {{ 
            background-color: rgb({c.background_secondary[0]}, {c.background_secondary[1]}, {c.background_secondary[2]});
            color: rgb({c.text[0]}, {c.text[1]}, {c.text[2]});
            border: 1px solid rgb({c.border[0]}, {c.border[1]}, {c.border[2]});
            border-radius: 4px;
            padding: {cls.spacing.sm}px;
        }}
        
        /* Status labels */
        QLabel.status {{ 
            color: rgb({c.text_secondary[0]}, {c.text_secondary[1]}, {c.text_secondary[2]});
            font-size: {f.size_small}px;
        }}
        
        /* Success/warning/error indicators */
        QLabel.success {{ color: rgb({c.success[0]}, {c.success[1]}, {c.success[2]}); }}
        QLabel.warning {{ color: rgb({c.warning[0]}, {c.warning[1]}, {c.warning[2]}); }}
        QLabel.error {{ color: rgb({c.error[0]}, {c.error[1]}, {c.error[2]}); }}
        """
```

---

## Step 6 — Create `__init__.py` for tests

```powershell
New-Item -ItemType File -Force -Path gui/__init__.py -Value "" | Out-Null
```

Wait, we already created `gui/__init__.py` in Step 3. Skip this step.

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify files exist
Get-ChildItem gui\*.py | Select-Object Name, LastWriteTime

# Verify imports work
python -c "from gui import launch_gui; print('gui/__init__.py OK')"
python -c "from gui.app import GUIApp; print('gui/app.py OK')"
python -c "from gui.styles import Style, Colors, Fonts; print('gui/styles.py OK')"

# Verify basic functionality
python -c "from gui.styles import Style; print('QSS length:', len(Style.qss()))"
```

Expected:
- Three files listed: `__init__.py`, `app.py`, `styles.py`
- All imports succeed
- QSS string has reasonable length (> 100 characters)

---

## Done criteria

- [ ] `gui/__init__.py` exists with exact content
- [ ] `gui/app.py` exists with exact content
- [ ] `gui/styles.py` exists with exact content
- [ ] All imports work without errors
- [ ] No other files were created or modified
- [ ] `python -m pytest -q` still passes (if tests exist)

---

## Common pitfalls

- **Indentation errors**: Python is strict about indentation; copy carefully
- **Circular imports**: Don't import from gui submodules in gui/__init__.py
- **Wrong directory**: Create files in `gui/` not in project root
- **Encoding issues**: Use UTF-8 encoding for all files

---

## Do NOT

- Do not create other GUI files yet (those are in later tasks)
- Do not modify `main.py` or any core modules
- Do not add any GUI-specific code to existing modules
- Do not start task 03

---

## Report

Report: files created, pasted verification output, any issues encountered, anything unfinished.
