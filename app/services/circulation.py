"""Circulation rules: issuing, returning, renewing, fines and reservations.

Every function adds its changes to the session and leaves the commit to the caller, so each
API request is one atomic transaction. Rows that decide availability are locked with
SELECT ... FOR UPDATE so two librarians cannot issue the same copy at the same moment.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.clock import today as local_today
from app.core.exceptions import BadRequest, Conflict, NotFound
from app.models import Book, BookCopy, Fine, Loan, Member, Reservation, User
from app.services import library_settings as cfg

ACTIVE_LOAN_STATUSES = ("Issued", "Overdue")


# ---------- helpers ----------


def days_overdue(loan: Loan, on: date | None = None) -> int:
    end = loan.return_date or on or local_today()
    return max((end - loan.due_date).days, 0)


def estimated_fine(db: Session, loan: Loan) -> Decimal:
    if loan.status not in ACTIVE_LOAN_STATUSES:
        return Decimal(0)
    return days_overdue(loan) * cfg.get_decimal(db, "fine_per_day_inr")


def outstanding_fines(db: Session, member_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(Fine.fine_amount - func.coalesce(Fine.paid_amount, 0)), 0)).where(
            Fine.member_id == member_id, Fine.is_paid.is_not(True)
        )
    )
    return Decimal(value or 0)


def active_loan_count(db: Session, member_id: int) -> int:
    return db.scalar(
        select(func.count()).where(Loan.member_id == member_id, Loan.status.in_(ACTIVE_LOAN_STATUSES))
    ) or 0


def _pending_reservations(db: Session, book_id: int, *, exclude_member: int | None = None):
    today = local_today()
    stmt = select(Reservation).where(
        Reservation.book_id == book_id,
        Reservation.status == "Pending",
        or_(Reservation.expiry_date.is_(None), Reservation.expiry_date >= today),
    )
    if exclude_member is not None:
        stmt = stmt.where(Reservation.member_id != exclude_member)
    return stmt


def _available_copy_count(db: Session, book_id: int) -> int:
    return db.scalar(
        select(func.count()).where(
            BookCopy.book_id == book_id,
            BookCopy.is_available.is_(True),
            BookCopy.condition != "Lost",
        )
    ) or 0


def ensure_member_can_borrow(db: Session, member: Member) -> None:
    today = local_today()
    if not member.is_active:
        raise Conflict(f"Member {member.member_id} is inactive")
    if member.membership_end and member.membership_end < today:
        raise Conflict(f"Membership of member {member.member_id} expired on {member.membership_end}")

    limit = cfg.borrow_limit(db, member.member_type)
    current = active_loan_count(db, member.member_id)
    if current >= limit:
        raise Conflict(f"Borrowing limit reached ({current}/{limit} books for {member.member_type})")

    has_overdue = db.scalar(
        select(func.count()).where(
            Loan.member_id == member.member_id,
            Loan.status.in_(ACTIVE_LOAN_STATUSES),
            Loan.due_date < today,
        )
    )
    if has_overdue:
        raise Conflict("Member has overdue books - they must be returned before a new issue")

    owed = outstanding_fines(db, member.member_id)
    if owed > 0:
        raise Conflict(f"Member has unpaid fines of INR {owed:.2f}")


# ---------- loans ----------


def issue_book(
    db: Session,
    *,
    member_id: int,
    staff: User,
    copy_id: int | None = None,
    accession_no: str | None = None,
    due_date: date | None = None,
    remarks: str | None = None,
) -> Loan:
    if copy_id is None and not accession_no:
        raise BadRequest("Provide either copy_id or accession_no")

    stmt = select(BookCopy).with_for_update()
    stmt = stmt.where(BookCopy.copy_id == copy_id) if copy_id is not None else stmt.where(
        BookCopy.accession_no == accession_no
    )
    copy = db.scalar(stmt)
    if copy is None:
        raise NotFound("Copy", copy_id or accession_no)
    if copy.condition == "Lost":
        raise Conflict(f"Copy {copy.accession_no} is marked as lost")
    if not copy.is_available:
        raise Conflict(f"Copy {copy.accession_no} is already on loan")

    # Locking the member row serialises concurrent issues to the same member (limit check).
    member = db.get(Member, member_id, with_for_update=True)
    if member is None:
        raise NotFound("Member", member_id)
    ensure_member_can_borrow(db, member)

    # Reservations: the member's own pending reservation is fulfilled; otherwise make sure
    # we are not handing out a copy that is being held for someone else.
    own_reservation = db.scalar(
        _pending_reservations(db, copy.book_id).where(Reservation.member_id == member_id)
    )
    if own_reservation is None:
        others_waiting = db.scalar(
            select(func.count()).select_from(
                _pending_reservations(db, copy.book_id, exclude_member=member_id).subquery()
            )
        ) or 0
        if others_waiting and others_waiting >= _available_copy_count(db, copy.book_id):
            raise Conflict("All available copies of this book are held for members with earlier reservations")

    today = local_today()
    due = due_date or today + timedelta(days=cfg.get_int(db, "loan_period_days"))
    if due <= today:
        raise BadRequest("due_date must be after today")

    loan = Loan(
        copy_id=copy.copy_id,
        member_id=member.member_id,
        issued_by=staff.user_id,
        issue_date=today,
        due_date=due,
        status="Issued",
        remarks=remarks,
    )
    copy.is_available = False
    if own_reservation is not None:
        own_reservation.status = "Fulfilled"
    db.add(loan)
    db.flush()
    return loan


def _get_active_loan(db: Session, loan_id: int) -> Loan:
    loan = db.get(Loan, loan_id, with_for_update=True)
    if loan is None:
        raise NotFound("Loan", loan_id)
    if loan.status not in ACTIVE_LOAN_STATUSES:
        raise Conflict(f"Loan {loan_id} is already {loan.status}")
    return loan


def _overdue_fine(db: Session, loan: Loan, on: date) -> Decimal:
    return max((on - loan.due_date).days, 0) * cfg.get_decimal(db, "fine_per_day_inr")


def return_book(
    db: Session, *, loan_id: int, condition: str | None = None, remarks: str | None = None
) -> tuple[Loan, Fine | None]:
    loan = _get_active_loan(db, loan_id)
    today = local_today()

    copy = db.get(BookCopy, loan.copy_id, with_for_update=True)
    assert copy is not None
    if condition:
        copy.condition = condition
    copy.is_available = copy.condition != "Lost"

    loan.return_date = today
    loan.status = "Lost" if copy.condition == "Lost" else "Returned"
    if remarks:
        loan.remarks = f"{loan.remarks}\n{remarks}" if loan.remarks else remarks

    fine = None
    amount = _overdue_fine(db, loan, today)
    if amount > 0:
        late_days = (today - loan.due_date).days
        fine = Fine(
            loan_id=loan.loan_id,
            member_id=loan.member_id,
            fine_amount=amount,
            paid_amount=Decimal(0),
            fine_reason=f"Overdue by {late_days} day(s)",
            is_paid=False,
            fine_date=today,
        )
        db.add(fine)
    db.flush()
    return loan, fine


def mark_lost(db: Session, *, loan_id: int, replacement_charge: Decimal, remarks: str | None) -> tuple[Loan, Fine | None]:
    loan = _get_active_loan(db, loan_id)
    today = local_today()

    copy = db.get(BookCopy, loan.copy_id, with_for_update=True)
    assert copy is not None
    copy.condition = "Lost"
    copy.is_available = False

    loan.status = "Lost"
    loan.return_date = today
    if remarks:
        loan.remarks = f"{loan.remarks}\n{remarks}" if loan.remarks else remarks

    overdue = _overdue_fine(db, loan, today)
    total = replacement_charge + overdue
    fine = None
    if total > 0:
        reason = "Book lost - replacement charge"
        if overdue > 0:
            reason += f" + overdue by {(today - loan.due_date).days} day(s)"
        fine = Fine(
            loan_id=loan.loan_id,
            member_id=loan.member_id,
            fine_amount=total,
            paid_amount=Decimal(0),
            fine_reason=reason,
            is_paid=False,
            fine_date=today,
        )
        db.add(fine)
    db.flush()
    return loan, fine


def renew_loan(db: Session, *, loan_id: int) -> Loan:
    loan = _get_active_loan(db, loan_id)
    today = local_today()
    if loan.due_date < today:
        raise Conflict("Overdue loans cannot be renewed - return the book and settle the fine first")

    copy = db.get(BookCopy, loan.copy_id)
    assert copy is not None
    waiting = db.scalar(
        select(func.count()).select_from(
            _pending_reservations(db, copy.book_id, exclude_member=loan.member_id).subquery()
        )
    )
    if waiting:
        raise Conflict("This book is reserved by another member and cannot be renewed")

    loan.due_date = loan.due_date + timedelta(days=cfg.get_int(db, "loan_period_days"))
    loan.status = "Issued"
    db.flush()
    return loan


def refresh_overdue_statuses(db: Session) -> int:
    result = db.execute(
        update(Loan)
        .where(Loan.status == "Issued", Loan.due_date < local_today())
        .values(status="Overdue")
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


# ---------- fines ----------


def pay_fine(db: Session, *, fine_id: int, amount: Decimal) -> Fine:
    fine = db.get(Fine, fine_id, with_for_update=True)
    if fine is None:
        raise NotFound("Fine", fine_id)
    if fine.is_paid:
        raise Conflict(f"Fine {fine_id} is already fully paid")
    balance = fine.balance
    if amount > balance:
        raise BadRequest(f"Payment exceeds the outstanding balance of INR {balance:.2f}")

    fine.paid_amount = Decimal(fine.paid_amount or 0) + amount
    if fine.paid_amount >= fine.fine_amount:
        fine.is_paid = True
        fine.paid_date = local_today()
    db.flush()
    return fine


# ---------- reservations ----------


def create_reservation(db: Session, *, book_id: int, member_id: int) -> Reservation:
    if db.get(Book, book_id) is None:
        raise NotFound("Book", book_id)
    member = db.get(Member, member_id)
    if member is None:
        raise NotFound("Member", member_id)
    if not member.is_active or (member.membership_end and member.membership_end < local_today()):
        raise Conflict(f"Member {member_id} does not have an active membership")

    if db.scalar(_pending_reservations(db, book_id).where(Reservation.member_id == member_id)):
        raise Conflict("Member already has a pending reservation for this book")

    has_copy = db.scalar(
        select(func.count())
        .select_from(Loan)
        .join(BookCopy, BookCopy.copy_id == Loan.copy_id)
        .where(Loan.member_id == member_id, BookCopy.book_id == book_id, Loan.status.in_(ACTIVE_LOAN_STATUSES))
    )
    if has_copy:
        raise Conflict("Member already has a copy of this book on loan")

    reservation = Reservation(
        book_id=book_id,
        member_id=member_id,
        status="Pending",
        expiry_date=local_today() + timedelta(days=cfg.get_int(db, "reservation_expiry_days")),
    )
    db.add(reservation)
    db.flush()
    return reservation


def cancel_reservation(db: Session, *, reservation_id: int) -> Reservation:
    reservation = db.get(Reservation, reservation_id, with_for_update=True)
    if reservation is None:
        raise NotFound("Reservation", reservation_id)
    if reservation.status != "Pending":
        raise Conflict(f"Reservation {reservation_id} is already {reservation.status}")
    reservation.status = "Cancelled"
    db.flush()
    return reservation


def expire_reservations(db: Session) -> int:
    result = db.execute(
        update(Reservation)
        .where(Reservation.status == "Pending", Reservation.expiry_date < local_today())
        .values(status="Expired")
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0
