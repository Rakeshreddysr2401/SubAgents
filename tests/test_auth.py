"""Auth dependency: disabled mode, and JWT sub extraction / rejection."""

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.api.auth import DEFAULT_USER, get_current_claims, get_user_id
from src.configs.settings import get_settings


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class _FakeRequest:
    """Minimal stand-in for fastapi.Request — only `.cookies` is used."""

    def __init__(self, cookies: dict | None = None):
        self.cookies = cookies or {}


async def test_auth_disabled_returns_default(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "true")
    assert await get_user_id(None) == DEFAULT_USER
    get_settings.cache_clear()


async def test_valid_token_yields_sub(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    token = jwt.encode({"sub": "alice", "type": "access"}, "s3cret", algorithm="HS256")
    assert await get_user_id(_creds(token)) == "alice"
    get_settings.cache_clear()


async def test_missing_token_rejected(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await get_user_id(None)
    assert exc.value.status_code == 401
    get_settings.cache_clear()


async def test_bad_token_rejected(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await get_user_id(_creds("garbage.token.here"))
    assert exc.value.status_code == 401
    get_settings.cache_clear()


async def test_cookie_token_yields_sub(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    token = jwt.encode({"sub": "alice", "type": "access"}, "s3cret", algorithm="HS256")
    assert await get_user_id(None, _FakeRequest({"access_token": token})) == "alice"
    get_settings.cache_clear()


async def test_bearer_takes_priority_over_cookie(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    bearer_token = jwt.encode({"sub": "bearer-user", "type": "access"}, "s3cret", algorithm="HS256")
    cookie_token = jwt.encode({"sub": "cookie-user", "type": "access"}, "s3cret", algorithm="HS256")
    user_id = await get_user_id(_creds(bearer_token), _FakeRequest({"access_token": cookie_token}))
    assert user_id == "bearer-user"
    get_settings.cache_clear()


async def test_get_current_claims_disabled_returns_default(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "true")
    claims = await get_current_claims(None, None)
    assert claims == {"id": DEFAULT_USER, "email": "dev@localhost"}
    get_settings.cache_clear()


async def test_get_current_claims_returns_email(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    token = jwt.encode(
        {"sub": "alice", "email": "alice@example.com", "type": "access"}, "s3cret", algorithm="HS256"
    )
    claims = await get_current_claims(_creds(token), None)
    assert claims == {"id": "alice", "email": "alice@example.com"}
    get_settings.cache_clear()
