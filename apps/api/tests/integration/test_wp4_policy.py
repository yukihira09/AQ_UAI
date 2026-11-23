"""Exercise WP4 through real PostgreSQL and the application runtime role."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
import pytest
import sqlalchemy as sa
from fastapi import Depends
from psycopg import sql
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.security import hash_password
from aq_uai_api.auth.service import authenticate_session, lock_account, revoke_user_sessions
from aq_uai_api.auth.write import WriteProof
from aq_uai_api.authorization import writes
from aq_uai_api.authorization.dependencies import read_authority, require_authenticated_write
from aq_uai_api.authorization.policy import (
    ActorAuthority,
    GrantScope,
    GrantSubject,
    PermissionCode,
    require_group_management,
    resolve_effective_grants,
    validate_profile_fields,
    validate_role_assignment,
)
from aq_uai_api.core.config import get_settings
from aq_uai_api.db.identity import (
    AccountGroup,
    AuthSession,
    GroupMembership,
    GroupRoleAssignment,
    Institution,
    RolePermission,
    Unit,
    User,
    UserCredential,
    UserRoleAssignment,
)
from aq_uai_api.db.identity import Permission as CatalogPermission
from aq_uai_api.db.session import get_session

from .test_wp2_database import assert_denied, connect
from .test_wp2_database import pytestmark as postgres_marks
from .test_wp3_auth import ORIGIN, ORIGIN_HEADER, PERSONAL, client, csrf_headers, log_in
from .test_wp3_auth import auth_db as auth_db

pytestmark = postgres_marks

READ = PermissionCode.DIRECTORY_READ
EDIT = PermissionCode.PROFILE_UPDATE
CENTRAL = PermissionCode.DIRECTORY_MANAGE


@pytest.fixture
def estate(auth_db):
    db = auth_db
    db.tenant, db.other = uuid4(), uuid4()
    db.units = {name: uuid4() for name in ("a", "b", "c", "inactive", "foreign")}
    db.people = {
        name: uuid4()
        for name in (
            "administrator",
            "editor",
            "reader",
            "nogrants",
            "member",
            "pending",
            "disabled",
            "visible-a",
            "hidden-b",
            "archived",
            "foreign-user",
            "temporary",
        )
    }
    db.groups = {
        name: uuid4()
        for name in (
            "eligible",
            "inactive",
            "system",
            "specialist",
            "foreign",
        )
    }

    hashed = hash_password(PERSONAL)
    with db.owner_factory.begin() as owner:
        owner.add_all(
            [
                Institution(id=db.tenant, code="LOCAL", name="Local"),
                Institution(id=db.other, code="FOREIGN", name="Foreign"),
            ]
        )
        owner.flush()
        owner.add_all(
            [
                Unit(
                    id=unit_id,
                    institution_id=db.other if name == "foreign" else db.tenant,
                    code=name,
                    name=name,
                    active=name != "inactive",
                )
                for name, unit_id in db.units.items()
            ]
        )
        owner.flush()
        homes = {
            "administrator": "c",
            "editor": "c",
            "reader": "c",
            "nogrants": "a",
            "member": "c",
            "pending": "a",
            "disabled": "a",
            "visible-a": "a",
            "hidden-b": "b",
            "archived": "inactive",
            "foreign-user": "foreign",
            "temporary": "a",
        }
        owner.add_all(
            [
                User(
                    id=user_id,
                    institution_id=db.other if name == "foreign-user" else db.tenant,
                    primary_unit_id=db.units[homes[name]],
                    username=name,
                    display_name=f"Search {name}",
                    code_type="STAFF",
                    institutional_code=name,
                    state="PENDING"
                    if name == "pending"
                    else "DISABLED"
                    if name == "disabled"
                    else "ACTIVE",
                )
                for name, user_id in db.people.items()
            ]
        )
        owner.flush()
        owner.add_all(
            [
                UserCredential(
                    user_id=db.people[name],
                    password_hash=hashed,
                    must_change_password=name == "temporary",
                )
                for name in ("administrator", "editor", "reader", "nogrants", "member", "temporary")
            ]
        )
        group_kinds = {"system": "SYSTEM", "specialist": "AI_SPECIALIST"}
        owner.add_all(
            [
                AccountGroup(
                    id=group_id,
                    institution_id=db.other if name == "foreign" else db.tenant,
                    code=name,
                    name=name,
                    kind=group_kinds.get(name, "AUTHORIZATION"),
                    active=name != "inactive",
                )
                for name, group_id in db.groups.items()
            ]
        )
        owner.add_all(
            [
                direct_grant(db, "administrator", "FOUNDATION_ADMIN"),
                direct_grant(db, "editor", "UNIT_DIRECTORY_MANAGER", "a"),
                direct_grant(db, "reader", "DIRECTORY_READER"),
                direct_grant(db, "temporary", "FOUNDATION_ADMIN"),
            ]
        )

    db.app.dependency_overrides[get_settings] = lambda: db.settings
    db.before_write = None
    install_policy_routes(db)
    return db


def direct_grant(db, name, role, unit=None):
    return UserRoleAssignment(
        user_id=db.people[name],
        institution_id=db.tenant,
        role_code=role,
        scope="UNIT" if unit else "GLOBAL",
        unit_id=db.units[unit] if unit else None,
    )


def inherited_grant(db, group, role="UNIT_DIRECTORY_MANAGER", unit="b"):
    return GroupRoleAssignment(
        group_id=db.groups[group],
        institution_id=db.tenant,
        role_code=role,
        scope="UNIT" if unit else "GLOBAL",
        unit_id=db.units[unit] if unit else None,
    )


def add_inheritance(db, group, *, membership_active=True, role="UNIT_DIRECTORY_MANAGER", unit="b"):
    with db.owner_factory.begin() as owner:
        owner.add(
            GroupMembership(
                group_id=db.groups[group],
                user_id=db.people["member"],
                institution_id=db.tenant,
                active=membership_active,
            )
        )
        owner.add(inherited_grant(db, group, role, unit))


def visible_user(db, authority, user_id):
    visibility = authority.scope_for(READ).predicate(User.institution_id, User.primary_unit_id)
    target = db.scalar(sa.select(User).where(User.id == user_id, visibility))
    if target is None:
        raise DomainError(ErrorCode.NOT_FOUND)
    return target


def install_policy_routes(fixture):
    """Proof routes exist only in the test application's router."""
    app = fixture.app

    @app.get("/test-wp4/users")
    def list_users(
        authority: Annotated[ActorAuthority, Depends(read_authority)],
        db: Annotated[Session, Depends(get_session)],
        search: str = "Search",
        limit: int = 30,
        offset: int = 0,
    ):
        visibility = authority.require_permission(READ).predicate(
            User.institution_id, User.primary_unit_id
        )
        filters = (visibility, User.display_name.contains(search, autoescape=True))
        names = db.scalars(
            sa.select(User.username)
            .where(*filters)
            .order_by(
                User.username,
            )
            .offset(offset)
            .limit(limit)
        ).all()
        total = db.scalar(sa.select(sa.func.count()).select_from(User).where(*filters))
        return {"rows": names, "total": total}

    @app.get("/test-wp4/users/{user_id}")
    def detail(
        user_id: UUID,
        authority: Annotated[ActorAuthority, Depends(read_authority)],
        db: Annotated[Session, Depends(get_session)],
    ):
        authority.require_permission(READ)
        return {"username": visible_user(db, authority, user_id).username}

    @app.post("/test-wp4/profile/{user_id}")
    def profile(
        user_id: UUID,
        proof: Annotated[WriteProof, Depends(require_authenticated_write)],
        precheck: Annotated[ActorAuthority, Depends(read_authority)],
    ):
        precheck.require_permission(EDIT)
        if fixture.before_write:
            fixture.before_write()
        with fixture.runtime_factory.begin() as db:
            authority = writes.resolve_write_authority(db, proof, fixture.settings)
            authority.require_permission(EDIT)
            target = visible_user(db, authority, user_id)
            authority.require_unit(EDIT, target.institution_id, target.primary_unit_id)
            validate_profile_fields({"display_name"})
            return {"checked": str(target.id)}

    @app.get("/test-wp4/central")
    def central(authority: Annotated[ActorAuthority, Depends(read_authority)]):
        authority.require_institution(CENTRAL, fixture.tenant)
        return {"allowed": True}


