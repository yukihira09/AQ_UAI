"""Stage Q2 against disposable PostgreSQL: group registry, sync, specialist groups & quotas.

All requests go through real FastAPI routes with session cookies, exact Origin, CSRF headers,
and the restricted ``aq_uai_runtime`` database login.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from psycopg import sql

from .test_m1_mdl_access import sign_in
from .test_m2_mdl_schema import add_model, add_provider
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


def create_group(browser, kind: str, *, code: str | None = None, name: str | None = None):
    group_code = code or kind.lower()
    group_name = name or group_code
    return expect(
        send(browser, "POST", "/groups", {"code": group_code, "name": group_name, "kind": kind}),
        201,
    )


def qta_path(path: str) -> str:
    return "/qta" + path


def qta_get(browser, path: str, params=None, status: int = 200):
    return expect(get(browser, qta_path(path), params=params), status)


def qta_send(browser, method: str, path: str, body=None, status: int = 200):
    return expect(send(browser, method, qta_path(path), body), status)


def audit_rows(db, *, action_prefix: str | None = None, target_id: str | None = None):
    clauses = []
    params = []
    if action_prefix is not None:
        clauses.append("action LIKE %s")
        params.append(action_prefix)
    if target_id is not None:
        clauses.append("target_id = %s")
        params.append(target_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect(db.owner) as connection:
        return connection.execute(
            f"SELECT action, actor_id, target_type, target_id, changes"
            f" FROM audit_events {where} ORDER BY occurred_at, id",
            params,
        ).fetchall()


@pytest.fixture
def qta(directory):
    db = directory
    unit_a = create_unit(db.admin, "Q2UA")
    unit_b = create_unit(db.admin, "Q2UB")
    qta_admin_user = create_user(db.admin, unit_a["id"], "q2admin", active=True)
    global_viewer_user = create_user(db.admin, unit_a["id"], "q2gviewer", active=True)
    unit_viewer_user = create_user(db.admin, unit_a["id"], "q2uviewer", active=True)
    mdl_admin_user = create_user(db.admin, unit_a["id"], "q2mdladmin", active=True)
    member_user = create_user(db.admin, unit_a["id"], "q2member", active=True)
    disabled_user = create_user(db.admin, unit_b["id"], "q2disabled", active=True)
    expect(send(db.admin, "POST", f"/users/{disabled_user['id']}/disable"), 200)

    add_grant(db.admin, f"/users/{qta_admin_user['id']}", "AI_QUOTA_ADMIN")
    add_grant(db.admin, f"/users/{global_viewer_user['id']}", "AI_QUOTA_VIEWER")
    add_grant(db.admin, f"/users/{unit_viewer_user['id']}", "AI_QUOTA_VIEWER", unit_a["id"])
    add_grant(db.admin, f"/users/{mdl_admin_user['id']}", "AI_MODEL_ADMIN")

    with connect(db.runtime, autocommit=True) as conn:
        ext_provider = add_provider(conn, db.tenant, "Q2 External", provider_type="EXTERNAL")
        int_provider = add_provider(conn, db.tenant, "Q2 Internal", provider_type="INTERNAL")
        model_a = add_model(conn, db.tenant, ext_provider, "gpt-q2", risk_level="LOW")
        model_b = add_model(conn, db.tenant, int_provider, "llama-q2", risk_level="LOW")
        inactive_model = add_model(conn, db.tenant, int_provider, "retired-q2", risk_level="LOW")
        conn.execute("UPDATE mdl_models SET active = false WHERE id = %s", (inactive_model,))

    db.unit_a = unit_a["id"]
    db.unit_b = unit_b["id"]
    db.qta_admin_id = qta_admin_user["id"]
    db.member_id = member_user["id"]
    db.disabled_user_id = disabled_user["id"]
    db.model_a = str(model_a)
    db.model_b = str(model_b)
    db.inactive_model = str(inactive_model)

    db.qta_admin = sign_in(db, "q2admin")
    db.global_viewer = sign_in(db, "q2gviewer")
    db.unit_viewer = sign_in(db, "q2uviewer")
    db.mdl_admin = sign_in(db, "q2mdladmin")
    try:
        yield db
    finally:
        for browser in (db.qta_admin, db.global_viewer, db.unit_viewer, db.mdl_admin):
            browser.__exit__(None, None, None)


def test_rbac_matrix(qta):
    db = qta
    sys_group = create_group(db.admin, "SYSTEM", code="G_RBAC")
    # Sync once so an enrolled group exists for detail/members/quotas checks.
    qta_send(db.qta_admin, "POST", "/groups/sync")
    spec = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "AI_RBAC", "name": "RBAC Specialist"}, 201
    )

    read_routes = [
        "/models",
        "/groups",
        "/groups/sync-runs",
        f"/groups/{sys_group['id']}",
        f"/groups/{sys_group['id']}/members",
    ]
    write_routes = [
        ("POST", "/groups/sync", None),
        ("POST", "/groups", {"code": "AI_NEW_R", "name": "New R"}),
        ("PATCH", f"/groups/{spec['id']}", {"name": "Renamed"}),
        ("POST", f"/groups/{spec['id']}/deactivate", None),
        ("POST", f"/groups/{spec['id']}/activate", None),
        ("PUT", f"/groups/{spec['id']}/members/{db.member_id}", None),
        ("DELETE", f"/groups/{spec['id']}/members/{db.member_id}", None),
        (
            "PUT",
            f"/groups/{sys_group['id']}/quotas",
            {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 1000}]},
        ),
    ]

    # Anonymous: 401 on every Q2 route.
    with client(db) as anon:
        for path in read_routes:
            expect(get(anon, qta_path(path)), 401)
        for method, path, body in write_routes:
            expect(anon.request(method, f"/api/v1{qta_path(path)}", json=body, headers=ORIGIN_HEADER), 401)

    # FOUNDATION_ADMIN, AI_MODEL_ADMIN, AI_QUOTA_VIEWER (UNIT): 403 on every Q2 route.
    for denied_browser in (db.admin, db.mdl_admin, db.unit_viewer):
        for path in read_routes:
            qta_get(denied_browser, path, status=403)
        for method, path, body in write_routes:
            qta_send(denied_browser, method, path, body, status=403)

    # AI_QUOTA_VIEWER (GLOBAL): reads 200, writes 403.
    for path in read_routes:
        qta_get(db.global_viewer, path, status=200)
    for method, path, body in write_routes:
        qta_send(db.global_viewer, method, path, body, status=403)

    # Writes without CSRF header are refused even for AI_QUOTA_ADMIN (403).
    for method, path, body in write_routes:
        response = db.qta_admin.request(
            method, f"/api/v1{qta_path(path)}", json=body, headers=ORIGIN_HEADER
        )
        expect(response, 403)

    # AI_QUOTA_ADMIN succeeds on all reads and writes.
    models_page = qta_get(db.qta_admin, "/models")
    assert {item["id"] for item in models_page["items"]} == {db.model_a, db.model_b}
    assert all(item["provider_type"] in {"EXTERNAL", "INTERNAL"} for item in models_page["items"])
    assert db.inactive_model not in {item["id"] for item in models_page["items"]}

    qta_send(db.qta_admin, "PATCH", f"/groups/{spec['id']}", {"name": "Renamed Ok"}, 200)
    qta_send(db.qta_admin, "PUT", f"/groups/{spec['id']}/members/{db.member_id}", None, 200)
    qta_send(db.qta_admin, "DELETE", f"/groups/{spec['id']}/members/{db.member_id}", None, 204)
    qta_send(db.qta_admin, "POST", f"/groups/{spec['id']}/deactivate", None, 200)
    qta_send(db.qta_admin, "POST", f"/groups/{spec['id']}/activate", None, 200)
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{sys_group['id']}/quotas",
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 1000}]},
        200,
    )


def test_group_list_empty_before_first_sync(qta):
    """FR-QTA-001 AC2: authorized account opens an empty group list before sync even with directory groups."""
    db = qta
    sys_group = create_group(db.admin, "SYSTEM", code="G_PRESYNC")
    assert qta_get(db.qta_admin, "/groups")["items"] == []
    assert qta_get(db.qta_admin, "/groups")["total"] == 0
    assert qta_get(db.global_viewer, "/groups")["items"] == []
    assert qta_get(db.qta_admin, "/groups/sync-runs")["items"] == []
    qta_get(db.qta_admin, f"/groups/{sys_group['id']}", status=404)
    qta_get(db.qta_admin, f"/groups/{sys_group['id']}/members", status=404)


def test_sync_enrols_system_and_directory_specialist_groups(qta):
    """FR-QTA-020 AC1: sync enrolls active SYSTEM groups and directory-created AI_SPECIALIST groups."""
    db = qta
    g_gv = create_group(db.admin, "SYSTEM", code="G_GV", name="Giảng viên")
    g_sv = create_group(db.admin, "SYSTEM", code="G_SV", name="Sinh viên")
    dir_spec = create_group(db.admin, "AI_SPECIALIST", code="AI_DIR", name="Nhóm AI từ danh bạ")
    # Inactive SYSTEM group created before sync must not be enrolled.
    inactive_sys = create_group(db.admin, "SYSTEM", code="G_INACT", name="Ngừng")
    expect(send(db.admin, "POST", f"/groups/{inactive_sys['id']}/deactivate"), 200)

    expect(send(db.admin, "PUT", f"/groups/{g_gv['id']}/members/{db.member_id}"), 200)
    expect(send(db.admin, "PUT", f"/groups/{g_gv['id']}/members/{db.disabled_user_id}"), 200)

    first = qta_send(db.qta_admin, "POST", "/groups/sync")
    assert first["system_group_count"] == 2
    assert first["specialist_group_count"] == 1
    assert first["active_member_count"] == 1  # only ACTIVE users with active memberships
    assert first["groups_added"] == 3
    assert first["groups_retired"] == 0

    listed = qta_get(db.qta_admin, "/groups")
    assert listed["total"] == 3
    by_id = {item["id"]: item for item in listed["items"]}
    assert by_id[g_gv["id"]]["origin"] == "SYNC"
    assert by_id[g_gv["id"]]["in_directory"] is True
    assert by_id[g_gv["id"]]["active_member_count"] == 1
    assert by_id[g_sv["id"]]["origin"] == "SYNC"
    assert by_id[dir_spec["id"]]["origin"] == "SPECIALIST"
    assert by_id[dir_spec["id"]]["kind"] == "AI_SPECIALIST"
    assert inactive_sys["id"] not in by_id

    # Filters kind, origin, active work cleanly.
    assert qta_get(db.qta_admin, "/groups", {"kind": "SYSTEM"})["total"] == 2
    assert qta_get(db.qta_admin, "/groups", {"origin": "SPECIALIST"})["total"] == 1

    # Second sync with no changes adds/retires 0; sync-runs returns newest first.
    second = qta_send(db.qta_admin, "POST", "/groups/sync")
    assert second["groups_added"] == 0 and second["groups_retired"] == 0
    runs = qta_get(db.qta_admin, "/groups/sync-runs")["items"]
    assert [r["id"] for r in runs[:2]] == [second["id"], first["id"]]

    # Audit trail records qta.groups_synced with exact counts.
    synced_audits = audit_rows(db, action_prefix="qta.groups_synced")
    assert len(synced_audits) == 2
    assert synced_audits[0][4]["groups_added"] == 3 and synced_audits[0][4]["groups_retired"] == 0


def test_sync_retires_and_restores_system_groups_without_deleting_quotas(qta):
    db = qta
    g_gv = create_group(db.admin, "SYSTEM", code="G_RET", name="Retire Test")
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_gv['id']}/quotas",
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 2500}]},
    )

    # Deactivate in Phase 2 directory -> sync marks in_directory=false, groups_retired=1, keeps quotas.
    expect(send(db.admin, "POST", f"/groups/{g_gv['id']}/deactivate"), 200)
    retire_run = qta_send(db.qta_admin, "POST", "/groups/sync")
    assert retire_run["groups_retired"] == 1 and retire_run["system_group_count"] == 0

    detail = qta_get(db.qta_admin, f"/groups/{g_gv['id']}")
    assert detail["in_directory"] is False and detail["active"] is False
    assert len(detail["quotas"]) == 1 and detail["quotas"][0]["monthly_limit"] == 2500

    # Syncing again while still inactive does not double-count groups_retired.
    repeat_run = qta_send(db.qta_admin, "POST", "/groups/sync")
    assert repeat_run["groups_retired"] == 0

    # Re-activating in directory -> sync restores in_directory=true, quotas still intact.
    expect(send(db.admin, "POST", f"/groups/{g_gv['id']}/activate"), 200)
    restore_run = qta_send(db.qta_admin, "POST", "/groups/sync")
    assert restore_run["groups_added"] == 0 and restore_run["groups_retired"] == 0
    assert restore_run["system_group_count"] == 1

    restored = qta_get(db.qta_admin, f"/groups/{g_gv['id']}")
    assert restored["in_directory"] is True and restored["active"] is True
    assert restored["quotas"][0]["monthly_limit"] == 2500


def test_sync_preserves_specialist_groups_members_and_quotas(qta):
    """FR-QTA-020 AC2 & RULE-QTA-05: sync never deletes or modifies existing SPECIALIST rows/quotas."""
    db = qta
    create_group(db.admin, "SYSTEM", code="G_SYS1", name="System One")
    active_spec = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "AI_KEEP", "name": "Keep Me"}, 201
    )
    qta_send(db.qta_admin, "PUT", f"/groups/{active_spec['id']}/members/{db.member_id}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{active_spec['id']}/quotas",
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 3000}]},
    )

    # Also keep an inactive SPECIALIST group to prove sync never flips its in_directory or last_synced_at.
    inactive_spec = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "AI_PAUSED", "name": "Paused Specialist"}, 201
    )
    qta_send(db.qta_admin, "POST", f"/groups/{inactive_spec['id']}/deactivate")

    run = qta_send(db.qta_admin, "POST", "/groups/sync")
    assert run["groups_added"] == 1  # only G_SYS1
    assert run["groups_retired"] == 0  # inactive_spec was NOT touched
    assert run["specialist_group_count"] == 1  # active_spec only

    kept = qta_get(db.qta_admin, f"/groups/{active_spec['id']}")
    assert kept["origin"] == "SPECIALIST" and kept["in_directory"] is True
    assert kept["last_synced_at"] is None
    assert kept["active_member_count"] == 1
    assert kept["quotas"][0]["monthly_limit"] == 3000

    paused = qta_get(db.qta_admin, f"/groups/{inactive_spec['id']}")
    assert paused["origin"] == "SPECIALIST"
    assert paused["in_directory"] is True
    assert paused["last_synced_at"] is None

    members = qta_get(db.qta_admin, f"/groups/{active_spec['id']}/members")
    assert [m["user"]["id"] for m in members["items"]] == [db.member_id]


def test_sync_ignores_authorization_groups(qta):
    db = qta
    auth_group = create_group(db.admin, "AUTHORIZATION", code="G_AUTH_IGN")
    sys_group = create_group(db.admin, "SYSTEM", code="G_SYS_ONLY")

    run = qta_send(db.qta_admin, "POST", "/groups/sync")
    assert run["groups_added"] == 1 and run["system_group_count"] == 1
    listed_ids = {item["id"] for item in qta_get(db.qta_admin, "/groups")["items"]}
    assert sys_group["id"] in listed_ids
    assert auth_group["id"] not in listed_ids
    qta_get(db.qta_admin, f"/groups/{auth_group['id']}", status=404)


def test_specialist_group_lifecycle_uses_directory_audit_actions(qta):
    """FR-QTA-022 AC1: QTA specialist lifecycle delegates to directory.service and writes directory audits."""
    db = qta
    created = qta_send(
        db.qta_admin, "POST", "/groups", {"code": "AI_RES", "name": "Nhóm AI Nghiên cứu"}, 201
    )
    assert created["kind"] == "AI_SPECIALIST" and created["origin"] == "SPECIALIST"
    assert created["in_directory"] is True and created["active"] is True

    # Confirm qta_quota_groups row exists with origin SPECIALIST.
    with connect(db.owner) as conn:
        reg_row = conn.execute(
            "SELECT group_kind, origin, in_directory FROM qta_quota_groups WHERE group_id = %s",
            (created["id"],),
        ).fetchone()
    assert reg_row == ("AI_SPECIALIST", "SPECIALIST", True)

    # Rename, add member, deactivate/reactivate member, deactivate/activate group.
    renamed = qta_send(
        db.qta_admin, "PATCH", f"/groups/{created['id']}", {"name": "Nhóm AI Lab"}
    )
    assert renamed["name"] == "Nhóm AI Lab"

    added = qta_send(db.qta_admin, "PUT", f"/groups/{created['id']}/members/{db.member_id}")
    assert added["active"] is True and added["user"]["id"] == db.member_id
    assert qta_get(db.qta_admin, f"/groups/{created['id']}")["active_member_count"] == 1

    qta_send(db.qta_admin, "DELETE", f"/groups/{created['id']}/members/{db.member_id}", None, 204)
    assert qta_get(db.qta_admin, f"/groups/{created['id']}")["active_member_count"] == 0

    qta_send(db.qta_admin, "PUT", f"/groups/{created['id']}/members/{db.member_id}")
    assert qta_get(db.qta_admin, f"/groups/{created['id']}")["active_member_count"] == 1

    deactivated = qta_send(db.qta_admin, "POST", f"/groups/{created['id']}/deactivate")
    assert deactivated["active"] is False
    # Duplicate deactivate -> 409 CONFLICT (same as directory.service).
    qta_send(db.qta_admin, "POST", f"/groups/{created['id']}/deactivate", None, 409)
    # Adding member to inactive group -> 409 CONFLICT.
    qta_send(db.qta_admin, "PUT", f"/groups/{created['id']}/members/{db.disabled_user_id}", None, 409)

    activated = qta_send(db.qta_admin, "POST", f"/groups/{created['id']}/activate")
    assert activated["active"] is True

    # Duplicate specialist group code -> 409 QTA_DUPLICATE.
    dup = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_RES", "name": "Dup"}, 409)
    assert dup["code"] == "QTA_DUPLICATE"

    # Existing directory audit actions were recorded on this group with qta_admin as actor.
    actions = [row[0] for row in audit_rows(db, target_id=created["id"])]
    assert actions == [
        "group.created",
        "group.updated",
        "membership.state_changed",
        "membership.state_changed",
        "membership.state_changed",
        "group.state_changed",
        "group.state_changed",
    ]
    assert all(str(row[1]) == db.qta_admin_id for row in audit_rows(db, target_id=created["id"]))


def test_quota_admin_cannot_touch_system_or_authorization_groups(qta):
    db = qta
    sys_group = create_group(db.admin, "SYSTEM", code="G_LOCKED_SYS")
    auth_group = create_group(db.admin, "AUTHORIZATION", code="G_LOCKED_AUTH")
    dir_spec = create_group(db.admin, "AI_SPECIALIST", code="AI_UNENROLLED")
    qta_send(db.qta_admin, "POST", "/groups/sync")

    # Even after sync enrolls G_LOCKED_SYS, qta.manage cannot rename/toggle/edit members on SYSTEM or AUTHORIZATION.
    for gid in (sys_group["id"], auth_group["id"]):
        qta_send(db.qta_admin, "PATCH", f"/groups/{gid}", {"name": "Hacked"}, 403)
        qta_send(db.qta_admin, "POST", f"/groups/{gid}/deactivate", None, 403)
        qta_send(db.qta_admin, "POST", f"/groups/{gid}/activate", None, 403)
        qta_send(db.qta_admin, "PUT", f"/groups/{gid}/members/{db.member_id}", None, 403)
        qta_send(db.qta_admin, "DELETE", f"/groups/{gid}/members/{db.member_id}", None, 403)

    # Also verify qta.manage cannot create SYSTEM or AUTHORIZATION groups through Phase 2 /groups route.
    # AI_SPECIALIST too: quota admins create specialist groups only via /qta/groups.
    for kind in ("SYSTEM", "AUTHORIZATION", "AI_SPECIALIST"):
        expect(
            send(db.qta_admin, "POST", "/groups", {"code": f"TRY_{kind}", "name": "Nope", "kind": kind}),
            403,
        )
    expect(send(db.qta_admin, "PATCH", f"/groups/{sys_group['id']}", {"name": "Nope"}), 403)
    expect(send(db.qta_admin, "POST", f"/groups/{auth_group['id']}/deactivate"), 403)

    # An AI_SPECIALIST group created in directory AFTER sync (not yet enrolled) -> 422 QTA_GROUP_NOT_ELIGIBLE.
    unenrolled = create_group(db.admin, "AI_SPECIALIST", code="AI_NOT_YET")
    err = qta_send(db.qta_admin, "PATCH", f"/groups/{unenrolled['id']}", {"name": "Wait"}, 422)
    assert err["code"] == "QTA_GROUP_NOT_ELIGIBLE"
    # While the synced directory specialist group IS editable via QTA.
    qta_send(db.qta_admin, "PATCH", f"/groups/{dir_spec['id']}", {"name": "Now Editable"}, 200)


def test_directory_behaviour_unchanged_for_specialist_groups(qta):
    """FOUNDATION_ADMIN using Phase 2 /api/v1/groups still manages AI_SPECIALIST groups identically."""
    db = qta
    group = create_group(db.admin, "AI_SPECIALIST", code="DIR_SPEC_1", name="Dir Specialist")
    renamed = expect(send(db.admin, "PATCH", f"/groups/{group['id']}", {"name": "Dir Renamed"}), 200)
    assert renamed["name"] == "Dir Renamed"
    member = expect(send(db.admin, "PUT", f"/groups/{group['id']}/members/{db.member_id}"), 200)
    assert member["active"] is True
    expect(send(db.admin, "DELETE", f"/groups/{group['id']}/members/{db.member_id}"), 204)
    deactivated = expect(send(db.admin, "POST", f"/groups/{group['id']}/deactivate"), 200)
    assert deactivated["active"] is False
    activated = expect(send(db.admin, "POST", f"/groups/{group['id']}/activate"), 200)
    assert activated["active"] is True

    # Confirm directory audit actions are identical.
    actions = [row[0] for row in audit_rows(db, target_id=group["id"])]
    assert actions == [
        "group.created",
        "group.updated",
        "membership.state_changed",
        "membership.state_changed",
        "group.state_changed",
        "group.state_changed",
    ]


def test_two_models_two_limits_on_one_group(qta):
    """FR-QTA-021 AC1: one group can configure two distinct monthly limits for two active models."""
    db = qta
    g_gv = create_group(db.admin, "SYSTEM", code="G_MULTI")
    qta_send(db.qta_admin, "POST", "/groups/sync")

    updated = qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_gv['id']}/quotas",
        {
            "quotas": [
                {
                    "model_id": db.model_a,
                    "enabled": True,
                    "monthly_limit": 1000,
                    "warning_threshold_pct": 80,
                },
                {
                    "model_id": db.model_b,
                    "enabled": True,
                    "monthly_limit": 3500,
                    "warning_threshold_pct": 90,
                },
            ]
        },
    )
    by_model = {rule["model_id"]: rule for rule in updated["quotas"]}
    assert by_model[db.model_a]["monthly_limit"] == 1000
    assert by_model[db.model_a]["warning_threshold_pct"] == 80
    assert by_model[db.model_b]["monthly_limit"] == 3500
    assert by_model[db.model_b]["warning_threshold_pct"] == 90

    # Partial update on model_a preserves model_b untouched (never deletes rows).
    partial = qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{g_gv['id']}/quotas",
        {"quotas": [{"model_id": db.model_a, "enabled": False, "monthly_limit": 0}]},
    )
    by_model2 = {rule["model_id"]: rule for rule in partial["quotas"]}
    assert by_model2[db.model_a]["enabled"] is False and by_model2[db.model_a]["monthly_limit"] == 0
    assert by_model2[db.model_b]["enabled"] is True and by_model2[db.model_b]["monthly_limit"] == 3500


def test_quota_rules(qta):
    db = qta
    sys_group = create_group(db.admin, "SYSTEM", code="G_QRULES")
    unenrolled = create_group(db.admin, "SYSTEM", code="G_UNENROLLED")
    auth_group = create_group(db.admin, "AUTHORIZATION", code="G_AUTH_Q")

    # Unenrolled SYSTEM group and AUTHORIZATION group -> 422 QTA_GROUP_NOT_ELIGIBLE.
    sample = {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 500}]}
    assert qta_send(db.qta_admin, "PUT", f"/groups/{unenrolled['id']}/quotas", sample, 422)["code"] == "QTA_GROUP_NOT_ELIGIBLE"
    assert qta_send(db.qta_admin, "PUT", f"/groups/{auth_group['id']}/quotas", sample, 422)["code"] == "QTA_GROUP_NOT_ELIGIBLE"

    # Enroll sys_group and configure initial quota.
    qta_send(db.qta_admin, "POST", "/groups/sync")
    qta_send(db.qta_admin, "PUT", f"/groups/{sys_group['id']}/quotas", sample, 200)
    audits_before = audit_rows(db, action_prefix="qta.group_quota_updated")
    assert len(audits_before) == 1
    assert audits_before[0][4]["before_enabled"] is None and audits_before[0][4]["after_enabled"] is True
    assert audits_before[0][4]["before_limit"] is None and audits_before[0][4]["after_limit"] == 500

    # No-op upsert writes no audit event and leaves updated_at unchanged.
    before_detail = qta_get(db.qta_admin, f"/groups/{sys_group['id']}")
    qta_send(db.qta_admin, "PUT", f"/groups/{sys_group['id']}/quotas", sample, 200)
    after_detail = qta_get(db.qta_admin, f"/groups/{sys_group['id']}")
    assert after_detail["quotas"][0]["updated_at"] == before_detail["quotas"][0]["updated_at"]
    assert len(audit_rows(db, action_prefix="qta.group_quota_updated")) == 1

    # Changed row writes audit with exact before/after values.
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{sys_group['id']}/quotas",
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 900, "warning_threshold_pct": 75}]},
        200,
    )
    audits_after = audit_rows(db, action_prefix="qta.group_quota_updated")
    assert len(audits_after) == 2
    assert audits_after[1][4]["before_limit"] == 500 and audits_after[1][4]["after_limit"] == 900
    assert audits_after[1][4]["warning_threshold_pct"] == 75

    # Inactive model -> 409 QTA_MODEL_NOT_ELIGIBLE.
    inactive_err = qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{sys_group['id']}/quotas",
        {"quotas": [{"model_id": db.inactive_model, "enabled": True, "monthly_limit": 100}]},
        409,
    )
    assert inactive_err["code"] == "QTA_MODEL_NOT_ELIGIBLE"

    # Invalid payloads -> 422 VALIDATION_FAILED.
    for bad_body in (
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": -1}]},
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 100, "warning_threshold_pct": 0}]},
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 100, "warning_threshold_pct": 101}]},
        {
            "quotas": [
                {"model_id": db.model_a, "enabled": True, "monthly_limit": 100},
                {"model_id": db.model_a, "enabled": True, "monthly_limit": 200},
            ]
        },
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 100, "price": 5}]},
    ):
        assert qta_send(db.qta_admin, "PUT", f"/groups/{sys_group['id']}/quotas", bad_body, 422)["code"] == "VALIDATION_FAILED"

    # Retired or inactive group -> 422 QTA_GROUP_NOT_ELIGIBLE.
    expect(send(db.admin, "POST", f"/groups/{sys_group['id']}/deactivate"), 200)
    assert qta_send(db.qta_admin, "PUT", f"/groups/{sys_group['id']}/quotas", sample, 422)["code"] == "QTA_GROUP_NOT_ELIGIBLE"
    qta_send(db.qta_admin, "POST", "/groups/sync")  # now in_directory=false too
    assert qta_send(db.qta_admin, "PUT", f"/groups/{sys_group['id']}/quotas", sample, 422)["code"] == "QTA_GROUP_NOT_ELIGIBLE"


def test_tenant_isolation(qta):
    """Another institution's groups, users, and models are invisible (404 everywhere)."""
    db = qta
    other_inst = uuid4()
    with connect(db.owner, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO institutions (id, code, name) VALUES (%s, 'OTHER_Q2', 'Other Q2')",
            (other_inst,),
        )
        other_unit = conn.execute(
            "INSERT INTO units (institution_id, code, name) VALUES (%s, 'OU', 'Other Unit') RETURNING id",
            (other_inst,),
        ).fetchone()[0]
        other_user = conn.execute(
            "INSERT INTO users (institution_id, primary_unit_id, username, display_name,"
            " code_type, institutional_code, state) VALUES (%s, %s, 'otherq2', 'Other User',"
            " 'STAFF', 'OQ2-1', 'ACTIVE') RETURNING id",
            (other_inst, other_unit),
        ).fetchone()[0]
        other_group = conn.execute(
            "INSERT INTO account_groups (institution_id, code, name, kind)"
            " VALUES (%s, 'G_OTHER', 'Other Group', 'AI_SPECIALIST') RETURNING id",
            (other_inst,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO qta_quota_groups (institution_id, group_id, group_kind, origin, in_directory, enrolled_by)"
            " VALUES (%s, %s, 'AI_SPECIALIST', 'SPECIALIST', true, %s)",
            (other_inst, other_group, other_user),
        )
        other_provider = add_provider(conn, other_inst, "Foreign Vendor")
        other_model = add_model(conn, other_inst, other_provider, "foreign-model", risk_level="LOW")

    own_spec = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_OWN", "name": "Own"}, 201)

    # Listings contain zero foreign items.
    assert str(other_group) not in {g["id"] for g in qta_get(db.qta_admin, "/groups")["items"]}
    assert str(other_model) not in {m["id"] for m in qta_get(db.qta_admin, "/models")["items"]}

    # Direct access to foreign group, foreign user, or foreign model -> 404 NOT_FOUND everywhere.
    qta_get(db.qta_admin, f"/groups/{other_group}", status=404)
    qta_get(db.qta_admin, f"/groups/{other_group}/members", status=404)
    qta_send(db.qta_admin, "PATCH", f"/groups/{other_group}", {"name": "Steal"}, 404)
    qta_send(db.qta_admin, "POST", f"/groups/{other_group}/deactivate", None, 404)
    qta_send(db.qta_admin, "POST", f"/groups/{other_group}/activate", None, 404)
    qta_send(db.qta_admin, "PUT", f"/groups/{other_group}/members/{db.member_id}", None, 404)
    qta_send(db.qta_admin, "DELETE", f"/groups/{other_group}/members/{db.member_id}", None, 404)
    qta_send(db.qta_admin, "PUT", f"/groups/{own_spec['id']}/members/{other_user}", None, 404)
    qta_send(db.qta_admin, "DELETE", f"/groups/{own_spec['id']}/members/{other_user}", None, 404)
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{other_group}/quotas",
        {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 100}]},
        404,
    )
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{own_spec['id']}/quotas",
        {"quotas": [{"model_id": str(other_model), "enabled": True, "monthly_limit": 100}]},
        404,
    )


