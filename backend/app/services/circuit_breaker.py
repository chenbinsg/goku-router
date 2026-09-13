"""
In-memory circuit breaker for provider fault tolerance.

States:
  CLOSED    — normal operation, all requests pass through
  OPEN      — provider tripped, requests rejected immediately
  HALF_OPEN — exactly one probe request allowed to test recovery

Admission is token-based: a caller acquires an ``Admission`` via
``try_acquire``, runs the upstream call, then reports the outcome with that same
token (``record_success`` / ``record_failure``).  The name-only API this
replaced could not guarantee two properties the recovery path depends on:

  * Single probe.  When an OPEN breaker cools down, the FIRST caller to acquire
    takes the one probe slot and moves the breaker to HALF_OPEN; every other
    caller is rejected until that probe resolves.  A probe also carries a
    deadline for accepting a recovery result. An expired probe retains its
    slot until the caller reports or releases it: expiry cannot cancel an
    in-flight synchronous upstream request, so reissuing would overlap calls.

  * No stale overwrite.  Each OPEN transition bumps a generation counter, and an
    Admission captures the generation it was acquired under.  A late result from
    a request that started in an older generation (for example an in-flight call
    from before the breaker tripped) can neither close a freshly-opened breaker
    nor push its cooldown back.

Configuration (via environment variables):
  CB_FAILURE_THRESHOLD  — consecutive failures before OPEN (default: 5)
  CB_RECOVERY_TIMEOUT_S — seconds before OPEN → HALF_OPEN (default: 60)
  CB_PROBE_TIMEOUT_S    — max probe duration accepted as recovery (default: 30)
"""
from __future__ import annotations

import os
import threading
import time
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

_FAILURE_THRESHOLD = int(os.environ.get("CB_FAILURE_THRESHOLD", "5"))
_RECOVERY_TIMEOUT_S = float(os.environ.get("CB_RECOVERY_TIMEOUT_S", "60"))
_PROBE_TIMEOUT_S = float(os.environ.get("CB_PROBE_TIMEOUT_S", "30"))


class CBState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class Admission:
    """Token returned by ``try_acquire``; pass it back to ``record_*``.

    ``generation`` pins the outcome to the breaker state it was admitted under,
    so a stale result cannot flip a newer state.  ``is_probe`` marks the single
    HALF_OPEN recovery probe.
    """
    provider_name: str
    generation: int
    is_probe: bool


@dataclass
class _ProviderBreaker:
    state: CBState = CBState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    opened_at: float = 0.0
    # Bumped on every CLOSED/HALF_OPEN → OPEN transition (and on reset). Any
    # Admission acquired under an earlier value is stale.
    generation: int = 0
    probe_in_flight: bool = False
    probe_deadline: float = 0.0


