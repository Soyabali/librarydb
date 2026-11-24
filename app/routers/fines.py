from datetime import date

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core.deps import DB, StaffUser
from app.core.exceptions import NotFound
from app.models import Fine
from app.schemas.circulation import FinePayment, FineRead
from app.schemas.common import Page
from app.services import circulation
from app.services.activity import log_activity
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/fines", tags=["Fines"])


@router.get("", response_model=Page[FineRead], summary="List fines")
def list_fines(
    db: DB,
    _: StaffUser,
    pagination: Pagination,
    member_id: int | None = None,
    is_paid: bool | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    stmt = select(Fine).order_by(Fine.fine_date.desc(), Fine.fine_id.desc())
    if member_id is not None:
        stmt = stmt.where(Fine.member_id == member_id)
    if is_paid is True:
        stmt = stmt.where(Fine.is_paid.is_(True))
    elif is_paid is False:
        stmt = stmt.where(Fine.is_paid.is_not(True))
    if from_date:
        stmt = stmt.where(Fine.fine_date >= from_date)
    if to_date:
        stmt = stmt.where(Fine.fine_date <= to_date)
    return paginate(db, stmt, pagination)


@router.get("/{fine_id}", response_model=FineRead, summary="Get a fine")
def get_fine(fine_id: int, db: DB, _: StaffUser):
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise NotFound("Fine", fine_id)
    return fine


@router.post("/{fine_id}/pay", response_model=FineRead, summary="Record a (partial) payment")
def pay(fine_id: int, payload: FinePayment, db: DB, user: StaffUser, request: Request):
    fine = circulation.pay_fine(db, fine_id=fine_id, amount=payload.amount)
    log_activity(db, user=user, action="FINE_PAID",
                 description=f"INR {payload.amount} received for fine {fine_id} (member {fine.member_id})",
                 request=request)
    db.commit()
    return fine
