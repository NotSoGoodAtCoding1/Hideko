# Task 02 — Tool registry & scheduler

**Depends on task 01. Touch at most 3 files.** Do not touch `main.py`, `response_handler.py`, or `config.yaml`.

## Goal

Create the `tools/` package: a `Tool` base class, a `ToolRegistry` for name-based tool lookup and execution, and a `Scheduler` that runs delayed callbacks on a background thread. Nothing is wired into the turn loop yet — that is task 03.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Standard library only (`heapq`, `threading`, `time`, `uuid`, `dataclasses`, `logging`, `typing`, `collections.abc`).
- No `print()` in library code outside `__main__`. Log with `logging.getLogger(__name__)`.
- `python -m pytest -q` passes offline with no mic/server.
- `Scheduler` callbacks must never crash the background thread: wrap in try/except, log, continue.
- Importing `tools.scheduler` must never start a thread. Threads start only on `Scheduler.start()`.

## Exact code to create — `tools/__init__.py`

Empty file (or with a one-line docstring). Makes `tools` a package.

## Exact code to create — `tools/registry.py`

```python
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
```

## Exact code to create — `tools/scheduler.py`

```python
"""Background delayed-scheduler for Hideko tools.

Runs delayed callbacks on a single daemon thread. Used by tools such as the
timer to fire actions (publish bus events, speak text) while the voice loop is
blocked on the microphone or TTS playback. Importing this module never starts
a thread; call `Scheduler.start()` to begin.
"""
from __future__ import annotations

import heapq
import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from events import EventBus

logger = logging.getLogger(__name__)


class Scheduler:
    """Thread-safe delayed callback scheduler."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._lock = threading.Lock()
        self._heap: list[tuple[float, str, Callable[[], None]]] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._condition = threading.Condition(self._lock)

    def start(self) -> None:
        """Start the background scheduler thread. Idempotent."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="hideko-scheduler", daemon=True)
            self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        """Stop the background thread and wait for it to exit."""
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None

    def schedule(self, callback: Callable[[], None], delay_seconds: float) -> str:
        """Schedule `callback` to run after `delay_seconds`. Returns a job id."""
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        run_at = time.monotonic() + delay_seconds
        job_id = uuid.uuid4().hex
        with self._condition:
            heapq.heappush(self._heap, (run_at, job_id, callback))
            self._condition.notify_all()
        logger.debug("scheduled job %s in %.1fs", job_id, delay_seconds)
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job by id. Returns True if a pending job was removed."""
        with self._condition:
            for i, (run_at, jid, callback) in enumerate(self._heap):
                if jid == job_id:
                    self._heap.pop(i)
                    heapq.heapify(self._heap)
                    self._condition.notify_all()
                    logger.debug("cancelled job %s", job_id)
                    return True
        return False

    def pending(self) -> list[str]:
        """Return job ids of jobs not yet fired."""
        with self._lock:
            return [jid for _, jid, _ in self._heap]

    def _run(self) -> None:
        """Background thread loop: wait for next due job, execute it."""
        while not self._stop.is_set():
            with self._condition:
                if not self._heap:
                    # Wait for a new job or stop.
                    self._condition.wait(timeout=0.5)
                    continue
                run_at = self._heap[0][0]
                now = time.monotonic()
                if run_at > now:
                    self._condition.wait(timeout=run_at - now)
                    continue
                # Job is due: pop and execute outside the lock.
                _, _, callback = heapq.heappop(self._heap)
            try:
                callback()
            except Exception as exc:  # a callback must never kill the scheduler thread
                logger.exception("scheduler callback failed: %s", exc)

    # Context-manager convenience
    def __enter__(self) -> "Scheduler":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
```

## Tests — create `tests/test_tools.py`

- `test_tool_result_ok` / `test_tool_result_error` — construct ToolResult directly.
- `test_register_and_get` — register a dummy Tool, `get(name)` returns it, `get("missing")` is None.
- `test_register_replaces` — register two tools with same name, `get` returns the second.
- `test_execute_unknown_tool` — `execute("no_such_tool")` returns `ok=False` with an error message.
- `test_execute_tool_raises_returns_error` — dummy tool whose `execute` raises; registry returns `ok=False`, never propagates.
- `test_names_sorted` — register tools "b", "a", "c"; `names()` returns `["a", "b", "c"]`.
- `test_scheduler_start_stop_idempotent` — start twice, stop once; thread alive after start, not after stop.
- `test_scheduler_fires_callback` — schedule a callback that sets an event after 0.05s; start scheduler; wait on event; assert fired within 1s. Stop scheduler.
- `test_scheduler_cancel_pending` — schedule a job with a long delay, cancel it, fire remaining jobs, assert cancelled job did not run.
- `test_scheduler_callback_exception_isolated` — one callback raises, a second scheduled callback still runs.
- `test_scheduler_no_thread_on_import` — after `import tools.scheduler`, no scheduler thread is running (check `threading.enumerate()`).

Use `threading.Event` for waits, not `sleep`. Keep each test under 2 seconds.

## Verification

```powershell
python -m pytest -q
python -m pytest -q tests/test_tools.py -v
```

Expected: all tests pass.

## Stop and ask the human if

- A test needs a sleep longer than 2 seconds — simplify it and report instead.
- You want `Scheduler` to be a context manager by default — it already is (`__enter__`/`__exit__`).
