"""Calendar-month parsing, open-window enforcement, and institutional clock for QTA (Phase 4, Q3).

RULE-QTA-01 / FR-QTA-010: quota cycles are strictly monthly (YYYY-MM).
``utc_now()`` is the single clock helper used across QTA so tests can freeze time cleanly.
"""

import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.core.config import Settings

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def utc_now() -> datetime:
    """Return the current UTC timestamp (single clock seam for QTA)."""
    return datetime.now(UTC)


def institution_tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.institution_timezone)


def current_month(settings: Settings) -> date:
    """First day of the current calendar month in the institution's local timezone."""
    local = utc_now().astimezone(institution_tz(settings))
    return date(local.year, local.month, 1)


def following_month(month: date) -> date:
    """First day of the calendar month immediately following ``month``."""
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def next_month(settings: Settings) -> date:
    """First day of the calendar month immediately following the institution's current month."""
    return following_month(current_month(settings))


def format_month(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def parse_month(value: str) -> date:
    """Parse strict ``YYYY-MM`` into the first day of that month or raise QTA_INVALID_PERIOD."""
    if not isinstance(value, str) or not MONTH_RE.fullmatch(value):
        raise DomainError(ErrorCode.QTA_INVALID_PERIOD)
    try:
        return date(int(value[:4]), int(value[5:7]), 1)
    except ValueError:
        raise DomainError(ErrorCode.QTA_INVALID_PERIOD) from None


def is_open_month(month: date, settings: Settings) -> bool:
    """Return True iff ``month`` is the current or immediately following calendar month."""
    cur = current_month(settings)
    return month == cur or month == following_month(cur)


def require_open_month(month: date, settings: Settings) -> date:
    """Require ``month`` to be the current or next month, else raise QTA_PERIOD_NOT_OPEN."""
    if not is_open_month(month, settings):
        raise DomainError(ErrorCode.QTA_PERIOD_NOT_OPEN)
    return month


def resolve_month(raw: str | None, settings: Settings, *, open_only: bool = False) -> date:
    """Default omitted ``month`` to current month; validate format and optionally open window."""
    month = current_month(settings) if raw is None else parse_month(raw)
    if open_only:
        require_open_month(month, settings)
    return month
