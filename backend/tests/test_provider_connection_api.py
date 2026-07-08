import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal
from app.main import app
from tests.helpers import authenticate_admin_client


client = authenticate_admin_client(TestClient(app))


def test_provider_connection_endpoint_for_mock_provider():
    suffix = uuid.uuid4().hex[:8]
    create_response = client.post(
        "/admin/providers",
        json={
            "name": f"mock_connection_test_provider_{suffix}",
            "adapter_type": "mock",
            "status": "active",
            "health_status": "healthy",
            "priority": 100,
            "input_cost_per_1k": 0.001,
            "output_cost_per_1k": 0.002,
            "avg_latency_ms": 100,
            "capabilities": ["chat"],
            "supports_zdr": False,
            "data_collection_mode": "allow",
            "supported_parameters": ["temperature", "max_tokens"],
            "max_input_tokens": 4096,
            "max_output_tokens": 2048,
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    response = client.post(
        "/admin/providers/test",
        json={
            "provider_id": provider_id,
            "provider_model_name": "mock-primary-model1",
            "prompt": "Ping provider",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["provider_name"] == f"mock_connection_test_provider_{suffix}"
    assert payload["completion"]


def test_delete_provider_clears_model_catalog_references_from_logs():
    suffix = uuid.uuid4().hex[:8]
    provider_name = f"obsolete_provider_for_delete_test_{suffix}"
    model_name = f"obsolete-delete-test-model-{suffix}"
    request_id = f"obsolete-delete-test-request-{suffix}"
    create_response = client.post(
        "/admin/providers",
        json={
            "name": provider_name,
            "adapter_type": "mock",
            "status": "disabled",
            "health_status": "unhealthy",
            "priority": 999,
            "input_cost_per_1k": 0.001,
            "output_cost_per_1k": 0.002,
            "avg_latency_ms": 1000,
            "capabilities": ["chat"],
            "supports_zdr": False,
            "data_collection_mode": "allow",
            "supported_parameters": ["temperature", "max_tokens"],
            "max_input_tokens": 4096,
            "max_output_tokens": 2048,
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    db = SessionLocal()
    try:
        model = models.ModelCatalog(
            model_id=model_name,
            provider_id=provider_id,
            provider_model_name=model_name,
            status="active",
        )
        db.add(model)
        db.commit()
        db.refresh(model)

        log = models.RequestLog(
            request_id=request_id,
            model_catalog_id=model.id,
            requested_model=model_name,
            resolved_model=model_name,
            provider_name=provider_name,
            status_code=200,
            latency=12.0,
        )
        db.add(log)
        db.add(
            models.ProviderQualityScore(
                provider_name=provider_name,
                workload_class="chat",
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()
        log_id = log.id
    finally:
        db.close()

    delete_response = client.delete(f"/admin/providers/{provider_id}")
    assert delete_response.status_code == 204

    db = SessionLocal()
    try:
        assert db.query(models.Provider).filter(models.Provider.id == provider_id).first() is None
        assert db.query(models.ModelCatalog).filter(models.ModelCatalog.provider_id == provider_id).count() == 0
        retained_log = db.query(models.RequestLog).filter(models.RequestLog.id == log_id).one()
        assert retained_log.model_catalog_id is None
        assert retained_log.provider_name == provider_name
        assert (
            db.query(models.ProviderQualityScore)
            .filter(models.ProviderQualityScore.provider_name == provider_name)
            .count()
            == 0
        )
    finally:
        db.close()


def test_delete_model_catalog_item_clears_request_log_reference():
    suffix = uuid.uuid4().hex[:8]
    provider_name = f"model_delete_provider_{suffix}"
    model_name = f"model-delete-test-{suffix}"
    request_id = f"model-delete-test-request-{suffix}"
    provider_response = client.post(
        "/admin/providers",
        json={
            "name": provider_name,
            "adapter_type": "mock",
            "status": "active",
            "health_status": "healthy",
            "priority": 888,
            "input_cost_per_1k": 0.001,
            "output_cost_per_1k": 0.002,
            "avg_latency_ms": 100,
            "capabilities": ["chat"],
            "supports_zdr": False,
            "data_collection_mode": "allow",
            "supported_parameters": ["temperature", "max_tokens"],
            "max_input_tokens": 4096,
            "max_output_tokens": 2048,
        },
    )
    assert provider_response.status_code == 200
    provider_id = provider_response.json()["id"]
    model_response = client.post(
        "/admin/models",
        json={
            "model_id": model_name,
            "provider_id": provider_id,
            "provider_model_name": model_name,
            "status": "active",
        },
    )
    assert model_response.status_code == 200
    model_id = model_response.json()["id"]

    db = SessionLocal()
    try:
        log = models.RequestLog(
            request_id=request_id,
            model_catalog_id=model_id,
            requested_model=model_name,
            resolved_model=model_name,
            provider_name=provider_name,
            status_code=200,
            latency=3.0,
        )
        db.add(log)
        db.commit()
        log_id = log.id
    finally:
        db.close()

    delete_response = client.delete(f"/admin/models/{model_id}")
    assert delete_response.status_code == 204

    db = SessionLocal()
    try:
        assert db.query(models.ModelCatalog).filter(models.ModelCatalog.id == model_id).first() is None
        retained_log = db.query(models.RequestLog).filter(models.RequestLog.id == log_id).one()
        assert retained_log.model_catalog_id is None
        assert retained_log.provider_name == provider_name
    finally:
        db.close()

    cleanup_response = client.delete(f"/admin/providers/{provider_id}")
    assert cleanup_response.status_code == 204
