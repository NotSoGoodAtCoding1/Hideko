# Task 06 — Settings Panel

**Phase:** GUI Components · **Depends on:** task 04 · **Blocks:** task 07 · **Effort:** 60-75 min

---

## Goal

Create a settings panel that allows users to configure Hideko's behavior through the GUI. This includes audio device selection, volume controls, VAD sensitivity, and other settings.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `gui/settings_panel.py` — **create only this** |
| Depends on | task 04 (MainWindow exists) |
| Blocks | task 07 |
| Time budget | ~70 min |

---

## Step 1 — Verify dependencies

```powershell
# Verify GUI modules
python -c "from gui.main_window import MainWindow; from gui.app import GUIApp; print('GUI modules OK')"

# Verify PySide6 widgets
python -c "from PySide6.QtWidgets import QDialog, QTabWidget, QComboBox, QSlider; print('Qt widgets OK')"

# Verify config module
python -c "from config import AppConfig, load_config; print('config module OK')"

# Verify audio_manager for device listing
python -c "from audio_manager import list_devices; print('audio_manager OK')"
```

All must succeed. If any fail, stop and report.

---

## Step 2 — Create `gui/settings_panel.py`

This module provides a settings dialog for configuring Hideko.

```python
"""Settings panel for Hideko GUI.

This module provides a dialog for configuring application settings
including audio devices, volume, VAD sensitivity, and more.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
    from config import AppConfig
    from gui.app import GUIApp
    from PySide6.QtWidgets import QWidget

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QFrame,
    QDialogButtonBox,
    QSizePolicy,
    QSpacerItem,
    QScrollArea,
)
from PySide6.QtGui import QFont, QPalette, QColor

from gui.styles import Style

logger = logging.getLogger(__name__)


class AudioSettingsTab(QWidget):
    """Audio settings tab for the settings dialog."""
    
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """Initialize the audio settings tab.
        
        Args:
            config: The current application configuration.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.config = config
        self._devices: list[dict[str, Any]] = []
        
        self._init_ui()
        self._load_devices()
        self._load_settings()
    
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        spacing = Style.spacing
        
        # Create main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        layout.setSpacing(spacing.md)
        
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(spacing.md)
        
        # Audio devices group
        devices_group = QGroupBox("Audio Devices")
        devices_layout = QFormLayout()
        devices_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        devices_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Input device selector
        self._input_device_combo = QComboBox()
        self._input_device_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        devices_layout.addRow("Input Device:", self._input_device_combo)
        
        # Output device selector
        self._output_device_combo = QComboBox()
        self._output_device_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        devices_layout.addRow("Output Device:", self._output_device_combo)
        
        # Test buttons
        test_layout = QHBoxLayout()
        test_layout.setSpacing(spacing.sm)
        
        self._test_input_button = QPushButton("Test Input")
        self._test_input_button.setFixedWidth(100)
        test_layout.addWidget(self._test_input_button)
        
        self._test_output_button = QPushButton("Test Output")
        self._test_output_button.setFixedWidth(100)
        test_layout.addWidget(self._test_output_button)
        
        devices_layout.addRow("", test_layout)
        devices_group.setLayout(devices_layout)
        scroll_layout.addWidget(devices_group)
        
        # Volume group
        volume_group = QGroupBox("Volume")
        volume_layout = QFormLayout()
        volume_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        volume_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Input volume slider
        self._input_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._input_volume_slider.setRange(0, 100)
        self._input_volume_slider.setValue(100)
        self._input_volume_label = QLabel("100%")
        volume_layout.addRow("Input Volume:", self._create_slider_row(
            self._input_volume_slider, self._input_volume_label
        ))
        
        # Output volume slider
        self._output_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._output_volume_slider.setRange(0, 100)
        self._output_volume_slider.setValue(100)
        self._output_volume_label = QLabel("100%")
        volume_layout.addRow("Output Volume:", self._create_slider_row(
            self._output_volume_slider, self._output_volume_label
        ))
        
        volume_group.setLayout(volume_layout)
        scroll_layout.addWidget(volume_group)
        
        # Add spacer
        scroll_layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        ))
        
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
    
    def _create_slider_row(self, slider: QSlider, label: QLabel) -> QWidget:
        """Create a widget containing a slider and its label.
        
        Args:
            slider: The slider widget.
            label: The label widget showing the value.
        
        Returns:
            A widget containing the slider and label.
        """
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Style.spacing.sm)
        
        layout.addWidget(slider, stretch=1)
        layout.addWidget(label)
        
        # Connect slider to label
        slider.valueChanged.connect(lambda v: label.setText(f"{v}%"))
        
        return widget
    
    def _load_devices(self) -> None:
        """Load available audio devices."""
        try:
            from audio_manager import list_devices
            self._devices = list_devices()
            
            # Add devices to combos
            for device in self._devices:
                name = device.get("name", "Unknown")
                self._input_device_combo.addItem(name, device.get("index"))
                self._output_device_combo.addItem(name, device.get("index"))
            
            # Add default option
            self._input_device_combo.insertItem(0, "Default", -1)
            self._output_device_combo.insertItem(0, "Default", -1)
            
        except Exception as e:
            logger.warning("Failed to load audio devices: %s", e)
            self._input_device_combo.addItem("Error loading devices")
            self._output_device_combo.addItem("Error loading devices")
    
    def _load_settings(self) -> None:
        """Load settings from configuration."""
        # Set input device
        input_device = getattr(self.config, "audio", {}).get("input_device")
        if input_device is not None:
            # Try to find the device in the list
            for i in range(self._input_device_combo.count()):
                if self._input_device_combo.itemData(i) == input_device:
                    self._input_device_combo.setCurrentIndex(i)
                    break
        
        # Set output device
        output_device = getattr(self.config, "audio", {}).get("output_device")
        if output_device is not None:
            for i in range(self._output_device_combo.count()):
                if self._output_device_combo.itemData(i) == output_device:
                    self._output_device_combo.setCurrentIndex(i)
                    break
    
    def get_settings(self) -> dict[str, Any]:
        """Get the current settings from the UI.
        
        Returns:
            Dictionary with the current settings.
        """
        settings = {}
        
        # Audio devices
        input_device = self._input_device_combo.currentData()
        if input_device != -1:
            settings["audio"] = {"input_device": input_device}
        
        output_device = self._output_device_combo.currentData()
        if output_device != -1:
            if "audio" not in settings:
                settings["audio"] = {}
            settings["audio"]["output_device"] = output_device
        
        # Volume
        settings["input_volume"] = self._input_volume_slider.value() / 100.0
        settings["output_volume"] = self._output_volume_slider.value() / 100.0
        
        return settings


class VADSettingsTab(QWidget):
    """VAD (Voice Activity Detection) settings tab."""
    
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """Initialize the VAD settings tab.
        
        Args:
            config: The current application configuration.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        spacing = Style.spacing
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        layout.setSpacing(spacing.md)
        
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(spacing.md)
        
        # Sensitivity group
        sensitivity_group = QGroupBox("Sensitivity")
        sensitivity_layout = QFormLayout()
        sensitivity_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        sensitivity_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Threshold slider
        self._threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setRange(-60, 0)  # dB range
        self._threshold_label = QLabel("-30 dBFS")
        sensitivity_layout.addRow("Threshold:", self._create_slider_row(
            self._threshold_slider, self._threshold_label
        ))
        
        # Silence timeout
        self._silence_timeout_spin = QSpinBox()
        self._silence_timeout_spin.setRange(100, 5000)  # ms
        self._silence_timeout_spin.setValue(700)
        self._silence_timeout_spin.setSuffix(" ms")
        sensitivity_layout.addRow("Silence Timeout:", self._silence_timeout_spin)
        
        # Minimum utterance length
        self._min_utterance_spin = QSpinBox()
        self._min_utterance_spin.setRange(100, 5000)  # ms
        self._min_utterance_spin.setValue(500)
        self._min_utterance_spin.setSuffix(" ms")
        sensitivity_layout.addRow("Min Utterance Length:", self._min_utterance_spin)
        
        sensitivity_group.setLayout(sensitivity_layout)
        scroll_layout.addWidget(sensitivity_group)
        
        # Calibration group
        calibration_group = QGroupBox("Calibration")
        calibration_layout = QVBoxLayout()
        
        self._calibrate_check = QCheckBox("Auto-calibrate on startup")
        calibration_layout.addWidget(self._calibrate_check)
        
        self._calibrate_button = QPushButton("Calibrate Now")
        self._calibrate_button.setFixedWidth(150)
        calibration_layout.addWidget(self._calibrate_button)
        
        calibration_group.setLayout(calibration_layout)
        scroll_layout.addWidget(calibration_group)
        
        # Add spacer
        scroll_layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        ))
        
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
    
    def _create_slider_row(self, slider: QSlider, label: QLabel) -> QWidget:
        """Create a widget containing a slider and its label.
        
        Args:
            slider: The slider widget.
            label: The label widget showing the value.
        
        Returns:
            A widget containing the slider and label.
        """
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Style.spacing.sm)
        
        layout.addWidget(slider, stretch=1)
        layout.addWidget(label)
        
        # Connect slider to label
        def update_label(value: int) -> None:
            label.setText(f"{value} dBFS")
        slider.valueChanged.connect(update_label)
        
        return widget
    
    def _load_settings(self) -> None:
        """Load settings from configuration."""
        vad_config = getattr(self.config, "vad", {})
        
        # Threshold
        threshold = vad_config.get("threshold", -30)
        self._threshold_slider.setValue(threshold)
        self._threshold_label.setText(f"{threshold} dBFS")
        
        # Silence timeout
        silence_timeout = vad_config.get("silence_ms", 700)
        self._silence_timeout_spin.setValue(silence_timeout)
        
        # Minimum utterance
        min_utterance = vad_config.get("min_utterance_ms", 500)
        self._min_utterance_spin.setValue(min_utterance)
        
        # Auto-calibrate
        calibrate = vad_config.get("calibrate", True)
        self._calibrate_check.setChecked(calibrate)
    
    def get_settings(self) -> dict[str, Any]:
        """Get the current settings from the UI.
        
        Returns:
            Dictionary with the current settings.
        """
        settings = {}
        
        settings["vad"] = {
            "threshold": self._threshold_slider.value(),
            "silence_ms": self._silence_timeout_spin.value(),
            "min_utterance_ms": self._min_utterance_spin.value(),
            "calibrate": self._calibrate_check.isChecked(),
        }
        
        return settings


class ModelSettingsTab(QWidget):
    """Model settings tab for STT and TTS."""
    
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """Initialize the model settings tab.
        
        Args:
            config: The current application configuration.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        spacing = Style.spacing
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        layout.setSpacing(spacing.md)
        
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(spacing.md)
        
        # STT group
        stt_group = QGroupBox("Speech-to-Text (STT)")
        stt_layout = QFormLayout()
        stt_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        stt_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self._stt_model_combo = QComboBox()
        self._stt_model_combo.addItems([
            "tiny.en",
            "base.en",
            "small.en",
            "medium.en",
        ])
        stt_layout.addRow("Model:", self._stt_model_combo)
        
        self._stt_quant_combo = QComboBox()
        self._stt_quant_combo.addItems([
            "int8",
            "int16",
            "float32",
        ])
        stt_layout.addRow("Quantization:", self._stt_quant_combo)
        
        stt_group.setLayout(stt_layout)
        scroll_layout.addWidget(stt_group)
        
        # TTS group
        tts_group = QGroupBox("Text-to-Speech (TTS)")
        tts_layout = QFormLayout()
        tts_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        tts_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self._tts_voice_combo = QComboBox()
        self._tts_voice_combo.addItems([
            "en_US-amy-medium",
            "en_US-libritts-r",
            "en_GB-apope-low",
        ])
        tts_layout.addRow("Voice:", self._tts_voice_combo)
        
        self._tts_speaker_spin = QSpinBox()
        self._tts_speaker_spin.setRange(50, 300)
        self._tts_speaker_spin.setValue(200)
        self._tts_speaker_spin.setSuffix(" %")
        tts_layout.addRow("Speaker ID:", self._tts_speaker_spin)
        
        tts_group.setLayout(tts_layout)
        scroll_layout.addWidget(tts_group)
        
        # LLM group
        llm_group = QGroupBox("LLM (Optional)")
        llm_layout = QFormLayout()
        llm_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        llm_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self._llm_enabled_check = QCheckBox()
        llm_layout.addRow("Enabled:", self._llm_enabled_check)
        
        self._llm_base_url_edit = QLabel("http://127.0.0.1:5001/v1")
        llm_layout.addRow("Base URL:", self._llm_base_url_edit)
        
        llm_group.setLayout(llm_layout)
        scroll_layout.addWidget(llm_group)
        
        # Add spacer
        scroll_layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        ))
        
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
    
    def _load_settings(self) -> None:
        """Load settings from configuration."""
        # STT
        stt_config = getattr(self.config, "stt", {})
        model = stt_config.get("model_size", "tiny.en")
        for i in range(self._stt_model_combo.count()):
            if self._stt_model_combo.itemText(i) == model:
                self._stt_model_combo.setCurrentIndex(i)
                break
        
        # TTS
        tts_config = getattr(self.config, "tts", {})
        voice = tts_config.get("voice", "en_US-amy-medium")
        for i in range(self._tts_voice_combo.count()):
            if self._tts_voice_combo.itemText(i) == voice:
                self._tts_voice_combo.setCurrentIndex(i)
                break
        
        # LLM
        llm_config = getattr(self.config, "llm", {})
        enabled = llm_config.get("enabled", False)
        self._llm_enabled_check.setChecked(enabled)
    
    def get_settings(self) -> dict[str, Any]:
        """Get the current settings from the UI.
        
        Returns:
            Dictionary with the current settings.
        """
        settings = {}
        
        settings["stt"] = {
            "model_size": self._stt_model_combo.currentText(),
        }
        
        settings["tts"] = {
            "voice": self._tts_voice_combo.currentText(),
        }
        
        settings["llm"] = {
            "enabled": self._llm_enabled_check.isChecked(),
        }
        
        return settings


class AppearanceSettingsTab(QWidget):
    """Appearance settings tab for GUI customization."""
    
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """Initialize the appearance settings tab.
        
        Args:
            config: The current application configuration.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        spacing = Style.spacing
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        layout.setSpacing(spacing.md)
        
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(spacing.md)
        
        # Theme group
        theme_group = QGroupBox("Theme")
        theme_layout = QVBoxLayout()
        
        self._theme_light_radio = QCheckBox("Light")
        self._theme_dark_radio = QCheckBox("Dark")
        self._theme_system_radio = QCheckBox("System")
        self._theme_system_radio.setChecked(True)
        
        theme_layout.addWidget(self._theme_light_radio)
        theme_layout.addWidget(self._theme_dark_radio)
        theme_layout.addWidget(self._theme_system_radio)
        
        theme_group.setLayout(theme_layout)
        scroll_layout.addWidget(theme_group)
        
        # Window group
        window_group = QGroupBox("Window")
        window_layout = QFormLayout()
        window_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        window_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self._always_on_top_check = QCheckBox()
        window_layout.addRow("Always on Top:", self._always_on_top_check)
        
        self._start_minimized_check = QCheckBox()
        window_layout.addRow("Start Minimized:", self._start_minimized_check)
        
        self._minimize_to_tray_check = QCheckBox()
        window_layout.addRow("Minimize to Tray:", self._minimize_to_tray_check)
        
        window_group.setLayout(window_layout)
        scroll_layout.addWidget(window_group)
        
        # Conversation group
        conversation_group = QGroupBox("Conversation")
        conversation_layout = QFormLayout()
        conversation_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        conversation_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 24)
        self._font_size_spin.setValue(12)
        conversation_layout.addRow("Font Size:", self._font_size_spin)
        
        self._max_history_spin = QSpinBox()
        self._max_history_spin.setRange(10, 1000)
        self._max_history_spin.setValue(100)
        self._max_history_spin.setSuffix(" messages")
        conversation_layout.addRow("Max History:", self._max_history_spin)
        
        conversation_group.setLayout(conversation_layout)
        scroll_layout.addWidget(conversation_group)
        
        # Add spacer
        scroll_layout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        ))
        
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
    
    def _load_settings(self) -> None:
        """Load settings from configuration."""
        # These settings might be in a GUI-specific section of config
        # For now, we'll use defaults
        pass
    
    def get_settings(self) -> dict[str, Any]:
        """Get the current settings from the UI.
        
        Returns:
            Dictionary with the current settings.
        """
        settings = {}
        
        # Theme
        theme = "system"
        if self._theme_light_radio.isChecked():
            theme = "light"
        elif self._theme_dark_radio.isChecked():
            theme = "dark"
        settings["theme"] = theme
        
        # Window
        settings["window"] = {
            "always_on_top": self._always_on_top_check.isChecked(),
            "start_minimized": self._start_minimized_check.isChecked(),
            "minimize_to_tray": self._minimize_to_tray_check.isChecked(),
        }
        
        # Conversation
        settings["conversation"] = {
            "font_size": self._font_size_spin.value(),
            "max_history": self._max_history_spin.value(),
        }
        
        return settings


class SettingsDialog(QDialog):
    """Main settings dialog with multiple tabs."""
    
    settings_saved = Signal(dict)
    
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """Initialize the settings dialog.
        
        Args:
            config: The current application configuration.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        self._init_ui()
        self._load_all_settings()
    
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("Hideko Settings")
        self.setMinimumSize(600, 400)
        
        spacing = Style.spacing
        
        # Create main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        layout.setSpacing(spacing.md)
        
        # Create tab widget
        self._tab_widget = QTabWidget()
        
        # Create tabs
        self._audio_tab = AudioSettingsTab(self.config)
        self._vad_tab = VADSettingsTab(self.config)
        self._model_tab = ModelSettingsTab(self.config)
        self._appearance_tab = AppearanceSettingsTab(self.config)
        
        self._tab_widget.addTab(self._audio_tab, "Audio")
        self._tab_widget.addTab(self._vad_tab, "VAD")
        self._tab_widget.addTab(self._model_tab, "Models")
        self._tab_widget.addTab(self._appearance_tab, "Appearance")
        
        layout.addWidget(self._tab_widget, stretch=1)
        
        # Create button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply
        )
        
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply_settings
        )
        
        layout.addWidget(button_box)
        
        # Apply stylesheet
        self.setStyleSheet(Style.qss())
    
    def _load_all_settings(self) -> None:
        """Load all settings from configuration."""
        # Settings are loaded by individual tabs in their _load_settings methods
        pass
    
    def _apply_settings(self) -> None:
        """Apply the current settings."""
        self._save_settings()
    
    def _save_settings(self) -> None:
        """Save settings from all tabs."""
        settings = {}
        
        # Merge settings from all tabs
        settings.update(self._audio_tab.get_settings())
        settings.update(self._vad_tab.get_settings())
        settings.update(self._model_tab.get_settings())
        settings.update(self._appearance_tab.get_settings())
        
        # Emit signal
        self.settings_saved.emit(settings)
    
    def accept(self) -> None:
        """Handle OK button click."""
        self._save_settings()
        super().accept()
    
    def reject(self) -> None:
        """Handle Cancel button click."""
        super().reject()


class SettingsButton(QPushButton):
    """Button to open settings dialog."""
    
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """Initialize the settings button.
        
        Args:
            config: The current application configuration.
            parent: The parent widget.
        """
        super().__init__("Settings", parent)
        self.config = config
        self._dialog: SettingsDialog | None = None
        
        self.clicked.connect(self._show_dialog)
    
    def _show_dialog(self) -> None:
        """Show the settings dialog."""
        if self._dialog is None:
            self._dialog = SettingsDialog(self.config, self.window())
            self._dialog.settings_saved.connect(self._on_settings_saved)
        
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
    
    def _on_settings_saved(self, settings: dict) -> None:
        """Handle settings saved.
        
        Args:
            settings: The saved settings.
        """
        logger.info("Settings saved: %s", settings)
        # In a real implementation, this would save to config file
        # and potentially restart components


# Singleton settings panel instance
_settings_panel: SettingsDialog | None = None
_settings_button: SettingsButton | None = None


def get_settings_dialog(config: AppConfig, parent: QWidget | None = None) -> SettingsDialog:
    """Get or create the settings dialog.
    
    Args:
        config: The application configuration.
        parent: The parent widget.
    
    Returns:
        The settings dialog instance.
    """
    global _settings_dialog
    if _settings_dialog is None:
        _settings_dialog = SettingsDialog(config, parent)
    return _settings_dialog


def get_settings_button(config: AppConfig, parent: QWidget | None = None) -> SettingsButton:
    """Get or create the settings button.
    
    Args:
        config: The application configuration.
        parent: The parent widget.
    
    Returns:
        The settings button instance.
    """
    global _settings_button
    if _settings_button is None:
        _settings_button = SettingsButton(config, parent)
    return _settings_button
```

