from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.common import Gender, MemberType, Money, ORMModel

# ---------- Departments & courses ----------


class DepartmentCreate(BaseModel):
    department_name: str = Field(min_length=1, max_length=100)
    hod_name: str | None = None


class DepartmentUpdate(BaseModel):
    department_name: str | None = Field(default=None, min_length=1, max_length=100)
    hod_name: str | None = None


class DepartmentRead(ORMModel):
    department_id: int
    department_name: str
    hod_name: str | None
    created_at: datetime | None


class CourseCreate(BaseModel):
    department_id: int
    course_name: str = Field(min_length=1, max_length=150)
    course_code: str = Field(min_length=1, max_length=20)
    duration_years: int | None = Field(default=None, ge=1, le=6)


class CourseUpdate(BaseModel):
    department_id: int | None = None
    course_name: str | None = Field(default=None, min_length=1, max_length=150)
    course_code: str | None = Field(default=None, min_length=1, max_length=20)
    duration_years: int | None = Field(default=None, ge=1, le=6)


class CourseRead(ORMModel):
    course_id: int
    department_id: int
    course_name: str
    course_code: str
    duration_years: int | None
    created_at: datetime | None


# ---------- Members ----------


class MemberBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    member_type: MemberType
    enrollment_no: str | None = Field(default=None, max_length=50)
    gender: Gender | None = None
    address: str | None = None
    course_id: int | None = None
    department_id: int | None = None
    membership_start: date | None = None
    membership_end: date | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.membership_start and self.membership_end and self.membership_end < self.membership_start:
            raise ValueError("membership_end must be on or after membership_start")
        return self


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    member_type: MemberType | None = None
    enrollment_no: str | None = Field(default=None, max_length=50)
    gender: Gender | None = None
    address: str | None = None
    course_id: int | None = None
    department_id: int | None = None
    membership_start: date | None = None
    membership_end: date | None = None
    is_active: bool | None = None


class MemberRead(ORMModel):
    member_id: int
    full_name: str
    email: str | None
    phone: str | None
    member_type: str
    enrollment_no: str | None
    gender: str | None
    address: str | None
    course_id: int | None
    department_id: int | None
    membership_start: date | None
    membership_end: date | None
    is_active: bool | None
    created_at: datetime | None


class MemberSummary(BaseModel):
    member: MemberRead
    active_loans: int
    borrow_limit: int
    overdue_loans: int
    outstanding_fines: Money
    pending_reservations: int
    can_borrow: bool


# ---------- Staff users ----------


class RoleRead(ORMModel):
    role_id: int
    role_name: str
    description: str | None


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone: str | None = None
    role_id: int


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = None
    role_id: int | None = None
    is_active: bool | None = None


class UserRead(ORMModel):
    user_id: int
    full_name: str
    email: str
    phone: str | None
    role_id: int
    role_name: str
    is_active: bool | None
    last_login: datetime | None
    created_at: datetime | None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=72)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
