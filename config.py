from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

from errors import ConfigError

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent


# Dataclasses (must be defined before use)
@dataclass(frozen=True)
class AudioConfig:
    input_device: int | str | None
    output_device: int | str | None
    sample_rate: int
    channels: int
    block_ms: int
    playback_volume: float

    @property
    def blocksize(self) -> int:
        return self.sample_rate * self.block_ms // 1000


@dataclass(frozen=True)
class VADConfig:
    energy_threshold_db: float
    calibrate: bool
    calibration_ms: int
    silence_ms: int
    min_speech_ms: int
    max_utterance_s: float
    pre_roll_ms: int
    post_playback_flush_ms: int


@dataclass(frozen=True)
class STTConfig:
    model_size: str
    device: str
    compute_type: str
    language: str | None
    beam_size: int
    cpu_threads: int | None
    download_root: Path
    min_avg_logprob: float
    max_audio_s: float


@dataclass(frozen=True)
class TTSConfig:
    backend: str
    piper_exe: Path
    voice_model: Path
    length_scale: float
    max_chars: int
    timeout_s: float


@dataclass(frozen=True)
class ResponsesConfig:
    triggers_file: Path
    fallbacks_file: Path


@dataclass(frozen=True)
class RuntimeConfig:
    half_duplex: bool
    max_turns: int
    log_transcripts: bool
    greet_on_start: bool
    echo_mode: bool


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    file: Path
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    base_url: str
    endpoint: str
    model: str
    temperature: float
    max_tokens: int
    timeout_s: float
    system_prompt: str
    persona_file: Path


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool
    file: Path
    max_facts: int
    max_value_chars: int


@dataclass(frozen=True)
class WakeWordConfig:
    enabled: bool
    phrases: tuple[str, ...]
    threshold_db: float
    min_wake_duration_ms: int
    listen_mode_timeout_s: float


@dataclass(frozen=True)
class AppConfig:
    root: Path
    audio: AudioConfig
    vad: VADConfig
    stt: STTConfig
    tts: TTSConfig
    responses: ResponsesConfig
    runtime: RuntimeConfig
    logging: LoggingConfig
    memory: MemoryConfig
    llm: LLMConfig
    wake_word: WakeWordConfig
    source: Path  # the config.yaml that produced this object


# Default values matching config.yaml exactly
_DEFAULTS: dict[str, Any] = {
    "audio": {
        "input_device": None,
        "output_device": None,
        "sample_rate": 16000,
        "channels": 1,
        "block_ms": 32,
        "playback_volume": 1.0,
    },
    "vad": {
        "energy_threshold_db": -40.0,
        "calibrate": True,
        "calibration_ms": 1000,
        "silence_ms": 450,
        "min_speech_ms": 200,
        "max_utterance_s": 15.0,
        "pre_roll_ms": 300,
        "post_playback_flush_ms": 150,
    },
    "stt": {
        "model_size": "tiny.en",
        "device": "cpu",
        "compute_type": "int8",
        "language": "en",
        "beam_size": 1,
        "cpu_threads": None,
        "download_root": "models/whisper",
        "min_avg_logprob": -1.0,
        "max_audio_s": 30.0,
    },
    "tts": {
        "backend": "exe",
        "piper_exe": "models/piper/piper/piper.exe",
        "voice_model": "models/piper/en_US-amy-medium.onnx",
        "length_scale": 1.0,
        "max_chars": 300,
        "timeout_s": 30.0,
    },
    "responses": {
        "triggers_file": "responses/triggers.yaml",
        "fallbacks_file": "responses/fallbacks.yaml",
    },
    "runtime": {
        "half_duplex": True,
        "max_turns": 0,
        "log_transcripts": True,
        "greet_on_start": True,
        "echo_mode": False,
    },
    "logging": {
        "level": "INFO",
        "file": "logs/hideko.log",
        "max_bytes": 1048576,
        "backup_count": 3,
    },
    "memory": {
        "enabled": True,
        "file": "memory/facts.json",
        "max_facts": 100,
        "max_value_chars": 120,
    },
    "llm": {
        "enabled": False,
        "base_url": "http://127.0.0.1:5001",
        "endpoint": "/v1/chat/completions",
        "model": "local",
        "temperature": 0.7,
        "max_tokens": 80,
        "timeout_s": 15.0,
        "system_prompt": (
            "You are Hideko, a brief friendly voice assistant. "
            "Answer in one or two short sentences. "
            "Never claim to have internet access."
        ),
        "persona_file": "persona/hideko.yaml",
    },
    "wake_word": {
        "enabled": False,
        "phrases": ("hideko", "hey hideko"),
        "threshold_db": -35.0,
        "min_wake_duration_ms": 800,
        "listen_mode_timeout_s": 10.0,
    },
}


