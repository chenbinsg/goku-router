"""
Per-provider concurrency limiting with a bounded wait queue.

The circuit breaker is *reactive* — it only protects an upstream after failures
have already happened.  This gate is *proactive*: it caps how many requests may
be in flight to a single provider at once, so a burst cannot pile onto an
upstream and drive it into the timeouts/502s that trip the breaker in the first
place.

Model (FastAPI sync endpoints run in a threadpool, so this is thread-based):

  * ``max_concurrency`` requests run against a provider at once.
  * Up to ``max_queue`` further requests WAIT for a slot, each for at most
    ``acquire_timeout_s`` seconds.
  * Anything beyond that — queue full, or the wait times out — raises
    ``ProviderCapacityError`` immediately.  The caller (the routing loop) then
    fails over to the next candidate, and only returns backpressure to the
    client when every candidate is saturated.

Configuration (env; per-provider key wins over the global default):
  PROVIDER_<NAME>_MAX_CONCURRENCY / PROVIDER_MAX_CONCURRENCY   (default 0 = off)
  PROVIDER_<NAME>_MAX_QUEUE       / PROVIDER_MAX_QUEUE          (default 0)
  PROVIDER_<NAME>_ACQUIRE_TIMEOUT_S / PROVIDER_ACQUIRE_TIMEOUT_S (default 0.0)

Defaults are deliberately OFF (``max_concurrency <= 0`` means unlimited) so
enabling the limiter is an explicit, per-provider opt-in with no behaviour
change on deploy.
"""
from __future__ import annotations

import threading
import time
import logging
from dataclasses import dataclass, field

from ..config import get_provider_int_setting, get_provider_float_setting

logger = logging.getLogger(__name__)


class ProviderCapacityError(Exception):
    """Raised when a provider's concurrency limit (and its queue) is saturated."""


@dataclass
class _GateConfig:
    max_concurrency: int
    max_queue: int
    acquire_timeout_s: float


def _load_config(provider_name: str) -> _GateConfig:
    return _GateConfig(
        max_concurrency=get_provider_int_setting(
            provider_name, "MAX_CONCURRENCY", default=0,
            global_key="PROVIDER_MAX_CONCURRENCY",
        ),
        max_queue=get_provider_int_setting(
            provider_name, "MAX_QUEUE", default=0,
            global_key="PROVIDER_MAX_QUEUE",
        ),
        acquire_timeout_s=get_provider_float_setting(
            provider_name, "ACQUIRE_TIMEOUT_S", default=0.0,
            global_key="PROVIDER_ACQUIRE_TIMEOUT_S",
        ),
    )


@dataclass
class _ProviderGate:
    config: _GateConfig
    cond: threading.Condition = field(default_factory=threading.Condition)
    active: int = 0        # requests currently running against the upstream
    waiting: int = 0       # requests parked, waiting for a slot
    rejected: int = 0      # cumulative rejections (capacity/timeout), for metrics

    def acquire(self, provider_name: str) -> None:
        cfg = self.config
        if cfg.max_concurrency <= 0:
            return  # limiter disabled for this provider

        with self.cond:
            if self.active < cfg.max_concurrency:
                self.active += 1
                return

            # At capacity — can we queue?
            if self.waiting >= cfg.max_queue:
                self.rejected += 1
                raise ProviderCapacityError(
                    f"Provider {provider_name} at capacity "
                    f"({self.active}/{cfg.max_concurrency} active, "
                    f"{self.waiting}/{cfg.max_queue} queued)"
                )

            self.waiting += 1
            deadline = time.monotonic() + cfg.acquire_timeout_s
            try:
                while self.active >= cfg.max_concurrency:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self.rejected += 1
                        raise ProviderCapacityError(
                            f"Provider {provider_name} slot wait timed out after "
                            f"{cfg.acquire_timeout_s:g}s"
                        )
                    self.cond.wait(timeout=remaining)
                self.active += 1
            finally:
                self.waiting -= 1

    def release(self) -> None:
        if self.config.max_concurrency <= 0:
            return
        with self.cond:
            if self.active > 0:
                self.active -= 1
            self.cond.notify()

    def stats(self) -> dict:
        with self.cond:
            return {
                "max_concurrency": self.config.max_concurrency,
                "max_queue": self.config.max_queue,
                "acquire_timeout_s": self.config.acquire_timeout_s,
                "active": self.active,
                "waiting": self.waiting,
                "rejected_total": self.rejected,
                "enabled": self.config.max_concurrency > 0,
            }


class ProviderConcurrencyRegistry:
    """Thread-safe registry of per-provider concurrency gates."""

    def __init__(self):
        self._gates: dict[str, _ProviderGate] = {}
        self._lock = threading.Lock()

    def _gate(self, provider_name: str) -> _ProviderGate:
        with self._lock:
            gate = self._gates.get(provider_name)
            if gate is None:
                gate = _ProviderGate(config=_load_config(provider_name))
                self._gates[provider_name] = gate
            return gate

    def acquire(self, provider_name: str) -> None:
        """Reserve a slot, blocking within limits. Raises ProviderCapacityError."""
        self._gate(provider_name).acquire(provider_name)

    def release(self, provider_name: str) -> None:
        gate = self._gates.get(provider_name)
        if gate is not None:
            gate.release()

    def reload(self, provider_name: str | None = None) -> None:
        """Re-read config from the environment (admin/testing).

        With no name, drops every cached gate so all are rebuilt on next use.
        Gates with in-flight requests are left untouched to avoid losing the
        active count.
        """
        with self._lock:
            if provider_name is None:
                self._gates = {
                    name: gate for name, gate in self._gates.items() if gate.active or gate.waiting
                }
                return
            gate = self._gates.get(provider_name)
            if gate is not None and not gate.active and not gate.waiting:
                del self._gates[provider_name]

    def get_all_stats(self) -> dict[str, dict]:
        with self._lock:
            gates = list(self._gates.items())
        return {name: gate.stats() for name, gate in gates}


# Global singleton — shared across all requests in the process
provider_concurrency = ProviderConcurrencyRegistry()
