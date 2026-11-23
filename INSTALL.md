# Installation Guide for llama-cpp-python on Windows

## Problem Summary
`llama-cpp-python==0.3.36` has **no pre-built wheels** for Python 3.11 on Windows. It requires building from source, which needs C++ build tools.

---

## Solution Options

### Option A: Install Visual Studio Build Tools (Recommended for full control)
This is the most reliable solution and gives you full package management control.

**Steps:**
1. Download [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. Run installer, select "Desktop development with C++"
3. Install (takes ~5-10GB, 30+ minutes)
4. Reinstall requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

### Option B: Use conda (Your Current Approach)
Conda can download pre-built wheels, but requires building `llama-cpp-python` from source too.

**Steps:**
1. Your conda is already installed at `C:\Users\Ilya\miniforge3` ✅
2. Create environment and install:

```powershell
C:\Users\Ilya\miniforge3\Scripts\conda.exe create -n llama-env python=3.11 -y
C:\Users\Ilya\miniforge3\Scripts\conda.exe activate llama-env

# Install from conda-forge (will try to build if no pre-built available)
C:\Users\Ilya\miniforge3\Scripts\conda.exe install -c conda-forge \
  numpy sounddevice soundfile faster-whisper pyyaml pytest llama-cpp-python
```

**Note:** You'll still get the "nmake not found" error with this approach because `llama-cpp-python` requires building from source even in conda.

---

### Option C: Use Pre-built Binary Fork (Fastest!)
Use `llama-cpp-bin`, a fork that provides pre-built Windows wheels.

**Steps:**
1. Create venv and install:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# Install the binary version
python -m pip install llama-cpp-bin
```

Then update your code to import from `llama_cpp_bin` instead of `llama_cpp_python`.

---

### Option D: Use Miniconda with Pre-built Wheels (Simplest for conda users)
Use an older version that has pre-built wheels available.

**Steps:**
```powershell
# Create fresh env with Python 3.10 (has more pre-built wheels)
C:\Users\Ilya\miniforge3\Scripts\conda.exe create -n llama-env python=3.10 -y
C:\Users\Ilya\miniforge3\Scripts\conda.exe activate llama-env

# Try installing specific older version with pre-built wheel
python -m pip install --only-binary :all: llama-cpp-python==0.2.x
```

---

## Quick Recommendation

**For your project**, I recommend **Option A (Visual Studio Build Tools)** because:
- ✅ Full control over packages via pip (no conda conflicts)
- ✅ Latest versions of all packages
- ✅ No platform-specific issues
- ✅ Works across different Python/OS setups

**Time to setup:** ~45 minutes (mostly download time for the 8GB installer)

---

## Alternative: Skip llama-cpp-python temporarily

If you just want to test your main.py code without LLM features, comment out llama-cpp-python in requirements.txt:

```bash
python -m pip install numpy sounddevice soundfile faster-whisper pyyaml pytest
```

Then run `main.py` - it will show the "calibrating" message but won't use LLM features.

---

## Status of Your Installation

- ✅ Conda is installed at: `C:\Users\Ilya\miniforge3`
- ✅ Virtual environment exists at: `.venv` (using Python 3.11)
- ⚠️ Problem: No pre-built wheel for `llama-cpp-python==0.3.36` on Windows + Python 3.11
- ℹ️ Other packages (numpy, sounddevice, etc.) install fine as pre-built wheels
