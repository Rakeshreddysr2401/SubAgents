"""Auth dependency: disabled mode, and JWT sub extraction / rejection."""

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.api.auth import DEFAULT_USER, get_user_id
from src.configs.settings import get_settings


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_auth_disabled_returns_default(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "true")
    assert await get_user_id(None) == DEFAULT_USER
    get_settings.cache_clear()


async def test_valid_token_yields_sub(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    token = jwt.encode({"sub": "alice"}, "s3cret", algorithm="HS256")
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
