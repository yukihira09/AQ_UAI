"""Stage Q3 against disposable PostgreSQL: live entitlements, additive lookup & append-only budgets.

All requests go through real FastAPI routes with session cookies, exact Origin, CSRF headers,
and the restricted ``aq_uai_runtime`` database login. All clock-dependent assertions monkeypatch
``aq_uai_api.qta.periods.utc_now`` rather than relying on the host wall clock.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from psycopg import sql

from aq_uai_api.qta import entitlements, periods

from .test_m1_mdl_access import sign_in
from .test_m2_mdl_schema import add_model, add_provider
from .test_q2_qta_groups import audit_rows, create_group, qta_get, qta_path, qta_send
from .test_wp2_database import connect
from .test_wp3_auth import ORIGIN_HEADER, client, csrf_headers
from .test_wp5_directory import (
    add_grant,
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

# Fixed clock: 2026-11-15T05:00Z = 2026-11-15T12:00+07:00 (Asia/Ho_Chi_Minh).
# Open window: current = 2026-11, next = 2026-12. Past = 2026-10; far future = 2027-01.
FROZEN_UTC = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)


@pytest.fixture
def qta3(directory, monkeypatch):
    monkeypatch.setattr(periods, "utc_now", lambda: FROZEN_UTC)
    db = directory
    unit_a = create_unit(db.admin, "Q3UA")
    unit_b = create_unit(db.admin, "Q3UB")
    qta_admin_user = create_user(db.admin, unit_a["id"], "q3admin", active=True)
    global_viewer_user = create_user(db.admin, unit_a["id"], "q3gviewer", active=True)
    unit_viewer_user = create_user(db.admin, unit_a["id"], "q3uviewer", active=True)
    mdl_admin_user = create_user(db.admin, unit_a["id"], "q3mdladmin", active=True)

    add_grant(db.admin, f"/users/{qta_admin_user['id']}", "AI_QUOTA_ADMIN")
    add_grant(db.admin, f"/users/{global_viewer_user['id']}", "AI_QUOTA_VIEWER")
    add_grant(db.admin, f"/users/{unit_viewer_user['id']}", "AI_QUOTA_VIEWER", unit_a["id"])
    add_grant(db.admin, f"/users/{mdl_admin_user['id']}", "AI_MODEL_ADMIN")

    with connect(db.runtime, autocommit=True) as conn:
        ext_provider = add_provider(conn, db.tenant, "Q3 External", provider_type="EXTERNAL")
        int_provider = add_provider(conn, db.tenant, "Q3 Internal", provider_type="INTERNAL")
        m1 = add_model(conn, db.tenant, ext_provider, "m1-tech", display_name="M1", risk_level="LOW")
        m2 = add_model(conn, db.tenant, int_provider, "m2-tech", display_name="M2", risk_level="LOW")

    db.unit_a = unit_a["id"]
    db.unit_b = unit_b["id"]
    db.qta_admin_id = qta_admin_user["id"]
    db.m1 = str(m1)
    db.m2 = str(m2)
    db.ext_provider = ext_provider
    db.int_provider = int_provider

    db.qta_admin = sign_in(db, "q3admin")
    db.global_viewer = sign_in(db, "q3gviewer")
    db.unit_viewer = sign_in(db, "q3uviewer")
    db.mdl_admin = sign_in(db, "q3mdladmin")
    try:
        yield db
    finally:
        for browser in (db.qta_admin, db.global_viewer, db.unit_viewer, db.mdl_admin):
            browser.__exit__(None, None, None)


def _by_model(entitlement_response: dict) -> dict[str, dict]:
    return {item["model_id"]: item for item in entitlement_response["models"]}


def test_architecture_numerical_example(qta3):
    """Exact verification of every row in QTA_ARCHITECTURE_AND_DECISIONS.md §2.1."""
    db = qta3
    alice = create_user(db.admin, db.unit_a, "alice", active=True)
    bob = create_user(db.admin, db.unit_a, "bob", active=True)
    carol = create_user(db.admin, db.unit_a, "carol", active=True)
    expect(send(db.admin, "POST", f"/users/{carol['id']}/disable"), 200)

    # G_GV (SYSTEM via sync): members Alice, Bob, Carol[DISABLED]; M1=1000, M2=2000 (both enabled).
    g_gv = create_group(db.admin, "SYSTEM", code="G_GV", name="Giảng viên")
    for uid in (alice["id"], bob["id"], carol["id"]):
        expect(send(db.admin, "PUT", f"/groups/{g_gv['id']}/members/{uid}"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_gv['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 1000},
                {"model_id": db.m2, "enabled": True, "monthly_limit": 2000},
            ]
        },
    )

    # AI_LAB (AI_SPECIALIST): member Alice; M1=3000 (enabled), M2=5000 (disabled).
    ai_lab = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "AI_LAB", "name": "AI Lab"}, 201
    )
    qta_send(db.qta_admin, "PUT", f"/groups/{ai_lab['id']}/members/{alice['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{ai_lab['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 3000},
                {"model_id": db.m2, "enabled": False, "monthly_limit": 5000},
            ]
        },
    )

    # Assert Alice, Bob, Carol entitlements.
    alice_ent = qta_get(db.qta_admin, f"/users/{alice['id']}/entitlements", {"month": "2026-11"})
    alice_models = _by_model(alice_ent)
    assert alice_ent["unit_label"] == "đơn vị hạn mức"
    assert alice_models[db.m1]["base_entitlement"] == 4000  # 1000 + 3000, NOT max 3000
    assert alice_models[db.m2]["base_entitlement"] == 2000  # 2000 + 0 (AI_LAB disabled)
    assert alice_ent["base_entitlement_total"] == 6000

    bob_ent = qta_get(db.qta_admin, f"/users/{bob['id']}/entitlements", {"month": "2026-11"})
    bob_models = _by_model(bob_ent)
    assert bob_models[db.m1]["base_entitlement"] == 1000
    assert bob_models[db.m2]["base_entitlement"] == 2000
    assert bob_ent["base_entitlement_total"] == 3000

    carol_ent = qta_get(db.qta_admin, f"/users/{carol['id']}/entitlements", {"month": "2026-11"})
    assert carol_ent["user"]["state"] == "DISABLED"
    assert carol_ent["base_entitlement_total"] == 0
    assert all(m["base_entitlement"] == 0 for m in carol_ent["models"])

    # Institutional allocated = 9,000.
    before_budget = qta_get(db.qta_admin, "/budgets", {"month": "2026-11"})
    assert before_budget["allocated"] == 9000 and before_budget["allocation_status"] == "LIVE"

    # Revision 1: 10,000 with QD-01 -> remaining = 1,000.
    rev1 = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 10_000, "decision_number": "QD-01", "decision_date": "2026-11-01"},
    )
    assert rev1["current"]["revision"] == 1
    assert rev1["allocated"] == 9000 and rev1["remaining"] == 1000 and rev1["over_allocated"] == 0

    # Revision 2 attempt: 7,500 < 9,000 -> 409 QTA_BUDGET_BELOW_ALLOCATED with {allocated: 9000, deficit: 1500}.
    denied = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 7500, "decision_number": "QD-02", "decision_date": "2026-11-10"},
        409,
    )
    assert denied["code"] == "QTA_BUDGET_BELOW_ALLOCATED"
    assert denied["details"] == {"allocated": 9000, "deficit": 1500}

    # Mid-month: deactivate AI_LAB -> Alice drops to 1,000 + 2,000; allocated drops immediately to 6,000.
    qta_send(db.qta_admin, "POST", f"/groups/{ai_lab['id']}/deactivate")
    alice_after = qta_get(db.qta_admin, f"/users/{alice['id']}/entitlements", {"month": "2026-11"})
    assert _by_model(alice_after)[db.m1]["base_entitlement"] == 1000
    assert _by_model(alice_after)[db.m2]["base_entitlement"] == 2000

    # 7,500 now succeeds as revision 2 (remaining = 1,500), while revision 1 stays preserved in history.
    rev2 = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 7500, "decision_number": "QD-02", "decision_date": "2026-11-10"},
    )
    assert rev2["current"]["revision"] == 2 and rev2["current"]["total_limit"] == 7500
    assert rev2["allocated"] == 6000 and rev2["remaining"] == 1500 and rev2["over_allocated"] == 0
    assert [(r["revision"], r["decision_number"], r["total_limit"]) for r in rev2["revisions"]] == [
        (2, "QD-02", 7500),
        (1, "QD-01", 10_000),
    ]


def test_additive_not_max_1000_plus_3000(qta3):
    """FR-QTA-030 AC1, AC2: user in 1,000 + 3,000 groups gets 4,000 with both contributions listed."""
    db = qta3
    user = create_user(db.admin, db.unit_a, "stacked", active=True)
    g1 = create_group(db.admin, "SYSTEM", code="G_1000", name="Nhóm 1000")
    expect(send(db.admin, "PUT", f"/groups/{g1['id']}/members/{user['id']}"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g1['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 1000}]},
    )

    g2 = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_3000", "name": "Nhóm 3000"}, 201)
    qta_send(db.qta_admin, "PUT", f"/groups/{g2['id']}/members/{user['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g2['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 3000}]},
    )

    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    m1_row = _by_model(ent)[db.m1]
    assert m1_row["base_entitlement"] == 4000
    assert [(c["code"], c["contributes"]) for c in m1_row["contributions"]] == [
        ("AI_3000", 3000),
        ("G_1000", 1000),
    ]
    assert {m["code"] for m in ent["memberships"] if m["qualifies"]} == {"G_1000", "AI_3000"}


def test_no_group_user_has_zero_base(qta3):
    """FR-QTA-031 AC2: user in zero groups has base_entitlement 0 for every active model."""
    db = qta3
    solo = create_user(db.admin, db.unit_a, "nogroup", active=True)
    ent = qta_get(db.qta_admin, f"/users/{solo['id']}/entitlements")
    assert ent["memberships"] == []
    assert ent["base_entitlement_total"] == 0
    assert len(ent["models"]) == 2
    assert all(m["base_entitlement"] == 0 and m["contributions"] == [] for m in ent["models"])


def test_disabling_model_quota_removes_base_for_single_group_user(qta3):
    """FR-QTA-021 AC2: disabling a model on a group drops single-group member's base to 0 immediately."""
    db = qta3
    user = create_user(db.admin, db.unit_a, "singlegrp", active=True)
    grp = create_group(db.admin, "SYSTEM", code="G_SINGLE")
    expect(send(db.admin, "PUT", f"/groups/{grp['id']}/members/{user['id']}"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 2500}]},
    )
    assert _by_model(qta_get(db.qta_admin, f"/users/{user['id']}/entitlements"))[db.m1]["base_entitlement"] == 2500

    # Disable model on the group -> base entitlement immediately becomes 0.
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": False, "monthly_limit": 2500}]},
    )
    m1_after = _by_model(qta_get(db.qta_admin, f"/users/{user['id']}/entitlements"))[db.m1]
    assert m1_after["base_entitlement"] == 0
    assert m1_after["contributions"][0]["enabled"] is False
    assert m1_after["contributions"][0]["contributes"] == 0


