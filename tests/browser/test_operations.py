"""Rehearse legacy upgrades, actual pg_restore, and service restart in isolation."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from playwright.sync_api import expect
from psycopg import sql

from .conftest import ROOT, TEMPORARY, Stack, connect, free_port
from .test_admin import admin_session, create_named, login, section, write_api

HEAD = "0002_identity_foundation"
TABLES = (
    "app_metadata",
    "institutions",
    "units",
    "users",
    "user_credentials",
    "roles",
    "permissions",
    "role_permissions",
    "account_groups",
    "group_memberships",
    "user_role_assignments",
    "group_role_assignments",
    "auth_sessions",
    "auth_throttle_buckets",
    "audit_events",
)


def new_stack(database, path):
    return Stack(database, free_port(), free_port(), path)


@pytest.mark.parametrize("prior", ["0001_phase1_metadata", HEAD])
def test_legacy_upgrade_preserves_data_and_enables_restricted_api_writes(
    page, database_factory, tmp_path, prior
):
    with database_factory() as database:
        database.alembic("upgrade", prior, as_bootstrap=True)
        with connect(database.bootstrap) as db:
            db.execute("INSERT INTO app_metadata (key, value) VALUES ('wp7_legacy', 'preserved')")
        database.provision()
        if prior == HEAD:
            # Simulate an existing identity and readiness at the old read-only grant level.
            database.seed()
            with connect(database.owner) as db:
                db.execute(
                    sql.SQL("REVOKE INSERT (institution_id, code, name) ON units FROM {}").format(
                        sql.Identifier(database.roles.runtime)
                    )
                )
                existing_identity = db.execute(
                    "SELECT id FROM users WHERE username='admin'"
                ).fetchone()[0]
        stack = new_stack(database, tmp_path)
        with stack.api(), stack.proxy():
            ready_url = stack.demo + "/api/v1/ready"
            assert page.request.get(ready_url).status == (200 if prior == HEAD else 503)
            if prior == HEAD:
                admin_session(page, stack)
                write_api(
                    page,
                    stack,
                    "POST",
                    "/units",
                    {"code": "BLOCKED", "name": "Blocked"},
                    status=500,
                )
            database.provision()
            database.migrate()
            database.alembic("check")
            assert page.request.get(ready_url).status == 200
            if prior != HEAD:
                database.seed()
                admin_session(page, stack)
            else:
                assert page.request.get(stack.admin + "/api/v1/auth/me").json()["id"] == str(
                    existing_identity
                )
            created = write_api(
                page, stack, "POST", "/units", {"code": "UPGRADED", "name": "Đã nâng cấp"}
            )
            events = page.request.get(
                stack.admin + f"/api/v1/audit-events?target_id={created['id']}"
            ).json()
            assert events["total"] == 1 and events["items"][0]["action"] == "unit.created"
        with connect(database.runtime) as db:
            assert db.execute(
                "SELECT value FROM app_metadata WHERE key='wp7_legacy'"
            ).fetchone() == ("preserved",)


def pg_tool(name, url, *arguments):
    bindir = os.getenv("AQ_PHASE2_PG_BIN")
    tool = str(Path(bindir) / name) if bindir else shutil.which(name)
    if not tool:
        pytest.fail(f"Install PostgreSQL 18 client tools or set AQ_PHASE2_PG_BIN for {name}.")
    return subprocess.run(
        [
            tool,
            "--host",
            url.host,
            "--port",
            str(url.port),
            "--username",
            url.username,
            "--no-password",
            *arguments,
        ],
        env={**os.environ, "PGPASSWORD": url.password},
        check=True,
        capture_output=True,
        text=True,
        timeout=45,
    ).stdout


def snapshot(url):
    with connect(url) as db:
        result = {}
        for table in TABLES:
            records = db.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} AS t ORDER BY to_jsonb(t)").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            # Compare all content without sending password hashes or token digests to test output.
            digest = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
            result[table] = (len(records), digest)
        return result


def test_backup_restores_history_and_runtime_writes(page, stack, database_factory, tmp_path):
    admin_session(page, stack)
    unit = write_api(page, stack, "POST", "/units", {"code": "ARCHIVE", "name": "Kho lưu trữ"})
    user = write_api(
        page,
        stack,
        "POST",
        "/users",
        {
            "primary_unit_id": unit["id"],
            "username": "archive",
            "display_name": "Người dùng lưu trữ",
            "code_type": "STUDENT",
            "institutional_code": "ARC-001",
            "temporary_password": TEMPORARY,
        },
    )
    group = write_api(
        page,
        stack,
        "POST",
        "/groups",
        {"code": "ARC", "name": "Nhóm lưu trữ", "kind": "AUTHORIZATION"},
    )
    write_api(page, stack, "PUT", f"/groups/{group['id']}/members/{user['id']}", status=200)
    for subject in (f"/users/{user['id']}", f"/groups/{group['id']}"):
        write_api(
            page,
            stack,
            "POST",
            subject + "/role-assignments",
            {
                "role_code": "DIRECTORY_READER",
                "scope": "UNIT",
                "unit_id": unit["id"],
            },
        )
    source = stack.database
    original = snapshot(source.owner)
    assert original["audit_events"][0] >= 8
    backup = tmp_path / "phase2-synthetic.dump"
    backup.touch(mode=0o600, exist_ok=False)
    pg_tool(
        "pg_dump",
        source.bootstrap,
        "--format=custom",
        "--file",
        str(backup),
        source.bootstrap.database,
    )
    assert backup.stat().st_mode & 0o077 == 0
    toc = pg_tool("pg_restore", source.bootstrap, "--list", str(backup))
    assert "TABLE DATA public audit_events" in toc and "TABLE DATA public user_credentials" in toc

    with database_factory() as restored:
        pg_tool(
            "pg_restore",
            restored.bootstrap,
            "--no-owner",
            "--no-privileges",
            "--single-transaction",
            "--exit-on-error",
            "--dbname",
            restored.bootstrap.database,
            str(backup),
        )
        restored.provision()
        restored.migrate()
        restored.alembic("check")
        assert snapshot(restored.owner) == original
        with connect(restored.runtime) as db:
            assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)
            for command in (
                "UPDATE audit_events SET action=action",
                "DELETE FROM group_memberships",
                "CREATE TABLE runtime_forbidden (id int)",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
                    db.execute(command)
        # Cookies are hostname-scoped, not port-scoped. Use a separate browser context.
        with page.context.browser.new_context() as context:
            restored_page = context.new_page()
            restore_root = tmp_path / "restored"
            restore_root.mkdir()
            restored_stack = new_stack(restored, restore_root)
            with restored_stack.api(), restored_stack.proxy():
                restored_page.goto(restored_stack.admin)
                from .conftest import PERSONAL

                login(restored_page, "admin", PERSONAL)
                expect(restored_page.get_by_role("heading", name="Tổng quan")).to_be_visible()
                section(restored_page, "Nhóm tài khoản")
                restored_page.get_by_role("link", name="Nhóm lưu trữ").click()
                expect(restored_page.get_by_role("link", name="Người dùng lưu trữ")).to_be_visible()
                events = restored_page.request.get(
                    restored_stack.admin + "/api/v1/audit-events?action=membership.state_changed"
                ).json()
                assert events["items"][0]["changes"]["user_id"] == user["id"]
                section(restored_page, "Đơn vị")
                create_named(restored_page, "Tạo đơn vị", "AFTER", "Đơn vị sau phục hồi")
                with connect(restored.runtime) as db:
                    assert db.execute(
                        "SELECT count(*) FROM audit_events WHERE action='unit.created'"
                    ).fetchone() == (2,)


def test_demo_browser_isolation_and_application_restart(page, provisioned_stack):
    stack = provisioned_stack
    with stack.proxy():
        with stack.api():
            subprocess.run(
                [sys.executable, "scripts/phase1_smoke.py", "--base-url", stack.demo],
                cwd=ROOT,
                check=True,
                timeout=25,
            )
            admin_session(page, stack)
            section(page, "Đơn vị")
            create_named(page, "Tạo đơn vị", "PERSIST", "Đơn vị lưu bền")
            demo = page.context.new_page()
            demo.goto(stack.demo + "/#module1")
            expect(demo.locator(".model-shell")).to_be_visible()
            sidebar = demo.locator(".sidebar").bounding_box()["width"]
            demo.locator('[data-action="tab"][data-tab="dpa"]').click()
            demo.locator('[data-action="add-provider"]').first.click()
            expect(demo.get_by_role("dialog")).to_be_visible()
            demo.get_by_role("button", name="Đóng", exact=True).click()
            demo.locator('[data-action="nav"][data-page="quotas"]').first.click()
            expect(demo.locator(".quota-shell")).to_be_visible()
            assert demo.locator(".sidebar").bounding_box()["width"] == sidebar
            demo.locator('[data-action="sync-groups"]').first.click()
            demo.locator('[data-action="confirm-sync"]').click()
            assert demo.evaluate(
                "JSON.parse(localStorage.getItem('aq_uai-demo-v1')).groups.some(g => g.id === 'G_BGH')"
            )
            demo.locator('[data-action="nav"][data-page="credits"]').first.click()
            expect(demo.locator(".credits-shell")).to_be_visible()
            assert demo.locator(".sidebar").bounding_box()["width"] == sidebar
            demo.locator('[data-action="grant"]').first.click()
            expect(demo.get_by_role("dialog")).to_be_visible()
            demo.get_by_role("button", name="Đóng", exact=True).click()
            demo.go_back()
            expect(demo).to_have_url(re.compile(r"#module2$"))
            expect(demo.locator(".quota-shell")).to_be_visible()
            demo.go_forward()
            expect(demo.locator(".credits-shell")).to_be_visible()
            demo.reload()
            expect(demo.locator(".credits-shell")).to_be_visible()
            assert page.evaluate("localStorage.getItem('aq_uai-demo-v1')") is None
            assert demo.request.get(stack.demo + "/api/v1/users").status == 404
            assert not demo.context.cookies(stack.demo)
            assert page.request.get(stack.admin + "/api/v1/groups").json()["total"] == 0
            me = page.request.get(stack.admin + "/api/v1/auth/me").json()
            token = next(
                cookie["value"]
                for cookie in page.context.cookies(stack.admin)
                if cookie["name"] == "aq_uai_session"
            )
            logs = (stack.path / "api.log").read_text() + (stack.path / "nginx.log").read_text()
            assert all(value not in logs for value in (TEMPORARY, me["csrf_token"], token))
        assert page.request.get(stack.demo + "/api/v1/health").status == 502
        with stack.api():
            page.reload()
            expect(page.get_by_role("link", name="Đơn vị lưu bền")).to_be_visible()
            assert page.request.get(stack.admin + "/api/v1/auth/me").json()["id"] == me["id"]
            expect(demo.locator(".credits-shell")).to_be_visible()
