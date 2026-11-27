"""M4 against PostgreSQL: the real connection test through the routes.

Requests run as the restricted runtime login with session, Origin and CSRF. The
"provider" is a local HTTP server on 127.0.0.1 started by the test, reached because the
test configures the operator allowlist (``127.0.0.1/32:<port>``) and trusts the test CA
(``AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE``) exactly as an operator would (``fake_provider``).
External providers are exercised up to the egress policy with a simulated resolver; no
request leaves the machine and no provider charge can occur.

Evidence label: controlled-server tests prove wire format, transaction shape and the
quota-free path. They are NOT genuine provider verification (FR-MDL-020 AC1 still needs
a recorded live run with a PO/TL-supplied provider).
"""

import ipaddress
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import SecretStr

from aq_uai_api.mdl import egress, testing
from aq_uai_api.mdl.adapters.openai_compatible import probe_body

from .fake_provider import LocalProvider, ProviderPki
from .test_m3_mdl_api import (
    EXTERNAL,
    KEY,
    ROTATED,
    SECRET,
    audit_actions,
    call,
    mdl_path,
)
from .test_m3_mdl_api import mdl as mdl
from .test_wp2_database import connect
from .test_wp3_auth import ORIGIN_HEADER, client, csrf_headers
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import directory as directory
from .test_wp5_directory import expect, get, pytestmark, send

pytestmark = pytestmark
PKI = None


def pki():
    global PKI
    if PKI is None:
        PKI = ProviderPki()
    return PKI


@pytest.fixture
def m4(mdl, monkeypatch):
    db = mdl
    monkeypatch.setattr(testing, "COOLDOWN_SECONDS", 0)
    db.provider = LocalProvider(pki())
    # The mdl fixture's settings override reads db.settings on every request. Operator
    # configuration: this one loopback port, and the private CA of the test server.
    set_settings(
        db,
        mdl_egress_internal_allowlist=db.provider.allowlist,
        mdl_egress_internal_ca_file=str(pki().ca_file),
    )
    try:
        yield db
    finally:
        db.provider.close()


def set_settings(db, **changes):
    db.settings = db.settings.model_copy(update=changes)


def local_provider(db, name="Local", scheme="BEARER", **extra):
    body = {
        "name": name,
        "provider_type": "INTERNAL",
        "endpoint": db.provider.url(),
        "auth_scheme": scheme,
    }
    if scheme != "NONE":
        body["secret"] = SECRET
    return call(db, "POST", "/providers", body | extra, 201)


def add_model(db, provider_id, technical_id="local-model", capabilities=("TEXT",)):
    return call(
        db,
        "POST",
        "/models",
        {
            "provider_id": provider_id,
            "technical_id": technical_id,
            "display_name": technical_id.upper(),
            "capabilities": list(capabilities),
        },
        201,
    )


def run_test(db, model_id, status=201, body=None):
    return call(db, "POST", f"/models/{model_id}/connection-tests", body, status)


def stored_tests(db, model_id):
    with connect(db.owner) as connection:
        return connection.execute(
            "SELECT status, error_code, http_status_class, connection_version,"
            " credential_version FROM mdl_connection_tests WHERE model_id = %s"
            " ORDER BY started_at, id",
            (model_id,),
        ).fetchall()


def test_routes_require_mdl_rights_and_make_no_call_without_them(m4):
    db = m4
    model = add_model(db, local_provider(db)["id"])
    path = f"/models/{model['id']}/connection-tests"
    with client(db) as anonymous:
        assert anonymous.get("/api/v1/mdl" + path).status_code == 401
        assert anonymous.post("/api/v1/mdl" + path, headers=ORIGIN_HEADER).status_code == 401
    # The FOUNDATION_ADMIN has no MDL authority (D7).
    assert get(db.admin, mdl_path(path)).status_code == 403
    assert send(db.admin, "POST", mdl_path(path)).status_code == 403
    # Without CSRF proof the MDL administrator is refused too.
    assert db.manager.post("/api/v1/mdl" + path).status_code in (401, 403)
    assert db.provider.requests == [] and stored_tests(db, model["id"]) == []
    assert call(db, "GET", path)["items"] == []


