# Task 01 — GUI Framework Selection & Requirements

**Phase:** GUI Foundation · **Depends on:** nothing · **Blocks:** all GUI tasks · **Effort:** 15-30 min

---

## Goal

Select the GUI framework (PySide6) and create the GUI-specific requirements file. Verify PySide6 can be installed and imported on this machine.

**You only need this file.** Everything is inlined. Do not open other task files, `README.md`, or `plan.md`.

| | |
|---|---|
| Files you touch | `requirements-gui.txt` — **create**, nothing else |
| Depends on | — |
| Blocks | task 02 |
| Time budget | ~20 min |

---

## Step 1 — Verify Python 3.11 and existing venv

From project root (`C:\Users\Ilya\Documents\new_prj`):

```powershell
python --version
```

Expected: `Python 3.11.x` (where x is any number)

If not 3.11, **stop** and report it. The GUI must work with the existing venv.

---

## Step 2 — Activate venv if not active

```powershell
# Check if venv is active
python -c "import sys; print(sys.prefix)"
```

If the output does **not** end with `.venv`, activate it:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Verify again: `python -c "import sys; print(sys.prefix)"` must end with `.venv`.

---

## Step 3 — Test PySide6 import (may fail)

```powershell
python -c "import PySide6; print('PySide6 version:', PySide6.__version__)"
```

If this **succeeds**, note the version and skip to Step 5.

If this **fails** with `ModuleNotFoundError`, proceed to Step 4.

---

## Step 4 — Install PySide6

```powershell
python -m pip install PySide6==6.7.0
```

Expected last line: `Successfully installed PySide6-6.7.0`

If installation fails:

| Error | Fix |
|-------|-----|
| `ERROR: Could not find a version that satisfies PySide6==6.7.0` | Try without version pin: `python -m pip install PySide6` |
| `ERROR: Could not build wheels` | Ensure Microsoft Visual C++ 14.0+ is installed; or try `python -m pip install --only-binary=:all: PySide6==6.7.0` |
| Permission denied | You're not in the venv; go back to Step 2 |

After successful install, verify:

```powershell
python -c "import PySide6; from PySide6.QtWidgets import QApplication, QLabel; print('PySide6 OK')"
```

Expected: `PySide6 OK`

---

## Step 5 — Create `requirements-gui.txt`

Create the file `requirements-gui.txt` in the project root with this exact content:

```
# GUI-specific dependencies for Hideko
# These are optional and separate from core requirements.txt
# Install with: python -m pip install -r requirements-gui.txt

PySide6==6.7.0
```

> **Note:** We pin to 6.7.0 for reproducibility. Future tasks may add `pyqtgraph` for enhanced audio visualization, but it's optional and not required for basic GUI functionality.

---

## Step 6 — Create decision documentation

Create a new file `docs/gui-framework-decision.md` with this exact content:

```markdown
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
```

---

## Step 7 — Verify Qt can create a basic window

Create a temporary test file `test_qt.py`:

```python
"""Test that PySide6 can create and show a basic window."""
import sys
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Hideko GUI Test")
    layout = QVBoxLayout()
    label = QLabel("Hello from PySide6!")
    layout.addWidget(label)
    window.setLayout(layout)
    window.show()
    print("Window created, running event loop for 2 seconds...")
    app.processEvents()
    # Don't actually run the full event loop, just verify creation
    print("Qt window creation successful")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

Run it:

```powershell
python test_qt.py
```

Expected: `Window created, running event loop for 2 seconds...` followed by `Qt window creation successful`

Delete the test file:

```powershell
Remove-Item test_qt.py
```

---

## Verification

Run all commands and paste their output in your report.

```powershell
python --version
python -c "import PySide6; print('PySide6 version:', PySide6.__version__)"
python -c "from PySide6.QtWidgets import QApplication, QLabel; print('Qt widgets OK')"
cat requirements-gui.txt
cat docs/gui-framework-decision.md
```

---

## Done criteria

- [ ] `requirements-gui.txt` exists with exact content above
- [ ] `docs/gui-framework-decision.md` exists with exact content above
- [ ] PySide6 6.7.0 (or later 6.x) is installed and imports successfully
- [ ] Qt can create widgets without errors
- [ ] No other files were modified
- [ ] No changes to `requirements.txt` (GUI deps are separate)

---

## Common pitfalls

- **Using wrong Python**: Verify `python` is from the venv, not system Python
- **Version conflicts**: Stick to PySide6 6.7.0; don't "upgrade to latest"
- **Missing Visual C++**: Required for building Qt wheels on Windows
- **32-bit Python**: Use 64-bit Python 3.11; Qt wheels are 64-bit only
- **Path issues**: Ensure you're in the project root directory

---

## Do NOT

- Do not add PySide6 to `requirements.txt` — it's optional and in `requirements-gui.txt`
- Do not create any GUI module files yet (that's task 02)
- Do not modify `main.py` or any core modules
- Do not install other GUI frameworks "just in case"
- Do not start task 02

---

## Report

Report: files created, pasted verification output, any issues encountered, anything unfinished.
