"""Execution time tracking, used to enforce the 120s Analyst Agent cap."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


class ExecutionTimeoutError(Exception):
    pass


@dataclass
class Deadline:
    max_seconds: float
    _start: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        return max(0.0, self.max_seconds - self.elapsed())

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def check(self) -> None:
        if self.remaining() <= 0:
            raise ExecutionTimeoutError(
                f"Execution exceeded max allowed time of {self.max_seconds}s "
                f"(elapsed {self.elapsed():.1f}s)."
            )

    def expired(self) -> bool:
        return self.remaining() <= 0


class Stopwatch:
    """Simple context manager for timing a block, used in logging."""

    def __enter__(self) -> "Stopwatch":
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc_info) -> None:
        self.elapsed_seconds = time.monotonic() - self._start