def logged_in(fixture, username):
    browser = client(fixture)
    response = log_in(browser, username, PERSONAL)
    assert response.status_code == 204
    return browser


def current_authority(db, browser, session):
    principal = authenticate_session(session, browser.cookies["aq_uai_session"])
    return resolve_effective_grants(session, principal)


def write_profile(browser, fixture, name, headers=None):
    return browser.post(
        f"/test-wp4/profile/{fixture.people[name]}",
        headers=csrf_headers(browser) if headers is None else headers,
    )


def test_global_and_exact_unit_grants_keep_permissions_paired(estate):
    db = estate
    with db.owner_factory.begin() as owner:
        owner.add(direct_grant(db, "editor", "DIRECTORY_READER"))
    with logged_in(db, "editor") as browser, db.runtime_factory() as reader:
        authority = current_authority(db, browser, reader)
        assert authority.scope_for(READ).institution_wide
        assert authority.scope_for(EDIT).unit_ids == frozenset({db.units["a"]})
        assert authority.scope_for(EDIT).allows_unit(db.tenant, db.units["a"])
        assert not authority.scope_for(EDIT).allows_unit(db.tenant, db.units["b"])
        assert not authority.scope_for(EDIT).allows_unit(db.tenant, db.units["c"])
        assert not authority.scope_for(EDIT).allows_institution(db.tenant)
        assert (
            reader.scalars(
                sa.select(AccountGroup.id).where(
                    authority.scope_for(EDIT).predicate(AccountGroup.institution_id)
                )
            ).all()
            == []
        )
        assert not authority.scope_for(READ).allows_institution(db.other)
        assert not authority.has_permission("unapproved.permission")
        assert browser.get("/test-wp4/users").status_code == 200
        assert write_profile(browser, db, "visible-a").status_code == 200
        assert write_profile(browser, db, "hidden-b").status_code == 403
        assert write_profile(browser, db, "foreign-user").status_code == 404
        assert browser.get("/test-wp4/central").status_code == 403

    with logged_in(db, "administrator") as browser, db.runtime_factory() as reader:
        authority = current_authority(db, browser, reader)
        for permission in (CENTRAL, PermissionCode.AUTHORIZATION_MANAGE, PermissionCode.AUDIT_READ):
            authority.require_institution(permission, db.tenant)
        assert set(
            reader.scalars(
                sa.select(AccountGroup.id).where(
                    authority.scope_for(CENTRAL).predicate(AccountGroup.institution_id)
                )
            )
        ) == {group_id for name, group_id in db.groups.items() if name != "foreign"}
        assert browser.get("/test-wp4/central").status_code == 200
        assert "archived" in browser.get("/test-wp4/users").json()["rows"]
        assert "foreign-user" not in browser.get("/test-wp4/users").json()["rows"]
    with logged_in(db, "reader") as browser:
        assert browser.get("/test-wp4/users").status_code == 200
        assert write_profile(browser, db, "visible-a").status_code == 403
    with logged_in(db, "nogrants") as browser, db.runtime_factory() as reader:
        authority = current_authority(db, browser, reader)
        assert not authority.has_permission(READ)
        assert (
            reader.scalars(
                sa.select(User.id).where(
                    authority.scope_for(READ).predicate(
                        User.institution_id,
                        User.primary_unit_id,
                    )
                )
            ).all()
            == []
        )
        assert browser.get("/test-wp4/users").status_code == 403


