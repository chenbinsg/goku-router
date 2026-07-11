from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import _mask_environment_value, get_startup_environment_snapshot
from app.main import app, require_superadmin, system_environment
from app.services.auth import create_access_token
from tests.helpers import authenticate_admin_client


def _request(role: str):
    return SimpleNamespace(
        state=SimpleNamespace(
            admin_user_id=1,
            admin_username="tester",
            admin_role=role,
        )
    )


def test_startup_environment_masks_all_secret_values():
    snapshot = get_startup_environment_snapshot()

    assert snapshot["startup_time"]
    assert snapshot["items"]
    for item in snapshot["items"]:
        if item["sensitive"] and item["value"]:
            assert "configured" in item["value"] or "••••" in item["value"]


def test_database_url_password_is_redacted():
    value, sensitive = _mask_environment_value(
        "DATABASE_URL",
        "mysql+pymysql://router:real-password@mysql:3306/router",
    )

    assert sensitive is True
    assert "real-password" not in value
    assert "router:••••@mysql:3306/router" in value


def test_environment_endpoint_is_superadmin_only():
    result = system_environment(require_superadmin(_request("superadmin")))
    assert result["items"]

    with pytest.raises(HTTPException) as exc_info:
        require_superadmin(_request("admin"))
    assert exc_info.value.status_code == 403


def test_environment_http_endpoint_enforces_role_and_returns_snapshot():
    superadmin_client = authenticate_admin_client(TestClient(app))
    response = superadmin_client.get("/admin/system/environment")
    assert response.status_code == 200
    assert response.json()["items"]

    admin_token = create_access_token(999, "limited-admin", "admin")
    forbidden = TestClient(app).get(
        "/admin/system/environment",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert forbidden.status_code == 403
