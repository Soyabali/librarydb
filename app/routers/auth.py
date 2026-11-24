from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from sqlalchemy import func, select

from app.core.deps import DB, CurrentUser
from app.core.exceptions import BadRequest
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.common import Message
from app.schemas.people import PasswordChange, Token, UserRead
from app.services.activity import log_activity

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=Token, summary="Log in with email and password")
def login(
    username: Annotated[str, Form(description="Staff email", examples=["rajesh.sharma@library.edu.in"])],
    password: Annotated[str, Form(json_schema_extra={"format": "password"})],
    db: DB,
    request: Request,
):
    """Use the staff **email** as `username`. Copy `access_token` from the response, click **Authorize** and paste it."""
    user = db.scalar(select(User).where(func.lower(User.email) == username.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    user.last_login = func.now()  # database clock, same as every other timestamp
    log_activity(db, user=user, action="LOGIN", description=f"{user.email} logged in", request=request)
    db.commit()
    db.refresh(user)

    token, expires_in = create_access_token(user.user_id, user.role_name)
    return Token(access_token=token, expires_in=expires_in, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead, summary="Current user profile")
def me(user: CurrentUser):
    return user


@router.post("/change-password", response_model=Message, summary="Change your own password")
def change_password(payload: PasswordChange, db: DB, user: CurrentUser, request: Request):
    if not verify_password(payload.current_password, user.password_hash):
        raise BadRequest("Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    log_activity(db, user=user, action="PASSWORD_CHANGED", request=request)
    db.commit()
    return Message(detail="Password updated")
