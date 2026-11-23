#!/usr/bin/env python
"""Benchmark STT/TTS/response latency on real CPU hardware and write logs/benchmark.md.

Usage:
    benchmark.py [--wav PATH] [--text TEXT] [--repeat N]
                 [--out PATH] [--skip-stt] [--skip-tts]

Defaults: --text "Hello, I am Hideko, and this is a benchmark sentence.", --repeat 3, --out logs/benchmark.md.
--repeat minimum is 2 so a median is meaningful. The first run is always reported as cold and excluded from the median.
"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import re
import statistics
import sys
import time
import warnings
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import numpy as np
    import soundfile as sf
except ImportError as exc:
    print(f"Missing dependency: {exc}", file=sys.stderr)
    sys.exit(1)

# Import Hideko modules - catch errors gracefully
STT_AVAILABLE = False
TTS_AVAILABLE = False
RESPONSE_HANDLER_AVAILABLE = False
try:
    from config import load_config, AppConfig
    from stt_engine import STTEngine
    from tts_engine import TTSEngine
    from response_handler import ResponseHandler
    STT_AVAILABLE = True
    TTS_AVAILABLE = True
    RESPONSE_HANDLER_AVAILABLE = True
except Exception as e:
    print(f"Failed to import Hideko modules: {e}", file=sys.stderr)

logger = logging.getLogger(__name__)


class BenchmarkResult:
    """Container for benchmark results."""

    def __init__(self) -> None:
        self.stt_cold_s: float | None = None
        self.stt_warm_median_s: float | None = None
        self.stt_warm_max_s: float | None = None
        self.stt_10s_median_s: float | None = None
        self.stt_10s_max_s: float | None = None
        self.tts_cold_s: float | None = None
        self.tts_warm_median_s: float | None = None
        self.tts_warm_max_s: float | None = None
        self.tts_cached_median_s: float | None = None
        self.tts_cached_max_s: float | None = None
        self.response_median_ms: float | None = None
        self.response_max_ms: float | None = None
        self.text_turn_median_s: float | None = None
        self.text_turn_max_s: float | None = None

    def to_table_rows(self, stt_skipped: bool = False, tts_skipped: bool = False) -> list[tuple[str, str, str, str, str]]:
        """Convert results to table rows (metric, median, max, budget, verdict)."""
        rows = []

        # STT cold (load + 5 s) - informational, no budget
        if stt_skipped:
            rows.append(("STT cold (load + 5 s)", "n/a", "n/a", "-", "-"))
        elif self.stt_cold_s is not None:
            rows.append(("STT cold (load + 5 s)", f"{self.stt_cold_s:.2f} s", f"{self.stt_cold_s:.2f} s", "-", self._info_verdict()))

        # STT warm (5 s audio) - budget 3.0 s
        if stt_skipped:
            rows.append(("STT warm (5 s audio)", "n/a", "n/a", "3.0 s", "-"))
        elif self.stt_warm_median_s is not None:
            verdict = self._verdict(self.stt_warm_median_s, 3.0)
            rows.append(("STT warm (5 s audio)", f"{self.stt_warm_median_s:.2f} s", f"{self.stt_warm_max_s:.2f} s", "3.0 s", verdict))

        # STT on 10 s audio - budget 6.0 s
        if stt_skipped:
            rows.append(("STT on 10 s audio", "n/a", "n/a", "6.0 s", "-"))
        elif self.stt_10s_median_s is not None:
            verdict = self._verdict(self.stt_10s_median_s, 6.0)
            rows.append(("STT on 10 s audio", f"{self.stt_10s_median_s:.2f} s", f"{self.stt_10s_max_s:.2f} s", "6.0 s", verdict))

        # TTS cold - informational, no budget
        if tts_skipped:
            rows.append(("TTS cold", "n/a", "n/a", "-", "-"))
        elif self.tts_cold_s is not None:
            rows.append(("TTS cold", f"{self.tts_cold_s:.2f} s", f"{self.tts_cold_s:.2f} s", "-", self._info_verdict()))

        # TTS warm (10 words) - budget 1.5 s
        if tts_skipped:
            rows.append(("TTS warm (10 words)", "n/a", "n/a", "1.5 s", "-"))
        elif self.tts_warm_median_s is not None:
            verdict = self._verdict(self.tts_warm_median_s, 1.5)
            rows.append(("TTS warm (10 words)", f"{self.tts_warm_median_s:.2f} s", f"{self.tts_warm_max_s:.2f} s", "1.5 s", verdict))

        # TTS cached - informational, no budget
        if tts_skipped:
            rows.append(("TTS cached", "n/a", "n/a", "-", "-"))
        elif self.tts_cached_median_s is not None:
            rows.append(("TTS cached", f"{self.tts_cached_median_s:.2f} s", f"{self.tts_cached_max_s:.2f} s", "-", self._info_verdict()))

        # Response matching - budget 20 ms
        if self.response_median_ms is not None:
            verdict = self._verdict(self.response_median_ms, 20.0)
            rows.append(("Response matching", f"{self.response_median_ms:.1f} ms", f"{self.response_max_ms:.1f} ms", "20 ms", verdict))

        # Text turn end-to-end - budget 10 s
        if stt_skipped or tts_skipped:
            rows.append(("Text turn end-to-end", "n/a", "n/a", "10 s", "-"))
        elif self.text_turn_median_s is not None:
            verdict = self._verdict(self.text_turn_median_s, 10.0)
            rows.append(("Text turn end-to-end", f"{self.text_turn_median_s:.2f} s", f"{self.text_turn_max_s:.2f} s", "10 s", verdict))

        return rows

    def _verdict(self, value: float, budget: float) -> str:
        """Return PASS/FAIL based on whether value exceeds budget."""
        if value > budget * 1.5:
            return "FAIL"
        return "PASS"

    def _info_verdict(self) -> str:
        """Return dash for informational rows without budgets."""
        return "-"

    def has_soft_failure(self) -> bool:
        """Check if any measured value exceeds its budget by more than 50%."""
        checks = [
            (self.stt_warm_median_s, 3.0),
            (self.stt_10s_median_s, 6.0),
            (self.tts_warm_median_s, 1.5),
            (self.response_median_ms, 20.0),
            (self.text_turn_median_s, 10.0),
        ]
        for value, budget in checks:
            if value is not None and value > budget * 1.5:
                return True
        return False


def generate_synthetic_audio(duration_s: float = 5.0, sample_rate: int = 16000) -> np.ndarray:
    """Generate a synthetic 5 s signal: a 220 Hz tone with an amplitude envelope.

    Args:
        duration_s: Duration in seconds (default 5).
        sample_rate: Sample rate in Hz (default 16000).

    Returns:
        numpy array of float32 audio samples.
    """
    n_samples = int(sample_rate * duration_s)
    t = np.linspace(0, duration_s, n_samples, dtype=np.float32)
    # Amplitude envelope: fade in for first 0.5s, hold, fade out for last 0.5s
    envelope = np.ones(n_samples, dtype=np.float32)
    envelope[:int(sample_rate * 0.5)] = t[:int(sample_rate * 0.5)] / (sample_rate * 0.5)
    envelope[-int(sample_rate * 0.5):] = 1 - (t[-int(sample_rate * 0.5):] - (duration_s - sample_rate * 0.5)) / (sample_rate * 0.5)
    # 220 Hz sine wave
    audio = 0.3 * np.sin(2 * np.pi * 220 * t).astype(np.float32) * envelope
    return audio


def load_audio_file(wav_path: Path, sample_rate: int = 16000) -> np.ndarray | None:
    """Load a WAV file with soundfile.

    Args:
        wav_path: Path to the WAV file.
        sample_rate: Expected sample rate (must be exactly 16000).

    Returns:
        Audio array if valid, None otherwise.
    """
    try:
        data, sr = sf.read(wav_path)
    except Exception as e:
        print(f"Failed to load {wav_path}: {e}", file=sys.stderr)
        return None

    # Require 16 kHz mono
    if sr != sample_rate:
        print(f"Audio must be {sample_rate} Hz, got {sr} Hz", file=sys.stderr)
        return None
    if len(data.shape) > 1 and data.shape[1] != 1:
        print(f"Audio must be mono, got {data.shape[1]} channels", file=sys.stderr)
        return None

    # Convert to float32
    audio = (data if data.dtype == np.float32 else data.astype(np.float32))
    return audio


def format_time(value: float | None, unit: str = "s") -> str:
    """Format a time value with unit."""
    if value is None:
        return "n/a"
    return f"{value:.2f} {unit}"


def format_time_ms(value: float | None) -> str:
    """Format milliseconds."""
    if value is None:
        return "n/a"
    return f"{value:.1f} ms"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark STT/TTS/response latency on real CPU hardware."
    )
    parser.add_argument("--wav", type=str, help="Path to WAV file for STT testing (must be 16 kHz mono)")
    parser.add_argument("--text", type=str, default="Hello, I am Hideko, and this is a benchmark sentence.",
                        help="Text for TTS testing (default: 'Hello, I am Hideko, and this is a benchmark sentence.')")
    parser.add_argument("--repeat", type=int, default=3, help="Number of repeat runs (minimum 2)")
    parser.add_argument("--out", type=str, default="logs/benchmark.md", help="Output file path")
    parser.add_argument("--skip-stt", action="store_true", help="Skip STT benchmarks")
    parser.add_argument("--skip-tts", action="store_true", help="Skip TTS benchmarks")

    args = parser.parse_args()

    # Validate --repeat
    if args.repeat < 2:
        print("--repeat must be at least 2 for meaningful median calculation", file=sys.stderr)
        return 1

    # Load config
    try:
        config = load_config()
    except Exception as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    # Initialize engines
    stt_engine = STTEngine(config) if STT_AVAILABLE else None
    tts_engine = TTSEngine(config) if TTS_AVAILABLE else None
    response_handler = ResponseHandler(config) if RESPONSE_HANDLER_AVAILABLE else None

    # Check for missing models
    stt_available = STT_AVAILABLE and stt_engine is not None
    tts_available = TTS_AVAILABLE and tts_engine is not None

    if not stt_available:
        print("SKIP stt", file=sys.stderr)
    if not tts_available:
        print("SKIP tts", file=sys.stderr)

    # Initialize result container
    result = BenchmarkResult()
    
    # Track which benchmarks were skipped
    stt_skipped = not stt_available or args.skip_stt
    tts_skipped = not tts_available or args.skip_tts

    audio = None
    if args.wav:
        audio = load_audio_file(Path(args.wav))
        if audio is None:
            print(f"Invalid WAV file: {args.wav}", file=sys.stderr)
            return 1

    # Generate synthetic audio for STT if no WAV provided and not skipped
    use_synthetic_stt = not stt_skipped and args.wav is None
    if use_synthetic_stt:
        warnings.warn("STT numbers on synthetic audio are valid for timing only, not accuracy.", UserWarning)
        audio = generate_synthetic_audio(5.0, 16000)

    # STT benchmarks
    if not stt_skipped:
        # STT cold: warmup time (includes model load)
        t0 = time.perf_counter()
        stt_cold_s = stt_engine.warmup()
        result.stt_cold_s = stt_cold_s

        # STT warm: transcribe 5s clip (multiple runs)
        warm_times = []
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            stt_engine.transcribe(audio, sample_rate=16000)
            warm_times.append(time.perf_counter() - t0)
        result.stt_warm_median_s = statistics.median(warm_times)
        result.stt_warm_max_s = max(warm_times)

        # STT on 10s: double the audio (concatenate with itself)
        audio_10s = np.concatenate([audio, audio])

        # Run 10s transcriptions (multiple runs)
        warm_times_10s = []
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            stt_engine.transcribe(audio_10s, sample_rate=16000)
            warm_times_10s.append(time.perf_counter() - t0)
        result.stt_10s_median_s = statistics.median(warm_times_10s)
        result.stt_10s_max_s = max(warm_times_10s)

    # TTS benchmarks
    if not tts_skipped:
        # TTS cold: first synthesize (subprocess spawn)
        t0 = time.perf_counter()
        tts_engine.synthesize(args.text)
        result.tts_cold_s = time.perf_counter() - t0

        # Clear cache for warm test
        tts_engine.clear_cache()

        # TTS warm: distinct sentences (cached-miss)
        warm_texts = [
            "The quick brown fox jumps over the lazy dog.",
            "Hello world, this is a test of text to speech.",
            "Benchmarking performance with varied content here.",
        ]
        warm_times = []
        for text in warm_texts:
            t0 = time.perf_counter()
            tts_engine.synthesize(text)
            warm_times.append(time.perf_counter() - t0)
        result.tts_warm_median_s = statistics.median(warm_times)
        result.tts_warm_max_s = max(warm_times)

        # TTS cached: repeat of already-synthesized sentence
        t0 = time.perf_counter()
        tts_engine.synthesize(args.text)  # This should be cached
        result.tts_cached_median_s = time.perf_counter() - t0
        result.tts_cached_max_s = result.tts_cached_median_s

    # Response benchmarks
    if RESPONSE_HANDLER_AVAILABLE and response_handler is not None:
        # Response matching: 1000 calls
        response_times = []
        test_text = "hello"  # Simple trigger text
        for _ in range(1000):
            t0 = time.perf_counter()
            response_handler.respond(test_text)
            response_times.append((time.perf_counter() - t0) * 1000)  # Convert to ms
        result.response_median_ms = statistics.median(response_times)
        result.response_max_ms = max(response_times)

    # Text turn end-to-end: responder + TTS, no playback
    if not stt_skipped and not tts_skipped:
        text_turn_times = []
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            # Simulate a turn: respond to input + synthesize response
            response_handler.respond("hello")
            tts_engine.synthesize("Hello, I am Hideko.")
            text_turn_times.append(time.perf_counter() - t0)
        result.text_turn_median_s = statistics.median(text_turn_times)
        result.text_turn_max_s = max(text_turn_times)

    # Build header info
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    cpu_count = os.cpu_count() or 1
    python_version = platform.python_version()
    stt_model = config.stt.model_size
    tts_voice = config.tts.voice_model.name if hasattr(config.tts.voice_model, "name") else str(config.tts.voice_model)

    # Build markdown table
    rows = result.to_table_rows(stt_skipped, tts_skipped)
    header = "| Metric | median | max | budget | verdict |\n|--------|--------|-----|--------|---------|"
    data_rows = "\n".join(f"| {metric} | {median} | {max_val} | {budget} | {verdict} |" for metric, median, max_val, budget, verdict in rows)

    # Use ASCII dash for compatibility
    info_dash = "-"

    markdown_content = f"""# Hideko benchmark - {timestamp}
CPU: {cpu_count} logical cores | Python {python_version} | {stt_model} int8 | {tts_voice}

{header}
{data_rows}

*No latency target was set for this sprint; verdicts are informational.*
"""

    # Ensure output directory exists
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output file
    out_path.write_text(markdown_content, encoding="utf-8")

    # Print table to stdout
    print(markdown_content)

    # Check for soft failure (>150% budget breach)
    if result.has_soft_failure():
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