def _get(section: dict[str, Any], key: str, default: Any, where: str) -> Any:
    """Get a value from the config section with path-aware error messages."""
    if section is None:
        return default
    if key not in section:
        return default
    value = section[key]
    # Check for unknown keys (keys that aren't in defaults)
    if key not in _DEFAULTS.get(section.get("audio") if "audio" in section else {}, {}):
        # Actually, we need to check against the specific section's defaults
        pass
    return value


def _get_known_keys(section_type: str) -> set[str]:
    """Return known keys for a config section."""
    if section_type == "audio":
        return {"input_device", "output_device", "sample_rate", "channels", "block_ms", "playback_volume"}
    elif section_type == "vad":
        return {
            "energy_threshold_db", "calibrate", "calibration_ms", "silence_ms",
            "min_speech_ms", "max_utterance_s", "pre_roll_ms", "post_playback_flush_ms"
        }
    elif section_type == "stt":
        return {
            "model_size", "device", "compute_type", "language", "beam_size",
            "cpu_threads", "download_root", "min_avg_logprob", "max_audio_s"
        }
    elif section_type == "tts":
        return {
            "backend", "piper_exe", "voice_model", "length_scale",
            "max_chars", "timeout_s"
        }
    elif section_type == "responses":
        return {"triggers_file", "fallbacks_file"}
    elif section_type == "runtime":
        return {
            "half_duplex", "max_turns", "log_transcripts",
            "greet_on_start", "echo_mode"
        }
    elif section_type == "logging":
        return {"level", "file", "max_bytes", "backup_count"}
    elif section_type == "memory":
        return {"enabled", "file", "max_facts", "max_value_chars"}
    elif section_type == "llm":
        return {
            "enabled", "base_url", "endpoint", "model", "temperature",
            "max_tokens", "timeout_s", "system_prompt", "persona_file",
        }
    return set()


def _check_unknown_keys(config: dict[str, Any], path: str = "") -> None:
    """Check for unknown keys and log warnings."""
    known_sections = {
        "audio", "vad", "stt", "tts", "responses", "runtime", "logging", "memory", "llm", "wake_word"
    }
    
    # Known keys for each section
    section_keys = {
        "audio": {"input_device", "output_device", "sample_rate", "channels", "block_ms", "playback_volume"},
        "vad": {"energy_threshold_db", "calibrate", "calibration_ms", "silence_ms", "min_speech_ms", "max_utterance_s", "pre_roll_ms", "post_playback_flush_ms"},
        "stt": {"model_size", "device", "compute_type", "language", "beam_size", "cpu_threads", "download_root", "min_avg_logprob", "max_audio_s"},
        "tts": {"backend", "piper_exe", "voice_model", "length_scale", "max_chars", "timeout_s"},
        "responses": {"triggers_file", "fallbacks_file"},
        "runtime": {"half_duplex", "max_turns", "log_transcripts", "greet_on_start", "echo_mode"},
        "logging": {"level", "file", "max_bytes", "backup_count"},
        "memory": {"enabled", "file", "max_facts", "max_value_chars"},
        "llm": {
            "enabled", "base_url", "endpoint", "model", "temperature",
            "max_tokens", "timeout_s", "system_prompt", "persona_file",
        },
        "wake_word": {"enabled", "phrases", "threshold_db", "min_wake_duration_ms", "listen_mode_timeout_s"},
    }
    
    for key, value in config.items():
        current_path = f"{path}.{key}" if path else key
        
        # Check top-level keys
        if key not in known_sections:
            logger.warning(f"Unknown top-level key: {current_path}")
            continue
        
        # Check nested keys within known sections
        if isinstance(value, dict):
            known = section_keys.get(key, set())
            for nested_key in value:
                if nested_key not in known:
                    logger.warning(f"Unknown key: {current_path}.{nested_key}")


# Known keys for each section (used by _get_known_keys)
SECTION_KEY_MAP: dict[str, set[str]] = {
    "audio": {"input_device", "output_device", "sample_rate", "channels", "block_ms", "playback_volume"},
    "vad": {"energy_threshold_db", "calibrate", "calibration_ms", "silence_ms", "min_speech_ms", "max_utterance_s", "pre_roll_ms", "post_playback_flush_ms"},
    "stt": {"model_size", "device", "compute_type", "language", "beam_size", "cpu_threads", "download_root", "min_avg_logprob", "max_audio_s"},
    "tts": {"backend", "piper_exe", "voice_model", "length_scale", "max_chars", "timeout_s"},
    "responses": {"triggers_file", "fallbacks_file"},
    "runtime": {"half_duplex", "max_turns", "log_transcripts", "greet_on_start", "echo_mode"},
    "logging": {"level", "file", "max_bytes", "backup_count"},
    "memory": {"enabled", "file", "max_facts", "max_value_chars"},
    "llm": {
        "enabled", "base_url", "endpoint", "model", "temperature",
        "max_tokens", "timeout_s", "system_prompt", "persona_file",
    },
    "wake_word": {"enabled", "phrases", "threshold_db", "min_wake_duration_ms", "listen_mode_timeout_s"},
}


