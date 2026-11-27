"""M7: MDL backup and restore with sealed credentials, including key loss.

What: a real ``pg_dump`` / ``pg_restore`` of a database that holds an encrypted provider
secret, a PASSED connection test, routing and its history; then the restored database
is served by a fresh API process

1. with the **same** key ring: the route is usable and a new connection test sends the
   original secret (the ciphertext survived the backup and still opens);
2. with a **different** key ring (the old key was lost): the credential is reported
   unreadable, the route fails closed and a connection test is refused before any
   request leaves the API; re-entering the secret recovers the provider.

Why: D14 keeps the key ring outside PostgreSQL, so a backup alone never reveals a
secret, and losing the key ring must fail closed rather than corrupt or leak anything.
The dump is written uncompressed so the plaintext check below is meaningful.
"""

import hashlib
import json

from psycopg import sql

from .conftest import MDL_KEY, PERSONAL, connect
from .test_mdl import SECRET, api, model_admin
from .test_operations import new_stack, pg_tool

ROTATED_AFTER_LOSS = "sk-browser-canary-after-key-loss-5c2e"
OTHER_KEY = "q0mTn3z1J3x6m8b1Qe4gXcY2p5v7s9w0A1b3C5d7E9g="  # synthetic, never the original
MDL_TABLES = (
    "mdl_providers",
    "mdl_provider_credentials",
    "mdl_provider_agreements",
    "mdl_provider_agreement_withdrawals",
    "mdl_models",
    "mdl_connection_tests",
    "mdl_routing",
    "mdl_routing_revisions",
    "audit_events",
)


def snapshot(url):
    with connect(url) as db:
        result = {}
        for table in MDL_TABLES:
            rows = db.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} AS t ORDER BY to_jsonb(t)").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
            result[table] = (len(rows), digest)
        return result


def fetch(page, stack, method, path, body=None):
    if method == "GET":
        return page.request.get(stack.admin + "/api/v1" + path)
    csrf = page.request.get(stack.admin + "/api/v1/auth/me").json()["csrf_token"]
    return page.request.fetch(
        stack.admin + "/api/v1" + path, method=method, data=body,
        headers={"Origin": stack.admin, "X-CSRF-Token": csrf},
    )


def signed_in(browser, stack):
    context = browser.new_context()
    page = context.new_page()
    response = page.request.post(
        stack.admin + "/api/v1/auth/login",
        data={"username": "ai.admin", "password": PERSONAL},
        headers={"Origin": stack.admin},
    )
    assert response.status == 204, response.status
    return context, page


