"""M5 against PostgreSQL: routing, eligibility, history, guards and races.

Real routes, runtime login, session + Origin + CSRF. Connection tests run against the
loopback HTTPS fake provider (``fake_provider``). External providers cannot be tested
without public DNS, so where an external model needs a PASSED test the test inserts one
directly as the database owner, as a prior successful test would have left it.
"""

import base64
import ipaddress
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.errors import CheckViolation, InsufficientPrivilege
from pydantic import SecretStr

from aq_uai_api.db.schema import REQUIRED_SCHEMA_REVISION
from aq_uai_api.mdl import egress, testing
from aq_uai_api.mdl.credentials import KeyRing
from aq_uai_api.mdl.rewrap import rewrap_all

from .test_m3_mdl_api import EXTERNAL, KEY, ROTATED, SECRET, audit_actions, call, mdl_path
from .test_m3_mdl_api import mdl as mdl
from .test_m4_connection_tests import (
    add_model,
    local_provider,
    run_test,
    set_settings,
    stored_tests,
)
from .test_m4_connection_tests import m4 as m4
from .test_wp2_database import alembic, connect, disposable_database, migrate, prepare
from .test_wp3_auth import ORIGIN_HEADER, client, csrf_headers
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import directory as directory
from .test_wp5_directory import get, pytestmark, send

pytestmark = pytestmark


@pytest.fixture
def m5(m4):
    db = m4
    db.local = local_provider(db, "Local")
    return db


def ready_model(db, technical_id, provider_id=None, risk="LOW"):
    """A model that is eligible: TEXT, risk recorded, current PASSED test."""
    model = add_model(db, provider_id or db.local["id"], technical_id)
    call(db, "PATCH", f"/models/{model['id']}", {"risk_level": risk})
    assert run_test(db, model["id"])["status"] == "PASSED"
    return call(db, "GET", f"/models/{model['id']}")


def routing(db):
    return call(db, "GET", "/routing")


def put(db, expected, primary, fallback=None, status=200, reference=None):
    body = {"expected_revision": expected, "primary_model_id": primary,
            "fallback_model_id": fallback}
    if reference is not None:
        body["decision_reference"] = reference
    return call(db, "PUT", "/routing", body, status)


def issues(db, model_id):
    return call(db, "GET", f"/models/{model_id}")["routing"]["issues"]


def insert_passed_test(db, model_id, connection_version=1, credential_version=1):
    with connect(db.owner) as connection:
        connection.execute(
            "INSERT INTO mdl_connection_tests (institution_id, model_id, connection_version,"
            " credential_version, started_by, status, http_status_class, latency_ms,"
            " started_at, finished_at) VALUES (%s, %s, %s, %s, %s, 'PASSED', 2, 5,"
            " now() - interval '1 minute', now() - interval '59 seconds')",
            (db.tenant, model_id, connection_version, credential_version, db.manager_id),
        )
        connection.commit()


def external_ready(db, name="Vendor"):
    provider = call(db, "POST", "/providers", EXTERNAL | {"name": name}, 201)
    agreement = call(
        db, "POST", f"/providers/{provider['id']}/agreements",
        {"basis": "NO_TRAINING_COMMITMENT", "document_number": "HD-07/2026"}, 201,
    )
    model = add_model(db, provider["id"], f"{name.lower()}-model")
    call(db, "PATCH", f"/models/{model['id']}", {"risk_level": "MEDIUM"})
    insert_passed_test(db, model["id"])
    return provider, agreement, model


def revision_rows(db):
    with connect(db.owner) as connection:
        return connection.execute(
            "SELECT revision, before_primary_model_id::text, after_primary_model_id::text,"
            " before_fallback_model_id::text, after_fallback_model_id::text,"
            " after_primary_name, decision_reference FROM mdl_routing_revisions ORDER BY revision"
        ).fetchall()


# ------------------------------------------------------------------- access, basics


