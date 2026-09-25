"""Auth endpoints: register / login / me (docs/CONTRACT.md §Auth)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginIn, MeResponse, RegisterIn, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "email": user.email,
        "role": user.role,
    }


def token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id, user.role),
        "token_type": "bearer",
        "user": user_out(user),
    }


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=409, detail="email_already_registered")
    if db.scalar(select(User).where(User.phone == body.phone)):
        raise HTTPException(status_code=409, detail="phone_already_registered")
    user = User(
        name=body.name,
        phone=body.phone,
        email=body.email,
        password_hash=hash_password(body.password),
        role="customer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    if body.email:
        user = db.scalar(select(User).where(User.email == body.email))
    else:
        user = db.scalar(select(User).where(User.phone == body.phone))
    if user is None or not user.is_active or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    return token_response(user)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": user_out(user)}
