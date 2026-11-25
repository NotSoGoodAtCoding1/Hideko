from __future__ import annotations

import argparse
import logging
import sys
import wave
from collections import deque
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any

import numpy as np

from audio_manager import AudioError, Microphone
from config import AppConfig, load_config

logger = logging.getLogger(__name__)


class VAD:
    """Voice Activity Detector using energy thresholding."""

    def __init__(self, sample_rate: int, frame_ms: int, threshold_db: float) -> None:
        """Initialize VAD.

        Args:
            sample_rate: Audio sample rate in Hz (typically 16000).
            frame_ms: Frame duration in milliseconds.
            threshold_db: Energy threshold in dBFS for speech detection.
        """
        self._sample_rate = sample_rate
        self._frame_ms = frame_ms
        self._threshold_db = threshold_db

    @property
    def threshold_db(self) -> float:
        """Return the current energy threshold in dBFS."""
        return self._threshold_db

    @threshold_db.setter
    def threshold_db(self, value: float) -> None:
        """Set the energy threshold.

        Args:
            value: Threshold in dBFS. Must be between -70 and -20.
        """
        if value < -70.0 or value > -20.0:
            raise ValueError(f"threshold_db must be between -70.0 and -20.0, got {value}")
        self._threshold_db = value

    def level_db(self, frame: np.ndarray) -> float:
        """Compute RMS level in dBFS for a frame.

        Args:
            frame: Float array of audio samples.

        Returns:
            RMS level in dBFS (0 dBFS = full scale, silence ≈ -120 dBFS).
        """
        if len(frame) < 2:
            return -100.0  # Treat very short frames as silence
        
        # Compute RMS in float64 to avoid overflow with float32 squares
        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)) + 1e-12))
        level_db = 20.0 * np.log10(rms + 1e-12)
        return level_db

    def is_speech(self, frame: np.ndarray) -> bool:
        """Determine if a frame contains speech based on energy threshold.

        Args:
            frame: Float array of audio samples.

        Returns:
            True if the frame's energy exceeds the threshold (speech), False otherwise.
        """
        level_db = self.level_db(frame)
        return level_db >= self.threshold_db


