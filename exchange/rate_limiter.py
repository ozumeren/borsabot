import asyncio
import time
from collections import deque


class RateLimiter:
    """Token-bucket benzeri rate limiter (sync + async destekli)."""

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self._calls: deque = deque()
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    def _cleanup(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.period:
            self._calls.popleft()

    def acquire(self) -> None:
        """Sync mod için bekleme."""
        while True:
            self._cleanup()
            if len(self._calls) < self.max_calls:
                self._calls.append(time.monotonic())
                return
            sleep_time = self.period - (time.monotonic() - self._calls[0])
            time.sleep(max(0, sleep_time))

    async def acquire_async(self) -> None:
        """Async mod için bekleme."""
        while True:
            self._cleanup()
            if len(self._calls) < self.max_calls:
                self._calls.append(time.monotonic())
                return
            sleep_time = self.period - (time.monotonic() - self._calls[0])
            await asyncio.sleep(max(0, sleep_time))

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        pass