def test_scoped_search_detail_pagination_and_count_do_not_leak_rows(estate):
    db = estate
    with logged_in(db, "editor") as browser:
        response = browser.get("/test-wp4/users", params={"limit": 2, "offset": 1})
        assert response.json() == {"rows": ["nogrants", "pending"], "total": 5}
        assert browser.get("/test-wp4/users", params={"search": "hidden-b"}).json() == {
            "rows": [],
            "total": 0,
        }
        assert browser.get("/test-wp4/users", params={"search": "visible-a"}).json() == {
            "rows": ["visible-a"],
            "total": 1,
        }
        assert browser.get(f"/test-wp4/users/{db.people['disabled']}").json() == {
            "username": "disabled",
        }
        denied = browser.get(f"/test-wp4/users/{db.people['hidden-b']}")
        missing = browser.get(f"/test-wp4/users/{uuid4()}")
        assert denied.status_code == missing.status_code == 404
        assert denied.json()["message"] == missing.json()["message"]
        assert write_profile(browser, db, "hidden-b").status_code == 404


@pytest.mark.parametrize(
    ("group", "membership_active"),
    [("eligible", False), ("inactive", True), ("system", True), ("specialist", True)],
)
def test_ineligible_group_membership_or_group_confers_no_authority(
    estate, group, membership_active
):
    db = estate
    add_inheritance(db, group, membership_active=membership_active)
    with logged_in(db, "member") as browser, db.runtime_factory() as reader:
        assert not current_authority(db, browser, reader).has_permission(EDIT)
        assert browser.get("/test-wp4/users").status_code == 403


