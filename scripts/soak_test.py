"""Soak test script for memory leak detection.

Runs repeated response + synthesis cycles without audio playback and fails
if RSS grows more than 300 MB over the test duration.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

# Import from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import load_config
from logging_setup import memory_rss_mb
from response_handler import ResponseHandler
from tts_engine import TTSEngine

logger = logging.getLogger(__name__)


def run_soak_test(
    minutes: float,
    interval: int,
    out_path: Path,
) -> bool:
    """Run the soak test loop.

    Args:
        minutes: Test duration in minutes.
        interval: Logging interval in seconds.
        out_path: Path to write results.

    Returns:
        True if test passed (RSS growth <= 300 MB), False otherwise.
    """
    config = load_config()
    handler = ResponseHandler(config)
    engine = TTSEngine(config)

    # Sample triggers once at startup
    triggers_path = PROJECT_ROOT / "responses" / "triggers.yaml"
    triggers_data = yaml.safe_load(triggers_path.read_text(encoding="utf-8"))
    trigger_list = triggers_data["triggers"]
    patterns: list[str] = []
    for t in trigger_list:
        patterns.extend(t["patterns"])

    # State tracking
    start_time = time.monotonic()
    deadline = start_time + minutes * 60
    last_log = start_time
    turn_count = 0
    rss_samples: list[float] = []
    first_rss: Optional[float] = None
    last_rss: Optional[float] = None

    # Main loop
    while time.monotonic() < deadline:
        # Pick random trigger pattern
        pattern = random.choice(patterns)

        # Respond
        response = handler.respond(pattern)

        # Synthesize (no playback, no mic)
        engine.synthesize(response.text)

        # Sample RSS
        rss = memory_rss_mb()
        if rss is not None:
            rss_samples.append(rss)
            last_rss = rss
            if first_rss is None:
                first_rss = rss

        # Log at interval
        now = time.monotonic()
        if now - last_log >= interval:
            rss_str = f"{round(rss, 1) if rss is not None else 'N/A'}"
            logger.info("t=%ds rss=%sMB turns=%d", int(now - start_time), rss_str, turn_count)
            last_log = now

        # Increment turn count
        turn_count += 1

    # Calculate results
    rss_growth_mb = (last_rss - first_rss) if first_rss is not None and last_rss is not None else 0.0
    passed = rss_growth_mb <= 300.0

    # Write results to file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    min_rss = min(rss_samples) if rss_samples else 0.0
    max_rss = max(rss_samples) if rss_samples else 0.0
    sorted_samples = sorted(rss_samples)
    n = len(sorted_samples)
    if n == 0:
        median_rss = 0.0
    elif n == 1:
        median_rss = sorted_samples[0]
    else:
        mid = n // 2
        if n % 2 == 0:
            median_rss = (sorted_samples[mid - 1] + sorted_samples[mid]) / 2
        else:
            median_rss = sorted_samples[mid]

    results_text = f"""# Soak Test Results

Duration: {minutes} minutes
Turns: {turn_count}

## RSS Statistics
- First: {round(first_rss, 1) if first_rss is not None else 'N/A'} MB
- Last: {round(last_rss, 1) if last_rss is not None else 'N/A'} MB
- Growth: {round(rss_growth_mb, 1)} MB

- Min: {round(min_rss, 1)} MB
- Max: {round(max_rss, 1)} MB
- Median: {round(median_rss, 1)} MB

## Result
{'PASS' if passed else 'FAIL'}: rss growth {round(rss_growth_mb, 1)} MB over {minutes} min, {turn_count} turns
"""

    out_path.write_text(results_text, encoding="utf-8")

    # Print to stdout
    status = "PASS" if passed else "FAIL"
    print(f"{status}: rss growth {round(rss_growth_mb, 1)} MB over {minutes} min, {turn_count} turns")

    return passed


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Soak test script for memory leak detection"
    )
    parser.add_argument(
        "--minutes",
        type=float,
        default=5.0,
        help="Test duration in minutes (default: 5)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Logging interval in seconds (default: 10)"
    )
    parser.add_argument(
        "--out",
        type=str,
        default="logs/soak.md",
        help="Output file path (default: logs/soak.md)"
    )

    args = parser.parse_args()

    out_path = Path(args.out)

    try:
        passed = run_soak_test(
            minutes=args.minutes,
            interval=args.interval,
            out_path=out_path,
        )
        sys.exit(0 if passed else 1)
    except Exception as e:
        logger.exception("Soak test failed with exception")
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
