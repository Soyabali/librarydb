import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


@dataclass
class PageParams:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def page_params(
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


Pagination = Annotated[PageParams, Depends(page_params)]


def paginate(
    db: Session,
    stmt: Select,
    params: PageParams,
    *,
    scalars: bool = True,
    transform: Callable[[Any], Any] | None = None,
) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    paged = stmt.limit(params.size).offset(params.offset)
    rows: Sequence[Any] = db.scalars(paged).unique().all() if scalars else db.execute(paged).all()
    items = [transform(r) for r in rows] if transform else list(rows)
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": math.ceil(total / params.size) if total else 0,
    }