def test_direct_and_group_grants_union_exact_units_and_respect_unit_deactivation(estate):
    db = estate
    add_inheritance(db, "eligible")
    with db.owner_factory.begin() as owner:
        owner.add(direct_grant(db, "member", "UNIT_DIRECTORY_MANAGER", "a"))
        owner.add(direct_grant(db, "member", "UNIT_DIRECTORY_MANAGER", "inactive"))
    with logged_in(db, "member") as browser, db.runtime_factory() as reader:
        authority = current_authority(db, browser, reader)
        assert authority.scope_for(EDIT).unit_ids == frozenset({db.units["a"], db.units["b"]})
        assert {grant.group_id for grant in authority.grants} == {None, db.groups["eligible"]}
        assert not authority.scope_for(EDIT).allows_unit(db.tenant, None)
        assert not authority.scope_for(EDIT).allows_institution(db.tenant)
        assert not authority.scope_for(EDIT).allows_unit(db.tenant, db.units["c"])
        assert write_profile(browser, db, "visible-a").status_code == 200
        assert write_profile(browser, db, "hidden-b").status_code == 200
        assert write_profile(browser, db, "archived").status_code == 404
        with db.owner_factory.begin() as owner:
            owner.get(Unit, db.units["b"]).active = False
        assert current_authority(db, browser, reader).scope_for(EDIT).unit_ids == frozenset(
            {db.units["a"]}
        )
        assert write_profile(browser, db, "hidden-b").status_code == 404


def test_catalog_is_resolved_but_unknown_and_group_central_permissions_fail_closed(estate):
    db = estate
    add_inheritance(db, "eligible", role="DIRECTORY_READER", unit=None)
    with db.owner_factory.begin() as owner:
        owner.add(CatalogPermission(code="unapproved.permission"))
        owner.flush()
        owner.add_all(
            [
                RolePermission(
                    role_code="DIRECTORY_READER", permission_code="unapproved.permission"
                ),
                RolePermission(role_code="DIRECTORY_READER", permission_code="directory.manage"),
            ]
        )
    with logged_in(db, "member") as browser, db.runtime_factory() as reader:
        authority = current_authority(db, browser, reader)
        assert authority.scope_for(READ).institution_wide
        assert not authority.has_permission("unapproved.permission")
        assert not authority.has_permission(CENTRAL)
        with db.owner_factory.begin() as owner:
            owner.delete(owner.get(RolePermission, ("DIRECTORY_READER", "directory.read")))
        assert not current_authority(db, browser, reader).has_permission(READ)


