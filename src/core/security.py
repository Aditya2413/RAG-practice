import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from src.core.config import get_settings
from src.core.exceptions import AuthError

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _get_algorithm() -> str:
    settings = get_settings()
    return "RS256" if settings.app_secret_key.strip().startswith("-----BEGIN") else "HS256"


def create_access_token(payload: dict[str, Any]) -> str:
    settings = get_settings()
    algorithm = _get_algorithm()
    data = {
        **payload,
        "exp": datetime.now(UTC) + ACCESS_TOKEN_TTL,
        "iat": datetime.now(UTC),
    }
    key = settings.app_secret_key if algorithm == "RS256" else settings.app_secret_key or "dev-secret"
    return jwt.encode(data, key, algorithm=algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    algorithm = _get_algorithm()
    key = settings.app_public_key if algorithm == "RS256" else settings.app_secret_key or "dev-secret"
    try:
        return jwt.decode(token, key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")


def create_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Store only the hash in the DB."""
    raw = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def refresh_token_expires_at() -> datetime:
    return datetime.now(UTC) + REFRESH_TOKEN_TTL
