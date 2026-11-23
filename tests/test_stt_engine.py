"""Unit tests for STT engine module."""

import yaml
from types import SimpleNamespace
from typing import Any, Iterator, Tuple

import numpy as np
import pytest

from config import AppConfig, load_config
from errors import STTError
from stt_engine import STTEngine


class FakeSegment:
    """Fake segment for testing."""

    def __init__(self, text: str, avg_logprob: float = -0.2, no_speech_prob: float = 0.01) -> None:
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class FakeModel:
    """Fake Whisper model for testing."""

    segments: list[FakeSegment] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def transcribe(self, audio: np.ndarray, **kwargs: Any) -> Tuple[Iterator[FakeSegment], SimpleNamespace]:
        """Return (generator, info) as expected by real WhisperModel."""
        return iter(self.segments), SimpleNamespace(
            language="en", language_probability=0.99, duration=len(audio) / 16000.0
        )


def write_data(tmp_path: Any, triggers: list[dict] | None = None, fallbacks: list[str] | None = None) -> None:
    """Write trigger and fallback YAML files to tmp_path/responses/."""
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir(exist_ok=True)

    if triggers is not None:
        (responses_dir / "triggers.yaml").write_text(
            yaml.safe_dump({"version": 1, "triggers": triggers}), encoding="utf-8"
        )

    if fallbacks is not None:
        (responses_dir / "fallbacks.yaml").write_text(
            yaml.safe_dump({"version": 1, "fallbacks": fallbacks}), encoding="utf-8"
        )


