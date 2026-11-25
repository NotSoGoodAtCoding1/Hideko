"""Logging setup module for the application."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

import ctypes
from ctypes import wintypes


class _PMC(ctypes.Structure):
    """Windows PROCESS_MEMORY_COUNTERS structure for RSS queries."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def setup_logging(config, *, debug: bool = False, log_file: Optional[Path] = None) -> None:
    """Set up logging configuration based on the provided LoggingConfig.

    Args:
        config: The LoggingConfig object containing logging settings.
        debug: If True, set logger level to DEBUG. Defaults to False.
        log_file: Optional custom log file path. Defaults to config.file.
    """
    # Remove and close all existing handlers on the root logger for idempotency
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)

    # Determine log level
    log_level = logging.DEBUG if debug else getattr(logging, config.level)

    # Create log file path
    log_path = log_file or config.file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Console handler -> stderr
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    # File handler with rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Add handlers to root logger
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(log_level)

    # Silence noisy third parties
    for logger_name in ["faster_whisper", "ctranslate2", "urllib3", "numba"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)


def memory_rss_mb() -> Optional[float]:
    """Get the current process's Resident Set Size (RSS) memory usage in MB.

    Returns:
        The RSS memory usage in megabytes as a float on Windows, None otherwise.
    """
    try:
        # Get current process handle
        process_handle = ctypes.windll.kernel32.GetCurrentProcess()

        # Create structure to hold memory info
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(pmc)

        # Get process memory information
        ctypes.windll.psapi.GetProcessMemoryInfo(
            process_handle,
            ctypes.byref(pmc),
            ctypes.sizeof(pmc),
        )

        # Return working set size in MB
        return pmc.WorkingSetSize / 1e6

    except (OSError, AttributeError):
        return None
