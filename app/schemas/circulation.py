from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import CopyCondition, Money, ORMModel

# ---------- Loans ----------


class IssueRequest(BaseModel):
    member_id: int
    copy_id: int | None = Field(default=None, description="Specific copy to issue")
    accession_no: str | None = Field(default=None, description="Alternative to copy_id (barcode scan)")
    due_date: date | None = Field(default=None, description="Defaults to today + loan_period_days")
    remarks: str | None = None


class ReturnRequest(BaseModel):
    condition: CopyCondition | None = Field(default=None, description="Condition of the copy on return")
    remarks: str | None = None


class LostRequest(BaseModel):
    replacement_charge: Decimal = Field(ge=0, description="Charged in addition to any overdue fine")
    remarks: str | None = None


class LoanRead(ORMModel):
    loan_id: int
    copy_id: int
    member_id: int
    issued_by: int
    issue_date: date
    due_date: date
    return_date: date | None
    status: str | None
    remarks: str | None
    created_at: datetime | None


class LoanDetail(LoanRead):
    book_id: int
    book_title: str
    accession_no: str
    member_name: str
    days_overdue: int
    estimated_fine: Money


class FineRead(ORMModel):
    fine_id: int
    loan_id: int
    member_id: int
    fine_amount: Money
    paid_amount: Money | None
    balance: Money
    fine_reason: str | None
    is_paid: bool | None
    fine_date: date | None
    paid_date: date | None
    created_at: datetime | None


class ReturnResult(BaseModel):
    loan: LoanRead
    fine: FineRead | None = None


class FinePayment(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


# ---------- Reservations ----------


class ReservationCreate(BaseModel):
    book_id: int
    member_id: int


class ReservationRead(ORMModel):
    reservation_id: int
    book_id: int
    member_id: int
    reserved_on: datetime | None
    expiry_date: date | None
    status: str | None


class BulkUpdateResult(BaseModel):
    updated: int
