from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, select

from app.core.deps import DB, AdminUser, CurrentUser, StaffUser
from app.core.exceptions import BadRequest, Conflict, NotFound
from app.models import Book, BookCopy, Loan
from app.schemas.catalog import CopyCreate, CopyRead, CopyUpdate
from app.schemas.circulation import LoanRead
from app.schemas.common import CopyCondition, Page
from app.services.activity import log_activity
from app.services.circulation import ACTIVE_LOAN_STATUSES
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/copies", tags=["Book copies"])


def _has_active_loan(db, copy_id: int) -> bool:
    return bool(
        db.scalar(select(func.count()).where(Loan.copy_id == copy_id, Loan.status.in_(ACTIVE_LOAN_STATUSES)))
    )


@router.get("", response_model=Page[CopyRead], summary="List copies")
def list_copies(
    db: DB,
    _: CurrentUser,
    pagination: Pagination,
    book_id: int | None = None,
    accession_no: Annotated[str | None, Query(description="Exact accession number / barcode")] = None,
    condition: CopyCondition | None = None,
    is_available: bool | None = None,
):
    stmt = select(BookCopy).order_by(BookCopy.copy_id)
    if book_id is not None:
        stmt = stmt.where(BookCopy.book_id == book_id)
    if accession_no:
        stmt = stmt.where(BookCopy.accession_no == accession_no)
    if condition is not None:
        stmt = stmt.where(BookCopy.condition == condition)
    if is_available is not None:
        stmt = stmt.where(BookCopy.is_available.is_(is_available))
    return paginate(db, stmt, pagination)


@router.get("/{copy_id}", response_model=CopyRead, summary="Get a copy")
def get_copy(copy_id: int, db: DB, _: CurrentUser):
    copy = db.get(BookCopy, copy_id)
    if copy is None:
        raise NotFound("Copy", copy_id)
    return copy


@router.get("/{copy_id}/history", response_model=list[LoanRead], summary="Loan history of a copy")
def copy_history(copy_id: int, db: DB, _: StaffUser):
    if db.get(BookCopy, copy_id) is None:
        raise NotFound("Copy", copy_id)
    return db.scalars(select(Loan).where(Loan.copy_id == copy_id).order_by(Loan.issue_date.desc())).all()


@router.post("", response_model=CopyRead, status_code=status.HTTP_201_CREATED, summary="Add a physical copy")
def create_copy(payload: CopyCreate, db: DB, user: StaffUser, request: Request):
    if db.get(Book, payload.book_id) is None:
        raise BadRequest(f"Book {payload.book_id} does not exist")
    copy = BookCopy(**payload.model_dump(), is_available=payload.condition != CopyCondition.LOST)
    db.add(copy)
    db.flush()
    log_activity(db, user=user, action="COPY_CREATED",
                 description=f"Added copy {copy.accession_no} of book {copy.book_id}", request=request)
    db.commit()
    db.refresh(copy)
    return copy


@router.patch("/{copy_id}", response_model=CopyRead, summary="Update a copy (condition, shelf, accession no.)")
def update_copy(copy_id: int, payload: CopyUpdate, db: DB, user: StaffUser, request: Request):
    """Availability is managed by issue/return. Marking a copy **Lost** takes it out of circulation;
    use `POST /loans/{id}/lost` instead if the copy is currently on loan."""
    copy = db.get(BookCopy, copy_id, with_for_update=True)
    if copy is None:
        raise NotFound("Copy", copy_id)
    data = payload.model_dump(exclude_unset=True)
    on_loan = _has_active_loan(db, copy_id)

    if "condition" in data and data["condition"] is not None:
        if data["condition"] == CopyCondition.LOST:
            if on_loan:
                raise Conflict("Copy is on loan - use POST /loans/{loan_id}/lost")
            copy.is_available = False
        elif copy.condition == CopyCondition.LOST and not on_loan:
            copy.is_available = True  # found again
    for key, value in data.items():
        setattr(copy, key, value)

    log_activity(db, user=user, action="COPY_UPDATED", description=f"Updated copy {copy.accession_no}",
                 request=request)
    db.commit()
    return copy


@router.delete("/{copy_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a copy (admin)")
def delete_copy(copy_id: int, db: DB, user: AdminUser, request: Request):
    copy = db.get(BookCopy, copy_id)
    if copy is None:
        raise NotFound("Copy", copy_id)
    if db.scalar(select(func.count()).where(Loan.copy_id == copy_id)):
        raise Conflict("Copy has loan history - mark it as Lost or Poor instead of deleting it")
    db.delete(copy)
    log_activity(db, user=user, action="COPY_DELETED", description=f"Deleted copy {copy.accession_no}",
                 request=request)
    db.commit()