def test_routing_requires_mdl_rights_and_starts_empty(m5):
    db = m5
    empty = routing(db)
    assert empty == {
        "revision": 0, "primary": None, "fallback": None,
        "effective": {"state": "NOT_CONFIGURED", "model_id": None},
        "updated_by": None, "updated_at": None,
    }
    assert call(db, "GET", "/routing/revisions")["items"] == []
    body = {"expected_revision": 0, "primary_model_id": None}
    with client(db) as anonymous:
        for path in ("/routing", "/routing/revisions"):
            assert anonymous.get("/api/v1/mdl" + path).status_code == 401
        assert anonymous.put("/api/v1/mdl/routing", json=body, headers=ORIGIN_HEADER).status_code == 401
    for path in ("/routing", "/routing/revisions"):
        assert get(db.admin, mdl_path(path)).status_code == 403  # FOUNDATION_ADMIN: no MDL rights
    assert send(db.admin, "PUT", mdl_path("/routing"), body).status_code == 403
    assert db.manager.put("/api/v1/mdl/routing", json=body).status_code in (401, 403)  # no CSRF
    for invalid in (
        {"primary_model_id": None},  # expected_revision required
        {"expected_revision": "0", "primary_model_id": None},  # strict integer
        {"expected_revision": -1, "primary_model_id": None},
        {"expected_revision": 0, "primary_model_id": None, "fallback_model_id": str(uuid4())},
        {"expected_revision": 0, "primary_model_id": None, "temperature": 0.2},  # FR-MDL-040
        {"expected_revision": 0, "primary_model_id": None, "decision_reference": "  "},
        {"expected_revision": 0, "primary_model_id": None, "decision_reference": "x" * 129},
    ):
        assert call(db, "PUT", "/routing", invalid, 422)["code"] == "VALIDATION_FAILED"
    assert put(db, 0, str(uuid4()), status=404)["code"] == "NOT_FOUND"
    assert revision_rows(db) == []


# ------------------------------------------------------------------ eligibility


def test_eligibility_matrix_and_selection_list(m5):
    db = m5
    good = ready_model(db, "good")
    assert good["routing"] == {"eligible": True, "issues": []}

    untested = add_model(db, db.local["id"], "untested")
    call(db, "PATCH", f"/models/{untested['id']}", {"risk_level": "LOW"})
    assert issues(db, untested["id"]) == ["not_tested"]

    unclassified = add_model(db, db.local["id"], "unclassified")
    run_test(db, unclassified["id"])
    assert issues(db, unclassified["id"]) == ["risk_unclassified"]  # 031: before routing

    failed = add_model(db, db.local["id"], "failed")
    call(db, "PATCH", f"/models/{failed['id']}", {"risk_level": "HIGH"})
    db.provider.mode = "auth"
    run_test(db, failed["id"])
    db.provider.mode = "ok"
    assert issues(db, failed["id"]) == ["test_failed"]  # 020-AC2

    image = add_model(db, db.local["id"], "image", ("IMAGE",))
    assert set(issues(db, image["id"])) == {"text_unsupported", "risk_unclassified"}

    inactive = ready_model(db, "inactive")
    call(db, "POST", f"/models/{inactive['id']}/deactivate")
    assert issues(db, inactive["id"]) == ["model_inactive"]

    # External model without an agreement in force (FR-MDL-030 AC1, use gate).
    vendor = call(db, "POST", "/providers", EXTERNAL | {"name": "No DPA"}, 201)
    no_dpa = add_model(db, vendor["id"], "no-dpa")
    call(db, "PATCH", f"/models/{no_dpa['id']}", {"risk_level": "LOW"})
    insert_passed_test(db, no_dpa["id"])
    assert issues(db, no_dpa["id"]) == ["dpa_missing"]

    # FR-MDL-021 AC1: the selection list holds only eligible models.
    listed = call(db, "GET", "/models", {"routing_eligible": "true"})
    assert [item["id"] for item in listed["items"]] == [good["id"]] and listed["total"] == 1
    others = call(db, "GET", "/models", {"routing_eligible": "false", "limit": 2, "offset": 1})
    assert others["total"] == 6 and len(others["items"]) == 2

    # Every new selection is re-checked on the server; reasons name the slot.
    for model, reason in (
        (untested, "not_tested"), (unclassified, "risk_unclassified"), (failed, "test_failed"),
        (image, "text_unsupported"), (inactive, "model_inactive"), (no_dpa, "dpa_missing"),
    ):
        refused = put(db, 0, model["id"], status=409)
        assert refused["code"] == "MDL_NOT_ELIGIBLE"
        assert f"primary.{reason}" in refused["details"]["reasons"]
    refused = put(db, 0, good["id"], failed["id"], status=409)
    assert refused["details"]["reasons"] == ["fallback.test_failed"]

    # Provider-level conditions: inactive provider, unreadable key, blocked endpoint.
    call(db, "POST", f"/providers/{db.local['id']}/deactivate")
    assert issues(db, good["id"]) == ["provider_inactive"]
    call(db, "POST", f"/providers/{db.local['id']}/activate")
    set_settings(db, mdl_credential_keys=SecretStr(""))
    assert issues(db, good["id"]) == ["credential_unavailable"]
    set_settings(db, mdl_credential_keys=SecretStr(f"k1:{KEY}"))
    set_settings(db, mdl_egress_internal_allowlist="")
    assert issues(db, good["id"]) == ["endpoint_blocked"]
    set_settings(db, mdl_egress_internal_allowlist=db.provider.allowlist)
    # Credential change: the earlier PASSED test no longer describes the configuration.
    call(db, "PATCH", f"/providers/{db.local['id']}", {"secret": ROTATED})
    assert issues(db, good["id"]) == ["test_outdated"]
    assert revision_rows(db) == []


