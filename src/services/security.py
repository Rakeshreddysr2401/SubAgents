"""Password hashing + JWT access/refresh token helpers.

Access tokens carry `sub` (user_id) and `email`, are short-lived, and are
verified stateless (no DB/Redis lookup). Refresh tokens are long-lived, carry
a `jti` that's tracked in Redis (see src/api/auth.py) so they can be revoked
on logout/rotation/password-change.
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from src.configs.settings import get_settings

ACCESS = "access"
REFRESH = "refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _encode(payload: dict) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, email: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_ttl_minutes)
    token = _encode(
        {"sub": user_id, "email": email, "type": ACCESS, "exp": expires_at}
    )
    return token, expires_at


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). Caller stores jti -> user_id in Redis."""
    settings = get_settings()
    jti = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)
    token = _encode({"sub": user_id, "type": REFRESH, "jti": jti, "exp": expires_at})
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> dict:
    """Raises jwt.PyJWTError (incl. subclasses) on any invalid/expired/wrong-type token."""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
    return payload
