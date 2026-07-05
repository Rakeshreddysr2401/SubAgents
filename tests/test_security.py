"""Password hashing + JWT access/refresh token helpers."""

import time

import jwt
import pytest

from src.configs.settings import get_settings
from src.services import security


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    yield
    get_settings.cache_clear()


def test_hash_and_verify_password():
    hashed = security.hash_password("hunter2isgreat")
    assert hashed != "hunter2isgreat"
    assert security.verify_password("hunter2isgreat", hashed)
    assert not security.verify_password("wrongpassword", hashed)


def test_verify_password_rejects_garbage_hash():
    assert not security.verify_password("anything", "not-a-bcrypt-hash")


def test_access_token_round_trip():
    token, _ = security.create_access_token("user-1", "a@example.com")
    payload = security.decode_token(token, security.ACCESS)
    assert payload["sub"] == "user-1"
    assert payload["email"] == "a@example.com"
    assert payload["type"] == "access"


def test_refresh_token_round_trip():
    token, jti, _ = security.create_refresh_token("user-1")
    payload = security.decode_token(token, security.REFRESH)
    assert payload["sub"] == "user-1"
    assert payload["jti"] == jti
    assert payload["type"] == "refresh"


def test_decode_rejects_wrong_type():
    token, _ = security.create_access_token("user-1", "a@example.com")
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_token(token, security.REFRESH)


def test_decode_rejects_expired_token(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_TTL_MINUTES", "0")
    get_settings.cache_clear()
    token, _ = security.create_access_token("user-1", "a@example.com")
    time.sleep(1.1)
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_token(token, security.ACCESS)
    get_settings.cache_clear()
