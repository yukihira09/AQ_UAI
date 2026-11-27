"""M3 against PostgreSQL: MDL provider, credential, agreement and model APIs.

Requests go through the real routes with session, Origin and CSRF, as the restricted
runtime login. A canary secret is used everywhere and searched for in every response
body, every audit row and the captured logs (RULE-MDL-04).
"""

import base64
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from psycopg import sql
from pydantic import SecretStr

from aq_uai_api.core.config import get_settings
from aq_uai_api.mdl.credentials import (
    CredentialBinding,
    KeyRing,
    SealedCredential,
    endpoint_origin,
)

from .test_m1_mdl_access import sign_in
from .test_wp2_database import connect
from .test_wp3_auth import ORIGIN_HEADER, client, csrf_headers
from .test_wp5_directory import (
    add_grant,
    create_group,
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
SECRET = "sk-m3-canary-9b7e2c41-never-show"
ROTATED = "sk-m3-canary-rotated-5d1a0f77"
KEY = base64.b64encode(os.urandom(32)).decode()
EXTERNAL = {
    "name": "Vendor A",
    "provider_type": "EXTERNAL",
    "endpoint": "https://API.vendor-a.test/v1/",
    "auth_scheme": "BEARER",
    "secret": SECRET,
}
INTERNAL = {
    "name": "On-prem",
    "provider_type": "INTERNAL",
    "endpoint": "http://ollama:11434/v1",
    "auth_scheme": "NONE",
}


class Recorder:
    """Keeps every response body so the canary scan covers the whole test."""

    def __init__(self):
        self.bodies = []

    def __call__(self, response, status):
        self.bodies.append(response.text)
        return expect(response, status)


@pytest.fixture
def mdl(directory):
    db = directory
    db.settings = db.settings.model_copy(
        update={
            "mdl_credential_keys": SecretStr(f"k1:{KEY}"),
            "mdl_credential_active_key_id": "k1",
        }
    )
    db.app.dependency_overrides[get_settings] = lambda: db.settings
    unit = create_unit(db.admin, "AIUNIT")
    create_user(db.admin, unit["id"], "modeladmin", active=True)
    user = expect(get(db.admin, "/users", params={"q": "modeladmin"}), 200)["items"][0]
    add_grant(db.admin, f"/users/{user['id']}", "AI_MODEL_ADMIN")
    db.manager = sign_in(db, "modeladmin")
    db.manager_id = user["id"]
    db.unit = unit["id"]
    db.seen = Recorder()
    try:
        yield db
    finally:
        db.manager.__exit__(None, None, None)
        assert_no_secret_leaked(db)


def assert_no_secret_leaked(db):
    leaked = [body for body in db.seen.bodies if SECRET in body or ROTATED in body or KEY in body]
    assert not leaked
    with connect(db.owner) as connection:
        rows = connection.execute("SELECT row_to_json(a)::text FROM audit_events a").fetchall()
    dump = " ".join(row[0] for row in rows)
    assert SECRET not in dump and ROTATED not in dump and KEY not in dump


def mdl_path(path):
    return "/mdl" + path


def call(db, method, path, body=None, status=200, browser=None):
    browser = browser or db.manager
    if method == "GET":
        response = get(browser, mdl_path(path), params=body)
    else:
        response = send(browser, method, mdl_path(path), body)
    return db.seen(response, status)


def stored_credential(db, provider_id):
    with connect(db.owner) as connection:
        return connection.execute(
            "SELECT c.ciphertext, c.nonce, c.key_id, c.credential_version, p.endpoint,"
            " p.institution_id FROM mdl_provider_credentials c"
            " JOIN mdl_providers p ON p.id = c.provider_id WHERE c.provider_id = %s",
            (provider_id,),
        ).fetchone()


def open_stored(db, provider_id, keys=None):
    ciphertext, nonce, key_id, version, endpoint, tenant = stored_credential(db, provider_id)
    keys = keys or KeyRing.parse(f"k1:{KEY}", "k1")
    binding = CredentialBinding(tenant, provider_id, endpoint_origin(endpoint), version)
    sealed = SealedCredential(bytes(ciphertext), bytes(nonce), key_id)
    return keys.open(sealed, binding).get_secret_value(), version


def audit_actions(db, target_id):
    with connect(db.owner) as connection:
        return [
            (action, changes)
            for action, changes in connection.execute(
                "SELECT action, changes FROM audit_events WHERE target_id = %s"
                " ORDER BY occurred_at, id",
                (target_id,),
            ).fetchall()
        ]


ROUTES = [
    ("GET", "/status", None),
    ("GET", "/providers", None),
    ("POST", "/providers", INTERNAL),
    ("GET", "/providers/{p}", None),
    ("PATCH", "/providers/{p}", {"name": "Renamed"}),
    ("POST", "/providers/{p}/deactivate", None),
    ("POST", "/providers/{p}/activate", None),
    ("GET", "/providers/{p}/agreements", None),
    ("POST", "/providers/{p}/agreements", {"basis": "NO_TRAINING_COMMITMENT", "document_number": "X"}),
    ("POST", "/providers/{p}/agreements/{a}/withdraw", None),
    ("GET", "/models", None),
    ("POST", "/models", {"provider_id": "{p}", "technical_id": "x", "display_name": "X", "capabilities": ["TEXT"]}),
    ("GET", "/models/{m}", None),
    ("PATCH", "/models/{m}", {"display_name": "Y"}),
    ("POST", "/models/{m}/deactivate", None),
    ("POST", "/models/{m}/activate", None),
]


def fill(value, ids):
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {key: fill(item, ids) for key, item in value.items()}
    return value


def test_authorization_matrix_and_empty_lists(mdl):
    db = mdl
    # 001-AC2: an authorized account sees the (empty) lists.
    for path in ("/providers", "/models"):
        assert call(db, "GET", path)["items"] == []
    status = call(db, "GET", "/status")
    assert (status["credential_keys"], status["active_key_id"]) == ("AVAILABLE", "k1")

    external = call(db, "POST", "/providers", EXTERNAL, 201)
    agreement = call(
        db,
        "POST",
        f"/providers/{external['id']}/agreements",
        {"basis": "NO_TRAINING_COMMITMENT", "document_number": "HD-01"},
        201,
    )
    model = call(
        db,
        "POST",
        "/models",
        {"provider_id": external["id"], "technical_id": "m-1", "display_name": "M1", "capabilities": ["TEXT"]},
        201,
    )
    ids = {"p": external["id"], "a": agreement["id"], "m": model["id"]}

    # A group member of an AI_SPECIALIST group and a FOUNDATION_ADMIN have no MDL rights.
    create_user(db.admin, db.unit, "specialist", active=True)
    specialist_id = expect(get(db.admin, "/users", params={"q": "specialist"}), 200)["items"][0]["id"]
    group = create_group(db.admin, "AI_SPECIALIST")
    membership = send(db.admin, "PUT", f"/groups/{group['id']}/members/{specialist_id}")
    assert membership.status_code in (200, 201)
    specialist = sign_in(db, "specialist")
    try:
        for method, path, body in ROUTES:
            target, payload = fill(path, ids), fill(body, ids)
            with client(db) as anonymous:
                response = (
                    anonymous.get("/api/v1/mdl" + target)
                    if method == "GET"
                    else anonymous.request(
                        method, "/api/v1/mdl" + target, json=payload, headers=ORIGIN_HEADER
                    )
                )
                assert response.status_code == 401, (method, path)
            for browser in (db.admin, specialist):
                response = (
                    get(browser, mdl_path(target))
                    if method == "GET"
                    else send(browser, method, mdl_path(target), payload)
                )
                assert response.status_code == 403, (method, path, response.text)
        # Writes without CSRF proof are refused even for the MDL administrator.
        response = db.manager.request(
            "POST", "/api/v1/mdl/providers", json=INTERNAL | {"name": "No CSRF"}
        )
        assert response.status_code in (401, 403)
    finally:
        specialist.__exit__(None, None, None)

    # The MDL administrator can call every route (state routes return 200).
    for method, path, body in ROUTES:
        target, payload = fill(path, ids), fill(body, ids)
        if method == "POST" and not path.endswith("activate"):
            continue  # creates and withdrawal are one-shot; covered by the other tests
        call(db, method, target, payload, 200)


def test_provider_credentials_follow_the_secret_rules(mdl, caplog):
    caplog.set_level(logging.DEBUG)
    db = mdl
    created = call(db, "POST", "/providers", EXTERNAL, 201)
    pid = created["id"]
    assert created["endpoint"] == "https://api.vendor-a.test/v1"  # canonical form
    assert created["has_credential"] and created["credential_status"] == "STORED"
    assert created["connection_version"] == 1 and created["agreement_in_force"] is None
    assert "secret" not in created and SECRET not in json.dumps(created)
    assert open_stored(db, pid) == (SECRET, 1)

    # FR-MDL-010 AC2: blank secret on edit keeps the stored value unchanged.
    before = stored_credential(db, pid)
    edited = call(db, "PATCH", f"/providers/{pid}", {"name": "Vendor A2", "secret": ""})
    assert edited["name"] == "Vendor A2" and edited["connection_version"] == 1
    assert stored_credential(db, pid) == before
    # Same origin, new path: connection changes, the secret stays valid.
    moved = call(db, "PATCH", f"/providers/{pid}", {"endpoint": "https://api.vendor-a.test/v2"})
    assert moved["connection_version"] == 2 and open_stored(db, pid) == (SECRET, 1)
    # A new origin needs the secret again: a stored secret is never redirected.
    redirect = {"endpoint": "https://other-host.test/v1"}
    assert call(db, "PATCH", f"/providers/{pid}", redirect, 422)["code"] == "MDL_CREDENTIAL_REQUIRED"
    rotated = call(db, "PATCH", f"/providers/{pid}", redirect | {"secret": ROTATED})
    assert rotated["connection_version"] == 3 and open_stored(db, pid) == (ROTATED, 2)
    # Rotation alone bumps only the credential version.
    call(db, "PATCH", f"/providers/{pid}", {"secret": SECRET})
    assert open_stored(db, pid) == (SECRET, 3)
    assert call(db, "GET", f"/providers/{pid}")["connection_version"] == 3
    # HEADER_KEY needs a header name and (being a scheme change) a new secret.
    header = {"auth_scheme": "HEADER_KEY", "auth_header_name": "X-Api-Key"}
    assert call(db, "PATCH", f"/providers/{pid}", header, 422)["code"] == "MDL_CREDENTIAL_REQUIRED"
    call(db, "PATCH", f"/providers/{pid}", {"auth_scheme": "HEADER_KEY"}, 422)
    call(db, "PATCH", f"/providers/{pid}", header | {"auth_header_name": "Host", "secret": "x"}, 422)
    keyed = call(db, "PATCH", f"/providers/{pid}", header | {"secret": ROTATED})
    assert keyed["auth_header_name"] == "X-Api-Key" and open_stored(db, pid) == (ROTATED, 4)

    for invalid, code in (
        ({"provider_type": "INTERNAL"}, "VALIDATION_FAILED"),  # immutable
        ({"prompt": "You are..."}, "VALIDATION_FAILED"),  # FR-MDL-040
        ({"temperature": 0.7}, "VALIDATION_FAILED"),
        ({"endpoint": "http://api.vendor-a.test/v1"}, "MDL_ENDPOINT_BLOCKED"),  # external: https
        ({"endpoint": "https://user:pw@api.vendor-a.test"}, "VALIDATION_FAILED"),
        ({"endpoint": "https://api.vendor-a.test/v1?key=x"}, "VALIDATION_FAILED"),
        ({"name": None}, "VALIDATION_FAILED"),
        ({}, "VALIDATION_FAILED"),
        ({"secret": "line\nbreak"}, "VALIDATION_FAILED"),
    ):
        assert call(db, "PATCH", f"/providers/{pid}", invalid, 422)["code"] == code, invalid

    # Creation rules.
    for invalid, status, code in (
        (EXTERNAL | {"secret": None, "name": "No secret"}, 422, "MDL_CREDENTIAL_REQUIRED"),
        (EXTERNAL | {"secret": "", "name": "Blank secret"}, 422, "MDL_CREDENTIAL_REQUIRED"),
        (INTERNAL | {"secret": "x", "name": "Secret with NONE"}, 422, "VALIDATION_FAILED"),
        (EXTERNAL | {"name": "vendor a2"}, 409, "MDL_DUPLICATE"),  # case-insensitive
        (EXTERNAL | {"name": "Plain", "endpoint": "http://x.test"}, 422, "MDL_ENDPOINT_BLOCKED"),
        (EXTERNAL | {"name": "Bad", "system_prompt": "x"}, 422, "VALIDATION_FAILED"),
        (EXTERNAL | {"name": "Bad", "provider_type": "CLOUD"}, 422, "VALIDATION_FAILED"),
    ):
        assert call(db, "POST", "/providers", invalid, status)["code"] == code, invalid
    internal = call(db, "POST", "/providers", INTERNAL, 201)
    assert internal["credential_status"] == "NOT_REQUIRED" and not internal["has_credential"]

    # Switching to NONE keeps no usable secret; switching back requires a new one.
    none = call(db, "PATCH", f"/providers/{pid}", {"auth_scheme": "NONE"})
    assert none["auth_header_name"] is None and none["credential_status"] == "NOT_REQUIRED"
    assert (
        call(db, "PATCH", f"/providers/{pid}", {"auth_scheme": "BEARER"}, 422)["code"]
        == "MDL_CREDENTIAL_REQUIRED"
    )

    actions = [action for action, _ in audit_actions(db, pid)]
    assert actions[0] == "mdl.provider_created"
    assert actions.count("mdl.provider_credential_rotated") == 3
    for _, changes in audit_actions(db, pid):
        assert "endpoint" not in changes and "secret" not in json.dumps(changes)
    created_event = audit_actions(db, pid)[0][1]
    assert created_event["endpoint_origin"] == "https://api.vendor-a.test"
    assert SECRET not in caplog.text and ROTATED not in caplog.text and KEY not in caplog.text


def test_missing_key_ring_is_reported_and_blocks_only_secret_writes(mdl):
    db = mdl
    stored = call(db, "POST", "/providers", EXTERNAL, 201)
    db.settings = db.settings.model_copy(update={"mdl_credential_keys": SecretStr("")})
    status = call(db, "GET", "/status")
    assert (status["credential_keys"], status["active_key_id"]) == ("UNAVAILABLE", None)
    assert call(db, "GET", f"/providers/{stored['id']}")["credential_status"] == "UNREADABLE"
    blocked = call(db, "POST", "/providers", EXTERNAL | {"name": "Other"}, 503)
    assert blocked["code"] == "MDL_CREDENTIAL_UNAVAILABLE"
    with connect(db.owner) as connection:
        assert connection.execute("SELECT count(*) FROM mdl_providers").fetchone() == (1,)
    call(db, "POST", "/providers", INTERNAL, 201)  # no secret needed, still works
    call(db, "PATCH", f"/providers/{stored['id']}", {"name": "Renamed"})  # keeps the secret
    # A key ring without the row's key ID also reports UNREADABLE.
    other = base64.b64encode(os.urandom(32)).decode()
    db.settings = db.settings.model_copy(
        update={"mdl_credential_keys": SecretStr(f"k2:{other}"), "mdl_credential_active_key_id": "k2"}
    )
    assert call(db, "GET", f"/providers/{stored['id']}")["credential_status"] == "UNREADABLE"


def test_agreements_are_append_only_and_external_only(mdl):
    db = mdl
    external = call(db, "POST", "/providers", EXTERNAL, 201)
    internal = call(db, "POST", "/providers", INTERNAL, 201)
    path = f"/providers/{external['id']}/agreements"
    first = call(db, "POST", path, {"basis": "NO_TRAINING_COMMITMENT", "document_number": " HD-01 "}, 201)
    assert first["document_number"] == "HD-01" and first["in_force"]
    second = call(
        db,
        "POST",
        path,
        {"basis": "SCHOOL_WRITTEN_AUTHORIZATION", "document_number": "QD-02", "signed_on": "2026-11-01"},
        201,
    )
    listed = call(db, "GET", path)["items"]
    assert [item["id"] for item in listed] == [second["id"], first["id"]]
    assert [item["in_force"] for item in listed] == [True, False]
    assert call(db, "GET", f"/providers/{external['id']}")["agreement_in_force"]["id"] == second["id"]

    withdrawn = call(db, "POST", f"{path}/{second['id']}/withdraw")
    assert withdrawn["agreement"]["withdrawn_at"] and not withdrawn["agreement"]["in_force"]
    assert withdrawn["affected_routing"] == []
    # The earlier, never-withdrawn agreement is in force again.
    assert call(db, "GET", f"/providers/{external['id']}")["agreement_in_force"]["id"] == first["id"]
    assert call(db, "POST", f"{path}/{second['id']}/withdraw", None, 409)["code"] == "CONFLICT"
    call(db, "POST", f"{path}/{uuid4()}/withdraw", None, 404)
    call(db, "POST", f"/providers/{internal['id']}/agreements/{first['id']}/withdraw", None, 404)
    call(db, "POST", f"{path}/{first['id']}/withdraw")
    assert call(db, "GET", f"/providers/{external['id']}")["agreement_in_force"] is None

    for invalid, status in (
        ({"basis": "LEGAL_OPINION", "document_number": "X"}, 422),
        ({"basis": "NO_TRAINING_COMMITMENT", "document_number": "   "}, 422),
        ({"basis": "NO_TRAINING_COMMITMENT"}, 422),
        ({"basis": "NO_TRAINING_COMMITMENT", "document_number": "X", "file": "x.pdf"}, 422),
    ):
        call(db, "POST", path, invalid, status)
    body = {"basis": "NO_TRAINING_COMMITMENT", "document_number": "X"}
    call(db, "POST", f"/providers/{internal['id']}/agreements", body, 422)
    assert {action for action, _ in audit_actions(db, second["id"])} == {
        "mdl.agreement_recorded",
        "mdl.agreement_withdrawn",
    }


def test_models_registry_risk_and_where_used_guards(mdl):
    db = mdl
    external = call(db, "POST", "/providers", EXTERNAL, 201)
    internal = call(db, "POST", "/providers", INTERNAL, 201)

    def model(provider, technical, **extra):
        body = {
            "provider_id": provider["id"],
            "technical_id": technical,
            "display_name": technical.upper(),
            "capabilities": ["TEXT"],
        }
        return call(db, "POST", "/models", body | extra, 201)

    primary = model(external, "gpt-x", risk_level="LOW", capabilities=["VOICE", "TEXT"])
    assert primary["capabilities"] == ["TEXT", "VOICE"] and primary["risk_level"] == "LOW"
    fallback = model(internal, "llama", risk_level="MEDIUM")
    spare = model(internal, "gpt-x")  # same technical ID under another provider is allowed
    assert spare["risk_level"] is None  # no default classification (FR-MDL-031)

    for invalid, status, code in (
        ({"technical_id": "gpt-x"}, 409, "MDL_DUPLICATE"),
        ({"technical_id": "y", "capabilities": []}, 422, "VALIDATION_FAILED"),
        ({"technical_id": "y", "capabilities": ["TEXT", "TEXT"]}, 422, "VALIDATION_FAILED"),
        ({"technical_id": "y", "risk_level": "Cao"}, 422, "VALIDATION_FAILED"),
        ({"technical_id": "y", "max_output_tokens": 0}, 422, "VALIDATION_FAILED"),
        ({"technical_id": "y", "system_prompt": "x"}, 422, "VALIDATION_FAILED"),
        ({"technical_id": "y", "temperature": 1}, 422, "VALIDATION_FAILED"),
        ({"technical_id": "y", "provider_id": str(uuid4())}, 404, "NOT_FOUND"),
    ):
        body = {"provider_id": external["id"], "display_name": "Y", "capabilities": ["TEXT"]} | invalid
        assert call(db, "POST", "/models", body, status)["code"] == code, invalid
    for invalid in ({"technical_id": "z"}, {"provider_id": internal["id"]}, {"template": "x"}):
        call(db, "PATCH", f"/models/{spare['id']}", invalid, 422)

    listed = call(db, "GET", "/models", {"risk_level": "UNCLASSIFIED"})["items"]
    assert [item["id"] for item in listed] == [spare["id"]]
    assert len(call(db, "GET", "/models", {"provider_id": internal["id"]})["items"]) == 2

    changed = call(db, "PATCH", f"/models/{spare['id']}", {"risk_level": "HIGH", "max_output_tokens": 512})
    assert changed["risk_level"] == "HIGH" and changed["max_output_tokens"] == 512
    assert [a for a, _ in audit_actions(db, spare["id"])] == [
        "mdl.model_created",
        "mdl.model_updated",
        "mdl.model_risk_changed",
    ]
    call(db, "PATCH", f"/models/{spare['id']}", {"risk_level": None})  # unrouted: may unclassify

    # Seed routing directly (routing writes are M5) to exercise the where-used seam.
    with connect(db.owner) as connection:
        connection.execute(
            "INSERT INTO mdl_routing (institution_id, primary_model_id, fallback_model_id,"
            " revision, updated_by) VALUES (%s, %s, %s, 1, %s)",
            (db.tenant, primary["id"], fallback["id"], db.manager_id),
        )
    refused = call(db, "POST", f"/models/{primary['id']}/deactivate", None, 409)
    assert refused["code"] == "MDL_MODEL_IN_USE" and refused["details"] == {
        "used_in": ["routing.primary"]
    }
    refused = call(db, "POST", f"/providers/{internal['id']}/deactivate", None, 409)
    assert refused["details"] == {"used_in": ["routing.fallback"]}
    risk = call(db, "PATCH", f"/models/{primary['id']}", {"risk_level": None}, 422)
    assert risk["code"] == "MDL_RISK_REQUIRED"
    text = call(db, "PATCH", f"/models/{fallback['id']}", {"capabilities": ["IMAGE"]}, 409)
    assert text["details"] == {"used_in": ["routing.fallback"]}
    agreement = call(
        db,
        "POST",
        f"/providers/{external['id']}/agreements",
        {"basis": "NO_TRAINING_COMMITMENT", "document_number": "HD-9"},
        201,
    )
    # D5: withdrawal is allowed while routed and reports the affected routing.
    withdrawn = call(
        db, "POST", f"/providers/{external['id']}/agreements/{agreement['id']}/withdraw"
    )
    assert withdrawn["affected_routing"] == ["routing.primary"]
    call(db, "POST", f"/models/{spare['id']}/deactivate")  # unused: allowed

    # FR-MDL-012 AC2: after switching the primary, the old one can be deactivated.
    with connect(db.owner) as connection:
        connection.execute(
            "UPDATE mdl_routing SET primary_model_id = %s, fallback_model_id = NULL,"
            " revision = 2 WHERE institution_id = %s",
            (fallback["id"], db.tenant),
        )
    deactivated = call(db, "POST", f"/models/{primary['id']}/deactivate")
    assert not deactivated["active"]
    assert call(db, "POST", f"/models/{primary['id']}/deactivate")["active"] is False  # no-op
    call(db, "POST", f"/providers/{external['id']}/deactivate")
    assert [a for a, _ in audit_actions(db, primary["id"])].count("mdl.model_state_changed") == 1
    # No hard delete exists: the model is still listed after deactivation.
    assert call(db, "GET", f"/models/{primary['id']}")["technical_id"] == "gpt-x"


def test_other_institutions_are_invisible(mdl):
    db = mdl
    other, other_user = uuid4(), uuid4()
    with connect(db.owner) as connection:
        connection.execute(
            "INSERT INTO institutions (id, code, name) VALUES (%s, 'OTHER', 'Other')", (other,)
        )
        unit = connection.execute(
            "INSERT INTO units (institution_id, code, name) VALUES (%s, 'o', 'O') RETURNING id",
            (other,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO users (id, institution_id, primary_unit_id, username, display_name,"
            " code_type, institutional_code) VALUES (%s, %s, %s, 'other', 'O', 'STAFF', '9')",
            (other_user, other, unit),
        )
        provider = connection.execute(
            "INSERT INTO mdl_providers (institution_id, name, provider_type, api_style, endpoint,"
            " auth_scheme) VALUES (%s, 'Foreign', 'EXTERNAL', 'OPENAI_COMPATIBLE',"
            " 'https://foreign.test', 'NONE') RETURNING id",
            (other,),
        ).fetchone()[0]
        model = connection.execute(
            "INSERT INTO mdl_models (institution_id, provider_id, technical_id, display_name,"
            " supports_text) VALUES (%s, %s, 'f', 'F', true) RETURNING id",
            (other, provider),
        ).fetchone()[0]
    assert call(db, "GET", "/providers")["total"] == 0 and call(db, "GET", "/models")["total"] == 0
    for method, path, body in (
        ("GET", f"/providers/{provider}", None),
        ("PATCH", f"/providers/{provider}", {"name": "Mine"}),
        ("POST", f"/providers/{provider}/deactivate", None),
        ("GET", f"/providers/{provider}/agreements", None),
        ("POST", f"/providers/{provider}/agreements", {"basis": "NO_TRAINING_COMMITMENT", "document_number": "X"}),
        ("GET", f"/models/{model}", None),
        ("PATCH", f"/models/{model}", {"display_name": "Mine"}),
        ("POST", f"/models/{model}/deactivate", None),
        ("POST", "/models", {"provider_id": str(provider), "technical_id": "x", "display_name": "X", "capabilities": ["TEXT"]}),
    ):
        assert call(db, method, path, body, 404)["code"] == "NOT_FOUND", path


def test_audit_failure_rolls_back_provider_and_credential(mdl):
    db = mdl
    with connect(db.owner) as connection:
        connection.execute(
            sql.SQL("REVOKE INSERT ON audit_events FROM {}").format(
                sql.Identifier(db.roles.runtime)
            )
        )
    response = send(db.manager, "POST", mdl_path("/providers"), EXTERNAL)
    db.seen.bodies.append(response.text)
    assert response.status_code == 500 and response.json()["code"] == "DATABASE_ERROR"
    with connect(db.owner) as connection:
        for table in ("mdl_providers", "mdl_provider_credentials", "audit_events"):
            count = connection.execute(
                f"SELECT count(*) FROM {table}"
                + (" WHERE action LIKE 'mdl.%%'" if table == "audit_events" else "")
            ).fetchone()
            assert count == (0,), table


def test_concurrent_duplicate_creates_yield_one_provider(mdl):
    db = mdl
    barrier = Barrier(2)
    headers = csrf_headers(db.manager)
    cookies = dict(db.manager.cookies)

    def attempt(index):
        with client(db) as browser:
            browser.cookies.update(cookies)
            barrier.wait()
            body = EXTERNAL | {"name": "Racing" if index else "RACING"}
            response = browser.post("/api/v1/mdl/providers", json=body, headers=headers)
            db.seen.bodies.append(response.text)
            return response.status_code, response.json().get("code")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(attempt, range(2)), key=lambda item: item[0])
    assert results[0][0] == 201 and results[1] == (409, "MDL_DUPLICATE")
    with connect(db.owner) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mdl_providers WHERE lower(name) = 'racing'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM mdl_provider_credentials").fetchone() == (1,)
