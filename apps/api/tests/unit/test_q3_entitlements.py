"""Stage Q3 unit tests without a database: calendar-month parsing, open window, timezone & OpenAPI."""

import json
import re
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.core.config import Settings
from aq_uai_api.main import create_app
from aq_uai_api.qta import periods, schemas

FORBIDDEN_INPUT = re.compile(r"period|semester|cycle|price|token|credit|consumption", re.IGNORECASE)


def test_parse_month_accepts_only_calendar_months():
    assert periods.parse_month("2026-01") == date(2026, 1, 1)
    assert periods.parse_month("2026-11") == date(2026, 11, 1)
    assert periods.parse_month("2026-12") == date(2026, 12, 1)
    assert periods.format_month(date(2027, 1, 1)) == "2027-01"

    for invalid in (
        "2026-00",
        "2026-13",
        "2026-1",
        "26-11",
        "HK1-2026",
        "semester",
        "exam",
        "project",
        "2026-11-01",
        " 2026-11",
        "2026-11 ",
        "",
        "0000-01",
    ):
        with pytest.raises(DomainError) as exc:
            periods.parse_month(invalid)
        assert exc.value.code is ErrorCode.QTA_INVALID_PERIOD, invalid


def test_open_window_current_and_next_month_in_institution_timezone(monkeypatch):
    settings = Settings(institution_timezone="Asia/Ho_Chi_Minh")

    # 2026-11-30T17:30Z is already 2026-12-01T00:30+07:00 in Asia/Ho_Chi_Minh -> Dec 2026 & Jan 2027.
    monkeypatch.setattr(periods, "utc_now", lambda: datetime(2026, 11, 30, 17, 30, tzinfo=UTC))
    assert periods.current_month(settings) == date(2026, 12, 1)
    assert periods.next_month(settings) == date(2027, 1, 1)
    assert periods.require_open_month(date(2026, 12, 1), settings) == date(2026, 12, 1)
    assert periods.require_open_month(date(2027, 1, 1), settings) == date(2027, 1, 1)

    for closed in (date(2026, 11, 1), date(2027, 2, 1)):
        with pytest.raises(DomainError) as exc:
            periods.require_open_month(closed, settings)
        assert exc.value.code is ErrorCode.QTA_PERIOD_NOT_OPEN, closed

    # One hour earlier (2026-11-30T16:30Z = 23:30+07:00) is still November 2026 -> Nov & Dec 2026.
    monkeypatch.setattr(periods, "utc_now", lambda: datetime(2026, 11, 30, 16, 30, tzinfo=UTC))
    assert periods.current_month(settings) == date(2026, 11, 1)
    assert periods.next_month(settings) == date(2026, 12, 1)
    with pytest.raises(DomainError) as exc:
        periods.require_open_month(date(2027, 1, 1), settings)
    assert exc.value.code is ErrorCode.QTA_PERIOD_NOT_OPEN


def test_settings_reject_invalid_timezone():
    assert Settings().institution_timezone == "Asia/Ho_Chi_Minh"
    assert Settings(institution_timezone="UTC").institution_timezone == "UTC"
    for invalid in ("", "   ", "Asia/Ho_Chi_Minh ", "Mars/Olympus", "UTC+7"):
        with pytest.raises(ValidationError):
            Settings(institution_timezone=invalid)


def test_q3_openapi_routes_and_month_only_inputs():
    openapi = create_app().openapi()
    qta_paths = {path: set(ops) for path, ops in openapi["paths"].items() if "/qta" in path}

    # Exact Q3 budget and lookup routes; no PATCH or DELETE on budgets.
    assert qta_paths["/api/v1/qta/users"] == {"get"}
    assert qta_paths["/api/v1/qta/users/{user_id}/entitlements"] == {"get"}
    assert qta_paths["/api/v1/qta/budgets"] == {"get"}
    assert qta_paths["/api/v1/qta/budgets/{month}"] == {"put"}
    assert not any(
        op in {"patch", "delete"}
        for path, ops in qta_paths.items()
        if "budget" in path
        for op in ops
    )

    # No cycle/semester/period/price/token/credit/consumption inputs anywhere on Q3 routes.
    for path in (
        "/api/v1/qta/users",
        "/api/v1/qta/users/{user_id}/entitlements",
        "/api/v1/qta/budgets",
        "/api/v1/qta/budgets/{month}",
    ):
        assert not FORBIDDEN_INPUT.search(json.dumps(openapi["paths"][path])), path

    # SetMonthlyBudget strictly rejects unknown fields, non-positive limits, booleans, and invalid dates.
    valid = {
        "total_limit": 10_000,
        "decision_number": " QD-2026-01 ",
        "decision_date": "2026-11-01",
    }
    parsed = schemas.SetMonthlyBudget.model_validate(valid)
    assert parsed.decision_number == "QD-2026-01" and parsed.decision_date == date(2026, 11, 1)

    for invalid in (
        valid | {"cycle": "MONTH"},
        valid | {"semester": "HK1"},
        valid | {"period_month": "2026-11"},
        valid | {"extra": 1},
        valid | {"total_limit": 0},
        valid | {"total_limit": -100},
        valid | {"total_limit": True},
        valid | {"decision_number": ""},
        valid | {"decision_number": "   "},
        {"total_limit": 10_000, "decision_date": "2026-11-01"},
        {"total_limit": 10_000, "decision_number": "QD-1"},
        valid | {"decision_date": None},
        valid | {"decision_date": 20261101},
        valid | {"decision_date": datetime(2026, 11, 1, tzinfo=UTC)},
    ):
        with pytest.raises(ValidationError):
            schemas.SetMonthlyBudget.model_validate(invalid)

    # MonthQuery rejects unknown query parameters.
    assert schemas.MonthQuery.model_validate({}).month is None
    assert schemas.MonthQuery.model_validate({"month": "2026-11"}).month == "2026-11"
    for bad_query in ({"semester": "HK1"}, {"cycle": "exam"}, {"period": "2026-11"}):
        with pytest.raises(ValidationError):
            schemas.MonthQuery.model_validate(bad_query)
