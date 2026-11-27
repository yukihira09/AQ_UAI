"""Stage Q1-R against disposable PostgreSQL: QTA access catalog, schema, constraints & privileges."""

from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

from aq_uai_api.db.provision import QTA_RUNTIME_PRIVILEGES
from aq_uai_api.db.schema import REQUIRED_SCHEMA_REVISION

from .test_m1_mdl_access import capabilities, has_scope, sign_in
from .test_m2_mdl_schema import add_model, add_provider, rejected, seed_tenant
from .test_wp2_database import (
    alembic,
    assert_denied,
    connect,
    disposable_database,
    migrate,
    prepare,
)
from .test_wp5_directory import (
    add_grant,
    create_group,
    create_unit,
    create_user,
    expect,
    get,
    send,
)
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import directory as directory
from .test_wp5_directory import pytestmark as postgres_marks

pytestmark = postgres_marks

QTA_TABLES = (
    "qta_budget_revisions",
    "qta_quota_groups",
    "qta_group_model_quotas",
    "qta_group_sync_runs",
    "qta_suspensions",
    "qta_suspension_restorations",
    "qta_monthly_resets",
    "qta_events",
)
UPDATABLE = {
    "qta_budget_revisions": set(),
    "qta_quota_groups": {"in_directory", "last_synced_at"},
    "qta_group_model_quotas": {
        "enabled",
        "monthly_limit",
        "warning_threshold_pct",
        "updated_by",
        "updated_at",
    },
    "qta_group_sync_runs": set(),
    "qta_suspensions": set(),
    "qta_suspension_restorations": set(),
    "qta_monthly_resets": set(),
    "qta_events": set(),
}


@pytest.fixture(scope="module")
def qta_db():
    with disposable_database() as (admin, roles, owner, runtime):
        prepare(admin, roles)
        migrate(owner, roles)
        yield admin, roles, owner, runtime


def test_qta_upgrade_creates_empty_tables_matching_orm(qta_db):
    _, roles, owner, _ = qta_db
    alembic(owner, "check")
    with connect(owner) as connection:
        for table in QTA_TABLES:
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        owners = connection.execute(
            "SELECT DISTINCT pg_get_userbyid(relowner) FROM pg_class WHERE relname LIKE 'qta\\_%'"
        ).fetchall()
        assert owners == [(roles.migration,)]


def test_qta_runtime_privilege_matrix(qta_db):
    _, roles, _, runtime = qta_db
    assert set(QTA_RUNTIME_PRIVILEGES) == set(QTA_TABLES)
    with connect(runtime, autocommit=True) as connection:
        for table in QTA_TABLES:
            assert connection.execute(
                "SELECT has_any_column_privilege(current_user, %s, 'INSERT')",
                (f"public.{table}",),
            ).fetchone() == (True,)
            for privilege, expected in (
                ("SELECT", True),
                ("INSERT", False),
                ("UPDATE", False),
                ("DELETE", False),
                ("TRUNCATE", False),
                ("REFERENCES", False),
                ("TRIGGER", False),
            ):
                assert connection.execute(
                    "SELECT has_table_privilege(current_user, %s, %s)",
                    (f"public.{table}", privilege),
                ).fetchone() == (expected,), (table, privilege)
            for (column,) in connection.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            ).fetchall():
                assert connection.execute(
                    "SELECT has_column_privilege(current_user, %s, %s, 'UPDATE')",
                    (f"public.{table}", column),
                ).fetchone() == (column in UPDATABLE[table],), (table, column)
            assert_denied(connection, f"DELETE FROM {table}")
            assert_denied(connection, f"TRUNCATE {table}")
            assert_denied(connection, f"DROP TABLE {table}")
        for statement in (
            "UPDATE qta_budget_revisions SET total_limit = total_limit",
            "UPDATE qta_budget_revisions SET decision_number = decision_number",
            "UPDATE qta_budget_revisions SET decision_date = decision_date",
            "UPDATE qta_quota_groups SET group_kind = group_kind",
            "UPDATE qta_quota_groups SET origin = origin",
            "UPDATE qta_quota_groups SET enrolled_by = enrolled_by",
            "UPDATE qta_group_model_quotas SET group_id = group_id",
            "UPDATE qta_group_model_quotas SET model_id = model_id",
            "UPDATE qta_group_sync_runs SET system_group_count = 0",
            "UPDATE qta_group_sync_runs SET groups_added = 0",
            "UPDATE qta_suspensions SET reason = reason",
            "UPDATE qta_suspension_restorations SET note = note",
            "UPDATE qta_monthly_resets SET period_month = period_month",
            "UPDATE qta_events SET summary = summary",
        ):
            assert_denied(connection, statement)
        assert connection.execute(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = %s", (roles.runtime,)
        ).fetchone() == (False,)


