"""Auth & user routes: register / login / refresh (rotating) / logout / me."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import RefreshToken, User, UserPreference, UserProfile
from app.schemas.schemas import (
    ChangePasswordIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    TokenPairOut,
    UpdateMeIn,
    UserOut,
)

router = APIRouter(tags=["auth"])
me_router = APIRouter(tags=["users"])


def _issue_tokens(db: Session, user: User) -> TokenPairOut:
    access, _ = create_access_token(user.id)
    refresh, exp, jti = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp))
    db.commit()
    return TokenPairOut(access_token=access, refresh_token=refresh, expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60)


@router.post("/auth/register", response_model=UserOut, status_code=201, operation_id="auth_register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise AppError("CONFLICT", "Email already registered")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), display_name=body.display_name)
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    db.add(UserPreference(user_id=user.id))
    db.commit()
    return user


@router.post("/auth/login", response_model=TokenPairOut, operation_id="auth_login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise AppError("UNAUTHORIZED", "Incorrect email or password")
    return _issue_tokens(db, user)


@router.post("/auth/refresh", response_model=TokenPairOut, operation_id="auth_refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AppError("UNAUTHORIZED", "Invalid refresh token")
    row = db.query(RefreshToken).filter(RefreshToken.jti == payload["jti"]).first()
    if not row or row.revoked_at is not None or row.expires_at < datetime.now(UTC):
        raise AppError("UNAUTHORIZED", "Refresh token revoked or expired")
    row.revoked_at = datetime.now(UTC)  # rotation: old token can never be replayed
    user = db.query(User).get(payload["sub"])
    if not user or not user.is_active:
        raise AppError("UNAUTHORIZED", "User not found")
    return _issue_tokens(db, user)


@router.post("/auth/logout", operation_id="auth_logout")
def logout(body: LogoutIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payload = decode_token(body.refresh_token)
    if payload:
        row = db.query(RefreshToken).filter(RefreshToken.jti == payload["jti"]).first()
        if row:
            row.revoked_at = datetime.now(UTC)
            db.commit()
    return {"ok": True}


@me_router.get("/users/me", response_model=UserOut, operation_id="users_me_get")
def get_me(user: User = Depends(get_current_user)):
    return user


@me_router.patch("/users/me", response_model=UserOut, operation_id="users_me_update")
def update_me(body: UpdateMeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.display_name is not None:
        user.display_name = body.display_name
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    if body.grade is not None:
        profile.grade = body.grade
    if body.timezone is not None:
        profile.timezone = body.timezone
    db.commit()
    return user


@me_router.post("/users/me/change-password", operation_id="users_change_password")
def change_password(body: ChangePasswordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise AppError("UNAUTHORIZED", "Current password incorrect")
    user.password_hash = hash_password(body.new_password)
    # revoke all refresh tokens on password change
    for rt in db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)):
        rt.revoked_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}
