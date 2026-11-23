"""Exercise real directory routes and locks as the restricted PostgreSQL runtime."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from psycopg import sql

from aq_uai_api.auth import operator
from aq_uai_api.auth import service as authentication
from aq_uai_api.authorization import writes
from aq_uai_api.core.config import get_settings
from aq_uai_api.db.audit import AuditAction
from aq_uai_api.db.identity import (
    AccountGroup,
    AuditEvent,
    Institution,
    RolePermission,
    Unit,
    User,
    UserRoleAssignment,
)
from aq_uai_api.directory import service

from .test_wp2_database import assert_denied, connect, prepare
from .test_wp2_database import pytestmark as postgres_marks
from .test_wp3_auth import PERSONAL, RESET, TEMPORARY, client, csrf_headers, log_in
from .test_wp3_auth import auth_db as auth_db
from .test_wp3_auth import bootstrapped as bootstrapped

pytestmark = postgres_marks
API = "/api/v1"


def get(browser, path, **kwargs):
    return browser.get(API + path, **kwargs)


def send(browser, method, path, body=None, *, headers=None):
    return browser.request(
        method,
        API + path,
        headers=csrf_headers(browser) if headers is None else headers,
        json=body,
    )


def expect(response, status):
    # Avoid printing successful credential-bearing bodies if a contract assertion fails.
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def finish_password_change(browser, current=TEMPORARY):
    expect(
        send(
            browser,
            "POST",
            "/auth/change-password",
            {"current_password": current, "new_password": PERSONAL},
        ),
        204,
    )


@pytest.fixture
def directory(bootstrapped, monkeypatch):
    db = bootstrapped
    monkeypatch.setattr(service, "write_transaction", db.runtime_factory.begin)
    db.app.dependency_overrides[get_settings] = lambda: db.settings
    with db.owner_factory() as owner:
        profile = owner.get(User, db.user_id)
        db.main_unit = str(profile.primary_unit_id)
        db.tenant = str(profile.institution_id)
    with client(db) as browser:
        expect(log_in(browser), 204)
        finish_password_change(browser)
        expect(log_in(browser, password=PERSONAL), 204)
        db.admin = browser
        yield db


def create_unit(browser, code):
    return expect(send(browser, "POST", "/units", {"code": code, "name": f"Unit {code}"}), 201)


def create_user(browser, unit, username, *, active=False):
    data = {
        "primary_unit_id": unit,
        "username": username,
        "display_name": f"Person {username}",
        "code_type": "STAFF",
        "institutional_code": username,
    }
    if active:
        data["temporary_password"] = TEMPORARY
    return expect(send(browser, "POST", "/users", data), 201)


def create_group(browser, kind):
    return expect(
        send(browser, "POST", "/groups", {"code": kind.lower(), "name": kind, "kind": kind}), 201
    )


def add_grant(browser, subject_path, role, unit=None):
    data = {"role_code": role, "scope": "UNIT" if unit else "GLOBAL", "unit_id": unit}
    return expect(send(browser, "POST", subject_path + "/role-assignments", data), 201)


def open_user(db, user):
    browser = client(db)
    expect(log_in(browser, username=user), 204)
    finish_password_change(browser)
    expect(log_in(browser, username=user, password=PERSONAL), 204)
    return browser


def test_user_and_unit_lifecycle_with_persisted_credentials_and_grants(directory, caplog):
    db, admin = directory, directory.admin
    roles = expect(get(admin, "/roles"), 200)
    assert {role["code"] for role in roles["items"]} == {
        "FOUNDATION_ADMIN",
        "DIRECTORY_READER",
        "UNIT_DIRECTORY_MANAGER",
    }
    alpha = create_unit(admin, "ALPHA")
    beta = create_unit(admin, "BETA")
    pending = create_user(admin, alpha["id"], "pending")
    uid = pending["id"]
    path = f"/users/{uid}"
    assert pending["state"] == "PENDING"
    assert "temporary_password" not in pending and "password_hash" not in pending
    with client(db) as target:
        expect(log_in(target, username="pending"), 401)
        expect(send(admin, "POST", path + "/activate"), 422)
        expect(send(admin, "POST", path + "/activate", {"temporary_password": TEMPORARY}), 200)
        expect(log_in(target, username="pending"), 204)
        expect(get(target, "/directory/capabilities"), 403)
        finish_password_change(target)
        expect(log_in(target, username="pending", password=PERSONAL), 204)
        grant = add_grant(admin, path, "DIRECTORY_READER", alpha["id"])
        assert expect(get(target, "/units"), 200)["items"][0]["id"] == alpha["id"]

        assert (
            expect(send(admin, "PATCH", f"/units/{alpha['id']}", {"name": "Updated unit"}), 200)[
                "name"
            ]
            == "Updated unit"
        )
        expect(send(admin, "POST", f"/units/{alpha['id']}/deactivate"), 409)
        moved = expect(
            send(admin, "POST", path + "/transfer", {"primary_unit_id": beta["id"]}), 200
        )
        assert moved["id"] == uid and moved["primary_unit_id"] == beta["id"]
        assert expect(get(admin, path + "/role-assignments", params={"scope": "UNIT"}), 200)[
            "items"
        ] == [grant]
        expect(send(admin, "POST", f"/units/{alpha['id']}/deactivate"), 409)
        expect(send(admin, "DELETE", path + "/role-assignments/" + grant["id"]), 204)
        expect(send(admin, "POST", f"/units/{alpha['id']}/deactivate"), 200)
        expect(get(admin, f"/units/{alpha['id']}"), 200)
        expect(send(admin, "POST", f"/units/{alpha['id']}/activate"), 200)

        changed = expect(
            send(
                admin,
                "PATCH",
                path + "/identity",
                {"username": " Renamed ", "code_type": "STUDENT", "institutional_code": "ST-009"},
            ),
            200,
        )
        assert changed["username"] == "renamed" and changed["id"] == uid
        expect(get(target, "/auth/me"), 401)
        expect(log_in(target, username="pending", password=PERSONAL), 401)
        expect(log_in(target, username="renamed", password=PERSONAL), 204)
        cookie = target.cookies["aq_uai_session"]
        expect(send(admin, "POST", path + "/disable", {"temporary_password": TEMPORARY}), 422)
        expect(send(admin, "POST", path + "/disable"), 200)
        expect(get(target, "/auth/me"), 401)
        expect(send(admin, "POST", path + "/activate", {"temporary_password": TEMPORARY}), 409)
        expect(send(admin, "POST", path + "/activate"), 200)
        expect(get(target, "/auth/me", headers={"Cookie": f"aq_uai_session={cookie}"}), 401)
        expect(log_in(target, username="renamed", password=PERSONAL), 204)
        assert not expect(get(target, "/auth/me"), 200)["must_change_password"]
    with client(db) as fresh:
        expect(log_in(fresh, password=PERSONAL), 204)
        assert (
            expect(get(fresh, "/users", params={"q": "ST-009", "code_type": "STUDENT"}), 200)[
                "items"
            ][0]["id"]
            == uid
        )
    events = expect(get(admin, "/audit-events", params={"target_id": uid}), 200)
    assert {event["action"] for event in events["items"]}.issuperset(
        {"user.created", "user.state_changed", "user.transferred", "user.identity_updated"}
    )
    assert TEMPORARY not in str(events) + caplog.text and PERSONAL not in str(events) + caplog.text


def test_directory_input_conflicts_and_cross_institution_references(directory):
    db, admin = directory, directory.admin
    unit = create_unit(admin, "UNIQUE")
    user = create_user(admin, unit["id"], "unique")
    with db.owner_factory.begin() as owner:
        inst = Institution(code="OUT", name="Outside")
        owner.add(inst)
        owner.flush()
        foreign_unit = Unit(institution_id=inst.id, code="OUT", name="Outside")
        owner.add(foreign_unit)
        owner.flush()
        foreign_user = User(
            institution_id=inst.id,
            primary_unit_id=foreign_unit.id,
            username="outside",
            display_name="Outside",
            code_type="STAFF",
            institutional_code="outside",
        )
        owner.add(foreign_user)
        owner.flush()
        outside_unit, outside_user = str(foreign_unit.id), str(foreign_user.id)
    expect(send(admin, "POST", "/units", {"code": "UNIQUE", "name": "Duplicate"}), 409)
    expect(send(admin, "PATCH", f"/units/{unit['id']}", {"code": "MAIN"}), 409)
    data = {
        "primary_unit_id": unit["id"],
        "username": " UNIQUE ",
        "display_name": "Duplicate",
        "code_type": "STAFF",
        "institutional_code": "different",
    }
    expect(send(admin, "POST", "/users", data), 409)
    expect(
        send(
            admin,
            "POST",
            "/users",
            data | {"username": "different", "institutional_code": "unique"},
        ),
        409,
    )
    expect(send(admin, "POST", "/users", data | {"institution_id": db.tenant}), 422)
    expect(send(admin, "POST", "/users", data | {"primary_unit_id": outside_unit}), 404)
    expect(
        send(admin, "POST", f"/users/{user['id']}/transfer", {"primary_unit_id": outside_unit}), 404
    )
    expect(get(admin, f"/users/{outside_user}"), 404)
    expect(get(admin, f"/units/{outside_unit}"), 404)
    expect(get(admin, f"/users/{outside_user}/role-assignments"), 404)
    expect(send(admin, "PATCH", f"/users/{user['id']}/identity", {"username": None}), 422)
    expect(send(admin, "PATCH", f"/users/{user['id']}/identity", {"state": "ACTIVE"}), 422)
    expect(send(admin, "PATCH", f"/users/{user['id']}/identity", {"username": "unsafe/user"}), 422)
    expect(send(admin, "POST", f"/units/{unit['id']}/deactivate"), 200)
    expect(send(admin, "POST", "/users", data | {"username": "inactive"}), 409)
    expect(
        send(admin, "POST", f"/users/{user['id']}/activate", {"temporary_password": TEMPORARY}), 409
    )
    ordinary = create_group(admin, "SYSTEM")
    expect(
        send(admin, "POST", "/groups", {"code": ordinary["code"], "name": "Dup", "kind": "SYSTEM"}),
        409,
    )
    expect(send(admin, "PUT", f"/groups/{ordinary['id']}/members/{outside_user}"), 404)
    expect(get(admin, "/audit-events", params={"from_time": "2026-01-01T00:00:00"}), 422)
    expect(get(admin, "/users", params={"limit": 101}), 422)


def test_sql_visibility_scope_mixing_and_forged_profile_fields(directory):
    db, admin = directory, directory.admin
    unit_a, unit_b = (create_unit(admin, code) for code in ("ALPHA", "BETA"))
    editor = create_user(admin, unit_b["id"], "editor", active=True)
    target = create_user(admin, unit_a["id"], "visible")
    hidden = create_user(admin, unit_b["id"], "hidden")
    reader = create_user(admin, unit_b["id"], "reader", active=True)
    add_grant(admin, f"/users/{reader['id']}", "DIRECTORY_READER")
    add_grant(admin, f"/users/{editor['id']}", "UNIT_DIRECTORY_MANAGER", unit_a["id"])
    with open_user(db, "editor") as browser, open_user(db, "reader") as read_only:
        page = expect(get(browser, "/users", params={"q": "Person", "limit": 1}), 200)
        assert page["total"] == 1 and page["items"][0]["id"] == target["id"]
        assert expect(get(browser, "/users", params={"q": "hidden"}), 200)["total"] == 0
        assert expect(get(browser, "/users", params={"offset": 1}), 200)["total"] == 1
        assert expect(get(browser, "/units"), 200)["items"] == [unit_a]
        nonexistent = expect(get(browser, f"/users/{uuid4()}"), 404)
        invisible = expect(get(browser, f"/users/{hidden['id']}"), 404)
        assert (
            invisible["code"] == nonexistent["code"]
            and invisible["message"] == nonexistent["message"]
        )
        expect(
            send(browser, "PATCH", f"/users/{target['id']}/profile", {"display_name": "Updated"}),
            200,
        )
        expect(
            send(browser, "PATCH", f"/users/{hidden['id']}/profile", {"display_name": "Denied"}),
            404,
        )
        expect(
            send(
                browser,
                "PATCH",
                f"/users/{target['id']}/profile",
                {"display_name": "Name", "state": "DISABLED"},
            ),
            422,
        )
        expect(
            send(browser, "PATCH", f"/users/{target['id']}/identity", {"username": "denied"}), 403
        )
        expect(
            send(
                browser,
                "POST",
                f"/users/{target['id']}/transfer",
                {"primary_unit_id": unit_b["id"]},
            ),
            403,
        )
        expect(
            send(read_only, "PATCH", f"/users/{target['id']}/profile", {"display_name": "Denied"}),
            403,
        )
        expect(get(browser, "/groups"), 403)
        expect(get(read_only, "/audit-events"), 403)
        expect(get(read_only, "/roles"), 403)
        add_grant(admin, f"/users/{editor['id']}", "DIRECTORY_READER")
        expect(get(browser, f"/users/{hidden['id']}"), 200)
        expect(
            send(
                browser, "PATCH", f"/users/{hidden['id']}/profile", {"display_name": "Still denied"}
            ),
            403,
        )
        caps = expect(get(browser, "/directory/capabilities"), 200)["permissions"]
        assert caps["directory.read"]["institution_wide"]
        assert caps["directory.profile.update"] == {
            "institution_wide": False,
            "unit_ids": [unit_a["id"]],
        }
        for headers in (
            {},
            {"Origin": "http://localhost:8000"},
            {"Origin": csrf_headers(browser)["Origin"], "X-CSRF-Token": "bad"},
        ):
            expect(
                send(
                    browser,
                    "PATCH",
                    f"/users/{target['id']}/profile",
                    {"display_name": "Denied"},
                    headers=headers,
                ),
                403,
            )


def test_groups_memberships_and_assignment_reactivation_are_audited(directory):
    db, admin = directory, directory.admin
    system = create_group(admin, "SYSTEM")
    specialist = create_group(admin, "AI_SPECIALIST")
    allowed = create_group(admin, "AUTHORIZATION")
    path = f"/groups/{allowed['id']}"
    assert expect(get(admin, path), 200) == allowed
    member = create_user(admin, db.main_unit, "member", active=True)
    uid = member["id"]
    membership = path + f"/members/{uid}"
    with open_user(db, "member") as browser:
        flags = {"role_code": "DIRECTORY_READER", "scope": "GLOBAL"}
        for group in (system, specialist):
            expect(send(admin, "POST", f"/groups/{group['id']}/role-assignments", flags), 422)
            expect(send(admin, "PUT", f"/groups/{group['id']}/members/{uid}"), 200)
            expect(get(browser, "/users"), 403)
        expect(send(admin, "PATCH", path, {"kind": "SYSTEM", "name": "Bad"}), 422)
        assert (
            expect(send(admin, "PATCH", path, {"name": "Approval group"}), 200)["name"]
            == "Approval group"
        )
        assert (
            expect(get(admin, "/groups", params={"kind": "AUTHORIZATION", "q": "Approval"}), 200)[
                "total"
            ]
            == 1
        )
        grant = add_grant(admin, path, "DIRECTORY_READER")
        expect(send(admin, "POST", path + "/role-assignments", flags), 409)
        expect(
            send(
                admin,
                "POST",
                path + "/role-assignments",
                {"role_code": "FOUNDATION_ADMIN", "scope": "GLOBAL"},
            ),
            422,
        )
        first = expect(send(admin, "PUT", membership), 200)
        assert expect(send(admin, "PUT", membership), 200) == first
        assert expect(get(admin, path + "/members", params={"q": "member"}), 200)["total"] == 1
        expect(get(browser, "/users"), 200)
        expect(send(admin, "DELETE", membership), 204)
        expect(send(admin, "DELETE", membership), 204)
        expect(get(browser, "/users"), 403)
        assert expect(get(admin, path + "/members", params={"active": False}), 200)["total"] == 1
        second = expect(send(admin, "PUT", membership), 200)
        assert (
            second["created_at"] == first["created_at"]
            and second["updated_at"] != first["updated_at"]
        )
        expect(send(admin, "POST", path + "/deactivate"), 200)
        expect(send(admin, "PUT", membership), 409)
        expect(get(browser, "/users"), 403)
        expect(send(admin, "POST", path + "/activate"), 200)
        expect(get(browser, "/users"), 200)
        assert expect(get(admin, path + "/role-assignments"), 200)["items"] == [grant]
        expect(send(admin, "DELETE", f"/groups/{system['id']}/role-assignments/{grant['id']}"), 404)
        expect(send(admin, "DELETE", path + "/role-assignments/" + grant["id"]), 204)
        expect(get(browser, "/users"), 403)
    events = expect(
        get(
            admin,
            "/audit-events",
            params={"action": "membership.state_changed", "target_id": allowed["id"]},
        ),
        200,
    )
    assert events["total"] == 3
    assert [row["changes"] for row in reversed(events["items"])] == [
        {"user_id": uid, "before": None, "after": True},
        {"user_id": uid, "before": True, "after": False},
        {"user_id": uid, "before": False, "after": True},
    ]
    assert all(
        row["target_type"] == "group_membership" and row["target_id"] == allowed["id"]
        for row in events["items"]
    )
    removal = expect(
        get(
            admin,
            "/audit-events",
            params={"target_id": grant["id"], "action": "role_assignment.removed"},
        ),
        200,
    )
    assert removal["items"][0]["changes"] == {
        "subject_type": "GROUP",
        "subject_id": allowed["id"],
        "role_code": "DIRECTORY_READER",
        "scope": "GLOBAL",
        "unit_id": None,
    }


def test_group_management_checks_actual_kind_instead_of_promoting_ordinary_membership(directory):
    db, admin = directory, directory.admin
    ordinary = create_group(admin, "SYSTEM")
    delegated = create_group(admin, "AUTHORIZATION")
    target = create_user(admin, db.main_unit, "member")
    with db.owner_factory.begin() as owner:
        owner.delete(owner.get(RolePermission, ("FOUNDATION_ADMIN", "authorization.manage")))
    expect(send(admin, "PUT", f"/groups/{ordinary['id']}/members/{target['id']}"), 200)
    expect(send(admin, "PUT", f"/groups/{delegated['id']}/members/{target['id']}"), 403)
    expect(send(admin, "PATCH", f"/groups/{delegated['id']}", {"name": "Forbidden"}), 403)
    expect(get(admin, f"/groups/{delegated['id']}/role-assignments"), 403)


def test_audit_visibility_and_legacy_payload_projection(directory):
    db, admin = directory, directory.admin
    local, hidden, unattributed, malformed = uuid4(), uuid4(), uuid4(), uuid4()
    with db.owner_factory.begin() as owner:
        other = Institution(code="OUT", name="Outside")
        owner.add(other)
        owner.flush()
        for event_id, institution_id, changes in (
            (local, UUID(db.tenant), {"before": False, "after": True}),
            (hidden, other.id, {"before": False, "after": True}),
            (unattributed, None, {}),
            (malformed, UUID(db.tenant), {"password": TEMPORARY}),
        ):
            owner.add(
                AuditEvent(
                    id=event_id,
                    institution_id=institution_id,
                    actor_id=None,
                    action="membership.state_changed",
                    target_type="group_membership",
                    target_id=uuid4(),
                    outcome="SUCCESS",
                    request_id=str(uuid4()),
                    changes=changes,
                )
            )
    result = expect(get(admin, f"/audit-events/{local}"), 200)
    assert result["actor_id"] is None and result["changes"] == {"before": False, "after": True}
    assert expect(get(admin, f"/audit-events/{malformed}"), 200)["changes"] == {}
    for event in (hidden, unattributed, uuid4()):
        expect(get(admin, f"/audit-events/{event}"), 404)
    response = get(
        admin, "/audit-events", params={"action": "membership.state_changed", "limit": 1}
    )
    assert expect(response, 200)["total"] == 2 and response.headers["cache-control"] == "no-store"


def test_last_admin_conflicts_with_pending_or_disabled_backup(directory):
    db, admin = directory, directory.admin
    pending = create_user(admin, db.main_unit, "backup")
    add_grant(admin, f"/users/{pending['id']}", "FOUNDATION_ADMIN")
    admin_path = f"/users/{db.user_id}"
    grants = expect(get(admin, admin_path + "/role-assignments"), 200)["items"]
    expect(send(admin, "POST", admin_path + "/disable"), 409)
    expect(send(admin, "DELETE", admin_path + "/role-assignments/" + grants[0]["id"]), 409)
    expect(send(admin, "POST", f"/users/{pending['id']}/disable"), 200)
    expect(send(admin, "POST", admin_path + "/disable"), 409)
    assert expect(get(admin, "/auth/me"), 200)["id"] == str(db.user_id)
    assert expect(get(admin, admin_path + "/role-assignments"), 200)["items"] == grants
    with connect(db.owner) as connection:
        connection.execute("UPDATE users SET state = 'ACTIVE' WHERE id = %s", (pending["id"],))
    expect(send(admin, "POST", admin_path + "/disable"), 409)


def test_temporary_credential_admin_counts_as_usable(directory):
    db, admin = directory, directory.admin
    backup = create_user(admin, db.main_unit, "backup", active=True)
    add_grant(admin, f"/users/{backup['id']}", "FOUNDATION_ADMIN")
    expect(send(admin, "POST", f"/users/{db.user_id}/disable"), 200)
    expect(get(admin, "/auth/me"), 401)
    with client(db) as temporary:
        expect(log_in(temporary, "backup"), 204)
        expect(get(temporary, "/users"), 403)
        finish_password_change(temporary)
        expect(log_in(temporary, "backup", PERSONAL), 204)
        expect(get(temporary, "/users"), 200)


@pytest.mark.parametrize(
    "operations", [("disable", "disable"), ("revoke", "revoke"), ("disable", "revoke")]
)
def test_concurrent_self_departures_leave_one_usable_admin(directory, operations):
    db, admin = directory, directory.admin
    second = create_user(admin, db.main_unit, "backup", active=True)
    add_grant(admin, f"/users/{second['id']}", "FOUNDATION_ADMIN")
    barrier = Barrier(2)

    def depart(browser, user_id, operation):
        path = f"/users/{user_id}"
        headers = csrf_headers(browser)
        if operation == "revoke":
            grant = expect(get(browser, path + "/role-assignments"), 200)["items"][0]
            path += "/role-assignments/" + grant["id"]
        else:
            path += "/disable"
        barrier.wait(timeout=10)
        response = send(
            browser, "DELETE" if operation == "revoke" else "POST", path, headers=headers
        )
        return response.status_code

    with open_user(db, "backup") as backup, ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(depart, browser, user_id, op)
            for browser, user_id, op in zip(
                (admin, backup), (db.user_id, second["id"]), operations, strict=True
            )
        ]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(results) in ([200, 409], [204, 409])
    with connect(db.runtime) as connection:
        assert connection.execute(
            "SELECT count(*) FROM users JOIN user_credentials c ON c.user_id = users.id "
            "JOIN user_role_assignments a ON a.user_id = users.id AND a.institution_id = users.institution_id "
            "WHERE users.state = 'ACTIVE' AND a.role_code = 'FOUNDATION_ADMIN' AND a.scope = 'GLOBAL'"
        ).fetchone() == (1,)


def test_audit_failure_rolls_back_directory_categories_and_preserves_sessions(directory):
    db, admin = directory, directory.admin
    group = create_group(admin, "SYSTEM")
    user = create_user(admin, db.main_unit, "target", active=True)
    uid = user["id"]
    allowed_grant = {"role_code": "DIRECTORY_READER", "scope": "GLOBAL"}
    with open_user(db, "target") as target:
        with connect(db.owner) as connection:
            connection.execute(
                sql.SQL("REVOKE INSERT ON audit_events FROM {}").format(
                    sql.Identifier(db.roles.runtime)
                )
            )
        for method, path, body in (
            ("PATCH", f"/units/{db.main_unit}", {"name": "Rolled back"}),
            (
                "POST",
                "/users",
                {
                    "primary_unit_id": db.main_unit,
                    "username": "rollback",
                    "display_name": "Rollback",
                    "code_type": "STAFF",
                    "institutional_code": "rollback",
                    "temporary_password": TEMPORARY,
                },
            ),
            ("POST", f"/users/{uid}/disable", None),
            ("PUT", f"/groups/{group['id']}/members/{uid}", None),
            ("POST", f"/users/{uid}/role-assignments", allowed_grant),
        ):
            response = send(admin, method, path, body)
            expect(response, 500)
            assert TEMPORARY not in response.text
        assert expect(get(target, "/auth/me"), 200)["id"] == uid
    assert expect(get(admin, "/users", params={"q": "rollback"}), 200)["total"] == 0
    assert expect(get(admin, f"/units/{db.main_unit}"), 200)["name"] != "Rolled back"
    assert expect(get(admin, f"/users/{uid}"), 200)["state"] == "ACTIVE"
    assert expect(get(admin, f"/users/{uid}/role-assignments"), 200)["total"] == 0
    assert expect(get(admin, f"/groups/{group['id']}/members"), 200)["total"] == 0


def test_profile_rechecks_grant_after_waiting_for_committed_revocation(directory, monkeypatch):
    db, admin = directory, directory.admin
    editor = create_user(admin, db.main_unit, "editor", active=True)
    target = create_user(admin, db.main_unit, "target")
    grant = add_grant(admin, f"/users/{editor['id']}", "UNIT_DIRECTORY_MANAGER", db.main_unit)
    waiting = Event()
    acquire = writes.lock_institution

    def track(session, institution_id, *, exclusive):
        if not exclusive:
            waiting.set()
        return acquire(session, institution_id, exclusive=exclusive)

    monkeypatch.setattr(writes, "lock_institution", track)
    with open_user(db, "editor") as browser, ThreadPoolExecutor(max_workers=1) as pool:
        headers = csrf_headers(browser)
        with db.owner_factory.begin() as owner:
            acquire(owner, UUID(db.tenant), exclusive=True)
            owner.delete(owner.get(UserRoleAssignment, UUID(grant["id"])))
            future = pool.submit(
                send,
                browser,
                "PATCH",
                f"/users/{target['id']}/profile",
                {"display_name": "Denied"},
                headers=headers,
            )
            assert waiting.wait(10) and not future.done()
        expect(future.result(timeout=10), 403)
    assert (
        expect(get(admin, f"/users/{target['id']}"), 200)["display_name"] == target["display_name"]
    )


@pytest.mark.parametrize("operation", ["login", "password-reset"])
def test_disable_serializes_with_wp3_credential_operations(directory, monkeypatch, operation):
    db, admin = directory, directory.admin
    user = create_user(admin, db.main_unit, "race", active=True)
    held, waiting, release = Event(), Event(), Event()
    original_record = service.record
    acquire = authentication.lock_account

    def staged_record(session, context, authority, action, target, changes):
        original_record(session, context, authority, action, target, changes)
        if action is AuditAction.USER_STATE_CHANGED:
            held.set()
            assert release.wait(10)

    def track(session, user_id):
        if str(user_id) == user["id"]:
            waiting.set()
        return acquire(session, user_id)

    monkeypatch.setattr(service, "record", staged_record)
    monkeypatch.setattr(authentication, "lock_account", track)
    monkeypatch.setattr(operator, "lock_account", track)
    reset_request = uuid4()
    headers = csrf_headers(admin)
    with client(db) as target, ThreadPoolExecutor(max_workers=2) as pool:
        disable = pool.submit(send, admin, "POST", f"/users/{user['id']}/disable", headers=headers)
        try:
            assert held.wait(10)
            contender = (
                pool.submit(log_in, target, "race")
                if operation == "login"
                else pool.submit(operator.reset_password, "race", RESET, reset_request)
            )
            assert waiting.wait(10) and not contender.done()
        finally:
            release.set()
        expect(disable.result(timeout=10), 200)
        if operation == "login":
            expect(contender.result(timeout=10), 401)
        else:
            with pytest.raises(operator.OperatorError, match="active, provisioned account"):
                contender.result(timeout=10)
            events = expect(get(admin, "/audit-events", params={"target_id": user["id"]}), 200)
            assert all(item["request_id"] != str(reset_request) for item in events["items"])


def test_membership_does_not_mutate_group_created_after_account_lock_hint(directory, monkeypatch):
    db, admin = directory, directory.admin
    user = create_user(admin, db.main_unit, "new-member")
    group_id = uuid4()
    resolve = service.resolve_write_authority

    def create_before_guard(*args, **kwargs):
        assert kwargs["related_account_ids"] == ()
        with db.owner_factory.begin() as owner:
            owner.add(
                AccountGroup(
                    id=group_id,
                    institution_id=UUID(db.tenant),
                    code="late",
                    name="Late",
                    kind="AUTHORIZATION",
                )
            )
        return resolve(*args, **kwargs)

    member_path = f"/groups/{group_id}/members/{user['id']}"
    with monkeypatch.context() as patched:
        patched.setattr(service, "resolve_write_authority", create_before_guard)
        expect(send(admin, "PUT", member_path), 404)
    assert expect(get(admin, f"/groups/{group_id}/members"), 200)["total"] == 0
    expect(send(admin, "PUT", member_path), 200)


def test_typed_audit_allows_repair_of_historical_blank_metadata(directory):
    db, admin = directory, directory.admin
    group = create_group(admin, "SYSTEM")
    unit = create_unit(admin, "OLD")
    user = create_user(admin, unit["id"], "old-user")
    with db.owner_factory.begin() as owner:
        owner.get(AccountGroup, UUID(group["id"])).name = ""
        stored_unit = owner.get(Unit, UUID(unit["id"]))
        stored_unit.code = stored_unit.name = ""
        owner.get(User, UUID(user["id"])).display_name = ""
    for path, field, changes in (
        (f"/groups/{group['id']}", "name", {"before": "", "after": "Repaired"}),
        (
            f"/units/{unit['id']}",
            "name",
            {
                "before": {"code": "", "name": ""},
                "after": {"code": "", "name": "Repaired"},
            },
        ),
        (f"/users/{user['id']}/profile", "display_name", {"before": "", "after": "Repaired"}),
    ):
        expect(send(admin, "PATCH", path, {field: "Repaired"}), 200)
        target = path.split("/")[2]
        events = expect(get(admin, "/audit-events", params={"target_id": target}), 200)
        assert events["items"][0]["changes"] == changes


def test_runtime_cannot_delete_history_or_change_primary_identity_columns(directory):
    db = directory
    with connect(db.runtime, autocommit=True) as connection:
        for statement in (
            "DELETE FROM users",
            "DELETE FROM units",
            "DELETE FROM account_groups",
            "DELETE FROM group_memberships",
            "UPDATE users SET id = id",
            "UPDATE users SET institution_id = institution_id",
            "UPDATE users SET created_at = created_at",
            "UPDATE account_groups SET kind = kind",
            "UPDATE account_groups SET code = code",
            "INSERT INTO units (active) VALUES (false)",
            "INSERT INTO account_groups (active) VALUES (false)",
            "UPDATE group_memberships SET user_id = user_id",
            "UPDATE group_role_assignments SET role_code = role_code",
            "DELETE FROM role_permissions",
            "TRUNCATE audit_events",
            "UPDATE audit_events SET action = action",
        ):
            assert_denied(connection, statement)
    prepare(get_settings().database_url.set(database=db.owner.database), db.roles)
    unit = create_unit(db.admin, "REPROVISIONED")
    user = create_user(db.admin, unit["id"], "reprovisioned", active=True)
    grant = add_grant(db.admin, f"/users/{user['id']}", "DIRECTORY_READER")
    expect(send(db.admin, "DELETE", f"/users/{user['id']}/role-assignments/{grant['id']}"), 204)
    with client(db) as browser:
        expect(log_in(browser, "reprovisioned"), 204)
        finish_password_change(browser)
        expect(log_in(browser, "reprovisioned", PERSONAL), 204)
        with connect(db.owner) as connection:
            connection.execute(
                "UPDATE auth_sessions SET issued_at = now() - interval '9 hours', "
                "expires_at = now() - interval '1 hour' WHERE user_id = %s AND revoked_at IS NULL",
                (user["id"],),
            )
        expect(get(browser, "/directory/capabilities"), 401)
