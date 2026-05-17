"""
In-memory circuit breaker for provider fault tolerance.

States:
  CLOSED    — normal operation, all requests pass through
  OPEN      — provider tripped, requests rejected immediately
  HALF_OPEN — one probe request allowed to test recovery

Configuration (via environment variables):
  CB_FAILURE_THRESHOLD  — consecutive failures before OPEN (default: 5)
  CB_RECOVERY_TIMEOUT_S — seconds before OPEN → HALF_OPEN (default: 60)
"""
from __future__ import annotations

import os
import threading
import time
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

_FAILURE_THRESHOLD = int(os.environ.get("CB_FAILURE_THRESHOLD", "5"))
_RECOVERY_TIMEOUT_S = float(os.environ.get("CB_RECOVERY_TIMEOUT_S", "60"))


class CBState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ProviderBreaker:
    state: CBState = CBState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    tripped_at: float = 0.0


class CircuitBreakerRegistry:
    """Thread-safe in-process circuit breaker for LLM providers."""

    def __init__(
        self,
        failure_threshold: int = _FAILURE_THRESHOLD,
        recovery_timeout_s: float = _RECOVERY_TIMEOUT_S,
    ):
        self._threshold = failure_threshold
        self._timeout = recovery_timeout_s
        self._breakers: dict[str, _ProviderBreaker] = {}
        self._lock = threading.Lock()

    def _get(self, provider_name: str) -> _ProviderBreaker:
        if provider_name not in self._breakers:
            self._breakers[provider_name] = _ProviderBreaker()
        return self._breakers[provider_name]

    def is_available(self, provider_name: str) -> bool:
        """Return True if the provider circuit allows a request."""
        with self._lock:
            cb = self._get(provider_name)
            if cb.state == CBState.CLOSED:
                return True
            if cb.state == CBState.OPEN:
                if time.monotonic() - cb.last_failure_time >= self._timeout:
                    cb.state = CBState.HALF_OPEN
                    logger.info("Circuit breaker → HALF_OPEN for provider '%s'", provider_name)
                    return True
                return False
            # HALF_OPEN: allow exactly one probe
            return True

    def record_success(self, provider_name: str) -> None:
        """Call after a successful provider response."""
        with self._lock:
            cb = self._get(provider_name)
            was_open = cb.state != CBState.CLOSED
            cb.failure_count = 0
            cb.state = CBState.CLOSED
            cb.last_success_time = time.monotonic()
            if was_open:
                logger.info("Circuit breaker → CLOSED for provider '%s' (recovered)", provider_name)

    def record_failure(self, provider_name: str) -> None:
        """Call after a failed provider response."""
        with self._lock:
            cb = self._get(provider_name)
            cb.failure_count += 1
            cb.last_failure_time = time.monotonic()
            if cb.failure_count >= self._threshold or cb.state == CBState.HALF_OPEN:
                if cb.state != CBState.OPEN:
                    logger.warning(
                        "Circuit breaker → OPEN for provider '%s' after %d failures",
                        provider_name,
                        cb.failure_count,
                    )
                    cb.tripped_at = time.monotonic()
                cb.state = CBState.OPEN

    def get_state(self, provider_name: str) -> CBState:
        with self._lock:
            return self._get(provider_name).state

    def get_all_states(self) -> dict[str, dict]:
        with self._lock:
            return {
                name: {
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "last_failure_ago_s": round(time.monotonic() - cb.last_failure_time, 1)
                    if cb.last_failure_time else None,
                }
                for name, cb in self._breakers.items()
            }

    def reset(self, provider_name: str) -> None:
        """Manually reset a tripped circuit (admin action)."""
        with self._lock:
            self._breakers[provider_name] = _ProviderBreaker()
            logger.info("Circuit breaker manually RESET for provider '%s'", provider_name)


# Global singleton — shared across all requests in the process
circuit_breakers = CircuitBreakerRegistry()
