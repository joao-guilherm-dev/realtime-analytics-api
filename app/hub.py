"""Buffers em memória (ring buffer) + pub/sub assíncrono para WebSocket/SSE."""
import asyncio
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

import numpy as np


class StreamHub:
    WILDCARD = "*"

    def __init__(self, buffer_size: int = 5000) -> None:
        self.buffer_size = buffer_size
        self._buffers: Dict[str, Deque[Tuple[float, float]]] = {}
        self._subs: Dict[str, Set[asyncio.Queue]] = {}

    # ---- buffers
    def load(self, metric: str, rows) -> None:
        self._buffers[metric] = deque(rows, maxlen=self.buffer_size)

    def add(self, metric: str, ts: float, value: float) -> None:
        self._buffers.setdefault(metric, deque(maxlen=self.buffer_size)).append((ts, value))

    def has(self, metric: str) -> bool:
        return metric in self._buffers and len(self._buffers[metric]) > 0

    def metrics(self) -> List[str]:
        return sorted(m for m, b in self._buffers.items() if b)

    def size(self, metric: str) -> int:
        return len(self._buffers.get(metric, ()))

    def last(self, metric: str) -> Optional[Tuple[float, float]]:
        buf = self._buffers.get(metric)
        return buf[-1] if buf else None

    def recent_values(self, metric: str, n: int) -> List[float]:
        buf = self._buffers.get(metric)
        if not buf:
            return []
        return [v for _, v in list(buf)[-n:]]

    def arrays(self, metric: str, limit: Optional[int] = None, since: Optional[float] = None):
        buf = self._buffers.get(metric)
        if not buf:
            return np.array([]), np.array([])
        data = sorted(buf, key=lambda x: x[0])
        if since is not None:
            data = [d for d in data if d[0] >= since]
        if limit:
            data = data[-limit:]
        if not data:
            return np.array([]), np.array([])
        arr = np.array(data, dtype=float)
        return arr[:, 0], arr[:, 1]

    def delete(self, metric: str) -> None:
        self._buffers.pop(metric, None)

    # ---- pub/sub
    def subscribe(self, metric: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.setdefault(metric, set()).add(q)
        return q

    def unsubscribe(self, metric: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(metric)
        if subs:
            subs.discard(q)
            if not subs:
                self._subs.pop(metric, None)

    def publish(self, metric: str, event: dict) -> None:
        for key in (metric, self.WILDCARD):
            for q in list(self._subs.get(key, ())):
                if q.full():  # consumidor lento: descarta o mais antigo
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(event)