def _get_known_keys(section_type: str) -> set[str]:
    """Return known keys for a config section."""
    if section_type == "audio":
        return {"input_device", "output_device", "sample_rate", "channels", "block_ms", "playback_volume"}
    elif section_type == "vad":
        return {
            "energy_threshold_db", "calibrate", "calibration_ms", "silence_ms",
            "min_speech_ms", "max_utterance_s", "pre_roll_ms", "post_playback_flush_ms"
        }
    elif section_type == "stt":
        return {
            "model_size", "device", "compute_type", "language", "beam_size",
            "cpu_threads", "download_root", "min_avg_logprob", "max_audio_s"
        }
    elif section_type == "tts":
        return {
            "backend", "piper_exe", "voice_model", "length_scale",
            "max_chars", "timeout_s"
        }
    elif section_type == "responses":
        return {"triggers_file", "fallbacks_file"}
    elif section_type == "runtime":
        return {
            "half_duplex", "max_turns", "log_transcripts",
            "greet_on_start", "echo_mode"
        }
    elif section_type == "logging":
        return {"level", "file", "max_bytes", "backup_count"}
    elif section_type == "memory":
        return {"enabled", "file", "max_facts", "max_value_chars"}
    elif section_type == "llm":
        return {
            "enabled", "model_path", "temperature", "max_tokens", "context_window",
            "n_threads", "n_gpu_layers", "timeout_s", "system_prompt",
        }
    elif section_type == "wake_word":
        return {"enabled", "phrases", "threshold_db", "min_wake_duration_ms", "listen_mode_timeout_s"}
    return set()


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping, got {type(value).__name__}")
    return value


