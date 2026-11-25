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
                    self._condition.wait()
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