def test_specialist_member_appears_in_additive_lookup(qta3):
    """FR-QTA-022 AC2: member of an AI_SPECIALIST group appears in lookup with that group's quota."""
    db = qta3
    researcher = create_user(db.admin, db.unit_a, "researcher", active=True)
    spec = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "AI_SPEC_LU", "name": "AI Lookup"}, 201
    )
    qta_send(db.qta_admin, "PUT", f"/groups/{spec['id']}/members/{researcher['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{spec['id']}/quotas",
        {"quotas": [{"model_id": db.m2, "enabled": True, "monthly_limit": 4200}]},
    )
    ent = qta_get(db.qta_admin, f"/users/{researcher['id']}/entitlements")
    assert ent["memberships"][0]["code"] == "AI_SPEC_LU" and ent["memberships"][0]["qualifies"] is True
    assert _by_model(ent)[db.m2]["base_entitlement"] == 4200


def test_exclusions(qta3):
    """Retired, inactive, unenrolled groups, inactive memberships, inactive models, disabled/zero quotas, and non-ACTIVE users contribute 0 with exact excluded_reason."""
    db = qta3
    active_user = create_user(db.admin, db.unit_a, "excluser", active=True)
    pending_user = create_user(db.admin, db.unit_a, "pendinguser", active=False)

    # 1. Retired SYSTEM group (enrolled -> quota set -> deactivated -> synced => in_directory=false).
    g_retired = create_group(db.admin, "SYSTEM", code="G_EX_RET")
    # 2. Inactive AI_SPECIALIST group (enrolled -> quota set -> deactivated => active=false, in_directory=true).
    g_inact = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_EX_INACT", "name": "Inact"}, 201)
    # 3. Qualifying group with disabled quota (m1), zero quota (m2), and an inactive MDL model.
    g_ok = create_group(db.admin, "SYSTEM", code="G_EX_OK")
    # 4. Group where membership is deactivated.
    g_removed = create_group(db.admin, "SYSTEM", code="G_EX_REM")

    for gid in (g_retired["id"], g_ok["id"], g_removed["id"]):
        expect(send(db.admin, "PUT", f"/groups/{gid}/members/{active_user['id']}"), 200)
    expect(send(db.admin, "PUT", f"/groups/{g_ok['id']}/members/{pending_user['id']}"), 200)
    qta_send(db.qta_admin, "PUT", f"/groups/{g_inact['id']}/members/{active_user['id']}")
    qta_send(db.qta_admin, "POST", "/groups/sync")

    # Add an extra model, configure quota, then deactivate the model in MDL.
    with connect(db.runtime, autocommit=True) as conn:
        m_retired = str(
            add_model(conn, db.tenant, db.int_provider, "m-gone", display_name="M Gone", risk_level="LOW")
        )

    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_retired['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 5000}]},
    )
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_inact['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 5000}]},
    )
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_removed['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 5000}]},
    )
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_ok['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": False, "monthly_limit": 5000},
                {"model_id": db.m2, "enabled": True, "monthly_limit": 0},
                {"model_id": m_retired, "enabled": True, "monthly_limit": 5000},
            ]
        },
    )

    # Apply exclusions: retire g_retired, deactivate g_inact, remove membership in g_removed, deactivate m_retired, create unenrolled group.
    expect(send(db.admin, "POST", f"/groups/{g_retired['id']}/deactivate"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(db.qta_admin, "POST", f"/groups/{g_inact['id']}/deactivate")
    expect(send(db.admin, "DELETE", f"/groups/{g_removed['id']}/members/{active_user['id']}"), 204)
    with connect(db.runtime, autocommit=True) as conn:
        conn.execute("UPDATE mdl_models SET active = false WHERE id = %s", (m_retired,))
    g_unenrolled = create_group(db.admin, "SYSTEM", code="G_EX_UNENROLLED")
    expect(send(db.admin, "PUT", f"/groups/{g_unenrolled['id']}/members/{active_user['id']}"), 200)

    ent = qta_get(db.qta_admin, f"/users/{active_user['id']}/entitlements")
    by_code = {m["code"]: m for m in ent["memberships"]}
    assert by_code["G_EX_OK"]["qualifies"] is True and by_code["G_EX_OK"]["excluded_reason"] is None
    assert by_code["G_EX_RET"]["qualifies"] is False and by_code["G_EX_RET"]["excluded_reason"] == "RETIRED"
    assert by_code["AI_EX_INACT"]["qualifies"] is False and by_code["AI_EX_INACT"]["excluded_reason"] == "GROUP_INACTIVE"
    assert by_code["G_EX_UNENROLLED"]["qualifies"] is False and by_code["G_EX_UNENROLLED"]["excluded_reason"] == "NOT_ENROLLED"
    assert "G_EX_REM" not in by_code  # inactive membership excluded from active memberships
    assert m_retired not in {m["model_id"] for m in ent["models"]}
    assert ent["base_entitlement_total"] == 0

    # Non-ACTIVE (PENDING) user gets USER_NOT_ACTIVE and 0 entitlement.
    pend_ent = qta_get(db.qta_admin, f"/users/{pending_user['id']}/entitlements")
    assert pend_ent["user"]["state"] == "PENDING"
    assert pend_ent["memberships"][0]["qualifies"] is False
    assert pend_ent["memberships"][0]["excluded_reason"] == "USER_NOT_ACTIVE"
    assert pend_ent["base_entitlement_total"] == 0


def test_consumption_is_null_not_integrated(qta3):
    """Architecture §2.3 & QD10: actual_consumption and remaining_quota are always null, never 0."""
    db = qta3
    user = create_user(db.admin, db.unit_a, "consuser", active=True)
    grp = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_CONS", "name": "Cons"}, 201)
    qta_send(db.qta_admin, "PUT", f"/groups/{grp['id']}/members/{user['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 1500}]},
    )
    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    assert len(ent["models"]) == 2
    for row in ent["models"]:
        assert row["actual_consumption"] is None
        assert row["remaining_quota"] is None
        assert row["consumption_status"] == "NOT_INTEGRATED"


def test_allocated_equals_sum_of_user_entitlements(qta3):
    """Consistency invariant: SQL aggregate allocated_for_month == sum of per-user entitlements."""
    db = qta3
    u1 = create_user(db.admin, db.unit_a, "sum1", active=True)
    u2 = create_user(db.admin, db.unit_b, "sum2", active=True)
    u3_disabled = create_user(db.admin, db.unit_a, "sum3dis", active=True)
    expect(send(db.admin, "POST", f"/users/{u3_disabled['id']}/disable"), 200)

    g_sys = create_group(db.admin, "SYSTEM", code="G_SUM")
    for u in (u1, u2, u3_disabled):
        expect(send(db.admin, "PUT", f"/groups/{g_sys['id']}/members/{u['id']}"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 1200},
                {"model_id": db.m2, "enabled": False, "monthly_limit": 9999},
            ]
        },
    )

    g_spec = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_SUM", "name": "AI Sum"}, 201)
    qta_send(db.qta_admin, "PUT", f"/groups/{g_spec['id']}/members/{u1['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_spec['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 800}, {"model_id": db.m2, "enabled": True, "monthly_limit": 500}]},
    )

    all_users = qta_get(db.qta_admin, "/users", {"limit": 100})["items"]
    sum_of_users = sum(
        qta_get(db.qta_admin, f"/users/{u['id']}/entitlements")["base_entitlement_total"]
        for u in all_users
    )
    budget_view = qta_get(db.qta_admin, "/budgets")
    assert budget_view["allocated"] == sum_of_users == 3700

    # Also verify direct DB call matches the API projection.
    with db.runtime_factory() as session:
        assert entitlements.allocated_for_month(session, db.tenant) == sum_of_users


