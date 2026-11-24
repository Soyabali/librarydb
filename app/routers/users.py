from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import or_, select

from app.core.deps import DB, AdminUser
from app.core.exceptions import BadRequest, NotFound
from app.core.security import hash_password
from app.models import Role, User
from app.schemas.common import Message, Page
from app.schemas.people import PasswordReset, RoleRead, UserCreate, UserRead, UserUpdate
from app.services.activity import log_activity
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/users", tags=["Staff users (admin)"])


@router.get("/roles", response_model=list[RoleRead], summary="List roles")
def list_roles(db: DB, _: AdminUser):
    return db.scalars(select(Role).order_by(Role.role_id)).all()


@router.get("", response_model=Page[UserRead], summary="List staff users")
def list_users(
    db: DB,
    _: AdminUser,
    pagination: Pagination,
    q: Annotated[str | None, Query()] = None,
    is_active: bool | None = None,
):
    stmt = select(User).order_by(User.user_id)
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    return paginate(db, stmt, pagination)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Create a staff user")
def create_user(payload: UserCreate, db: DB, admin: AdminUser, request: Request):
    if db.get(Role, payload.role_id) is None:
        raise BadRequest(f"Role {payload.role_id} does not exist")
    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        phone=payload.phone,
        role_id=payload.role_id,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    log_activity(db, user=admin, action="USER_CREATED", description=f"Created user {user.email}", request=request)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead, summary="Get a staff user")
def get_user(user_id: int, db: DB, _: AdminUser):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User", user_id)
    return user


@router.patch("/{user_id}", response_model=UserRead, summary="Update a staff user")
def update_user(user_id: int, payload: UserUpdate, db: DB, admin: AdminUser, request: Request):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User", user_id)
    data = payload.model_dump(exclude_unset=True)
    if user.user_id == admin.user_id and (data.get("is_active") is False or data.get("role_id", user.role_id) != user.role_id):
        raise BadRequest("You cannot deactivate yourself or change your own role")
    if "role_id" in data and db.get(Role, data["role_id"]) is None:
        raise BadRequest(f"Role {data['role_id']} does not exist")
    for key, value in data.items():
        setattr(user, key, value)
    log_activity(db, user=admin, action="USER_UPDATED", description=f"Updated user {user.email}", request=request)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", response_model=Message, summary="Set a new password for a user")
def reset_password(user_id: int, payload: PasswordReset, db: DB, admin: AdminUser, request: Request):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User", user_id)
    user.password_hash = hash_password(payload.new_password)
    log_activity(db, user=admin, action="PASSWORD_RESET", description=f"Reset password for {user.email}",
                 request=request)
    db.commit()
    return Message(detail=f"Password reset for {user.email}")
