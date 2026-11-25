# Task 05 — Audio Visualization

**Phase:** GUI Components · **Depends on:** task 04 · **Blocks:** task 06 · **Effort:** 45-60 min

---

## Goal

Create audio visualization components (VU meter and optional waveform display) for the GUI. This provides visual feedback about audio input and output levels.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `gui/audio_viz.py` — **create only this** |
| Depends on | task 04 (MainWindow exists) |
| Blocks | task 06 |
| Time budget | ~50 min |

---

## Step 1 — Verify dependencies

```powershell
# Verify PySide6 and GUI modules
python -c "from PySide6.QtWidgets import QWidget, QVBoxLayout; from gui.main_window import MainWindow; print('Dependencies OK')"

# Verify numpy for audio processing
python -c "import numpy as np; print('numpy OK')"
```

All must succeed. If any fail, stop and report.

---

## Step 2 — Create `gui/audio_viz.py`

This module provides visual feedback for audio input and output.

```python
"""Audio visualization components for Hideko GUI.

This module provides VU meter and waveform display components for
visualizing audio input and output levels.
"""

from __future__ import annotations

import logging
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from PySide6.QtGui import QPaintEvent, QResizeEvent

from PySide6.QtCore import Qt, QTimer, Signal, QRect, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QPaintEvent,
    QResizeEvent,
)

from gui.styles import Style

logger = logging.getLogger(__name__)


class VUMeter(QWidget):
    """Vertical VU meter for displaying audio level.
    
    Shows a bar that rises and falls with the audio input level.
    The level is normalized between 0.0 (silence) and 1.0 (full scale).
    """
    
    # Signal emitted when the level changes
    level_changed = Signal(float)
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the VU meter.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        
        # Visual properties
        self._level: float = 0.0
        self._peak_level: float = 0.0
        self._peak_hold_time: int = 500  # ms to hold peak indicator
        self._falloff_speed: float = 0.95  # Falloff multiplier per frame
        
        # Colors
        colors = Style.colors
        self._bg_color = QColor(*colors.background_secondary)
        self._bar_color = QColor(*colors.primary)
        self._peak_color = QColor(255, 50, 50)  # Red for peak
        self._warning_color = QColor(255, 165, 0)  # Orange for warning
        self._border_color = QColor(*colors.border)
        
        # Peak indicator state
        self._peak_active = False
        self._peak_timer: QTimer | None = None
        
        # Create peak timer
        self._create_peak_timer()
        
        # Set size policy
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding
        )
        self.setMinimumWidth(20)
        self.setMinimumHeight(60)
    
    def _create_peak_timer(self) -> None:
        """Create the peak indicator timer."""
        self._peak_timer = QTimer(self)
        self._peak_timer.setInterval(50)  # 20 FPS
        self._peak_timer.timeout.connect(self._update_peak)
    
    def _update_peak(self) -> None:
        """Update peak indicator state."""
        if self._peak_active:
            # Peak is still active, maybe deactivate
            pass
        else:
            # Peak timer timed out
            self._peak_timer.stop()
            self._peak_active = False
            self.update()
    
    def set_level(self, level: float) -> None:
        """Set the current audio level.
        
        The level should be normalized between 0.0 and 1.0.
        Levels above 1.0 will be clamped and trigger the peak indicator.
        
        Args:
            level: The audio level (0.0 to 1.0+).
        """
        # Clamp level
        level = max(0.0, min(level, 2.0))  # Allow up to 2.0 for headroom
        
        # Check for peak (level > 1.0)
        if level > 1.0:
            self._peak_level = 1.0
            self._peak_active = True
            if self._peak_timer and not self._peak_timer.isActive():
                self._peak_timer.start()
        else:
            self._peak_level = level
            self._peak_active = False
        
        self._level = level
        self.level_changed.emit(self._level)
        self.update()
    
    def update_level(self, samples: np.ndarray) -> None:
        """Update the level from audio samples.
        
        Computes the RMS level from the audio samples and updates the meter.
        
        Args:
            samples: Audio samples as a numpy array (float32).
        """
        if len(samples) == 0:
            self.set_level(0.0)
            return
        
        # Compute RMS
        rms = np.sqrt(np.mean(np.square(samples)))
        
        # Convert to decibels (relative to full scale)
        # We use a simple linear scale for now
        level = min(rms, 1.0)
        
        self.set_level(level)
    
    def sizeHint(self) -> QSize:
        """Return the suggested size for the widget."""
        return QSize(30, 100)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the VU meter.
        
        Args:
            event: The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        painter.fillRect(self.rect(), self._bg_color)
        
        # Draw border
        painter.setPen(QPen(self._border_color, 1))
        painter.drawRect(self.rect())
        
        # Get dimensions
        width = self.width()
        height = self.height()
        
        # Draw main bar
        bar_height = int(self._level * height)
        bar_rect = QRect(2, height - bar_height, width - 4, bar_height)
        
        if bar_height > 0:
            # Use different colors based on level
            if self._level > 0.8:
                color = self._warning_color
            elif self._level > 0.5:
                color = self._bar_color.lighter(120)
            else:
                color = self._bar_color
            
            painter.fillRect(bar_rect, color)
        
        # Draw peak indicator
        if self._peak_active:
            peak_bar_height = int(self._peak_level * height)
            peak_rect = QRect(2, height - peak_bar_height, width - 4, 2)
            painter.fillRect(peak_rect, self._peak_color)
        
        # Draw scale markers
        self._draw_scale(painter, width, height)
    
    def _draw_scale(self, painter: QPainter, width: int, height: int) -> None:
        """Draw scale markers on the VU meter.
        
        Args:
            painter: The painter to use.
            width: The width of the widget.
            height: The height of the widget.
        """
        # Draw horizontal lines at key levels
        levels = [0.2, 0.4, 0.6, 0.8, 1.0]
        colors = [
            QColor(0, 200, 0),     # Green for low levels
            QColor(0, 200, 0),
            QColor(200, 200, 0),   # Yellow for mid levels
            QColor(255, 165, 0),   # Orange for high levels
            QColor(255, 50, 50),   # Red for peak
        ]
        
        for i, (level, color) in enumerate(zip(levels, colors)):
            y = height - int(level * height)
            painter.setPen(QPen(color, 1))
            painter.drawLine(2, y, width - 2, y)


class StereoVUMeter(QWidget):
    """Stereo VU meter with left and right channels.
    
    Displays two VU meters side by side for stereo audio visualization.
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the stereo VU meter.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Create labels
        self._left_label = QFrame()
        self._left_label.setFrameShape(QFrame.Shape.NoFrame)
        self._left_label.setFixedHeight(15)
        
        self._right_label = QFrame()
        self._right_label.setFrameShape(QFrame.Shape.NoFrame)
        self._right_label.setFixedHeight(15)
        
        # Create VU meters
        self._left_meter = VUMeter()
        self._right_meter = VUMeter()
        
        # Layout: labels on top, meters below
        label_layout = QHBoxLayout()
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(8)
        label_layout.addWidget(self._left_label)
        label_layout.addWidget(self._right_label)
        
        meter_layout = QHBoxLayout()
        meter_layout.setContentsMargins(0, 0, 0, 0)
        meter_layout.setSpacing(8)
        meter_layout.addWidget(self._left_meter)
        meter_layout.addWidget(self._right_meter)
        
        layout.addLayout(label_layout)
        layout.addLayout(meter_layout)
        
        # Set size policy
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )
    
    def set_left_level(self, level: float) -> None:
        """Set the left channel level.
        
        Args:
            level: The audio level for the left channel (0.0 to 1.0).
        """
        self._left_meter.set_level(level)
    
    def set_right_level(self, level: float) -> None:
        """Set the right channel level.
        
        Args:
            level: The audio level for the right channel (0.0 to 1.0).
        """
        self._right_meter.set_level(level)
    
    def set_levels(self, left: float, right: float) -> None:
        """Set both channel levels.
        
        Args:
            left: The audio level for the left channel.
            right: The audio level for the right channel.
        """
        self.set_left_level(left)
        self.set_right_level(right)


class WaveformDisplay(QWidget):
    """Simple waveform display for visualizing audio.
    
    Shows a scrolling waveform of recent audio samples.
    """
    
    def __init__(self, width: int = 200, height: int = 60, parent: QWidget | None = None) -> None:
        """Initialize the waveform display.
        
        Args:
            width: The width of the display in pixels.
            height: The height of the display in pixels.
            parent: The parent widget.
        """
        super().__init__(parent)
        
        self._width = width
        self._height = height
        self._samples: list[float] = []
        self._max_samples = width  # One sample per pixel
        self._color = QColor(0, 150, 255)  # Blue for waveform
        self._bg_color = QColor(240, 240, 240)  # Light gray background
        
        self.setFixedSize(width, height)
    
    def add_samples(self, samples: np.ndarray) -> None:
        """Add new samples to the display.
        
        Args:
            samples: Audio samples as a numpy array.
        """
        # Downsample to fit our display width
        if len(samples) > 0:
            # Take the maximum absolute value in chunks
            chunk_size = max(1, len(samples) // self._width)
            for i in range(0, len(samples), chunk_size):
                chunk = samples[i:i + chunk_size]
                if len(chunk) > 0:
                    self._samples.append(float(np.max(np.abs(chunk))))
            
            # Keep only the most recent samples
            if len(self._samples) > self._max_samples:
                self._samples = self._samples[-self._max_samples:]
        
        self.update()
    
    def clear(self) -> None:
        """Clear the waveform display."""
        self._samples = []
        self.update()
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the waveform.
        
        Args:
            event: The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        painter.fillRect(self.rect(), self._bg_color)
        
        # Draw center line
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        center_y = self.height() // 2
        painter.drawLine(0, center_y, self.width(), center_y)
        
        # Draw waveform
        if len(self._samples) > 0:
            painter.setPen(QPen(self._color, 1))
            
            # Scale samples to fit
            max_val = max(1.0, max(self._samples)) if self._samples else 1.0
            
            x = 0
            for sample in self._samples:
                # Map sample to y position (inverted because Qt's origin is top-left)
                y = center_y - int((sample / max_val) * (center_y - 4))
                painter.drawPoint(x, y)
                x += 1
    
    def sizeHint(self) -> QSize:
        """Return the suggested size for the widget."""
        return QSize(self._width, self._height)


class AudioVisualizer(QWidget):
    """Combined audio visualization widget.
    
    Contains VU meter(s) and optional waveform display.
    This is the main component to integrate into the GUI.
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the audio visualizer.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Create VU meter
        self._vu_meter = StereoVUMeter()
        layout.addWidget(self._vu_meter)
        
        # Create waveform display (optional, can be hidden)
        self._waveform = WaveformDisplay(200, 40)
        layout.addWidget(self._waveform)
        
        # Set size policy
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )
    
    def update_audio(self, samples: np.ndarray) -> None:
        """Update visualization with new audio samples.
        
        Args:
            samples: Audio samples as a numpy array (float32, mono or stereo).
        """
        if len(samples) == 0:
            return
        
        # Handle mono or stereo
        if samples.ndim == 1:
            # Mono
            rms = np.sqrt(np.mean(np.square(samples)))
            self._vu_meter.set_levels(float(rms), float(rms))
            self._waveform.add_samples(samples)
        elif samples.ndim == 2 and samples.shape[1] == 2:
            # Stereo
            left_rms = np.sqrt(np.mean(np.square(samples[:, 0])))
            right_rms = np.sqrt(np.mean(np.square(samples[:, 1])))
            self._vu_meter.set_levels(float(left_rms), float(right_rms))
            # For waveform, use left channel
            self._waveform.add_samples(samples[:, 0])
        else:
            # Unknown format, just use first channel
            if samples.ndim == 2:
                samples = samples[:, 0]
            rms = np.sqrt(np.mean(np.square(samples)))
            self._vu_meter.set_levels(float(rms), float(rms))
            self._waveform.add_samples(samples)
    
    def set_level(self, level: float) -> None:
        """Set the level for mono audio.
        
        Args:
            level: The audio level (0.0 to 1.0).
        """
        self._vu_meter.set_levels(level, level)
    
    def clear(self) -> None:
        """Clear all visualizations."""
        self._vu_meter.set_levels(0.0, 0.0)
        self._waveform.clear()
    
    def sizeHint(self) -> QSize:
        """Return the suggested size for the widget."""
        return QSize(220, 120)
```

