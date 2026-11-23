"""Disk-backed memory store for learned facts.

This module provides an offline, JSON-backed store for facts that Hideko learns from the user.
No LLM or network access is used. The store is designed to never crash the app on missing or corrupt files.
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from config import AppConfig
from errors import MemoryError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fact:
    """A single fact stored in the memory."""
    key: str
    value: str
    updated_at: float


class MemoryStore:
    """A disk-backed store for learned facts.

    Facts are stored as JSON in a file with versioning and atomic writes.
    When disabled, all operations are no-ops.
    """

    def __init__(self, config: AppConfig) -> None:
        """Initialize the memory store with the given configuration.

        Args:
            config: The AppConfig containing memory settings.

        Raises:
            MemoryError: If the memory file cannot be read during initialization.
        """
        self.config = config
        self._facts: dict[str, Fact] = {}
        self.load()

    def load(self) -> None:
        """Load facts from the disk file.

        If the file does not exist, returns silently.
        On any error (OSError, JSONDecodeError, corrupt data), logs a warning and starts empty.
        Never raises an exception.
        """
        if not self.config.memory.enabled:
            return

        path = self.config.memory.file
        try:
            if not path.exists():
                return
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Cannot read memory file {path}: {e}")
            self._facts.clear()
            return

        if not isinstance(data, dict):
            logger.warning(f"Memory file root is not a dict: {type(data).__name__}")
            self._facts.clear()
            return

        if data.get("version") != 1:
            logger.warning(f"Invalid memory version: {data.get('version')}, expected 1")
            self._facts.clear()
            return

        facts_data = data.get("facts")
        if not isinstance(facts_data, dict):
            logger.warning(f"Memory 'facts' is not a dict: {type(facts_data).__name__}")
            self._facts.clear()
            return

        for key, entry in facts_data.items():
            try:
                if not isinstance(entry, dict) or "value" not in entry or "updated_at" not in entry:
                    logger.debug(f"Skipping malformed fact entry for key '{key}'")
                    continue
                value = entry["value"]
                updated_at = entry["updated_at"]
                if not isinstance(value, str) or not isinstance(updated_at, (int, float)):
                    logger.debug(f"Skipping malformed fact entry for key '{key}': invalid value or timestamp")
                    continue
                self._facts[key] = Fact(key=key, value=value, updated_at=float(updated_at))
            except Exception as e:
                logger.debug(f"Error processing fact '{key}': {e}")
                continue

    def save(self) -> None:
        """Save all facts to the disk file atomically.

        Creates parent directories if needed. Writes to a .tmp file first, then renames for atomicity.
        Wraps OSError into MemoryError.
        """
        if not self.config.memory.enabled:
            return

        path = self.config.memory.file
        try:
            tmp_path = path.with_name(path.name + ".tmp")
            content = json.dumps(
                {"version": 1, "facts": {k: {"value": v.value, "updated_at": v.updated_at} for k, v in self._facts.items()}},
                indent=2,
                sort_keys=True,
            ) + "\n"
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(path)
        except OSError as e:
            raise MemoryError(f"Cannot write memory file {path}: {e}")

    def get(self, key: str) -> str | None:
        """Get the value for a fact key.

        Args:
            key: The fact key to retrieve.

        Returns:
            The fact value, or None if not found or store is disabled.
        """
        if not self.config.memory.enabled:
            return None
        fact = self._facts.get(key)
        return fact.value if fact else None

    def set(self, key: str, value: str) -> None:
        """Set a fact with the given key and value.

        Normalizes key (lowercase, stripped) and value (whitespace normalized).
        Caps value at max_value_chars. Does not auto-save; caller must call save().

        Args:
            key: The fact key.
            value: The fact value.

        Returns:
            None. Raises ValueError if key or value is empty after normalization.
        """
        if not self.config.memory.enabled:
            return

        key = key.strip().lower()
        value = re.sub(r"\s+", " ", value).strip()

        if not key or not value:
            raise ValueError(f"Empty key or value after normalization for key '{key}'")

        max_chars = self.config.memory.max_value_chars
        if len(value) > max_chars:
            value = value[:max_chars]

        self._facts[key] = Fact(key=key, value=value, updated_at=time.time())

        while len(self._facts) > self.config.memory.max_facts:
            oldest_key = min(self._facts.keys(), key=lambda k: self._facts[k].updated_at)
            del self._facts[oldest_key]

    def delete(self, key: str) -> None:
        """Delete a fact by key.

        Args:
            key: The fact key to delete.

        Returns:
            None. No-op if store is disabled or key not found.
        """
        if not self.config.memory.enabled:
            return
        self._facts.pop(key, None)

    def all(self) -> dict[str, str]:
        """Get all facts as a plain mapping.

        Returns:
            A dict mapping keys to values. Empty dict if store is disabled.
        """
        if not self.config.memory.enabled:
            return {}
        return {k: v.value for k, v in self._facts.items()}

    def observe(self, text: str) -> list[Fact]:
        """Extract facts from text using predefined patterns.

        Args:
            text: The text to scan for fact patterns.

        Returns:
            A list of Fact objects that were stored. Empty list if store is disabled or no matches.
        """
        if not self.config.memory.enabled:
            return []

        facts_found: list[Fact] = []
        _OBSERVE_PATTERNS: tuple[tuple[str, str], ...] = (
            (r"\bmy name is\s+([A-Za-z][\w'\- ]{0,59})", "name"),
            (r"\bcall me\s+([A-Za-z][\w'\- ]{0,59})", "name"),
            (r"\bi like\s+([A-Za-z][\w'\- ]{0,59})", "likes"),
            (r"\bi love\s+([A-Za-z][\w'\- ]{0,59})", "likes"),
            (r"\bi (?:hate|dislike)\s+([A-Za-z][\w'\- ]{0,59})", "dislikes"),
            (r"\bmy favou?rite\s+([\w'\- ]{1,40}?)\s+is\s+([A-Za-z][\w'\- ]{0,59})", "favorite"),
            (r"\bremember that\s+([\w'\- ]{1,40}?)\s+is\s+([A-Za-z][\w'\- ]{0,59})", "note"),
        )

        for pattern, key in _OBSERVE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            groups = match.groups()
            if len(groups) == 1:
                value = groups[0]
            else:
                value = f"{groups[0].strip()}: {groups[1].strip()}"

            value = re.split(r"\s+and\b|\s*,|\s+but\b", value, maxsplit=1)[0]
            value = re.sub(r"\s+", " ", value).strip(" '\"")

            if not value:
                continue

            self.set(key, value)
            fact = Fact(key=key, value=self.get(key) or "", updated_at=time.time())
            facts_found.append(fact)

        return facts_found

    def clear(self) -> None:
        """Clear all facts and remove the file.

        Swallows OSError on unlink with a warning log.
        """
        if not self.config.memory.enabled:
            return

        path = self.config.memory.file
        self._facts.clear()
        try:
            if path.exists():
                path.unlink()
        except OSError as e:
            logger.warning(f"Cannot unlink memory file {path}: {e}")


def main() -> None:
    """CLI for the memory store."""
    parser = argparse.ArgumentParser(description="Hideko memory store CLI")
    parser.add_argument("--facts", action="store_true", help="Print all stored facts")
    parser.add_argument("--clear", action="store_true", help="Clear all stored facts")
    args = parser.parse_args()

    from config import load_config

    config = load_config("config.yaml")
    store = MemoryStore(config)

    if args.clear:
        store.clear()
        print("memory cleared")
        sys.exit(0)

    if args.facts:
        facts = store.all()
        if not facts:
            print("(no facts)")
        else:
            for key, value in sorted(facts.items()):
                print(f"{key}: {value}")


if __name__ == "__main__":
    main()
