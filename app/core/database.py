from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# pool_pre_ping + pool_recycle keep connections healthy when Neon scales compute to zero.
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    echo=settings.debug,
    # Neon's pooled endpoint runs PgBouncer in transaction mode: disable psycopg's
    # automatic server-side prepared statements so they can't land on another backend.
    connect_args={"prepare_threshold": None},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
