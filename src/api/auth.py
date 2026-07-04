"""JWT auth → user_id dependency.

When AUTH_DISABLED (dev default) every request maps to "default_user".
Otherwise a valid `Authorization: Bearer <jwt>` is required and `user_id`
comes from the token's `sub` claim. The user_id scopes memory and RAG.
"""

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.configs.settings import get_settings

DEFAULT_USER = "default_user"

# auto_error=False so we can allow anonymous access when auth is disabled
_bearer = HTTPBearer(auto_error=False)


async def get_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    settings = get_settings()
    if settings.auth_disabled:
        return DEFAULT_USER

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    return sub
