import uuid

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import authenticate_admin_client


client = authenticate_admin_client(TestClient(app))


def _create_mock_provider(name: str) -> int:
    response = client.post(
        "/admin/providers",
        json={
            "name": name,
            "adapter_type": "mock",
            "status": "active",
            "health_status": "healthy",
            "priority": 777,
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
    assert response.status_code == 200
    return response.json()["id"]


def test_delete_route_rule_removes_rule_from_admin_list():
    suffix = uuid.uuid4().hex[:8]
    provider_id = _create_mock_provider(f"route_delete_provider_{suffix}")
    model_id = f"route-delete-model-{suffix}"

    create_response = client.post(
        "/admin/routes",
        json={
            "model_id": model_id,
            "preferred_provider_id": provider_id,
            "backup_provider_id": None,
            "timeout_ms": 60000,
        },
    )
    assert create_response.status_code == 200
    route_id = create_response.json()["id"]

    delete_response = client.delete(f"/admin/routes/{route_id}")
    assert delete_response.status_code == 204

    list_response = client.get("/admin/routes")
    assert list_response.status_code == 200
    assert all(route["id"] != route_id for route in list_response.json())

    cleanup_response = client.delete(f"/admin/providers/{provider_id}")
    assert cleanup_response.status_code == 204


def test_delete_route_rule_returns_404_for_missing_rule():
    response = client.delete("/admin/routes/999999999")
    assert response.status_code == 404
