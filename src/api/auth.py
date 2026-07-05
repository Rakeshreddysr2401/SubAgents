"""Auth: JWT verification dependency + signup/login/refresh/logout/account routes.

When AUTH_DISABLED (dev default) every request maps to "default_user" and the
routes below still work (useful for exercising the UI locally) but nothing is
actually gated. Otherwise:

- Access tokens (short-lived) are verified statelessly and carry `sub`/`email`.
- Refresh tokens (long-lived) carry a `jti` tracked in Redis so they can be
  revoked on logout / rotated on refresh / invalidated on password change.
- Both are set as httpOnly cookies; a bearer header is also accepted for
  non-browser API clients.
"""

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.models.schema import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    SignupRequest,
    UserOut,
)
from src.services import security
from src.services.rate_limit import enforce_rate_limit
from src.services.redis_client import get_redis
from src.services.user_store import EmailAlreadyExists

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

DEFAULT_USER = "default_user"

# auto_error=False so we can allow anonymous access when auth is disabled
_bearer = HTTPBearer(auto_error=False)

_ACCESS_COOKIE = "access_token"
_REFRESH_COOKIE = "refresh_token"
_REFRESH_KEY_PREFIX = "refresh_token:"


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None, request: Request | None
) -> str | None:
    if credentials is not None:
        return credentials.credentials
    if request is not None:
        return request.cookies.get(_ACCESS_COOKIE)
    return None


def _decode_access(
    credentials: HTTPAuthorizationCredentials | None, request: Request | None
) -> dict:
    token = _extract_token(credentials, request)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing access token")
    try:
        return security.decode_token(token, security.ACCESS)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    request: Request = None,
) -> str:
    settings = get_settings()
    if settings.auth_disabled:
        return DEFAULT_USER
    payload = _decode_access(credentials, request)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    return sub


async def get_current_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    request: Request = None,
) -> dict:
    """Like get_user_id but returns {id, email} — used by /auth/me."""
    settings = get_settings()
    if settings.auth_disabled:
        return {"id": DEFAULT_USER, "email": "dev@localhost"}
    payload = _decode_access(credentials, request)
    return {"id": payload.get("sub"), "email": payload.get("email")}


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=_ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path="/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(_ACCESS_COOKIE, path="/")
    response.delete_cookie(_REFRESH_COOKIE, path="/auth")


async def _issue_tokens(response: Response, user_id: str, email: str) -> None:
    access_token, _ = security.create_access_token(user_id, email)
    refresh_token, jti, expires_at = security.create_refresh_token(user_id)
    redis = get_redis()
    ttl_seconds = get_settings().refresh_token_ttl_days * 24 * 3600
    await redis.set(f"{_REFRESH_KEY_PREFIX}{jti}", user_id, ex=ttl_seconds)
    _set_auth_cookies(response, access_token, refresh_token)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/signup", response_model=UserOut)
async def signup(req: SignupRequest, request: Request, response: Response):
    await enforce_rate_limit("signup", _client_key(request))
    user_store = request.app.state.user_store
    try:
        user = await user_store.create(req.email, security.hash_password(req.password))
    except EmailAlreadyExists:
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    await _issue_tokens(response, user.id, user.email)
    logger.info("New signup: %s", user.email)
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=UserOut)
async def login(req: LoginRequest, request: Request, response: Response):
    await enforce_rate_limit("login", req.email.lower())
    user_store = request.app.state.user_store
    user = await user_store.get_by_email(req.email)
    if user is None or not security.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await _issue_tokens(response, user.id, user.email)
    return UserOut(id=user.id, email=user.email)


@router.post("/refresh", response_model=UserOut)
async def refresh(request: Request, response: Response):
    token = request.cookies.get(_REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = security.decode_token(token, security.REFRESH)
    except jwt.PyJWTError:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    jti, user_id = payload.get("jti"), payload.get("sub")
    redis = get_redis()
    redis_key = f"{_REFRESH_KEY_PREFIX}{jti}"
    stored_user_id = await redis.get(redis_key)
    if stored_user_id is None or stored_user_id != user_id:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token revoked or reused")

    user = await request.app.state.user_store.get_by_id(user_id)
    if user is None:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Account no longer exists")

    await redis.delete(redis_key)  # rotate: old refresh token is single-use
    await _issue_tokens(response, user.id, user.email)
    return UserOut(id=user.id, email=user.email)


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(_REFRESH_COOKIE)
    if token:
        try:
            payload = security.decode_token(token, security.REFRESH)
            await get_redis().delete(f"{_REFRESH_KEY_PREFIX}{payload.get('jti')}")
        except jwt.PyJWTError:
            pass
    _clear_auth_cookies(response)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(claims: dict = Depends(get_current_claims)):
    return UserOut(id=claims["id"], email=claims["email"])


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest, request: Request, user_id: str = Depends(get_user_id)
):
    user_store = request.app.state.user_store
    user = await user_store.get_by_id(user_id)
    if user is None or not security.verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await user_store.update_password(user_id, security.hash_password(req.new_password))
    return {"status": "ok"}


@router.delete("/account")
async def delete_account(
    req: DeleteAccountRequest,
    request: Request,
    response: Response,
    user_id: str = Depends(get_user_id),
):
    user_store = request.app.state.user_store
    user = await user_store.get_by_id(user_id)
    if user is None or not security.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect")
    await user_store.delete(user_id)  # cascades to chat_threads
    _clear_auth_cookies(response)
    return {"status": "ok"}
