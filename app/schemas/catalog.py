from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import CopyCondition, ORMModel

# ---------- Categories ----------


class CategoryCreate(BaseModel):
    category_name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class CategoryUpdate(BaseModel):
    category_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class CategoryRead(ORMModel):
    category_id: int
    category_name: str
    description: str | None
    created_at: datetime | None


# ---------- Publishers ----------


class PublisherCreate(BaseModel):
    publisher_name: str = Field(min_length=1, max_length=150)
    city: str | None = None
    country: str | None = "India"
    website: str | None = None


class PublisherUpdate(BaseModel):
    publisher_name: str | None = Field(default=None, min_length=1, max_length=150)
    city: str | None = None
    country: str | None = None
    website: str | None = None


class PublisherRead(ORMModel):
    publisher_id: int
    publisher_name: str
    city: str | None
    country: str | None
    website: str | None
    created_at: datetime | None


# ---------- Authors ----------


class AuthorCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    bio: str | None = None
    nationality: str | None = "Indian"


class AuthorUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    bio: str | None = None
    nationality: str | None = None


class AuthorRead(ORMModel):
    author_id: int
    full_name: str
    bio: str | None
    nationality: str | None
    created_at: datetime | None


class AuthorBrief(ORMModel):
    author_id: int
    full_name: str


# ---------- Books ----------


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    isbn: str | None = Field(default=None, max_length=20)
    edition: str | None = None
    language: str | None = "English"
    total_pages: int | None = Field(default=None, gt=0)
    published_year: int | None = Field(default=None, ge=1900, le=2100)
    description: str | None = None


class BookCreate(BookBase):
    category_id: int
    publisher_id: int
    author_ids: list[int] = Field(default_factory=list)


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    isbn: str | None = Field(default=None, max_length=20)
    edition: str | None = None
    language: str | None = None
    total_pages: int | None = Field(default=None, gt=0)
    published_year: int | None = Field(default=None, ge=1900, le=2100)
    description: str | None = None
    category_id: int | None = None
    publisher_id: int | None = None
    author_ids: list[int] | None = Field(default=None, description="Replaces the full author list when given")


class CategoryBrief(ORMModel):
    category_id: int
    category_name: str


class PublisherBrief(ORMModel):
    publisher_id: int
    publisher_name: str


class BookRead(ORMModel):
    book_id: int
    title: str
    isbn: str | None
    edition: str | None
    language: str | None
    total_pages: int | None
    published_year: int | None
    description: str | None
    category: CategoryBrief
    publisher: PublisherBrief
    authors: list[AuthorBrief]
    total_copies: int = 0
    available_copies: int = 0
    created_at: datetime | None


# ---------- Copies ----------


class CopyCreate(BaseModel):
    book_id: int
    accession_no: str = Field(min_length=1, max_length=50)
    condition: CopyCondition = CopyCondition.GOOD
    shelf_location: str | None = None


class CopyUpdate(BaseModel):
    accession_no: str | None = Field(default=None, min_length=1, max_length=50)
    condition: CopyCondition | None = None
    shelf_location: str | None = None


class CopyRead(ORMModel):
    copy_id: int
    book_id: int
    accession_no: str
    condition: str | None
    is_available: bool | None
    shelf_location: str | None
    added_on: date | None


class BookDetail(BookRead):
    copies: list[CopyRead] = []
