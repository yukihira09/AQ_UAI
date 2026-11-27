"""Stage Q4 carry-over corrections (C1–C3) against disposable PostgreSQL."""

import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aq_uai_api.db import audit
from aq_uai_api.db.identity import AuditEvent
from aq_uai_api.qta import access, entitlements, periods

from .test_q2_qta_groups import audit_rows, create_group, qta_get, qta_send
from .test_q3_qta_lookup_budgets import qta3 as qta3
from .test_wp5_directory import (
    auth_db as auth_db,
)
from .test_wp5_directory import (
    bootstrapped as bootstrapped,
)
from .test_wp5_directory import (
    create_user,
    expect,
    send,
)
from .test_wp5_directory import (
    directory as directory,
)
from .test_wp5_directory import (
    pytestmark as postgres_marks,
)

pytestmark = postgres_marks

ENTITLEMENTS_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "aq_uai_api" / "qta" / "entitlements.py"
)


def test_inactive_provider_models_are_not_usable_anywhere(qta3):
    """C1 / R6: deactivating an MDL provider makes its active models unusable everywhere in QTA."""
    db = qta3
    alice = create_user(db.admin, db.unit_a, "c1alice", active=True)
    g_sys = create_group(db.admin, "SYSTEM", code="G_C1", name="Nhóm C1")
    expect(send(db.admin, "PUT", f"/groups/{g_sys['id']}/members/{alice['id']}"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")

    # Create a dedicated unrouted INTERNAL provider + active model through the real MDL API.
    provider = expect(
        send(
            db.mdl_admin,
            "POST",
            "/mdl/providers",
            {
                "name": "C1 Internal Provider",
                "provider_type": "INTERNAL",
                "api_style": "OPENAI_COMPATIBLE",
                "endpoint": "http://ollama-c1:11434/v1",
                "auth_scheme": "NONE",
            },
        ),
        201,
    )
    model = expect(
        send(
            db.mdl_admin,
            "POST",
            "/mdl/models",
            {
                "provider_id": provider["id"],
                "technical_id": "c1-llama",
                "display_name": "C1 Llama",
                "capabilities": ["TEXT"],
                "risk_level": "LOW",
            },
        ),
        201,
    )

    # Configure quotas on both M1 (active provider) and C1 Llama (dedicated provider).
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 1000},
                {"model_id": model["id"], "enabled": True, "monthly_limit": 2500},
            ]
        },
    )

    # Before provider deactivation: /qta/models includes C1 Llama, allocated = 3500, access ALLOWED.
    listed_before = {item["id"] for item in qta_get(db.qta_admin, "/models")["items"]}
    assert model["id"] in listed_before
    assert qta_get(db.qta_admin, "/budgets", {"month": "2026-11"})["allocated"] == 3500
    ent_before = qta_get(db.qta_admin, f"/users/{alice['id']}/entitlements", {"month": "2026-11"})
    assert ent_before["base_entitlement_total"] == 3500
    assert model["id"] in {m["model_id"] for m in ent_before["models"]}

    with db.runtime_factory() as session:
        assert (
            access.check_ai_access(
                session, UUID(db.tenant), UUID(alice["id"]), UUID(model["id"])
            ).allowed
            is True
        )

    # Deactivate the provider through the real MDL API (model itself remains active=true in DB!).
    deactivated = expect(
        send(db.mdl_admin, "POST", f"/mdl/providers/{provider['id']}/deactivate"), 200
    )
    assert deactivated["active"] is False

    # 1. GET /qta/models omits C1 Llama.
    listed_after = {item["id"] for item in qta_get(db.qta_admin, "/models")["items"]}
    assert model["id"] not in listed_after

    # 2. Institutional allocated drops immediately from 3500 -> 1000.
    assert qta_get(db.qta_admin, "/budgets", {"month": "2026-11"})["allocated"] == 1000

    # 3. Personal lookup omits C1 Llama and drops total to 1000.
    ent_after = qta_get(db.qta_admin, f"/users/{alice['id']}/entitlements", {"month": "2026-11"})
    assert ent_after["base_entitlement_total"] == 1000
    assert model["id"] not in {m["model_id"] for m in ent_after["models"]}

    # 4. Quota upsert referencing C1 Llama fails with 409 QTA_MODEL_NOT_ELIGIBLE.
    refused = qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {"quotas": [{"model_id": model["id"], "enabled": True, "monthly_limit": 3000}]},
        409,
    )
    assert refused["code"] == "QTA_MODEL_NOT_ELIGIBLE"

    # 5. check_ai_access blocks with MODEL_UNAVAILABLE.
    with db.runtime_factory() as session:
        denied = access.check_ai_access(
            session, UUID(db.tenant), UUID(alice["id"]), UUID(model["id"])
        )
        assert denied.allowed is False and denied.reason == "MODEL_UNAVAILABLE"

    # 6. Stored quota row on the group was NEVER deleted (model_active shows False while inactive).
    detail_inactive = qta_get(db.qta_admin, f"/groups/{g_sys['id']}")
    by_mid_inactive = {q["model_id"]: q for q in detail_inactive["quotas"]}
    assert by_mid_inactive[model["id"]]["monthly_limit"] == 2500
    assert by_mid_inactive[model["id"]]["model_active"] is False

    # Re-activate provider via real MDL API -> everything returns immediately (PD-Q5).
    expect(send(db.mdl_admin, "POST", f"/mdl/providers/{provider['id']}/activate"), 200)
    assert model["id"] in {item["id"] for item in qta_get(db.qta_admin, "/models")["items"]}
    assert qta_get(db.qta_admin, "/budgets", {"month": "2026-11"})["allocated"] == 3500
    ent_restored = qta_get(db.qta_admin, f"/users/{alice['id']}/entitlements", {"month": "2026-11"})
    assert ent_restored["base_entitlement_total"] == 3500
    with db.runtime_factory() as session:
        assert (
            access.check_ai_access(
                session, UUID(db.tenant), UUID(alice["id"]), UUID(model["id"])
            ).allowed
            is True
        )


