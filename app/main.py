import logging
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import CONSTRAINT_MESSAGES
from app.routers import (
    auth,
    books,
    copies,
    fines,
    loans,
    members,
    reference,
    reports,
    reservations,
    settings,
    users,
)

config = get_settings()
logging.basicConfig(level=logging.DEBUG if config.debug else logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("library")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        logger.info("Connected to the database")
    except OperationalError:
        logger.exception("Database is not reachable at startup")
    yield
    engine.dispose()


app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description=(
        "REST API for a college library: catalogue, copies, members, circulation (issue / return / "
        "renew / lost), fines, reservations, reports and audit logs.\n\n"
        "**Auth:** `POST /api/v1/auth/login` with a staff email + password, then click *Authorize*."
    ),
    lifespan=lifespan,
)

if config.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


# ---------- error handling ----------


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint in CONSTRAINT_MESSAGES:
        detail = CONSTRAINT_MESSAGES[constraint]
    elif getattr(exc.orig, "sqlstate", None) == "23503":
        detail = "This record is referenced by (or references) other records and the change is not allowed"
    else:
        detail = getattr(diag, "message_primary", None) or "The change violates a database constraint"
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": detail, "constraint": constraint})


@app.exception_handler(OperationalError)
async def db_unavailable_handler(_: Request, exc: OperationalError):
    logger.error("Database unavailable: %s", exc)
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        content={"detail": "Database is temporarily unavailable, please retry"})


@app.exception_handler(DBAPIError)
async def db_error_handler(_: Request, exc: DBAPIError):
    logger.exception("Database error")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "Unexpected database error"})


# ---------- routes ----------


@app.get("/", include_in_schema=False)
def root():
    return {"name": config.app_name, "version": config.app_version, "docs": "/docs"}


@app.get("/health", tags=["System"], summary="Liveness + database check")
def health():
    started = time.perf_counter()
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok", "database": "ok", "db_latency_ms": round((time.perf_counter() - started) * 1000, 1)}


api = APIRouter(prefix="/api/v1")
for module in (auth, users, books, copies, members, loans, fines, reservations, reports, settings):
    api.include_router(module.router)
for router in reference.routers:
    api.include_router(router)
app.include_router(api)
