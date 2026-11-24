from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import Money, ORMModel


class DashboardStats(BaseModel):
    total_titles: int
    total_copies: int
    available_copies: int
    lost_copies: int
    active_members: int
    active_loans: int
    overdue_loans: int
    loans_issued_today: int
    returns_today: int
    pending_reservations: int
    outstanding_fines: Money
    fines_collected: Money


class OverdueItem(BaseModel):
    loan_id: int
    member_id: int
    member_name: str
    member_phone: str | None
    member_email: str | None
    book_title: str
    accession_no: str
    issue_date: date
    due_date: date
    days_overdue: int
    estimated_fine: Money


class PopularBook(BaseModel):
    book_id: int
    title: str
    times_borrowed: int


class TopBorrower(BaseModel):
    member_id: int
    full_name: str
    member_type: str
    times_borrowed: int


class CategoryStat(BaseModel):
    category_id: int
    category_name: str
    titles: int
    copies: int
    loans: int


class ActivityLogRead(ORMModel):
    log_id: int
    user_id: int | None
    action: str
    description: str | None
    ip_address: str | None
    logged_at: datetime | None


class SettingRead(ORMModel):
    setting_key: str
    setting_value: str
    description: str | None
    updated_at: datetime | None


class SettingUpdate(BaseModel):
    setting_value: str