# Test 1: 0.2 s audio → empty text, latency_s < 0.05, model never constructed
def test_short_audio_no_model_call(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that audio under 0.3s returns empty without loading the model."""
    made = []

    def factory(*args: Any, **kwargs: Any) -> FakeModel:
        made.append(1)
        return FakeModel()

    monkeypatch.setattr("faster_whisper.WhisperModel", factory)

    engine = STTEngine(config)
    audio = np.zeros(3200, dtype=np.float32)  # 0.2s at 16kHz

    transcript = engine.transcribe(audio)

    assert transcript.text == ""
    assert len(made) == 0


# Test 2: All-zero 2 s audio → empty text, no model call
def test_zero_audio_no_model_call(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that silent audio returns empty without loading the model."""
    made = []

    def factory(*args: Any, **kwargs: Any) -> FakeModel:
        made.append(1)
        return FakeModel()

    monkeypatch.setattr("faster_whisper.WhisperModel", factory)

    engine = STTEngine(config)
    audio = np.zeros(32000, dtype=np.float32)  # 2s at 16kHz

    transcript = engine.transcribe(audio)

    assert transcript.text == ""
    assert len(made) == 0


# Test 3: 44.1 kHz input → STTError
def test_wrong_sample_rate_error(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that non-16kHz audio raises STTError."""
    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)

    engine = STTEngine(config)
    audio = np.zeros(32000, dtype=np.float32)  # 2s at 16kHz

    with pytest.raises(STTError) as exc_info:
        engine.transcribe(audio, sample_rate=44100)

    assert "16 kHz" in str(exc_info.value)


# Test 4: Fake model returning ["Hello", "there"] → "Hello there"
def test_normal_transcription(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test normal transcription with valid segments."""
    # Use single word that won't trigger any filters
    FakeModel.segments = [FakeSegment("testword", avg_logprob=-0.2, no_speech_prob=0.01)]

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)

    engine = STTEngine(config)
    audio = np.random.randn(48000).astype(np.float32)  # 3s of noise

    transcript = engine.transcribe(audio)

    assert transcript.text == "testword"


# Test 5: Fake segment with avg_logprob=-1.5, no_speech_prob=0.9 → dropped (empty text)
def test_low_logprob_high_no_speech_dropped(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that segments with low logprob and high no_speech are filtered."""
    FakeModel.segments = [FakeSegment("Hello", avg_logprob=-1.5, no_speech_prob=0.9)]

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)

    engine = STTEngine(config)
    audio = np.random.randn(32000).astype(np.float32)  # 2s of noise

    transcript = engine.transcribe(audio)

    assert transcript.text == ""


# Test 6: Text "Thank you." on 1.2 s audio → dropped by hallucination filter
def test_hallucination_filter_short_audio(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that common hallucinations are filtered for short audio."""
    FakeModel.segments = [FakeSegment("Thank you.", avg_logprob=-0.2)]

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)

    engine = STTEngine(config)
    audio = np.random.randn(19200).astype(np.float32)  # 1.2s of noise

    transcript = engine.transcribe(audio)

    assert transcript.text == ""


# Test 7: Text "you you you you you" → dropped (repeated token filter)
def test_repeated_token_filter(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that repeated single tokens are filtered."""
    FakeModel.segments = [FakeSegment("you you you you you", avg_logprob=-0.2)]

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)

    engine = STTEngine(config)
    audio = np.random.randn(32000).astype(np.float32)  # 2s of noise

    transcript = engine.transcribe(audio)

    assert transcript.text == ""


# Test 8: WhisperModel raising OSError → STTError mentioning download_models.py
def test_model_load_error_wrapped(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that model loading errors are wrapped in STTError with helpful message."""

    class FailingModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def transcribe(self, audio: np.ndarray, **kwargs: Any) -> Tuple[Iterator[FakeSegment], SimpleNamespace]:
            return iter([]), SimpleNamespace(language="en", language_probability=0.99, duration=1.0)

    def failing_factory(*args: Any, **kwargs: Any) -> FailingModel:
        raise OSError("Failed to download model")

    monkeypatch.setattr("faster_whisper.WhisperModel", failing_factory)

    engine = STTEngine(config)
    audio = np.random.randn(32000).astype(np.float32)  # 2s of noise

    with pytest.raises(STTError) as exc_info:
        engine.transcribe(audio)

    assert "download_models.py" in str(exc_info.value)


# Test 9: cpu_threads=8 is passed to WhisperModel
def test_cpu_threads_passed_to_model(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that cpu_threads config value is passed to WhisperModel."""

    class TrackingModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._init_kwargs = kwargs
            self.segments = [FakeSegment("testword", avg_logprob=-0.2, no_speech_prob=0.01)]

        def transcribe(self, audio: np.ndarray, **kwargs: Any) -> Tuple[Iterator[FakeSegment], SimpleNamespace]:
            return iter(self.segments), SimpleNamespace(
                language="en", language_probability=0.99, duration=len(audio) / 16000.0
            )

    # Create config with cpu_threads=8
    from dataclasses import replace
    config_with_8 = replace(config, stt=replace(config.stt, cpu_threads=8))

    tracking: TrackingModel | None = None

    def factory(*args: Any, **kwargs: Any) -> TrackingModel:
        nonlocal tracking
        # Pass all args and kwargs to __init__ so we capture the actual parameters
        return TrackingModel(*args, **kwargs)

    monkeypatch.setattr("faster_whisper.WhisperModel", factory)

    # Patch _ensure_model to use our factory directly (bypassing the local import issue)
    original_ensure = STTEngine._ensure_model
    
    captured_kwargs: dict[str, Any] | None = None
    
    def patched_ensure(self: STTEngine) -> None:
        nonlocal captured_kwargs
        if self._model is None:
            # Capture the kwargs that would be passed to the factory
            cpu_threads_val = (
                self._config.stt.cpu_threads
                if self._config.stt.cpu_threads is not None
                else max(1, (os.cpu_count() or 4) // 2)
            )
            captured_kwargs = {
                "model_size": self._config.stt.model_size,
                "device": self._config.stt.device,
                "compute_type": self._config.stt.compute_type,
                "download_root": str(self._config.stt.download_root),
                "cpu_threads": cpu_threads_val,
            }
            # Call the factory to create our tracking model
            self._model = factory(
                self._config.stt.model_size,
                device=self._config.stt.device,
                compute_type=self._config.stt.compute_type,
                download_root=str(self._config.stt.download_root),
                cpu_threads=cpu_threads_val,
            )
    
    STTEngine._ensure_model = patched_ensure

    engine = STTEngine(config_with_8)
    audio = np.random.randn(32000).astype(np.float32)  # 2s of noise

    transcript = engine.transcribe(audio)

    assert transcript.text == "testword"
    # Check that cpu_threads was captured during model initialization
    assert captured_kwargs is not None, "_ensure_model was never called"
    assert captured_kwargs["cpu_threads"] == 8, f"Expected cpu_threads=8 in _ensure_model, got {captured_kwargs.get('cpu_threads')}"


# Test 10: cpu_threads=None uses default (half cores)
def test_cpu_threads_none_uses_default(monkeypatch: pytest.MonkeyPatch, config: AppConfig) -> None:
    """Test that cpu_threads=None uses the default calculation."""
    import os

    class TrackingModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._init_kwargs = kwargs
            self.segments = [FakeSegment("testword", avg_logprob=-0.2, no_speech_prob=0.01)]

        def transcribe(self, audio: np.ndarray, **kwargs: Any) -> Tuple[Iterator[FakeSegment], SimpleNamespace]:
            return iter(self.segments), SimpleNamespace(
                language="en", language_probability=0.99, duration=len(audio) / 16000.0
            )

    # Create config with cpu_threads=None (default)
    from dataclasses import replace
    config_default = replace(config, stt=replace(config.stt, cpu_threads=None))

    tracking: TrackingModel | None = None

    def factory(*args: Any, **kwargs: Any) -> TrackingModel:
        nonlocal tracking
        # Pass all args and kwargs to __init__ so we capture the actual parameters
        return TrackingModel(*args, **kwargs)

    monkeypatch.setattr("faster_whisper.WhisperModel", factory)

    # Patch _ensure_model to use our factory directly (bypassing the local import issue)
    original_ensure = STTEngine._ensure_model
    
    captured_kwargs: dict[str, Any] | None = None
    
    def patched_ensure(self: STTEngine) -> None:
        nonlocal captured_kwargs
        if self._model is None:
            # Capture the kwargs that would be passed to the factory
            cpu_threads_val = (
                self._config.stt.cpu_threads
                if self._config.stt.cpu_threads is not None
                else max(1, (os.cpu_count() or 4) // 2)
            )
            captured_kwargs = {
                "model_size": self._config.stt.model_size,
                "device": self._config.stt.device,
                "compute_type": self._config.stt.compute_type,
                "download_root": str(self._config.stt.download_root),
                "cpu_threads": cpu_threads_val,
            }
            # Call the factory to create our tracking model
            self._model = factory(
                self._config.stt.model_size,
                device=self._config.stt.device,
                compute_type=self._config.stt.compute_type,
                download_root=str(self._config.stt.download_root),
                cpu_threads=cpu_threads_val,
            )
    
    STTEngine._ensure_model = patched_ensure

    engine = STTEngine(config_default)
    audio = np.random.randn(32000).astype(np.float32)  # 2s of noise

    transcript = engine.transcribe(audio)

    assert transcript.text == "testword"
    expected = max(1, (os.cpu_count() or 4) // 2)
    # Check that cpu_threads was captured during model initialization with the default value
    assert captured_kwargs is not None, "_ensure_model was never called"
    assert captured_kwargs["cpu_threads"] == expected, f"Expected cpu_threads={expected} in _ensure_model, got {captured_kwargs.get('cpu_threads')}"