# -------------------------------------------------------------- history and writes


def test_changes_create_immutable_revisions_and_no_ops_do_not(m5):
    db = m5
    first, second, third = (ready_model(db, name) for name in ("first", "second", "third"))
    created = put(db, 0, first["id"], reference="QĐ-12/2026")
    assert created["revision"] == 1 and created["effective"] == {
        "state": "PRIMARY", "model_id": first["id"],
    }
    assert created["primary"]["usable"] and created["fallback"] is None
    # No-op: same values (a reference alone is not a change) creates no revision.
    assert put(db, 1, first["id"], reference="other")["revision"] == 1
    # Stale writer: optimistic control.
    assert put(db, 0, second["id"], status=409)["code"] == "MDL_ROUTING_CONFLICT"
    # FR-MDL-021 AC2.
    same = put(db, 1, first["id"], first["id"], status=422)
    assert same["code"] == "MDL_FALLBACK_EQUALS_PRIMARY"
    with_fallback = put(db, 1, first["id"], second["id"])
    assert with_fallback["revision"] == 2 and with_fallback["fallback"]["model_id"] == second["id"]
    # FR-MDL-021 AC3: two primary changes, every version readable, names snapshotted.
    put(db, 2, third["id"], second["id"])
    call(db, "PATCH", f"/models/{first['id']}", {"display_name": "Renamed later"})
    cleared = put(db, 3, None)
    assert cleared["effective"]["state"] == "NOT_CONFIGURED"
    history = call(db, "GET", "/routing/revisions")
    assert [item["revision"] for item in history["items"]] == [4, 3, 2, 1]
    oldest = history["items"][-1]
    assert (oldest["before_primary_model_id"], oldest["after_primary_model_id"]) == (None, first["id"])
    assert oldest["after_primary_name"] == "FIRST" and oldest["decision_reference"] == "QĐ-12/2026"
    assert history["items"][1]["before_primary_name"] == "FIRST"  # snapshot, not "Renamed later"
    assert history["items"][1]["decision_reference"] is None

    events = [c for a, c in audit_actions_all(db) if a == "mdl.routing_changed"]
    assert [event["revision"] for event in events] == [1, 2, 3, 4]
    assert events[0]["after"] == {"primary_model_id": first["id"], "fallback_model_id": None}
    assert events[0]["decision_reference"] == "QĐ-12/2026"

    # Append-only for the runtime login: no UPDATE or DELETE on history.
    with connect(db.runtime) as connection:
        for statement in (
            "UPDATE mdl_routing_revisions SET decision_reference = 'x'",
            "DELETE FROM mdl_routing_revisions",
            "DELETE FROM mdl_routing",
        ):
            with pytest.raises(Exception) as denied:
                connection.execute(statement)
            assert "permission denied" in str(denied.value)
            connection.rollback()


