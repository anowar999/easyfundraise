"""Small in-process caches with a size cap, so a long-running API process never grows without bound."""

import time
from collections import OrderedDict
from threading import Lock
from typing import Any


class BoundedCache:
    """LRU dict with an optional time-to-live. Thread-safe (FastAPI runs sync routes on a thread pool)."""

    def __init__(self, maxsize: int = 1000, ttl: float | None = None):
        self.maxsize, self.ttl = maxsize, ttl
        self._d: OrderedDict = OrderedDict()
        self._lock = Lock()

    def get(self, key, default: Any = None) -> Any:
        with self._lock:
            hit = self._d.get(key)
            if hit is None:
                return default
            exp, val = hit
            if exp is not None and exp < time.monotonic():
                del self._d[key]
                return default
            self._d.move_to_end(key)
            return val

    def __contains__(self, key) -> bool:
        return self.get(key, _MISS) is not _MISS

    def __getitem__(self, key):
        val = self.get(key, _MISS)
        if val is _MISS:
            raise KeyError(key)
        return val

    def __setitem__(self, key, val) -> None:
        with self._lock:
            self._d[key] = (time.monotonic() + self.ttl if self.ttl else None, val)
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def pop(self, key, default: Any = None) -> Any:
        with self._lock:
            hit = self._d.pop(key, None)
        return default if hit is None else hit[1]

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def __len__(self) -> int:
        return len(self._d)


_MISS = object()