def test_lookup_scope(qta3):
    """UNIT viewer sees only own-unit users and gets 404 for another unit; 403 on /qta/budgets."""
    db = qta3
    user_a = create_user(db.admin, db.unit_a, "unitauser", active=True)
    user_b = create_user(db.admin, db.unit_b, "unitbuser", active=True)

    # UNIT viewer (unit_a): sees user_a, does not see user_b; 200 on user_a entitlements, 404 on user_b.
    unit_users = qta_get(db.unit_viewer, "/users", {"limit": 100})["items"]
    unit_ids = {u["id"] for u in unit_users}
    assert user_a["id"] in unit_ids
    assert user_b["id"] not in unit_ids
    assert all(u["primary_unit_id"] == db.unit_a for u in unit_users)
    # Item shape: identity + quota_status only — no group, budget or entitlement amounts.
    assert set(unit_users[0]) == {
        "id",
        "username",
        "display_name",
        "institutional_code",
        "primary_unit_id",
        "state",
        "quota_status",
    }
    assert unit_users[0]["quota_status"] == "ACTIVE"

    qta_get(db.unit_viewer, f"/users/{user_a['id']}/entitlements", status=200)
    qta_get(db.unit_viewer, f"/users/{user_b['id']}/entitlements", status=404)
    # Search filter works within unit scope.
    found = qta_get(db.unit_viewer, "/users", {"q": "unitauser"})["items"]
    assert [u["id"] for u in found] == [user_a["id"]]
    assert qta_get(db.unit_viewer, "/users", {"q": "unitbuser"})["items"] == []

    # UNIT viewer -> 403 on /qta/budgets.
    qta_get(db.unit_viewer, "/budgets", status=403)

    # GLOBAL viewer sees both units and reads /qta/budgets.
    global_ids = {u["id"] for u in qta_get(db.global_viewer, "/users", {"limit": 100})["items"]}
    assert {user_a["id"], user_b["id"]} <= global_ids
    qta_get(db.global_viewer, f"/users/{user_b['id']}/entitlements", status=200)
    qta_get(db.global_viewer, "/budgets", status=200)

    # FOUNDATION_ADMIN and AI_MODEL_ADMIN -> 403 on all Q3 read routes.
    for denied in (db.admin, db.mdl_admin):
        qta_get(denied, "/users", status=403)
        qta_get(denied, f"/users/{user_a['id']}/entitlements", status=403)
        qta_get(denied, "/budgets", status=403)

    # Anonymous -> 401 on all Q3 read routes.
    with client(db) as anon:
        for path in ("/users", f"/users/{user_a['id']}/entitlements", "/budgets"):
            expect(get(anon, qta_path(path)), 401)


