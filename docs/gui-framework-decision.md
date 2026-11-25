# GUI Framework Decision: PySide6

## Decision

Use **PySide6** (Qt for Python) as the GUI framework for Hideko.

## Rationale

### Why PySide6

1. **Native look and feel** — Uses platform-native widgets on Windows, macOS, Linux
2. **Mature ecosystem** — Qt is industry-standard, PySide6 is well-maintained by Qt Company
3. **Thread-safe architecture** — Signal/slot mechanism aligns perfectly with our event bus
4. **Excellent documentation** — Both official Qt docs and PySide6-specific guides
5. **No GPU requirement** — All rendering happens on CPU
6. **LGPL license** — Permissive, compatible with our project goals
7. **Familiar patterns** — Similar to other successful desktop applications

### Why not other frameworks

| Framework | Rejected Because |
|-----------|------------------|
| tkinter | Too basic, poor styling options, non-native on Windows |
| Kivy | Non-native look, heavy, complex deployment |
| Dear PyGui | Great for tools/demos, not for traditional desktop apps |
| PyQt5/PyQt6 | Same Qt basis but GPL license (PySide6 is LGPL) |
| Web (Flask/FastAPI) | Requires browser, adds unnecessary complexity for desktop app |
| Streamlit | Not suitable for always-on desktop applications |
| wxPython | Less modern, smaller community, dated appearance |

### Verification

PySide6 6.7.0 verified working on Windows 10/11 with Python 3.11:

```python
import PySide6
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtCore import QTimer, Signal, Slot, QObject

print(f"PySide6 version: {PySide6.__version__}")
print("All core imports successful")
```

## Installation

```powershell
python -m pip install PySide6==6.7.0
```

Or from requirements file:

```powershell
python -m pip install -r requirements-gui.txt
```

## Architecture Integration

The GUI will:

1. **Subscribe to the existing event bus** — No changes to core audio loop
2. **Run in a separate thread** — Qt event loop alongside audio processing
3. **Be optional** — `--gui` flag enables it; CLI works without it
4. **Gracefully degrade** — If PySide6 import fails, fall back to CLI with warning

## Module Structure

```
gui/
├── __init__.py           # Public API: launch_gui()
├── app.py                # Qt application wrapper
├── main_window.py        # Primary window
├── audio_viz.py          # VU meter, waveform
├── settings_panel.py     # Configuration UI
├── tray.py               # System tray icon
└── event_handler.py      # Event bus → GUI bridge
```