def test_qta_constraints_enforce_month_only_cycles_tenancy_and_immutability(qta_db):
    _, _, owner, runtime = qta_db
    tenant, actor = seed_tenant(owner, "Q1A")
    other, other_actor = seed_tenant(owner, "Q1B")
    with connect(runtime, autocommit=True) as db:
        provider = add_provider(db, tenant, "QTA Vendor")
        other_provider = add_provider(db, other, "Other Vendor")
        model = add_model(db, tenant, provider, "qta-model-1")
        other_model = add_model(db, other, other_provider, "qta-model-1")
        sys_group = db.execute(
            "INSERT INTO account_groups (institution_id, code, name, kind)"
            " VALUES (%s, 'G_GV', 'Giảng viên', 'SYSTEM') RETURNING id",
            (tenant,),
        ).fetchone()[0]
        unenrolled_sys_group = db.execute(
            "INSERT INTO account_groups (institution_id, code, name, kind)"
            " VALUES (%s, 'G_SV', 'Sinh viên', 'SYSTEM') RETURNING id",
            (tenant,),
        ).fetchone()[0]
        specialist_group = db.execute(
            "INSERT INTO account_groups (institution_id, code, name, kind)"
            " VALUES (%s, 'AI_LAB', 'Nhóm Nghiên cứu AI', 'AI_SPECIALIST') RETURNING id",
            (tenant,),
        ).fetchone()[0]
        auth_group = db.execute(
            "INSERT INTO account_groups (institution_id, code, name, kind)"
            " VALUES (%s, 'G_AUTH', 'Nhóm Phân quyền', 'AUTHORIZATION') RETURNING id",
            (tenant,),
        ).fetchone()[0]
        other_group = db.execute(
            "INSERT INTO account_groups (institution_id, code, name, kind)"
            " VALUES (%s, 'G_GV', 'Giảng viên', 'SYSTEM') RETURNING id",
            (other,),
        ).fetchone()[0]

        # 1. qta_budget_revisions: append-only revisions, day=1, rev >= 1, total > 0, decision_date required.
        budget_sql = (
            "INSERT INTO qta_budget_revisions (institution_id, period_month, revision, total_limit,"
            " decision_number, decision_date, recorded_by) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        db.execute(
            budget_sql, (tenant, date(2026, 11, 1), 1, 1_000_000, "QD-2026-01", date(2026, 11, 1), actor)
        )
        db.execute(
            budget_sql, (tenant, date(2026, 11, 1), 2, 1_500_000, "QD-2026-02", date(2026, 11, 5), actor)
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 11, 1), 2, 900_000, "QD-DUP", date(2026, 11, 6), actor),
            "23505",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 11, 2), 1, 500_000, "QD-2", date(2026, 11, 1), actor),
            "23514",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 12, 1), 0, 500_000, "QD-2", date(2026, 12, 1), actor),
            "23514",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 12, 1), 1, 0, "QD-2", date(2026, 12, 1), actor),
            "23514",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 12, 1), 1, -5, "QD-2", date(2026, 12, 1), actor),
            "23514",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 12, 1), 1, 100, "", date(2026, 12, 1), actor),
            "23514",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 12, 1), 1, 100, " QD-2 ", date(2026, 12, 1), actor),
            "23514",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 12, 1), 1, 100, "QD-2", None, actor),
            "23502",
        )
        rejected(
            db,
            budget_sql,
            (tenant, date(2026, 12, 1), 1, 100, "QD-2", date(2026, 12, 1), other_actor),
            "23503",
        )

        # 2. qta_quota_groups: registry enforces SYSTEM<->SYNC, AI_SPECIALIST<->SPECIALIST,
        #    refuses AUTHORIZATION and cross-tenant groups, allows updating in_directory/last_synced_at.
        reg_sql = (
            "INSERT INTO qta_quota_groups (institution_id, group_id, group_kind, origin,"
            " in_directory, enrolled_by, last_synced_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        now = datetime.now(UTC)
        db.execute(reg_sql, (tenant, sys_group, "SYSTEM", "SYNC", True, actor, now))
        db.execute(reg_sql, (tenant, specialist_group, "AI_SPECIALIST", "SPECIALIST", True, actor, None))
        # Duplicate enrollment refused.
        rejected(db, reg_sql, (tenant, sys_group, "SYSTEM", "SYNC", True, actor, now), "23505")
        # AUTHORIZATION group refused by CHECK and FK.
        rejected(db, reg_sql, (tenant, auth_group, "AUTHORIZATION", "SYNC", True, actor, now), "23514")
        rejected(db, reg_sql, (tenant, auth_group, "SYSTEM", "SYNC", True, actor, now), "23503")
        # Origin/kind mismatch refused by CHECK.
        rejected(db, reg_sql, (tenant, sys_group, "SYSTEM", "SPECIALIST", True, actor, now), "23514")
        rejected(
            db, reg_sql, (tenant, specialist_group, "AI_SPECIALIST", "SYNC", True, actor, now), "23514"
        )
        # Lying about persisted group kind refused by composite FK (institution_id, group_id, group_kind).
        rejected(
            db, reg_sql, (tenant, unenrolled_sys_group, "AI_SPECIALIST", "SPECIALIST", True, actor, None), "23503"
        )
        # Cross-tenant group or actor refused by composite FK.
        rejected(db, reg_sql, (tenant, other_group, "SYSTEM", "SYNC", True, actor, now), "23503")
        rejected(
            db, reg_sql, (tenant, unenrolled_sys_group, "SYSTEM", "SYNC", True, other_actor, now), "23503"
        )
        # Sync can update in_directory and last_synced_at on enrolled groups.
        db.execute(
            "UPDATE qta_quota_groups SET in_directory = false, last_synced_at = %s"
            " WHERE institution_id = %s AND group_id = %s",
            (now, tenant, sys_group),
        )
        db.execute(
            "UPDATE qta_quota_groups SET in_directory = true, last_synced_at = %s"
            " WHERE institution_id = %s AND group_id = %s",
            (now, tenant, sys_group),
        )

        # 3. qta_group_model_quotas: requires enrolled group in qta_quota_groups, unique (inst, group, model).
        quota_sql = (
            "INSERT INTO qta_group_model_quotas (institution_id, group_id, model_id, enabled,"
            " monthly_limit, warning_threshold_pct, updated_by) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        db.execute(quota_sql, (tenant, sys_group, model, True, 2000, 80, actor))
        rejected(db, quota_sql, (tenant, sys_group, model, True, 3000, None, actor), "23505")
        # Unenrolled SYSTEM group and AUTHORIZATION group refused by FK to qta_quota_groups.
        rejected(db, quota_sql, (tenant, unenrolled_sys_group, model, True, 500, None, actor), "23503")
        rejected(db, quota_sql, (tenant, auth_group, model, True, 500, None, actor), "23503")
        rejected(db, quota_sql, (tenant, sys_group, other_model, True, 100, None, actor), "23503")
        rejected(db, quota_sql, (tenant, other_group, model, True, 100, None, actor), "23503")
        model2 = add_model(db, tenant, provider, "qta-model-2")
        rejected(db, quota_sql, (tenant, sys_group, model2, True, -1, None, actor), "23514")
        rejected(db, quota_sql, (tenant, sys_group, model2, True, 100, 0, actor), "23514")
        rejected(db, quota_sql, (tenant, sys_group, model2, True, 100, 101, actor), "23514")
        db.execute(quota_sql, (tenant, sys_group, model2, False, 0, None, actor))

        # 4. qta_group_sync_runs: non-negative counts including groups_added & groups_retired.
        sync_sql = (
            "INSERT INTO qta_group_sync_runs (institution_id, system_group_count,"
            " active_member_count, specialist_group_count, groups_added, groups_retired, synced_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        db.execute(sync_sql, (tenant, 4, 12, 2, 1, 0, actor))
        rejected(db, sync_sql, (tenant, -1, 0, 0, 0, 0, actor), "23514")
        rejected(db, sync_sql, (tenant, 0, 0, 0, -1, 0, actor), "23514")
        rejected(db, sync_sql, (tenant, 0, 0, 0, 0, -1, actor), "23514")
        rejected(db, sync_sql, (tenant, 0, 0, 0, 0, 0, other_actor), "23503")

        # 5. qta_suspensions & qta_suspension_restorations: NULL or future expiry allowed; past refused.
        future = datetime.now(UTC) + timedelta(days=7)
        past = datetime.now(UTC) - timedelta(days=1)
        susp_sql = (
            "INSERT INTO qta_suspensions (institution_id, user_id, scope, reason, ordered_by,"
            " expires_at, suspended_by) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id"
        )
        susp_id = db.execute(
            susp_sql, (tenant, actor, "PAID_EXTERNAL_ONLY", "Vi phạm định mức", "BGH", future, actor)
        ).fetchone()[0]
        # NULL expiry accepted (PD-Q3: active until explicitly restored).
        db.execute(
            susp_sql, (tenant, actor, "ALL_MODELS", "Tạm ngưng không thời hạn", "BGH", None, actor)
        )
        rejected(db, susp_sql, (tenant, actor, "INTERNAL_ONLY", "Reason", "BGH", future, actor), "23514")
        rejected(db, susp_sql, (tenant, actor, "ALL_MODELS", " ", "BGH", future, actor), "23514")
        rejected(db, susp_sql, (tenant, actor, "ALL_MODELS", "Reason", "", future, actor), "23514")
        rejected(db, susp_sql, (tenant, actor, "ALL_MODELS", "Reason", "BGH", past, actor), "23514")
        rejected(db, susp_sql, (tenant, other_actor, "ALL_MODELS", "Reason", "BGH", future, actor), "23503")

        restore_sql = (
            "INSERT INTO qta_suspension_restorations (suspension_id, institution_id, restored_by, note)"
            " VALUES (%s, %s, %s, %s)"
        )
        rejected(db, restore_sql, (susp_id, other, other_actor, None), "23503")
        rejected(db, restore_sql, (susp_id, tenant, actor, "  "), "23514")
        db.execute(restore_sql, (susp_id, tenant, actor, "Khôi phục theo đề nghị"))
        rejected(db, restore_sql, (susp_id, tenant, actor, None), "23505")

        # 6. qta_monthly_resets: day=1, trigger mode, manual requires actor, unique per month.
        reset_sql = (
            "INSERT INTO qta_monthly_resets (institution_id, period_month, trigger_mode, triggered_by)"
            " VALUES (%s, %s, %s, %s)"
        )
        db.execute(reset_sql, (tenant, date(2026, 11, 1), "SCHEDULED", None))
        rejected(db, reset_sql, (tenant, date(2026, 11, 1), "MANUAL_SIMULATION", actor), "23505")
        rejected(db, reset_sql, (tenant, date(2026, 12, 15), "SCHEDULED", None), "23514")
        rejected(db, reset_sql, (tenant, date(2026, 12, 1), "MANUAL_SIMULATION", None), "23514")
        rejected(db, reset_sql, (tenant, date(2026, 12, 1), "SEMESTER", actor), "23514")
        db.execute(reset_sql, (tenant, date(2026, 12, 1), "MANUAL_SIMULATION", actor))

        # 7. qta_events: day=1, event_type, user_id null iff MONTHLY_REFRESH, non-blank summary.
        event_sql = (
            "INSERT INTO qta_events (institution_id, period_month, event_type, user_id, actor_id, summary)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
        )
        db.execute(event_sql, (tenant, date(2026, 11, 1), "MONTHLY_REFRESH", None, actor, "Làm mới tháng 11/2026"))
        db.execute(event_sql, (tenant, date(2026, 11, 1), "SUSPEND", actor, actor, "Cắt hạn mức"))
        db.execute(event_sql, (tenant, date(2026, 11, 1), "RESTORE", actor, actor, "Khôi phục hạn mức"))
        rejected(db, event_sql, (tenant, date(2026, 11, 2), "MONTHLY_REFRESH", None, actor, "Bad day"), "23514")
        rejected(db, event_sql, (tenant, date(2026, 11, 1), "MONTHLY_REFRESH", actor, actor, "Has user"), "23514")
        rejected(db, event_sql, (tenant, date(2026, 11, 1), "SUSPEND", None, actor, "Missing user"), "23514")
        rejected(db, event_sql, (tenant, date(2026, 11, 1), "RESTORE", actor, actor, ""), "23514")


def test_populated_0006_database_upgrades_cleanly_to_0008():
    """Populated Phase 3 (0006) DB -> 0008 preserves MDL, account_groups & memberships unchanged."""
    with disposable_database() as (admin, roles, owner, runtime):
        alembic(admin, "upgrade", "0006_mdl_routing_and_styles")
        prepare(admin, roles)
        tenant, actor = seed_tenant(owner, "UPG6")
        with connect(runtime, autocommit=True) as db:
            provider = add_provider(db, tenant, "Kept Vendor")
            add_model(db, tenant, provider, "kept-model", risk_level="LOW")
            sys_group = db.execute(
                "INSERT INTO account_groups (institution_id, code, name, kind)"
                " VALUES (%s, 'G_GV', 'Giảng viên', 'SYSTEM') RETURNING id",
                (tenant,),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO group_memberships (institution_id, group_id, user_id, active)"
                " VALUES (%s, %s, %s, true)",
                (tenant, sys_group, actor),
            )
            groups_before = db.execute(
                "SELECT id, institution_id, code, name, kind, active"
                " FROM account_groups ORDER BY id"
            ).fetchall()
            memberships_before = db.execute(
                "SELECT institution_id, group_id, user_id, active"
                " FROM group_memberships ORDER BY group_id, user_id"
            ).fetchall()
        prepare(admin, roles)
        migrate(owner, roles)
        alembic(owner, "check")
        migrate(owner, roles)  # idempotent second run
        with connect(runtime) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
                REQUIRED_SCHEMA_REVISION,
            )
            assert connection.execute("SELECT count(*) FROM mdl_providers").fetchone() == (1,)
            assert connection.execute("SELECT count(*) FROM mdl_models").fetchone() == (1,)
            assert (
                connection.execute(
                    "SELECT id, institution_id, code, name, kind, active"
                    " FROM account_groups ORDER BY id"
                ).fetchall()
                == groups_before
            )
            assert (
                connection.execute(
                    "SELECT institution_id, group_id, user_id, active"
                    " FROM group_memberships ORDER BY group_id, user_id"
                ).fetchall()
                == memberships_before
            )
            for table in QTA_TABLES:
                assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_qta_roles_enforce_direct_scope_and_separation_of_duties(directory):
    unit_a = create_unit(directory.admin, "QTAUNIT1")
    unit_b = create_unit(directory.admin, "QTAUNIT2")
    qta_admin = create_user(directory.admin, unit_a["id"], "qtaadmin", active=True)
    global_viewer = create_user(directory.admin, unit_a["id"], "qtaviewer", active=True)
    unit_viewer = create_user(directory.admin, unit_a["id"], "unitviewer", active=True)
    auth_group = create_group(directory.admin, "AUTHORIZATION")

    # Direct GLOBAL AI_QUOTA_ADMIN gets qta.read + qta.manage only.
    grant = add_grant(directory.admin, f"/users/{qta_admin['id']}", "AI_QUOTA_ADMIN")
    assert grant["scope"] == "GLOBAL" and grant["role_code"] == "AI_QUOTA_ADMIN"
    # UNIT-scoped AI_QUOTA_ADMIN refused.
    expect(
        send(
            directory.admin,
            "POST",
            f"/users/{qta_admin['id']}/role-assignments",
            {"role_code": "AI_QUOTA_ADMIN", "scope": "UNIT", "unit_id": unit_a["id"]},
        ),
        422,
    )
    # Neither QTA role may be granted to a group.
    for role in ("AI_QUOTA_ADMIN", "AI_QUOTA_VIEWER"):
        for scoped in ({"scope": "GLOBAL"}, {"scope": "UNIT", "unit_id": unit_a["id"]}):
            expect(
                send(
                    directory.admin,
                    "POST",
                    f"/groups/{auth_group['id']}/role-assignments",
                    {"role_code": role, **scoped},
                ),
                422,
            )

    # Direct GLOBAL and UNIT AI_QUOTA_VIEWER grants succeed.
    add_grant(directory.admin, f"/users/{global_viewer['id']}", "AI_QUOTA_VIEWER")
    add_grant(directory.admin, f"/users/{unit_viewer['id']}", "AI_QUOTA_VIEWER", unit_a["id"])

    browser = sign_in(directory, "qtaadmin")
    try:
        caps = capabilities(browser)
        assert caps["qta.read"]["institution_wide"] and caps["qta.manage"]["institution_wide"]
        assert not has_scope(caps["mdl.read"]) and not has_scope(caps["directory.read"])
    finally:
        browser.__exit__(None, None, None)

    browser = sign_in(directory, "qtaviewer")
    try:
        caps = capabilities(browser)
        assert caps["qta.read"]["institution_wide"] and not has_scope(caps["qta.manage"])
    finally:
        browser.__exit__(None, None, None)

    browser = sign_in(directory, "unitviewer")
    try:
        caps = capabilities(browser)
        assert not caps["qta.read"]["institution_wide"]
        assert caps["qta.read"]["unit_ids"] == [unit_a["id"]]
        assert unit_b["id"] not in caps["qta.read"]["unit_ids"]
        assert not has_scope(caps["qta.manage"])
    finally:
        browser.__exit__(None, None, None)

    # Even if a drifted group grant existed in PostgreSQL, policy ignores it.
    grouped_user = create_user(directory.admin, unit_a["id"], "qtagrouped", active=True)
    expect(send(directory.admin, "PUT", f"/groups/{auth_group['id']}/members/{grouped_user['id']}"), 200)
    with directory.owner_factory.begin() as owner:
        owner.execute(
            sa.text(
                "ALTER TABLE group_role_assignments DROP CONSTRAINT ck_group_role_assignments_no_qta_admin"
            )
        )
        owner.execute(
            sa.text(
                "INSERT INTO group_role_assignments (institution_id, group_id, role_code, scope)"
                " VALUES (:i, :g, 'AI_QUOTA_ADMIN', 'GLOBAL')"
            ),
            {"i": directory.tenant, "g": auth_group["id"]},
        )
    try:
        browser = sign_in(directory, "qtagrouped")
        try:
            caps = capabilities(browser)
            assert not has_scope(caps["qta.read"]) and not has_scope(caps["qta.manage"])
        finally:
            browser.__exit__(None, None, None)
    finally:
        with directory.owner_factory.begin() as owner:
            owner.execute(
                sa.text("DELETE FROM group_role_assignments WHERE role_code = 'AI_QUOTA_ADMIN'")
            )
            owner.execute(
                sa.text(
                    "ALTER TABLE group_role_assignments ADD CONSTRAINT ck_group_role_assignments_no_qta_admin"
                    " CHECK (role_code <> 'AI_QUOTA_ADMIN')"
                )
            )
    # Confirm roles endpoint exposes both new roles with exact permission lists.
    roles = {
        item["code"]: item["permissions"]
        for item in expect(get(directory.admin, "/roles"), 200)["items"]
    }
    assert roles["AI_QUOTA_ADMIN"] == ["qta.manage", "qta.read"]
    assert roles["AI_QUOTA_VIEWER"] == ["qta.read"]
