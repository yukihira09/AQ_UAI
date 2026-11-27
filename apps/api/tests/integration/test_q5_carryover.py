"""Stage Q5 carry-over integration tests (C6 & C7) against disposable PostgreSQL.

- C6: Pin ``sum(c["contributes"] for c in model["contributions"]) == model["base_entitlement"]``
  for every model in ``GET /qta/users/{id}/entitlements`` across overlapping active groups,
  disabled quota rules, inactive groups, and disabled users.
- C7: Real PostgreSQL (``aq_uai_runtime``) tests of ``access.check_ai_access`` for
  ``USER_NOT_FOUND`` (random UUID and user in another institution), ``USER_NOT_ACTIVE``
  (disabled and pending users), and ``NO_ENTITLEMENT`` (zero quota groups and disabled rule).
"""

from uuid import UUID, uuid4

from aq_uai_api.qta import access
from aq_uai_api.qta.access import AccessDecision

from .test_m2_mdl_schema import seed_tenant
from .test_q2_qta_groups import create_group, qta_get, qta_send
from .test_q3_qta_lookup_budgets import _by_model
from .test_q3_qta_lookup_budgets import qta3 as qta3
from .test_q4_qta_killswitch_reset import _setup_entitled_user
from .test_q4_qta_killswitch_reset import qta4 as qta4
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import create_user, expect, send
from .test_wp5_directory import directory as directory
from .test_wp5_directory import pytestmark as postgres_marks

pytestmark = postgres_marks


def _assert_contribution_sum_invariant(entitlements_payload: dict) -> None:
    """Every model's contribution breakdown must sum to its additive base_entitlement."""
    assert entitlements_payload["models"], "Expected at least one usable model"
    total = 0
    for model in entitlements_payload["models"]:
        contrib_sum = sum(item["contributes"] for item in model["contributions"])
        assert contrib_sum == model["base_entitlement"], (
            model["technical_id"],
            contrib_sum,
            model["base_entitlement"],
            model["contributions"],
        )
        total += model["base_entitlement"]
    assert total == entitlements_payload["base_entitlement_total"]


def test_c6_contributions_sum_equals_base_entitlement(qta3):
    """C6: sum(contributes) == base_entitlement across overlapping, disabled, inactive & disabled-user cases."""
    db = qta3
    alice = create_user(db.admin, db.unit_a, "c6alice", active=True)
    carol = create_user(db.admin, db.unit_a, "c6carol", active=True)
    expect(send(db.admin, "POST", f"/users/{carol['id']}/disable"), 200)

    # Group 1 (SYSTEM via sync): M1=1000 (enabled), M2=2000 (enabled).
    g_sys = create_group(db.admin, "SYSTEM", code="C6_SYS", name="Nhóm hệ thống C6")
    for uid in (alice["id"], carol["id"]):
        expect(send(db.admin, "PUT", f"/groups/{g_sys['id']}/members/{uid}"), 200)
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_sys['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 1000},
                {"model_id": db.m2, "enabled": True, "monthly_limit": 2000},
            ]
        },
    )

    # Group 2 (AI_SPECIALIST, active): M1=3000 (enabled), M2=5000 (DISABLED rule -> contributes 0).
    g_spec_on = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "C6_SPEC_ON", "name": "Chuyên biệt Bật"}, 201
    )
    for uid in (alice["id"], carol["id"]):
        qta_send(db.qta_admin, "PUT", f"/groups/{g_spec_on['id']}/members/{uid}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_spec_on['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 3000},
                {"model_id": db.m2, "enabled": False, "monthly_limit": 5000},
            ]
        },
    )

    # Group 3 (AI_SPECIALIST, later deactivated): M1=7000 (enabled), M2=9000 (enabled).
    g_spec_off = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "C6_SPEC_OFF", "name": "Chuyên biệt Tắt"}, 201
    )
    qta_send(db.qta_admin, "PUT", f"/groups/{g_spec_off['id']}/members/{alice['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_spec_off['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m1, "enabled": True, "monthly_limit": 7000},
                {"model_id": db.m2, "enabled": True, "monthly_limit": 9000},
            ]
        },
    )

    # 1. Overlapping active groups + disabled quota rule (M2 on C6_SPEC_ON has enabled=False, limit=5000).
    alice_overlap = qta_get(db.qta_admin, f"/users/{alice['id']}/entitlements", {"month": "2026-11"})
    _assert_contribution_sum_invariant(alice_overlap)
    overlap_models = _by_model(alice_overlap)
    assert overlap_models[db.m1]["base_entitlement"] == 11_000
    assert overlap_models[db.m2]["base_entitlement"] == 11_000
    disabled_contrib = [
        c for c in overlap_models[db.m2]["contributions"] if c["code"] == "C6_SPEC_ON"
    ]
    assert len(disabled_contrib) == 1
    assert disabled_contrib[0]["enabled"] is False
    assert disabled_contrib[0]["monthly_limit"] == 5000
    assert disabled_contrib[0]["contributes"] == 0

    # 2. Inactive group: deactivate C6_SPEC_OFF -> dropped from contributions and base_entitlement.
    qta_send(db.qta_admin, "POST", f"/groups/{g_spec_off['id']}/deactivate")
    alice_inactive_grp = qta_get(
        db.qta_admin, f"/users/{alice['id']}/entitlements", {"month": "2026-11"}
    )
    _assert_contribution_sum_invariant(alice_inactive_grp)
    after_models = _by_model(alice_inactive_grp)
    assert after_models[db.m1]["base_entitlement"] == 4000
    assert after_models[db.m2]["base_entitlement"] == 2000
    assert all(
        c["code"] != "C6_SPEC_OFF"
        for m in alice_inactive_grp["models"]
        for c in m["contributions"]
    )

    # 3. Disabled user: contributions empty, base_entitlement == 0 on every model.
    carol_ent = qta_get(db.qta_admin, f"/users/{carol['id']}/entitlements", {"month": "2026-11"})
    _assert_contribution_sum_invariant(carol_ent)
    assert carol_ent["user"]["state"] == "DISABLED"
    assert carol_ent["base_entitlement_total"] == 0
    assert all(m["contributions"] == [] and m["base_entitlement"] == 0 for m in carol_ent["models"])


