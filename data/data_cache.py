import time
from typing import Any, Optional


class TTLCache:
    """Basit TTL tabanlı bellek cache."""

    def __init__(self, default_ttl: float = 300.0):
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[Any, float]] = {}

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        expiry = time.monotonic() + (ttl if ttl is not None else self.default_ttl)
        self._store[key] = (value, expiry)

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.monotonic() > expiry:
            del self._store[key]
            return None
        return value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def has(self, key: str) -> bool:
        return self.get(key) is not None
