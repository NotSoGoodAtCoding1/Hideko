"""Offline unit tests for tts_engine.py: no Piper process, audio device, or model."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
import pytest
import soundfile as sf

import tts_engine
from config import AppConfig
from errors import TTSError
from tts_engine import TTSEngine

FrameReader = Callable[[], tuple[np.ndarray, int]]


@dataclass
class FakePiper:
    """Mutable stand-in for subprocess.run + sf.read used by TTSEngine."""

    calls: list[tuple[list[str], dict[str, Any]]] = field(default_factory=list)
    returncode: int = 0
    stderr: bytes = b""
    reader: FrameReader | None = None

    def run(self, cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        """Record the call and write a real (silent) WAV under tmp_path."""
        self.calls.append((list(cmd), dict(kwargs)))
        if self.returncode == 0:
            out = Path(cmd[cmd.index("--output_file") + 1])
            sf.write(out, np.zeros(22050, dtype=np.float32), 22050)
        return SimpleNamespace(returncode=self.returncode, stderr=self.stderr)

    def read(self, *args: Any, **kwargs: Any) -> tuple[np.ndarray, int]:
        """Return deterministic frames, or a test-provided override."""
        if self.reader is not None:
            return self.reader()
        return np.zeros(22050, dtype=np.float32), 22050


def _tts_config(
    config: AppConfig,
    tmp_path: Path,
    *,
    max_chars: int = 300,
    missing_exe: bool = False,
) -> AppConfig:
    """Build a config whose TTS paths live under tmp_path and exist on disk."""
    piper_exe = tmp_path / "missing_piper.exe" if missing_exe else tmp_path / "piper.exe"
    voice_model = tmp_path / "voice.onnx"
    if not missing_exe:
        piper_exe.touch()
    voice_model.touch()
    (tmp_path / "voice.onnx.json").touch()
    return replace(
        config,
        tts=replace(
            config.tts,
            piper_exe=piper_exe,
            voice_model=voice_model,
            max_chars=max_chars,
        ),
    )


@pytest.fixture
def piper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakePiper:
    """Patch every external dependency TTSEngine touches."""
    fake = FakePiper()
    monkeypatch.setattr(tts_engine, "subprocess", SimpleNamespace(run=fake.run))
    monkeypatch.setattr(tts_engine, "sf", SimpleNamespace(read=fake.read, write=sf.write))
    monkeypatch.setattr(tts_engine.tempfile, "gettempdir", lambda: str(tmp_path))
    return fake


def test_missing_exe_reports_download_hint(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """Missing exe -> is_available() False and a TTSError with the download hint."""
    engine = TTSEngine(_tts_config(config, tmp_path, missing_exe=True))

    assert engine.is_available() is False
    with pytest.raises(TTSError) as exc_info:
        engine.synthesize("Hello")
    assert "download_models.py" in str(exc_info.value)
    assert piper.calls == []


def test_empty_or_whitespace_text_raises(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """Empty and whitespace-only text are both rejected before Piper runs."""
    engine = TTSEngine(_tts_config(config, tmp_path))

    with pytest.raises(TTSError, match="empty"):
        engine.synthesize("")
    with pytest.raises(TTSError, match="empty"):
        engine.synthesize("  \n\t  ")
    assert piper.calls == []


def test_long_text_is_truncated_on_word_boundary(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """With max_chars=20 the subprocess receives <= 20 chars, ending at a word."""
    engine = TTSEngine(_tts_config(config, tmp_path, max_chars=20))

    engine.synthesize("Hello world this is a very long sentence")

    assert len(piper.calls) == 1
    decoded = piper.calls[0][1]["input"].decode("utf-8")
    assert len(decoded) <= 20
    assert decoded.strip() == "Hello world this is"


def test_identical_calls_are_cached(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """Two identical synthesize calls invoke subprocess.run only once."""
    engine = TTSEngine(_tts_config(config, tmp_path))

    first = engine.synthesize("Hello world")
    second = engine.synthesize("Hello world")

    assert len(piper.calls) == 1
    assert second is first


def test_nonzero_return_code_includes_stderr_tail(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """A failing Piper exit code surfaces the stderr tail in TTSError."""
    piper.returncode = 3
    piper.stderr = b"boom: missing voice\nlast line"
    engine = TTSEngine(_tts_config(config, tmp_path))

    with pytest.raises(TTSError) as exc_info:
        engine.synthesize("Hello")

    assert "exit code 3" in str(exc_info.value)
    assert "boom: missing voice" in str(exc_info.value)
    assert "last line" in str(exc_info.value)


def test_zero_frames_is_reported_as_empty_audio(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """Exit 0 with no frames still raises the explicit empty-audio error."""

    def empty_frames() -> tuple[np.ndarray, int]:
        return np.zeros(0, dtype=np.float32), 22050

    piper.reader = empty_frames
    engine = TTSEngine(_tts_config(config, tmp_path))

    with pytest.raises(TTSError, match="empty audio"):
        engine.synthesize("Hello")


def test_stereo_output_is_downmixed_to_mono(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """A (n, 2) WAV is averaged into a 1-D samples array."""

    def stereo_frames() -> tuple[np.ndarray, int]:
        left = np.ones(22050, dtype=np.float32)
        right = np.zeros(22050, dtype=np.float32)
        return np.column_stack((left, right)), 22050

    piper.reader = stereo_frames
    engine = TTSEngine(_tts_config(config, tmp_path))

    clip = engine.synthesize("Hello")

    assert clip.samples.ndim == 1
    assert clip.samples.shape == (22050,)
    np.testing.assert_allclose(clip.samples, 0.5)


def test_clip_rate_and_duration_match_frames(
    config: AppConfig, tmp_path: Path, piper: FakePiper
) -> None:
    """AudioClip carries the WAV sample rate and duration = frames / rate."""
    engine = TTSEngine(_tts_config(config, tmp_path))

    clip = engine.synthesize("Hello")

    assert clip.sample_rate == 22050
    assert clip.duration_s == pytest.approx(22050 / 22050)
    assert clip.samples.dtype == np.float32
