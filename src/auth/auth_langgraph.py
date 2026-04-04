"""
LangGraph Server Authentication Handler.

This module provides JWT-based authentication for both:
- LangGraph Studio (development)
- Custom API endpoints (production)
"""
import os
import jwt
from langgraph_sdk import Auth

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

auth = Auth()

# Development fallback token (use DEV_API_KEY in production dev environments)
DEV_TOKEN = os.getenv("DEV_API_KEY", "")


@auth.authenticate
async def authenticate_jwt(headers: dict) -> dict:
    """
    Authenticate requests using JWT Bearer tokens.

    Validates JWT from Authorization header and returns user context.
    Falls back to DEV_API_KEY for development environments.

    Args:
        headers: Request headers dict (bytes keys/values from LangGraph)

    Returns:
        User context dict with identity, token, client_id, scopes

    Raises:
        Auth.exceptions.HTTPException: 401 if authentication fails
    """
    # Extract Authorization header (LangGraph passes headers as bytes)
    auth_header = headers.get(b"authorization") or headers.get(b"Authorization")

    if not auth_header:
        # Fallback to DEV_API_KEY for Studio development
        if DEV_TOKEN:
            logger.debug("No Authorization header, using DEV_API_KEY")
            return _validate_token(DEV_TOKEN)

        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    # Parse Bearer token
    auth_str = auth_header.decode() if isinstance(auth_header, bytes) else auth_header

    if not auth_str.startswith("Bearer "):
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Authorization header must start with 'Bearer '"
        )

    token = auth_str.split(" ", 1)[1].strip()

    if not token:
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Bearer token is empty"
        )

    return _validate_token(token)


def _validate_token(token: str) -> dict:
    """
    Validate JWT token and extract user information.

    Args:
        token: JWT token string

    Returns:
        User context dict

    Raises:
        Auth.exceptions.HTTPException: 401 if token is invalid
    """
    try:
        # Decode JWT (disable signature verification for dev - enable in production)
        # TODO: Set verify_signature=True and provide PUBLIC_KEY for production
        payload = jwt.decode(
            token,
            options={"verify_signature": False},  # ⚠️ DEV MODE ONLY
            algorithms=["RS256"]
        )

        client_id = payload.get("client_id", "unknown")
        scopes = payload.get("scope", [])

        logger.debug("Authenticated user: client_id=%s, scopes=%s", client_id, scopes)

        # Return user context (accessible in graph nodes via config)
        return {
            "identity": client_id,
            "token": token,
            "client_id": client_id,
            "scopes": scopes,
            "exp": payload.get("exp"),
            "jti": payload.get("jti"),
        }

    except jwt.ExpiredSignatureError:
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        logger.error("Token validation failed: %s", e, exc_info=True)
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Authentication failed"
        )


# ─────────────────────────────────────────────────────────────────────────────
# RESOURCE AUTHORIZATION - DISABLED (2026-03-20)
# ─────────────────────────────────────────────────────────────────────────────
# Issue: Using unscoped @auth.on applied to ALL resource operations (assistants,
#        threads, runs, etc.). On read/list operations, LangGraph treats the
#        returned value as a metadata FILTER. Since assistants defined in
#        langgraph.json have no "owner" metadata, the filter returned zero
#        results → Studio showed "No assistants found." Similarly, thread reads
#        failed with "Thread or assistant not found" (HTTP 404).
#
# Root cause: @auth.on (no scope) acts as a global handler for every resource
#             type and every operation (create, read, list, delete). The handler
#             was injecting owner metadata, which LangGraph then used as a filter
#             on read/list — blocking access to server-defined assistants and
#             newly created threads.
#
# Fix: Commented out the handler. Authentication (@auth.authenticate) still
#      validates all requests via JWT / DEV_API_KEY.
#
# To re-enable per-user thread isolation later, scope narrowly:
#   @auth.on("threads:create")   → only stamp ownership on new threads
#   @auth.on("threads:read")     → filter reads by owner
#   @auth.on("threads:search")   → filter listing by owner
# Do NOT use unscoped @auth.on — it will break assistant listing.
# ─────────────────────────────────────────────────────────────────────────────
# @auth.on("threads:create")
# async def add_owner_metadata(ctx: Auth.types.AuthContext, value: dict):
#     metadata = value.setdefault("metadata", {})
#     user = ctx.user if isinstance(ctx.user, dict) else {}
#     metadata["owner"] = user.get("identity", "unknown")
#     metadata["client_id"] = user.get("client_id", "unknown")
#     return value
