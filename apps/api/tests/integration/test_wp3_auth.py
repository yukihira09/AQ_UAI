"""Real PostgreSQL tests for WP3 using separate operator and runtime connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from aq_uai_api.api.v1 import auth
from aq_uai_api.auth import operator, service
from aq_uai_api.auth.security import COOKIE_NAME, hash_password, token_digest
from aq_uai_api.core.config import Settings
from aq_uai_api.db.identity import AuthSession, User, UserCredential
from aq_uai_api.db.session import get_session
from aq_uai_api.main import create_app

from .test_wp2_database import assert_denied, connect, disposable_database, migrate, prepare
from .test_wp2_database import pytestmark as postgres_marks

pytestmark = postgres_marks
ORIGIN = "http://admin.localhost:8000"
ORIGIN_HEADER = {"Origin": ORIGIN}
TEMPORARY = "synthetic-temporary-99"
PERSONAL = "synthetic-personal-88"
RESET = "synthetic-recovery-77"
PROFILE = operator.InitialAdmin(
    "WP3", "Synthetic University", "MAIN", "Main", " Admin ", "Synthetic Admin", "STAFF-001"
)


@pytest.fixture
def auth_db(monkeypatch):
    with disposable_database() as (admin, roles, owner, runtime):
        prepare(admin, roles)
        migrate(owner, roles)
        owner_engine = sa.create_engine(owner, hide_parameters=True)
        runtime_engine = sa.create_engine(runtime, hide_parameters=True)
        owner_factory = sessionmaker(bind=owner_engine, autoflush=False, expire_on_commit=False)
        runtime_factory = sessionmaker(bind=runtime_engine, autoflush=False, expire_on_commit=False)
        monkeypatch.setattr(operator, "write_transaction", owner_factory.begin)
        monkeypatch.setattr(service, "write_transaction", runtime_factory.begin)
        settings = Settings(
            environment="test",
            auth_origin=ORIGIN,
            auth_allow_http_local=True,
            auth_throttle_key="a5" * 32,
            db_password=runtime.password,
        )
        monkeypatch.setattr(auth, "get_settings", lambda: settings)
        app = create_app()

        def runtime_read():
            with Session(runtime_engine) as db:
                yield db

        app.dependency_overrides[get_session] = runtime_read

        @app.get("/test-protected")
        def protected(user: Annotated[User, Depends(auth.require_authenticated_user)]):
            return {"id": user.id}

        try:
            yield SimpleNamespace(
                app=app,
                owner=owner,
                runtime=runtime,
                roles=roles,
                owner_factory=owner_factory,
                runtime_factory=runtime_factory,
                settings=settings,
            )
        finally:
            owner_engine.dispose()
            runtime_engine.dispose()


@pytest.fixture
def bootstrapped(auth_db):
    auth_db.user_id = operator.bootstrap_admin(PROFILE, TEMPORARY, uuid4())
    return auth_db


def client(db, base_url=ORIGIN):
    return TestClient(db.app, base_url=base_url)


def log_in(browser, username="ADMIN", password=TEMPORARY, headers=None):
    return browser.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers=ORIGIN_HEADER if headers is None else headers,
    )


def token_header(token):
    return {"Cookie": f"{COOKIE_NAME}={token}"}


def csrf_headers(browser):
    csrf = browser.get("/api/v1/auth/me").json()["csrf_token"]
    return {**ORIGIN_HEADER, "X-CSRF-Token": csrf}


def count(connection, table):
    # Test call sites only pass constant table names.
    return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_bootstrap_is_atomic_and_only_one_concurrent_attempt_succeeds(auth_db):
    invalid = operator.InitialAdmin(
        "WP3", "Synthetic University", "", "Main", "admin", "Admin", "STAFF-001"
    )
    with pytest.raises(operator.OperatorError):
        operator.bootstrap_admin(invalid, TEMPORARY, uuid4())
    with connect(auth_db.owner) as db:
        assert count(db, "institutions") == count(db, "audit_events") == 0

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(operator.bootstrap_admin, PROFILE, TEMPORARY, uuid4()) for _ in range(2)
        ]
        outcomes = [future.exception(timeout=15) for future in futures]
    assert sum(error is None for error in outcomes) == 1
    assert sum(isinstance(error, operator.OperatorError) for error in outcomes) == 1

    with connect(auth_db.owner) as db:
        assert [
            count(db, table)
            for table in (
                "institutions",
                "units",
                "users",
                "user_credentials",
                "user_role_assignments",
                "audit_events",
            )
        ] == [1] * 6
        assert db.execute(
            "SELECT username, state, role_code, scope, a.unit_id FROM users u "
            "JOIN user_role_assignments a ON a.user_id = u.id"
        ).fetchone() == ("admin", "ACTIVE", "FOUNDATION_ADMIN", "GLOBAL", None)
        password_hash, change = db.execute(
            "SELECT password_hash, must_change_password FROM user_credentials"
        ).fetchone()
        assert password_hash.startswith("$argon2id$") and TEMPORARY not in password_hash and change
        assert db.execute("SELECT action, actor_id, outcome FROM audit_events").fetchone() == (
            "auth.admin_bootstrapped",
            None,
            "SUCCESS",
        )


def test_cookie_rotation_me_password_change_and_logout(bootstrapped, caplog):
    fixture = bootstrapped
    with client(fixture) as first, client(fixture) as second:
        response = log_in(first, username=" ADMIN ")
        assert response.status_code == 204 and response.content == b""
        cookie = response.headers["set-cookie"].lower()
        assert all(
            part in cookie for part in ("httponly", "samesite=lax", "max-age=28800", "path=/")
        )
        assert "domain=" not in cookie and "; secure" not in cookie
        assert response.headers["cache-control"] == "no-store"
        stale_token = first.cookies.get(COOKIE_NAME)
        assert log_in(first).status_code == 204
        current_token = first.cookies.get(COOKIE_NAME)
        assert current_token != stale_token
        assert first.get("/api/v1/auth/me", headers=token_header(stale_token)).status_code == 401
        assert log_in(second).status_code == 204
        me = first.get("/api/v1/auth/me")
        assert set(me.json()) == {
            "id",
            "username",
            "display_name",
            "institution_id",
            "primary_unit_id",
            "state",
            "must_change_password",
            "csrf_token",
        }
        assert me.json()["id"] == str(fixture.user_id) and me.json()["must_change_password"]
        assert me.headers["cache-control"] == "no-store"
        assert first.get("/test-protected").status_code == 403
        headers = csrf_headers(first)
        change = {"current_password": TEMPORARY, "new_password": PERSONAL}
        assert (
            first.post(
                "/api/v1/auth/change-password", json=change, headers=ORIGIN_HEADER
            ).status_code
            == 403
        )
        assert (
            first.post(
                "/api/v1/auth/change-password", json=change, headers=csrf_headers(second)
            ).status_code
            == 403
        )
        wrong = {**change, "current_password": "not-the-current-password"}
        assert (
            first.post("/api/v1/auth/change-password", json=wrong, headers=headers).status_code
            == 401
        )
        reused = {**change, "new_password": fixture.runtime.password}
        assert (
            first.post("/api/v1/auth/change-password", json=reused, headers=headers).status_code
            == 422
        )
        response = first.post("/api/v1/auth/change-password", json=change, headers=headers)
        assert response.status_code == 204 and "Max-Age=0" in response.headers["set-cookie"]
        assert second.get("/api/v1/auth/me").status_code == 401
        assert first.get("/api/v1/auth/me", headers=token_header(current_token)).status_code == 401
        assert log_in(first, password=PERSONAL).status_code == 204
        assert not first.get("/api/v1/auth/me").json()["must_change_password"]
        assert first.get("/test-protected").status_code == 200
        new_token = first.cookies.get(COOKIE_NAME)
        headers = csrf_headers(first)
        assert (
            first.post(
                "/api/v1/auth/logout", headers={**headers, "Origin": "http://localhost:8000"}
            ).status_code
            == 403
        )
        assert (
            first.post(
                "/api/v1/auth/logout", headers={**headers, "X-CSRF-Token": "wrong"}
            ).status_code
            == 403
        )
        assert first.post("/api/v1/auth/logout", headers=headers).status_code == 204
        assert first.get("/api/v1/auth/me", headers=token_header(new_token)).status_code == 401

    with connect(fixture.runtime) as db:
        digests = db.execute(
            "SELECT token_digest, expires_at - issued_at, revoked_at FROM auth_sessions"
        ).fetchall()
        assert len(digests) == 4
        assert {digest for digest, _, _ in digests}.issuperset(
            {
                token_digest(stale_token),
                token_digest(current_token),
                token_digest(new_token),
            }
        )
        assert all(
            len(digest) == 32 and lifetime == timedelta(hours=8) and revoked
            for digest, lifetime, revoked in digests
        )
        events = db.execute("SELECT action, changes FROM audit_events").fetchall()
        assert ("auth.password_changed", {"revoked_sessions": 2}) in events
        assert ("auth.logout", {}) in events
        for secret in (TEMPORARY, PERSONAL, current_token, new_token, me.json()["csrf_token"]):
            assert secret not in str(events) + caplog.text


def test_origin_password_validation_and_generic_account_failures(bootstrapped, caplog):
    fixture = bootstrapped
    with fixture.owner_factory.begin() as db:
        active = db.get(User, fixture.user_id)
        for name, state in (("disabled", "DISABLED"), ("pending", "PENDING")):
            account = User(
                institution_id=active.institution_id,
                primary_unit_id=active.primary_unit_id,
                username=name,
                display_name=name,
                code_type="STAFF",
                institutional_code=name,
                state=state,
            )
            db.add(account)
            db.flush()
            db.add(UserCredential(user_id=account.id, password_hash=hash_password(TEMPORARY)))

    with client(fixture) as browser:
        assert log_in(browser, headers={}).status_code == 403
        assert log_in(browser, headers={"Origin": "http://localhost:8000"}).status_code == 403
        large = "synthetic-too-long-" * 20
        response = log_in(browser, password=large)
        assert response.status_code == 422 and large not in response.text + caplog.text
        rejected = [
            log_in(browser, "missing"),
            log_in(browser, "disabled"),
            log_in(browser, "pending"),
            log_in(browser, "admin", "wrong"),
            log_in(browser, "invalid user"),
        ]
        assert all(response.status_code == 401 for response in rejected)
        assert len({(r.json()["code"], r.json()["message"]) for r in rejected}) == 1
        for malformed in ("bad!", "a" * 43):
            assert (
                browser.get("/api/v1/auth/me", headers=token_header(malformed)).status_code == 401
            )
    with connect(fixture.runtime) as db:
        assert count(db, "auth_sessions") == 0
        assert db.execute(
            "SELECT count(*) FROM audit_events WHERE action = 'auth.login_rejected' AND actor_id IS NULL"
        ).fetchone() == (5,)


def test_https_cookie_and_expired_or_disabled_sessions(bootstrapped, monkeypatch):
    fixture = bootstrapped
    https = "https://admin.localhost:8000"
    settings = fixture.settings.model_copy(
        update={"auth_origin": https, "auth_allow_http_local": False}
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    with client(fixture, https) as browser:
        response = log_in(browser, headers={"Origin": https})
        assert response.status_code == 204 and "; Secure" in response.headers["set-cookie"]
        past = datetime.now(UTC) - timedelta(hours=10)
        with fixture.owner_factory.begin() as db:
            db.execute(
                sa.update(AuthSession).values(issued_at=past, expires_at=past + timedelta(hours=8))
            )
        assert browser.get("/api/v1/auth/me").status_code == 401
        assert log_in(browser, headers={"Origin": https}).status_code == 204
        with fixture.owner_factory.begin() as db:
            service.lock_account(db, fixture.user_id)
            db.get(User, fixture.user_id).state = "DISABLED"
        assert browser.get("/api/v1/auth/me").status_code == 401
    with pytest.raises(operator.OperatorError):
        operator.reset_password("admin", RESET, uuid4())


def test_operator_reset_revokes_sessions_and_preserves_roles(bootstrapped):
    fixture = bootstrapped
    with client(fixture) as first, client(fixture) as second:
        assert log_in(first).status_code == log_in(second).status_code == 204
        operator.reset_password("ADMIN", RESET, uuid4())
        assert (
            first.get("/api/v1/auth/me").status_code
            == second.get("/api/v1/auth/me").status_code
            == 401
        )
        assert log_in(first).status_code == 401
        assert log_in(first, password=RESET).status_code == 204
        assert first.get("/api/v1/auth/me").json()["must_change_password"]
        assert first.get("/test-protected").status_code == 403
    with connect(fixture.runtime) as db:
        assert db.execute("SELECT user_id FROM user_role_assignments").fetchone() == (
            fixture.user_id,
        )
        assert db.execute(
            "SELECT actor_id, target_id, changes FROM audit_events WHERE action = 'auth.operator_reset'"
        ).fetchone() == (None, fixture.user_id, {"revoked_sessions": 2})


@pytest.mark.parametrize("operation", ["reset", "disable"])
def test_login_waits_for_account_invalidation(bootstrapped, monkeypatch, operation):
    fixture = bootstrapped
    waiting = Event()
    lock = service.lock_account

    def mark_waiting(db, user_id):
        waiting.set()
        lock(db, user_id)

    monkeypatch.setattr(service, "lock_account", mark_waiting)

    def attempt():
        with client(fixture) as browser:
            return log_in(browser).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        if operation == "reset":
            acquired, release = Event(), Event()

            def pause_reset(db, user_id):
                lock(db, user_id)
                acquired.set()
                assert release.wait(10)

            monkeypatch.setattr(operator, "lock_account", pause_reset)
            reset = pool.submit(operator.reset_password, "admin", RESET, uuid4())
            try:
                assert acquired.wait(10)
                pending = pool.submit(attempt)
                assert waiting.wait(10)
                assert not pending.done()
            finally:
                release.set()
            reset.result(timeout=15)
        else:
            with fixture.owner_factory.begin() as db:
                lock(db, fixture.user_id)
                pending = pool.submit(attempt)
                assert waiting.wait(10)
                assert not pending.done()
                db.get(User, fixture.user_id).state = "DISABLED"
                service.revoke_user_sessions(db, fixture.user_id, datetime.now(UTC))
        assert pending.result(timeout=15) == 401
    with connect(fixture.runtime) as db:
        assert count(db, "auth_sessions") == 0


@pytest.fixture
def fixed_throttle_clock(monkeypatch):
    moment = datetime.now(UTC)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    monkeypatch.setattr(service, "datetime", FixedClock)
    return moment


def test_login_throttle_serializes_concurrent_failures(auth_db, fixed_throttle_clock):
    def attempt(index):
        with client(auth_db) as browser:
            return log_in(
                browser,
                " Missing ",
                "bad",
                {**ORIGIN_HEADER, "X-Forwarded-For": f"198.51.100.{index + 1}"},
            ).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sorted(pool.map(attempt, range(10))) == [401] * 5 + [429] * 5
    with connect(auth_db.runtime) as db:
        assert db.execute(
            "SELECT dimension, failure_count, octet_length(key_digest) FROM auth_throttle_buckets "
            "ORDER BY dimension"
        ).fetchall() == [("ADDRESS", 5, 32), ("LOGIN", 5, 32)]
        assert count(db, "audit_events") == 10


def test_address_throttle_ignores_forged_forwarding_and_cleanup_is_bounded(
    auth_db,
    fixed_throttle_clock,
):
    with client(auth_db) as browser:
        for index in range(31):
            headers = {
                **ORIGIN_HEADER,
                "X-Forwarded-For": f"198.51.100.{index + 1}",
                "X-Real-IP": f"192.0.2.{index + 1}",
            }
            expected = 429 if index == 30 else 401
            assert log_in(browser, f"missing-{index}", "bad", headers).status_code == expected
    expired = fixed_throttle_clock - timedelta(days=2)
    with connect(auth_db.owner) as db:
        for index in range(105):
            db.execute(
                "INSERT INTO auth_throttle_buckets VALUES ('LOGIN', %s, %s, 1)",
                (index.to_bytes(32, "big"), expired),
            )
    with auth_db.runtime_factory.begin() as db:
        assert service.cleanup_throttle(db, fixed_throttle_clock) == 100
    with connect(auth_db.runtime) as db:
        assert db.execute(
            "SELECT count(*) FROM auth_throttle_buckets WHERE window_start = %s", (expired,)
        ).fetchone() == (5,)
        assert db.execute(
            "SELECT failure_count FROM auth_throttle_buckets WHERE dimension = 'ADDRESS'"
        ).fetchone() == (30,)


def test_audit_failure_rolls_back_login_and_runtime_cannot_grant_roles(bootstrapped, caplog):
    fixture = bootstrapped
    with connect(fixture.owner) as db:
        db.execute(safer_revoke_audit(fixture.roles.runtime))
    with client(fixture) as browser:
        response = log_in(browser)
        assert response.status_code == 500 and "set-cookie" not in response.headers
        assert TEMPORARY not in response.text + caplog.text
    with connect(fixture.runtime, autocommit=True) as db:
        assert count(db, "auth_sessions") == 0
        assert count(db, "audit_events") == 1
        assert_denied(db, "INSERT INTO user_role_assignments SELECT * FROM user_role_assignments")
        assert_denied(db, "UPDATE users SET state = 'DISABLED'")
        assert_denied(db, "UPDATE audit_events SET action = 'fake'")


def safer_revoke_audit(role):
    from psycopg import sql

    return sql.SQL("REVOKE INSERT ON audit_events FROM {}").format(sql.Identifier(role))


def test_audit_failure_keeps_password_and_session_intact(bootstrapped):
    fixture = bootstrapped
    with client(fixture) as browser:
        assert log_in(browser).status_code == 204
        with connect(fixture.owner) as db:
            old_hash = db.execute("SELECT password_hash FROM user_credentials").fetchone()[0]
            db.execute(safer_revoke_audit(fixture.roles.runtime))

        response = browser.post(
            "/api/v1/auth/change-password",
            json={"current_password": TEMPORARY, "new_password": PERSONAL},
            headers=csrf_headers(browser),
        )
        assert response.status_code == 500 and "set-cookie" not in response.headers
        assert browser.get("/api/v1/auth/me").json()["must_change_password"]
    with connect(fixture.runtime) as db:
        assert db.execute("SELECT password_hash FROM user_credentials").fetchone() == (old_hash,)
        assert db.execute("SELECT revoked_at FROM auth_sessions").fetchone() == (None,)
        assert count(db, "audit_events") == 2
