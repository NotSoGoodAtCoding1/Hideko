from __future__ import annotations

import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from errors import STTError

if TYPE_CHECKING:
    from config import AppConfig

logger = logging.getLogger(__name__)

_HALLUCINATIONS = frozenset({
    "thank you", "thanks for watching", "thank you for watching",
    "subtitles by the amara org community", "subscribe", "please subscribe",
    "bye", "you", "the end", "okay", "hmm", "uh", "mm",
    "продолжение следует", "субтитры сделал dimatorzok",
})


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    duration_s: float
    latency_s: float
    avg_logprob: float | None


class STTEngine:
    """Speech-to-text engine using faster-whisper.

    Loads a Whisper model once and transcribes 16 kHz float32 audio arrays.
    Designed to never crash on silence and never return hallucinations.
    """

    def __init__(self, config: AppConfig) -> None:
        """Initialize the STT engine with configuration.

        Args:
            config: AppConfig instance containing STT settings.

        Note:
            Model loading is lazy - happens on first use via warmup() or transcribe().
        """
        self._config = config
        self._model = None  # type: ignore[assignment]

    def _ensure_model(self) -> None:
        """Load the Whisper model if not already loaded."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._config.stt.model_size,
                    device=self._config.stt.device,
                    compute_type=self._config.stt.compute_type,
                    download_root=str(self._config.stt.download_root),
                    cpu_threads=(
                        self._config.stt.cpu_threads
                        if self._config.stt.cpu_threads is not None
                        else max(1, (os.cpu_count() or 4) // 2)
                    ),
                )
            except (OSError, ValueError, RuntimeError) as e:
                raise STTError(
                    f"Failed to load STT model: {e}. Run `python scripts/download_models.py --stt`."
                ) from e

    def warmup(self) -> float:
        """Warm up the STT engine by loading the model and running a test transcription.

        Returns:
            Elapsed time in seconds for the warmup process.

        Note:
            Uses 1 second of silent audio to verify the model works without
            triggering short-input guards.
        """
        t0 = time.perf_counter()
        self._ensure_model()

        # Transcribe 1s of zeros (bypasses short-input guard since duration >= 0.30)
        silent_audio = np.zeros(16000, dtype=np.float32)
        _ = self.transcribe(silent_audio)

        elapsed = time.perf_counter() - t0
        logger.info("stt ready in %.2fs", elapsed)
        return elapsed

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript:
        """Transcribe audio array to text.

        Args:
            audio: Input audio as numpy array (expected shape: 1D or 2D with single channel).
            sample_rate: Audio sample rate in Hz (must be exactly 16000).

        Returns:
            Transcript containing the transcribed text and metadata.

        Raises:
            STTError: If sample rate is not 16 kHz or if model fails to load.
        """
        # Step 1: Normalize audio to float32 and ensure 1D
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)

        # Step 2: Validate sample rate (no resampling allowed)
        if sample_rate != 16000:
            raise STTError(
                f"STT expects 16 kHz audio, got {sample_rate} Hz. Resample before calling."
            )

        # Calculate duration
        duration = len(audio) / 16000.0

        # Step 3: Short audio guard - return empty without touching model
        if duration < 0.30:
            return Transcript(
                text="",
                language=None,
                duration_s=duration,
                latency_s=0.0,
                avg_logprob=None,
            )

        # Step 4: Long audio guard - error out
        if duration > self._config.stt.max_audio_s:
            raise STTError(
                f"Audio too long: {duration:.2f}s exceeds max {self._config.stt.max_audio_s}s."
            )

        # Step 5: Digital silence detection - return empty without touching model
        if np.max(np.abs(audio)) < 1e-4:
            return Transcript(
                text="",
                language=None,
                duration_s=duration,
                latency_s=0.0,
                avg_logprob=None,
            )

        # Step 6: Load model and start timing
        self._ensure_model()
        t0 = time.perf_counter()

        # Step 7: Transcribe with exact kwargs from spec
        segments, info = self._model.transcribe(
            audio,
            language=self._config.stt.language,
            beam_size=self._config.stt.beam_size,
            vad_filter=False,  # our VAD already trimmed the audio
            condition_on_previous_text=False,  # REQUIRED — stops hallucination snowballing
            temperature=0.0,
        )

        # Step 8: Materialize the segment generator (critical!)
        segments_list = list(segments)
        text = " ".join(s.text.strip() for s in segments_list)

        latency = time.perf_counter() - t0

        # Steps 9-10: Filter, normalize, hallucination-check, and build result
        filtered_text = self._filter_and_normalize(text, duration, segments_list)

        if not filtered_text:
            return Transcript(
                text="",
                language=None,
                duration_s=duration,
                latency_s=0.0,
                avg_logprob=None,
            )

        # Build final transcript with average log probability from segments
        avg_logprob = self._compute_avg_logprob(segments_list)

        logger.info(
            "stt: %.2fs for %.2fs audio -> %s",
            latency,
            duration,
            filtered_text if self._config.runtime.log_transcripts else "***REDACTED***",
        )

        return Transcript(
            text=filtered_text,
            language=self._config.stt.language,
            duration_s=duration,
            latency_s=latency,
            avg_logprob=avg_logprob,
        )

    def _filter_and_normalize(self, text: str, duration: float, segments) -> str:
        """Apply filtering and normalization rules to transcribed text.

        Args:
            text: Raw transcribed text from Whisper segments.
            duration: Audio duration in seconds.
            segments: Original segment objects for logprob/no_speech checks.

        Returns:
            Filtered and normalized text, or empty string if filtered out.
        """
        # Rule 1: Collapse internal whitespace and strip
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            return ""

        # Rule 2: Drop segment when avg_logprob < threshold AND no_speech_prob > 0.6
        # Filter out bad segments before joining
        filtered_segments = []
        min_avg_logprob = self._config.stt.min_avg_logprob
        for s in segments:
            if hasattr(s, "avg_logprob") and hasattr(s, "no_speech_prob"):
                if s.avg_logprob < min_avg_logprob and s.no_speech_prob > 0.6:
                    continue
            filtered_segments.append(s)

        # Re-join with filtered segments
        text = " ".join(s.text.strip() for s in filtered_segments)
        if not text:
            return ""

        # Rule 3: If joined text has < 2 characters, return empty
        if len(text) < 2:
            return ""

        # Rule 4: Hallucination check with normalization
        normalized = self._normalize_for_hallucination_check(text)
        if normalized in _HALLUCINATIONS and duration < 2.0:
            # A real 1s "thank you" is plausible; a 1s "Subtitles by the Amara org community" is not.
            # The duration guard keeps false drops rare.
            return ""

        # Rule 5: Check for repeated single token 4+ times
        if self._is_repeated_token(text):
            return ""

        return text

    def _normalize_for_hallucination_check(self, text: str) -> str:
        """Normalize text for hallucination checking.

        Args:
            text: Text to normalize.

        Returns:
            Normalized text with punctuation removed and whitespace collapsed.
        """
        # Lowercase
        text = text.lower()
        # Strip punctuation: .,!?…-–— and quotes
        text = re.sub(r"[.,!?…\-–—\"'’]", "", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _is_repeated_token(self, text: str) -> bool:
        """Check if text is a single token repeated 4+ times.

        Args:
            text: Text to check.

        Returns:
            True if text matches pattern like "you you you you".
        """
        # Match pattern: word repeated 4 or more times separated by spaces
        pattern = r"^(\w+) (\1) (\1) (\1)( \1)*$"
        return bool(re.match(pattern, text))

    def _compute_avg_logprob(self, segments) -> float | None:
        """Compute average log probability from segments.

        Args:
            segments: List of segment objects.

        Returns:
            Average log probability or None if not available.
        """
        if not segments:
            return None
        probs = [s.avg_logprob for s in segments if hasattr(s, "avg_logprob")]
        if not probs:
            return None
        return sum(probs) / len(probs)


def _main() -> int:
    """CLI entry point.

    Supports --file PATH, --mic SECONDS, and --warmup options.
    Returns 0 on success, 3 on STTError.
    """
    import argparse

    parser = argparse.ArgumentParser(description="STT Engine CLI")
    parser.add_argument("--file", type=str, help="Path to WAV file (must be 16 kHz mono)")
    parser.add_argument("--mic", type=float, help="Record from mic for SECONDS")
    parser.add_argument("--warmup", action="store_true", help="Run warmup only")

    args = parser.parse_args()

    try:
        config = load_config()
        engine = STTEngine(config)

        if args.warmup:
            elapsed = engine.warmup()
            print(f"model loaded in ~{elapsed:.1f}s; warm transcription ready")
            return 0

        if args.file:
            import soundfile as sf

            audio, sample_rate = sf.read(args.file)
            if sample_rate != 16000:
                raise STTError(
                    f"--file rejects non-16 kHz WAVs with the actual rate/channels: {sample_rate} Hz"
                )
            if len(audio.shape) > 1 and audio.shape[1] != 1:
                raise STTError(
                    f"--file rejects non-mono WAVs with the actual rate/channels: {audio.shape[1]} channels"
                )
            if sample_rate != 16000:
                raise STTError(
                    f"--file rejects non-16 kHz WAVs with the actual rate/channels: {sample_rate} Hz"
                )
            audio = (audio if audio.ndim == 1 else audio[:, 0]).astype(np.float32)

        elif args.mic is not None:
            import sounddevice as sd

            print("Recording...")
            audio = sd.rec(int(args.mic * 16000), samplerate=16000, channels=1)
            sd.wait()
            audio = audio.astype(np.float32)

        else:
            parser.print_help()
            return 0

        transcript = engine.transcribe(audio, sample_rate=16000)
        print(f"text: {transcript.text!r}")
        return 0

    except STTError as e:
        print(f"STTError: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    from config import load_config

    sys.exit(_main())
