"""M1 against PostgreSQL: MDL authority is direct, GLOBAL and never inherited."""

import sqlalchemy as sa

from .test_wp5_directory import (
    PERSONAL,
    TEMPORARY,
    add_grant,
    client,
    create_group,
    create_unit,
    create_user,
    expect,
    finish_password_change,
    get,
    log_in,
    send,
)
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import directory as directory
from .test_wp5_directory import pytestmark as postgres_marks

pytestmark = postgres_marks
DIRECTORY_KEYS = {
    "directory.read",
    "directory.profile.update",
    "directory.manage",
    "authorization.manage",
    "audit.read",
}


def capabilities(browser):
    return expect(get(browser, "/directory/capabilities"), 200)["permissions"]


def has_scope(entry):
    return entry["institution_wide"] or bool(entry["unit_ids"])


def sign_in(db, username):
    browser = client(db)
    browser.__enter__()
    expect(log_in(browser, username, TEMPORARY), 204)
    finish_password_change(browser)
    expect(log_in(browser, username, PERSONAL), 204)
    return browser


def test_foundation_admin_and_directory_roles_gain_no_mdl_authority(directory):
    caps = capabilities(directory.admin)
    assert set(caps) == DIRECTORY_KEYS | {"mdl.read", "mdl.manage", "qta.read", "qta.manage"}
    assert all(has_scope(caps[key]) for key in DIRECTORY_KEYS)
    assert not has_scope(caps["mdl.read"]) and not has_scope(caps["mdl.manage"])
    assert not has_scope(caps["qta.read"]) and not has_scope(caps["qta.manage"])
    roles = {
        item["code"]: item["permissions"]
        for item in expect(get(directory.admin, "/roles"), 200)["items"]
    }
    assert roles["AI_MODEL_ADMIN"] == ["mdl.manage", "mdl.read"]
    assert (
        "mdl.read" not in roles["FOUNDATION_ADMIN"]
        and "mdl.manage" not in roles["FOUNDATION_ADMIN"]
    )


def test_direct_global_grant_confers_only_the_mdl_permissions(directory):
    unit = create_unit(directory.admin, "MDLUNIT")
    user = create_user(directory.admin, unit["id"], "modeladmin", active=True)
    grant = add_grant(directory.admin, f"/users/{user['id']}", "AI_MODEL_ADMIN")
    assert grant["scope"] == "GLOBAL" and grant["role_code"] == "AI_MODEL_ADMIN"
    browser = sign_in(directory, "modeladmin")
    try:
        caps = capabilities(browser)
        assert caps["mdl.read"]["institution_wide"] and caps["mdl.manage"]["institution_wide"]
        assert not any(has_scope(caps[key]) for key in DIRECTORY_KEYS)
        expect(get(browser, "/users"), 403)
    finally:
        browser.__exit__(None, None, None)


def test_mdl_role_cannot_be_unit_scoped_or_group_granted(directory):
    unit = create_unit(directory.admin, "MDLUNIT2")
    user = create_user(directory.admin, unit["id"], "unitscoped", active=True)
    body = {"role_code": "AI_MODEL_ADMIN", "scope": "UNIT", "unit_id": unit["id"]}
    expect(send(directory.admin, "POST", f"/users/{user['id']}/role-assignments", body), 422)
    group = create_group(directory.admin, "AUTHORIZATION")
    for scoped in ({"scope": "GLOBAL"}, {"scope": "UNIT", "unit_id": unit["id"]}):
        expect(
            send(
                directory.admin,
                "POST",
                f"/groups/{group['id']}/role-assignments",
                {"role_code": "AI_MODEL_ADMIN", **scoped},
            ),
            422,
        )
    assert (
        expect(get(directory.admin, f"/groups/{group['id']}/role-assignments"), 200)["total"] == 0
    )
    assert expect(get(directory.admin, f"/users/{user['id']}/role-assignments"), 200)["total"] == 0


def test_group_member_inherits_no_mdl_authority_even_with_a_drifted_row(directory):
    """If the DB check were bypassed, the policy still ignores a group-derived MDL grant."""
    unit = create_unit(directory.admin, "MDLUNIT3")
    user = create_user(directory.admin, unit["id"], "grouped", active=True)
    group = create_group(directory.admin, "AUTHORIZATION")
    send(directory.admin, "PUT", f"/groups/{group['id']}/members/{user['id']}")
    with directory.owner_factory.begin() as owner:
        owner.execute(
            sa.text(
                "ALTER TABLE group_role_assignments DROP CONSTRAINT ck_group_role_assignments_no_mdl_admin"
            )
        )
        try:
            owner.execute(
                sa.text(
                    "INSERT INTO group_role_assignments (institution_id, group_id, role_code, scope)"
                    " VALUES (:i, :g, 'AI_MODEL_ADMIN', 'GLOBAL')"
                ),
                {"i": directory.tenant, "g": group["id"]},
            )
            drifted = True
        except Exception:
            drifted = False
    assert drifted
    try:
        browser = sign_in(directory, "grouped")
        try:
            caps = capabilities(browser)
            assert not has_scope(caps["mdl.read"]) and not has_scope(caps["mdl.manage"])
        finally:
            browser.__exit__(None, None, None)
    finally:
        with directory.owner_factory.begin() as owner:
            owner.execute(
                sa.text("DELETE FROM group_role_assignments WHERE role_code = 'AI_MODEL_ADMIN'")
            )
            owner.execute(
                sa.text(
                    "ALTER TABLE group_role_assignments ADD CONSTRAINT ck_group_role_assignments_no_mdl_admin"
                    " CHECK (role_code <> 'AI_MODEL_ADMIN')"
                )
            )
