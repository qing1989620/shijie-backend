"""Auth dependencies + request-id middleware wiring helpers."""
import uuid

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import decode_token
from app.models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AppError("UNAUTHORIZED", "Missing bearer token")
    payload = decode_token(auth.removeprefix("Bearer ").strip())
    if not payload or payload.get("type") != "access":
        raise AppError("UNAUTHORIZED", "Invalid or expired token")
    user = db.query(User).get(payload["sub"])
    if not user or not user.is_active:
        raise AppError("UNAUTHORIZED", "User not found or disabled")
    return user


def request_id_middleware(request: Request):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = rid
    return rid


def owner_or_404(obj, user_id: str, code: str = "NOT_FOUND"):
    """IDOR guard: private resources must always be scoped by owner."""
    if obj is None or (getattr(obj, "user_id", None) and obj.user_id != user_id):
        raise AppError(code)
    return obj