def test_lifecycle_blank_secret_rotation_and_failure(m4, caplog):
    caplog.set_level(logging.DEBUG)
    db = m4
    provider = local_provider(db)
    model = add_model(db, provider["id"])
    assert model["connection_test"] == {
        "result": "NOT_TESTED", "test_id": None, "error_code": None,
        "finished_at": None, "running": False,
    }

    first = run_test(db, model["id"])
    assert first["status"] == "PASSED" and first["error_code"] is None
    assert first["http_status_class"] == 2 and first["latency_ms"] >= 0
    assert first["current"] and first["finished_at"] is not None
    assert (first["connection_version"], first["credential_version"]) == (1, 1)
    sent = db.provider.requests[-1]
    # FR-MDL-020: fixed request, no institutional data; the stored secret is sent.
    assert sent["path"] == "/v1/chat/completions"
    assert sent["body"] == probe_body("local-model")
    assert sent["headers"]["authorization"] == f"Bearer {SECRET}"
    state = call(db, "GET", f"/models/{model['id']}")["connection_test"]
    assert (state["result"], state["test_id"]) == ("PASSED", first["id"])

    # FR-MDL-010 AC2: blank secret on edit keeps the connection (checked by a real test).
    call(db, "PATCH", f"/providers/{provider['id']}", {"name": "Local renamed", "secret": ""})
    second = run_test(db, model["id"])
    assert second["status"] == "PASSED" and second["credential_version"] == 1
    assert db.provider.requests[-1]["headers"]["authorization"] == f"Bearer {SECRET}"

    # Rotation makes earlier results outdated; the next test uses the new secret.
    call(db, "PATCH", f"/providers/{provider['id']}", {"secret": ROTATED})
    assert call(db, "GET", f"/models/{model['id']}")["connection_test"]["result"] == "OUTDATED"
    assert not any(item["current"] for item in call(db, "GET", f"/models/{model['id']}/connection-tests")["items"])
    third = run_test(db, model["id"])
    assert third["status"] == "PASSED" and third["credential_version"] == 2
    assert db.provider.requests[-1]["headers"]["authorization"] == f"Bearer {ROTATED}"

    # FR-MDL-020 AC2 groundwork: a failed latest test leaves the model FAILED.
    db.provider.mode = "auth"
    failed = run_test(db, model["id"])
    assert (failed["status"], failed["error_code"], failed["http_status_class"]) == (
        "FAILED", "AUTH_FAILED", 4,
    )
    state = call(db, "GET", f"/models/{model['id']}")["connection_test"]
    assert (state["result"], state["error_code"]) == ("FAILED", "AUTH_FAILED")

    history = call(db, "GET", f"/models/{model['id']}/connection-tests")
    assert [item["id"] for item in history["items"]] == [
        failed["id"], third["id"], second["id"], first["id"],
    ]
    tested = [changes for action, changes in audit_actions(db, model["id"])
              if action == "mdl.model_connection_tested"]
    assert [event["status"] for event in tested] == ["PASSED", "PASSED", "PASSED", "FAILED"]
    assert tested[-1]["error_code"] == "AUTH_FAILED" and tested[-1]["test_id"] == failed["id"]
    for text in (SECRET, ROTATED, KEY, "bad key"):  # nor the provider's error text
        assert text not in caplog.text and text not in json.dumps(tested)


