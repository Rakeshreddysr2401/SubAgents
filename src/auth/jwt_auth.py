"""
JWT Authentication module for OWP Agent.

Decodes JWT tokens and extracts client user info.

TODO: Add real JWT validation once public key / validation API is available.
"""

import os
from dataclasses import dataclass
from typing import Optional

import jwt

from src.configs.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

@dataclass
class CurrentUser:
    """Client user extracted from a JWT token."""
    data: dict
    token: str

    @property
    def client_id(self) -> str:
        return self.data.get("client_id", "")

    @property
    def email(self) -> str:
        return self.data.get("client_email", "")

    @property
    def exp(self) -> int:
        return self.data.get("exp", 0)

    @property
    def scopes(self) -> list[str]:
        return self.data.get("scope", [])


# ---------------------------------------------------------------------------
# Public key loader
# ---------------------------------------------------------------------------

def _get_public_key():
    """Build an RSA public key from the GAUTH_PUBLIC_KEY env var."""
    raw = os.getenv("GAUTH_PUBLIC_KEY", "")
    if not raw or raw == "PASTE_YOUR_RSA_PUBLIC_KEY_HERE":
        raise ValueError("GAUTH_PUBLIC_KEY is not configured")
    pem = f"-----BEGIN PUBLIC KEY-----\n{raw}\n-----END PUBLIC KEY-----"
    return pem


# ---------------------------------------------------------------------------
# Core authentication
# ---------------------------------------------------------------------------

def authenticate(token: str) -> Optional[CurrentUser]:
    """
    Decode a JWT token and return a CurrentUser object.

    TODO: Once the public key or validation API is available, enable real
          RS256 signature verification by uncommenting the verified path below.

    Returns a CurrentUser instance, or None if the token is invalid.
    """
    if not token:
        return None

    try:
        # Strip "Bearer " prefix if present
        token = token.replace("Bearer", "").replace("bearer", "").strip()
        if not token:
            return None

        # --- FUTURE: verified decode (uncomment when public key is ready) ---
        # public_key = _get_public_key()
        # payload = jwt.decode(
        #     token,
        #     public_key,
        #     algorithms=["RS256"],
        #     options={"verify_exp": True, "require": ["exp"]},
        # )

        # --- CURRENT: decode without verification (dev/testing only) ---
        payload = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=["RS256"],
        )

        if not payload:
            return None

        user = CurrentUser(data=payload, token=token)
        logger.info("Authenticated client: %s (UNVERIFIED - dev mode)", user.client_id)
        return user

    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: %s", e)
        return None
    except Exception as e:
        logger.error("Authentication error: %s", e)
        return None
