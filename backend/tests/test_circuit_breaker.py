"""Circuit breaker: single-probe recovery and stale-result protection."""
from app.services import circuit_breaker as cb_mod
from app.services.circuit_breaker import CBState, CircuitBreakerRegistry


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


def _registry(monkeypatch, *, threshold=3, recovery=60.0, probe=30.0):
    clock = FakeClock()
    monkeypatch.setattr(cb_mod.time, "monotonic", clock)
    reg = CircuitBreakerRegistry(
        failure_threshold=threshold, recovery_timeout_s=recovery, probe_timeout_s=probe
    )
    return reg, clock


def _trip(reg, name="p", n=3):
    """Drive the breaker OPEN via n consecutive failures."""
    for _ in range(n):
        adm = reg.try_acquire(name)
        assert adm is not None
        reg.record_failure(adm)


def test_closed_admits_and_success_stays_closed(monkeypatch):
    reg, _ = _registry(monkeypatch)
    adm = reg.try_acquire("p")
    assert adm is not None and not adm.is_probe
    reg.record_success(adm)
    assert reg.get_state("p") == CBState.CLOSED


def test_failures_to_threshold_open_and_reject(monkeypatch):
    reg, _ = _registry(monkeypatch, threshold=3)
    _trip(reg, n=3)
    assert reg.get_state("p") == CBState.OPEN
    # OPEN rejects immediately.
    assert reg.try_acquire("p") is None


def test_open_rejects_until_timeout_then_single_probe(monkeypatch):
    reg, clock = _registry(monkeypatch, threshold=3, recovery=60.0)
    _trip(reg, n=3)

    clock.advance(59.0)
    assert reg.try_acquire("p") is None  # still cooling down

    clock.advance(2.0)  # past the 60s window
    probe = reg.try_acquire("p")
    assert probe is not None and probe.is_probe
    assert reg.get_state("p") == CBState.HALF_OPEN
    # Only ONE probe: a concurrent second caller is rejected.
    assert reg.try_acquire("p") is None


def test_probe_success_closes(monkeypatch):
    reg, clock = _registry(monkeypatch, threshold=3, recovery=60.0)
    _trip(reg, n=3)
    clock.advance(61.0)
    probe = reg.try_acquire("p")
    reg.record_success(probe)
    assert reg.get_state("p") == CBState.CLOSED
    assert reg.try_acquire("p") is not None


def test_probe_failure_reopens_with_new_generation(monkeypatch):
    reg, clock = _registry(monkeypatch, threshold=3, recovery=60.0)
    _trip(reg, n=3)
    gen_open = reg.get_all_states()["p"]["generation"]
    clock.advance(61.0)
    probe = reg.try_acquire("p")
    reg.record_failure(probe)
    assert reg.get_state("p") == CBState.OPEN
    assert reg.get_all_states()["p"]["generation"] == gen_open + 1
    # Cools down from the new opened_at, not the old one.
    assert reg.try_acquire("p") is None


def test_stale_success_does_not_close_reopened_breaker(monkeypatch):
    """A late success from before the breaker tripped must not resurrect it."""
    reg, _ = _registry(monkeypatch, threshold=3)
    # An old in-flight request admitted while CLOSED (generation 0).
    stale = reg.try_acquire("p")
    assert stale.generation == 0
    # Meanwhile the breaker trips on other failures.
    _trip(reg, n=3)
    assert reg.get_state("p") == CBState.OPEN
    # The stale request finally succeeds — must be ignored.
    reg.record_success(stale)
    assert reg.get_state("p") == CBState.OPEN


def test_stale_failure_does_not_push_cooldown(monkeypatch):
    reg, clock = _registry(monkeypatch, threshold=3, recovery=60.0)
    stale = reg.try_acquire("p")  # generation 0, still "in flight"
    _trip(reg, n=3)              # opens; generation now 1
    clock.advance(30.0)
    reg.record_failure(stale)    # stale gen-0 failure: must not reset the timer
    clock.advance(31.0)          # 61s total since opened_at
    assert reg.try_acquire("p") is not None  # probe admitted on schedule


def test_abandoned_probe_reoffered_after_deadline(monkeypatch):
    reg, clock = _registry(monkeypatch, threshold=3, recovery=60.0, probe=30.0)
    _trip(reg, n=3)
    clock.advance(61.0)
    first = reg.try_acquire("p")   # takes the probe slot, never reports
    assert first is not None and first.is_probe
    assert reg.try_acquire("p") is None  # slot held
    clock.advance(31.0)            # probe deadline (30s) lapsed
    second = reg.try_acquire("p")
    assert second is not None and second.is_probe


def test_reset_clears_state_and_invalidates_inflight(monkeypatch):
    reg, _ = _registry(monkeypatch, threshold=3)
    stale = reg.try_acquire("p")   # generation 0
    _trip(reg, n=3)                # open
    reg.reset("p")
    assert reg.get_state("p") == CBState.CLOSED
    # A pre-reset admission is now stale and cannot flip the fresh breaker.
    reg.record_failure(stale)
    assert reg.get_state("p") == CBState.CLOSED


def test_is_available_is_non_mutating(monkeypatch):
    reg, clock = _registry(monkeypatch, threshold=3, recovery=60.0)
    _trip(reg, n=3)
    clock.advance(61.0)
    assert reg.is_available("p") is True          # cooldown elapsed
    assert reg.get_state("p") == CBState.OPEN      # but state unchanged (no probe taken)
    # try_acquire is what actually transitions to HALF_OPEN.
    reg.try_acquire("p")
    assert reg.get_state("p") == CBState.HALF_OPEN