def test_budget_revisions_append_only(qta3):
    """INV-18 / RULE-QTA-04: revisions append (1, 2, 3), history newest first, row 1 never mutates."""
    db = qta3
    r1 = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 50_000, "decision_number": "QD-101", "decision_date": "2026-11-01"},
    )
    with connect(db.owner) as conn:
        row1_before = conn.execute(
            "SELECT id, revision, total_limit, decision_number, decision_date, recorded_by, recorded_at"
            " FROM qta_budget_revisions WHERE revision = 1"
        ).fetchone()

    r2 = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 80_000, "decision_number": "QD-102", "decision_date": "2026-11-05"},
    )
    # Repeating the exact same numbers still appends revision 3 (every write is a decision record).
    r3 = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 80_000, "decision_number": "QD-102", "decision_date": "2026-11-05"},
    )
    assert r1["current"]["revision"] == 1
    assert r2["current"]["revision"] == 2
    assert r3["current"]["revision"] == 3
    assert [rev["revision"] for rev in r3["revisions"]] == [3, 2, 1]

    with connect(db.owner) as conn:
        row1_after = conn.execute(
            "SELECT id, revision, total_limit, decision_number, decision_date, recorded_by, recorded_at"
            " FROM qta_budget_revisions WHERE revision = 1"
        ).fetchone()
    assert row1_after == row1_before

    audits = audit_rows(db, action_prefix="qta.monthly_budget_set")
    assert len(audits) == 3
    assert audits[0][4] == {
        "period_month": "2026-11-01",
        "revision": 1,
        "before_limit": None,
        "after_limit": 50_000,
        "before_decision_number": None,
        "decision_number": "QD-101",
        "decision_date": "2026-11-01",
    }
    assert audits[1][4]["before_limit"] == 50_000 and audits[1][4]["after_limit"] == 80_000
    assert audits[1][4]["before_decision_number"] == "QD-101"
    assert audits[1][4]["decision_number"] == "QD-102"


