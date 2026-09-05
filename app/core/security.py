"""Password hashing (Argon2id) and JWT issue/verify utilities."""
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

pwd_hasher = PasswordHasher()  # Argon2id by default

ALG = "HS256"


def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # malformed hash
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(user_id: str) -> tuple[str, datetime]:
    exp = _now() + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    payload = {"sub": user_id, "type": "access", "jti": uuid.uuid4().hex, "exp": exp, "iat": _now()}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALG), exp


def create_refresh_token(user_id: str) -> tuple[str, datetime, str]:
    """Returns (token, expires_at, jti). jti is stored for rotation/revocation."""
    exp = _now() + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)
    jti = uuid.uuid4().hex
    payload = {"sub": user_id, "type": "refresh", "jti": jti, "exp": exp, "iat": _now()}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALG), exp, jti


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALG])
    except jwt.PyJWTError:
        return None
