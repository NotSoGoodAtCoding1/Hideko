#!/usr/bin/env python
"""Check that every runtime dependency for Hideko MVP is present.

Prints a table with columns: check | status | detail.
Returns 0 only when no required check is FAILED. --no-audio downgrades the
input/output device rows to WARN for headless machines and CI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Add project root to path so we can import config module
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(script_dir, "..")
os.chdir(project_root)  # Change to project root for relative imports to work
sys.path.insert(0, os.getcwd())
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
PIPER_DIR = MODELS_DIR / "piper"
WHISPER_DIR = MODELS_DIR / "whisper"
LLM_DIR = MODELS_DIR / "llm"
VOICE_CONFIG = PIPER_DIR / "en_US-amy-medium.onnx.json"

# The pinned piper.exe is 509,952 bytes; 400 KB catches truncated files.
MIN_PIPER_EXE_BYTES = 400 * 1024
MIN_VOICE_BYTES = 10 * 1024 * 1024
MIN_WHISPER_BYTES = 10 * 1024 * 1024
MIN_LLM_BYTES = 300 * 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check environment for Hideko MVP.")
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Downgrade audio device checks to WARN (for CI/headless)",
    )
    return parser


def print_table_row(check: str, status: str, detail: str) -> None:
    print(f"{check:<20} {status:<8} {detail}")


def check_python_version() -> tuple[str, str]:
    if sys.version_info[:2] == (3, 11):
        return "OK", f"Python {sys.version_info.major}.{sys.version_info.minor}"
    return (
        "FAILED",
        f"Expected Python 3.11, got {sys.version_info.major}.{sys.version_info.minor}",
    )


def check_numpy_version() -> tuple[str, str]:
    try:
        import numpy
    except ImportError as exc:
        return "FAILED", str(exc)
    if numpy.__version__.startswith("1."):
        return "OK", f"numpy {numpy.__version__}"
    return "FAILED", f"Expected numpy 1.x, got {numpy.__version__}"


def check_imports() -> tuple[str, str]:
    names = ("sounddevice", "soundfile", "faster_whisper", "yaml")
    try:
        for name in names:
            __import__(name)
    except ImportError as exc:
        return "FAILED", str(exc)
    return "OK", ", ".join(names)


def _portaudio_version():
    import sounddevice as sd

    return sd.get_portaudio_version()


def check_portaudio() -> tuple[str, str]:
    try:
        version = _portaudio_version()
        if isinstance(version, tuple):
            text = next(
                (
                    item
                    for item in reversed(version)
                    if isinstance(item, str) and item.startswith("PortAudio")
                ),
                None,
            )
            if text:
                return "OK", text
            numbers = [item for item in version if isinstance(item, int) and item > 0]
            if numbers:
                return "OK", f"PortAudio version code {numbers[0]}"
        if isinstance(version, str) and version.startswith("PortAudio"):
            return "OK", version
        return "FAILED", f"Unexpected version format: {version!r}"
    except Exception as exc:
        return "FAILED", str(exc)


def check_piper_binary() -> tuple[str, str]:
    exe = PIPER_DIR / "piper" / "piper.exe"
    if not exe.is_file():
        return "FAILED", f"Not found: {exe}"
    size = exe.stat().st_size
    if size < MIN_PIPER_EXE_BYTES:
        return "FAILED", f"Too small: {size / 1e6:.2f} MB"
    return "OK", f"{size / 1e6:.2f} MB"


def check_piper_espeak_data() -> tuple[str, str]:
    data = PIPER_DIR / "piper" / "espeak-ng-data"
    if not data.is_dir():
        return "FAILED", f"Not found: {data}"
    total = sum(item.stat().st_size for item in data.rglob("*") if item.is_file())
    if total == 0:
        return "FAILED", "Empty directory"
    return "OK", f"{total / 1e6:.2f} MB"


def check_piper_voice() -> tuple[str, str]:
    model = PIPER_DIR / "en_US-amy-medium.onnx"
    if not model.is_file():
        return "FAILED", f"Not found: {model}"
    size = model.stat().st_size
    if size < MIN_VOICE_BYTES:
        return "FAILED", f"Too small: {size / 1e6:.2f} MB"
    return "OK", f"{size / 1e6:.2f} MB"


def check_voice_config() -> tuple[str, str]:
    if not VOICE_CONFIG.is_file():
        return "FAILED", f"Not found: {VOICE_CONFIG}"
    return "OK", f"{VOICE_CONFIG.stat().st_size} bytes"


def check_voice_compatibility() -> tuple[str, str]:
    """Reject configs the pinned Piper 2023.11.14-2 binary cannot parse."""
    try:
        config = json.loads(VOICE_CONFIG.read_text(encoding="utf-8"))
    except Exception as exc:
        return "FAILED", f"Cannot read voice config: {exc}"

    phonemes = config.get("phoneme_id_map", {})
    multi = [key for key in phonemes if len(key) != 1]
    if multi:
        preview = ", ".join(repr(item) for item in multi[:3])
        return (
            "FAILED",
            f"{len(multi)} multi-codepoint phoneme(s) incompatible with pinned Piper: {preview}",
        )

    version = str(config.get("piper_version", ""))
    if version and version.split(".")[:2] != ["1", "0"]:
        return "FAILED", f"piper_version {version} is incompatible with pinned Piper 2023.11.14-2"
    return "OK", f"piper_version {version or 'unknown'}, single-codepoint phonemes"


def check_whisper_model() -> tuple[str, str]:
    models = list(WHISPER_DIR.rglob("model.bin")) if WHISPER_DIR.is_dir() else []
    if not models:
        return "FAILED", "No model.bin found"
    total = sum(item.stat().st_size for item in models)
    if total < MIN_WHISPER_BYTES:
        return "FAILED", f"Too small: {total / 1e6:.2f} MB"
    return "OK", f"{len(models)} file(s), {total / 1e6:.2f} MB"


def _llm_settings() -> AppConfig.LLMConfig:
    """Return LLM settings from config.yaml."""
    from config import load_config
    return load_config().llm


def check_llm_server() -> tuple[str, str]:
    """Check if KoboldCpp is running at the configured base_url.
    
    Skips the check if llm.enabled is False in config.yaml.
    """
    try:
        from config import load_config
        cfg = load_config().llm
    except Exception as e:
        return "FAILED", f"Cannot load config to check LLM settings: {e}"
    
    # Skip check if LLM is disabled
    if not cfg.enabled:
        return "SKIPPED", "LLM disabled in config"
    
    from urllib.error import URLError
    from urllib.request import urlopen
    
    url = f"{cfg.base_url}/v1/models"
    
    try:
        with urlopen(url, timeout=2) as resp:
            if resp.status == 200:
                return "OK", f"{url} returned HTTP {resp.status}"
    except URLError as e:
        return "FAILED", f"Cannot reach KoboldCpp at {url}: {e.reason}"


def check_input_device() -> tuple[str, str]:
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        matches = [d for d in devices if d.get("max_input_channels", 0) >= 1]
        if matches:
            return "OK", f"{len(matches)} device(s) found"
        return "FAILED", "No input devices with max_input_channels >= 1"
    except Exception as exc:
        return "FAILED", str(exc)


def check_output_device() -> tuple[str, str]:
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        matches = [d for d in devices if d.get("max_output_channels", 0) >= 1]
        if matches:
            return "OK", f"{len(matches)} device(s) found"
        return "FAILED", "No output devices with max_output_channels >= 1"
    except Exception as exc:
        return "FAILED", str(exc)


def as_warning(checker):
    """Turn a failed audio-device check into WARN when --no-audio is used."""

    def wrapped() -> tuple[str, str]:
        status, detail = checker()
        if status == "FAILED":
            return "WARN", f"skipped (--no-audio): {detail}"
        return status, detail

    return wrapped


def main(argv=None) -> int:
    args = argv if isinstance(argv, argparse.Namespace) else build_parser().parse_args(argv)

    checks = [
        ("Python 3.11", check_python_version),
        ("numpy 1.x", check_numpy_version),
        ("imports", check_imports),
        ("PortAudio", check_portaudio),
        ("Piper binary", check_piper_binary),
        ("Piper espeak data", check_piper_espeak_data),
        ("Piper voice", check_piper_voice),
        ("Voice config", check_voice_config),
        ("Voice compatibility", check_voice_compatibility),
        ("Whisper model", check_whisper_model),
        ("KoboldCpp server", check_llm_server),
    ]

    audio_checks = [("Input device", check_input_device), ("Output device", check_output_device)]
    if args.no_audio:
        audio_checks = [(name, as_warning(fn)) for name, fn in audio_checks]
    checks.extend(audio_checks)

    print("=" * 60)
    print("Hideko MVP - Environment Check")
    print("=" * 60)
    print(f"{'check':<20} {'status':<8} detail")
    print("-" * 60)

    all_passed = True
    for name, checker in checks:
        status, detail = checker()
        print_table_row(name, status, detail)
        if status == "FAILED":
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("All required checks passed.")
        return 0
    print("Some checks failed. See details above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
