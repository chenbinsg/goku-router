"""Traffic timeseries: time-bucketed request counts for the traffic dashboard."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


_seq = [0]


def _log(db, *, minutes_ago, status_code, tokens=10, latency=100.0):
    _seq[0] += 1
    db.add(models.RequestLog(
        request_id=f"r-{_seq[0]}",
        requested_model="m",
        status_code=status_code,
        latency=latency,
        prompt_tokens=tokens,
        completion_tokens=tokens,
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
    ))


def test_buckets_split_success_and_error(db):
    _log(db, minutes_ago=1, status_code=200)
    _log(db, minutes_ago=1, status_code=200)
    _log(db, minutes_ago=1, status_code=500)
    db.commit()

    result = crud.get_traffic_timeseries(db, hours=1, bucket_minutes=5)
    assert result["total_requests"] == 3
    assert result["total_errors"] == 1
    assert result["error_rate"] == round(1 / 3, 4)
    # Buckets are contiguous and cover the window.
    assert result["bucket_minutes"] == 5
    assert len(result["points"]) >= 1
    busy = [p for p in result["points"] if p["total"] > 0]
    assert len(busy) == 1
    assert busy[0]["success"] == 2
    assert busy[0]["error"] == 1
    assert busy[0]["tokens"] == 60  # 3 rows * (10 prompt + 10 completion)


def test_old_rows_outside_window_excluded(db):
    _log(db, minutes_ago=5, status_code=200)      # inside 1h
    _log(db, minutes_ago=120, status_code=200)    # outside 1h
    db.commit()

    result = crud.get_traffic_timeseries(db, hours=1, bucket_minutes=15)
    assert result["total_requests"] == 1


def test_auto_bucket_width_scales_with_window(db):
    db.commit()
    assert crud.get_traffic_timeseries(db, hours=1)["bucket_minutes"] == 1
    assert crud.get_traffic_timeseries(db, hours=24)["bucket_minutes"] == 15
    assert crud.get_traffic_timeseries(db, hours=24 * 7)["bucket_minutes"] == 60


def test_empty_window_is_well_formed(db):
    result = crud.get_traffic_timeseries(db, hours=6)
    assert result["total_requests"] == 0
    assert result["error_rate"] == 0.0
    assert result["peak_rpm"] == 0.0
    assert all(p["total"] == 0 for p in result["points"])
