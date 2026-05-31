from fastapi.testclient import TestClient
import uuid

from app.main import app
from tests.helpers import authenticate_admin_client


client = authenticate_admin_client(TestClient(app))


def test_models_catalog_is_public():
    response = client.get("/v1/models")
    assert response.status_code == 200


def test_admin_routes_require_jwt():
    response = TestClient(app).get("/admin/organizations")
    assert response.status_code == 401


def test_models_accepts_bearer_api_key():
    response = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer demo-router-key"},
    )
    assert response.status_code == 200
    assert "models" in response.json()


def test_models_accept_db_backed_router_api_key():
    suffix = uuid.uuid4().hex[:8]
    org_response = client.post("/admin/organizations", json={"name": f"Customer Org {suffix}"})
    assert org_response.status_code == 200
    project_response = client.post(
        "/admin/projects",
        json={"name": f"Customer Project {suffix}", "organization_id": org_response.json()["id"]},
    )
    assert project_response.status_code == 200

    create_response = client.post(
        "/admin/router-api-keys",
        json={
            "name": f"customer-a-{suffix}",
            "organization_id": org_response.json()["id"],
            "project_id": project_response.json()["id"],
            "quota_requests": 5,
        },
    )
    assert create_response.status_code == 200
    plain_api_key = create_response.json()["plain_api_key"]

    response = client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {plain_api_key}"},
    )
    assert response.status_code == 200
    assert "models" in response.json()
