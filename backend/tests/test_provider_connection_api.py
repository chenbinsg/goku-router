from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import authenticate_admin_client


client = authenticate_admin_client(TestClient(app))


def test_provider_connection_endpoint_for_mock_provider():
    providers_response = client.get("/admin/providers")
    assert providers_response.status_code == 200
    provider_id = providers_response.json()[0]["id"]

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
    assert payload["provider_name"] == "provider_primary"
    assert payload["completion"]
