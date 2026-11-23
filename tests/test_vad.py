"""Tests for VAD and UtteranceRecorder."""

import dataclasses
from typing import Any, Generator

import numpy as np
import pytest

from config import AppConfig, load_config
from vad import UtteranceRecorder, VAD


def feed(rec: UtteranceRecorder, blocks: list[np.ndarray]) -> list[np.ndarray]:
    """Yield every non-None utterance produced by the sequence of blocks."""
    out: list[np.ndarray] = []
    for b in blocks:
        u = rec.process_block(b)
        if u is not None:
            out.append(u)
    return out


def seconds_of_silence(n_blocks: int, n: int = 512) -> list[np.ndarray]:
    """Generate n_blocks of silence."""
    return [np.zeros(n, dtype=np.float32) for _ in range(n_blocks)]


def seconds_of_speech(
    n_blocks: int, rng: np.random.Generator, n: int = 512, amp: float = 0.1
) -> list[np.ndarray]:
    """Generate n_blocks of speech-like noise."""
    return [(amp * rng.standard_normal(n)).astype(np.float32) for _ in range(n_blocks)]


# Test 1: level_db(zeros) < -100
def test_level_db_zeros(vad: VAD) -> None:
    """Test that silence produces very low dBFS."""
    frame = np.zeros(512, dtype=np.float32)
    assert vad.level_db(frame) < -100.0


# Test 2: level_db(ones) ≈ 0.0 (within 0.1)
def test_level_db_ones(vad: VAD) -> None:
    """Test that full-scale signal produces ~0 dBFS."""
    frame = np.ones(512, dtype=np.float32)
    level = vad.level_db(frame)
    assert abs(level - 0.0) < 0.1


# Test 3: is_speech True above threshold, False below
def test_is_speech_threshold(config: AppConfig, tmp_path: Any) -> None:
    """Test that is_speech correctly detects speech vs silence."""
    vad = VAD(sample_rate=16000, frame_ms=32, threshold_db=-40.0)
    
    # Loud frame (above threshold) - RMS of 0.5 is about -6 dBFS, well above -40 dBFS
    loud_frame = np.full(512, 0.5, dtype=np.float32)
    assert vad.is_speech(loud_frame)
    
    # Silent frame (below threshold)
    silent_frame = np.zeros(512, dtype=np.float32)
    assert not vad.is_speech(silent_frame)


# Test 4: 1 s silence → no utterance
def test_one_second_silence_no_utterance(config: AppConfig, tmp_path: Any) -> None:
    """Test that 1 second of silence produces no utterance."""
    rec = UtteranceRecorder(config)
    
    # 1 second = ~31 blocks at 16kHz/32ms
    n_blocks = 31
    blocks = seconds_of_silence(n_blocks)
    utterances = feed(rec, blocks)
    
    assert len(utterances) == 0


# Test 5: 1 s speech + 1 s silence → exactly one utterance
def test_one_second_speech_one_utterance(config: AppConfig, tmp_path: Any) -> None:
    """Test that 1 second of speech produces exactly one utterance."""
    rng = np.random.default_rng(0)
    rec = UtteranceRecorder(config)
    
    # 1 second of speech (~31 blocks) + 1 second of silence to trigger emission
    n_speech_blocks = 31
    n_silence_blocks = 31
    blocks = seconds_of_speech(n_speech_blocks, rng)
    blocks.extend(seconds_of_silence(n_silence_blocks))
    
    utterances = feed(rec, blocks)
    
    assert len(utterances) == 1


# Test 6: Utterance duration ≈ 1 s ± 0.15 s (trailing silence trimmed)
def test_utterance_duration(config: AppConfig, tmp_path: Any) -> None:
    """Test that utterance duration is approximately the speech duration."""
    rng = np.random.default_rng(0)
    rec = UtteranceRecorder(config)
    
    # 1 second of speech (~31 blocks) + silence to trigger emission
    n_speech_blocks = 31
    n_silence_blocks = 31
    blocks = seconds_of_speech(n_speech_blocks, rng)
    blocks.extend(seconds_of_silence(n_silence_blocks))
    
    utterances = feed(rec, blocks)
    
    assert len(utterances) == 1
    duration_s = len(utterances[0]) / config.audio.sample_rate
    # Allow some variance due to pre-roll and trailing silence trimming
    assert abs(duration_s - 1.0) <= 0.15


