"""A cap on how often a metered service may be called."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from wayfinder.core.errors import RateLimited


class SlidingWindowLimiter:
    """At most `max_calls` in any `window` seconds."""

    def __init__(
        self,
        max_calls: int,
        window: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_calls
        self._window = window
        self._clock = clock  # injectable so the behavior can be checked without waiting
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Record a call, or raise RateLimited saying how long to wait."""
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0] >= self._window:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                wait = self._window - (now - self._calls[0])
                raise RateLimited(
                    f"too many model calls: the limit is {self._max} per {self._window:g}s. "
                    f"Try again in {wait:.0f}s.",
                    retry_after=wait,
                )
            self._calls.append(now)