def test_budget_requires_decision_number_and_date(qta3):
    """FR-QTA-010 AC2 & PD-Q4: missing or blank decision_number or decision_date -> 422, nothing written."""
    db = qta3
    for bad in (
        {"total_limit": 1000, "decision_date": "2026-11-01"},
        {"total_limit": 1000, "decision_number": "", "decision_date": "2026-11-01"},
        {"total_limit": 1000, "decision_number": "   ", "decision_date": "2026-11-01"},
        {"total_limit": 1000, "decision_number": "QD-1"},
        {"total_limit": 1000, "decision_number": "QD-1", "decision_date": None},
        {"total_limit": 0, "decision_number": "QD-1", "decision_date": "2026-11-01"},
    ):
        assert qta_send(db.qta_admin, "PUT", "/budgets/2026-11", bad, 422)["code"] == "VALIDATION_FAILED"

    with connect(db.owner) as conn:
        assert conn.execute("SELECT count(*) FROM qta_budget_revisions").fetchone() == (0,)


def test_budget_month_window(qta3):
    """Open window under frozen clock (2026-11, 2026-12): past/far-future -> QTA_PERIOD_NOT_OPEN; malformed -> QTA_INVALID_PERIOD."""
    db = qta3
    body = {"total_limit": 10_000, "decision_number": "QD-WIN", "decision_date": "2026-11-15"}

    # Current (2026-11) and next (2026-12) accepted.
    assert qta_send(db.qta_admin, "PUT", "/budgets/2026-11", body, 200)["month"] == "2026-11"
    assert qta_send(db.qta_admin, "PUT", "/budgets/2026-12", body, 200)["month"] == "2026-12"

    # Past (2026-10) and month after next (2027-01) -> 422 QTA_PERIOD_NOT_OPEN.
    for closed in ("2026-10", "2027-01"):
        assert qta_send(db.qta_admin, "PUT", f"/budgets/{closed}", body, 422)["code"] == "QTA_PERIOD_NOT_OPEN"
        # Entitlements lookup also enforces open window (R1).
        assert (
            qta_get(db.qta_admin, f"/users/{db.qta_admin_id}/entitlements", {"month": closed}, status=422)[
                "code"
            ]
            == "QTA_PERIOD_NOT_OPEN"
        )

    # Malformed / non-month strings -> 422 QTA_INVALID_PERIOD on both PUT and GET.
    for bad in ("2026-13", "2026-1", "HK1-2026", "semester", "exam", "2026-11-01"):
        assert qta_send(db.qta_admin, "PUT", f"/budgets/{bad}", body, 422)["code"] == "QTA_INVALID_PERIOD"
        assert qta_get(db.qta_admin, "/budgets", {"month": bad}, status=422)["code"] == "QTA_INVALID_PERIOD"
        assert (
            qta_get(db.qta_admin, f"/users/{db.qta_admin_id}/entitlements", {"month": bad}, status=422)[
                "code"
            ]
            == "QTA_INVALID_PERIOD"
        )


