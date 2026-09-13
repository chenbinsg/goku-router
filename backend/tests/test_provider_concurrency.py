"""Per-provider concurrency limiter: capacity cap, bounded queue, timeout."""
import threading
import time

import pytest

from app.services import concurrency as conc_mod
from app.services.concurrency import (
    ProviderConcurrencyRegistry,
    ProviderCapacityError,
    _GateConfig,
    _ProviderGate,
)


def _registry_with(monkeypatch, cfg: _GateConfig) -> ProviderConcurrencyRegistry:
    monkeypatch.setattr(conc_mod, "_load_config", lambda name: cfg)
    return ProviderConcurrencyRegistry()


def test_disabled_by_default_is_unlimited(monkeypatch):
    reg = _registry_with(monkeypatch, _GateConfig(0, 0, 0.0))
    # Many acquires without release must all pass (no limit).
    for _ in range(50):
        reg.acquire("p")
    assert reg.get_all_stats()["p"]["enabled"] is False


def test_rejects_immediately_when_full_and_no_queue(monkeypatch):
    reg = _registry_with(monkeypatch, _GateConfig(max_concurrency=2, max_queue=0, acquire_timeout_s=1.0))
    reg.acquire("p")
    reg.acquire("p")
    with pytest.raises(ProviderCapacityError):
        reg.acquire("p")
    stats = reg.get_all_stats()["p"]
    assert stats["active"] == 2
    assert stats["rejected_total"] == 1


def test_release_frees_a_slot(monkeypatch):
    reg = _registry_with(monkeypatch, _GateConfig(max_concurrency=1, max_queue=0, acquire_timeout_s=0.5))
    reg.acquire("p")
    with pytest.raises(ProviderCapacityError):
        reg.acquire("p")
    reg.release("p")
    reg.acquire("p")  # now succeeds
    assert reg.get_all_stats()["p"]["active"] == 1


def test_queued_waiter_is_admitted_when_slot_frees(monkeypatch):
    reg = _registry_with(monkeypatch, _GateConfig(max_concurrency=1, max_queue=1, acquire_timeout_s=5.0))
    reg.acquire("p")  # occupies the only slot

    admitted = threading.Event()

    def waiter():
        reg.acquire("p")  # should block, then succeed once we release
        admitted.set()

    t = threading.Thread(target=waiter)
    t.start()
    # Give the waiter time to park in the queue.
    for _ in range(100):
        if reg.get_all_stats()["p"]["waiting"] == 1:
            break
        time.sleep(0.005)
    assert reg.get_all_stats()["p"]["waiting"] == 1
    assert not admitted.is_set()

    reg.release("p")  # wake the waiter
    assert admitted.wait(timeout=2.0)
    t.join(timeout=2.0)
    assert reg.get_all_stats()["p"]["active"] == 1


def test_queue_full_rejects_third_request(monkeypatch):
    reg = _registry_with(monkeypatch, _GateConfig(max_concurrency=1, max_queue=1, acquire_timeout_s=5.0))
    reg.acquire("p")  # active slot taken

    def waiter():
        try:
            reg.acquire("p")
        except ProviderCapacityError:
            pass

    t = threading.Thread(target=waiter)  # fills the single queue slot
    t.start()
    for _ in range(100):
        if reg.get_all_stats()["p"]["waiting"] == 1:
            break
        time.sleep(0.005)
    assert reg.get_all_stats()["p"]["waiting"] == 1

    # Queue is full (1 active + 1 waiting) → the next acquire is rejected fast.
    with pytest.raises(ProviderCapacityError):
        reg.acquire("p")

    reg.release("p")
    t.join(timeout=2.0)


def test_wait_times_out_when_no_slot_frees(monkeypatch):
    reg = _registry_with(monkeypatch, _GateConfig(max_concurrency=1, max_queue=2, acquire_timeout_s=0.1))
    reg.acquire("p")  # hold the slot, never release
    started = time.monotonic()
    with pytest.raises(ProviderCapacityError):
        reg.acquire("p")  # waits ~0.1s then gives up
    elapsed = time.monotonic() - started
    assert elapsed >= 0.1
    assert reg.get_all_stats()["p"]["waiting"] == 0  # cleaned up on timeout


def test_config_precedence_per_provider_over_global(monkeypatch):
    from app.config import get_provider_int_setting

    monkeypatch.setenv("PROVIDER_MAX_CONCURRENCY", "10")          # global default
    monkeypatch.setenv("PROVIDER_TOKYO_QWEN_MAX_CONCURRENCY", "3")  # per-provider
    assert get_provider_int_setting(
        "TOKYO_QWEN", "MAX_CONCURRENCY", default=0, global_key="PROVIDER_MAX_CONCURRENCY"
    ) == 3
    # A provider without its own key falls back to the global default.
    assert get_provider_int_setting(
        "other", "MAX_CONCURRENCY", default=0, global_key="PROVIDER_MAX_CONCURRENCY"
    ) == 10
    # No env at all → hard-coded default.
    monkeypatch.delenv("PROVIDER_MAX_CONCURRENCY", raising=False)
    assert get_provider_int_setting(
        "other", "MAX_CONCURRENCY", default=0, global_key="PROVIDER_MAX_CONCURRENCY"
    ) == 0


def test_capacity_rejection_surfaces_without_tripping_breaker(monkeypatch):
    """A throttle must fail over (ProviderExecutionError) but not open the breaker."""
    from app.models import ModelCatalog, Provider
    from app import schemas
    from app.services import providers
    from app.services.circuit_breaker import circuit_breakers, CBState

    # Force the singleton gate to a single busy slot for this provider.
    monkeypatch.setattr(
        conc_mod, "_load_config",
        lambda name: _GateConfig(max_concurrency=1, max_queue=0, acquire_timeout_s=0.0),
    )
    providers.provider_concurrency.reload("capacity_test")
    providers.provider_concurrency.acquire("capacity_test")  # occupy the only slot
    circuit_breakers.reset("capacity_test")

    provider = Provider(
        name="capacity_test", adapter_type="mock", status="active",
        health_status="healthy", priority=10,
    )
    model = ModelCatalog(
        model_id="m", provider_id=1, provider_model_name="m", status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="m", messages=[schemas.ChatMessage(role="user", content="hi")],
    )

    with pytest.raises(providers.ProviderExecutionError):
        providers.execute_chat_completion(provider, model, request)

    # The breaker must stay CLOSED — a local throttle is not an upstream failure.
    assert circuit_breakers.get_state("capacity_test") == CBState.CLOSED
    providers.provider_concurrency.release("capacity_test")


def test_reload_rebuilds_idle_gate(monkeypatch):
    cfg_holder = {"cfg": _GateConfig(max_concurrency=1, max_queue=0, acquire_timeout_s=0.1)}
    monkeypatch.setattr(conc_mod, "_load_config", lambda name: cfg_holder["cfg"])
    reg = ProviderConcurrencyRegistry()
    reg.acquire("p")
    reg.release("p")  # idle now
    cfg_holder["cfg"] = _GateConfig(max_concurrency=5, max_queue=0, acquire_timeout_s=0.1)
    reg.reload("p")
    for _ in range(5):
        reg.acquire("p")  # new limit in effect
    assert reg.get_all_stats()["p"]["max_concurrency"] == 5