# Test 7: A 50 ms tap (≈2 speech blocks) → no utterance (min_speech_ms=250)
def test_short_tap_no_utterance(config: AppConfig, tmp_path: Any) -> None:
    """Test that a short burst (< min_speech_ms) produces no utterance."""
    rng = np.random.default_rng(0)
    rec = UtteranceRecorder(config)
    
    # 50 ms = ~2 blocks at 32ms/block
    n_blocks = 2
    blocks = seconds_of_speech(n_blocks, rng, amp=0.5)  # Higher amplitude to pass threshold
    utterances = feed(rec, blocks)
    
    assert len(utterances) == 0


# Test 8: Speech longer than max_utterance_s → emitted and capped
def test_max_utterance_cap(config: AppConfig, tmp_path: Any) -> None:
    """Test that speech longer than max_utterance_s is capped."""
    rng = np.random.default_rng(0)
    
    # Create a config with small max_utterance_s
    short_vad = dataclasses.replace(config.vad, max_utterance_s=0.5)
    rec = UtteranceRecorder(dataclasses.replace(config, vad=short_vad))
    
    # Feed ~1.5 s of speech (~47 blocks at 32ms/block) + trailing silence to trigger emission
    n_blocks = 47
    n_trailing = 25
    blocks = seconds_of_speech(n_blocks, rng, amp=0.5)
    blocks.extend(seconds_of_silence(n_trailing))
    
    utterances = feed(rec, blocks)
    
    # With max_utterance_s=0.5s and ~1.5s of speech, we should get multiple capped utterances
    # Each ~0.5s chunk gets emitted when trailing silence is detected
    assert len(utterances) >= 1
    duration_s = len(utterances[0]) / config.audio.sample_rate
    # First utterance should be capped at ~0.5 s (± 0.1 for variance)
    assert abs(duration_s - 0.5) <= 0.1


# Test 9: Pre-roll: with 300 ms of silence before speech, first 100 ms is not all zeros
def test_pre_roll_no_clipping(config: AppConfig, tmp_path: Any) -> None:
    """Test that pre-roll doesn't clip the onset of speech."""
    rng = np.random.default_rng(0)
    rec = UtteranceRecorder(config)
    
    # 300 ms silence (~10 blocks) + 1 s speech (~31 blocks) + trailing silence to trigger emission
    n_silence_blocks = 10
    n_speech_blocks = 31
    n_trailing_silence = 25  # Need ~700ms of silence to trigger emission
    
    all_blocks = seconds_of_silence(n_silence_blocks)
    all_blocks.extend(seconds_of_speech(n_speech_blocks, rng))
    all_blocks.extend(seconds_of_silence(n_trailing_silence))
    
    utterances = feed(rec, all_blocks)
    
    assert len(utterances) == 1
    utterance = utterances[0]
    
    # First 100 ms = ~2 blocks at 32ms/block
    first_100ms_samples = int(100 * config.audio.sample_rate / 1000.0)
    first_block = utterance[:min(first_100ms_samples, len(utterance))]
    
    # Check that it's not all zeros (speech onset should be present)
    assert not np.allclose(first_block, 0.0)


# Test 10: reset() during speech → next block doesn't emit old buffer
def test_reset_during_speech(config: AppConfig, tmp_path: Any) -> None:
    """Test that reset() clears state and prevents old utterance emission."""
    rng = np.random.default_rng(0)
    rec = UtteranceRecorder(config)
    
    # Start speech (need min_speech_ms worth, round up to ensure we reach threshold)
    n_min_blocks = int((config.vad.min_speech_ms + config.audio.block_ms - 1) / config.audio.block_ms)
    blocks = seconds_of_speech(n_min_blocks, rng, amp=0.5)
    
    # Process all min_speech_ms worth to enter speech state (but not enough for emission without trailing silence)
    for b in blocks:
        rec.process_block(b)
    
    assert rec.state == "speech"
    
    # Reset
    rec.reset()
    assert rec.state == "idle"
    
    # Continue with more speech + trailing silence - should not emit the old buffer
    n_trailing = 25
    blocks.extend(seconds_of_silence(n_trailing))
    utterances = feed(rec, blocks)
    
    # Should still get one utterance from the fresh phrase
    assert len(utterances) == 1
