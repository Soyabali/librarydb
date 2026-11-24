"""Factory for the simple reference-data endpoints (categories, publishers, authors, departments, courses)."""

from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import InstrumentedAttribute

from app.core.deps import DB, AdminUser, CurrentUser, StaffUser
from app.core.exceptions import BadRequest, NotFound
from app.schemas.common import Page
from app.services.activity import log_activity
from app.services.pagination import Pagination, paginate


def build_crud_router(
    *,
    model: Any,
    name: str,
    tag: str,
    prefix: str,
    read_schema: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    search_fields: Sequence[InstrumentedAttribute],
    order_by: InstrumentedAttribute,
    filters: dict[str, InstrumentedAttribute] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])
    pk = model.__mapper__.primary_key[0].key
    filters = filters or {}

    @router.get("", response_model=Page[read_schema], summary=f"List {name}s")
    def list_items(
        db: DB,
        _: CurrentUser,
        pagination: Pagination,
        request: Request,
        q: Annotated[str | None, Query(description="Search text")] = None,
    ):
        stmt = select(model).order_by(order_by)
        if q:
            stmt = stmt.where(or_(*(field.ilike(f"%{q}%") for field in search_fields)))
        for param, column in filters.items():
            value = request.query_params.get(param)
            if value is not None:
                if not value.isdigit():
                    raise BadRequest(f"{param} must be an integer")
                stmt = stmt.where(column == int(value))
        return paginate(db, stmt, pagination)

    @router.get("/{item_id}", response_model=read_schema, summary=f"Get a {name}")
    def get_item(item_id: int, db: DB, _: CurrentUser):
        item = db.get(model, item_id)
        if item is None:
            raise NotFound(name.title(), item_id)
        return item

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED, summary=f"Create a {name}")
    def create_item(payload: create_schema, db: DB, user: StaffUser, request: Request):  # type: ignore[valid-type]
        item = model(**payload.model_dump())
        db.add(item)
        db.flush()
        log_activity(db, user=user, action=f"{name.upper()}_CREATED",
                     description=f"Created {name} {getattr(item, pk)}", request=request)
        db.commit()
        return item

    @router.patch("/{item_id}", response_model=read_schema, summary=f"Update a {name}")
    def update_item(item_id: int, payload: update_schema, db: DB, user: StaffUser, request: Request):  # type: ignore[valid-type]
        item = db.get(model, item_id)
        if item is None:
            raise NotFound(name.title(), item_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        log_activity(db, user=user, action=f"{name.upper()}_UPDATED",
                     description=f"Updated {name} {item_id}", request=request)
        db.commit()
        return item

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary=f"Delete a {name} (admin)")
    def delete_item(item_id: int, db: DB, user: AdminUser, request: Request):
        item = db.get(model, item_id)
        if item is None:
            raise NotFound(name.title(), item_id)
        db.delete(item)
        db.flush()  # raises IntegrityError (-> 409) if still referenced
        log_activity(db, user=user, action=f"{name.upper()}_DELETED",
                     description=f"Deleted {name} {item_id}", request=request)
        db.commit()

    return router