def test_unrecorded_month_shows_chua_ghi_nhan_while_quotas_apply(qta3):
    """F8: an open month with no revision shows 'chưa ghi nhận' while group quotas still apply."""
    db = qta3
    user = create_user(db.admin, db.unit_a, "unrec", active=True)
    grp = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_UNREC", "name": "Unrec"}, 201)
    qta_send(db.qta_admin, "PUT", f"/groups/{grp['id']}/members/{user['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 1200}]},
    )

    view = qta_get(db.qta_admin, "/budgets", {"month": "2026-12"})
    assert view["month"] == "2026-12"
    assert view["status"] == "NOT_RECORDED"
    assert view["status_label"] == "chưa ghi nhận"
    assert view["current"] is None and view["revisions"] == []
    assert view["allocation_status"] == "LIVE"
    assert view["allocated"] == 1200
    assert view["remaining"] is None and view["over_allocated"] is None

    # Group quotas still apply in entitlement lookup for that unrecorded month.
    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements", {"month": "2026-12"})
    assert _by_model(ent)[db.m1]["base_entitlement"] == 1200


def test_past_month_read_is_not_snapshotted(qta3):
    """R1: past months return revision history with allocated/remaining/over_allocated null and NOT_SNAPSHOTTED."""
    db = qta3
    with connect(db.runtime, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO qta_budget_revisions"
            " (institution_id, period_month, revision, total_limit, decision_number, decision_date, recorded_by)"
            " VALUES (%s, %s, 1, 20000, 'QD-OCT-1', %s, %s)",
            (db.tenant, date(2026, 10, 1), date(2026, 10, 1), db.qta_admin_id),
        )

    past = qta_get(db.qta_admin, "/budgets", {"month": "2026-10"})
    assert past["month"] == "2026-10"
    assert past["status"] == "RECORDED"
    assert past["current"]["decision_number"] == "QD-OCT-1"
    assert len(past["revisions"]) == 1
    assert past["allocation_status"] == "NOT_SNAPSHOTTED"
    assert past["allocated"] is None
    assert past["remaining"] is None
    assert past["over_allocated"] is None