def audit_actions_all(db):
    with connect(db.owner) as connection:
        return connection.execute(
            "SELECT action, changes FROM audit_events WHERE action LIKE 'mdl.routing%%'"
            " ORDER BY occurred_at, id"
        ).fetchall()


def test_audit_failure_rolls_back_routing(m5):
    db = m5
    model = ready_model(db, "solo")
    with connect(db.owner) as connection:
        connection.execute(
            sql.SQL("REVOKE INSERT ON audit_events FROM {}").format(sql.Identifier(db.roles.runtime))
        )
    response = send(db.manager, "PUT", mdl_path("/routing"),
                    {"expected_revision": 0, "primary_model_id": model["id"]})
    db.seen.bodies.append(response.text)
    assert response.status_code == 500
    with connect(db.owner) as connection:
        for table in ("mdl_routing", "mdl_routing_revisions"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


# ------------------------------------- persistence vs permission to use (D5, D9)


def test_route_persists_but_unusable_slots_fail_closed(m5):
    db = m5
    primary, fallback, spare = (ready_model(db, name) for name in ("prim", "fall", "spare"))
    put(db, 0, primary["id"], fallback["id"])

    # A failed retest of the primary: the route is kept (no automatic change) ...
    db.provider.mode = "auth"
    run_test(db, primary["id"])
    db.provider.mode = "ok"
    state = routing(db)
    assert state["revision"] == 1 and state["primary"]["model_id"] == primary["id"]
    # ... but the primary may no longer be used; the usable fallback takes over.
    assert (state["primary"]["usable"], state["primary"]["issues"]) == (False, ["test_failed"])
    assert state["effective"] == {"state": "FALLBACK", "model_id": fallback["id"]}

    # Unchanged slot persists: the fallback can be replaced while the primary stays.
    changed = put(db, 1, primary["id"], spare["id"])
    assert changed["revision"] == 2 and not changed["primary"]["usable"]
    # A new value is always validated: the failed model cannot move to another slot.
    refused = put(db, 2, spare["id"], primary["id"], status=409)
    assert refused["details"]["reasons"] == ["fallback.test_failed"]

    # A passing retest restores use without any routing change.
    run_test(db, primary["id"])
    assert routing(db)["effective"] == {"state": "PRIMARY", "model_id": primary["id"]}

    # A configuration change (endpoint path) makes both slots' tests outdated: nothing usable.
    call(db, "PATCH", f"/providers/{db.local['id']}", {"endpoint": db.provider.url("/v2")})
    state = routing(db)
    assert state["primary"]["issues"] == ["test_outdated"] == state["fallback"]["issues"]
    assert state["effective"] == {"state": "UNAVAILABLE", "model_id": None}
    assert state["revision"] == 2 and len(revision_rows(db)) == 2


def test_agreement_withdrawal_fails_closed_and_keeps_history(m5):
    db = m5
    provider, agreement, model = external_ready(db)
    backup = ready_model(db, "backup")
    assert issues(db, model["id"]) == []
    put(db, 0, model["id"], backup["id"], reference="QĐ-01")

    withdrawn = call(db, "POST", f"/providers/{provider['id']}/agreements/{agreement['id']}/withdraw")
    assert withdrawn["affected_routing"] == ["routing.primary"]
    state = routing(db)
    assert state["revision"] == 1 and state["primary"]["model_id"] == model["id"]
    assert (state["primary"]["usable"], state["primary"]["issues"]) == (False, ["dpa_missing"])
    assert state["effective"] == {"state": "FALLBACK", "model_id": backup["id"]}
    # It cannot be newly selected anywhere either.
    assert put(db, 1, backup["id"], model["id"], status=409)["details"]["reasons"] == [
        "fallback.dpa_missing"
    ]
    # A new agreement restores use; history was never rewritten.
    call(db, "POST", f"/providers/{provider['id']}/agreements",
         {"basis": "SCHOOL_WRITTEN_AUTHORIZATION", "document_number": "CV-99"}, 201)
    assert routing(db)["effective"] == {"state": "PRIMARY", "model_id": model["id"]}
    assert len(revision_rows(db)) == 1


def test_deactivation_guards_follow_routing(m5):
    db = m5
    first, second = ready_model(db, "one"), ready_model(db, "two")
    put(db, 0, first["id"], second["id"])
    for path, used in (
        (f"/models/{first['id']}/deactivate", ["routing.primary"]),
        (f"/models/{second['id']}/deactivate", ["routing.fallback"]),
        (f"/providers/{db.local['id']}/deactivate", ["routing.primary", "routing.fallback"]),
    ):
        refused = call(db, "POST", path, None, 409)
        assert (refused["code"], refused["details"]["used_in"]) == ("MDL_MODEL_IN_USE", used)
    # FR-MDL-012 AC2: after switching, the old primary can be deactivated.
    put(db, 1, second["id"])
    assert call(db, "POST", f"/models/{first['id']}/deactivate")["active"] is False
    assert issues(db, first["id"]) == ["model_inactive"]


# ------------------------------------------------------------------------ races


def race(db, *requests):
    """Send the given (method, path, body) requests at the same moment."""
    barrier = Barrier(len(requests))
    headers = csrf_headers(db.manager)
    cookies = dict(db.manager.cookies)

    def attempt(request):
        method, path, body = request
        with client(db) as browser:
            browser.cookies.update(cookies)
            barrier.wait()
            response = browser.request(method, "/api/v1/mdl" + path, json=body, headers=headers)
            db.seen.bodies.append(response.text)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(attempt, requests))