def _validate_bool(value: Any, field_name: str, where: str) -> bool:
    """Validate that a value is a proper boolean (not a string like 'true')."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        # YAML 1.1 booleans like 'yes', 'on', 'no', 'off' are handled by safe_load as actual bools
        # But someone might manually write "true" or "false" as a string - that's an error
        raise ConfigError(f"{where}.{field_name} must be a boolean, got string '{value}'")
    raise ConfigError(f"{where}.{field_name} must be a boolean, got {type(value).__name__}")


def _validate_audio(config: dict[str, Any], path: str = "audio") -> None:
    """Validate audio section."""
    sample_rate = config.get("sample_rate", _DEFAULTS["audio"]["sample_rate"])
    if sample_rate != 16000:
        raise ConfigError(f"{path}.sample_rate must be 16000 (Whisper requires 16 kHz), got {sample_rate}")

    block_ms = config.get("block_ms", _DEFAULTS["audio"]["block_ms"])
    # Convert to int if string, for YAML compatibility
    if isinstance(block_ms, str):
        try:
            block_ms = int(block_ms)
        except ValueError:
            raise ConfigError(f"{path}.block_ms must be an int between 10 and 100, got '{block_ms}'")
    if not (10 <= block_ms <= 100):
        raise ConfigError(f"{path}.block_ms must be between 10 and 100, got {block_ms}")

    channels = config.get("channels", _DEFAULTS["audio"]["channels"])
    if channels != 1:
        raise ConfigError(f"{path}.channels must be 1 (mono), got {channels}")

    volume = config.get("playback_volume", _DEFAULTS["audio"]["playback_volume"])
    # Convert to float if string, for YAML compatibility  
    if isinstance(volume, str):
        try:
            volume = float(volume)
        except ValueError:
            raise ConfigError(f"{path}.playback_volume must be a float between 0.0 and 1.5, got '{volume}'")
    if not (0.0 <= volume <= 1.5):
        raise ConfigError(f"{path}.playback_volume must be between 0.0 and 1.5, got {volume}")


def _validate_vad(config: dict[str, Any], path: str = "vad") -> None:
    """Validate VAD section."""
    silence_ms = config.get("silence_ms", _DEFAULTS["vad"]["silence_ms"])
    # Convert to int if string, for YAML compatibility
    if isinstance(silence_ms, str):
        try:
            silence_ms = int(silence_ms)
        except ValueError:
            raise ConfigError(f"{path}.silence_ms must be an int between 100 and 2000, got '{silence_ms}'")
    if not (100 <= silence_ms <= 2000):
        raise ConfigError(f"{path}.silence_ms must be at least 100, got {silence_ms}")

    min_speech_ms = config.get("min_speech_ms", _DEFAULTS["vad"]["min_speech_ms"])
    if isinstance(min_speech_ms, str):
        try:
            min_speech_ms = int(min_speech_ms)
        except ValueError:
            raise ConfigError(f"{path}.min_speech_ms must be an int between 50 and 3000, got '{min_speech_ms}'")
    if not (50 <= min_speech_ms <= 3000):
        raise ConfigError(f"{path}.min_speech_ms must be at least 50, got {min_speech_ms}")

    max_utterance_s = config.get("max_utterance_s", _DEFAULTS["vad"]["max_utterance_s"])
    if not (1.0 <= max_utterance_s <= 60.0):
        raise ConfigError(f"{path}.max_utterance_s must be between 1 and 60, got {max_utterance_s}")

    pre_roll_ms = config.get("pre_roll_ms", _DEFAULTS["vad"]["pre_roll_ms"])
    if isinstance(pre_roll_ms, str):
        try:
            pre_roll_ms = int(pre_roll_ms)
        except ValueError:
            raise ConfigError(f"{path}.pre_roll_ms must be an int > {path}.min_speech_ms, got '{pre_roll_ms}'")
    if not isinstance(pre_roll_ms, int) or pre_roll_ms <= min_speech_ms:
        raise ConfigError(
            f"{path}.pre_roll_ms ({pre_roll_ms}) must be >= {path}.min_speech_ms ({min_speech_ms}) "
            "(the utterance onset would be clipped; pre-roll must cover the speech-detection window)"
        )

    flush_ms = config.get("post_playback_flush_ms", _DEFAULTS["vad"]["post_playback_flush_ms"])
    if isinstance(flush_ms, str):
        try:
            flush_ms = int(flush_ms)
        except ValueError:
            raise ConfigError(f"{path}.post_playback_flush_ms must be an int between 50 and 2000, got '{flush_ms}'")
    if not isinstance(flush_ms, int) or not (50 <= flush_ms <= 2000):
        raise ConfigError(
            f"{path}.post_playback_flush_ms must be an int between 50 and 2000, got {flush_ms}"
        )


def _validate_stt(config: dict[str, Any], path: str = "stt") -> None:
    """Validate STT section."""
    model_size = config.get("model_size", _DEFAULTS["stt"]["model_size"])
    valid_sizes = {"tiny", "tiny.en", "base", "base.en", "small", "small.en"}
    if model_size not in valid_sizes:
        raise ConfigError(
            f"{path}.model_size must be one of {sorted(valid_sizes)}, got '{model_size}'"
        )

    compute_type = config.get("compute_type", _DEFAULTS["stt"]["compute_type"])
    valid_compute = {"int8", "int8_float32", "float32"}
    if compute_type not in valid_compute:
        raise ConfigError(
            f"{path}.compute_type must be one of {sorted(valid_compute)}, got '{compute_type}'"
        )

    cpu_threads = config.get("cpu_threads", _DEFAULTS["stt"]["cpu_threads"])
    if cpu_threads is not None and (
        isinstance(cpu_threads, bool) or not isinstance(cpu_threads, int) or not (1 <= cpu_threads <= 64)
    ):
        raise ConfigError(
            f"{path}.cpu_threads must be null or an int between 1 and 64, got {cpu_threads}"
        )


def _validate_tts(config: dict[str, Any], path: str = "tts") -> None:
    """Validate TTS section."""
    backend = config.get("backend", _DEFAULTS["tts"]["backend"])
    if backend not in {"exe", "python"}:
        raise ConfigError(f"{path}.backend must be 'exe' or 'python', got '{backend}'")

    length_scale = config.get("length_scale", _DEFAULTS["tts"]["length_scale"])
    if not (0.5 <= length_scale <= 2.0):
        raise ConfigError(f"{path}.length_scale must be between 0.5 and 2.0, got {length_scale}")


def _validate_logging(config: dict[str, Any], path: str = "logging") -> None:
    """Validate logging section."""
    level = config.get("level", _DEFAULTS["logging"]["level"])
    if not isinstance(level, str):
        raise ConfigError(f"{path}.level must be a string, got {type(level).__name__}")
    
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}
    if level not in valid_levels:
        raise ConfigError(f"{path}.level must be one of {sorted(valid_levels)}, got '{level}'")


def _validate_memory(config: dict[str, Any], path: str = "memory") -> None:
    """Validate the memory section."""
    max_facts = config.get("max_facts", _DEFAULTS["memory"]["max_facts"])
    if not isinstance(max_facts, int) or isinstance(max_facts, bool) or not (1 <= max_facts <= 1000):
        raise ConfigError(f"{path}.max_facts must be an int between 1 and 1000, got {max_facts}")

    max_value_chars = config.get("max_value_chars", _DEFAULTS["memory"]["max_value_chars"])
    if not isinstance(max_value_chars, int) or isinstance(max_value_chars, bool) or not (10 <= max_value_chars <= 500):
        raise ConfigError(f"{path}.max_value_chars must be an int between 10 and 500, got {max_value_chars}")


def _validate_llm(config: dict[str, Any], path: str = "llm") -> None:
    """Validate the LLM section."""
    base_url = config.get("base_url", _DEFAULTS["llm"]["base_url"])
    if not isinstance(base_url, str) or not base_url.startswith(("http://127.0.0.1", "http://localhost")):
        raise ConfigError(f"{path}.base_url must be a loopback http URL, got {base_url!r}")
    endpoint = config.get("endpoint", _DEFAULTS["llm"]["endpoint"])
    if not isinstance(endpoint, str) or not endpoint.startswith("/"):
        raise ConfigError(f"{path}.endpoint must start with '/', got {endpoint!r}")
    model = config.get("model", _DEFAULTS["llm"]["model"])
    if not isinstance(model, str) or not model.strip():
        raise ConfigError(f"{path}.model must be a non-empty string")
    temperature = config.get("temperature", _DEFAULTS["llm"]["temperature"])
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not (0.0 <= temperature <= 1.5):
        raise ConfigError(f"{path}.temperature must be between 0.0 and 1.5, got {temperature}")
    max_tokens = config.get("max_tokens", _DEFAULTS["llm"]["max_tokens"])
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not (8 <= max_tokens <= 256):
        raise ConfigError(f"{path}.max_tokens must be an int between 8 and 256, got {max_tokens}")
    timeout_s = config.get("timeout_s", _DEFAULTS["llm"]["timeout_s"])
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not (1.0 <= timeout_s <= 120.0):
        raise ConfigError(f"{path}.timeout_s must be between 1 and 120 seconds, got {timeout_s}")
    system_prompt = config.get("system_prompt", _DEFAULTS["llm"]["system_prompt"])
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ConfigError(f"{path}.system_prompt must be a non-empty string")


def _validate_wake_word(config: dict[str, Any], path: str = "wake_word") -> None:
    """Validate the wake word section."""
    enabled = config.get("enabled", _DEFAULTS["wake_word"]["enabled"])
    if not isinstance(enabled, bool):
        raise ConfigError(f"{path}.enabled must be a boolean, got {type(enabled).__name__}")

    phrases = config.get("phrases", _DEFAULTS["wake_word"]["phrases"])
    if not isinstance(phrases, (list, tuple)):
        raise ConfigError(f"{path}.phrases must be a list or tuple, got {type(phrases).__name__}")
    if not phrases:
        raise ConfigError(f"{path}.phrases must not be empty")
    for i, p in enumerate(phrases):
        if not isinstance(p, str) or not p.strip():
            raise ConfigError(f"{path}.phrases[{i}] must be a non-empty string, got {p!r}")

    threshold_db = config.get("threshold_db", _DEFAULTS["wake_word"]["threshold_db"])
    if not isinstance(threshold_db, (int, float)) or isinstance(threshold_db, bool):
        raise ConfigError(f"{path}.threshold_db must be a number, got {type(threshold_db).__name__}")
    if not (-90.0 <= threshold_db <= 0.0):
        raise ConfigError(f"{path}.threshold_db must be between -90.0 and 0.0, got {threshold_db}")

    min_wake_duration_ms = config.get("min_wake_duration_ms", _DEFAULTS["wake_word"]["min_wake_duration_ms"])
    if not isinstance(min_wake_duration_ms, int) or isinstance(min_wake_duration_ms, bool):
        raise ConfigError(f"{path}.min_wake_duration_ms must be an int, got {type(min_wake_duration_ms).__name__}")
    if not (200 <= min_wake_duration_ms <= 5000):
        raise ConfigError(f"{path}.min_wake_duration_ms must be between 200 and 5000, got {min_wake_duration_ms}")

    listen_mode_timeout_s = config.get("listen_mode_timeout_s", _DEFAULTS["wake_word"]["listen_mode_timeout_s"])
    if not isinstance(listen_mode_timeout_s, (int, float)) or isinstance(listen_mode_timeout_s, bool):
        raise ConfigError(f"{path}.listen_mode_timeout_s must be a number, got {type(listen_mode_timeout_s).__name__}")
    if not (1.0 <= listen_mode_timeout_s <= 120.0):
        raise ConfigError(f"{path}.listen_mode_timeout_s must be between 1.0 and 120.0, got {listen_mode_timeout_s}")


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate configuration from a YAML file."""
    # Convert to Path if string
    if isinstance(path, str):
        path = Path(path)
    
    config_path = PROJECT_ROOT / path if not path.is_absolute() else path
    
    # Check file exists and is readable
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")
    
    if not config_path.is_file():
        raise ConfigError(f"Config path is not a file: {config_path}")
    
    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read config file {config_path}: {e}")
    
    # Check for empty file
    if not content.strip():
        raise ConfigError("config.yaml is empty")
    
    # Parse YAML
    try:
        raw_config = yaml.safe_load(content)
    except yaml.YAMLError as e:
        if hasattr(e, "problem_mark"):
            mark = e.problem_mark
            line = mark.line + 1 if hasattr(mark, "line") else 1
            column = mark.column + 1 if hasattr(mark, "column") else 1
            raise ConfigError(
                f"YAML syntax error at line {line}, column {column}: {e}"
            ) from e
        raise ConfigError(f"YAML parsing failed: {e}") from e
    
    # Check top-level is a mapping
    if raw_config is None:
        raise ConfigError("config.yaml is empty or contains no valid YAML")
    if not isinstance(raw_config, dict):
        raise ConfigError(f"config root must be a mapping (dict), got {type(raw_config).__name__}")
    
    # Check for unknown keys
    _check_unknown_keys(raw_config)
    
    # Build config with defaults and validation
    def get_value(section: dict | None, key: str, default: Any) -> Any:
        if section is None or key not in section:
            return default
        value = section[key]
        # Special handling for null string
        if value == "null":
            return None
        return value
    
    def build_audio() -> AudioConfig:
        audio_section = get_value(raw_config, "audio", {})
        if not isinstance(audio_section, dict):
            raise ConfigError(f"audio must be a mapping (dict), got {type(audio_section).__name__}")
        _validate_audio(audio_section)
        
        # Convert string values to proper types for numeric fields
        def convert_value(val):
            if isinstance(val, str):
                try:
                    return int(val)
                except ValueError:
                    try:
                        return float(val)
                    except ValueError:
                        pass
            return val
        
        return AudioConfig(
            input_device=convert_value(get_value(audio_section, "input_device", _DEFAULTS["audio"]["input_device"])),
            output_device=convert_value(get_value(audio_section, "output_device", _DEFAULTS["audio"]["output_device"])),
            sample_rate=convert_value(get_value(audio_section, "sample_rate", _DEFAULTS["audio"]["sample_rate"])),
            channels=convert_value(get_value(audio_section, "channels", _DEFAULTS["audio"]["channels"])),
            block_ms=convert_value(get_value(audio_section, "block_ms", _DEFAULTS["audio"]["block_ms"])),
            playback_volume=convert_value(get_value(audio_section, "playback_volume", _DEFAULTS["audio"]["playback_volume"])),
        )
    
    def build_vad() -> VADConfig:
        vad_section = get_value(raw_config, "vad", {})
        if not isinstance(vad_section, dict):
            raise ConfigError(f"vad must be a mapping (dict), got {type(vad_section).__name__}")
        _validate_vad(vad_section)
        
        # Convert string values to proper types for numeric fields
        def convert_value(val):
            if isinstance(val, str):
                try:
                    return int(val)
                except ValueError:
                    try:
                        return float(val)
                    except ValueError:
                        pass
            return val
        
        return VADConfig(
            energy_threshold_db=convert_value(get_value(vad_section, "energy_threshold_db", _DEFAULTS["vad"]["energy_threshold_db"])),
            calibrate=_validate_bool(get_value(vad_section, "calibrate", _DEFAULTS["vad"]["calibrate"]), "calibrate", "vad"),
            calibration_ms=convert_value(get_value(vad_section, "calibration_ms", _DEFAULTS["vad"]["calibration_ms"])),
            silence_ms=convert_value(get_value(vad_section, "silence_ms", _DEFAULTS["vad"]["silence_ms"])),
            min_speech_ms=convert_value(get_value(vad_section, "min_speech_ms", _DEFAULTS["vad"]["min_speech_ms"])),
            max_utterance_s=convert_value(get_value(vad_section, "max_utterance_s", _DEFAULTS["vad"]["max_utterance_s"])),
            pre_roll_ms=convert_value(get_value(vad_section, "pre_roll_ms", _DEFAULTS["vad"]["pre_roll_ms"])),
            post_playback_flush_ms=convert_value(get_value(vad_section, "post_playback_flush_ms", _DEFAULTS["vad"]["post_playback_flush_ms"])),
        )
    
    def build_stt() -> STTConfig:
        stt_section = get_value(raw_config, "stt", {})
        if not isinstance(stt_section, dict):
            raise ConfigError(f"stt must be a mapping (dict), got {type(stt_section).__name__}")
        _validate_stt(stt_section)
        
        # Resolve paths against config_path.parent
        download_root = Path(get_value(stt_section, "download_root", _DEFAULTS["stt"]["download_root"]))
        if not download_root.is_absolute():
            download_root = config_path.parent / download_root
        
        return STTConfig(
            model_size=get_value(stt_section, "model_size", _DEFAULTS["stt"]["model_size"]),
            device=get_value(stt_section, "device", _DEFAULTS["stt"]["device"]),
            compute_type=get_value(stt_section, "compute_type", _DEFAULTS["stt"]["compute_type"]),
            language=get_value(stt_section, "language", _DEFAULTS["stt"]["language"]),
            beam_size=get_value(stt_section, "beam_size", _DEFAULTS["stt"]["beam_size"]),
            cpu_threads=get_value(stt_section, "cpu_threads", _DEFAULTS["stt"]["cpu_threads"]),
            download_root=download_root,
            min_avg_logprob=get_value(stt_section, "min_avg_logprob", _DEFAULTS["stt"]["min_avg_logprob"]),
            max_audio_s=get_value(stt_section, "max_audio_s", _DEFAULTS["stt"]["max_audio_s"]),
        )
    
    def build_tts() -> TTSConfig:
        tts_section = get_value(raw_config, "tts", {})
        if not isinstance(tts_section, dict):
            raise ConfigError(f"tts must be a mapping (dict), got {type(tts_section).__name__}")
        _validate_tts(tts_section)
        
        # Resolve paths against config_path.parent
        piper_exe = Path(get_value(tts_section, "piper_exe", _DEFAULTS["tts"]["piper_exe"]))
        if not piper_exe.is_absolute():
            piper_exe = config_path.parent / piper_exe
        
        voice_model = Path(get_value(tts_section, "voice_model", _DEFAULTS["tts"]["voice_model"]))
        if not voice_model.is_absolute():
            voice_model = config_path.parent / voice_model
        
        return TTSConfig(
            backend=get_value(tts_section, "backend", _DEFAULTS["tts"]["backend"]),
            piper_exe=piper_exe,
            voice_model=voice_model,
            length_scale=get_value(tts_section, "length_scale", _DEFAULTS["tts"]["length_scale"]),
            max_chars=get_value(tts_section, "max_chars", _DEFAULTS["tts"]["max_chars"]),
            timeout_s=get_value(tts_section, "timeout_s", _DEFAULTS["tts"]["timeout_s"]),
        )
    
    def build_responses() -> ResponsesConfig:
        responses_section = get_value(raw_config, "responses", {})
        if not isinstance(responses_section, dict):
            raise ConfigError(f"responses must be a mapping (dict), got {type(responses_section).__name__}")
        
        triggers_file = Path(get_value(responses_section, "triggers_file", _DEFAULTS["responses"]["triggers_file"]))
        if not triggers_file.is_absolute():
            triggers_file = config_path.parent / triggers_file
        
        fallbacks_file = Path(get_value(responses_section, "fallbacks_file", _DEFAULTS["responses"]["fallbacks_file"]))
        if not fallbacks_file.is_absolute():
            fallbacks_file = config_path.parent / fallbacks_file
        
        return ResponsesConfig(
            triggers_file=triggers_file,
            fallbacks_file=fallbacks_file,
        )
    
    def build_runtime() -> RuntimeConfig:
        runtime_section = get_value(raw_config, "runtime", {})
        if not isinstance(runtime_section, dict):
            raise ConfigError(f"runtime must be a mapping (dict), got {type(runtime_section).__name__}")
        
        return RuntimeConfig(
            half_duplex=_validate_bool(get_value(runtime_section, "half_duplex", _DEFAULTS["runtime"]["half_duplex"]), "half_duplex", "runtime"),
            max_turns=get_value(runtime_section, "max_turns", _DEFAULTS["runtime"]["max_turns"]),
            log_transcripts=_validate_bool(get_value(runtime_section, "log_transcripts", _DEFAULTS["runtime"]["log_transcripts"]), "log_transcripts", "runtime"),
            greet_on_start=_validate_bool(get_value(runtime_section, "greet_on_start", _DEFAULTS["runtime"]["greet_on_start"]), "greet_on_start", "runtime"),
            echo_mode=_validate_bool(get_value(runtime_section, "echo_mode", _DEFAULTS["runtime"]["echo_mode"]), "echo_mode", "runtime"),
        )
    
    def build_logging() -> LoggingConfig:
        logging_section = get_value(raw_config, "logging", {})
        if not isinstance(logging_section, dict):
            raise ConfigError(f"logging must be a mapping (dict), got {type(logging_section).__name__}")
        _validate_logging(logging_section)
        
        # Resolve paths against config_path.parent
        file_path = Path(get_value(logging_section, "file", _DEFAULTS["logging"]["file"]))
        if not file_path.is_absolute():
            file_path = config_path.parent / file_path
        
        return LoggingConfig(
            level=get_value(logging_section, "level", _DEFAULTS["logging"]["level"]),
            file=file_path,
            max_bytes=get_value(logging_section, "max_bytes", _DEFAULTS["logging"]["max_bytes"]),
            backup_count=get_value(logging_section, "backup_count", _DEFAULTS["logging"]["backup_count"]),
        )

    def build_memory() -> MemoryConfig:
        memory_section = get_value(raw_config, "memory", {})
        if not isinstance(memory_section, dict):
            raise ConfigError(f"memory must be a mapping (dict), got {type(memory_section).__name__}")
        _validate_memory(memory_section)
        memory_file = Path(get_value(memory_section, "file", _DEFAULTS["memory"]["file"]))
        if not memory_file.is_absolute():
            memory_file = config_path.parent / memory_file
        return MemoryConfig(
            enabled=_validate_bool(
                get_value(memory_section, "enabled", _DEFAULTS["memory"]["enabled"]),
                "enabled", "memory",
            ),
            file=memory_file,
            max_facts=get_value(memory_section, "max_facts", _DEFAULTS["memory"]["max_facts"]),
            max_value_chars=get_value(memory_section, "max_value_chars", _DEFAULTS["memory"]["max_value_chars"]),
        )

    def build_llm() -> LLMConfig:
        llm_section = get_value(raw_config, "llm", {})
        if not isinstance(llm_section, dict):
            raise ConfigError(f"llm must be a mapping (dict), got {type(llm_section).__name__}")
        _validate_llm(llm_section)

        # Resolve persona_file against config_path.parent
        persona_file = Path(get_value(llm_section, "persona_file", _DEFAULTS["llm"]["persona_file"]))
        if not persona_file.is_absolute():
            persona_file = config_path.parent / persona_file

        return LLMConfig(
            enabled=_validate_bool(
                get_value(llm_section, "enabled", _DEFAULTS["llm"]["enabled"]),
                "enabled", "llm",
            ),
            base_url=get_value(llm_section, "base_url", _DEFAULTS["llm"]["base_url"]),
            endpoint=get_value(llm_section, "endpoint", _DEFAULTS["llm"]["endpoint"]),
            model=get_value(llm_section, "model", _DEFAULTS["llm"]["model"]),
            temperature=get_value(llm_section, "temperature", _DEFAULTS["llm"]["temperature"]),
            max_tokens=get_value(llm_section, "max_tokens", _DEFAULTS["llm"]["max_tokens"]),
            timeout_s=get_value(llm_section, "timeout_s", _DEFAULTS["llm"]["timeout_s"]),
            system_prompt=get_value(llm_section, "system_prompt", _DEFAULTS["llm"]["system_prompt"]),
            persona_file=persona_file,
        )

    def build_wake_word() -> WakeWordConfig:
        wake_word_section = get_value(raw_config, "wake_word", {})
        if not isinstance(wake_word_section, dict):
            raise ConfigError(f"wake_word must be a mapping (dict), got {type(wake_word_section).__name__}")
        _validate_wake_word(wake_word_section)
        return WakeWordConfig(
            enabled=_validate_bool(
                get_value(wake_word_section, "enabled", _DEFAULTS["wake_word"]["enabled"]),
                "enabled", "wake_word",
            ),
            phrases=tuple(get_value(wake_word_section, "phrases", _DEFAULTS["wake_word"]["phrases"])),
            threshold_db=get_value(wake_word_section, "threshold_db", _DEFAULTS["wake_word"]["threshold_db"]),
            min_wake_duration_ms=get_value(wake_word_section, "min_wake_duration_ms", _DEFAULTS["wake_word"]["min_wake_duration_ms"]),
            listen_mode_timeout_s=get_value(wake_word_section, "listen_mode_timeout_s", _DEFAULTS["wake_word"]["listen_mode_timeout_s"]),
        )
    
    # Build final AppConfig
    audio = build_audio()
    vad = build_vad()
    stt = build_stt()
    tts = build_tts()
    responses = build_responses()
    runtime = build_runtime()
    logging_conf = build_logging()
    memory = build_memory()
    llm = build_llm()
    wake_word = build_wake_word()

    return AppConfig(
        root=PROJECT_ROOT,
        audio=audio,
        vad=vad,
        stt=stt,
        tts=tts,
        responses=responses,
        runtime=runtime,
        logging=logging_conf,
        memory=memory,
        llm=llm,
        wake_word=wake_word,
        source=config_path,
    )