def test_equal_to_allocated_is_allowed_and_below_is_409_with_details(qta3):
    """FR-QTA-011: total_limit == allocated succeeds (remaining=0); total_limit < allocated -> 409 + {allocated, deficit}."""
    db = qta3
    user = create_user(db.admin, db.unit_a, "exact", active=True)
    grp = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_EXACT", "name": "Exact"}, 201)
    qta_send(db.qta_admin, "PUT", f"/groups/{grp['id']}/members/{user['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 5000}]},
    )

    denied = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 4999, "decision_number": "QD-LOW", "decision_date": "2026-11-01"},
        409,
    )
    assert denied["code"] == "QTA_BUDGET_BELOW_ALLOCATED"
    assert denied["details"] == {"allocated": 5000, "deficit": 1}

    exact = qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 5000, "decision_number": "QD-EXACT", "decision_date": "2026-11-01"},
        200,
    )
    assert exact["allocated"] == 5000 and exact["remaining"] == 0 and exact["over_allocated"] == 0


def test_over_allocation_is_a_warning_not_a_block(qta3):
    """PD-Q1: quota edits and directory growth are never blocked by the budget; GET shows over_allocated > 0."""
    db = qta3
    u1 = create_user(db.admin, db.unit_a, "over1", active=True)
    u2 = create_user(db.admin, db.unit_a, "over2", active=True)
    grp = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_OVER", "name": "Over"}, 201)
    qta_send(db.qta_admin, "PUT", f"/groups/{grp['id']}/members/{u1['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 4000}]},
    )

    qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 5000, "decision_number": "QD-CAP", "decision_date": "2026-11-01"},
    )

    # Raising group quota above budget succeeds (never blocked).
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 6000}]},
        200,
    )
    # Adding a second member also succeeds (allocated = 12,000 > cap 5,000).
    qta_send(db.qta_admin, "PUT", f"/groups/{grp['id']}/members/{u2['id']}", None, 200)

    view = qta_get(db.qta_admin, "/budgets", {"month": "2026-11"})
    assert view["allocated"] == 12_000
    assert view["remaining"] == 0
    assert view["over_allocated"] == 7000


def test_budget_rbac_and_csrf(qta3):
    """Only direct GLOBAL AI_QUOTA_ADMIN with valid Origin and CSRF may PUT /qta/budgets/{month}."""
    db = qta3
    body = {"total_limit": 10_000, "decision_number": "QD-AUTH", "decision_date": "2026-11-01"}

    with client(db) as anon:
        expect(anon.put("/api/v1/qta/budgets/2026-11", json=body, headers=ORIGIN_HEADER), 401)

    for denied in (db.admin, db.mdl_admin, db.global_viewer, db.unit_viewer):
        qta_send(denied, "PUT", "/budgets/2026-11", body, 403)

    # Missing CSRF -> 403.
    expect(db.qta_admin.put("/api/v1/qta/budgets/2026-11", json=body, headers=ORIGIN_HEADER), 403)

    # Wrong Origin -> 403.
    bad_origin = csrf_headers(db.qta_admin) | {"Origin": "https://evil.example"}
    expect(db.qta_admin.put("/api/v1/qta/budgets/2026-11", json=body, headers=bad_origin), 403)