def test_assignment_validation_restricts_delegation_and_subject_scope(estate):
    db = estate
    args = {
        "institution_id": db.tenant,
        "subject": GrantSubject.GROUP,
        "subject_id": db.groups["eligible"],
        "role_code": "UNIT_DIRECTORY_MANAGER",
        "scope": GrantScope.UNIT,
        "unit_id": db.units["b"],
    }
    with logged_in(db, "administrator") as browser, db.runtime_factory() as reader:
        authority = current_authority(db, browser, reader)
        validate_role_assignment(reader, authority, **args)
        validate_role_assignment(
            reader,
            authority,
            **(
                args
                | {
                    "subject": GrantSubject.USER,
                    "subject_id": db.people["editor"],
                    "role_code": "FOUNDATION_ADMIN",
                    "scope": GrantScope.GLOBAL,
                    "unit_id": None,
                }
            ),
        )
        require_group_management(authority, db.tenant, "AUTHORIZATION")
        require_group_management(authority, db.tenant, "AI_SPECIALIST")
        for changes, code in (
            ({"subject_id": db.groups["system"]}, ErrorCode.VALIDATION_FAILED),
            ({"subject_id": db.groups["specialist"]}, ErrorCode.VALIDATION_FAILED),
            ({"subject_id": db.groups["inactive"]}, ErrorCode.VALIDATION_FAILED),
            ({"subject_id": db.groups["foreign"]}, ErrorCode.NOT_FOUND),
            ({"unit_id": db.units["foreign"]}, ErrorCode.NOT_FOUND),
            ({"unit_id": db.units["inactive"]}, ErrorCode.VALIDATION_FAILED),
            ({"unit_id": None}, ErrorCode.VALIDATION_FAILED),
            ({"role_code": "UNAPPROVED"}, ErrorCode.VALIDATION_FAILED),
            (
                {"role_code": "FOUNDATION_ADMIN", "scope": GrantScope.GLOBAL, "unit_id": None},
                ErrorCode.VALIDATION_FAILED,
            ),
            (
                {"subject": GrantSubject.USER, "subject_id": db.people["foreign-user"]},
                ErrorCode.NOT_FOUND,
            ),
            ({"institution_id": db.other}, ErrorCode.FORBIDDEN),
        ):
            with pytest.raises(DomainError) as denied:
                validate_role_assignment(reader, authority, **(args | changes))
            assert denied.value.code is code

    with logged_in(db, "editor") as browser, db.runtime_factory() as reader:
        authority = current_authority(db, browser, reader)
        for kind in ("SYSTEM", "AUTHORIZATION"):
            with pytest.raises(DomainError) as denied:
                require_group_management(authority, db.tenant, kind)
            assert denied.value.code is ErrorCode.FORBIDDEN
        with pytest.raises(DomainError) as denied:
            validate_role_assignment(reader, authority, **args)
        assert denied.value.code is ErrorCode.FORBIDDEN

    with pytest.raises(sa.exc.IntegrityError), db.owner_factory.begin() as owner:
        owner.add(inherited_grant(db, "eligible", "FOUNDATION_ADMIN", None))


def test_group_administrator_is_ignored_even_if_a_drifted_schema_allows_it(estate):
    db = estate
    # This database is created for this test and dropped by the fixture. Test
    # the runtime policy independently of the normal WP1 database constraint.
    with db.owner_factory.begin() as owner:
        owner.execute(
            sa.text(
                "ALTER TABLE group_role_assignments DROP CONSTRAINT ck_group_role_assignments_no_admin"
            )
        )
    add_inheritance(db, "eligible", role="FOUNDATION_ADMIN", unit=None)
    with logged_in(db, "member") as browser, db.runtime_factory() as reader:
        assert current_authority(db, browser, reader).grants == ()
        assert browser.get("/test-wp4/central").status_code == 403


