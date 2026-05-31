from fastapi.testclient import TestClient

from app import crud, models
from app.db import SessionLocal, engine


def authenticate_admin_client(client: TestClient) -> TestClient:
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        crud.seed_superadmin(db)
    finally:
        db.close()

    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    client.headers.update(
        {"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    return client
