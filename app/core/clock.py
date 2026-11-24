"""The library's local calendar. Servers (e.g. Render) run on UTC, but due dates and fines must follow
the library's own day, so every business date comes from here instead of date.today()."""

from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import get_settings


@lru_cache
def library_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def today() -> date:
    return datetime.now(library_tz()).date()