@pytest.mark.parametrize(
    ("mode", "code", "status_class"),
    [
        ("missing", "MODEL_NOT_FOUND", 4),
        ("bad", "BAD_RESPONSE", 2),
        ("server", "PROVIDER_ERROR", 5),
        ("redirect", "REDIRECT_REFUSED", 3),
    ],
)
def test_failure_classes_are_recorded_without_provider_text(m4, mode, code, status_class):
    db = m4
    db.provider.mode = mode
    model = add_model(db, local_provider(db, scheme="NONE")["id"])
    result = run_test(db, model["id"])
    assert (result["status"], result["error_code"], result["http_status_class"]) == (
        "FAILED", code, status_class,
    )
    assert len(db.provider.requests) == 1  # one attempt, no retry, no redirect follow
    assert "authorization" not in db.provider.requests[0]["headers"]  # NONE sends no secret


def test_egress_policy_failures_are_recorded(m4, monkeypatch):
    db = m4
    model = add_model(db, local_provider(db, scheme="NONE")["id"])
    # Operator removes the allowlist: the internal destination is refused, no request.
    set_settings(db, mdl_egress_internal_allowlist="")
    blocked = run_test(db, model["id"])
    assert (blocked["status"], blocked["error_code"]) == ("FAILED", "ENDPOINT_BLOCKED")
    assert call(db, "GET", "/status")["egress"]["internal_allowlist"] == "EMPTY"
    set_settings(db, mdl_egress_internal_allowlist="169.254.0.0/16")
    assert run_test(db, model["id"])["error_code"] == "ENDPOINT_BLOCKED"
    assert call(db, "GET", "/status")["egress"]["internal_allowlist"] == "INVALID"
    assert db.provider.requests == []

    # Unreachable port on an allowed host: a network failure, recorded.
    set_settings(db, mdl_egress_internal_allowlist=db.provider.allowlist + ",127.0.0.1/32:9")
    status = call(db, "GET", "/status")["egress"]
    assert (status["internal_allowlist"], status["internal_allowlist_entries"]) == ("CONFIGURED", 2)
    dead = add_model(db, local_provider(db, name="Dead", scheme="NONE", endpoint="http://127.0.0.1:9/v1")["id"])
    assert run_test(db, dead["id"])["error_code"] == "NETWORK_ERROR"


def test_gates_refuse_before_any_network_activity(m4, monkeypatch):
    db = m4
    lookups = []

    def hostile_dns(host, port, timeout):
        lookups.append(host)
        return [ipaddress.ip_address("127.0.0.1")]  # rebinding to loopback

    monkeypatch.setattr(egress, "resolve", hostile_dns)
    external = call(db, "POST", "/providers", EXTERNAL, 201)
    model = add_model(db, external["id"], "ext-model")
    path = f"/models/{model['id']}/connection-tests"

    # FR-MDL-030 AC1: no agreement, no test.
    assert run_test(db, model["id"], 409)["code"] == "MDL_DPA_REQUIRED"
    agreement = call(
        db, "POST", f"/providers/{external['id']}/agreements",
        {"basis": "NO_TRAINING_COMMITMENT", "document_number": "HD-2026/01"}, 201,
    )
    # D4: the cost notice must be acknowledged, strictly as a boolean.
    assert run_test(db, model["id"], 422)["code"] == "MDL_CHARGES_NOT_ACKNOWLEDGED"
    for invalid in ({"acknowledge_provider_charges": "true"}, {"prompt": "x"}):
        assert run_test(db, model["id"], 422, invalid)["code"] == "VALIDATION_FAILED"
    assert lookups == [] and stored_tests(db, model["id"]) == []

    # FR-MDL-030 AC2: with the agreement the test runs, and the egress policy refuses
    # a public name resolving to loopback even though loopback is on the internal list.
    ack = {"acknowledge_provider_charges": True}
    result = run_test(db, model["id"], 201, ack)
    assert (result["status"], result["error_code"]) == ("FAILED", "ENDPOINT_BLOCKED")
    assert lookups == ["api.vendor-a.test"] and db.provider.requests == []

    # Withdrawal invalidates future tests (D5).
    call(db, "POST", f"/providers/{external['id']}/agreements/{agreement['id']}/withdraw")
    assert run_test(db, model["id"], 409, ack)["code"] == "MDL_DPA_REQUIRED"

    # D3: image/voice-only models are registrable but not testable.
    local = local_provider(db)
    image = add_model(db, local["id"], "img", ("IMAGE", "VOICE"))
    assert run_test(db, image["id"], 409)["code"] == "MDL_TEST_UNSUPPORTED"
    assert image["connection_test"]["result"] == "UNSUPPORTED"

    # Inactive model or provider.
    text = add_model(db, local["id"], "txt")
    call(db, "POST", f"/models/{text['id']}/deactivate")
    assert run_test(db, text["id"], 409)["code"] == "MDL_NOT_ELIGIBLE"
    call(db, "POST", f"/models/{text['id']}/activate")
    call(db, "POST", f"/providers/{local['id']}/deactivate")
    assert run_test(db, text["id"], 409)["code"] == "MDL_NOT_ELIGIBLE"
    call(db, "POST", f"/providers/{local['id']}/activate")

    # Key ring missing, then a tampered ciphertext: 503, nothing sent.
    set_settings(db, mdl_credential_keys=SecretStr(""))
    assert run_test(db, text["id"], 503)["code"] == "MDL_CREDENTIAL_UNAVAILABLE"
    set_settings(db, mdl_credential_keys=SecretStr(f"k1:{KEY}"))
    with connect(db.owner) as connection:
        connection.execute(
            "UPDATE mdl_provider_credentials SET ciphertext = set_byte(ciphertext, 0,"
            " get_byte(ciphertext, 0) # 1) WHERE provider_id = %s",
            (local["id"],),
        )
        connection.commit()
    assert run_test(db, text["id"], 503)["code"] == "MDL_CREDENTIAL_UNAVAILABLE"
    assert call(db, "POST", "/models/00000000-0000-0000-0000-000000000000/connection-tests",
                None, 404)["code"] == "NOT_FOUND"
    assert db.provider.requests == [] and stored_tests(db, text["id"]) == []
    assert call(db, "GET", path)["total"] == 1


