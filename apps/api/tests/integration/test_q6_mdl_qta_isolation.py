"""Q6 (4.1): FR-MDL-020 AC3 cross-module isolation proof with a populated QTA (R17).

Proves end-to-end against disposable PostgreSQL 18 (under ``aq_uai_runtime``) that:
1. With every ``qta_*`` table populated and the MDL connection-test user holding a non-zero
   additive entitlement (1,000 + 3,000 = 4,000 ``đơn vị hạn mức``) on the model under test,
   running a PASSED connection test, a FAILED connection test (against the local loopback
   fake provider — nothing leaves the machine), and an MDL primary/fallback routing change
   leaves the tester's entitlement lookup, school monthly budget, QTA events, and every
   row of every ``qta_*`` table byte-identical, while statement-level triggers confirm zero
   ``qta_*`` writes occurred.
2. Positive control: with the same write log installed, one QTA write (suspending another
   user) is immediately detected in ``written()`` so the isolation assertion cannot pass
   vacuously.
3. Reverse direction: a QTA write burst (budget revision, quota upsert, suspend, restore,
   manual monthly reset) writes only QTA/audit/session tables and zero ``mdl_*`` tables.

Note: ``consumption_status`` is ``"NOT_INTEGRATED"``, so "balance" in Phase 4 means live
additive ``base_entitlement`` (and institutional ``allocated``).
"""

from datetime import UTC, datetime

from psycopg import sql

from aq_uai_api.qta import periods

from .test_m1_mdl_access import sign_in
from .test_m3_mdl_api import call
from .test_m3_mdl_api import mdl as mdl
from .test_m4_connection_tests import add_model, local_provider, run_test
from .test_m4_connection_tests import m4 as m4
from .test_m6_quota_isolation import install_write_log, written
from .test_q2_qta_groups import create_group, qta_get, qta_send
from .test_wp2_database import connect
from .test_wp5_directory import add_grant, create_user, expect, send
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
MDL_ALLOWED_WRITE_TABLES = frozenset(
    {
        "mdl_connection_tests",
        "mdl_routing",
        "mdl_routing_revisions",
        "audit_events",
        "auth_sessions",
    }
)


def _dump_qta_tables(owner_url) -> dict[str, list]:
    """Return an ordered, all-column JSON row dump for every QTA table."""
    with connect(owner_url) as conn:
        dump: dict[str, list] = {}
        for table in QTA_TABLES:
            rows = conn.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} AS t ORDER BY to_jsonb(t)").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            dump[table] = [row[0] for row in rows]
        return dump


