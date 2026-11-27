"""M7 against PostgreSQL: MDL configuration history with before/after values.

FRD section 6 ("Should": full configuration version history with diff). The endpoint
is read-only, needs ``mdl.read``, shows only the caller's institution and only typed,
allowlisted audit payloads, so no secret can appear (RULE-MDL-04, checked by the
``mdl`` fixture's canary scan of every response and audit row).
"""

import json
from uuid import uuid4

from .test_m3_mdl_api import EXTERNAL, ROTATED, SECRET, call
from .test_m3_mdl_api import mdl as mdl
from .test_wp2_database import connect
from .test_wp3_auth import client
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import directory as directory
from .test_wp5_directory import get
from .test_wp5_directory import pytestmark as postgres_marks

pytestmark = postgres_marks


def history(db, **params):
    return call(db, "GET", "/history", params or None)


def test_history_shows_each_change_with_before_and_after(mdl):
    db = mdl
    assert history(db) == {"items": [], "total": 0, "limit": 25, "offset": 0}

    provider = call(db, "POST", "/providers", EXTERNAL, 201)
    pid = provider["id"]
    call(db, "PATCH", f"/providers/{pid}", {"name": "Vendor B"})
    call(db, "PATCH", f"/providers/{pid}", {"endpoint": "https://api.vendor-b.test/v2", "secret": ROTATED})
    agreement = call(
        db, "POST", f"/providers/{pid}/agreements",
        {"basis": "NO_TRAINING_COMMITMENT", "document_number": "HD-07"}, 201,
    )
    call(db, "POST", f"/providers/{pid}/agreements/{agreement['id']}/withdraw")
    model = call(
        db, "POST", "/models",
        {"provider_id": pid, "technical_id": "m-1", "display_name": "M1", "capabilities": ["TEXT"]}, 201,
    )
    mid = model["id"]
    call(db, "PATCH", f"/models/{mid}", {"display_name": "M1 bis", "max_output_tokens": 512})
    call(db, "PATCH", f"/models/{mid}", {"risk_level": "HIGH"})
    call(db, "POST", f"/models/{mid}/deactivate")

    # A connection-test event (own history elsewhere) and another institution's MDL
    # event must never appear here.
    other = uuid4()
    with connect(db.owner) as connection:
        tenant = connection.execute("SELECT institution_id FROM mdl_models WHERE id = %s", (mid,)).fetchone()[0]
        connection.execute(
            "INSERT INTO institutions (id, code, name) VALUES (%s, 'OTHER7', 'Other')", (other,)
        )
        for institution, actor, action in (
            (tenant, db.manager_id, "mdl.model_connection_tested"),
            (other, None, "mdl.model_risk_changed"),
        ):
            connection.execute(
                "INSERT INTO audit_events (institution_id, actor_id, action, target_type, target_id,"
                " outcome, occurred_at, request_id, changes) VALUES (%s, %s, %s, 'mdl_model', %s,"
                " 'SUCCESS', clock_timestamp(), %s, %s)",
                (institution, actor, action, mid, str(uuid4()), json.dumps({"before": None, "after": "LOW"})),
            )

    page = history(db, limit=100)
    actions = [item["action"] for item in page["items"]]
    assert actions == [
        "mdl.model_state_changed",
        "mdl.model_risk_changed",
        "mdl.model_updated",
        "mdl.model_created",
        "mdl.agreement_withdrawn",
        "mdl.agreement_recorded",
        "mdl.provider_credential_rotated",
        "mdl.provider_updated",
        "mdl.provider_updated",
        "mdl.provider_created",
    ]
    assert page["total"] == 10
    by_action = {}
    for item in page["items"]:
        by_action.setdefault(item["action"], []).append(item)
        assert item["actor_id"] == db.manager_id

    renamed, moved = reversed(by_action["mdl.provider_updated"])
    assert (renamed["changes"]["before"]["name"], renamed["changes"]["after"]["name"]) == ("Vendor A", "Vendor B")
    assert renamed["changes"]["endpoint_changed"] is False
    assert moved["changes"]["before"]["endpoint_origin"] == "https://api.vendor-a.test"
    assert moved["changes"]["after"]["endpoint_origin"] == "https://api.vendor-b.test"
    assert moved["changes"]["endpoint_changed"] is True
    assert by_action["mdl.provider_credential_rotated"][0]["changes"] == {"credential_version": 2}
    updated = by_action["mdl.model_updated"][0]["changes"]
    assert (updated["before"]["display_name"], updated["after"]["display_name"]) == ("M1", "M1 bis")
    assert (updated["before"]["max_output_tokens"], updated["after"]["max_output_tokens"]) == (None, 512)
    assert by_action["mdl.model_risk_changed"][0]["changes"] == {"before": None, "after": "HIGH"}
    assert by_action["mdl.model_state_changed"][0]["changes"] == {"before": True, "after": False}
    assert by_action["mdl.agreement_withdrawn"][0]["changes"]["document_number"] == "HD-07"

    # Filters: one model's history; one target type; paging totals.
    model_events = history(db, target_id=mid)
    assert {item["target_id"] for item in model_events["items"]} == {mid}
    assert model_events["total"] == 4
    assert history(db, target_type="mdl_agreement")["total"] == 2
    assert len(history(db, limit=3)["items"]) == 3
    assert call(db, "GET", "/history", {"target_type": "user"}, 422)["code"] == "VALIDATION_FAILED"

    # Nothing secret-like is ever part of an event (in addition to the canary scan).
    dump = json.dumps(page)
    for forbidden in (SECRET, ROTATED, "ciphertext", "nonce", "/v2"):
        assert forbidden not in dump


def test_history_requires_mdl_read(mdl):
    db = mdl
    call(db, "POST", "/providers", EXTERNAL, 201)
    with client(db) as anonymous:
        assert anonymous.get("/api/v1/mdl/history").status_code == 401
    # The foundation administrator holds audit.read but no MDL right.
    response = get(db.admin, "/mdl/history")
    assert response.status_code == 403
    assert SECRET not in response.text
