# Debug task 01 — Get CUDA GPU offload working for `llama-cpp-python`

**One agent, one file.** Read only this file. Do not read `plan.md` or the other task folders. Everything you need (including what has already been tried) is inlined below.

---

## Goal

Make the **optional LLM fallback** run on the RTX 3060 GPU with `n_gpu_layers > 0`, without `0xc000001d`, so the 7B Coder GGUF becomes usable. Capture evidence for every attempt.

### Success criteria (all required)

1. `python scripts\llm_cuda_probe.py -1` loads `qwen2.5-0.5b-instruct-q4_k_m.gguf` on the GPU and generates a short reply, with no illegal-instruction error.
2. Report measured load time and generation latency for the 0.5B model on GPU.
3. Optionally repeat with `qwen2.5-coder-7b-instruct-q4_k_m.gguf` (4.68 GB) and report whether it fits in VRAM.
4. `python -m pytest -q` still passes.
5. If successful: update `config.yaml`, `config.py` defaults, `README.md`, `plan.md`, and `improvement-tasks/README.md` with the exact verified wheel/runtime versions. Keep `llm.enabled: false` by default.

### Non-goals / do not break

- Do **not** change the default response path: YAML triggers must still win; the LLM runs only on unmatched input.
- Do **not** permanently break the currently working **CPU** setup (`llama-cpp-python==0.3.36` CPU wheel) until a GPU setup is proven working.
- Do **not** delete either GGUF model. Do **not** change Python version without asking the human.
- Runtime remains offline; downloads only via `scripts/download_models.py` or explicit pip commands in this task.

---

## Environment snapshot (verified 2026-11-23)

| Item | Value |
|---|---|
| Project root | `C:\Users\Ilya\Documents\new_prj` |
| Shell | Windows 11 / PowerShell |
| Python used so far | System Python 3.11 at `C:\Users\Ilya\AppData\Local\Programs\Python\Python311\python.exe` (there is also a `.venv`; the working setup was verified with the **system** interpreter) |
| GPU | NVIDIA GeForce RTX 3060, 12288 MiB, driver **610.47**, CUDA UMD **13.3** |
| VRAM now | ~11.2 GB free (earlier only ~1.4 GB was free while other apps ran — VRAM is **not** currently the blocker) |
| CPU | AMD Ryzen 5 5600 6-Core (supports AVX2) |
| Working install | `llama_cpp_python 0.3.36` (prebuilt **CPU** wheel) |
| Installed but unused by CPU wheel | `nvidia-cuda-runtime-cu12 12.9.79`, `nvidia-cublas-cu12 12.9.2.10`, `nvidia-cuda-nvrtc-cu12 12.9.86`, `pefile 2024.8.26` |
| Models | `models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf` (491 MB, works on CPU); `models/llm/qwen2.5-coder-7b-instruct-q4_k_m.gguf` (4683 MB, unverified) |
| Config defaults | `llm.enabled: false`, `llm.n_gpu_layers: 0`, `max_tokens: 80`, `timeout_s: 15`, `context_window: 2048` |

**Re-check at start** (the user says "pip installed CUDA 12.5"; the pip list above shows 12.9 — resolve the discrepancy before changing anything):
```powershell
python -m pip list | Select-String -Pattern 'nvidia|llama.cpp|llama-cpp'
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,driver_version --format=csv
```

---

## What has ALREADY been tried — do not repeat blindly

1. `python -m pip install "llama-cpp-python==0.3.12"` → PyPI has only an **sdist**, no Windows wheel; source build stalled and was killed. **0.3.12 is a dead end.**
2. `python -m pip install --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu125 "llama-cpp-python==0.3.37"` → installed the 593.7 MB CUDA wheel successfully. (The CPU index tops out at **0.3.36**; the cu125 index has **0.3.22–0.3.37**.)
3. DLL problems found and partly fixed:
   - `bin/llama-common.dll` existed but was missing from `llama_cpp/lib/` → copied into `llama_cpp/lib/`.
   - `llama.dll`/`llama-common.dll` needed `libssl-3-x64.dll` and `libcrypto-3-x64.dll` → copied from `C:\Program Files\Git\mingw64\bin` into `llama_cpp/lib/`.
   - `ggml-cuda.dll` failed to load until the `nvidia-*` 12.9 packages above were installed.