@pytest.mark.parametrize("change", ["membership", "group", "assignment", "kind"])
def test_inherited_authority_is_revoked_on_next_request(estate, change):
    db = estate
    add_inheritance(db, "eligible")
    with logged_in(db, "member") as browser:
        assert write_profile(browser, db, "hidden-b").status_code == 200
        with db.owner_factory.begin() as owner:
            writes.lock_institution(owner, db.tenant, exclusive=True)
            if change == "membership":
                owner.get(
                    GroupMembership, (db.groups["eligible"], db.people["member"])
                ).active = False
            elif change == "group":
                owner.get(AccountGroup, db.groups["eligible"]).active = False
            elif change == "kind":
                owner.get(AccountGroup, db.groups["eligible"]).kind = "AI_SPECIALIST"
            else:
                owner.execute(
                    sa.delete(GroupRoleAssignment).where(
                        GroupRoleAssignment.group_id == db.groups["eligible"],
                    )
                )
        assert browser.get("/test-wp4/users").status_code == 403


def test_direct_grant_removal_leaves_only_alternative_authority(estate):
    db = estate
    with db.owner_factory.begin() as owner:
        owner.add(direct_grant(db, "editor", "DIRECTORY_READER"))
    with logged_in(db, "editor") as browser:
        assert write_profile(browser, db, "visible-a").status_code == 200
        with db.owner_factory.begin() as owner:
            writes.lock_institution(owner, db.tenant, exclusive=True)
            owner.execute(
                sa.delete(UserRoleAssignment).where(
                    UserRoleAssignment.user_id == db.people["editor"],
                    UserRoleAssignment.role_code == "UNIT_DIRECTORY_MANAGER",
                )
            )
        assert browser.get("/test-wp4/users").status_code == 200
        assert write_profile(browser, db, "visible-a").status_code == 403


def test_write_precheck_rejects_bad_auth_origin_and_csrf(estate):
    db = estate
    with client(db) as anonymous:
        assert anonymous.get("/test-wp4/users").status_code == 401
        assert write_profile(anonymous, db, "visible-a", ORIGIN_HEADER).status_code == 401
        assert (
            anonymous.get("/test-wp4/users", headers={"Cookie": "aq_uai_session=bad"}).status_code
            == 401
        )
    with logged_in(db, "temporary") as restricted:
        assert restricted.get("/test-wp4/users").status_code == 403
        assert write_profile(restricted, db, "visible-a").status_code == 403
        assert restricted.get("/api/v1/auth/me").status_code == 200
        assert (
            restricted.post("/api/v1/auth/logout", headers=csrf_headers(restricted)).status_code
            == 204
        )
    with logged_in(db, "editor") as first, logged_in(db, "editor") as second:
        valid = csrf_headers(first)
        for headers in (
            ORIGIN_HEADER,
            {"X-CSRF-Token": valid["X-CSRF-Token"]},
            valid | {"Origin": "http://localhost:8000"},
            valid | {"X-CSRF-Token": "invalid"},
            csrf_headers(second),
            [*valid.items(), ("X-CSRF-Token", valid["X-CSRF-Token"])],
        ):
            result = write_profile(first, db, "visible-a", headers)
            assert result.status_code == 403
            assert result.json()["request_id"] == result.headers["X-Request-ID"]
        assert write_profile(first, db, "visible-a", valid).status_code == 200


