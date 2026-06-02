"""
Tests for GET /v1/models/{model_name}/stats  (v1.6.0)
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db import SessionLocal
from app import crud, models

client = TestClient(app)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_log(
    db: Session,
    *,
    requested_model: str,
    status_code: int = 200,
    latency: float = 0.1,
    cost_amount: float = 0.001,
    fallback_used: bool = False,
    provider_name: str = "provider_primary",
    error_code: str | None = None,
):
    import uuid
    row = models.RequestLog(
        request_id=str(uuid.uuid4()),
        requested_model=requested_model,
        status_code=status_code,
        latency=latency,
        cost_amount=cost_amount,
        fallback_used=fallback_used,
        provider_name=provider_name,
        error_code=error_code,
    )
    db.add(row)

    # Also write a BillingRecord so the window filter picks it up
    db.add(models.BillingRecord(
        request_id=row.request_id,
        model=requested_model,
        provider=provider_name,
        cost_usd=cost_amount,
        upstream_cost_usd=cost_amount,
        date=datetime.now(timezone.utc),
    ))
    return row


def _clean(db: Session, model_name: str):
    """Remove test fixtures for a model name."""
    rows = db.query(models.RequestLog).filter(
        models.RequestLog.requested_model == model_name
    ).all()
    request_ids = [r.request_id for r in rows]
    if request_ids:
        db.query(models.BillingRecord).filter(
            models.BillingRecord.request_id.in_(request_ids)
        ).delete(synchronize_session=False)
    db.query(models.RequestLog).filter(
        models.RequestLog.requested_model == model_name
    ).delete(synchronize_session=False)
    db.commit()


# ─── tests ────────────────────────────────────────────────────────────────────

def test_returns_zeros_when_no_data():
    resp = client.get("/v1/models/nonexistent-model-xyz/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_name"] == "nonexistent-model-xyz"
    assert data["total_requests"] == 0
    assert data["success_rate"] == 0.0
    assert data["error_rate"] == 0.0
    assert data["avg_latency_ms"] == 0.0
    assert data["p99_latency_ms"] == 0.0
    assert data["fallback_rate"] == 0.0
    assert data["avg_cost_usd"] == 0.0
    assert data["providers_used"] == []
    assert data["error_breakdown"] == {}


def test_correct_success_rate():
    model = "test-stats-success-rate"
    db = SessionLocal()
    try:
        _clean(db, model)
        # 3 success, 1 error → success_rate = 0.75
        for _ in range(3):
            _make_log(db, requested_model=model, status_code=200)
        _make_log(db, requested_model=model, status_code=500)
        db.commit()

        resp = client.get(f"/v1/models/{model}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 4
        assert data["success_rate"] == 0.75
    finally:
        _clean(db, model)
        db.close()


def test_correct_error_rate():
    model = "test-stats-error-rate"
    db = SessionLocal()
    try:
        _clean(db, model)
        # 1 success, 3 errors → error_rate = 0.75
        _make_log(db, requested_model=model, status_code=200)
        for _ in range(3):
            _make_log(db, requested_model=model, status_code=500)
        db.commit()

        resp = client.get(f"/v1/models/{model}/stats")
        data = resp.json()
        assert data["total_requests"] == 4
        assert data["error_rate"] == 0.75
        assert abs(data["success_rate"] + data["error_rate"] - 1.0) < 1e-9
    finally:
        _clean(db, model)
        db.close()


def test_avg_latency_ms():
    model = "test-stats-latency"
    db = SessionLocal()
    try:
        _clean(db, model)
        # latencies in seconds: 0.1, 0.3 → avg = 0.2 s = 200 ms
        _make_log(db, requested_model=model, latency=0.1)
        _make_log(db, requested_model=model, latency=0.3)
        db.commit()

        resp = client.get(f"/v1/models/{model}/stats")
        data = resp.json()
        assert abs(data["avg_latency_ms"] - 200.0) < 1.0
    finally:
        _clean(db, model)
        db.close()


def test_p99_latency():
    model = "test-stats-p99"
    db = SessionLocal()
    try:
        _clean(db, model)
        # 100 rows: 99 at 0.1 s, 1 at 1.0 s → p99 index = 99th element = 1000 ms
        for _ in range(99):
            _make_log(db, requested_model=model, latency=0.1)
        _make_log(db, requested_model=model, latency=1.0)
        db.commit()

        resp = client.get(f"/v1/models/{model}/stats")
        data = resp.json()
        # p99 of 100 values: idx = int(100 * 0.99) = 99 → sorted[99] = 1000 ms
        assert data["p99_latency_ms"] == 1000.0
    finally:
        _clean(db, model)
        db.close()


def test_fallback_rate():
    model = "test-stats-fallback"
    db = SessionLocal()
    try:
        _clean(db, model)
        # 2 fallback, 2 not → 0.5
        for _ in range(2):
            _make_log(db, requested_model=model, fallback_used=True)
        for _ in range(2):
            _make_log(db, requested_model=model, fallback_used=False)
        db.commit()

        resp = client.get(f"/v1/models/{model}/stats")
        data = resp.json()
        assert data["fallback_rate"] == 0.5
    finally:
        _clean(db, model)
        db.close()


def test_error_breakdown_categorization():
    model = "test-stats-breakdown"
    db = SessionLocal()
    try:
        _clean(db, model)
        _make_log(db, requested_model=model, status_code=429, error_code="rate_limit_exceeded")
        _make_log(db, requested_model=model, status_code=408, error_code="timeout")
        _make_log(db, requested_model=model, status_code=500, error_code="internal_server_error")
        _make_log(db, requested_model=model, status_code=400, error_code="bad_request")
        _make_log(db, requested_model=model, status_code=200)  # success — not in breakdown
        db.commit()

        resp = client.get(f"/v1/models/{model}/stats")
        data = resp.json()
        bd = data["error_breakdown"]
        assert bd.get("rate_limit", 0) >= 1
        assert bd.get("timeout", 0) >= 1
        assert bd.get("server_error", 0) >= 1
        assert bd.get("other", 0) >= 1
    finally:
        _clean(db, model)
        db.close()


def test_providers_used_deduplication():
    model = "test-stats-providers"
    db = SessionLocal()
    try:
        _clean(db, model)
        for _ in range(3):
            _make_log(db, requested_model=model, provider_name="provider_a")
        for _ in range(2):
            _make_log(db, requested_model=model, provider_name="provider_b")
        db.commit()

        resp = client.get(f"/v1/models/{model}/stats")
        data = resp.json()
        assert sorted(data["providers_used"]) == ["provider_a", "provider_b"]
    finally:
        _clean(db, model)
        db.close()


def test_window_days_filter_excludes_old_requests():
    """
    Requests that only appear in BillingRecord with old dates should be excluded
    when window_days=1 but would be included if we just pull all RequestLogs.
    We test this by querying with window_days=1 and checking only the recent
    BillingRecord-backed row is counted (the old one has no matching BillingRecord
    within the window so the billing-based join excludes it).
    """
    model = "test-stats-window"
    db = SessionLocal()
    try:
        _clean(db, model)

        # Add one row with a matching recent BillingRecord
        import uuid
        recent_rid = str(uuid.uuid4())
        db.add(models.RequestLog(
            request_id=recent_rid,
            requested_model=model,
            status_code=200,
            latency=0.1,
            cost_amount=0.001,
            fallback_used=False,
            provider_name="provider_primary",
        ))
        db.add(models.BillingRecord(
            request_id=recent_rid,
            model=model,
            provider="provider_primary",
            cost_usd=0.001,
            upstream_cost_usd=0.001,
            date=datetime.now(timezone.utc),   # recent — within window
        ))

        # Add another row with NO BillingRecord (simulates old/out-of-window data)
        old_rid = str(uuid.uuid4())
        db.add(models.RequestLog(
            request_id=old_rid,
            requested_model=model,
            status_code=200,
            latency=0.5,
            cost_amount=0.002,
            fallback_used=False,
            provider_name="provider_primary",
        ))
        # Intentionally do NOT add a BillingRecord for old_rid

        db.commit()

        resp = client.get(f"/v1/models/{model}/stats", params={"window_days": 1})
        data = resp.json()
        # Only the recent row has a BillingRecord within the window
        assert data["total_requests"] == 1
    finally:
        _clean(db, model)
        db.close()