4. `import llama_cpp` initially failed with `Failed to load shared library ... llama.dll (or one of its dependencies)`. Fixed by `llm_fallback.py::_prepare_native_library_dirs()`, which:
   - registers `site-packages/bin` and `site-packages/nvidia/*/bin` with `os.add_dll_directory`, **retaining the handles** in `_DLL_DIR_HANDLES` (they are removed when garbage-collected), and
   - adds the same directories to `os.environ["PATH"]`, because `llama_cpp` loads with `winmode=ctypes.RTLD_GLOBAL` → `LOAD_WITH_ALTERED_SEARCH_PATH`, which ignores `AddDllDirectory`.
   After this, `import llama_cpp` succeeded and printed `0.3.37`.
5. **The blocker:** constructing `Llama(model_path=<0.5B GGUF>, n_gpu_layers=-1)` raised `[WinError -1073741795] Windows Error 0xc000001d` (`STATUS_ILLEGAL_INSTRUCTION`). Retrying in the same process with `n_gpu_layers=0` failed identically; a **fresh process** with `n_gpu_layers: 0` also failed. So it is not just VRAM and not just failed-retry state.
6. Switching to the prebuilt **CPU** wheel `0.3.36` made everything work: real generation returned `France's capital is Paris. Is there anything else you'd like to know? Let me know!`. The current checkout is in this working state.
7. Later fixes still in place: LLM replies have non-ASCII stripped in `llm_fallback.respond()` (Qwen appends emoji that broke the cp1251 console); `main.py` reconfigures stdout/stderr with `errors="replace"`; `check_env.py` checks `llama_cpp` when the LLM is enabled.

---

## Rules

- **One change at a time.** After each change, run the probe and record the exact result before trying the next idea.
- Use a **temporary config copy** for enabled-LLM tests; leave `config.yaml` at `llm.enabled: false` until a GPU setup is proven.
- Prefer a **separate venv** for CUDA experiments (see H4) so the working system Python install stays intact.
- Type hints + docstrings on any new helper. No bare `except:`. No `print()` in library code outside `__main__`.
- Keep `python -m pytest -q` green throughout.
- Do not close the user's other GPU applications or download >1 GB without asking.

---

## Step 1 — Build the probe script (once)

Create `scripts/llm_cuda_probe.py`:

```python
#!/usr/bin/env python
"""Minimal repro for llama-cpp-python GPU offload. No Hideko app code required."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm_fallback import _prepare_native_library_dirs  # noqa: E402

_prepare_native_library_dirs()

import llama_cpp  # noqa: E402

MODEL = ROOT / "models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf"
BIG = ROOT / "models/llm/qwen2.5-coder-7b-instruct-q4_k_m.gguf"


def probe(model: Path, n_gpu_layers: int) -> None:
    print(f"model={model.name} n_gpu_layers={n_gpu_layers} llama_cpp={llama_cpp.__version__}")
    t0 = time.perf_counter()
    try:
        llm = llama_cpp.Llama(
            model_path=str(model),
            n_ctx=512,
            n_threads=6,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        print(f"loaded in {time.perf_counter() - t0:.2f}s")
        t1 = time.perf_counter()
        out = llm(
            "User: what is the capital of France?\nHideko:",
            max_tokens=16,
            stop=["\n", "User:", "Hideko:"],
        )
        print(f"reply={out['choices'][0]['text'].strip()!r} gen={time.perf_counter() - t1:.2f}s")
    except Exception as exc:
        print(f"FAILED type={type(exc).__name__} error={exc!r}")


if __name__ == "__main__":
    target = BIG if "--big" in sys.argv else MODEL
    layers = [int(a) for a in sys.argv[1:] if a.lstrip("-").isdigit()] or [-1]
    for ngl in layers:
        probe(target, ngl)
```

Run it first on the **current CPU wheel** to confirm the harness itself works:
```powershell
python scripts\llm_cuda_probe.py 0
```
Expected: a reply, no failure. If this fails, fix the harness before hypothesising about CUDA.

---

## Step 2 — Hypotheses, in order

Record each attempt in the evidence table at the bottom. Stop as soon as one works.

### H1 — CUDA runtime version mismatch (most likely first try)

The cu125 wheel was tested with **12.9** runtime packages. Try exact 12.5 ones:

```powershell
python -m pip index versions nvidia-cuda-runtime-cu12
python -m pip index versions nvidia-cublas-cu12
python -m pip install --force-reinstall "nvidia-cuda-runtime-cu12==12.5.82" "nvidia-cublas-cu12==12.5.3.2"
python -m pip install --force-reinstall --no-deps --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu125 "llama-cpp-python==0.3.37"
python scripts\llm_cuda_probe.py -1
python scripts\llm_cuda_probe.py 0
```
If the exact cublas version is unavailable, pick the closest `12.5.x` from `pip index versions` and record it.

### H2 — Wheel version / CUDA flavour mismatch

Try older cu125 wheel versions and other CUDA flavours, one at a time:
```powershell
python -m pip install --force-reinstall --no-deps --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu125 "llama-cpp-python==0.3.36"
python scripts\llm_cuda_probe.py -1
```
Then try `cu121`, `cu124`, `cu130`, `cu132` indexes with the same version. Driver 610.47 supports CUDA 12.x and 13.x; `cu130`/`cu132` require compute capability ≥ 7.5 (RTX 3060 is 8.6, so it qualifies).

### H3 — Native DLL still missing or wrong

Use `pefile` (already installed) to list imports of `llama.dll`, `llama-common.dll`, `ggml-cuda.dll` in `site-packages\llama_cpp\lib\`, then check each dependency resolves with:
```powershell
python -c "import ctypes, os, sysconfig; from pathlib import Path; sp=Path(sysconfig.get_paths()['purelib']); hs=[os.add_dll_directory(str(d)) for d in [sp/'bin', *sorted((sp/'nvidia').glob('*/bin'))] if d.is_dir()]; ctypes.CDLL(str(sp/'llama_cpp'/'lib'/'llama.dll')); print('ok')"
```
Compare file lists in `site-packages/bin/` vs `site-packages/llama_cpp/lib/`. Only copy a DLL if you can show it comes from the wheel or a legitimate system install (Git's `libssl`/`libcrypto` was already used) — record the source. `0xc000001d` is an illegal-instruction fault, **not** a missing-DLL error, so treat H3 as lower priority than H1/H2.

### H4 — Contaminated environment from mixed installs

Create a clean venv and retry H1 there:
```powershell
py -3.11 -m venv .venv_cuda
.\.venv_cuda\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu125
python -m pip install --force-reinstall "nvidia-cuda-runtime-cu12==12.5.82" "nvidia-cublas-cu12==12.5.3.2"
python scripts\llm_cuda_probe.py -1
```
Then `deactivate`. Do **not** delete `.venv_cuda` until the human says so, and do not delete the working system install.

### H5 — Backend init detail

If wheels load but generation still faults, try `n_gpu_layers=1`, `n_ctx=256`, and the 0.5B model only. Check whether `llama_cpp` exposes `llama_supports_gpu_offload()`. Do not spend more than one attempt here before reporting H1–H4 evidence.

---

## Step 3 — Evidence table (fill this in as you go)

| # | Wheel version + index | `nvidia-*` versions | `n_gpu_layers` | Exact exception | VRAM free | Load / gen time | Conclusion |
|---|---|---|---|---|---|---|---|
| 0 | 0.3.36 CPU (cpu index) | 12.9 (unused) | 0 | none | ~1.9 GB | load=0.50s, gen=1.00s | baseline OK |
| 1 | 0.3.37 cu125 (abetlen) | nvidia-cuda-runtime-cu12==12.5.82, nvidia-cublas-cu12==12.5.3.2, nvidia-cuda-nvrtc-cu12==12.5.82 | -1 **and 0** | OSError(22, 'Windows Error 0xc000001d') | ~1.9 GB | FAILED | **Not** a CUDA runtime mismatch. SIGILL inside `ggml-cpu.dll` (AVX-512). Weights had already reached CUDA0 (25/25 layers, 373.73 MiB) before the fault. |
| 2 | 0.3.36 cu125 (abetlen) | same 12.5 runtime | -1 **and 0** | OSError(22, 'Windows Error 0xc000001d') | ~1.9 GB | FAILED | Same fault; this wheel's `ggml-cpu.dll` also contains AVX-512 (7,809 instructions) |
| 3 | 0.3.37 cu125 + 0.3.36 CPU `ggml-cpu.dll` | same 12.5 runtime | 0, -1 | `fatal error` at `ggml-cpu/ops.cpp:4547` (GGML_ABORT) | ~1.9 GB | FAILED | Cross-version mix breaks the ggml ABI (op enum mismatch) |
| 4 | **0.3.36 cu125 + 0.3.36 CPU `ggml-cpu.dll`** | 12.5.82 / 12.5.3.2 (nvrtc not needed) | 0 | none | 11.3 GB | load 0.42s, gen 0.14s (16 tok) | CPU path OK with the repaired CUDA wheel |
| 5 | same | same | -1 | none | 11.3 GB | load 0.42s, gen 0.07s (16 tok); 264 tok/s (64 tok) | **SUCCESS — GPU offload verified** |
| 6 | same, 7B Coder q4_k_m | same | -1 | none | 11.3 GB | 2.3s warm / 10.9s cold; 48 tok/s | **7B fits: 4,168 MiB weights + 56 MiB KV + 304 MiB compute (~4.5 GB)** |

**Summary**: the crash was never a CUDA/driver mismatch. The prebuilt CUDA wheels ship a `ggml-cpu.dll` compiled with **AVX-512**; on a CPU without AVX-512 (Ryzen 5 5600 = Zen 3) the first context allocation executes `vmovups zmm0, ...` in `ggml_backend_cpu_init` and faults with `STATUS_ILLEGAL_INSTRUCTION`, even when no layer is offloaded. Swapping in the `ggml-cpu.dll` from the **same-release CPU wheel** (baseline x86-64) fixes it; `ggml-cuda.dll` is untouched.

---

## Step 4 — Finish state

### If a GPU setup works

1. Report the exact `pip install` commands, wheel version, and `nvidia-*` versions.
2. Update `config.yaml` and `config.py` defaults: set `llm.n_gpu_layers` to the verified value; keep `llm.enabled: false` and `max_tokens: 80`.
3. Update `README.md` (Requirements, Install, Configuration, Known limitations), `plan.md` ("Model choices and licences"), and `improvement-tasks/README.md` ("Post-review corrections") to say GPU offload is verified, with the exact setup. Remove the "CUDA wheel crashed" limitation only if the crash is genuinely resolved.
4. Add a `tests/` unit test that asserts the new default value (mock the backend; do **not** load a model in tests).
5. Run `python -m pytest -q`, `python config.py --check`, `python scripts\check_env.py`, and one real LLM generation via a temp config with `llm.enabled: true`.
6. Only then consider testing the 7B Coder model; report whether it fits and whether its chat answers are coherent (it is code-tuned).

### If nothing works

1. Restore the working setup: `llama-cpp-python==0.3.36` CPU wheel from `.../whl/cpu`, `llm.n_gpu_layers: 0`.
2. Leave `config.yaml` with `llm.enabled: false`.
3. Write a short conclusion into `debug-tasks/01-cuda-wheel-debug.md` under a new `## Result` heading: what was tried, what failed, and the recommendation (stay on CPU / replace GPU hardware / try a different runtime such as Ollama).
4. Run `python -m pytest -q` and confirm it passes.