def test_concurrent_writers_serialize(m5):
    db = m5
    models = [ready_model(db, f"race{i}") for i in range(3)]
    expected = 0
    for round_ in range(4):  # repeated: includes the very first configuration (no row yet)
        a, b = models[round_ % 3], models[(round_ + 1) % 3]
        results = race(
            db,
            ("PUT", "/routing", {"expected_revision": expected, "primary_model_id": a["id"]}),
            ("PUT", "/routing", {"expected_revision": expected, "primary_model_id": b["id"]}),
        )
        statuses = sorted(status for status, _ in results)
        if statuses == [200, 409]:
            loser = next(body for status, body in results if status == 409)
            assert loser["code"] == "MDL_ROUTING_CONFLICT"
            expected += 1
        else:  # the same value as now for one of them: a no-op is also 200
            assert statuses == [200, 200]
            expected = routing(db)["revision"]
        assert routing(db)["revision"] == expected == len(revision_rows(db))


def test_selection_and_deactivation_never_leave_an_inactive_route(m5):
    db = m5
    for round_ in range(4):
        candidate = ready_model(db, f"cand{round_}")
        revision = routing(db)["revision"]
        (put_status, put_body), (off_status, off_body) = race(
            db,
            ("PUT", "/routing", {"expected_revision": revision, "primary_model_id": candidate["id"]}),
            ("POST", f"/models/{candidate['id']}/deactivate", None),
        )
        if put_status == 200:
            assert (off_status, off_body["code"]) == (409, "MDL_MODEL_IN_USE")
            put(db, revision + 1, None)  # clear for the next round
        else:
            assert (put_status, off_status) == (409, 200)
            assert put_body["details"]["reasons"] == ["primary.model_inactive"]
        state = routing(db)
        assert state["primary"] is None or state["primary"]["usable"]


def test_rotation_during_selection_is_never_lost(m5):
    db = m5
    for round_ in range(3):
        candidate = ready_model(db, f"rot{round_}")
        revision = routing(db)["revision"]
        results = race(
            db,
            ("PUT", "/routing", {"expected_revision": revision, "primary_model_id": candidate["id"]}),
            ("PATCH", f"/providers/{db.local['id']}", {"secret": f"{ROTATED}-{round_}"}),
        )
        assert results[1][0] == 200
        if results[0][0] == 200:  # selected first, rotated afterwards: not usable now
            assert routing(db)["primary"]["issues"] == ["test_outdated"]
            put(db, revision + 1, None)
        else:  # rotated first: the selection saw the outdated test
            assert results[0][1]["details"]["reasons"] == ["primary.test_outdated"]


# --------------------------------------------- M3/M4 review fixes made during M5


