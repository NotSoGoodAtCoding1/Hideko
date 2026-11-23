"""CLI module: argument parsing, non-blocking key listener, and status-line formatting."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path
from typing import Optional


@dataclasses.dataclass(frozen=True)
class CliOptions:
    """Command-line options for the application."""
    config: Path
    text: str | None
    turns: int | None
    debug: bool
    no_tts: bool
    no_greet: bool
    list_devices: bool
    calibrate: bool
    log_file: Path | None
    mute_key: str
    facts: bool
    forget: bool


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="hideko",
        description="Interactive voice assistant",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="One-shot text input (skip mic + VAD, run responder + TTS, exit)",
    )
    parser.add_argument(
        "--turns",
        type=str,
        default=None,
        help="Number of exchanges to run (overrides runtime.max_turns)",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        default=False,
        help="Print responses but do not synthesize or play",
    )
    parser.add_argument(
        "--no-greet",
        action="store_true",
        default=False,
        help="Skip the startup greeting",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        default=False,
        help="Print device table and exit",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        default=False,
        help="Print calibration result and exit",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (overrides config.logging.file)",
    )
    parser.add_argument(
        "--mute-key",
        type=str,
        default="m",
        help="Key to mute/resume (default: m; use 'none' to disable)",
    )
    parser.add_argument(
        "--facts",
        action="store_true",
        default=False,
        help="Print remembered facts and exit",
    )
    parser.add_argument(
        "--forget",
        action="store_true",
        default=False,
        help="Delete all remembered facts and exit",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> CliOptions:
    """Parse command-line arguments and return CliOptions."""
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    log_file_path = Path(args.log_file) if args.log_file is not None else None

    # Convert turns from string to int if provided
    turns = int(args.turns) if args.turns is not None else None

    return CliOptions(
        config=config_path,
        text=args.text,
        turns=turns,
        debug=args.debug,
        no_tts=args.no_tts,
        no_greet=args.no_greet,
        list_devices=args.list_devices,
        calibrate=args.calibrate,
        log_file=log_file_path,
        mute_key=args.mute_key,
        facts=args.facts,
        forget=args.forget,
    )


class KeyListener:
    """Non-blocking single-key reader (Windows only; no-op elsewhere)."""

    def __init__(self) -> None:
        """Initialize the key listener."""
        self._supported = sys.platform == "win32"
        self._msvcrt = None
        if self._supported:
            try:
                import msvcrt
            except ImportError:  # pragma: no cover
                self._supported = False

    @property
    def supported(self) -> bool:
        """Return True if key listener is supported on this platform."""
        return self._supported

    def poll(self) -> str | None:
        """Poll for a single key press without blocking.

        Returns the lowercase key character or None if no key was pressed.
        On non-Windows platforms, always returns None.
        """
        if not self._supported:
            return None

        if self._msvcrt is None:
            try:
                import msvcrt
            except ImportError:  # pragma: no cover
                return None

        if not msvcrt.kbhit():
            return None

        ch = msvcrt.getwch()

        # Handle special key prefix bytes (arrows, function keys, etc.)
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # consume the next byte
            return None

        return ch.lower()


class Status:
    """Console status lines with consistent formatting and flushing."""

    def listening(self) -> None:
        """Print listening status."""
        print("[listening]", flush=True)

    def thinking(self) -> None:
        """Print thinking status with carriage return for overwrite."""
        print("  ...thinking\r", end="", flush=True)

    def speaking(self) -> None:
        """Print speaking status."""
        print("[speaking]", flush=True)

    def paused(self) -> None:
        """Print paused status."""
        print("[paused — press m to resume]", flush=True)

    def heard(self, text: str) -> None:
        """Print heard text."""
        print(f"You:    {text}", flush=True)

    def say(self, text: str) -> None:
        """Print spoken text."""
        print(f"Hideko: {text}", flush=True)

    def timing(
        self, stt: float, resp: float, tts: float, play: float
    ) -> None:
        """Print timing information for STT, response, TTS, and playback."""
        total = stt + resp + tts + play
        print(
            f"  [stt {stt:.1f}s | resp {resp:.2f}s | tts {tts:.1f}s | play {play:.1f}s | total {total:.1f}s]",
            flush=True,
        )