def in_flight(db, model_id):
    """Start a test in a worker thread and return once the provider holds the request."""
    db.provider.gate = threading.Event()
    db.provider.entered.clear()
    headers = csrf_headers(db.manager)
    cookies = dict(db.manager.cookies)

    def attempt():
        with client(db) as browser:
            browser.cookies.update(cookies)
            response = browser.post(
                f"/api/v1/mdl/models/{model_id}/connection-tests", headers=headers
            )
            db.seen.bodies.append(response.text)
            return response.status_code, response.json()

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(attempt)
    assert db.provider.entered.wait(10)
    return pool, future


def test_network_call_holds_no_transaction_and_stale_results_are_discarded(m4):
    db = m4
    provider = local_provider(db)
    model = add_model(db, provider["id"])
    pool, future = in_flight(db, model["id"])
    try:
        runtime_user = db.runtime.username
        with connect(db.owner) as connection:
            # Transaction 1 committed: another session sees the RUNNING row ...
            assert stored_tests(db, model["id"]) == [("RUNNING", None, None, 1, 1)]
            # ... and no runtime session is inside a transaction while the call runs.
            assert connection.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = %s"
                " AND state LIKE 'idle in transaction%%'",
                (runtime_user,),
            ).fetchone() == (0,)
        assert call(db, "GET", f"/models/{model['id']}")["connection_test"]["running"]
        # One test per model.
        assert run_test(db, model["id"], 409)["code"] == "MDL_TEST_IN_PROGRESS"
        # Provider edits are not blocked by the call (no lock held during I/O) ...
        started = time.monotonic()
        call(db, "PATCH", f"/providers/{provider['id']}", {"endpoint": db.provider.url("/v2")})
        assert time.monotonic() - started < 5
    finally:
        db.provider.gate.set()
        status, result = future.result(timeout=30)
        pool.shutdown()
    # ... and the result for the old configuration is not accepted as PASSED.
    assert status == 201
    assert (result["status"], result["error_code"], result["current"]) == (
        "FAILED", "STALE_CONFIGURATION", False,
    )
    assert call(db, "GET", f"/models/{model['id']}")["connection_test"]["result"] == "OUTDATED"
    events = [c for a, c in audit_actions(db, model["id"]) if a == "mdl.model_connection_tested"]
    assert events[-1]["error_code"] == "STALE_CONFIGURATION"


