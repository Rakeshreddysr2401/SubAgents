import os
from dataclasses import dataclass
from typing import Optional
import jwt

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key")
ALGORITHM = "HS256"


@dataclass
class CurrentUser:
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


def authenticate(token: str) -> Optional[CurrentUser]:
    if not token:
        return None

    try:
        token = token.replace("Bearer", "").strip()

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        user = CurrentUser(data=payload, token=token)
        logger.info("Authenticated user: %s", user.client_id)

        return user

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid token")
        return None