class UtteranceRecorder:
    """Records utterances from a stream of audio blocks using VAD."""

    def __init__(self, config: AppConfig, vad: VAD | None = None) -> None:
        """Initialize the utterance recorder.

        Args:
            config: Application configuration.
            vad: Optional pre-configured VAD instance. If None, creates one with config.vad.energy_threshold_db.
        """
        self.config = config
        self._vad = vad if vad is not None else VAD(
            sample_rate=config.audio.sample_rate,
            frame_ms=config.audio.block_ms,
            threshold_db=config.vad.energy_threshold_db,
        )

        # State machine variables
        self._state: str = "idle"
        self._buffer: list[np.ndarray] = []
        self._buffered_samples = 0
        # Pre-roll buffer stores up to pre_roll_ms worth of blocks (maxlen = blocks needed)
        self._pre_roll_buffer: deque[np.ndarray] = deque(maxlen=int(config.vad.pre_roll_ms / config.audio.block_ms) + 1)
        
        # Counters and timing
        self._blocks_seen = 0
        self._utterances = 0
        self._last_utterance_s: float | None = None

        # State machine counters
        self._silence_run_ms = 0
        self._speech_blocks_count = 0
        self._max_buffer_samples = int(config.vad.max_utterance_s * config.audio.sample_rate)

    def calibrate(self, mic: Microphone) -> float:
        """Calibrate the VAD threshold from ambient noise.

        Reads calibration_ms worth of audio and computes a threshold based on
        the 95th percentile of energy levels.

        Args:
            mic: Open microphone for reading calibration samples.

        Returns:
            The calibrated threshold in dBFS.
        """
        if not self.config.vad.calibrate:
            raise RuntimeError("Calibration requested but config.vad.calibrate is False")

        block_ms = self.config.audio.block_ms
        num_blocks = max(1, self.config.vad.calibration_ms // block_ms)

        levels = []
        for _ in range(num_blocks):
            block = mic.read_block()
            if len(block) >= 2:
                level_db = self._vad.level_db(block)
                levels.append(level_db)

        if not levels:
            raise AudioError("No valid audio blocks captured during calibration")

        noise_p95 = float(np.percentile(levels, 95))
        threshold = max(noise_p95 + 8.0, -55.0)
        threshold = min(max(threshold, -70.0), -20.0)

        self._vad.threshold_db = threshold
        logger.info(f"VAD calibrated: noise p95 = {noise_p95:.1f} dBFS, threshold = {threshold:.1f} dBFS")

        return threshold

    def process_block(self, block: np.ndarray) -> np.ndarray | None:
        """Process a single audio block and potentially emit an utterance.

        Implements the state machine: idle → speech → trailing → (emit → idle).

        Args:
            block: Float32 mono audio block of config.audio.blocksize samples.

        Returns:
            Emited utterance as float32 mono array, or None if no utterance ended.
        """
        sample_rate = self.config.audio.sample_rate
        block_ms = self.config.audio.block_ms
        silence_ms = self.config.vad.silence_ms
        min_speech_ms = self.config.vad.min_speech_ms
        pre_roll_ms = self.config.vad.pre_roll_ms

        # Validate block length (warn once if different)
        expected_size = self.config.audio.blocksize
        if len(block) != expected_size:
            logger.warning(f"Block length {len(block)} != expected {expected_size}, processing anyway")

        self._blocks_seen += 1

        # Pre-roll handling: collect blocks before speech onset
        if self._state == "idle":
            # Add to pre-roll buffer (including current block)
            self._pre_roll_buffer.append(block)

            is_speech = self._vad.is_speech(block)

            if is_speech:
                # Count consecutive speech blocks
                self._speech_blocks_count += 1
                speech_ms = self._speech_blocks_count * block_ms

                # Check if we've reached minimum speech duration
                if speech_ms >= min_speech_ms:
                    # Transition to speech state
                    self._state = "speech"
                    # Buffer starts with pre-roll (includes onset, since pre_roll > min_speech)
                    self._buffer = list(self._pre_roll_buffer)
                    self._buffered_samples = sum(b.shape[0] for b in self._buffer)
                    self._silence_run_ms = 0
                    self._speech_blocks_count = 0

            # Reset speech counter if not speech (keep filling pre-roll)
            if not is_speech:
                self._speech_blocks_count = 0

        elif self._state == "speech":
            # Append every block to buffer
            self._buffer.append(block)
            self._buffered_samples += block.shape[0]

            is_speech = self._vad.is_speech(block)

            if is_speech:
                self._silence_run_ms = 0
            else:
                self._silence_run_ms += block_ms

            # Check for silence timeout (emit)
            if self._silence_run_ms >= silence_ms:
                utterance = self._emit(silence_ms)  # Pass silence_ms so we trim trailing
                return utterance

            # Check max utterance duration (truncate and emit)
            if self._buffered_samples >= self._max_buffer_samples:
                utterance = self._emit(0)  # Don't trim trailing silence
                return utterance

        elif self._state == "trailing":
            # Clear buffers and return to idle
            self._pre_roll_buffer.clear()
            self._buffer.clear()
            self._buffered_samples = 0
            self._state = "idle"
            self._silence_run_ms = 0

        return None

    def _emit(self, max_trailing_silence_ms: int) -> np.ndarray:
        """Emit the current utterance.

        Args:
            max_trailing_silence_ms: Maximum trailing silence to include (in ms).

        Returns:
            Concatenated utterance as float32 mono array.
        """
        # Concatenate buffer
        if not self._buffer:
            return np.array([], dtype=np.float32)

        utterance = np.concatenate(self._buffer).astype(np.float32)
        duration_s = len(utterance) / self.config.audio.sample_rate

        # Trim trailing silence to at most max_trailing_silence_ms
        # Find the point where significant signal ends and count consecutive silent blocks
        if max_trailing_silence_ms > 0 and duration_s > max_trailing_silence_ms / 1000.0:
            sample_rate = self.config.audio.sample_rate
            block_size = self.config.audio.blocksize
            block_ms = self.config.audio.block_ms
            max_blocks = int(max_trailing_silence_ms / block_ms) + 1
            
            # Count how many trailing blocks are below threshold
            silence_threshold = -50.0  # dBFS - anything below this is silence
            trailing_silent_blocks = 0
            
            for i in range(len(utterance), 0, -block_size):
                block = utterance[i-block_size:i]
                level_db = 20.0 * np.log10(np.sqrt(np.mean(np.square(block, dtype=np.float64)) + 1e-12) + 1e-12)
                
                if level_db < silence_threshold:
                    trailing_silent_blocks += 1
                else:
                    break
                
                if trailing_silent_blocks >= max_blocks:
                    break
            
            # Trim off the silent blocks
            if trailing_silent_blocks > 0:
                keep_samples = len(utterance) - (trailing_silent_blocks * block_size)
                utterance = utterance[:keep_samples]

        # Guard against utterances shorter than min_speech_ms
        min_samples = int(min_speech_ms := self.config.vad.min_speech_ms * self.config.audio.sample_rate / 1000.0)
        if len(utterance) < min_samples:
            logger.debug(f"Discarding short utterance: {len(utterance)} samples ({duration_s:.2f}s)")
            return np.array([], dtype=np.float32)

        # Update stats
        self._utterances += 1
        self._last_utterance_s = duration_s
        self._pre_roll_buffer.clear()
        self._buffer.clear()
        self._buffered_samples = 0
        self._state = "trailing"

        return utterance

    @property
    def state(self) -> str:
        """Return current state: 'idle', 'speech', or 'trailing'."""
        return self._state

    @property
    def stats(self) -> dict[str, float | int]:
        """Return recording statistics."""
        return {
            "blocks_seen": self._blocks_seen,
            "utterances": self._utterances,
            "last_utterance_s": self._last_utterance_s if self._last_utterance_s is not None else 0.0,
        }

    def reset(self) -> None:
        """Reset state and buffers."""
        self._state = "idle"
        self._buffer.clear()
        self._buffered_samples = 0
        self._pre_roll_buffer.clear()
        self._silence_run_ms = 0
        self._speech_blocks_count = 0


def write_wav(filepath: Path, samples: np.ndarray, sample_rate: int) -> None:
    """Write audio samples to a WAV file."""
    with wave.open(str(filepath), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        
        # Convert float32 [-1, 1] to int16 [-32768, 32767]
        samples_int16 = (samples * 32767).astype(np.int16)
        wav_file.writeframes(samples_int16.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="VAD & utterance recorder CLI")
    parser.add_argument("--test", action="store_true", help="Live microphone test")
    parser.add_argument("--record", type=str, default=None, help="Write utterances to WAV files")
    parser.add_argument("--selftest", action="store_true", help="Run synthetic self-test (no hardware)")
    args = parser.parse_args()

    try:
        if args.selftest:
            # Synthetic self-test: no microphone required
            print("Running VAD selftest...")

            from config import load_config
            config = load_config()

            vad = VAD(
                sample_rate=config.audio.sample_rate,
                frame_ms=config.audio.block_ms,
                threshold_db=config.vad.energy_threshold_db,
            )
            recorder = UtteranceRecorder(config, vad)

            sample_rate = config.audio.sample_rate
            blocksize = config.audio.blocksize
            block_ms = config.audio.block_ms

            # Generate test audio: 1.5s silence, 1.5s speech-like noise, 1.5s silence
            num_blocks = int(4.5 * sample_rate / blocksize)
            all_blocks = []

            # 1.5s silence (first ~1/3 blocks)
            silence_blocks = num_blocks // 3
            for _ in range(silence_blocks):
                all_blocks.append(np.zeros(blocksize, dtype=np.float32))

            # 1.5s speech-like noise (middle ~1/3 blocks)
            # Use higher amplitude to ensure we stay above threshold (-40 dBFS)
            # RMS of 0.1 is about -20 dBFS, which should be well above -40 dBFS threshold
            noise_level = 0.1
            for i in range(silence_blocks):
                block = noise_level * np.random.randn(blocksize).astype(np.float32)
                level_db = vad.level_db(block)
                if i < 5:  # Print first few levels for debugging
                    print(f"Test noise block {i}: level_db = {level_db:.1f}")
                all_blocks.append(block)

            # 1.5s silence (last ~1/3 blocks)
            for _ in range(silence_blocks):
                all_blocks.append(np.zeros(blocksize, dtype=np.float32))

            utterances = []
            for i, block in enumerate(all_blocks):
                result = recorder.process_block(block)
                if result is not None and len(result) > 0:
                    duration_s = len(result) / sample_rate
                    print(f"Emitted at block {i}: {len(result)} samples ({duration_s:.2f}s)")
                    utterances.append(result)

            # Verify exactly one utterance was emitted with duration in reasonable range
            # Note: duration will include pre-roll + speech + trailing silence
            if len(utterances) != 1:
                print(f"selftest failed: expected 1 utterance, got {len(utterances)}", file=sys.stderr)
                sys.exit(1)

            utterance = utterances[0]
            duration_s = len(utterance) / sample_rate
            
            # Expect ~1.5s (1.5s noise + pre_roll + some trailing silence)
            # The exact amount varies due to random noise and block alignment
            if not (1.0 <= duration_s <= 2.5):
                print(f"selftest failed: expected ~1.5s utterance, got {duration_s:.2f}s", file=sys.stderr)
                sys.exit(1)

            print(f"selftest ok: {len(utterances)} utterance(s), {duration_s:.2f} s")
            sys.exit(0)

        elif args.test:
            # Live microphone test
            from config import load_config
            config = load_config()

            print(f"threshold: {config.vad.energy_threshold_db:.1f} dBFS")
            print("[idle] listening...")

            recorder = UtteranceRecorder(config)

            if args.record:
                output_dir = Path(args.record).parent
                output_dir.mkdir(parents=True, exist_ok=True)
                counter = 0

            with Microphone(config) as mic:
                # Calibrate if enabled
                if config.vad.calibrate:
                    threshold = recorder.calibrate(mic)
                    print(f"threshold: {threshold:.1f} dBFS")
                    print("[idle] listening...")
                else:
                    threshold = config.vad.energy_threshold_db
                    print(f"threshold: {threshold:.1f} dBFS")
                    print("[idle] listening...")

                sample_rate = config.audio.sample_rate
                block_ms = config.audio.block_ms

                while True:
                    block = mic.read_block()
                    result = recorder.process_block(block)

                    if result is not None and len(result) > 0:
                        duration_s = len(result) / sample_rate
                        print(f"[trailing] {duration_s:.2f} s utterance, {len(result)} samples")

                        if args.record:
                            counter += 1
                            filepath = output_dir / f"out_{counter:03d}.wav"
                            write_wav(filepath, result, sample_rate)
                            print(f"[emit] wrote {filepath}")
                        else:
                            # Discard recorded utterance in non-record mode
                            pass

            print("Done.")
            sys.exit(0)

        else:
            # Default: just load config and show help
            parser.print_help()
            sys.exit(0)

    except AudioError as e:
        print(f"Audio Error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        logger.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