def test_mdl_connection_tests_and_routing_leave_populated_qta_untouched(m4, monkeypatch):
    """FR-MDL-020 AC3 end-to-end with populated QTA, positive control & reverse isolation."""
    # Freeze clock to Nov 2026 during setup + MDL operations, then Dec 2026 for QTA burst reset.
    clock = {"now": datetime(2026, 11, 15, 5, 0, tzinfo=UTC)}
    monkeypatch.setattr(periods, "utc_now", lambda: clock["now"])

    db = m4
    qta_admin_user = create_user(db.admin, db.unit, "q6qtaadmin", active=True)
    other_user_1 = create_user(db.admin, db.unit, "q6other1", active=True)
    other_user_2 = create_user(db.admin, db.unit, "q6other2", active=True)
    add_grant(db.admin, f"/users/{qta_admin_user['id']}", "AI_QUOTA_ADMIN")

    # Local loopback fake provider with two active LOW-risk TEXT models (nothing leaves host).
    provider = local_provider(db, name="Q6 Local Fake")
    primary_model = add_model(db, provider["id"], technical_id="q6-primary")
    fallback_model = add_model(db, provider["id"], technical_id="q6-fallback")
    call(db, "PATCH", f"/models/{primary_model['id']}", {"risk_level": "LOW"})
    call(db, "PATCH", f"/models/{fallback_model['id']}", {"risk_level": "LOW"})
    # Give fallback_model a PASSED test during setup so routing can select primary + fallback.
    assert run_test(db, fallback_model["id"])["status"] == "PASSED"

    # Put the MDL admin (db.manager_id) into a SYSTEM group (1,000) and an AI_SPECIALIST group (3,000).
    sys_group = create_group(db.admin, "SYSTEM", code="G_Q6_SYS", name="Nhóm Hệ thống Q6")
    expect(send(db.admin, "PUT", f"/groups/{sys_group['id']}/members/{db.manager_id}"), 200)

    qta_admin = sign_in(db, "q6qtaadmin")
    try:
        qta_send(qta_admin, "POST", "/groups/sync")
        qta_send(
            qta_admin,
            "PUT",
            f"/groups/{sys_group['id']}/quotas",
            {"quotas": [{"model_id": primary_model["id"], "enabled": True, "monthly_limit": 1000}]},
        )

        spec_group = qta_send(
            qta_admin, "POST", "/groups", {"code": "AI_Q6_SPEC", "name": "Nhóm AI Q6"}, 201
        )
        qta_send(qta_admin, "PUT", f"/groups/{spec_group['id']}/members/{db.manager_id}")
        qta_send(
            qta_admin,
            "PUT",
            f"/groups/{spec_group['id']}/quotas",
            {"quotas": [{"model_id": primary_model["id"], "enabled": True, "monthly_limit": 3000}]},
        )

        # Populate remaining QTA tables: budget revision, suspension + restoration, monthly reset & events.
        qta_send(
            qta_admin,
            "PUT",
            "/budgets/2026-11",
            {"total_limit": 10_000, "decision_number": "QD-Q6-ISO-01", "decision_date": "2026-11-01"},
        )
        qta_send(
            qta_admin,
            "POST",
            f"/users/{other_user_1['id']}/suspensions",
            {"scope": "ALL_MODELS", "reason": "Khởi tạo dữ liệu Q6", "ordered_by": "Ban Giám hiệu"},
            201,
        )
        qta_send(qta_admin, "POST", f"/users/{other_user_1['id']}/restore", {"note": "Khôi phục mẫu"})
        qta_send(qta_admin, "POST", "/monthly-resets", None, 201)

        # (a) BEFORE snapshots + assert every qta_* table is populated and tester has 4,000 base entitlement.
        before_tables = _dump_qta_tables(db.owner)
        for table_name in QTA_TABLES:
            assert len(before_tables[table_name]) >= 1, f"Expected populated table {table_name}"

        before_entitlements = qta_get(qta_admin, f"/users/{db.manager_id}/entitlements", {"month": "2026-11"})
        by_model = {m["model_id"]: m for m in before_entitlements["models"]}
        assert by_model[primary_model["id"]]["base_entitlement"] == 4000
        assert before_entitlements["base_entitlement_total"] == 4000
        assert by_model[primary_model["id"]]["consumption_status"] == "NOT_INTEGRATED"

        before_budget = qta_get(qta_admin, "/budgets", {"month": "2026-11"})
        assert before_budget["allocated"] == 4000
        before_events = qta_get(qta_admin, "/events", {"month": "2026-11"})
        assert before_events["total"] >= 3  # SUSPEND + RESTORE + MONTHLY_REFRESH

        # (b) Install statement-level write triggers on every public table; run MDL tests + routing change.
        tracked_tables = install_write_log(db)
        assert set(QTA_TABLES) <= set(tracked_tables)
        written(db, start_over=True)

        # 1. Failing connection test (local fake provider returns auth error).
        db.provider.mode = "auth"
        failed_test = run_test(db, primary_model["id"])
        assert failed_test["status"] == "FAILED" and failed_test["error_code"] == "AUTH_FAILED"

        # 2. Successful connection test (local fake provider returns valid completion).
        db.provider.mode = "ok"
        passed_test = run_test(db, primary_model["id"])
        assert passed_test["status"] == "PASSED"

        # 3. Primary + fallback routing change.
        routing = call(
            db,
            "PUT",
            "/routing",
            {
                "expected_revision": 0,
                "primary_model_id": primary_model["id"],
                "fallback_model_id": fallback_model["id"],
                "decision_reference": "QD-MDL-Q6-01",
            },
        )
        assert routing["effective"]["state"] == "PRIMARY"

        mdl_written = written(db, start_over=True)

        # (c) AFTER assertions: all four QTA snapshots byte-identical; zero qta_* tables written.
        assert mdl_written <= MDL_ALLOWED_WRITE_TABLES, mdl_written
        assert {"mdl_connection_tests", "mdl_routing", "mdl_routing_revisions", "audit_events"} <= mdl_written
        assert not [name for name in mdl_written if name.startswith("qta_")], mdl_written

        after_entitlements = qta_get(qta_admin, f"/users/{db.manager_id}/entitlements", {"month": "2026-11"})
        after_budget = qta_get(qta_admin, "/budgets", {"month": "2026-11"})
        after_events = qta_get(qta_admin, "/events", {"month": "2026-11"})
        after_tables = _dump_qta_tables(db.owner)

        assert after_entitlements == before_entitlements
        assert after_budget == before_budget
        assert after_events == before_events
        assert after_tables == before_tables

        # (d) Positive control: prove the write log catches QTA writes (cannot pass vacuously).
        written(db, start_over=True)
        qta_send(
            qta_admin,
            "POST",
            f"/users/{other_user_2['id']}/suspensions",
            {"scope": "PAID_EXTERNAL_ONLY", "reason": "Đối chứng ghi QTA", "ordered_by": "Ban Giám hiệu"},
            201,
        )
        control_written = written(db, start_over=True)
        assert any(name.startswith("qta_") for name in control_written), control_written
        assert {"qta_suspensions", "qta_events"} <= control_written

        # (e) Reverse direction: QTA write burst (budget, quota, suspend, restore, manual reset) writes zero mdl_* tables.
        clock["now"] = datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
        written(db, start_over=True)

        qta_send(
            qta_admin,
            "PUT",
            "/budgets/2026-12",
            {"total_limit": 12_000, "decision_number": "QD-Q6-ISO-02", "decision_date": "2026-12-01"},
        )
        qta_send(
            qta_admin,
            "PUT",
            f"/groups/{spec_group['id']}/quotas",
            {"quotas": [{"model_id": primary_model["id"], "enabled": True, "monthly_limit": 3500}]},
        )
        qta_send(
            qta_admin,
            "POST",
            f"/users/{other_user_1['id']}/suspensions",
            {"scope": "ALL_MODELS", "reason": "Kiểm tra chiều ngược", "ordered_by": "Ban Giám hiệu"},
            201,
        )
        qta_send(qta_admin, "POST", f"/users/{other_user_1['id']}/restore", {"note": "Mở lại chiều ngược"})
        qta_send(qta_admin, "POST", "/monthly-resets", None, 201)

        qta_written = written(db, start_over=True)
        assert {
            "qta_budget_revisions",
            "qta_group_model_quotas",
            "qta_suspensions",
            "qta_suspension_restorations",
            "qta_monthly_resets",
            "qta_events",
        } <= qta_written, qta_written
        assert not [name for name in qta_written if name.startswith("mdl_")], qta_written
    finally:
        qta_admin.__exit__(None, None, None)
