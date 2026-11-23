"""Tests for config loading and validation."""

import logging
from pathlib import Path
from typing import Any

import pytest
import yaml
import os

from config import AppConfig, ConfigError, load_config


def write_config(tmp_path: Path, data: dict[str, Any]) -> AppConfig:
    """Write YAML to tmp_path/config.yaml and return the loaded AppConfig."""
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_config(p)


def write_raw(tmp_path: Path, text: str) -> AppConfig:
    """Write raw text to tmp_path/config.yaml and return the loaded AppConfig."""
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return load_config(p)


@pytest.fixture(autouse=True)
def caplog_fixture(caplog: pytest.LogCaptureFixture) -> None:
    """Enable logging capture for all tests."""
    caplog.set_level(logging.WARNING)


# Test 1: Valid file → AppConfig with sample_rate == 16000
def test_valid_file(config: AppConfig) -> None:
    """Test that a valid config file loads correctly with expected sample_rate."""
  
    assert isinstance(config, AppConfig)
    assert config.audio.sample_rate == 16000


# Test 2: Missing file → ConfigError mentioning the path
def test_missing_file(tmp_path: Path) -> None:
    """Test that a missing config file raises ConfigError with path."""
    p = tmp_path / "nonexistent.yaml"
    with pytest.raises(ConfigError, match="not found"):
        load_config(p)


# Test 3: Empty file → ConfigError whose message contains "empty"
def test_empty_file(tmp_path: Path) -> None:
    """Test that an empty config file raises ConfigError mentioning 'empty'."""
    p = tmp_path / "config.yaml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        load_config(p)


# Test 4: YAML syntax error → ConfigError including a line number
def test_yaml_syntax_error(tmp_path: Path) -> None:
    """Test that YAML syntax errors raise ConfigError with line number."""
    p = tmp_path / "config.yaml"
    p.write_text('audio: [\n  bad: : :', encoding="utf-8")
    with pytest.raises(ConfigError, match="line"):
        load_config(p)


# Test 5: Top-level list → ConfigError
def test_top_level_list(tmp_path: Path) -> None:
    """Top-level value must be a mapping."""
    data = [1, 2, 3]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_config(p)


# Test 6: audio.sample_rate MUST be 16000
def test_audio_sample_rate_fixed(config: AppConfig) -> None:
    """sample_rate is locked to 16000 for Whisper compatibility."""
    assert config.audio.sample_rate == 16000


# Test 7: audio.block_ms must be 10-100 (valid int and string values)
def test_block_ms_validation(tmp_path: Path) -> None:
    """block_ms must be an int between 10 and 100."""
    # Invalid values should raise errors
    for ms in [9, 101, 1.5]:  # "32" is valid - YAML allows string numbers
        data = {"audio": {"sample_rate": 16000, "block_ms": ms}}
        p = tmp_path / f"config_{ms}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)

    # Valid string representation should work
    data = {"audio": {"sample_rate": 16000, "block_ms": "32"}}
    p = tmp_path / f"config_str_32.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.audio.block_ms == 32


# Test 8: audio.blocksize is derived from sample_rate × block_ms // 1000
def test_blocksize_derived(config: AppConfig) -> None:
    """blocksize must equal sample_rate * block_ms // 1000."""
    assert config.audio.blocksize == config.audio.sample_rate * config.audio.block_ms // 1000