---

## Step 3 — Integrate settings button into MainWindow

Now we need to add the settings button to the control panel in the main window.

**Modify `gui/control_panel.py`** (wait, we need to check if this file exists or if it's part of main_window.py):

Actually, ControlPanel is defined within main_window.py. Let's update the ControlPanel class in main_window.py.

**Find the ControlPanel class in `gui/main_window.py` and update it**:

Add a settings button to the control panel layout:

```python
# In the _init_ui method of ControlPanel class, add this after creating the listen button:

# Create settings button
self._settings_button = QPushButton("Settings")
self._settings_button.setFixedHeight(sizes.button_height)
self._settings_button.setStyleSheet(
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
self._settings_button.clicked.connect(self._on_settings_clicked)
layout.addWidget(self._settings_button)
```

**Add the settings button click handler to ControlPanel**:

```python
def _on_settings_clicked(self) -> None:
    """Handle settings button click."""
    logger.info("Settings button clicked")
    # This will be connected to actual settings dialog in later tasks
    # For now, just log it
```

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify file exists
Test-Path gui/settings_panel.py

# Verify imports work
python -c "from gui.settings_panel import SettingsDialog, AudioSettingsTab, VADSettingsTab, ModelSettingsTab, AppearanceSettingsTab; print('settings_panel imports OK')"

# Verify MainWindow still imports correctly
python -c "from gui.main_window import MainWindow, ControlPanel; print('main_window imports OK')"

# Test settings dialog creation (without showing)
python -c "
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
from gui.settings_panel import SettingsDialog

# Create a minimal config
import dataclasses
@dataclasses.dataclass
class MinimalConfig:
    pass

config = MinimalConfig()
dialog = SettingsDialog(config)

print('SettingsDialog created:', dialog is not None)
print('Number of tabs:', dialog._tab_widget.count())
"
```

---

## Done criteria

- [ ] `gui/settings_panel.py` exists with exact content
- [ ] `gui/main_window.py` updated with settings button in ControlPanel
- [ ] All imports work without errors
- [ ] Settings dialog can be created with all tabs
- [ ] No other files were modified
- [ ] Settings tabs are properly organized and labeled

---

## Common pitfalls

- **Config structure**: The actual config might have different attribute names
- **Qt layout**: Complex layouts can be tricky to get right
- **Tab order**: Tabs should be in a logical order
- **Setting persistence**: We don't save to file yet (that's a later enhancement)
- **Thread safety**: Settings dialog should not block the main thread

---

## Do NOT

- Do not modify core modules
- Do not implement actual setting persistence (that's for later)
- Do not create other GUI files (tray is task 07)
- Do not start task 07

---

## Report

Report: files created/modified, pasted verification output, any issues encountered, anything unfinished.
