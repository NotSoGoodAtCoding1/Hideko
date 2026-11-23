from __future__ import annotations

import argparse
import logging
import re
import sys
import subprocess
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from errors import TTSError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioClip:
    samples: np.ndarray      # float32, mono, -1.0..1.0
    sample_rate: int
    duration_s: float


class TTSEngine:
    """Text-to-speech engine using Piper TTS."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the TTS engine. Checks for required files but does not load models."""
        self._config = config
        self._available = (
            config.tts.piper_exe.is_file()
            and config.tts.voice_model.is_file()
            and config.tts.voice_model.with_suffix(".onnx.json").is_file()
        )
        self._cache: OrderedDict[str, AudioClip] = OrderedDict()

    def is_available(self) -> bool:
        """Return True if Piper binary and voice model are present."""
        return self._available

    def synthesize(self, text: str) -> AudioClip:
        """Synthesize speech from text and return an AudioClip."""
        # 1. Check availability
        if not self._available:
            missing = []
            if not self._config.tts.piper_exe.is_file():
                missing.append(str(self._config.tts.piper_exe))
            if not self._config.tts.voice_model.is_file():
                missing.append(str(self._config.tts.voice_model))
            if not self._config.tts.voice_model.with_suffix(".onnx.json").is_file():
                missing.append(str(self._config.tts.voice_model.with_suffix(".onnx.json")))
            
            paths = ", ".join(missing)
            raise TTSError(
                f"Piper binary or voice model not found: {paths}. "
                f"Run `python scripts/download_models.py --all`."
            )

        # 2. Clean text
        clean = self._clean(text)
        if not clean:
            raise TTSError("cannot synthesize empty text")

        # 3. Check cache
        if clean in self._cache:
            self._cache.move_to_end(clean)
            return self._cache[clean]

        # 4. Create temp file
        temp_dir = Path(tempfile.gettempdir())
        wav_path = temp_dir / f"piper_tts_{Path().cwd().parts[-1]}_{int(time.time() * 1000)}.wav"

        try:
            # 5. Run Piper subprocess with cleaned text
            start_time = time.perf_counter()
            proc = subprocess.run(
                [
                    str(self._config.tts.piper_exe),
                    "--model", str(self._config.tts.voice_model),
                    "--output_file", str(wav_path),
                    "--length_scale", f"{self._config.tts.length_scale:.2f}",
                ],
                input=clean.encode("utf-8"),  # Use cleaned text, not original
                capture_output=True,
                timeout=self._config.tts.timeout_s,
                cwd=str(self._config.tts.piper_exe.parent),
            )

            # 6. Check return code
            if proc.returncode != 0:
                stderr_tail = proc.stderr.decode("utf-8", "replace")[-800:]
                raise TTSError(
                    f"Piper failed with exit code {proc.returncode}:\n{stderr_tail}"
                )

            # 7. Read WAV and build AudioClip
            data, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
            
            if data.ndim > 1:
                data = data.mean(axis=1)
            clip = AudioClip(
                samples=np.ascontiguousarray(data, dtype=np.float32),
                sample_rate=int(sr),
                duration_s=len(data) / sr
            )

            # 8. Check for empty output (only if we actually read audio)
            if not wav_path.exists() or clip.duration_s < 0.05:
                raise TTSError("Piper produced empty audio (exit 0)")

            # 9. Cache and log
            latency = time.perf_counter() - start_time
            self._cache[clean] = clip
            if len(self._cache) > 32:
                self._cache.popitem(last=False)
            
            logger.info("tts: %.2fs -> %.2fs audio, %d chars", latency, clip.duration_s, len(text))

            return clip

        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass

    def clear_cache(self) -> None:
        """Clear the LRU cache."""
        self._cache.clear()

    def _clean(self, text: str) -> str:
        """Clean and normalize text for synthesis."""
        # Strip leading/trailing whitespace
        text = text.strip()
        
        if not text:
            return ""
        
        # Collapse whitespace runs to single spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Strip *, _, #, and backticks
        text = re.sub(r'[*_`]', '', text)
        
        # Truncate at word boundary if needed
        max_chars = self._config.tts.max_chars
        if len(text) > max_chars:
            # Find last space before max_chars
            trunc_pos = text.rfind(' ', 0, max_chars)
            if trunc_pos == -1:
                trunc_pos = max_chars
            truncated = text[:trunc_pos]
            # If we didn't find a space and trunc_pos < max_chars, add trailing space to reach max_chars
            if trunc_pos < max_chars:
                truncated = truncated + ' '
            logger.warning(
                f"Truncated text from {len(text)} to {len(truncated)} chars "
                f"(max={max_chars})"
            )
            text = truncated
        
        return text


def main() -> None:
    """CLI for testing the TTS engine."""
    parser = argparse.ArgumentParser(description="Piper TTS engine CLI")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if Piper and voice model are available"
    )
    parser.add_argument(
        "--say",
        type=str,
        nargs="+",
        metavar="TEXT",
        help="Synthesize and play text (use quotes for multi-word)"
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Write output WAV to file instead of playing"
    )
    args = parser.parse_args()

    try:
        from config import load_config
        config = load_config()
    except Exception as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    engine = TTSEngine(config)

    if args.check:
        piper_path = config.tts.piper_exe
        voice_path = config.tts.voice_model
        
        piper_ok = piper_path.is_file()
        voice_ok = voice_path.is_file() and voice_path.with_suffix(".onnx.json").is_file()
        
        if piper_ok:
            print(f"piper ok: {piper_path}")
        else:
            print(f"piper missing: {piper_path}", file=sys.stderr)
        
        if voice_ok:
            size_mb = voice_path.stat().st_size / (1024 * 1024)
            print(f"voice ok: {voice_path} ({size_mb:.1f} MB)")
        else:
            print(f"voice missing: {voice_path}", file=sys.stderr)
        
        if not piper_ok or not voice_ok:
            sys.exit(3)
        sys.exit(0)

    if args.say is None:
        parser.error("either --check or --say with text must be provided")

    # Join the list into a single string (argparse splits on whitespace)
    text = " ".join(args.say)

    try:
        clip = engine.synthesize(text)
    except TTSError as e:
        print(f"TTS error: {e}", file=sys.stderr)
        sys.exit(2)

    if args.out:
        sf.write(args.out, clip.samples, clip.sample_rate)
        print(f"written {clip.duration_s:.1f}s to {args.out}")
    else:
        from audio_manager import Speaker
        with Speaker(config) as speaker:
            speaker.play(clip.samples, clip.sample_rate)
        print(f"synthesized {clip.duration_s:.1f}s at {clip.sample_rate} Hz in {engine._config.tts.timeout_s}s")


if __name__ == "__main__":
    main()
