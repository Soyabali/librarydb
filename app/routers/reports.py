from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.clock import today as local_today
from app.core.deps import DB, AdminUser, StaffUser
from app.models import (
    ActivityLog,
    Book,
    BookCopy,
    Category,
    Fine,
    Loan,
    Member,
    Reservation,
)
from app.schemas.common import Page
from app.schemas.reports import (
    ActivityLogRead,
    CategoryStat,
    DashboardStats,
    OverdueItem,
    PopularBook,
    TopBorrower,
)
from app.services import library_settings as cfg
from app.services.circulation import ACTIVE_LOAN_STATUSES
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/reports", tags=["Reports"])

Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("/dashboard", response_model=DashboardStats, summary="Headline numbers for the dashboard")
def dashboard(db: DB, _: StaffUser):
    today = local_today()
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731

    copies = db.execute(
        select(
            func.count(),
            func.count().filter(BookCopy.is_available.is_(True), BookCopy.condition != "Lost"),
            func.count().filter(BookCopy.condition == "Lost"),
        ).select_from(BookCopy)
    ).one()
    loans = db.execute(
        select(
            func.count().filter(Loan.status.in_(ACTIVE_LOAN_STATUSES)),
            func.count().filter(Loan.status.in_(ACTIVE_LOAN_STATUSES), Loan.due_date < today),
            func.count().filter(Loan.issue_date == today),
            func.count().filter(Loan.return_date == today),
        ).select_from(Loan)
    ).one()
    fines = db.execute(
        select(
            func.coalesce(
                func.sum(Fine.fine_amount - func.coalesce(Fine.paid_amount, 0)).filter(Fine.is_paid.is_not(True)), 0
            ),
            func.coalesce(func.sum(Fine.paid_amount), 0),
        )
    ).one()

    return DashboardStats(
        total_titles=count(select(func.count()).select_from(Book)),
        total_copies=copies[0],
        available_copies=copies[1],
        lost_copies=copies[2],
        active_members=count(select(func.count()).where(Member.is_active.is_(True))),
        active_loans=loans[0],
        overdue_loans=loans[1],
        loans_issued_today=loans[2],
        returns_today=loans[3],
        pending_reservations=count(select(func.count()).where(Reservation.status == "Pending")),
        outstanding_fines=fines[0],
        fines_collected=fines[1],
    )


@router.get("/overdue", response_model=list[OverdueItem], summary="Overdue books with contact details")
def overdue(db: DB, _: StaffUser):
    today = local_today()
    rate = cfg.get_decimal(db, "fine_per_day_inr")
    rows = db.execute(
        select(Loan, Member, Book.title, BookCopy.accession_no)
        .join(Member, Member.member_id == Loan.member_id)
        .join(BookCopy, BookCopy.copy_id == Loan.copy_id)
        .join(Book, Book.book_id == BookCopy.book_id)
        .where(Loan.status.in_(ACTIVE_LOAN_STATUSES), Loan.due_date < today)
        .order_by(Loan.due_date)
    ).all()
    items = []
    for loan, member, title, accession_no in rows:
        late = (today - loan.due_date).days
        items.append(
            OverdueItem(
                loan_id=loan.loan_id,
                member_id=member.member_id,
                member_name=member.full_name,
                member_phone=member.phone,
                member_email=member.email,
                book_title=title,
                accession_no=accession_no,
                issue_date=loan.issue_date,
                due_date=loan.due_date,
                days_overdue=late,
                estimated_fine=late * rate,
            )
        )
    return items


@router.get("/popular-books", response_model=list[PopularBook], summary="Most borrowed titles")
def popular_books(db: DB, _: StaffUser, limit: Limit = 10, since: date | None = None):
    stmt = (
        select(Book.book_id, Book.title, func.count(Loan.loan_id).label("times_borrowed"))
        .join(BookCopy, BookCopy.book_id == Book.book_id)
        .join(Loan, Loan.copy_id == BookCopy.copy_id)
        .group_by(Book.book_id, Book.title)
        .order_by(func.count(Loan.loan_id).desc(), Book.title)
        .limit(limit)
    )
    if since:
        stmt = stmt.where(Loan.issue_date >= since)
    return [PopularBook(**row._mapping) for row in db.execute(stmt)]


@router.get("/top-borrowers", response_model=list[TopBorrower], summary="Most active members")
def top_borrowers(db: DB, _: StaffUser, limit: Limit = 10, since: date | None = None):
    stmt = (
        select(Member.member_id, Member.full_name, Member.member_type,
               func.count(Loan.loan_id).label("times_borrowed"))
        .join(Loan, Loan.member_id == Member.member_id)
        .group_by(Member.member_id)
        .order_by(func.count(Loan.loan_id).desc(), Member.full_name)
        .limit(limit)
    )
    if since:
        stmt = stmt.where(Loan.issue_date >= since)
    return [TopBorrower(**row._mapping) for row in db.execute(stmt)]


@router.get("/categories", response_model=list[CategoryStat], summary="Collection and usage by category")
def category_stats(db: DB, _: StaffUser):
    titles = select(Book.category_id, func.count().label("n")).group_by(Book.category_id).subquery()
    copies = (
        select(Book.category_id, func.count(BookCopy.copy_id).label("n"))
        .join(BookCopy, BookCopy.book_id == Book.book_id)
        .group_by(Book.category_id)
        .subquery()
    )
    loans = (
        select(Book.category_id, func.count(Loan.loan_id).label("n"))
        .join(BookCopy, BookCopy.book_id == Book.book_id)
        .join(Loan, Loan.copy_id == BookCopy.copy_id)
        .group_by(Book.category_id)
        .subquery()
    )
    stmt = (
        select(
            Category.category_id,
            Category.category_name,
            func.coalesce(titles.c.n, 0).label("titles"),
            func.coalesce(copies.c.n, 0).label("copies"),
            func.coalesce(loans.c.n, 0).label("loans"),
        )
        .outerjoin(titles, titles.c.category_id == Category.category_id)
        .outerjoin(copies, copies.c.category_id == Category.category_id)
        .outerjoin(loans, loans.c.category_id == Category.category_id)
        .order_by(Category.category_name)
    )
    return [CategoryStat(**row._mapping) for row in db.execute(stmt)]


@router.get("/activity-logs", response_model=Page[ActivityLogRead], summary="Audit trail (admin)")
def activity_logs(
    db: DB,
    _: AdminUser,
    pagination: Pagination,
    user_id: int | None = None,
    action: str | None = None,
):
    stmt = select(ActivityLog).order_by(ActivityLog.logged_at.desc(), ActivityLog.log_id.desc())
    if user_id is not None:
        stmt = stmt.where(ActivityLog.user_id == user_id)
    if action:
        stmt = stmt.where(ActivityLog.action == action.upper())
    return paginate(db, stmt, pagination)
