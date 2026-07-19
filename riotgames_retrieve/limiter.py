import asyncio
import logging
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_limit_header(header_val: str) -> List[Tuple[int, int]]:
    # formats look like '20:1,100:120'
    res = []
    for chunk in header_val.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) == 2:
            try:
                res.append((int(parts[0]), int(parts[1])))
            except ValueError:
                pass
    return res


class RiotRateLimiter:
    """Tracks both app-level and method-level rate limits dynamically."""

    def __init__(self, default_app_limits: Optional[List[Tuple[int, int]]] = None):
        # Riot dev keys default to 20/1s and 100/120s
        self.app_limits = default_app_limits or [(20, 1), (100, 120)]
        self.app_buckets: Dict[int, deque] = {w: deque() for _, w in self.app_limits}
        self.method_buckets: Dict[str, Dict[int, deque]] = {}
        self.method_limits: Dict[str, List[Tuple[int, int]]] = {}
        self._lock = asyncio.Lock()
        self._backoff_until: float = 0.0

    async def acquire(self, method_name: str):
        while True:
            async with self._lock:
                now = time.monotonic()

                # respect explicit 429 Retry-After
                if self._backoff_until > now:
                    wait = self._backoff_until - now
                    # print(f"backing off for {wait:.2f}s")
                    await asyncio.sleep(wait)
                    continue

                max_wait = 0.0

                # check app limit windows
                for max_reqs, window_sec in self.app_limits:
                    q = self.app_buckets.setdefault(window_sec, deque())
                    while q and now - q[0] >= window_sec:
                        q.popleft()
                    if len(q) >= max_reqs:
                        delay = window_sec - (now - q[0]) + 0.02
                        if delay > max_wait:
                            max_wait = delay

                # check method limit windows
                if method_name in self.method_limits:
                    m_buckets = self.method_buckets.setdefault(method_name, {})
                    for max_reqs, window_sec in self.method_limits[method_name]:
                        mq = m_buckets.setdefault(window_sec, deque())
                        while mq and now - mq[0] >= window_sec:
                            mq.popleft()
                        if len(mq) >= max_reqs:
                            delay = window_sec - (now - mq[0]) + 0.02
                            if delay > max_wait:
                                max_wait = delay

                if max_wait <= 0:
                    ts = time.monotonic()
                    for _, w in self.app_limits:
                        self.app_buckets[w].append(ts)
                    if method_name in self.method_limits:
                        for _, w in self.method_limits[method_name]:
                            self.method_buckets[method_name][w].append(ts)
                    return

            # sleep outside lock to avoid blocking other tasks
            await asyncio.sleep(max_wait)

    def update_limits(self, method_name: str, headers: dict):
        # header keys in httpx might be lowercase or capitalized
        raw_app = headers.get("x-app-rate-limit") or headers.get("X-App-Rate-Limit")
        raw_method = headers.get("x-method-rate-limit") or headers.get("X-Method-Rate-Limit")
        retry_after = headers.get("retry-after") or headers.get("Retry-After")

        if retry_after:
            try:
                seconds = float(retry_after)
                # small padding so we don't hit the wall immediately on return
                self._backoff_until = time.monotonic() + seconds + 0.25
                logger.warning("429 hit. Rate limit backoff set for %.2fs", seconds)
            except ValueError:
                pass

        if raw_app:
            parsed = parse_limit_header(raw_app)
            if parsed and parsed != self.app_limits:
                self.app_limits = parsed
                for _, w in parsed:
                    self.app_buckets.setdefault(w, deque())

        if raw_method:
            parsed_m = parse_limit_header(raw_method)
            if parsed_m:
                self.method_limits[method_name] = parsed_m
                m_dict = self.method_buckets.setdefault(method_name, {})
                for _, w in parsed_m:
                    m_dict.setdefault(w, deque())