def test_c7_check_ai_access_postgres_not_found_not_active_no_entitlement(qta4):
    """C7: real PostgreSQL (aq_uai_runtime) checks for USER_NOT_FOUND, USER_NOT_ACTIVE & NO_ENTITLEMENT."""
    db = qta4
    m_ext_id = UUID(db.m_ext)
    m_int_id = UUID(db.m_int)

    # Another institution's active user (must be invisible -> USER_NOT_FOUND).
    _other_institution, other_tenant_user = seed_tenant(db.owner, "Q5OTHER")

    # Disabled user who otherwise has active group membership and enabled quotas.
    disabled_user = _setup_entitled_user(db, "c7disabled", ext_limit=1500, int_limit=1500)
    expect(send(db.admin, "POST", f"/users/{disabled_user['id']}/disable"), 200)

    # Pending user (not yet activated).
    pending_user = create_user(db.admin, db.unit_a, "c7pending", active=False)

    # Active user in zero quota groups.
    zero_group_user = create_user(db.admin, db.unit_a, "c7nogroup", active=True)

    # Active user whose only group rule is disabled.
    disabled_rule_user = create_user(db.admin, db.unit_a, "c7offrule", active=True)
    off_group = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "C7_OFF_GRP", "name": "Nhóm tắt quy tắc"}, 201
    )
    qta_send(db.qta_admin, "PUT", f"/groups/{off_group['id']}/members/{disabled_rule_user['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{off_group['id']}/quotas",
        {"quotas": [{"model_id": db.m_ext, "enabled": False, "monthly_limit": 2000}]},
    )

    with db.runtime_factory.begin() as session:
        # 1. USER_NOT_FOUND: random UUID and user belonging to another institution.
        assert access.check_ai_access(session, db.tenant, uuid4(), m_ext_id) == AccessDecision(
            allowed=False, reason="USER_NOT_FOUND", suspension_id=None
        )
        assert access.check_ai_access(
            session, db.tenant, other_tenant_user, m_ext_id
        ) == AccessDecision(allowed=False, reason="USER_NOT_FOUND", suspension_id=None)

        # 2. USER_NOT_ACTIVE: disabled user (even with active quota group) and pending user.
        assert access.check_ai_access(
            session, db.tenant, UUID(disabled_user["id"]), m_ext_id
        ) == AccessDecision(allowed=False, reason="USER_NOT_ACTIVE", suspension_id=None)
        assert access.check_ai_access(
            session, db.tenant, UUID(pending_user["id"]), m_ext_id
        ) == AccessDecision(allowed=False, reason="USER_NOT_ACTIVE", suspension_id=None)

        # 3. NO_ENTITLEMENT: active user in zero groups, and active user with only disabled quota rule.
        assert access.check_ai_access(
            session, db.tenant, UUID(zero_group_user["id"]), m_ext_id
        ) == AccessDecision(allowed=False, reason="NO_ENTITLEMENT", suspension_id=None)
        assert access.check_ai_access(
            session, db.tenant, UUID(zero_group_user["id"]), m_int_id
        ) == AccessDecision(allowed=False, reason="NO_ENTITLEMENT", suspension_id=None)
        assert access.check_ai_access(
            session, db.tenant, UUID(disabled_rule_user["id"]), m_ext_id
        ) == AccessDecision(allowed=False, reason="NO_ENTITLEMENT", suspension_id=None)
