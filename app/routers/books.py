from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import DB, AdminUser, CurrentUser, StaffUser
from app.core.exceptions import BadRequest, Conflict, NotFound
from app.models import Author, Book, BookCopy, Category, Publisher
from app.schemas.catalog import BookCreate, BookDetail, BookRead, BookUpdate, CopyRead
from app.schemas.common import Page
from app.services.activity import log_activity
from app.services.pagination import Pagination, paginate

router = APIRouter(prefix="/books", tags=["Books"])


def _copy_counts():
    return (
        select(
            BookCopy.book_id,
            func.count().label("total"),
            func.count()
            .filter(and_(BookCopy.is_available.is_(True), BookCopy.condition != "Lost"))
            .label("available"),
        )
        .group_by(BookCopy.book_id)
        .subquery()
    )


def _to_read(row) -> BookRead:
    book, total, available = row
    return BookRead.model_validate(book).model_copy(update={"total_copies": total, "available_copies": available})


def _load_book_read(db: Session, book_id: int) -> BookRead:
    counts = _copy_counts()
    row = db.execute(
        select(Book, func.coalesce(counts.c.total, 0), func.coalesce(counts.c.available, 0))
        .outerjoin(counts, counts.c.book_id == Book.book_id)
        .where(Book.book_id == book_id)
    ).first()
    if row is None:
        raise NotFound("Book", book_id)
    return _to_read(row)


def _resolve_authors(db: Session, author_ids: list[int]) -> list[Author]:
    ids = list(dict.fromkeys(author_ids))
    if not ids:
        return []
    authors = db.scalars(select(Author).where(Author.author_id.in_(ids))).all()
    missing = set(ids) - {a.author_id for a in authors}
    if missing:
        raise BadRequest(f"Unknown author_ids: {sorted(missing)}")
    return list(authors)


def _check_refs(db: Session, category_id: int | None, publisher_id: int | None) -> None:
    if category_id is not None and db.get(Category, category_id) is None:
        raise BadRequest(f"Category {category_id} does not exist")
    if publisher_id is not None and db.get(Publisher, publisher_id) is None:
        raise BadRequest(f"Publisher {publisher_id} does not exist")


@router.get("", response_model=Page[BookRead], summary="Search the catalogue")
def list_books(
    db: DB,
    _: CurrentUser,
    pagination: Pagination,
    q: Annotated[str | None, Query(description="Matches title, ISBN or author name")] = None,
    category_id: int | None = None,
    publisher_id: int | None = None,
    author_id: int | None = None,
    language: str | None = None,
    available_only: Annotated[bool, Query(description="Only titles with a copy on the shelf")] = False,
    sort: Annotated[str, Query(pattern="^(title|newest|year)$")] = "title",
):
    counts = _copy_counts()
    total = func.coalesce(counts.c.total, 0)
    available = func.coalesce(counts.c.available, 0)
    stmt = select(Book, total, available).outerjoin(counts, counts.c.book_id == Book.book_id)

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Book.title.ilike(like), Book.isbn.ilike(like), Book.authors.any(Author.full_name.ilike(like)))
        )
    if category_id is not None:
        stmt = stmt.where(Book.category_id == category_id)
    if publisher_id is not None:
        stmt = stmt.where(Book.publisher_id == publisher_id)
    if author_id is not None:
        stmt = stmt.where(Book.authors.any(Author.author_id == author_id))
    if language:
        stmt = stmt.where(Book.language.ilike(language))
    if available_only:
        stmt = stmt.where(available > 0)

    order = {
        "title": Book.title.asc(),
        "newest": Book.created_at.desc(),
        "year": Book.published_year.desc().nulls_last(),
    }[sort]
    stmt = stmt.order_by(order, Book.book_id)
    return paginate(db, stmt, pagination, scalars=False, transform=_to_read)


@router.get("/{book_id}", response_model=BookDetail, summary="Book details with all copies")
def get_book(book_id: int, db: DB, _: CurrentUser):
    book = _load_book_read(db, book_id)
    copies = db.scalars(select(BookCopy).where(BookCopy.book_id == book_id).order_by(BookCopy.copy_id)).all()
    return BookDetail(**book.model_dump(), copies=[CopyRead.model_validate(c) for c in copies])


@router.get("/{book_id}/copies", response_model=list[CopyRead], summary="Copies of a book")
def list_book_copies(book_id: int, db: DB, _: CurrentUser, available_only: bool = False):
    if db.get(Book, book_id) is None:
        raise NotFound("Book", book_id)
    stmt = select(BookCopy).where(BookCopy.book_id == book_id).order_by(BookCopy.copy_id)
    if available_only:
        stmt = stmt.where(BookCopy.is_available.is_(True), BookCopy.condition != "Lost")
    return db.scalars(stmt).all()


@router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED, summary="Add a book title")
def create_book(payload: BookCreate, db: DB, user: StaffUser, request: Request):
    _check_refs(db, payload.category_id, payload.publisher_id)
    data = payload.model_dump(exclude={"author_ids"})
    book = Book(**data)
    book.authors = _resolve_authors(db, payload.author_ids)
    db.add(book)
    db.flush()
    log_activity(db, user=user, action="BOOK_CREATED", description=f"Added book '{book.title}' ({book.book_id})",
                 request=request)
    db.commit()
    return _load_book_read(db, book.book_id)


@router.patch("/{book_id}", response_model=BookRead, summary="Update a book title")
def update_book(book_id: int, payload: BookUpdate, db: DB, user: StaffUser, request: Request):
    book = db.get(Book, book_id)
    if book is None:
        raise NotFound("Book", book_id)
    data = payload.model_dump(exclude_unset=True)
    author_ids = data.pop("author_ids", None)
    _check_refs(db, data.get("category_id"), data.get("publisher_id"))
    for key, value in data.items():
        setattr(book, key, value)
    if author_ids is not None:
        book.authors = _resolve_authors(db, author_ids)
    log_activity(db, user=user, action="BOOK_UPDATED", description=f"Updated book {book_id}", request=request)
    db.commit()
    db.expire_all()
    return _load_book_read(db, book_id)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a book title (admin)")
def delete_book(book_id: int, db: DB, user: AdminUser, request: Request):
    book = db.get(Book, book_id)
    if book is None:
        raise NotFound("Book", book_id)
    if db.scalar(select(func.count()).where(BookCopy.book_id == book_id)):
        raise Conflict("Remove all copies of this book before deleting it")
    book.authors = []
    db.delete(book)
    db.flush()
    log_activity(db, user=user, action="BOOK_DELETED", description=f"Deleted book '{book.title}' ({book_id})",
                 request=request)
    db.commit()
