"""Typed access to the library_settings table (fine rate, loan period, borrowing limits...)."""

from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LibrarySetting

DEFAULTS: dict[str, str] = {
    "fine_per_day_inr": "10",
    "max_books_student": "3",
    "max_books_faculty": "10",
    "max_books_staff": "3",
    "loan_period_days": "14",
    "reservation_expiry_days": "7",
}

# Settings whose value must be a non-negative integer.
INTEGER_KEYS = {
    "max_books_student",
    "max_books_faculty",
    "max_books_staff",
    "loan_period_days",
    "reservation_expiry_days",
}
DECIMAL_KEYS = {"fine_per_day_inr"}


def get_raw(db: Session, key: str) -> str | None:
    value = db.scalar(select(LibrarySetting.setting_value).where(LibrarySetting.setting_key == key))
    return value if value is not None else DEFAULTS.get(key)


def get_int(db: Session, key: str) -> int:
    raw = get_raw(db, key)
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(DEFAULTS[key])


def get_decimal(db: Session, key: str) -> Decimal:
    raw = get_raw(db, key)
    try:
        return Decimal(raw)  # type: ignore[arg-type]
    except (TypeError, InvalidOperation):
        return Decimal(DEFAULTS[key])


def borrow_limit(db: Session, member_type: str) -> int:
    # Staff uses max_books_staff if that setting exists, otherwise the default above.
    key = {"Faculty": "max_books_faculty", "Staff": "max_books_staff"}.get(member_type, "max_books_student")
    return get_int(db, key)


def validate_value(key: str, value: str) -> str | None:
    """Return an error message if the value is invalid for this key."""
    if key in INTEGER_KEYS:
        if not value.isdigit():
            return f"{key} must be a non-negative whole number"
    if key in DECIMAL_KEYS:
        try:
            if Decimal(value) < 0:
                return f"{key} must not be negative"
        except InvalidOperation:
            return f"{key} must be a number"
    return None