---

## Result (2026-11-23) — RESOLVED

The earlier "stay on CPU" conclusion in this file was wrong: it blamed a CUDA runtime/DLL mismatch without identifying the faulting instruction.

### Root cause

`0xc000001d` is `STATUS_ILLEGAL_INSTRUCTION`. `ctypes` converts that SEH code into `OSError(22, 'Windows Error 0xc000001d')`, which made it look like a loader/DLL problem.

A vectored exception handler (`AddVectoredExceptionHandler` around `llama_init_from_model`) captured the real fault:

| Captured | Value |
|---|---|
| Exception code | `0xC000001D` |
| Faulting module | `site-packages/llama_cpp/lib/ggml-cpu.dll` |
| Faulting RVA | `0x94e9` (inside `ggml_backend_cpu_init`) |
| Instruction | `vmovups zmm0, zmmword ptr [rip + 0xedd6d]` |

`zmm` is an **AVX-512** register. The Ryzen 5 5600 is Zen 3 and has no AVX-512, so the first model load dies. Disassembly counts (capstone over `.text`):

| DLL | AVX-512 instructions |
|---|---|
| CUDA wheel `ggml-cpu.dll` (0.3.36) | 7,809 in 8 functions |
| CUDA wheel `ggml-cpu.dll` (0.3.37) | 8,217 in 8 functions |
| CPU wheel `ggml-cpu.dll` (0.3.36) | **0** |

This explains every confusing symptom: weights *did* upload to the GPU (`offloaded 25/25 layers`, `CUDA0 model buffer size = 373.73 MiB`) before the context init faulted, and `n_gpu_layers=0` failed identically because `ggml-cpu.dll` is loaded regardless.