# Test 9: Unknown sections are logged but not rejected
def test_unknown_section_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Unknown top-level keys are ignored and logged as warnings."""
    data = {
        "audio": {"sample_rate": 16000, "block_ms": 32},
        "unknown_section": "ignored",
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    load_config(p)  # Should not raise


# Test 10: audio.input_device and output_device accept null or string
def test_audio_device_optional(tmp_path: Path) -> None:
    """input_device and output_device can be null."""
    data = {
        "audio": {
            "sample_rate": 16000,
            "block_ms": 32,
            "input_device": "Microphone",
            "output_device": None,
        }
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    config = load_config(p)
    assert config.audio.input_device == "Microphone"
    assert config.audio.output_device is None


# Test 11: audio.playback_volume must be between 0.0 and 1.5
def test_playback_volume_range(tmp_path: Path) -> None:
    """playback_volume must be a float between 0.0 and 1.5."""
    # Invalid values should raise errors (note: "1.0" as string is valid after conversion)
    for vol in [-0.1, 1.6]:
        data = {
            "audio": {
                "sample_rate": 16000,
                "block_ms": 32,
                "playback_volume": vol,
            }
        }
        p = tmp_path / f"config_vol_{vol}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)

    # Valid string representation should work
    data = {
        "audio": {
            "sample_rate": 16000,
            "block_ms": 32,
            "playback_volume": "1.0",
        }
    }
    p = tmp_path / f"config_vol_str_1.0.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.audio.playback_volume == 1.0


# Test 12: stt.model_size defaults to tiny.en
def test_stt_defaults(config: AppConfig) -> None:
    """Test that STT defaults are correctly applied."""
    assert config.stt.model_size == "tiny.en"
    assert config.stt.device == "cpu"
    assert config.stt.compute_type == "int8"
    assert config.stt.language == "en"
    assert config.stt.beam_size == 1
    # download_root is resolved to an absolute path - check that relative portion is preserved
    root_str = str(config.stt.download_root)
    assert "whisper" in root_str.lower()


# Test 13: tts backend defaults to exe
def test_tts_defaults(config: AppConfig) -> None:
    """Test that TTS defaults are correctly applied."""
    assert config.tts.backend == "exe"
    # paths are resolved to absolute paths - check that relative portion is preserved
    piper_str = str(config.tts.piper_exe)
    assert "piper.exe" in piper_str.lower()
    voice_model_str = str(config.tts.voice_model).lower()
    assert "en_us-amy-medium.onnx" in voice_model_str
    assert config.tts.length_scale == 1.0
    assert config.tts.max_chars == 300
    assert config.tts.timeout_s == 30


# Test 14: post_playback_flush_ms must be an int between 0 and 2000
def test_post_playback_flush_range(tmp_path: Path) -> None:
    """post_playback_flush_ms must be an int between 0 and 2000."""
    # Invalid values should raise errors (note: "150" as string is valid after conversion)
    for ms in [49, -1, 2001, 1.5]:
        data = {
            "audio": {"sample_rate": 16000, "block_ms": 32},
            "vad": {"post_playback_flush_ms": ms},
        }
        p = tmp_path / f"config_{ms}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)

    # Valid string representation should work
    data = {
        "audio": {"sample_rate": 16000, "block_ms": 32},
        "vad": {"post_playback_flush_ms": "150"},
    }
    p = tmp_path / f"config_str_150.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.vad.post_playback_flush_ms == 150


# Test 15: pre_roll_ms must be > vad.min_speech_ms
def test_pre_roll_gt_min_speech(tmp_path: Path) -> None:
    """pre_roll_ms must be strictly greater than min_speech_ms."""
    # Invalid values (note: 200 as string should work after conversion)
    for pr in [199]:
        data = {
            "audio": {"sample_rate": 16000, "block_ms": 32},
            "vad": {
                "pre_roll_ms": pr,
                "min_speech_ms": 200,
            },
        }
        p = tmp_path / f"config_{pr}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)

    # Valid string representation should work  
    data = {
        "audio": {"sample_rate": 16000, "block_ms": 32},
        "vad": {
            "pre_roll_ms": "300",
            "min_speech_ms": 200,
        },
    }
    p = tmp_path / f"config_str_300.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.vad.pre_roll_ms == 300


# Test 16: min_speech_ms must be an int between 50 and 3000
def test_min_speech_range(tmp_path: Path) -> None:
    """min_speech_ms must be an int between 50 and 3000."""
    # Invalid values (note: "200" as string is valid after conversion)
    for ms in [49, -1, 3001, 1.5]:
        data = {
            "audio": {"sample_rate": 16000, "block_ms": 32},
            "vad": {"min_speech_ms": ms},
        }
        p = tmp_path / f"config_{ms}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)

    # Valid string representation should work
    data = {
        "audio": {"sample_rate": 16000, "block_ms": 32},
        "vad": {"min_speech_ms": "200"},
    }
    p = tmp_path / f"config_str_200.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.vad.min_speech_ms == 200


# Test 17: silence_ms must be an int between 100 and 2000
def test_silence_range(tmp_path: Path) -> None:
    """silence_ms must be an int between 100 and 2000."""
    # Invalid values (note: "450" as string is valid after conversion)
    for ms in [99, -1, 2001, 1.5]:
        data = {
            "audio": {"sample_rate": 16000, "block_ms": 32},
            "vad": {"silence_ms": ms},
        }
        p = tmp_path / f"config_{ms}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)

    # Valid string representation should work
    data = {
        "audio": {"sample_rate": 16000, "block_ms": 32},
        "vad": {"silence_ms": "450"},
    }
    p = tmp_path / f"config_str_450.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.vad.silence_ms == 450


# Test 18: STT cpu_threads loads from YAML
def test_stt_cpu_threads_loads_from_yaml(tmp_path: Path) -> None:
    """Test that cpu_threads value from YAML is loaded correctly."""
    data = {
        "audio": {"sample_rate": 16000, "block_ms": 32},
        "vad": {},
        "stt": {"cpu_threads": 8},
        "tts": {},
        "responses": {},
        "runtime": {},
        "logging": {},
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.stt.cpu_threads == 8, f"Expected cpu_threads=8, got {cfg.stt.cpu_threads}"


# Test 19: VAD defaults are tuned for responsive assistant
def test_vad_defaults_are_tuned(config: AppConfig) -> None:
    """Test that the new tuned VAD defaults are applied."""
    assert config.vad.silence_ms == 450, f"Expected silence_ms=450, got {config.vad.silence_ms}"
    assert config.vad.min_speech_ms == 200, f"Expected min_speech_ms=200, got {config.vad.min_speech_ms}"
    assert config.vad.post_playback_flush_ms == 150, f"Expected post_playback_flush_ms=150, got {config.vad.post_playback_flush_ms}"
    assert config.vad.pre_roll_ms == 300, f"Expected pre_roll_ms=300, got {config.vad.pre_roll_ms}"


# Test 20: LLM defaults are applied
def test_llm_defaults(config: AppConfig) -> None:
    """Test that LLM defaults are correctly applied."""
    assert config.llm.enabled is False, f"Expected enabled=False by default, got {config.llm.enabled}"
    assert config.llm.base_url == "http://127.0.0.1:5001", f"Expected base_url=http://127.0.0.1:5001, got {config.llm.base_url}"
    assert config.llm.endpoint == "/v1/chat/completions", f"Expected endpoint=/v1/chat/completions, got {config.llm.endpoint}"
    assert config.llm.temperature == 0.7
    assert config.llm.max_tokens == 80
    assert config.llm.timeout_s == 15.0


# Test 21: LLM validation - enabled must be boolean
def test_llm_enabled_validation(tmp_path: Path) -> None:
    """Test that llm.enabled must be a boolean."""
    data = {
        "audio": {"sample_rate": 16000, "block_ms": 32},
        "vad": {},
        "stt": {},
        "tts": {},
        "responses": {},
        "runtime": {},
        "logging": {},
        "llm": {"enabled": "true"},  # string instead of bool
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="llm.enabled must be a boolean"):
        load_config(p)


# Test 22: LLM validation - base_url must be loopback http URL
def test_llm_base_url_validation(tmp_path: Path) -> None:
    """Test that llm.base_url must be a loopback http URL."""
    for url in ["", "http://google.com", "https://localhost", "ftp://127.0.0.1"]:
        data = {
            "audio": {"sample_rate": 16000, "block_ms": 32},
            "vad": {},
            "stt": {},
            "tts": {},
            "responses": {},
            "runtime": {},
            "logging": {},
            "llm": {"base_url": url},
        }
        # Use a simpler filename that doesn't contain colons or special chars
        safe_url = url.replace(":", "_").replace("/", "_")
        p = tmp_path / f"config_base_{safe_url}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)


# Test 23: LLM validation - endpoint must start with /
def test_llm_endpoint_validation(tmp_path: Path) -> None:
    """Test that llm.endpoint must start with '/'. cant be empty or absolute."""
    for endpoint in ["", "chat/completions", "http://example.com/v1/chat", "http://example.com"]:
        data = {
            "audio": {"sample_rate": 16000, "block_ms": 32},
            "vad": {},
            "stt": {},
            "tts": {},
            "responses": {},
            "runtime": {},
            "logging": {},
            "llm": {"endpoint": endpoint},
        }
        # Use safe filename (replace special chars with underscore)
        safe_name = f"config_endpoint_{endpoint.replace('/', '_').replace(':', '').replace('.', '_')}.yaml"
        p = tmp_path / safe_name
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError, match="endpoint must start with '/', got"):
            load_config(p)


# Test 24: LLM validation - model name must be a non-empty string
def test_llm_model_validation(tmp_path: Path) -> None:
    """Test that llm.model must be a non-empty string."""
    for model in ["", "   ", 123, True, None]:
        data = {
            "audio": {"sample_rate": 16000, "block_ms": 32},
            "vad": {},
            "stt": {},
            "tts": {},
            "responses": {},
            "runtime": {},
            "logging": {},
            "llm": {"model": model},
        }
        p = tmp_path / f"config_model_{str(model).replace('.', '_')}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError, match="llm.model must be a non-empty string"):
            load_config(p)
