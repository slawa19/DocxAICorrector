import threading
import time
from pathlib import Path


class AppReadyMarkerWriter:
    def __init__(self, *, path: Path, freshness_window_seconds: float = 15.0, time_fn=None):
        self._path = path
        self._freshness_window_seconds = float(freshness_window_seconds)
        self._time_fn = time_fn or time.time
        self._lock = threading.Lock()
        self._last_write_monotonic = 0.0

    def mark_ready(self) -> bool:
        now = float(self._time_fn())
        with self._lock:
            if self._last_write_monotonic and (now - self._last_write_monotonic) < self._freshness_window_seconds:
                return False
            self._last_write_monotonic = now

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(f"{now:.6f}\n", encoding="utf-8")
        return True
