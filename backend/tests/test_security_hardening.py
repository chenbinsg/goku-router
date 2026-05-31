import os
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ROUTER_SECRET_KEY", Fernet.generate_key().decode())

from app import crud, models, schemas  # noqa: E402
from app.config import get_allowed_router_api_keys, settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.main import _allowed_cors_origins  # noqa: E402
from app.services.secrets import is_encrypted  # noqa: E402


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        session.query(models.ByokKey).delete()
        session.commit()
        yield session
    finally:
        session.close()


def test_byok_key_is_encrypted_at_rest(db):
    item = crud.create_byok_key(
        db=db,
        payload=schemas.ByokKeyCreate(
            label="openai-prod",
            provider="openai",
            api_key="sk-test-secret-value",
            description="test key",
        ),
    )

    row = db.query(models.ByokKey).filter(models.ByokKey.id == item.id).one()
    assert row.api_key_encrypted != "sk-test-secret-value"
    assert is_encrypted(row.api_key_encrypted)
    assert crud.get_byok_key_secret(db, item.id) == "sk-test-secret-value"


def test_legacy_plaintext_byok_key_remains_read_compatible(db):
    row = models.ByokKey(
        label="legacy",
        provider="openai",
        api_key_encrypted="sk-legacy-plaintext",
        key_preview="sk-legac...text",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert crud.get_byok_key_secret(db, row.id) == "sk-legacy-plaintext"


def test_default_cors_origins_do_not_allow_wildcard():
    assert "*" not in _allowed_cors_origins()


def test_production_rejects_demo_router_api_key():
    original_env = settings.app_env
    original_keys = settings.router_api_keys
    try:
        settings.app_env = "production"
        settings.router_api_keys = "demo-router-key"
        with pytest.raises(RuntimeError):
            get_allowed_router_api_keys()
    finally:
        settings.app_env = original_env
        settings.router_api_keys = original_keys