---

## Step 3 — Update `gui/main_window.py` to include audio visualization

We need to add the audio visualizer to the main window. This is a non-blocking change.

**Find the line in `MainWindow._init_ui` where indicators_layout is created** (around where the listening and speaking indicators are added).

**Add this after the indicators_layout section**:

```python
# Create audio visualizer (placeholder for now, will be added in task 05)
# This is a placeholder comment - actual integration happens in task 05
```

Actually, let's properly integrate it. Find the part where we create the main layout and add widgets. We'll add the audio visualizer in the right sidebar.

**Modify the `_init_ui` method in `MainWindow`**:

Replace the main layout creation with this (more sophisticated layout):

```python
# Replace the entire _init_ui method with this improved version:

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
    
    # Create main layout (horizontal: conversation + sidebar)
    main_layout = QHBoxLayout(central_widget)
    main_layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
    main_layout.setSpacing(spacing.md)
    
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
    
    # Add conversation area to main layout
    main_layout.addWidget(conversation_area, stretch=3)
    
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
    
    main_layout.addWidget(sidebar, stretch=1)
    
    # Create status bar (spans full width at bottom)
    self._status_bar = StatusBar()
    # Insert status bar at the end
    main_layout.addWidget(self._status_bar)
    
    # Apply stylesheet
    self._apply_stylesheet()
```