The prebuilt CUDA wheels are simply compiled with AVX-512 on their build machines. Nothing was wrong with the driver, the CUDA 12.5 runtime packages, or the DLL search path (the `libssl`/`libcrypto`/`llama-common.dll` copies from the earlier session were unnecessary and have been removed; the probe still passes without them).

### Fix (verified)

Use the CUDA wheel, then replace only its CPU backend with the same-release CPU wheel's `ggml-cpu.dll`:

```powershell
python -m pip install --upgrade --only-binary=:all: `
    "nvidia-cuda-runtime-cu12==12.5.82" "nvidia-cublas-cu12==12.5.3.2"
python -m pip install --force-reinstall --no-deps --only-binary=:all: `
    --index-url https://abetlen.github.io/llama-cpp-python/whl/cu125 `
    "llama-cpp-python==0.3.36"
python scripts\setup_llama_cuda.py --skip-install   # downloads the CPU wheel, swaps ggml-cpu.dll
python scripts\llm_cuda_probe.py -1
```

`scripts\setup_llama_cuda.py` (without `--skip-install`) does all three steps. It keeps the wheel's original DLL as `ggml-cpu.dll.cuda-avx512.bak`. `nvidia-cuda-nvrtc-cu12` is **not** needed: `ggml-cuda.dll` imports only `cudart64_12`, `cublas64_12`, `cublasLt64_12` and `nvcuda.dll`.

Exact verified stack: `llama-cpp-python==0.3.36` (cu125 index), `nvidia-cuda-runtime-cu12==12.5.82`, `nvidia-cublas-cu12==12.5.3.2`, Python 3.11.9, RTX 3060 12 GB, driver 610.47 (CUDA UMD 13.3).

### Measurements (Ryzen 5 5600 + RTX 3060, `n_ctx=1024`, 64 generated tokens)

| Model | Mode | Load | Generation |
|---|---|---|---|
| Qwen2.5-0.5B q4_k_m | CPU (`n_gpu_layers=0`) | 0.39 s | 85 tok/s |
| Qwen2.5-0.5B q4_k_m | GPU (`n_gpu_layers=-1`) | 0.43 s | **264 tok/s** (3.1×) |
| Qwen2.5-Coder-7B q4_k_m | GPU (`n_gpu_layers=-1`) | 2.3 s warm, 10.9 s cold | **48 tok/s** |

7B VRAM: 4,168.09 MiB weights + 56 MiB KV + 304 MiB compute = ~4.5 GB used (5,359 MiB total GPU memory in use with desktop apps). Answers are coherent code (`print("hello")`, a working `reverse_string`), though the code-tuned model keeps explaining after the answer.

Probe on the shipped 0.5B model (`n_ctx=512`, 16 tokens): GPU `load=0.42s, gen=0.07s`; CPU `load=0.42s, gen=0.14s`.

### Finish state (where a GPU setup works)

- `python scripts\llm_cuda_probe.py -1` → `loaded in 0.42s` / `reply="France's capital is Paris."` / exit 0
- `python -m pytest -q` → passes (140 passed, 8 skipped)
- `python config.py --check` → exit 0
- `python scripts\check_env.py` → all rows OK except the pre-existing `numpy 1.x` row (system Python has numpy 2.4.6, while `requirements.txt` pins 1.26.4); unrelated to this task
- Real generation with a temporary `llm.enabled: true` config: `Paris is the capital of France. ...` in 1.08 s
- `config.yaml` keeps `llm.enabled: false`; `llm.n_gpu_layers` now defaults to `-1` (ignored by the CPU wheel)
- Both GGUF models intact (491 MB and 4683 MB); YAML triggers still take precedence

### Notes for the future

- Every prebuilt CUDA wheel checked (0.3.36 and 0.3.37, cu125) has the AVX-512 CPU backend, so re-running `pip install` replaces the repair — re-run `python scripts\setup_llama_cuda.py --skip-install`.
- When `llama_cpp` fails with `0xc000001d`, `LLMError` now names the repair script instead of only showing the raw `OSError`.
- The CPU wheel remains a supported install: `--index-url .../whl/cpu`, `n_gpu_layers` is ignored there.

---

## Stop and ask the human if

- No wheel/runtime combination from H1–H4 works — report evidence rather than continuing to guess.
- A fix requires closing the user's other GPU applications, downloading >1 GB, uninstalling the working CPU wheel permanently, or changing Python version.
- The 7B model needs more VRAM than is available even after the other apps are closed.
