import numpy as np
import pytest
import yaml

from config import load_config


@pytest.fixture
def config(tmp_path):
    """A complete, valid AppConfig rooted in tmp_path."""
    data = {
        "audio": {
            "input_device": None, "output_device": None,
            "sample_rate": 16000, "channels": 1, "block_ms": 32,
            "playback_volume": 1.0,
        },
        "vad": {
            "energy_threshold_db": -40.0, "calibrate": False,
            "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200,
            "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150,
        },
        "stt": {
            "model_size": "tiny.en", "device": "cpu", "compute_type": "int8",
            "language": "en", "beam_size": 1, "download_root": "models/whisper",
            "min_avg_logprob": -1.0, "max_audio_s": 30,
        },
        "tts": {
            "backend": "exe", "piper_exe": "models/piper/piper/piper.exe",
            "voice_model": "models/piper/en_US-amy-medium.onnx",
            "length_scale": 1.0, "max_chars": 300, "timeout_s": 30,
        },
        "responses": {
            "triggers_file": "responses/triggers.yaml",
            "fallbacks_file": "responses/fallbacks.yaml",
        },
        "runtime": {
            "half_duplex": True, "max_turns": 0, "log_transcripts": True,
            "greet_on_start": True, "echo_mode": False,
        },
        "logging": {
            "level": "INFO", "file": "logs/hideko.log",
            "max_bytes": 1048576, "backup_count": 3,
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    (tmp_path / "responses").mkdir(exist_ok=True)
    return load_config(p)


@pytest.fixture
def silent_block():
    return lambda n=512: np.zeros(n, dtype=np.float32)


@pytest.fixture
def speech_block():
    rng = np.random.default_rng(0)
    return lambda n=512: (0.2 * rng.standard_normal(n)).astype(np.float32)


@pytest.fixture
def fake_devices(monkeypatch):
    devices = [
        {"name": "Speakers (Realtek)", "max_input_channels": 0,
         "max_output_channels": 2, "default_samplerate": 48000.0},
        {"name": "Microphone (USB)", "max_input_channels": 2,
         "max_output_channels": 0, "default_samplerate": 44100.0},
        {"name": "Headset Mic", "max_input_channels": 1,
         "max_output_channels": 1, "default_samplerate": 16000.0},
    ]
    import sounddevice as sd
    monkeypatch.setattr(sd, "query_devices", lambda *a, **k: devices)
    monkeypatch.setattr(sd, "default", type("D", (), {"device": (1, 0)})(), raising=False)
    return devices


@pytest.fixture
def vad():
    from vad import VAD
    return VAD(sample_rate=16000, frame_ms=32, threshold_db=-40.0)
