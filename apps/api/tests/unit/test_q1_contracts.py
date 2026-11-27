"""Stage Q1-R contracts without a database: QTA RBAC shapes, error codes, details, audit & schema."""

import re
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization import policy
from aq_uai_api.authorization.policy import GrantScope, GrantSubject, PermissionCode
from aq_uai_api.db import audit
from aq_uai_api.db.provision import LEGACY_TABLES, QTA_RUNTIME_PRIVILEGES, present_privileges
from aq_uai_api.main import create_app
from aq_uai_api.qta import models as qta_models

QTA_CODES = [
    "QTA_BUDGET_BELOW_ALLOCATED",
    "QTA_INVALID_PERIOD",
    "QTA_GROUP_NOT_ELIGIBLE",
    "QTA_MODEL_NOT_ELIGIBLE",
    "QTA_USER_ALREADY_SUSPENDED",
    "QTA_USER_NOT_SUSPENDED",
    "QTA_RESET_ALREADY_EXECUTED",
    "QTA_DUPLICATE",
    "QTA_PERIOD_NOT_OPEN",
]
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def test_qta_permissions_and_role_shapes_are_strictly_bounded():
    assert PermissionCode.QTA_READ == "qta.read" and PermissionCode.QTA_MANAGE == "qta.manage"
    assert PermissionCode.QTA_MANAGE in policy._CENTRAL_PERMISSIONS
    assert PermissionCode.QTA_READ not in policy._CENTRAL_PERMISSIONS
    valid = policy._valid_shape
    assert valid("AI_QUOTA_ADMIN", GrantSubject.USER, GrantScope.GLOBAL, None)
    assert not valid("AI_QUOTA_ADMIN", GrantSubject.USER, GrantScope.UNIT, uuid4())
    assert valid("AI_QUOTA_VIEWER", GrantSubject.USER, GrantScope.GLOBAL, None)
    assert valid("AI_QUOTA_VIEWER", GrantSubject.USER, GrantScope.UNIT, uuid4())
    for role in ("AI_QUOTA_ADMIN", "AI_QUOTA_VIEWER"):
        for scope, unit in ((GrantScope.GLOBAL, None), (GrantScope.UNIT, uuid4())):
            assert not valid(role, GrantSubject.GROUP, scope, unit)


def test_qta_error_codes_are_appended_after_mdl_codes():
    names = [code.name for code in ErrorCode]
    assert names[-len(QTA_CODES) :] == QTA_CODES
    assert len({code.value for code in ErrorCode}) == len(names)


def test_numeric_error_details_accept_non_negative_ints_and_reject_invalid_values():
    err = DomainError(
        ErrorCode.QTA_BUDGET_BELOW_ALLOCATED, {"deficit": 25_000, "allocated": 125_000}
    )
    assert err.details == {"deficit": 25_000, "allocated": 125_000}
    assert DomainError(ErrorCode.QTA_BUDGET_BELOW_ALLOCATED, {"deficit": 0}).details == {
        "deficit": 0
    }
    for invalid in (
        {"deficit": -1},
        {"deficit": True},
        {"deficit": "100"},
        {"deficit": 12.5},
        {"allocated": [1]},
        {"free_text": 10},
    ):
        with pytest.raises(ValueError):
            DomainError(ErrorCode.QTA_BUDGET_BELOW_ALLOCATED, invalid)


