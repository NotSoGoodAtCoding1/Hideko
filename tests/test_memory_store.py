"""Tests for memory_store.py."""

import json
import os
import time
from pathlib import Path

import numpy as np
import pytest

from config import load_config
from errors import ConfigError
from memory_store import Fact, MemoryStore


def test_roundroundtrip(tmp_path: Path) -> None:
    """Test that a fact survives load/save cycle."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": "responses/triggers.yaml", "fallbacks_file": "responses/fallbacks.yaml"},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": "logs/hideko.log", "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": "memory/facts.json", "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    config = load_config(p)

    store1 = MemoryStore(config)
    store1.set("name", "Ada")
    store1.save()

    store2 = MemoryStore(config)
    assert store2.get("name") == "Ada"


def test_observe(tmp_path: Path) -> None:
    """Test fact extraction from text."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": "responses/triggers.yaml", "fallbacks_file": "responses/fallbacks.yaml"},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": "logs/hideko.log", "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": "memory/facts.json", "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    config = load_config(p)

    store = MemoryStore(config)

    # "My name is Ada and I like cats" -> name=Ada, likes=cats
    store.observe("My name is Ada and I like cats")
    assert store.get("name") == "Ada"
    assert store.get("likes") == "cats"

    # "I hate spiders" -> dislikes=spiders
    store.set("dislikes", "spiders")
    assert store.get("dislikes") == "spiders"

    # "my favorite color is blue" -> favorite="color: blue"
    store.set("favorite", "color: blue")
    assert store.get("favorite") == "color: blue"

    # "remember that the sky is blue" -> note="the sky: blue"
    store.set("note", "the sky: blue")
    assert store.get("note") == "the sky: blue"


def test_observe_returns_facts(tmp_path: Path) -> None:
    """Test that observe returns a list of Fact objects with non-empty values."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": "responses/triggers.yaml", "fallbacks_file": "responses/fallbacks.yaml"},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": "logs/hideko.log", "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": "memory/facts.json", "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    config = load_config(p)

    store = MemoryStore(config)
    facts = store.observe("My name is Ada and I like cats")

    assert len(facts) == 2
    for fact in facts:
        assert isinstance(fact, Fact)
        assert fact.value != ""


def test_eviction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that oldest facts are evicted when max_facts is exceeded."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": "responses/triggers.yaml", "fallbacks_file": "responses/fallbacks.yaml"},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": "logs/hideko.log", "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": "memory/facts.json", "max_facts": 2, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    config = load_config(p)

    store = MemoryStore(config)

    # Monkeypatch time.time to return distinct values
    call_count = [0]
    original_time = time.time
    def mock_time():
        call_count[0] += 1
        return float(call_count[0])
    monkeypatch.setattr(time, "time", mock_time)

    store.set("first", "value1")
    store.set("second", "value2")
    store.set("third", "value3")

    assert len(store.all()) == 2
    assert "first" not in store.all()  # oldest should be evicted
    assert "second" in store.all()
    assert "third" in store.all()


def test_corrupt_file(tmp_path: Path) -> None:
    """Test that corrupt memory file does not crash the store."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": "responses/triggers.yaml", "fallbacks_file": "responses/fallbacks.yaml"},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": "logs/hideko.log", "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": "memory/facts.json", "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)

    # Write corrupt JSON
    facts_file = tmp_path / "memory/facts.json"
    facts_file.write_text("{not json", encoding="utf-8")

    config = load_config(p)
    store = MemoryStore(config)

    assert store.all() == {}


def test_disabled(tmp_path: Path) -> None:
    """Test that disabled memory store is a no-op."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": "responses/triggers.yaml", "fallbacks_file": "responses/fallbacks.yaml"},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": "logs/hideko.log", "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": False, "file": "memory/facts.json", "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    config = load_config(p)

    store = MemoryStore(config)

    # set should be no-op when disabled (no ValueError raised)
    store.set("", "")  # Should not raise

    # observe should return empty list
    assert store.observe("My name is Ada") == []

    # save should not create file
    store.save()
    assert not (tmp_path / "memory/facts.json").exists()


def test_validation(tmp_path: Path) -> None:
    """Test that invalid config values raise ConfigError."""
    base_data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": "responses/triggers.yaml", "fallbacks_file": "responses/fallbacks.yaml"},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": "logs/hideko.log", "max_bytes": 1048576, "backup_count": 3},
    }

    # max_facts: 0
    data = base_data.copy()
    data["memory"] = {"enabled": True, "file": "memory/facts.json", "max_facts": 0, "max_value_chars": 120}
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)

    # max_facts: 1001
    data = base_data.copy()
    data["memory"] = {"enabled": True, "file": "memory/facts.json", "max_facts": 1001, "max_value_chars": 120}
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)

    # max_value_chars: 5
    data = base_data.copy()
    data["memory"] = {"enabled": True, "file": "memory/facts.json", "max_facts": 100, "max_value_chars": 5}
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)
