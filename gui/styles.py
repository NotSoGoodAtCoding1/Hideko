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