def _path_to_str(obj: Any) -> Any:
    """Convert Path objects to strings for JSON serialization."""
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _path_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_path_to_str(item) for item in obj]
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description="Hideko configuration loader")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print config as JSON and exit (default if no other args)"
    )
    parser.add_argument(
        "--path",
        type=str,
        default="config.yaml",
        help="Path to config file (relative to project root or absolute)"
    )
    args = parser.parse_args()
    
    try:
        config = load_config(args.path)
        
        if args.check:
            # Convert to dict and serialize as JSON
            config_dict = {
                "root": str(config.root),
                "audio": asdict(config.audio),
                "vad": asdict(config.vad),
                "stt": asdict(config.stt),
                "tts": asdict(config.tts),
                "responses": asdict(config.responses),
                "runtime": asdict(config.runtime),
                "logging": asdict(config.logging),
                "memory": asdict(config.memory),
                "llm": asdict(config.llm),
                "wake_word": asdict(config.wake_word),
                "source": str(config.source),
            }
            # Convert all Path objects to strings
            config_dict = _path_to_str(config_dict)
            print(json.dumps(config_dict, indent=2))
        else:
            # Default behavior: just load (silently)
            pass
        
        sys.exit(0)
        
    except ConfigError as e:
        print(f"CONFIG ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
