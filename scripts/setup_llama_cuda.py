#!/usr/bin/env python
"""Install a CUDA-enabled llama-cpp-python that also works on non-AVX-512 CPUs.

Why this script exists
----------------------
The prebuilt CUDA wheels from ``abetlen/llama-cpp-python`` ship a
``llama_cpp/lib/ggml-cpu.dll`` compiled with AVX-512 instructions.  On CPUs
without AVX-512 (AMD Zen 1-3 such as the Ryzen 5 5600, and most Intel 12th-14th
gen desktop chips) loading a model raises
``OSError: [WinError -1073741795] Windows Error 0xc000001d``
(``STATUS_ILLEGAL_INSTRUCTION``) - even with ``n_gpu_layers=0``.

The CPU-only wheel for the same release is built for baseline x86-64, so this
script swaps its ``ggml-cpu.dll`` into the CUDA install.  Both DLLs come from
the same release, so the ggml ABI matches; only the CPU backend changes.  GPU
offload keeps working because ``ggml-cuda.dll`` is untouched.

Usage:
    python scripts\\setup_llama_cuda.py            # install + patch + verify
    python scripts\\setup_llama_cuda.py --skip-install
    python scripts\\setup_llama_cuda.py --no-verify

Requires network access (pip) at install time only; the runtime stays offline.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CUDA_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cu125"
CPU_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cpu"

# Verified 2026-11-23 on an RTX 3060 / driver 610.47 / CUDA UMD 13.3.
DEFAULT_VERSION = "0.3.36"
NVIDIA_RUNTIME_PINS = (
    "nvidia-cuda-runtime-cu12==12.5.82",
    "nvidia-cublas-cu12==12.5.3.2",
)

BACKUP_SUFFIX = ".cuda-avx512.bak"
WHEEL_BACKEND_MEMBER = "llama_cpp/lib/ggml-cpu.dll"
PROBE = PROJECT_ROOT / "scripts" / "llm_cuda_probe.py"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "llm" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"


class SetupError(RuntimeError):
    """Raised when the CUDA backend cannot be installed or repaired."""


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Install llama-cpp-python with working CUDA offload on any x86-64 CPU."
    )
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"llama-cpp-python version to install (default: {DEFAULT_VERSION})",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Interpreter whose environment should be patched (default: this one)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Only swap ggml-cpu.dll; do not run pip",
    )
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run scripts/llm_cuda_probe.py -1 afterwards (default: on)",
    )
    return parser


def _run(command: list[str]) -> str:
    """Run ``command`` and return its combined output.

    Args:
        command: Full argv, starting with the interpreter.

    Returns:
        Captured stdout+stderr.

    Raises:
        SetupError: If the command exits with a non-zero status.
    """
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-8:])
        raise SetupError(f"command failed ({completed.returncode}): {' '.join(command)}\n{tail}")
    return output


def purelib(python: Path) -> Path:
    """Return the ``site-packages`` directory of ``python``.

    Args:
        python: Interpreter to query.

    Returns:
        Absolute path to the interpreter's purelib directory.
    """
    output = _run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"])
    return Path(output.strip().splitlines()[-1])


def install_runtime(python: Path) -> None:
    """Install the CUDA 12.5 runtime DLL packages the wheel links against."""
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--only-binary=:all:",
            *NVIDIA_RUNTIME_PINS,
        ]
    )


def install_cuda_wheel(python: Path, version: str) -> None:
    """Install the prebuilt CUDA wheel (no dependencies, to keep the env pinned)."""
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "--no-deps",
            "--only-binary=:all:",
            "--index-url",
            CUDA_INDEX,
            f"llama-cpp-python=={version}",
        ]
    )


def download_cpu_backend(python: Path, version: str, workdir: Path) -> Path:
    """Download the CPU wheel and extract its ``ggml-cpu.dll``.

    Args:
        python: Interpreter used to invoke pip.
        version: llama-cpp-python version, which must exist on both indexes.
        workdir: Scratch directory for the wheel and the extracted DLL.

    Returns:
        Path to the extracted, non-AVX-512 ``ggml-cpu.dll``.

    Raises:
        SetupError: If no CPU wheel is available or the DLL is missing.
    """
    try:
        _run(
            [
                str(python),
                "-m",
                "pip",
                "download",
                f"llama-cpp-python=={version}",
                "--no-deps",
                "--only-binary=:all:",
                "--index-url",
                CPU_INDEX,
                "-d",
                str(workdir),
            ]
        )
    except SetupError as exc:
        raise SetupError(
            f"no CPU wheel for llama-cpp-python=={version} on {CPU_INDEX}. "
            f"Pick a version released on both indexes; {DEFAULT_VERSION} is verified."
        ) from exc

    wheels = sorted(workdir.glob("llama_cpp_python-*.whl"))
    if not wheels:
        raise SetupError(f"pip download produced no wheel in {workdir}")
    target = workdir / "ggml-cpu.dll"
    with zipfile.ZipFile(wheels[0]) as archive:
        try:
            payload = archive.read(WHEEL_BACKEND_MEMBER)
        except KeyError as exc:
            raise SetupError(f"{WHEEL_BACKEND_MEMBER} not present in {wheels[0].name}") from exc
    target.write_bytes(payload)
    return target


def replace_backend(lib_dir: Path, replacement: Path) -> Path:
    """Back up the wheel's AVX-512 backend and install ``replacement`` in its place.

    Args:
        lib_dir: ``llama_cpp/lib`` directory of the target environment.
        replacement: The non-AVX-512 ``ggml-cpu.dll`` to install.

    Returns:
        Path of the backup file.

    Raises:
        SetupError: If this is not a CUDA install or the files are missing.
    """
    cuda_dll = lib_dir / "ggml-cuda.dll"
    if not cuda_dll.is_file():
        raise SetupError(
            f"{cuda_dll} not found - install the CUDA wheel first "
            f"(--index-url {CUDA_INDEX})"
        )
    installed = lib_dir / "ggml-cpu.dll"
    if not installed.is_file():
        raise SetupError(f"{installed} not found")

    backup = lib_dir / f"ggml-cpu.dll{BACKUP_SUFFIX}"
    if not backup.exists():
        shutil.copy2(installed, backup)
    shutil.copy2(replacement, installed)
    return backup


def verify(python: Path) -> bool:
    """Run the CUDA probe on the 0.5B model in a subprocess.

    Args:
        python: Interpreter to test.

    Returns:
        True when the probe reports GPU offload success, or when the model is
        absent (verification is then skipped rather than failed).
    """
    if not DEFAULT_MODEL.is_file():
        print(f"SKIP verify: {DEFAULT_MODEL.name} not downloaded yet")
        return True
    completed = subprocess.run(
        [str(python), str(PROBE), "-1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(((completed.stdout or "") + (completed.stderr or "")).strip())
    return completed.returncode == 0


def main(argv=None) -> int:
    """Entry point: install the CUDA wheel, repair its CPU backend, verify."""
    args = argv if isinstance(argv, argparse.Namespace) else build_parser().parse_args(argv)
    python = Path(args.python).resolve()

    print("=" * 60)
    print("Hideko - llama-cpp-python CUDA setup")
    print("=" * 60)
    print(f"interpreter : {python}")
    print(f"version     : {args.version}")

    if sys.platform != "win32":
        print("ERROR: this repair targets the Windows CUDA wheels.", file=sys.stderr)
        return 1
    if not python.is_file():
        print(f"ERROR: interpreter not found: {python}", file=sys.stderr)
        return 1

    try:
        lib_dir = purelib(python) / "llama_cpp" / "lib"
        print(f"llama_cpp   : {lib_dir}")

        if not args.skip_install:
            print("1/3 installing CUDA 12.5 runtime DLLs...")
            install_runtime(python)
            print("2/3 installing CUDA wheel...")
            install_cuda_wheel(python, args.version)
        else:
            print("1-2/3 skipped (--skip-install)")

        print("3/3 swapping in the non-AVX-512 CPU backend...")
        with tempfile.TemporaryDirectory(prefix="hideko-cuda-") as tmp:
            replacement = download_cpu_backend(python, args.version, Path(tmp))
            backup = replace_backend(lib_dir, replacement)
        print(f"      backup of the wheel's backend: {backup}")
    except SetupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.verify and not verify(python):
        print("ERROR: the GPU probe failed; see output above.", file=sys.stderr)
        return 1

    print("Done. Set llm.enabled: true and llm.n_gpu_layers: -1 in config.yaml to use the GPU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
