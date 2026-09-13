"""Per-key RPM rate limiter: sliding window, retry-after, unlimited passthrough."""
from app.services import rate_limit as rl_mod
from app.services.rate_limit import RateLimiter


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def advance(self, s):
        self.now += s

    def __call__(self):
        return self.now


def _limiter(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(rl_mod.time, "monotonic", clock)
    return RateLimiter(window_s=60.0), clock


def test_unlimited_when_no_limit(monkeypatch):
    lim, _ = _limiter(monkeypatch)
    for _ in range(1000):
        allowed, _ra = lim.check("k", None)
        assert allowed
    for _ in range(1000):
        allowed, _ra = lim.check("k", 0)
        assert allowed


def test_blocks_over_limit_within_window(monkeypatch):
    lim, _ = _limiter(monkeypatch)
    assert lim.check("k", 2)[0] is True
    assert lim.check("k", 2)[0] is True
    allowed, retry_after = lim.check("k", 2)
    assert allowed is False
    assert 0 < retry_after <= 60


def test_window_slides_and_frees_capacity(monkeypatch):
    lim, clock = _limiter(monkeypatch)
    assert lim.check("k", 2)[0] is True
    assert lim.check("k", 2)[0] is True
    assert lim.check("k", 2)[0] is False
    clock.advance(61)  # both hits age out of the 60s window
    assert lim.check("k", 2)[0] is True


def test_retry_after_counts_down_to_oldest_hit(monkeypatch):
    lim, clock = _limiter(monkeypatch)
    lim.check("k", 1)          # hit at t=0
    clock.advance(20)
    allowed, retry_after = lim.check("k", 1)   # blocked; oldest ages out in 40s
    assert allowed is False
    assert abs(retry_after - 40.0) < 0.001


def test_limits_are_per_label(monkeypatch):
    lim, _ = _limiter(monkeypatch)
    assert lim.check("a", 1)[0] is True
    assert lim.check("b", 1)[0] is True   # different key, own budget
    assert lim.check("a", 1)[0] is False


def test_reset(monkeypatch):
    lim, _ = _limiter(monkeypatch)
    assert lim.check("k", 1)[0] is True
    assert lim.check("k", 1)[0] is False
    lim.reset("k")
    assert lim.check("k", 1)[0] is True


def test_default_rpm_env(monkeypatch):
    monkeypatch.setenv("RATELIMIT_DEFAULT_RPM", "120")
    assert rl_mod.default_rpm() == 120
    monkeypatch.delenv("RATELIMIT_DEFAULT_RPM", raising=False)
    assert rl_mod.default_rpm() == 0
    monkeypatch.setenv("RATELIMIT_DEFAULT_RPM", "not-an-int")
    assert rl_mod.default_rpm() == 0