def test_qualifying_rule_single_source(qta3):
    """C2: compute_user_entitlements, allocated_for_month & user_model_base_entitlement share _qualifying_quota_rows."""
    tree = ast.parse(ENTITLEMENTS_PATH.read_text())
    fn_calls: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            calls = {
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            fn_calls[node.name] = calls

    assert "_qualifying_quota_rows" in fn_calls
    for consumer in (
        "compute_user_entitlements",
        "allocated_for_month",
        "user_model_base_entitlement",
    ):
        assert "_qualifying_quota_rows" in fn_calls[consumer], consumer

    # Verify runtime agreement across overlapping groups, disabled user, and disabled quota.
    db = qta3
    u1 = create_user(db.admin, db.unit_a, "c2u1", active=True)
    u2 = create_user(db.admin, db.unit_b, "c2u2", active=True)
    u3 = create_user(db.admin, db.unit_a, "c2disabled", active=True)
    expect(send(db.admin, "POST", f"/users/{u3['id']}/disable"), 200)

    g_sys = create_group(db.admin, "SYSTEM", code="G_C2_SYS")
    for uid in (u1["id"], u2["id"], u3["id"]):
        expect(send(db.admin, "PUT", f"/groups/{g_sys['id']}/members/{uid}"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 900},
                {"model_id": db.m2, "enabled": False, "monthly_limit": 4000},
            ]
        },
    )

    g_spec = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_C2", "name": "AI C2"}, 201)
    qta_send(db.qta_admin, "PUT", f"/groups/{g_spec['id']}/members/{u1['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_spec['id']}/quotas",
        {"quotas": [{"model_id": db.m1, "enabled": True, "monthly_limit": 1100}]},
    )

    all_users = qta_get(db.qta_admin, "/users", {"limit": 100})["items"]
    sum_lookup = sum(
        qta_get(db.qta_admin, f"/users/{u['id']}/entitlements")["base_entitlement_total"]
        for u in all_users
    )
    assert sum_lookup == 2900  # u1: 900+1100=2000; u2: 900; u3 disabled: 0; admins: 0

    with db.runtime_factory() as session:
        tenant_uuid = UUID(db.tenant)
        assert entitlements.allocated_for_month(session, tenant_uuid) == sum_lookup
        sum_pair = sum(
            entitlements.user_model_base_entitlement(
                session, tenant_uuid, UUID(u["id"]), UUID(mid)
            )
            for u in all_users
            for mid in (db.m1, db.m2)
        )
        assert sum_pair == sum_lookup


def test_quota_threshold_change_audits_before_and_after(qta3):
    """C3: changing only warning_threshold_pct records before_warning_threshold_pct & warning_threshold_pct."""
    db = qta3
    g_sys = create_group(db.admin, "SYSTEM", code="G_C3")
    qta_send(db.qta_admin, "POST", "/groups/sync")

    # 1. Initial insert with threshold 80 -> before_warning_threshold_pct is None, after is 80.
    created = qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {
            "quotas": [
                {
                    "model_id": db.m1,
                    "enabled": True,
                    "monthly_limit": 1000,
                    "warning_threshold_pct": 80,
                }
            ]
        },
    )
    quota_id = created["quotas"][0]["id"]

    # 2. Change ONLY threshold 80 -> 60 (enabled & monthly_limit unchanged).
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {
            "quotas": [
                {
                    "model_id": db.m1,
                    "enabled": True,
                    "monthly_limit": 1000,
                    "warning_threshold_pct": 60,
                }
            ]
        },
    )

    # 3. Clear threshold 60 -> None.
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {
            "quotas": [
                {
                    "model_id": db.m1,
                    "enabled": True,
                    "monthly_limit": 1000,
                    "warning_threshold_pct": None,
                }
            ]
        },
    )

    rows = audit_rows(db, action_prefix="qta.group_quota_updated", target_id=quota_id)
    assert len(rows) == 3
    assert rows[0][4]["before_warning_threshold_pct"] is None
    assert rows[0][4]["warning_threshold_pct"] == 80
    assert rows[1][4]["before_warning_threshold_pct"] == 80
    assert rows[1][4]["warning_threshold_pct"] == 60
    assert rows[2][4]["before_warning_threshold_pct"] == 60
    assert rows[2][4]["warning_threshold_pct"] is None

    # Backward compatibility: legacy stored audit JSON without before_warning_threshold_pct still validates.
    legacy_event = AuditEvent(
        institution_id=UUID(db.tenant),
        actor_id=UUID(db.qta_admin_id),
        action="qta.group_quota_updated",
        target_type="qta_group_model_quota",
        target_id=UUID(quota_id),
        outcome="SUCCESS",
        occurred_at=datetime(2026, 11, 15, tzinfo=UTC),
        request_id="req-legacy",
        changes={
            "group_id": g_sys["id"],
            "model_id": db.m1,
            "before_enabled": True,
            "after_enabled": True,
            "before_limit": 1000,
            "after_limit": 1000,
            "warning_threshold_pct": 75,
        },
    )
    projected = audit.public_audit_changes(legacy_event)
    assert projected["before_warning_threshold_pct"] is None
    assert projected["warning_threshold_pct"] == 75
    assert periods.utc_now() is not None