def test_restore_keeps_ciphertext_usable_and_key_loss_fails_closed(page, mdl_stack, browser, database_factory, tmp_path):
    stack = mdl_stack
    context, mdl = model_admin(page, stack, browser)
    try:
        provider = api(mdl, stack, "POST", "/mdl/providers", {
            "name": "Máy chủ nội bộ", "provider_type": "INTERNAL", "endpoint": stack.provider.url(),
            "auth_scheme": "BEARER", "secret": SECRET,
        })
        model = api(mdl, stack, "POST", "/mdl/models", {
            "provider_id": provider["id"], "technical_id": "local-llm", "display_name": "Mô hình nội bộ",
            "capabilities": ["TEXT"], "risk_level": "LOW",
        })
        assert api(mdl, stack, "POST", f"/mdl/models/{model['id']}/connection-tests")["status"] == "PASSED"
        routing = api(mdl, stack, "PUT", "/mdl/routing", {
            "expected_revision": 0, "primary_model_id": model["id"], "decision_reference": "QĐ-BK-01",
        })
        assert routing["effective"]["state"] == "PRIMARY"
    finally:
        context.close()
    sent_before_restore = len(stack.provider.requests)

    source = stack.database
    original = snapshot(source.owner)
    assert original["mdl_provider_credentials"][0] == 1 and original["mdl_routing_revisions"][0] == 1
    backup = tmp_path / "mdl-synthetic.dump"
    backup.touch(mode=0o600, exist_ok=False)
    pg_tool("pg_dump", source.bootstrap, "--format=custom", "--compress=0", "--file", str(backup),
            source.bootstrap.database)
    toc = pg_tool("pg_restore", source.bootstrap, "--list", str(backup))
    assert "TABLE DATA public mdl_provider_credentials" in toc
    # D14: the backup holds ciphertext only; neither the secret nor the key is in it.
    raw = backup.read_bytes()
    assert SECRET.encode() not in raw and MDL_KEY.encode() not in raw

    with database_factory() as restored:
        pg_tool("pg_restore", restored.bootstrap, "--no-owner", "--no-privileges", "--single-transaction",
                "--exit-on-error", "--dbname", restored.bootstrap.database, str(backup))
        restored.provision()
        restored.migrate()
        restored.alembic("check")
        assert snapshot(restored.owner) == original
        with connect(restored.owner) as db:
            # Let the 30 s per-configuration cooldown of the source test elapse.
            db.execute("UPDATE mdl_connection_tests SET started_at = started_at - interval '1 hour',"
                       " finished_at = finished_at - interval '1 hour'")

        # 1. Same key ring: the restored ciphertext opens; the route is usable.
        same = new_stack(restored, tmp_path / "same-key")
        same.path.mkdir()
        same.api_env = dict(stack.api_env)
        with same.api(), same.proxy():
            context, admin = signed_in(browser, same)
            try:
                routing = fetch(admin, same, "GET", "/mdl/routing").json()
                assert routing["effective"]["state"] == "PRIMARY", routing
                assert routing["revision"] == 1
                revisions = fetch(admin, same, "GET", "/mdl/routing/revisions").json()
                assert revisions["items"][0]["decision_reference"] == "QĐ-BK-01"
                result = fetch(admin, same, "POST", f"/mdl/models/{model['id']}/connection-tests")
                assert result.status == 201 and result.json()["status"] == "PASSED"
                assert stack.provider.requests[-1]["headers"]["authorization"] == f"Bearer {SECRET}"
            finally:
                context.close()
        sent_with_same_key = len(stack.provider.requests)
        assert sent_with_same_key == sent_before_restore + 1

        # 2. Key loss: another key ring. Fail closed, nothing sent, then recovery.
        with connect(restored.owner) as db:  # the cooldown gate runs before decryption
            db.execute("UPDATE mdl_connection_tests SET started_at = started_at - interval '1 hour',"
                       " finished_at = finished_at - interval '1 hour'")
        lost = new_stack(restored, tmp_path / "lost-key")
        lost.path.mkdir()
        lost.api_env = {**stack.api_env, "AQ_UAI_MDL_CREDENTIAL_KEYS": f"b2:{OTHER_KEY}",
                        "AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID": "b2"}
        with lost.api(), lost.proxy():
            context, admin = signed_in(browser, lost)
            try:
                status = fetch(admin, lost, "GET", "/mdl/status").json()
                assert (status["credential_keys"], status["active_key_id"]) == ("AVAILABLE", "b2")
                found = fetch(admin, lost, "GET", f"/mdl/providers/{provider['id']}").json()
                assert found["credential_status"] == "UNREADABLE"
                routing = fetch(admin, lost, "GET", "/mdl/routing").json()
                assert routing["effective"]["state"] == "UNAVAILABLE"
                assert "credential_unavailable" in routing["primary"]["issues"]
                refused = fetch(admin, lost, "POST", f"/mdl/models/{model['id']}/connection-tests")
                assert refused.status == 503 and refused.json()["code"] == "MDL_CREDENTIAL_UNAVAILABLE"
                assert len(stack.provider.requests) == sent_with_same_key  # nothing left the API
                # History and configuration are intact; only the secret must be re-entered.
                assert fetch(admin, lost, "GET", "/mdl/routing/revisions").json()["total"] == 1
                patched = fetch(admin, lost, "PATCH", f"/mdl/providers/{provider['id']}",
                                {"secret": ROTATED_AFTER_LOSS})
                assert patched.status == 200 and patched.json()["credential_status"] == "STORED"
                result = fetch(admin, lost, "POST", f"/mdl/models/{model['id']}/connection-tests")
                assert result.status == 201 and result.json()["status"] == "PASSED"
                assert stack.provider.requests[-1]["headers"]["authorization"] == f"Bearer {ROTATED_AFTER_LOSS}"
                assert fetch(admin, lost, "GET", "/mdl/routing").json()["effective"]["state"] == "PRIMARY"
                for response_body in (found, routing, status):
                    text = json.dumps(response_body)
                    assert SECRET not in text and ROTATED_AFTER_LOSS not in text
            finally:
                context.close()