def test_qta_path_is_private_and_sets_no_store_cache_header():
    app = create_app()

    @app.get("/api/v1/qta/probe")
    def probe():
        raise DomainError(ErrorCode.QTA_BUDGET_BELOW_ALLOCATED, {"deficit": 500, "allocated": 1500})

    with TestClient(app) as browser:
        response = browser.get("/api/v1/qta/probe")
    assert response.status_code == 409
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["code"] == "QTA_BUDGET_BELOW_ALLOCATED"
    assert body["details"] == {"deficit": 500, "allocated": 1500}
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_qta_audit_payloads_enforce_strict_typed_schemas():
    budget = audit.BudgetRevisionRecorded(
        period_month=date(2026, 11, 1),
        revision=2,
        before_limit=100_000,
        after_limit=150_000,
        before_decision_number="QD-2026-01",
        decision_number="QD-2026-02",
        decision_date=date(2026, 11, 5),
    )
    dumped = budget.model_dump(mode="json")
    assert dumped["period_month"] == "2026-11-01" and dumped["revision"] == 2
    assert dumped["before_decision_number"] == "QD-2026-01"
    synced = audit.GroupsSynced(
        system_group_count=4,
        active_member_count=120,
        specialist_group_count=2,
        groups_added=1,
        groups_retired=0,
    )
    assert synced.groups_added == 1 and synced.groups_retired == 0
    quota = audit.GroupQuotaUpdated(
        group_id=uuid4(),
        model_id=uuid4(),
        before_enabled=None,
        after_enabled=True,
        before_limit=None,
        after_limit=5000,
        warning_threshold_pct=80,
    )
    assert quota.after_limit == 5000
    suspended_until = audit.UserSuspended(
        user_id=uuid4(),
        scope="PAID_EXTERNAL_ONLY",
        ordered_by="Hiệu trưởng",
        expires_at=datetime(2026, 12, 1, tzinfo=UTC),
    )
    assert suspended_until.scope == "PAID_EXTERNAL_ONLY"
    suspended_open = audit.UserSuspended(
        user_id=uuid4(),
        scope="ALL_MODELS",
        ordered_by="Hiệu trưởng",
        expires_at=None,
    )
    assert suspended_open.expires_at is None
    restored = audit.UserRestored(user_id=uuid4(), suspension_id=uuid4())
    assert restored.suspension_id
    reset = audit.MonthlyResetRecorded(
        period_month=date(2026, 12, 1), trigger_mode="MANUAL_SIMULATION"
    )
    assert reset.trigger_mode == "MANUAL_SIMULATION"

    # Missing decision_date or non-positive revision/limit rejected.
    with pytest.raises(ValidationError):
        audit.BudgetRevisionRecorded(
            period_month=date(2026, 11, 1),
            revision=1,
            after_limit=100,
            decision_number="QD-1",
        )
    with pytest.raises(ValidationError):
        audit.BudgetRevisionRecorded(
            period_month=date(2026, 11, 1),
            revision=0,
            after_limit=100,
            decision_number="QD-1",
            decision_date=date(2026, 11, 1),
        )
    with pytest.raises(ValidationError):
        audit.GroupsSynced(
            system_group_count=1,
            active_member_count=1,
            specialist_group_count=0,
            groups_added=-1,
            groups_retired=0,
        )
    with pytest.raises(ValidationError):
        audit.UserSuspended(
            user_id=uuid4(),
            scope="ALL_MODELS",
            ordered_by="Admin",
            expires_at=None,
            extra_field="forbidden",
        )
    assert audit.AuditAction.QTA_MONTHLY_RESET_SCHEDULED in audit._OPERATOR_ACTIONS
    assert audit.AuditAction.QTA_MONTHLY_RESET_EXECUTED not in audit._OPERATOR_ACTIONS


def test_qta_schema_has_no_non_month_cycles_or_invented_pricing_or_consumption():
    qta_tables = [
        table
        for name, table in qta_models.Base.metadata.tables.items()
        if name.startswith("qta_")
    ]
    assert len(qta_tables) == 8
    columns = [col.name for table in qta_tables for col in table.columns]
    # FR-QTA-050 / AGENTS.md: no semester/project/exam cycles, no invented prices, conversion or usage deductions.
    assert not [
        col
        for col in columns
        if re.search(
            r"semester|hoc_ky|project|de_tai|exam|dot_thi|price|cost|rate|conver|credit|usage|consumed",
            col,
            re.IGNORECASE,
        )
    ]
    assert not [name for name in qta_models.Base.metadata.tables if "qta_usage" in name]


def test_qta_runtime_privileges_and_legacy_tables_cover_all_eight_tables():
    expected_tables = {
        "qta_budget_revisions",
        "qta_quota_groups",
        "qta_group_model_quotas",
        "qta_group_sync_runs",
        "qta_suspensions",
        "qta_suspension_restorations",
        "qta_monthly_resets",
        "qta_events",
    }
    assert set(QTA_RUNTIME_PRIVILEGES) == expected_tables
    assert expected_tables <= LEGACY_TABLES
    assert "qta_monthly_budgets" not in LEGACY_TABLES
    insert_only = {
        "qta_budget_revisions",
        "qta_group_sync_runs",
        "qta_suspensions",
        "qta_suspension_restorations",
        "qta_monthly_resets",
        "qta_events",
    }
    for table, privs in QTA_RUNTIME_PRIVILEGES.items():
        assert "DELETE" not in privs, table
        if table in insert_only:
            assert "UPDATE" not in privs, table
        assert present_privileges(privs, set(re.findall(r"[a-z_]+", privs))) == privs, table


def test_qta_migration_revisions_fit_alembic_version_column():
    for name in ("0007_qta_access_catalog.py", "0008_qta_schema.py"):
        text = (MIGRATIONS / name).read_text()
        revision = re.search(r'^revision = "([^"]+)"', text, re.MULTILINE).group(1)
        assert len(revision) <= 32 and revision == Path(name).stem