**Add a method to update audio visualization**:

Add this method to the `MainWindow` class:

```python
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
```

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify file exists
Test-Path gui/audio_viz.py

# Verify imports work
python -c "from gui.audio_viz import VUMeter, StereoVUMeter, WaveformDisplay, AudioVisualizer; print('audio_viz imports OK')"

# Verify MainWindow still imports correctly
python -c "from gui.main_window import MainWindow; print('main_window imports OK')"

# Test VU meter creation
python -c "
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
from gui.audio_viz import VUMeter, StereoVUMeter, AudioVisualizer

# Create widgets (won't show without exec)
vu = VUMeter()
stereo = StereoVUMeter()
av = AudioVisualizer()

print('VUMeter created:', vu is not None)
print('StereoVUMeter created:', stereo is not None)
print('AudioVisualizer created:', av is not None)

# Test level setting
vu.set_level(0.5)
stereo.set_levels(0.3, 0.7)

print('Level setting works')
"
```

---

## Done criteria

- [ ] `gui/audio_viz.py` exists with exact content
- [ ] `gui/main_window.py` updated with audio visualization integration
- [ ] All imports work without errors
- [ ] VU meter widgets can be created and levels set
- [ ] No other files were modified
- [ ] Audio visualization is properly sized and positioned

---

## Common pitfalls

- **Qt painting issues**: Custom painting must be done in paintEvent, not elsewhere
- **Performance**: Don't update visualization too frequently (will be handled by event bus)
- **Thread safety**: Audio data may come from different threads
- **Import errors**: Ensure numpy is available for sample processing
- **Layout issues**: Widgets may not appear if layout is incorrect

---

## Do NOT

- Do not modify core audio modules
- Do not create other GUI files (settings, tray are later tasks)
- Do not add actual audio processing (that stays in audio_manager.py)
- Do not start task 06

---

## Report

Report: files created/modified, pasted verification output, any issues encountered, anything unfinished.