def test_orphans_expire_and_lost_authority_aborts(m4):
    db = m4
    model = add_model(db, local_provider(db)["id"])
    with connect(db.owner) as connection:
        connection.execute(
            "INSERT INTO mdl_connection_tests (institution_id, model_id, connection_version,"
            " credential_version, started_by, started_at) VALUES (%s, %s, 1, 1, %s,"
            " now() - interval '10 minutes')",
            (db.tenant, model["id"], db.manager_id),
        )
        connection.commit()
    assert call(db, "GET", f"/models/{model['id']}")["connection_test"]["running"] is False
    result = run_test(db, model["id"])
    assert result["status"] == "PASSED"
    assert [row[:2] for row in stored_tests(db, model["id"])] == [
        ("FAILED", "EXPIRED"), ("PASSED", None),
    ]

    # The tester loses the role while the provider is answering: no PASSED is
    # recorded for them, the row is closed as ABORTED and the request is refused.
    pool, future = in_flight(db, model["id"])
    try:
        grants = expect(get(db.admin, f"/users/{db.manager_id}/role-assignments"), 200)["items"]
        grant = next(item for item in grants if item["role_code"] == "AI_MODEL_ADMIN")
        expect(send(db.admin, "DELETE", f"/users/{db.manager_id}/role-assignments/{grant['id']}"), 204)
    finally:
        db.provider.gate.set()
        status, body = future.result(timeout=30)
        pool.shutdown()
    assert (status, body["code"]) == (403, "FORBIDDEN")
    assert stored_tests(db, model["id"])[-1][:2] == ("FAILED", "ABORTED")
    events = [a for a, _ in audit_actions(db, model["id"]) if a == "mdl.model_connection_tested"]
    assert len(events) == 1  # only the earlier PASSED test was audited


def test_cooldown_and_process_cap(m4, monkeypatch):
    db = m4
    model = add_model(db, local_provider(db, scheme="NONE")["id"])
    monkeypatch.setattr(testing, "COOLDOWN_SECONDS", 30)
    run_test(db, model["id"])
    assert run_test(db, model["id"], 429)["code"] == "MDL_TEST_COOLDOWN"
    # A configuration change (version bump) lifts the cooldown for the new configuration.
    provider_id = model["provider_id"]
    call(db, "PATCH", f"/providers/{provider_id}", {"endpoint": db.provider.url("/v2")})
    assert run_test(db, model["id"])["connection_version"] == 2
    assert run_test(db, model["id"], 429)["code"] == "MDL_TEST_COOLDOWN"
    monkeypatch.setattr(testing, "COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(testing, "_IN_FLIGHT", threading.BoundedSemaphore(1))
    assert testing._IN_FLIGHT.acquire(blocking=False)  # another test occupies the slot
    assert run_test(db, model["id"], 429)["code"] == "RATE_LIMITED"
    testing._IN_FLIGHT.release()
    assert run_test(db, model["id"])["status"] == "PASSED"
    assert len(db.provider.requests) == 3


def test_stored_rows_hold_codes_only(m4):
    db = m4
    model = add_model(db, local_provider(db)["id"])
    run_test(db, model["id"])
    with connect(db.owner) as connection:
        row = json.loads(
            connection.execute(
                "SELECT row_to_json(t)::text FROM mdl_connection_tests t WHERE model_id = %s",
                (model["id"],),
            ).fetchone()[0]
        )
    assert set(row) == {
        "id", "institution_id", "model_id", "connection_version", "credential_version",
        "status", "error_code", "http_status_class", "latency_ms", "started_by",
        "started_at", "finished_at",
    }
    assert SECRET not in json.dumps(row)
