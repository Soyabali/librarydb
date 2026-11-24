from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import today as local_today
from app.core.deps import DB, StaffUser
from app.core.exceptions import BadRequest, NotFound
from app.models import AcademicCourse, Department, Fine, Loan, Member, Reservation
from app.routers.loans import detail_transformer, loan_detail_query
from app.schemas.circulation import FineRead, LoanDetail, ReservationRead
from app.schemas.common import MemberType, Page
from app.schemas.people import MemberCreate, MemberRead, MemberSummary, MemberUpdate
from app.services import circulation
from app.services import library_settings as cfg
from app.services.activity import log_activity
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/members", tags=["Members"])


def _get_member(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise NotFound("Member", member_id)
    return member


def _check_refs(db: Session, course_id: int | None, department_id: int | None) -> None:
    if course_id is not None and db.get(AcademicCourse, course_id) is None:
        raise BadRequest(f"Course {course_id} does not exist")
    if department_id is not None and db.get(Department, department_id) is None:
        raise BadRequest(f"Department {department_id} does not exist")


@router.get("", response_model=Page[MemberRead], summary="List / search members")
def list_members(
    db: DB,
    _: StaffUser,
    pagination: Pagination,
    q: Annotated[str | None, Query(description="Name, email, phone or enrollment no.")] = None,
    member_type: MemberType | None = None,
    department_id: int | None = None,
    course_id: int | None = None,
    is_active: bool | None = None,
):
    stmt = select(Member).order_by(Member.full_name)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Member.full_name.ilike(like), Member.email.ilike(like),
                Member.phone.ilike(like), Member.enrollment_no.ilike(like))
        )
    if member_type is not None:
        stmt = stmt.where(Member.member_type == member_type)
    if department_id is not None:
        stmt = stmt.where(Member.department_id == department_id)
    if course_id is not None:
        stmt = stmt.where(Member.course_id == course_id)
    if is_active is not None:
        stmt = stmt.where(Member.is_active.is_(is_active))
    return paginate(db, stmt, pagination)


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED, summary="Register a member")
def create_member(payload: MemberCreate, db: DB, user: StaffUser, request: Request):
    _check_refs(db, payload.course_id, payload.department_id)
    data = payload.model_dump(exclude_none=True)
    if "email" in data:
        data["email"] = data["email"].lower()
    member = Member(**data, is_active=True)
    db.add(member)
    db.flush()
    log_activity(db, user=user, action="MEMBER_CREATED",
                 description=f"Registered member {member.member_id} ({member.full_name})", request=request)
    db.commit()
    db.refresh(member)
    return member


@router.get("/{member_id}", response_model=MemberRead, summary="Get a member")
def get_member(member_id: int, db: DB, _: StaffUser):
    return _get_member(db, member_id)


@router.get("/{member_id}/summary", response_model=MemberSummary, summary="Borrowing status of a member")
def member_summary(member_id: int, db: DB, _: StaffUser):
    member = _get_member(db, member_id)
    today = local_today()
    active = circulation.active_loan_count(db, member_id)
    limit = cfg.borrow_limit(db, member.member_type)
    overdue = db.scalar(
        select(func.count()).where(
            Loan.member_id == member_id, Loan.status.in_(circulation.ACTIVE_LOAN_STATUSES), Loan.due_date < today
        )
    ) or 0
    owed = circulation.outstanding_fines(db, member_id)
    pending = db.scalar(
        select(func.count()).where(Reservation.member_id == member_id, Reservation.status == "Pending")
    ) or 0
    membership_ok = bool(member.is_active) and not (member.membership_end and member.membership_end < today)
    return MemberSummary(
        member=MemberRead.model_validate(member),
        active_loans=active,
        borrow_limit=limit,
        overdue_loans=overdue,
        outstanding_fines=owed,
        pending_reservations=pending,
        can_borrow=membership_ok and active < limit and overdue == 0 and owed == 0,
    )


@router.get("/{member_id}/loans", response_model=Page[LoanDetail], summary="Loan history of a member")
def member_loans(member_id: int, db: DB, _: StaffUser, pagination: Pagination, active_only: bool = False):
    _get_member(db, member_id)
    stmt = loan_detail_query().where(Loan.member_id == member_id)
    if active_only:
        stmt = stmt.where(Loan.status.in_(circulation.ACTIVE_LOAN_STATUSES))
    stmt = stmt.order_by(Loan.issue_date.desc(), Loan.loan_id.desc())
    return paginate(db, stmt, pagination, scalars=False, transform=detail_transformer(db))


@router.get("/{member_id}/fines", response_model=list[FineRead], summary="Fines of a member")
def member_fines(member_id: int, db: DB, _: StaffUser, unpaid_only: bool = False):
    _get_member(db, member_id)
    stmt = select(Fine).where(Fine.member_id == member_id).order_by(Fine.fine_date.desc())
    if unpaid_only:
        stmt = stmt.where(Fine.is_paid.is_not(True))
    return db.scalars(stmt).all()


@router.get("/{member_id}/reservations", response_model=list[ReservationRead], summary="Reservations of a member")
def member_reservations(member_id: int, db: DB, _: StaffUser):
    _get_member(db, member_id)
    return db.scalars(
        select(Reservation).where(Reservation.member_id == member_id).order_by(Reservation.reserved_on.desc())
    ).all()


@router.patch("/{member_id}", response_model=MemberRead, summary="Update a member")
def update_member(member_id: int, payload: MemberUpdate, db: DB, user: StaffUser, request: Request):
    member = _get_member(db, member_id)
    data = payload.model_dump(exclude_unset=True)
    _check_refs(db, data.get("course_id"), data.get("department_id"))
    if data.get("email"):
        data["email"] = data["email"].lower()
    for key, value in data.items():
        setattr(member, key, value)
    start, end = member.membership_start, member.membership_end
    if start and end and end < start:
        raise BadRequest("membership_end must be on or after membership_start")
    log_activity(db, user=user, action="MEMBER_UPDATED", description=f"Updated member {member_id}", request=request)
    db.commit()
    return member


@router.delete("/{member_id}", response_model=MemberRead, summary="Deactivate a member")
def deactivate_member(member_id: int, db: DB, user: StaffUser, request: Request):
    """Members are never hard-deleted (their loan and fine history must stay). This sets `is_active=false`.
    Blocked while the member still holds books."""
    member = _get_member(db, member_id)
    if circulation.active_loan_count(db, member_id):
        raise BadRequest("Member still has books on loan")
    member.is_active = False
    log_activity(db, user=user, action="MEMBER_DEACTIVATED", description=f"Deactivated member {member_id}",
                 request=request)
    db.commit()
    return member
