from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.clock import today as local_today
from app.core.deps import DB, StaffUser
from app.core.exceptions import NotFound
from app.models import Book, BookCopy, Loan, Member
from app.schemas.circulation import (
    BulkUpdateResult,
    FineRead,
    IssueRequest,
    LoanDetail,
    LoanRead,
    LostRequest,
    ReturnRequest,
    ReturnResult,
)
from app.schemas.common import LoanStatus, Page
from app.services import circulation
from app.services import library_settings as cfg
from app.services.activity import log_activity
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/loans", tags=["Loans (circulation)"])


def loan_detail_query() -> Select:
    return (
        select(Loan, BookCopy.accession_no, Book.book_id, Book.title, Member.full_name)
        .join(BookCopy, BookCopy.copy_id == Loan.copy_id)
        .join(Book, Book.book_id == BookCopy.book_id)
        .join(Member, Member.member_id == Loan.member_id)
    )


def detail_transformer(db: Session):
    rate = cfg.get_decimal(db, "fine_per_day_inr")
    today = local_today()

    def transform(row) -> LoanDetail:
        loan, accession_no, book_id, title, member_name = row
        active = loan.status in circulation.ACTIVE_LOAN_STATUSES
        late = max((today - loan.due_date).days, 0) if active else circulation.days_overdue(loan)
        return LoanDetail(
            **LoanRead.model_validate(loan).model_dump(),
            book_id=book_id,
            book_title=title,
            accession_no=accession_no,
            member_name=member_name,
            days_overdue=late,
            estimated_fine=late * rate if active else 0,
        )

    return transform


@router.get("", response_model=Page[LoanDetail], summary="List loans")
def list_loans(
    db: DB,
    _: StaffUser,
    pagination: Pagination,
    status_: Annotated[LoanStatus | None, Query(alias="status")] = None,
    active_only: Annotated[bool, Query(description="Issued or Overdue")] = False,
    overdue_only: Annotated[bool, Query(description="Active loans past their due date")] = False,
    member_id: int | None = None,
    book_id: int | None = None,
    issued_from: date | None = None,
    issued_to: date | None = None,
):
    stmt = loan_detail_query()
    if status_ is not None:
        stmt = stmt.where(Loan.status == status_)
    if active_only or overdue_only:
        stmt = stmt.where(Loan.status.in_(circulation.ACTIVE_LOAN_STATUSES))
    if overdue_only:
        stmt = stmt.where(Loan.due_date < local_today())
    if member_id is not None:
        stmt = stmt.where(Loan.member_id == member_id)
    if book_id is not None:
        stmt = stmt.where(Book.book_id == book_id)
    if issued_from:
        stmt = stmt.where(Loan.issue_date >= issued_from)
    if issued_to:
        stmt = stmt.where(Loan.issue_date <= issued_to)
    stmt = stmt.order_by(Loan.issue_date.desc(), Loan.loan_id.desc())
    return paginate(db, stmt, pagination, scalars=False, transform=detail_transformer(db))


@router.get("/{loan_id}", response_model=LoanDetail, summary="Get a loan")
def get_loan(loan_id: int, db: DB, _: StaffUser):
    row = db.execute(loan_detail_query().where(Loan.loan_id == loan_id)).first()
    if row is None:
        raise NotFound("Loan", loan_id)
    return detail_transformer(db)(row)


@router.post("/issue", response_model=LoanRead, status_code=status.HTTP_201_CREATED, summary="Issue a book")
def issue(payload: IssueRequest, db: DB, user: StaffUser, request: Request):
    """Checks: copy available, member active and within borrowing limit, no overdue books,
    no unpaid fines, and the copy is not held for another member's reservation."""
    loan = circulation.issue_book(
        db,
        member_id=payload.member_id,
        staff=user,
        copy_id=payload.copy_id,
        accession_no=payload.accession_no,
        due_date=payload.due_date,
        remarks=payload.remarks,
    )
    log_activity(db, user=user, action="BOOK_ISSUED",
                 description=f"Loan {loan.loan_id}: copy {loan.copy_id} to member {loan.member_id}, due {loan.due_date}",
                 request=request)
    db.commit()
    return loan


@router.post("/{loan_id}/return", response_model=ReturnResult, summary="Return a book")
def return_loan(loan_id: int, db: DB, user: StaffUser, request: Request, payload: ReturnRequest | None = None):
    payload = payload or ReturnRequest()
    loan, fine = circulation.return_book(
        db, loan_id=loan_id, condition=payload.condition, remarks=payload.remarks
    )
    detail = f"Loan {loan_id} returned"
    if fine is not None:
        detail += f", fine INR {fine.fine_amount}"
    log_activity(db, user=user, action="BOOK_RETURNED", description=detail, request=request)
    db.commit()
    return ReturnResult(loan=LoanRead.model_validate(loan), fine=FineRead.model_validate(fine) if fine else None)


@router.post("/{loan_id}/renew", response_model=LoanRead, summary="Renew a loan")
def renew(loan_id: int, db: DB, user: StaffUser, request: Request):
    loan = circulation.renew_loan(db, loan_id=loan_id)
    log_activity(db, user=user, action="LOAN_RENEWED", description=f"Loan {loan_id} renewed to {loan.due_date}",
                 request=request)
    db.commit()
    return loan


@router.post("/{loan_id}/lost", response_model=ReturnResult, summary="Report a borrowed copy as lost")
def report_lost(loan_id: int, payload: LostRequest, db: DB, user: StaffUser, request: Request):
    loan, fine = circulation.mark_lost(
        db, loan_id=loan_id, replacement_charge=payload.replacement_charge, remarks=payload.remarks
    )
    log_activity(db, user=user, action="BOOK_LOST",
                 description=f"Loan {loan_id} marked lost" + (f", fine INR {fine.fine_amount}" if fine else ""),
                 request=request)
    db.commit()
    return ReturnResult(loan=LoanRead.model_validate(loan), fine=FineRead.model_validate(fine) if fine else None)


@router.post("/maintenance/mark-overdue", response_model=BulkUpdateResult,
             summary="Flag issued loans past their due date as Overdue")
def mark_overdue(db: DB, user: StaffUser, request: Request):
    """Run daily (cron) or on demand."""
    updated = circulation.refresh_overdue_statuses(db)
    log_activity(db, user=user, action="OVERDUE_REFRESH", description=f"{updated} loan(s) marked overdue",
                 request=request)
    db.commit()
    return BulkUpdateResult(updated=updated)
