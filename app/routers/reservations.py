from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select

from app.core.deps import DB, StaffUser
from app.core.exceptions import NotFound
from app.models import Reservation
from app.schemas.circulation import BulkUpdateResult, ReservationCreate, ReservationRead
from app.schemas.common import Page, ReservationStatus
from app.services import circulation
from app.services.activity import log_activity
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/reservations", tags=["Reservations"])


@router.get("", response_model=Page[ReservationRead], summary="List reservations (queue order)")
def list_reservations(
    db: DB,
    _: StaffUser,
    pagination: Pagination,
    status_: Annotated[ReservationStatus | None, Query(alias="status")] = None,
    book_id: int | None = None,
    member_id: int | None = None,
):
    stmt = select(Reservation).order_by(Reservation.reserved_on.asc(), Reservation.reservation_id)
    if status_ is not None:
        stmt = stmt.where(Reservation.status == status_)
    if book_id is not None:
        stmt = stmt.where(Reservation.book_id == book_id)
    if member_id is not None:
        stmt = stmt.where(Reservation.member_id == member_id)
    return paginate(db, stmt, pagination)


@router.post("", response_model=ReservationRead, status_code=status.HTTP_201_CREATED, summary="Reserve a book")
def create(payload: ReservationCreate, db: DB, user: StaffUser, request: Request):
    reservation = circulation.create_reservation(db, book_id=payload.book_id, member_id=payload.member_id)
    log_activity(db, user=user, action="RESERVATION_CREATED",
                 description=f"Member {payload.member_id} reserved book {payload.book_id}", request=request)
    db.commit()
    db.refresh(reservation)
    return reservation


@router.get("/{reservation_id}", response_model=ReservationRead, summary="Get a reservation")
def get_reservation(reservation_id: int, db: DB, _: StaffUser):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise NotFound("Reservation", reservation_id)
    return reservation


@router.post("/{reservation_id}/cancel", response_model=ReservationRead, summary="Cancel a reservation")
def cancel(reservation_id: int, db: DB, user: StaffUser, request: Request):
    reservation = circulation.cancel_reservation(db, reservation_id=reservation_id)
    log_activity(db, user=user, action="RESERVATION_CANCELLED",
                 description=f"Reservation {reservation_id} cancelled", request=request)
    db.commit()
    return reservation


@router.post("/maintenance/expire", response_model=BulkUpdateResult, summary="Expire stale reservations")
def expire(db: DB, user: StaffUser, request: Request):
    updated = circulation.expire_reservations(db)
    log_activity(db, user=user, action="RESERVATIONS_EXPIRED", description=f"{updated} reservation(s) expired",
                 request=request)
    db.commit()
    return BulkUpdateResult(updated=updated)
