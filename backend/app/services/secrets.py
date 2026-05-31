"""Secret-at-rest helpers for provider keys."""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


_PREFIX = "enc:v1:"


class SecretKeyMissing(ValueError):
    """Raised when ROUTER_SECRET_KEY is missing or invalid."""


class SecretDecryptError(ValueError):
    """Raised when encrypted data cannot be decrypted."""


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(_PREFIX))


def _router_secret_key() -> str:
    return os.getenv("ROUTER_SECRET_KEY") or getattr(settings, "router_secret_key", "")


def _fernet() -> Fernet:
    key = _router_secret_key()
    if not key:
        raise SecretKeyMissing("ROUTER_SECRET_KEY is required to store BYOK secrets")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise SecretKeyMissing("ROUTER_SECRET_KEY must be a valid Fernet key") from exc


def encrypt_secret(plaintext: str) -> str:
    if is_encrypted(plaintext):
        return plaintext
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    if not is_encrypted(value):
        return value
    token = value[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptError("Stored BYOK secret cannot be decrypted") from exc