def test_registration_refuses_credentials_without_tls_and_unusable_hosts(m5):
    db = m5
    plain = {"name": "Plain", "provider_type": "INTERNAL", "endpoint": "http://ollama:11434/v1"}
    for scheme in ({"auth_scheme": "BEARER", "secret": "x"},
                   {"auth_scheme": "HEADER_KEY", "auth_header_name": "X-Key", "secret": "x"}):
        assert call(db, "POST", "/providers", plain | scheme, 422)["code"] == "MDL_ENDPOINT_BLOCKED"
    assert call(db, "POST", "/providers", plain | {"auth_scheme": "NONE"}, 201)
    # An https provider with a secret cannot be moved to plain http.
    moved = call(db, "PATCH", f"/providers/{db.local['id']}",
                 {"endpoint": "http://127.0.0.1:1/v1", "secret": "y"}, 422)
    assert moved["code"] == "MDL_ENDPOINT_BLOCKED"
    for endpoint in ("https://exämple.test/v1", "https://2130706433/v1", "https://8.8.8.8/v1",
                     "https://api.vendor-a.test:8443/v1", "https://localhost/v1"):
        assert call(db, "POST", "/providers", EXTERNAL | {"name": endpoint, "endpoint": endpoint},
                    422)["code"] == "MDL_ENDPOINT_BLOCKED", endpoint
    unicode_internal = {"name": "Uni", "provider_type": "INTERNAL", "auth_scheme": "NONE",
                        "endpoint": "http://mô-hình:8000/v1"}
    assert call(db, "POST", "/providers", unicode_internal, 422)["code"] == "MDL_ENDPOINT_BLOCKED"


def test_institution_wide_test_cap_holds_across_workers(m5):
    db = m5
    target = add_model(db, db.local["id"], "capped")
    others = [add_model(db, db.local["id"], f"busy{i}") for i in range(testing.MAX_RUNNING_PER_INSTITUTION)]
    with connect(db.owner) as connection:
        for other in others:  # tests in flight in other API workers or processes
            connection.execute(
                "INSERT INTO mdl_connection_tests (institution_id, model_id, connection_version,"
                " credential_version, started_by) VALUES (%s, %s, 1, 1, %s)",
                (db.tenant, other["id"], db.manager_id),
            )
        connection.commit()
    assert run_test(db, target["id"], 429)["code"] == "RATE_LIMITED"
    assert db.provider.requests == []
    with connect(db.owner) as connection:  # one of them finishes (or expires)
        connection.execute(
            "UPDATE mdl_connection_tests SET started_at = now() - interval '10 minutes'"
            " WHERE model_id = %s", (others[0]["id"],),
        )
        connection.commit()
    assert run_test(db, target["id"])["status"] == "PASSED"


def test_charge_acknowledgement_is_audited(m5, monkeypatch):
    db = m5
    monkeypatch.setattr(egress, "resolve", lambda *a: [ipaddress.ip_address("127.0.0.1")])
    provider, _, model = external_ready(db, "Billed")
    result = run_test(db, model["id"], 201, {"acknowledge_provider_charges": True})
    assert result["error_code"] == "ENDPOINT_BLOCKED"  # loopback is never external
    events = [c for a, c in audit_actions(db, model["id"]) if a == "mdl.model_connection_tested"]
    assert events[-1]["charges_acknowledged"] is True
    local = ready_model(db, "free")
    events = [c for a, c in audit_actions(db, local["id"]) if a == "mdl.model_connection_tested"]
    assert events[-1]["charges_acknowledged"] is False


def test_rewrap_moves_credentials_to_the_active_key_without_outdating_tests(m5):
    db = m5
    model = ready_model(db, "keyed")
    put(db, 0, model["id"])
    new_key = base64.b64encode(os.urandom(32)).decode()
    ring = KeyRing.parse(f"k1:{KEY},k2:{new_key}", "k2")
    result = rewrap_all(ring, db.runtime_factory.begin)
    assert (result.rewrapped, result.current, result.unreadable) == (1, 0, 0)
    assert rewrap_all(ring, db.runtime_factory.begin).current == 1  # idempotent
    with connect(db.owner) as connection:
        assert connection.execute("SELECT key_id, credential_version FROM mdl_provider_credentials"
                                  ).fetchall() == [("k2", 1)]
        event = connection.execute(
            "SELECT actor_id, changes FROM audit_events WHERE action = 'mdl.credential_rewrapped'"
        ).fetchone()
    assert event[0] is None and event[1] == {
        "key_id_before": "k1", "key_id_after": "k2", "credential_version": 1,
    }
    # Retire k1: the secret still opens, the test stays current, the route stays usable.
    set_settings(db, mdl_credential_keys=SecretStr(f"k2:{new_key}"),
                 mdl_credential_active_key_id="k2")
    assert routing(db)["effective"] == {"state": "PRIMARY", "model_id": model["id"]}
    retest = run_test(db, model["id"])
    assert retest["status"] == "PASSED" and retest["credential_version"] == 1
    assert db.provider.requests[-1]["headers"]["authorization"] == f"Bearer {SECRET}"
    assert len(stored_tests(db, model["id"])) == 2
    assert SECRET not in json.dumps(event[1])