@pytest.mark.parametrize("state", ["disabled", "expired", "revoked"])
def test_protected_routes_recheck_account_and_session_state(estate, state):
    db = estate
    with logged_in(db, "editor") as browser:
        assert browser.get("/test-wp4/users").status_code == 200
        write_headers = csrf_headers(browser)
        with db.owner_factory.begin() as owner:
            lock_account(owner, db.people["editor"])
            if state == "disabled":
                owner.get(User, db.people["editor"]).state = "DISABLED"
            elif state == "revoked":
                revoke_user_sessions(owner, db.people["editor"], datetime.now(UTC))
            else:
                expires = datetime.now(UTC) - timedelta(seconds=5)
                owner.execute(
                    sa.update(AuthSession)
                    .where(
                        AuthSession.user_id == db.people["editor"],
                    )
                    .values(issued_at=expires - timedelta(hours=8), expires_at=expires)
                )
        assert browser.get("/test-wp4/users").status_code == 401
        assert write_profile(browser, db, "visible-a", write_headers).status_code == 401


def test_mutation_rechecks_grants_after_http_permission_precheck(estate):
    db = estate

    def revoke():
        with db.owner_factory.begin() as owner:
            writes.lock_institution(owner, db.tenant, exclusive=True)
            owner.execute(
                sa.delete(UserRoleAssignment).where(
                    UserRoleAssignment.user_id == db.people["editor"],
                )
            )

    db.before_write = revoke
    with logged_in(db, "editor") as browser:
        assert browser.get("/test-wp4/users").status_code == 200
        assert write_profile(browser, db, "visible-a").status_code == 403


@pytest.mark.parametrize("revocation", ["grant", "session"])
def test_write_rechecks_after_existing_revoker_commits(estate, monkeypatch, revocation):
    db = estate
    waiting = Event()
    original_institution_lock = writes.lock_institution
    original_account_locks = writes.lock_accounts

    def track_scope(db, institution_id, *, exclusive):
        waiting.set()
        original_institution_lock(db, institution_id, exclusive=exclusive)

    def track_accounts(db, account_ids):
        waiting.set()
        original_account_locks(db, account_ids)

    monkeypatch.setattr(
        writes,
        "lock_institution" if revocation == "grant" else "lock_accounts",
        track_scope if revocation == "grant" else track_accounts,
    )
    with logged_in(db, "editor") as browser, ThreadPoolExecutor(max_workers=1) as pool:
        headers = csrf_headers(browser)
        proof = WriteProof(
            browser.cookies["aq_uai_session"],
            (ORIGIN,),
            (headers["X-CSRF-Token"],),
        )

        def attempt():
            with db.runtime_factory.begin() as connection:
                authority = writes.resolve_write_authority(
                    connection,
                    proof,
                    db.settings,
                    related_account_ids=[db.people["visible-a"]],
                    related_account_permission=EDIT,
                )
                authority.require_unit(EDIT, db.tenant, db.units["a"])

        with db.owner_factory.begin() as owner:
            if revocation == "grant":
                original_institution_lock(owner, db.tenant, exclusive=True)
                owner.execute(
                    sa.delete(UserRoleAssignment).where(
                        UserRoleAssignment.user_id == db.people["editor"],
                    )
                )
            else:
                lock_account(owner, db.people["editor"])
                revoke_user_sessions(owner, db.people["editor"], datetime.now(UTC))
            future = pool.submit(attempt)
            assert waiting.wait(10)
            assert not future.done()
        with pytest.raises(DomainError) as denied:
            future.result(timeout=10)
        assert denied.value.code is (
            ErrorCode.FORBIDDEN if revocation == "grant" else ErrorCode.AUTH_REQUIRED
        )


def test_runtime_cannot_rewrite_grant_keys_group_kind_or_audit_history(estate):
    db = estate
    with connect(db.runtime, autocommit=True) as session:
        for statement in (
            "DELETE FROM role_permissions",
            "UPDATE user_role_assignments SET role_code = role_code",
            "UPDATE account_groups SET kind = 'AUTHORIZATION'",
            "UPDATE group_memberships SET institution_id = institution_id",
            "DELETE FROM audit_events",
            "UPDATE audit_events SET action = 'fake'",
        ):
            assert_denied(session, statement)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            session.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(db.roles.migration)))


