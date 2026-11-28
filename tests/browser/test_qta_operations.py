"""Q6 (4.3): Full Q1–Q6 end-to-end QTA workflow and pg_dump / pg_restore rehearsal (R18).

Populates every QTA capability through the real API (sync, specialist group, per-model
quotas, 409 deficit guard, two append-only school budget revisions, kill-switch suspension +
restoration, manual monthly reset, and events), dumps the database with ``pg_dump`` (custom
format, mode 600), restores into a brand-new database with ``--single-transaction
--exit-on-error``, runs provisioning and ``alembic check``, and verifies against a fresh
API + nginx stack in Chromium:
- every ``qta_*`` table is row-for-row identical to the source database;
- the restored ``#qta`` UI renders both budget revisions, the additive ``1.000 + 3.000 = 4.000``
  lookup, the suspension history, and the ``Đã làm mới`` (COMPLETED) reset state;
- runtime writes continue working after restore (a new suspension succeeds and renders ``ĐÃ CẮT``);
- append-only protection survives restore (``DELETE FROM qta_events`` as runtime role is denied);
- repeating ``POST /api/v1/qta/monthly-resets`` still returns ``409 QTA_RESET_ALREADY_EXECUTED``.
"""

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest
from playwright.sync_api import expect
from psycopg import sql

from .conftest import PERSONAL, TEMPORARY, connect
from .test_admin import admin_session, login
from .test_mdl import api
from .test_mdl_operations import fetch
from .test_operations import new_stack, pg_tool
from .test_qta import (
    assert_qta_dom_invariants,
    create_user_with_role,
    open_qta,
    seed_mdl_models,
    sign_in_new_browser,
)

QTA_TABLES = (
    "qta_budget_revisions",
    "qta_quota_groups",
    "qta_group_model_quotas",
    "qta_group_sync_runs",
    "qta_suspensions",
    "qta_suspension_restorations",
    "qta_monthly_resets",
    "qta_events",
)


def qta_snapshot(url) -> dict[str, tuple[int, str]]:
    """Return ``{table: (row_count, sha256_of_ordered_jsonb_rows)}`` for all 8 QTA tables."""
    with connect(url) as db:
        result: dict[str, tuple[int, str]] = {}
        for table in QTA_TABLES:
            rows = db.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} AS t ORDER BY to_jsonb(t)").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
            result[table] = (len(rows), digest)
        return result


def current_month_and_date() -> tuple[str, str]:
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return f"{now.year:04d}-{now.month:02d}", f"{now.year:04d}-{now.month:02d}-{now.day:02d}"