def test_audit_failure_rolls_back(qta):
    """Revoking INSERT on audit_events rolls back sync, specialist create, and quota upsert completely."""
    db = qta
    create_group(db.admin, "SYSTEM", code="G_ROLLBACK_SYNC")
    kept_spec = qta_send(db.qta_admin, "POST", "/groups", {"code": "AI_RB_BASE", "name": "Base"}, 201)

    with connect(db.owner, autocommit=True) as conn:
        conn.execute(
            sql.SQL("REVOKE INSERT ON audit_events FROM {}").format(
                sql.Identifier(db.roles.runtime)
            )
        )
    try:
        # 1. Sync fails -> no registry enrollment and no sync run persisted.
        sync_resp = send(db.qta_admin, "POST", qta_path("/groups/sync"))
        assert sync_resp.status_code == 500 and sync_resp.json()["code"] == "DATABASE_ERROR"

        # 2. Specialist create fails -> neither account_groups nor qta_quota_groups row persisted.
        create_resp = send(
            db.qta_admin, "POST", qta_path("/groups"), {"code": "AI_RB_FAIL", "name": "Fail"}
        )
        assert create_resp.status_code == 500 and create_resp.json()["code"] == "DATABASE_ERROR"

        # 3. Quota upsert fails -> no qta_group_model_quotas row persisted.
        quota_resp = send(
            db.qta_admin,
            "PUT",
            qta_path(f"/groups/{kept_spec['id']}/quotas"),
            {"quotas": [{"model_id": db.model_a, "enabled": True, "monthly_limit": 1234}]},
        )
        assert quota_resp.status_code == 500 and quota_resp.json()["code"] == "DATABASE_ERROR"
    finally:
        with connect(db.owner, autocommit=True) as conn:
            conn.execute(
                sql.SQL("GRANT INSERT ON audit_events TO {}").format(
                    sql.Identifier(db.roles.runtime)
                )
            )

    with connect(db.owner) as conn:
        assert conn.execute("SELECT count(*) FROM qta_group_sync_runs").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM qta_quota_groups").fetchone() == (1,)  # kept_spec only
        assert conn.execute("SELECT count(*) FROM account_groups WHERE code = 'AI_RB_FAIL'").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM qta_group_model_quotas").fetchone() == (0,)


def test_concurrent_syncs_serialize(qta):
    """Two concurrent POST /qta/groups/sync calls serialize cleanly with zero 500s or duplicate enrollments."""
    db = qta
    create_group(db.admin, "SYSTEM", code="G_CONC_1", name="Conc 1")
    create_group(db.admin, "SYSTEM", code="G_CONC_2", name="Conc 2")

    barrier = Barrier(2)
    headers = csrf_headers(db.qta_admin)
    cookies = dict(db.qta_admin.cookies)

    def run_sync(_):
        with client(db) as browser:
            browser.cookies.update(cookies)
            barrier.wait()
            response = browser.post("/api/v1/qta/groups/sync", headers=headers)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_sync, range(2)))

    assert all(status == 200 for status, _ in results)
    added_counts = sorted(body["groups_added"] for _, body in results)
    assert added_counts == [0, 2]
    with connect(db.owner) as conn:
        assert conn.execute("SELECT count(*) FROM qta_group_sync_runs").fetchone() == (2,)
        assert conn.execute("SELECT count(*) FROM qta_quota_groups").fetchone() == (2,)
