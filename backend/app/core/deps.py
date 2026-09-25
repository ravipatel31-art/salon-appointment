"""Shared FastAPI dependencies: current user / optional guest session / admin gate."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models import User


def _user_from_authorization(authorization: str | None, db: Session) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="not_authenticated")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise HTTPException(status_code=401, detail="invalid_token")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="invalid_token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="invalid_token")
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    return _user_from_authorization(authorization, db)


def get_optional_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """Optional-credentials dependency for guest checkout (CONTRACT §Bookings).

    No Authorization header → None (guest path; the route then requires
    guest_name + guest_phone). Header present → must be a valid Bearer token
    (401 otherwise — never silently downgraded to a guest session).
    """
    if not authorization:
        return None
    return _user_from_authorization(authorization, db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="not_authorized")
    return user