def test_qta_backup_restore_preserves_state_ui_writes_and_constraints(
    page, stack, browser, database_factory, tmp_path
):
    """Q6 full Q1–Q6 end-to-end population, pg_dump/pg_restore, restored #qta UI & guards."""
    admin_session(page, stack)
    models = seed_mdl_models(stack)
    unit = api(page, stack, "POST", "/units", {"code": "Q6OP", "name": "Đơn vị Vận hành Q6"})
    create_user_with_role(
        page, stack, unit["id"], "q6.admin", "Quản trị QTA Q6", "Q6-ADM", "AI_QUOTA_ADMIN"
    )
    stacked = api(
        page,
        stack,
        "POST",
        "/users",
        {
            "primary_unit_id": unit["id"],
            "username": "q6.stacked",
            "display_name": "Nguyễn Khôi Phục",
            "code_type": "STAFF",
            "institutional_code": "KP-01",
            "temporary_password": TEMPORARY,
        },
    )
    target = api(
        page,
        stack,
        "POST",
        "/users",
        {
            "primary_unit_id": unit["id"],
            "username": "q6.target",
            "display_name": "Trần Tạm Ngưng",
            "code_type": "STUDENT",
            "institutional_code": "TN-01",
            "temporary_password": TEMPORARY,
        },
    )
    g1 = api(page, stack, "POST", "/groups", {"code": "G1", "name": "Nhóm Hệ thống Q6", "kind": "SYSTEM"})
    api(page, stack, "PUT", f"/groups/{g1['id']}/members/{stacked['id']}")

    cur_month, today = current_month_and_date()

    # Populate all QTA features through the real API under AI_QUOTA_ADMIN.
    src_ctx, src_qta = sign_in_new_browser(browser, stack, "q6.admin")
    try:
        api(src_qta, stack, "POST", "/qta/groups/sync")
        api(
            src_qta,
            stack,
            "PUT",
            f"/qta/groups/{g1['id']}/quotas",
            {
                "quotas": [
                    {"model_id": models["ext_id"], "enabled": True, "monthly_limit": 1000},
                    {"model_id": models["int_id"], "enabled": True, "monthly_limit": 500},
                ]
            },
        )
        g2 = api(src_qta, stack, "POST", "/qta/groups", {"code": "G2", "name": "Nhóm Chuyên biệt Q6"})
        api(src_qta, stack, "PUT", f"/qta/groups/{g2['id']}/members/{stacked['id']}")
        api(
            src_qta,
            stack,
            "PUT",
            f"/qta/groups/{g2['id']}/quotas",
            {"quotas": [{"model_id": models["ext_id"], "enabled": True, "monthly_limit": 3000}]},
        )

        # Two append-only school budget revisions (plus verify 409 deficit guard in between).
        api(
            src_qta,
            stack,
            "PUT",
            f"/qta/budgets/{cur_month}",
            {"total_limit": 10_000, "decision_number": "QD-Q6-BK-01", "decision_date": today},
        )
        deficit_resp = fetch(
            src_qta,
            stack,
            "PUT",
            f"/qta/budgets/{cur_month}",
            {"total_limit": 3000, "decision_number": "QD-Q6-LOW", "decision_date": today},
        )
        assert deficit_resp.status == 409
        assert deficit_resp.json()["code"] == "QTA_BUDGET_BELOW_ALLOCATED"
        assert deficit_resp.json()["details"] == {"allocated": 4500, "deficit": 1500}

        api(
            src_qta,
            stack,
            "PUT",
            f"/qta/budgets/{cur_month}",
            {"total_limit": 8000, "decision_number": "QD-Q6-BK-02", "decision_date": today},
        )

        # Suspension + restoration + manual monthly reset.
        api(
            src_qta,
            stack,
            "POST",
            f"/qta/users/{target['id']}/suspensions",
            {
                "scope": "PAID_EXTERNAL_ONLY",
                "reason": "Kiểm tra sao lưu tạm ngưng",
                "ordered_by": "Hiệu trưởng",
            },
        )
        api(
            src_qta,
            stack,
            "POST",
            f"/qta/users/{target['id']}/restore",
            {"note": "Khôi phục trước khi sao lưu"},
        )
        api(src_qta, stack, "POST", "/qta/monthly-resets")
    finally:
        src_ctx.close()

    source = stack.database
    original = qta_snapshot(source.owner)
    for table_name, (row_count, _digest) in original.items():
        assert row_count >= 1, f"Expected populated QTA table before dump: {table_name}"
    assert original["qta_budget_revisions"][0] == 2

    backup = tmp_path / "qta-synthetic.dump"
    try:
        backup.touch(mode=0o600, exist_ok=False)
        pg_tool(
            "pg_dump",
            source.bootstrap,
            "--format=custom",
            "--file",
            str(backup),
            source.bootstrap.database,
        )
        assert (backup.stat().st_mode & 0o777) == 0o600
        toc = pg_tool("pg_restore", source.bootstrap, "--list", str(backup))
        assert "TABLE DATA public qta_budget_revisions" in toc
        assert "TABLE DATA public qta_events" in toc

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

            # Every qta_* table is row-for-row identical after restore.
            assert qta_snapshot(restored.owner) == original

            # Append-only still enforced on the restored database under the runtime role.
            with connect(restored.runtime, autocommit=True) as rconn:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    rconn.execute("DELETE FROM qta_events")

            restored_stack = new_stack(restored, tmp_path / "restored-qta")
            restored_stack.path.mkdir()
            with restored_stack.api(), restored_stack.proxy():
                r_ctx = browser.new_context(locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
                r_page = r_ctx.new_page()
                try:
                    r_page.goto(restored_stack.admin)
                    login(r_page, "q6.admin", PERSONAL)
                    expect(r_page.get_by_role("heading", name="Tổng quan")).to_be_visible()

                    # 1. Restored #qta budget header + both revisions render cleanly.
                    open_qta(r_page)
                    budget_panel = r_page.get_by_role("region", name="Tổng hạn mức AI theo tháng của trường")
                    expect(budget_panel).to_contain_text("Đã ghi nhận")
                    expect(budget_panel).to_contain_text("8.000 đơn vị hạn mức")
                    expect(budget_panel).to_contain_text("4.500 đơn vị hạn mức")
                    expect(budget_panel).to_contain_text("3.500 đơn vị hạn mức")
                    expect(budget_panel).to_contain_text("QD-Q6-BK-02")
                    expect(budget_panel).to_contain_text("QD-Q6-BK-01")
                    assert_qta_dom_invariants(r_page)

                    # 2. Restored lookup renders additive 1.000 + 3.000 = 4.000 & suspension history.
                    tabs_nav = r_page.get_by_role("navigation", name="Mục hạn mức AI")
                    tabs_nav.get_by_role("link", name="Tra cứu cá nhân & tạm ngưng").click()
                    r_page.locator("tr", has_text="q6.stacked").get_by_role("button", name="Xem hạn mức").click()
                    expect(
                        r_page.get_by_role("heading", name="Hạn mức cá nhân — Nguyễn Khôi Phục (q6.stacked)")
                    ).to_be_visible()
                    ext_row = r_page.locator("tr", has_text="Mô hình Ngoài Pro")
                    expect(ext_row).to_contain_text("4.000 đơn vị hạn mức")
                    expect(ext_row).to_contain_text("1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn mức")
                    expect(ext_row).to_contain_text("Chưa tích hợp đo tiêu thụ thực tế")
                    assert_qta_dom_invariants(r_page, check_consumption_cells=True)

                    r_page.locator("tr", has_text="q6.target").get_by_role("button", name="Xem hạn mức").click()
                    expect(
                        r_page.locator("section", has_text="Lịch sử tạm ngưng & khôi phục quyền AI")
                    ).to_contain_text("Khôi phục trước khi sao lưu")

                    # 3. Restored ledger shows COMPLETED reset state & events.
                    tabs_nav.get_by_role("link", name="Lịch sử & Làm mới tháng").click()
                    expect(r_page.get_by_role("heading", name="Làm mới hạn mức đầu tháng")).to_be_visible()
                    expect(r_page.locator("main")).to_contain_text("Đã làm mới")
                    expect(r_page.get_by_role("button", name="Mô phỏng làm mới tháng hiện tại")).to_be_disabled()
                    assert_qta_dom_invariants(r_page)

                    # 4. Runtime writes still work after restore: new suspension succeeds & renders ĐÃ CẮT.
                    susp_resp = fetch(
                        r_page,
                        restored_stack,
                        "POST",
                        f"/qta/users/{stacked['id']}/suspensions",
                        {
                            "scope": "PAID_EXTERNAL_ONLY",
                            "reason": "Tạm ngưng sau khôi phục",
                            "ordered_by": "Ban Giám hiệu",
                        },
                    )
                    assert susp_resp.status == 201, susp_resp.text()
                    tabs_nav.get_by_role("link", name="Tra cứu cá nhân & tạm ngưng").click()
                    expect(r_page.locator("tr", has_text="q6.stacked")).to_contain_text("ĐÃ CẮT")

                    # 5. Repeating manual reset still returns 409 QTA_RESET_ALREADY_EXECUTED.
                    repeat_reset = fetch(r_page, restored_stack, "POST", "/qta/monthly-resets")
                    assert repeat_reset.status == 409, repeat_reset.text()
                    assert repeat_reset.json()["code"] == "QTA_RESET_ALREADY_EXECUTED"
                finally:
                    r_ctx.close()
    finally:
        backup.unlink(missing_ok=True)
