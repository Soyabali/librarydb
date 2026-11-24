from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User

# Simple bearer token: log in once via POST /auth/login, then send "Authorization: Bearer <token>".
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the `access_token` from POST /api/v1/auth/login",
)

DB = Annotated[Session, Depends(get_db)]

ADMIN = "Admin"
LIBRARIAN = "Librarian"


def get_current_user(
    db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - log in at POST /api/v1/auth/login and send the token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token - log in again",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[[User], User]:
    def checker(user: CurrentUser) -> User:
        if user.role_name not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return user

    return checker


AdminUser = Annotated[User, Depends(require_roles(ADMIN))]
StaffUser = Annotated[User, Depends(require_roles(ADMIN, LIBRARIAN))]
