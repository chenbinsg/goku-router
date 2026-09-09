from fastapi.testclient import TestClient
from app.main import app, get_db

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["db"] == "ok"


def test_health_database_failure():
    class UnavailableDatabase:
        def execute(self, statement):
            raise RuntimeError("Database unavailable")

    app.dependency_overrides[get_db] = lambda: UnavailableDatabase()
    try:
        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["ok"] is False
        assert resp.json()["db"] == "error"
    finally:
        del app.dependency_overrides[get_db]