# ----------------------------------------------------------------------- migration


def test_populated_m4_database_upgrades_to_0006():
    """0005 database with a provider, model, routing row and revision -> migrate -> 0006."""
    with disposable_database() as (admin, roles, owner, runtime):
        alembic(admin, "upgrade", "0005_mdl_agreement_withdrawals")
        institution, unit, user, provider, model = (uuid4() for _ in range(5))
        with connect(admin) as connection:
            connection.execute("INSERT INTO institutions (id, code, name) VALUES (%s, 'M4', 'M4')",
                               (institution,))
            connection.execute("INSERT INTO units (id, institution_id, code, name)"
                               " VALUES (%s, %s, 'u', 'U')", (unit, institution))
            connection.execute(
                "INSERT INTO users (id, institution_id, primary_unit_id, username, display_name,"
                " code_type, institutional_code) VALUES (%s, %s, %s, 'm4', 'M4', 'STAFF', '1')",
                (user, institution, unit),
            )
            connection.execute(
                "INSERT INTO mdl_providers (id, institution_id, name, provider_type, api_style,"
                " endpoint, auth_scheme) VALUES (%s, %s, 'P', 'INTERNAL', 'OPENAI_COMPATIBLE',"
                " 'http://ollama:11434/v1', 'NONE')", (provider, institution),
            )
            connection.execute(
                "INSERT INTO mdl_models (id, institution_id, provider_id, technical_id,"
                " display_name, supports_text, risk_level) VALUES (%s, %s, %s, 'm', 'M', true,"
                " 'LOW')", (model, institution, provider),
            )
            connection.execute(
                "INSERT INTO mdl_routing (institution_id, primary_model_id, revision, updated_by)"
                " VALUES (%s, %s, 1, %s)", (institution, model, user),
            )
            connection.execute(
                "INSERT INTO mdl_routing_revisions (institution_id, revision,"
                " after_primary_model_id, after_primary_name, changed_by)"
                " VALUES (%s, 1, %s, 'M', %s)", (institution, model, user),
            )
        prepare(admin, roles)
        migrate(owner, roles)
        alembic(owner, "check")
        migrate(owner, roles)  # second run is a no-op
        with connect(runtime) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
                REQUIRED_SCHEMA_REVISION,
            )
            assert connection.execute(
                "SELECT revision, after_primary_name, decision_reference FROM mdl_routing_revisions"
            ).fetchall() == [(1, "M", None)]
            assert connection.execute("SELECT primary_model_id FROM mdl_routing").fetchone() == (
                model,
            )
            # Runtime grant covers the new column (INSERT only) and the widened API style.
            connection.execute(
                "INSERT INTO mdl_routing_revisions (institution_id, revision,"
                " before_primary_model_id, before_primary_name, decision_reference, changed_by)"
                " VALUES (%s, 2, %s, 'M', 'QĐ-2', %s)", (institution, model, user),
            )
            connection.execute("UPDATE mdl_providers SET api_style = 'OPENAI_COMPATIBLE_V2'")
            for statement in (
                "UPDATE mdl_routing_revisions SET decision_reference = 'x'",
                "INSERT INTO mdl_routing_revisions (institution_id, revision, decision_reference,"
                " changed_by) SELECT institution_id, 3, ' padded', changed_by"
                " FROM mdl_routing_revisions LIMIT 1",
            ):
                with pytest.raises((InsufficientPrivilege, CheckViolation)):
                    with connection.transaction():
                        connection.execute(statement)
