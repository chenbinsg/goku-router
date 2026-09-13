"""
Per-API-key request rate limiting (requests per minute).

Cumulative quotas (``quota_requests``) cap lifetime volume; they do nothing
about *rate*. A single key running a hot loop — as one test key did, reaching
34k requests — can saturate upstreams and trip every breaker before its lifetime
quota is anywhere near spent. This adds a sliding-window RPM cap so a runaway
client is throttled automatically instead of needing a human to disable the key.

In-process and thread-safe, matching the circuit breaker / concurrency limiter.
The window is a 60-second sliding log per key: accurate for the modest limits
used here, and self-pruning so memory stays bounded by the limit itself.

Caveat (same as the breaker): state is per-process. With multiple workers or
replicas the effective limit is per-process, i.e. N× the configured value. A
shared store (Redis) would be needed for a global limit across replicas.

Configuration:
  RATELIMIT_DEFAULT_RPM — fallback limit for keys with no per-key rpm_limit
                          (env; default 0 = unlimited).
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

_WINDOW_S = 60.0


def default_rpm() -> int:
    try:
        return int(os.environ.get("RATELIMIT_DEFAULT_RPM", "0"))
    except ValueError:
        return 0


class RateLimiter:
    """Sliding-window requests-per-minute limiter keyed by an opaque label."""

    def __init__(self, window_s: float = _WINDOW_S):
        self._window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, label: str, limit_per_min: int | None) -> tuple[bool, float]:
        """Record an attempt and report whether it is allowed.

        Returns ``(allowed, retry_after_s)``. ``retry_after_s`` is 0 when
        allowed, else the seconds until the oldest in-window hit ages out. A
        ``limit_per_min`` of None/<=0 means unlimited (always allowed).
        """
        if not limit_per_min or limit_per_min <= 0:
            return True, 0.0
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            dq = self._hits[label]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit_per_min:
                retry_after = max(0.0, dq[0] + self._window - now)
                return False, retry_after
            dq.append(now)
            return True, 0.0

    def reset(self, label: str | None = None) -> None:
        with self._lock:
            if label is None:
                self._hits.clear()
            else:
                self._hits.pop(label, None)


# Global singleton — shared across all requests in the process
rate_limiter = RateLimiter()