def test_authority_writer_waits_for_a_guarded_write_already_in_progress(estate, monkeypatch):
    db = estate
    waiting = Event()
    acquire = writes.lock_institution

    def track_exclusive(connection, institution_id, *, exclusive):
        if exclusive:
            waiting.set()
        acquire(connection, institution_id, exclusive=exclusive)

    monkeypatch.setattr(writes, "lock_institution", track_exclusive)

    def proof(browser):
        return WriteProof(
            browser.cookies["aq_uai_session"],
            (ORIGIN,),
            (csrf_headers(browser)["X-CSRF-Token"],),
        )

    with logged_in(db, "editor") as editor, logged_in(db, "administrator") as administrator:
        admin_proof = proof(administrator)

        def authority_change():
            with db.runtime_factory.begin() as connection:
                authority = writes.resolve_write_authority(
                    connection,
                    admin_proof,
                    db.settings,
                    changes_authority=True,
                    related_account_ids=[db.people["editor"]],
                    related_account_permission=PermissionCode.AUTHORIZATION_MANAGE,
                )
                authority.require_institution(PermissionCode.AUTHORIZATION_MANAGE, db.tenant)

        with ThreadPoolExecutor(max_workers=1) as pool:
            with db.runtime_factory.begin() as connection:
                authority = writes.resolve_write_authority(connection, proof(editor), db.settings)
                authority.require_unit(EDIT, db.tenant, db.units["a"])
                future = pool.submit(authority_change)
                assert waiting.wait(10)
                assert not future.done()
            future.result(timeout=10)


def test_related_account_locks_are_filtered_by_operation_scope(estate, monkeypatch):
    db = estate
    taken = []
    acquire = writes.lock_accounts

    def track(connection, account_ids):
        taken.append(set(account_ids))
        acquire(connection, account_ids)

    monkeypatch.setattr(writes, "lock_accounts", track)
    with logged_in(db, "editor") as browser:
        proof = WriteProof(
            browser.cookies["aq_uai_session"],
            (ORIGIN,),
            (csrf_headers(browser)["X-CSRF-Token"],),
        )
        hints = [db.people[name] for name in ("visible-a", "hidden-b", "foreign-user")]
        with db.runtime_factory.begin() as connection:
            authority = writes.resolve_write_authority(
                connection,
                proof,
                db.settings,
                related_account_ids=hints,
                related_account_permission=EDIT,
            )
            authority.require_unit(EDIT, db.tenant, db.units["a"])
        assert taken == [{db.people["editor"], db.people["visible-a"]}]

        with pytest.raises(DomainError) as denied, db.runtime_factory.begin() as connection:
            writes.resolve_write_authority(
                connection,
                proof,
                db.settings,
                related_account_ids=hints,
                related_account_permission=PermissionCode.AUTHORIZATION_MANAGE,
            )
        assert denied.value.code is ErrorCode.FORBIDDEN
        assert len(taken) == 1


def test_write_guard_requires_one_outer_transaction_with_final_lock_mode(estate):
    db = estate
    with logged_in(db, "editor") as browser:
        proof = WriteProof(
            browser.cookies["aq_uai_session"],
            (ORIGIN,),
            (csrf_headers(browser)["X-CSRF-Token"],),
        )
        with db.runtime_factory() as connection:
            with pytest.raises(RuntimeError, match="outer"):
                writes.resolve_write_authority(connection, proof, db.settings)
            with connection.begin():
                with connection.begin_nested(), pytest.raises(RuntimeError, match="outer"):
                    writes.resolve_write_authority(connection, proof, db.settings)
                with pytest.raises(ValueError, match="operation permission"):
                    writes.resolve_write_authority(
                        connection,
                        proof,
                        db.settings,
                        related_account_ids=[db.people["visible-a"]],
                    )
                writes.resolve_write_authority(connection, proof, db.settings)
                with pytest.raises(RuntimeError, match="once"):
                    writes.resolve_write_authority(
                        connection,
                        proof,
                        db.settings,
                        changes_authority=True,
                    )
            with connection.begin():
                writes.resolve_write_authority(connection, proof, db.settings)
