"""ORM mappings for the existing Neon schema. The tables already exist - these classes only map them."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

book_authors = Table(
    "book_authors",
    Base.metadata,
    Column("book_id", ForeignKey("books.book_id"), primary_key=True),
    Column("author_id", ForeignKey("authors.author_id"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.role_id"))
    full_name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default="true")
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    role: Mapped[Role] = relationship(lazy="joined")

    @property
    def role_name(self) -> str:
        return self.role.role_name


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    action: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String)
    logged_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class Department(Base):
    __tablename__ = "departments"

    department_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_name: Mapped[str] = mapped_column(String, unique=True)
    hod_name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class AcademicCourse(Base):
    __tablename__ = "academic_courses"

    course_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.department_id"))
    course_name: Mapped[str] = mapped_column(String)
    course_code: Mapped[str] = mapped_column(String, unique=True)
    duration_years: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class Publisher(Base):
    __tablename__ = "publishers"

    publisher_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publisher_name: Mapped[str] = mapped_column(String, unique=True)
    city: Mapped[str | None] = mapped_column(String)
    country: Mapped[str | None] = mapped_column(String, server_default="India")
    website: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class Author(Base):
    __tablename__ = "authors"

    author_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String)
    bio: Mapped[str | None] = mapped_column(Text)
    nationality: Mapped[str | None] = mapped_column(String, server_default="Indian")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class Book(Base):
    __tablename__ = "books"

    book_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.category_id"))
    publisher_id: Mapped[int] = mapped_column(ForeignKey("publishers.publisher_id"))
    title: Mapped[str] = mapped_column(String)
    isbn: Mapped[str | None] = mapped_column(String, unique=True)
    edition: Mapped[str | None] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String, server_default="English")
    total_pages: Mapped[int | None] = mapped_column(Integer)
    published_year: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    category: Mapped[Category] = relationship(lazy="joined")
    publisher: Mapped[Publisher] = relationship(lazy="joined")
    authors: Mapped[list[Author]] = relationship(secondary=book_authors, lazy="selectin", order_by=Author.full_name)
    copies: Mapped[list["BookCopy"]] = relationship(back_populates="book", lazy="raise", order_by="BookCopy.copy_id")


class BookCopy(Base):
    __tablename__ = "book_copies"

    copy_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.book_id"))
    accession_no: Mapped[str] = mapped_column(String, unique=True)
    condition: Mapped[str | None] = mapped_column(String, server_default="Good")
    is_available: Mapped[bool | None] = mapped_column(Boolean, server_default="true")
    shelf_location: Mapped[str | None] = mapped_column(String)
    added_on: Mapped[date | None] = mapped_column(Date, server_default=func.current_date())

    book: Mapped[Book] = relationship(back_populates="copies", lazy="raise")


class Member(Base):
    __tablename__ = "members"

    member_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("academic_courses.course_id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.department_id"))
    full_name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, unique=True)
    phone: Mapped[str | None] = mapped_column(String)
    member_type: Mapped[str] = mapped_column(String)
    enrollment_no: Mapped[str | None] = mapped_column(String, unique=True)
    gender: Mapped[str | None] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(Text)
    membership_start: Mapped[date | None] = mapped_column(Date, server_default=func.current_date())
    membership_end: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class Loan(Base):
    __tablename__ = "loans"

    loan_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    copy_id: Mapped[int] = mapped_column(ForeignKey("book_copies.copy_id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.member_id"))
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    issue_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    due_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String, server_default="Issued")
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    copy: Mapped[BookCopy] = relationship(lazy="raise")
    member: Mapped[Member] = relationship(lazy="raise")


class Fine(Base):
    __tablename__ = "fines"

    fine_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.loan_id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.member_id"))
    fine_amount: Mapped[Decimal] = mapped_column(Numeric)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric, server_default="0")
    fine_reason: Mapped[str | None] = mapped_column(String)
    is_paid: Mapped[bool | None] = mapped_column(Boolean, server_default="false")
    fine_date: Mapped[date | None] = mapped_column(Date, server_default=func.current_date())
    paid_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    @property
    def balance(self) -> Decimal:
        return Decimal(self.fine_amount) - Decimal(self.paid_amount or 0)


class Reservation(Base):
    __tablename__ = "reservations"

    reservation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.book_id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.member_id"))
    reserved_on: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String, server_default="Pending")


class LibrarySetting(Base):
    __tablename__ = "library_settings"

    setting_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String, unique=True)
    setting_value: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
