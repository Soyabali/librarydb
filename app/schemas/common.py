from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Money is serialised as a 2-decimal string ("50.00") so no precision is lost in JSON.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    return_type=str, when_used="json"),
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class Message(BaseModel):
    detail: str


class MemberType(StrEnum):
    STUDENT = "Student"
    FACULTY = "Faculty"
    STAFF = "Staff"


class Gender(StrEnum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"


class CopyCondition(StrEnum):
    NEW = "New"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    LOST = "Lost"


class LoanStatus(StrEnum):
    ISSUED = "Issued"
    RETURNED = "Returned"
    OVERDUE = "Overdue"
    LOST = "Lost"


class ReservationStatus(StrEnum):
    PENDING = "Pending"
    FULFILLED = "Fulfilled"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"