class CircuitBreakerRegistry:
    """Thread-safe in-process circuit breaker for LLM providers."""

    def __init__(
        self,
        failure_threshold: int = _FAILURE_THRESHOLD,
        recovery_timeout_s: float = _RECOVERY_TIMEOUT_S,
        probe_timeout_s: float = _PROBE_TIMEOUT_S,
    ):
        self._threshold = failure_threshold
        self._timeout = recovery_timeout_s
        self._probe_timeout = probe_timeout_s
        self._breakers: dict[str, _ProviderBreaker] = {}
        self._lock = threading.Lock()

    def _get(self, provider_name: str) -> _ProviderBreaker:
        if provider_name not in self._breakers:
            self._breakers[provider_name] = _ProviderBreaker()
        return self._breakers[provider_name]

    def try_acquire(self, provider_name: str) -> Admission | None:
        """Attempt to admit one request.

        Returns an ``Admission`` to run with, or ``None`` if the circuit is OPEN
        (cooling down) or a HALF_OPEN probe is already in flight.  The single
        probe slot is granted atomically here, so concurrent callers cannot all
        rush an unrecovered upstream at once.
        """
        now = time.monotonic()
        with self._lock:
            cb = self._get(provider_name)

            if cb.state == CBState.CLOSED:
                return Admission(provider_name, cb.generation, is_probe=False)

            if cb.state == CBState.OPEN:
                if now - cb.opened_at >= self._timeout:
                    cb.state = CBState.HALF_OPEN
                    cb.probe_in_flight = True
                    cb.probe_deadline = now + self._probe_timeout
                    logger.info(
                        "Circuit breaker → HALF_OPEN for provider '%s' (probe admitted)",
                        provider_name,
                    )
                    return Admission(provider_name, cb.generation, is_probe=True)
                return None

            # HALF_OPEN: admit exactly one probe at a time.
            if cb.probe_in_flight:
                return None
            # Only re-offer after the previous caller has actually released its slot.
            cb.generation += 1
            cb.probe_in_flight = True
            cb.probe_deadline = now + self._probe_timeout
            logger.info(
                "Circuit breaker re-issued HALF_OPEN probe for provider '%s'",
                provider_name,
            )
            return Admission(provider_name, cb.generation, is_probe=True)

    def record_success(self, admission: Admission) -> None:
        """Report a successful call for a previously acquired admission."""
        with self._lock:
            cb = self._get(admission.provider_name)
            if admission.generation != cb.generation:
                # Stale result from an older generation: do not resurrect a
                # breaker that has since re-opened.
                logger.debug(
                    "Ignoring stale success for '%s' (gen %d != current %d)",
                    admission.provider_name, admission.generation, cb.generation,
                )
                return
            if admission.is_probe and time.monotonic() >= cb.probe_deadline:
                # A late success is insufficient evidence of timely recovery.
                cb.state = CBState.OPEN
                cb.opened_at = time.monotonic()
                cb.generation += 1
                cb.probe_in_flight = False
                return
            was_recovering = cb.state != CBState.CLOSED
            if admission.is_probe:
                cb.generation += 1
            cb.failure_count = 0
            cb.state = CBState.CLOSED
            cb.probe_in_flight = False
            cb.last_success_time = time.monotonic()
            if was_recovering:
                logger.info(
                    "Circuit breaker → CLOSED for provider '%s' (recovered)",
                    admission.provider_name,
                )

    def record_failure(self, admission: Admission) -> None:
        """Report a failed call for a previously acquired admission."""
        now = time.monotonic()
        with self._lock:
            cb = self._get(admission.provider_name)
            if admission.generation != cb.generation:
                # Stale failure from an older generation: don't double-count and
                # don't push back the cooldown of the current OPEN window.
                logger.debug(
                    "Ignoring stale failure for '%s' (gen %d != current %d)",
                    admission.provider_name, admission.generation, cb.generation,
                )
                return

            cb.last_failure_time = now

            if cb.state == CBState.HALF_OPEN:
                # The recovery probe failed — re-open with a fresh generation.
                cb.state = CBState.OPEN
                cb.opened_at = now
                cb.generation += 1
                cb.probe_in_flight = False
                logger.warning(
                    "Circuit breaker → OPEN for provider '%s' (recovery probe failed)",
                    admission.provider_name,
                )
                return

            if cb.state == CBState.CLOSED:
                cb.failure_count += 1
                if cb.failure_count >= self._threshold:
                    cb.state = CBState.OPEN
                    cb.opened_at = now
                    cb.generation += 1
                    logger.warning(
                        "Circuit breaker → OPEN for provider '%s' after %d failures",
                        admission.provider_name, cb.failure_count,
                    )
            # state == OPEN with a matching generation should not occur (no
            # admissions are handed out while OPEN); nothing to do if it does.

    def release(self, admission: Admission) -> None:
        """Return an admission without recording an outcome.

        Used when the caller never actually reached the upstream (for example it
        was throttled by the concurrency limiter): a capacity rejection is not
        evidence about the upstream's health, so it must count as neither success
        nor failure.  If the admission held the HALF_OPEN probe slot, free it so
        the next caller can probe.
        """
        with self._lock:
            cb = self._get(admission.provider_name)
            if admission.generation != cb.generation:
                return
            if admission.is_probe and cb.state == CBState.HALF_OPEN:
                cb.probe_in_flight = False
                cb.generation += 1

    def is_available(self, provider_name: str) -> bool:
        """Advisory, non-mutating check of whether a request could be admitted.

        Kept for callers that only want a peek; the hot path uses
        ``try_acquire`` so the probe slot is granted atomically.
        """
        now = time.monotonic()
        with self._lock:
            cb = self._get(provider_name)
            if cb.state == CBState.CLOSED:
                return True
            if cb.state == CBState.OPEN:
                return now - cb.opened_at >= self._timeout
            # HALF_OPEN: available only if the single probe slot is free.
            return not cb.probe_in_flight

    def get_state(self, provider_name: str) -> CBState:
        with self._lock:
            return self._get(provider_name).state

    def get_all_states(self) -> dict[str, dict]:
        now = time.monotonic()
        with self._lock:
            return {
                name: {
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "generation": cb.generation,
                    "probe_in_flight": cb.probe_in_flight,
                    "last_failure_ago_s": round(now - cb.last_failure_time, 1)
                    if cb.last_failure_time else None,
                    "opened_ago_s": round(now - cb.opened_at, 1)
                    if cb.state != CBState.CLOSED and cb.opened_at else None,
                }
                for name, cb in self._breakers.items()
            }

    def reset(self, provider_name: str) -> None:
        """Manually reset a tripped circuit (admin action).

        Carries the generation forward so any still-in-flight request admitted
        before the reset is treated as stale and cannot flip the fresh state.
        """
        with self._lock:
            previous = self._breakers.get(provider_name)
            next_generation = (previous.generation + 1) if previous else 0
            self._breakers[provider_name] = _ProviderBreaker(generation=next_generation)
            logger.info("Circuit breaker manually RESET for provider '%s'", provider_name)


# Global singleton — shared across all requests in the process
circuit_breakers = CircuitBreakerRegistry()