def test_tenant_isolation(qta3):
    """Another institution's users and budget revisions are completely invisible (404 / isolated)."""
    db = qta3
    other_inst = uuid4()
    with connect(db.owner, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO institutions (id, code, name) VALUES (%s, 'OTHER_Q3', 'Other Q3')",
            (other_inst,),
        )
        other_unit = conn.execute(
            "INSERT INTO units (institution_id, code, name) VALUES (%s, 'OU3', 'Other Unit') RETURNING id",
            (other_inst,),
        ).fetchone()[0]
        other_user = conn.execute(
            "INSERT INTO users (institution_id, primary_unit_id, username, display_name,"
            " code_type, institutional_code, state) VALUES (%s, %s, 'otherq3', 'Other User',"
            " 'STAFF', 'OQ3-1', 'ACTIVE') RETURNING id",
            (other_inst, other_unit),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO qta_budget_revisions"
            " (institution_id, period_month, revision, total_limit, decision_number, decision_date, recorded_by)"
            " VALUES (%s, %s, 1, 999999, 'QD-FOREIGN', %s, %s)",
            (other_inst, date(2026, 11, 1), date(2026, 11, 1), other_user),
        )

    assert str(other_user) not in {u["id"] for u in qta_get(db.qta_admin, "/users", {"limit": 100})["items"]}
    qta_get(db.qta_admin, f"/users/{other_user}/entitlements", status=404)
    qta_get(db.global_viewer, f"/users/{other_user}/entitlements", status=404)
    qta_get(db.unit_viewer, f"/users/{other_user}/entitlements", status=404)

    own_budget = qta_get(db.qta_admin, "/budgets", {"month": "2026-11"})
    assert own_budget["status"] == "NOT_RECORDED" and own_budget["revisions"] == []


def test_budget_audit_failure_rolls_back(qta3):
    """If audit_events INSERT fails, no qta_budget_revisions row is committed."""
    db = qta3
    with connect(db.owner, autocommit=True) as conn:
        conn.execute(
            sql.SQL("REVOKE INSERT ON audit_events FROM {}").format(
                sql.Identifier(db.roles.runtime)
            )
        )
    try:
        resp = send(
            db.qta_admin,
            "PUT",
            qta_path("/budgets/2026-11"),
            {"total_limit": 25_000, "decision_number": "QD-RB", "decision_date": "2026-11-01"},
        )
        assert resp.status_code == 500 and resp.json()["code"] == "DATABASE_ERROR"
    finally:
        with connect(db.owner, autocommit=True) as conn:
            conn.execute(
                sql.SQL("GRANT INSERT ON audit_events TO {}").format(
                    sql.Identifier(db.roles.runtime)
                )
            )

    with connect(db.owner) as conn:
        assert conn.execute("SELECT count(*) FROM qta_budget_revisions").fetchone() == (0,)


def test_concurrent_budget_writes_serialize(qta3):
    """Two concurrent PUT /qta/budgets/2026-11 threads produce revisions 1 and 2 with zero 500s."""
    db = qta3
    barrier = Barrier(2)
    headers = csrf_headers(db.qta_admin)
    cookies = dict(db.qta_admin.cookies)

    def write_budget(idx: int):
        with client(db) as browser:
            browser.cookies.update(cookies)
            barrier.wait()
            resp = browser.put(
                "/api/v1/qta/budgets/2026-11",
                json={
                    "total_limit": 10_000 + idx * 5000,
                    "decision_number": f"QD-CONC-{idx + 1}",
                    "decision_date": "2026-11-15",
                },
                headers=headers,
            )
            return resp.status_code, resp.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write_budget, range(2)))

    assert all(status == 200 for status, _ in results)
    revs = sorted(body["current"]["revision"] for _, body in results)
    assert revs == [1, 2]
    with connect(db.owner) as conn:
        stored = conn.execute(
            "SELECT revision FROM qta_budget_revisions ORDER BY revision"
        ).fetchall()
    assert stored == [(1,), (2,)]
