"""Tests for memory wiring in main.py and response_handler.py."""

from pathlib import Path

import pytest

from cli import CliOptions, parse_args
from config import load_config
from memory_store import MemoryStore
from response_handler import ResponseHandler


def test_greeting_uses_name(tmp_path: Path) -> None:
    """Test that greetings use the stored name from memory."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": str(Path(__file__).parent.parent / "responses" / "triggers.yaml"), "fallbacks_file": str(Path(__file__).parent.parent / "responses" / "fallbacks.yaml")},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": str(tmp_path / "logs" / "hideko.log"), "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": str(tmp_path / "memory" / "facts.json"), "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    config = load_config(p)

    # Create a fake memory store that returns "Ada" for name
    class FakeMemoryStore:
        def __init__(self):
            self._facts = {"name": "Ada"}
        def get(self, key: str):
            return self._facts.get(key)
        def all(self):
            return self._facts

    fake_memory = FakeMemoryStore()

    handler = ResponseHandler(config, memory=fake_memory)

    # First greeting should use the name
    response1 = handler.respond("hello")
    assert response1.text == "Hello Ada. I am Hideko."

    # Second greeting should start with "Hello again, Ada."
    response2 = handler.respond("hello again")
    assert response2.text.startswith("Hello again, Ada.")


def test_greeting_without_memory_unchanged(tmp_path: Path) -> None:
    """Test that greetings without memory use original trigger responses."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": str(Path(__file__).parent.parent / "responses" / "triggers.yaml"), "fallbacks_file": str(Path(__file__).parent.parent / "responses" / "fallbacks.yaml")},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": str(tmp_path / "logs" / "hideko.log"), "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": str(tmp_path / "memory" / "facts.json"), "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    config = load_config(p)

    # No memory store passed
    handler = ResponseHandler(config)

    response = handler.respond("hello")
    # Should return one of the trigger responses (not a name-aware greeting)
    assert response.text in handler._triggers[0].responses


def test_cli_flags_parse() -> None:
    """Test that --facts and --forget flags are parsed correctly."""
    opts = parse_args(["--facts"])
    assert opts.facts is True
    assert opts.forget is False

    opts = parse_args(["--forget"])
    assert opts.facts is False
    assert opts.forget is True


def test_text_branch_observes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that --text branch calls observe and save on the memory store."""
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
    p = Path(__import__("pathlib").Path(__file__).parent / "conftest.py")
    # Use a temp path for the test
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = __import__("pathlib").Path(tmpdir)
        data_p = tmp_path / "config.yaml"
        data_p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
        (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
        config = load_config(data_p)

        # Track observe and save calls
        observed_texts: list[str] = []
        save_count = [0]

        original_memory = MemoryStore
        class FakeMemoryStore(original_memory):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
            def observe(self, text: str):
                observed_texts.append(text)
                return super().observe(text)
            def save(self):
                save_count[0] += 1
                return super().save()

        monkeypatch.setattr(__import__("main"), "MemoryStore", FakeMemoryStore)

        from main import main
        exit_code = main(["--text", "my name is Ada", "--no-tts"])

        assert exit_code == 0
        assert observed_texts == ["my name is Ada"]
        assert save_count[0] == 1


def test_facts_and_forget_commands(tmp_path: Path) -> None:
    """Test that --facts and --forget commands work correctly."""
    data = {
        "audio": {"input_device": None, "output_device": None, "sample_rate": 16000, "channels": 1, "block_ms": 32, "playback_volume": 1.0},
        "vad": {"energy_threshold_db": -40.0, "calibrate": False, "calibration_ms": 1000, "silence_ms": 450, "min_speech_ms": 200, "max_utterance_s": 15, "pre_roll_ms": 300, "post_playback_flush_ms": 150},
        "stt": {"model_size": "tiny.en", "device": "cpu", "compute_type": "int8", "language": "en", "beam_size": 1, "cpu_threads": None, "download_root": "models/whisper", "min_avg_logprob": -1.0, "max_audio_s": 30},
        "tts": {"backend": "exe", "piper_exe": "models/piper/piper/piper.exe", "voice_model": "models/piper/en_US-amy-medium.onnx", "length_scale": 1.0, "max_chars": 300, "timeout_s": 30},
        "responses": {"triggers_file": str(Path(__file__).parent.parent / "responses" / "triggers.yaml"), "fallbacks_file": str(Path(__file__).parent.parent / "responses" / "fallbacks.yaml")},
        "runtime": {"half_duplex": True, "max_turns": 0, "log_transcripts": True, "greet_on_start": True, "echo_mode": False},
        "logging": {"level": "INFO", "file": str(tmp_path / "logs" / "hideko.log"), "max_bytes": 1048576, "backup_count": 3},
        "memory": {"enabled": True, "file": str(tmp_path / "memory" / "facts.json"), "max_facts": 100, "max_value_chars": 120},
    }
    p = tmp_path / "config.yaml"
    p.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)

    # --facts should print "(no facts)" and return 0
    from io import StringIO
    from contextlib import redirect_stdout

    stdout_capture = StringIO()
    with redirect_stdout(stdout_capture):
        from main import main
        exit_code = main(["--config", str(p), "--facts"])

    assert exit_code == 0
    output = stdout_capture.getvalue().strip()
    assert output == "(no facts)"

    # --forget should print "memory cleared" and return 0
    stdout_capture = StringIO()
    with redirect_stdout(stdout_capture):
        exit_code = main(["--config", str(p), "--forget"])

    assert exit_code == 0
    output = stdout_capture.getvalue().strip()
    assert output == "memory cleared"
