"""Tool registry for Hideko.

Tools are named, executable units (timer, file search, etc.) that the turn
flow can invoke after speaking a response. The registry is name-keyed and
thread-safe for concurrent register/execute calls.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResult:
    """Result of tool execution."""
    ok: bool
    text: str | None = None      # text to speak back to the user, if any
    error: str | None = None     # error message, if not ok


class Tool:
    """Base class for Hideko tools.

    Subclass and implement `execute`. `name` is the registration key.
    """

    name: str = "tool"

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with keyword arguments.

        Returns a ToolResult. Never raises — convert exceptions to
        ToolResult(ok=False, error=...).
        """
        raise NotImplementedError


class ToolRegistry:
    """Name-keyed tool registry."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Re-registering the same name replaces it."""
        with self._lock:
            self._tools[tool.name] = tool
            logger.debug("registered tool: %s", tool.name)

    def get(self, name: str) -> Tool | None:
        """Return the tool for `name`, or None if not registered."""
        with self._lock:
            return self._tools.get(name)

    def execute(self, name: str, **kwargs: Any) -> ToolResult:
        """Execute a registered tool by name.

        Returns ToolResult(ok=False) if the tool is not registered or raises.
        Never raises.
        """
        with self._lock:
            tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"unknown tool: {name}")
        try:
            return tool.execute(**kwargs)
        except Exception as exc:  # tool failures must not crash the turn loop
            logger.exception("tool %s raised: %s", name, exc)
            return ToolResult(ok=False, error=str(exc))

    def names(self) -> list[str]:
        """Return sorted registered tool names."""
        with self._lock:
            return sorted(self._tools.keys())
