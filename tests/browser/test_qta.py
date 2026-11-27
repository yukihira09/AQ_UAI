"""Q5: Chromium checks of "Hạn mức AI theo Nhóm tài khoản" (#qta) through nginx.

Covers the four Q5 end-to-end groups (a: Access/RBAC + 375 px responsive, b: Groups/sync/
specialist/quotas/disablement, c: School budget/deficit + additive 1.000 + 3.000 = 4.000 +
zero-group NO_ENTITLEMENT, d: Kill-switch PAID_EXTERNAL_ONLY/restore/manual reset/events)
and asserts QTA wording, calendar-month-only controls, append-only tables, and
non-integrated consumption invariants in every test.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import expect

from .conftest import PERSONAL, TEMPORARY, connect
from .test_admin import admin_session, capture, change_password, login
from .test_mdl import api, choose, open_dialog, save

FORBIDDEN_TEXT = re.compile(
    r"\btokens?\b|\bcredits?\b|\bVND\b|\bUSD\b|\$|₫|học kỳ|đề tài|đợt thi|tín chỉ|chi phí|\bgiá\b",
    re.IGNORECASE,
)
FORBIDDEN_CONTROL = re.compile(
    r"semester|cycle|period|hoc.?ky|de.?tai|dot.?thi|\bexam\b|\bproject\b",
    re.IGNORECASE,
)
MUTATION_BUTTONS = (
    "Cập nhật tổng hạn mức tháng",
    "Đồng bộ nhóm từ Hệ thống",
    "Tạo nhóm AI chuyên biệt",
    "Lưu cấu hình hạn mức",
    "Đổi tên nhóm",
    "Ngừng hoạt động",
    "Kích hoạt lại",
    "Thêm thành viên",
    "Gỡ thành viên",
    "Cắt / tạm ngưng quyền AI",
    "Khôi phục quyền AI",
    "Mô phỏng làm mới tháng hiện tại",
)
APPEND_ONLY_SECTION_PREFIXES = (
    "Lịch sử phiên bản tổng hạn mức",
    "Lịch sử đồng bộ nhóm hệ thống",
    "Lịch sử tạm ngưng & khôi phục quyền AI",
    "Lịch sử các lần làm mới đầu tháng",
    "Nhật ký sự kiện hạn mức AI",
)


def current_and_next_months() -> tuple[str, str]:
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    cur = f"{now.year:04d}-{now.month:02d}"
    next_year, next_month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return cur, f"{next_year:04d}-{next_month:02d}"


def seed_mdl_models(stack) -> dict[str, str]:
    """Seed one EXTERNAL and one INTERNAL active MDL model directly via schema owner."""
    with connect(stack.database.owner) as db:
        institution_id = db.execute("SELECT id FROM institutions LIMIT 1").fetchone()[0]
        ext_provider = db.execute(
            "INSERT INTO mdl_providers (institution_id, name, provider_type, api_style, endpoint,"
            " auth_scheme, auth_header_name)"
            " VALUES (%s, 'Nhà cung cấp ngoài', 'EXTERNAL', 'OPENAI_COMPATIBLE',"
            " 'https://ext.example.test/v1', 'BEARER', NULL) RETURNING id",
            (institution_id,),
        ).fetchone()[0]
        int_provider = db.execute(
            "INSERT INTO mdl_providers (institution_id, name, provider_type, api_style, endpoint,"
            " auth_scheme, auth_header_name)"
            " VALUES (%s, 'Cụm nội bộ', 'INTERNAL', 'OPENAI_COMPATIBLE',"
            " 'https://int.example.test/v1', 'BEARER', NULL) RETURNING id",
            (institution_id,),
        ).fetchone()[0]
        m_ext = db.execute(
            "INSERT INTO mdl_models (institution_id, provider_id, technical_id, display_name,"
            " supports_text, max_output_tokens, risk_level)"
            " VALUES (%s, %s, 'ext-pro', 'Mô hình Ngoài Pro', true, 4096, 'LOW') RETURNING id",
            (institution_id, ext_provider),
        ).fetchone()[0]
        m_int = db.execute(
            "INSERT INTO mdl_models (institution_id, provider_id, technical_id, display_name,"
            " supports_text, max_output_tokens, risk_level)"
            " VALUES (%s, %s, 'int-base', 'Mô hình Nội bộ Base', true, 4096, 'LOW') RETURNING id",
            (institution_id, int_provider),
        ).fetchone()[0]
    return {"ext_id": str(m_ext), "int_id": str(m_int)}


def create_user_with_role(page, stack, unit_id, username, display_name, code, role_code, scope="GLOBAL", scope_unit_id=None):
    user = api(
        page,
        stack,
        "POST",
        "/users",
        {
            "primary_unit_id": unit_id,
            "username": username,
            "display_name": display_name,
            "code_type": "STAFF",
            "institutional_code": code,
            "temporary_password": TEMPORARY,
        },
    )
    if role_code is not None:
        api(
            page,
            stack,
            "POST",
            f"/users/{user['id']}/role-assignments",
            {"role_code": role_code, "scope": scope, "unit_id": scope_unit_id},
        )
    return user


def sign_in_new_browser(browser, stack, username):
    context = browser.new_context(locale="vi-VN")
    user_page = context.new_page()
    user_page.goto(stack.admin)
    login(user_page, username, TEMPORARY)
    change_password(user_page, TEMPORARY, PERSONAL)
    login(user_page, username, PERSONAL)
    expect(user_page.get_by_role("heading", name="Tổng quan")).to_be_visible()
    return context, user_page


def assert_qta_dom_invariants(page, *, require_unit_label: bool = True, check_consumption_cells: bool = False):
    """Enforce Q5 §5 wording, calendar-month-only controls, append-only tables & non-integrated usage."""
    expect(page.get_by_text("Đang tải tổng hạn mức tháng…")).to_have_count(0)
    expect(page.get_by_text("Đang tải dữ liệu…")).to_have_count(0)
    main_text = page.locator("main").inner_text()
    match = FORBIDDEN_TEXT.search(main_text)
    assert not match, f"Forbidden term rendered in #qta: {match.group(0)!r}"
    if require_unit_label:
        assert "đơn vị hạn mức" in main_text, "Expected 'đơn vị hạn mức' in visible QTA content"

    # Zero non-month cycle inputs.
    controls = page.evaluate(
        "[...document.querySelectorAll('main input, main select, main textarea')].map(e =>"
        " [e.name || '', e.id || '', e.labels?.[0]?.textContent || ''].join(' '))"
    )
    bad_controls = [text for text in controls if FORBIDDEN_CONTROL.search(text)]
    assert not bad_controls, f"Unexpected cycle/non-month control: {bad_controls}"

    # Zero progress bars anywhere in #qta.
    assert page.locator("main progress, main [role='progressbar']").count() == 0

    # Zero Edit/Delete buttons in append-only revision, sync, suspension, reset, or event tables.
    bad_history_buttons = page.evaluate(
        """prefixes => {
          const hits = [];
          for (const container of document.querySelectorAll('main section, main details')) {
            const heading = container.querySelector('h2, h3, summary')?.textContent?.trim() || '';
            if (!prefixes.some(p => heading.startsWith(p))) continue;
            for (const btn of container.querySelectorAll('tbody button')) {
              const label = btn.textContent.trim();
              if (/sửa|xóa|chỉnh|edit|delete|remove/i.test(label) || true) {
                hits.push([heading, label]);
              }
            }
          }
          return hits;
        }""",
        list(APPEND_ONLY_SECTION_PREFIXES),
    )
    assert not bad_history_buttons, f"Append-only history table rendered row buttons: {bad_history_buttons}"

    if check_consumption_cells:
        assert "Chưa tích hợp đo tiêu thụ thực tế" in main_text
        # Every "Tiêu thụ thực tế" table cell must hold only the non-integrated notice (never % or numbers).
        bad_cells = page.evaluate(
            """() => {
              const issues = [];
              for (const tbl of document.querySelectorAll('main table')) {
                const headers = [...tbl.querySelectorAll('thead th')].map(th => th.textContent.trim());
                const idx = headers.indexOf('Tiêu thụ thực tế');
                if (idx === -1) continue;
                for (const row of tbl.querySelectorAll('tbody tr')) {
                  const text = row.children[idx]?.textContent?.trim() || '';
                  if (text !== 'Chưa tích hợp đo tiêu thụ thực tế' || /%|\\d/.test(text)) {
                    issues.push(text);
                  }
                }
              }
              return issues;
            }"""
        )
        assert not bad_cells, f"Consumption cell leaked number or percentage: {bad_cells}"


def open_qta(page):
    """Click the QTA sidebar item under the flat Quản trị navigation."""
    page.get_by_role("navigation", name="Quản trị").get_by_role(
        "link", name="Hạn mức AI theo Nhóm tài khoản"
    ).click()


def test_qta_access_rbac_and_unit_viewer(page, stack, browser):
    """Q5a: MDL-only hidden/403; GLOBAL viewer read-only; UNIT viewer lookup-only & scoped."""
    admin_session(page, stack)
    seed_mdl_models(stack)
    unit_a = api(page, stack, "POST", "/units", {"code": "Q5UA", "name": "Khoa CNTT"})
    unit_b = api(page, stack, "POST", "/units", {"code": "Q5UB", "name": "Khoa Kinh tế"})

    create_user_with_role(page, stack, unit_a["id"], "q5.mdl", "Quản trị MDL", "Q5-MDL", "AI_MODEL_ADMIN")
    create_user_with_role(page, stack, unit_a["id"], "q5.gview", "Xem toàn trường", "Q5-GV", "AI_QUOTA_VIEWER", "GLOBAL")
    create_user_with_role(
        page, stack, unit_a["id"], "q5.uview", "Xem đơn vị A", "Q5-UV", "AI_QUOTA_VIEWER", "UNIT", unit_a["id"]
    )
    # Seed one target user in unit_a and one in unit_b so UNIT scoping is directly observable.
    api(
        page, stack, "POST", "/users",
        {
            "primary_unit_id": unit_a["id"], "username": "q5.student.a", "display_name": "Sinh viên Đơn vị A",
            "code_type": "STUDENT", "institutional_code": "SV-A01", "temporary_password": TEMPORARY,
        },
    )
    api(
        page, stack, "POST", "/users",
        {
            "primary_unit_id": unit_b["id"], "username": "q5.student.b", "display_name": "Sinh viên Đơn vị B",
            "code_type": "STUDENT", "institutional_code": "SV-B01", "temporary_password": TEMPORARY,
        },
    )

    # 1. MDL-only admin: QTA sidebar item absent; direct #qta navigation blocked with 403.
    mdl_ctx, mdl_page = sign_in_new_browser(browser, stack, "q5.mdl")
    try:
        expect(mdl_page.get_by_role("link", name="Hạn mức AI theo Nhóm tài khoản")).to_have_count(0)
        mdl_page.evaluate("location.hash = '#qta'")
        expect(mdl_page.get_by_role("alert")).to_contain_text("không có quyền")
    finally:
        mdl_ctx.close()

    # 2. GLOBAL AI_QUOTA_VIEWER: all 3 tabs + budget header visible; zero mutation controls.
    gv_ctx, gv_page = sign_in_new_browser(browser, stack, "q5.gview")
    try:
        open_qta(gv_page)
        budget_region = gv_page.get_by_role("region", name="Tổng hạn mức AI theo tháng của trường")
        expect(budget_region).to_be_visible()
        expect(budget_region).to_contain_text("Đang phân bổ hiện tại")
        tabs_nav = gv_page.get_by_role("navigation", name="Mục hạn mức AI")
        expect(tabs_nav.get_by_role("link", name="Nhóm & Hạn mức")).to_be_visible()
        expect(tabs_nav.get_by_role("link", name="Tra cứu cá nhân & tạm ngưng")).to_be_visible()
        expect(tabs_nav.get_by_role("link", name="Lịch sử & Làm mới tháng")).to_be_visible()
        for label in MUTATION_BUTTONS:
            expect(gv_page.get_by_role("button", name=label, exact=True)).to_have_count(0)
        assert_qta_dom_invariants(gv_page)

        tabs_nav.get_by_role("link", name="Tra cứu cá nhân & tạm ngưng").click()
        expect(gv_page.get_by_role("cell", name="Sinh viên Đơn vị A")).to_be_visible()
        gv_page.locator("tr", has_text="q5.student.a").get_by_role("button", name="Xem hạn mức").click()
        expect(gv_page.get_by_role("heading", name="Hạn mức cá nhân — Sinh viên Đơn vị A (q5.student.a)")).to_be_visible()
        for label in MUTATION_BUTTONS:
            expect(gv_page.get_by_role("button", name=label, exact=True)).to_have_count(0)
        assert_qta_dom_invariants(gv_page, check_consumption_cells=True)

        tabs_nav.get_by_role("link", name="Lịch sử & Làm mới tháng").click()
        expect(gv_page.get_by_role("heading", name="Làm mới hạn mức đầu tháng")).to_be_visible()
        expect(gv_page.get_by_role("region", name="Tổng hạn mức AI theo tháng của trường")).to_contain_text("Đang phân bổ hiện tại")
        for label in MUTATION_BUTTONS:
            expect(gv_page.get_by_role("button", name=label, exact=True)).to_have_count(0)
        assert_qta_dom_invariants(gv_page)
    finally:
        gv_ctx.close()

    # 3. UNIT-scoped AI_QUOTA_VIEWER: sees ONLY lookup tab, ONLY unit_a users, zero 403s, zero writes.
    uv_ctx, uv_page = sign_in_new_browser(browser, stack, "q5.uview")
    forbidden_responses = []
    uv_page.on("response", lambda resp: forbidden_responses.append((resp.status, resp.url)) if resp.status == 403 else None)
    try:
        open_qta(uv_page)
        expect(uv_page.get_by_role("heading", name="Chọn tháng tra cứu cá nhân")).to_be_visible()
        expect(uv_page.get_by_role("heading", name="Tổng hạn mức AI toàn trường theo tháng")).to_have_count(0)
        tabs_nav = uv_page.get_by_role("navigation", name="Mục hạn mức AI")
        expect(tabs_nav.get_by_role("link")).to_have_count(1)
        expect(tabs_nav.get_by_role("link", name="Tra cứu cá nhân & tạm ngưng")).to_be_visible()

        expect(uv_page.get_by_role("cell", name="Sinh viên Đơn vị A")).to_be_visible()
        expect(uv_page.get_by_role("cell", name="Sinh viên Đơn vị B")).to_have_count(0)
        uv_page.locator("tr", has_text="q5.student.a").get_by_role("button", name="Xem hạn mức").click()
        expect(uv_page.get_by_role("heading", name="Hạn mức cá nhân — Sinh viên Đơn vị A (q5.student.a)")).to_be_visible()
        for label in MUTATION_BUTTONS:
            expect(uv_page.get_by_role("button", name=label, exact=True)).to_have_count(0)
        assert not forbidden_responses, f"UNIT viewer triggered 403 responses: {forbidden_responses}"
        assert_qta_dom_invariants(uv_page, check_consumption_cells=True)
        capture(uv_page, "qta-unit-viewer-lookup")
    finally:
        uv_ctx.close()


def test_qta_groups_sync_specialist_and_quotas(page, stack, browser):
    """Q5b: sync SYSTEM groups, create specialist group, configure quotas, deactivate/reactivate & disablement."""
    admin_session(page, stack)
    models = seed_mdl_models(stack)
    unit = api(page, stack, "POST", "/units", {"code": "Q5GB", "name": "Đơn vị B"})
    create_user_with_role(page, stack, unit["id"], "q5.admin", "Quản trị QTA", "Q5-ADM", "AI_QUOTA_ADMIN")
    member = api(
        page, stack, "POST", "/users",
        {
            "primary_unit_id": unit["id"], "username": "q5.gv1", "display_name": "Giảng viên Một",
            "code_type": "STAFF", "institutional_code": "GV-01", "temporary_password": TEMPORARY,
        },
    )
    sys_group = api(
        page, stack, "POST", "/groups",
        {"code": "G_GV_SYS", "name": "Giảng viên Hệ thống", "kind": "SYSTEM"},
    )
    api(page, stack, "PUT", f"/groups/{sys_group['id']}/members/{member['id']}")

    ctx, qta_page = sign_in_new_browser(browser, stack, "q5.admin")
    try:
        open_qta(qta_page)
        expect(qta_page.get_by_role("heading", name="Danh sách nhóm áp dụng hạn mức AI")).to_be_visible()

        # Sync SYSTEM groups from directory.
        qta_page.get_by_role("button", name="Đồng bộ nhóm từ Hệ thống").click()
        expect(qta_page.get_by_role("status").first).to_contain_text("Đã đồng bộ nhóm hệ thống")
        expect(qta_page.get_by_role("link", name="Giảng viên Hệ thống")).to_be_visible()
        expect(qta_page.locator("section", has_text="Lịch sử đồng bộ nhóm hệ thống").locator("tbody tr")).to_have_count(1)

        # Create AI_SPECIALIST group.
        dialog = open_dialog(qta_page, "Tạo nhóm AI chuyên biệt")
        dialog.get_by_label("Mã nhóm").fill("AI_LAB_Q5")
        dialog.get_by_label("Tên nhóm").fill("Phòng thí nghiệm AI Q5")
        save(dialog, "Tạo nhóm")
        expect(qta_page.get_by_role("link", name="Phòng thí nghiệm AI Q5")).to_be_visible()
        capture(qta_page, "qta-admin-groups")
        assert_qta_dom_invariants(qta_page)

        # Open AI_SPECIALIST detail: add member, set quotas, deactivate then reactivate.
        qta_page.get_by_role("link", name="Phòng thí nghiệm AI Q5").click()
        expect(qta_page.get_by_role("heading", name="Phòng thí nghiệm AI Q5 (AI_LAB_Q5)")).to_be_visible()

        add_dlg = open_dialog(qta_page, "Thêm thành viên")
        expect(add_dlg.locator("select option", has_text="Giảng viên Một")).to_have_count(1)
        choose(add_dlg.get_by_label("Tài khoản", exact=True), "Giảng viên Một")
        save(add_dlg, "Thêm thành viên")
        expect(qta_page.get_by_role("cell", name="Giảng viên Một")).to_be_visible()

        qta_page.get_by_label("Bật hạn mức cho Mô hình Ngoài Pro").check()
        qta_page.get_by_label("Hạn mức tháng cho Mô hình Ngoài Pro (đơn vị hạn mức)").fill("3000")
        qta_page.get_by_label("Ngưỡng cảnh báo (%) cho Mô hình Ngoài Pro").fill("80")
        qta_page.get_by_role("button", name="Lưu cấu hình hạn mức").click()
        expect(qta_page.get_by_role("status").first).to_contain_text("Đã lưu cấu hình hạn mức")
        # Reviewer F-Q5-1: only the configured model is stored; the untouched internal model
        # gets no permanent disabled/0 row (quota rows are never deleted).
        specialist_id = qta_page.evaluate("location.hash").rsplit("/", 1)[-1]
        stored = api(qta_page, stack, "GET", f"/qta/groups/{specialist_id}")["quotas"]
        assert [rule["model_id"] for rule in stored] == [models["ext_id"]], stored

        deact_dlg = open_dialog(qta_page, "Ngừng hoạt động")
        save(deact_dlg, "Xác nhận ngừng hoạt động")
        expect(qta_page.get_by_role("button", name="Kích hoạt lại")).to_be_visible()

        act_dlg = open_dialog(qta_page, "Kích hoạt lại")
        save(act_dlg, "Xác nhận kích hoạt")
        expect(qta_page.get_by_role("button", name="Ngừng hoạt động")).to_be_visible()
        assert_qta_dom_invariants(qta_page)

        # Open synced SYSTEM group detail: no specialist rename/deactivate/member controls; test quota disablement.
        qta_page.get_by_role("link", name="← Quay lại danh sách nhóm hạn mức").click()
        qta_page.get_by_role("link", name="Giảng viên Hệ thống").click()
        expect(qta_page.get_by_role("button", name="Đổi tên nhóm")).to_have_count(0)
        expect(qta_page.get_by_role("button", name="Ngừng hoạt động")).to_have_count(0)
        expect(qta_page.get_by_role("button", name="Thêm thành viên")).to_have_count(0)

        qta_page.get_by_label("Bật hạn mức cho Mô hình Nội bộ Base").check()
        qta_page.get_by_label("Hạn mức tháng cho Mô hình Nội bộ Base (đơn vị hạn mức)").fill("1500")
        qta_page.get_by_role("button", name="Lưu cấu hình hạn mức").click()
        expect(qta_page.get_by_role("status").first).to_contain_text("Đã lưu cấu hình hạn mức")

        # Disable the model rule on the SYSTEM group -> member's base entitlement for that model drops to 0.
        qta_page.get_by_label("Bật hạn mức cho Mô hình Nội bộ Base").uncheck()
        qta_page.get_by_role("button", name="Lưu cấu hình hạn mức").click()
        expect(qta_page.get_by_role("status").first).to_contain_text("Đã lưu cấu hình hạn mức")

        qta_page.get_by_role("navigation", name="Mục hạn mức AI").get_by_role("link", name="Tra cứu cá nhân & tạm ngưng").click()
        qta_page.locator("tr", has_text="q5.gv1").get_by_role("button", name="Xem hạn mức").click()
        base_row = qta_page.locator("tr", has_text="Mô hình Nội bộ Base")
        expect(base_row).to_contain_text("0 đơn vị hạn mức")
        expect(base_row).to_contain_text("quy tắc đang tắt")
        assert_qta_dom_invariants(qta_page, check_consumption_cells=True)
    finally:
        ctx.close()


def test_qta_budget_deficit_additive_and_mobile(page, stack, browser):
    """Q5c: school monthly budget, 409 deficit details, additive 1.000 + 3.000 = 4.000, zero-group & 375 px."""
    admin_session(page, stack)
    models = seed_mdl_models(stack)
    unit = api(page, stack, "POST", "/units", {"code": "Q5GC", "name": "Đơn vị C"})
    create_user_with_role(page, stack, unit["id"], "q5.adm.c", "Quản trị QTA C", "Q5-ADMC", "AI_QUOTA_ADMIN")
    stacked = api(
        page, stack, "POST", "/users",
        {
            "primary_unit_id": unit["id"], "username": "q5.stacked", "display_name": "Nguyễn Cộng Dồn",
            "code_type": "STAFF", "institutional_code": "CD-01", "temporary_password": TEMPORARY,
        },
    )
    api(
        page, stack, "POST", "/users",
        {
            "primary_unit_id": unit["id"], "username": "q5.solo", "display_name": "Trần Chưa Nhóm",
            "code_type": "STUDENT", "institutional_code": "SL-01", "temporary_password": TEMPORARY,
        },
    )
    g1 = api(page, stack, "POST", "/groups", {"code": "G1", "name": "Nhóm Cơ Bản", "kind": "SYSTEM"})
    api(page, stack, "PUT", f"/groups/{g1['id']}/members/{stacked['id']}")

    ctx, qta_page = sign_in_new_browser(browser, stack, "q5.adm.c")
    try:
        # Prepare G1 (1.000) + G2 (3.000) via QTA API so the browser test focuses on budget & lookup UX.
        api(qta_page, stack, "POST", "/qta/groups/sync")
        api(
            qta_page, stack, "PUT", f"/qta/groups/{g1['id']}/quotas",
            {"quotas": [{"model_id": models["ext_id"], "enabled": True, "monthly_limit": 1000}]},
        )
        g2 = api(qta_page, stack, "POST", "/qta/groups", {"code": "G2", "name": "Nhóm Nghiên Cứu"})
        api(qta_page, stack, "PUT", f"/qta/groups/{g2['id']}/members/{stacked['id']}")
        api(
            qta_page, stack, "PUT", f"/qta/groups/{g2['id']}/quotas",
            {"quotas": [{"model_id": models["ext_id"], "enabled": True, "monthly_limit": 3000}]},
        )

        open_qta(qta_page)
        budget_panel = qta_page.get_by_role("region", name="Tổng hạn mức AI theo tháng của trường")
        expect(budget_panel).to_contain_text("4.000 đơn vị hạn mức")
        expect(budget_panel).to_contain_text("chưa ghi nhận")

        # FR-QTA-010 AC2 (reviewer addition): missing decision number -> nothing is saved.
        no_number = open_dialog(qta_page, "Cập nhật tổng hạn mức tháng")
        no_number.get_by_label("Tổng hạn mức tháng (đơn vị hạn mức)").fill("10000")
        no_number.get_by_label("Số quyết định").fill("")
        no_number.get_by_role("button", name="Ghi nhận tổng hạn mức", exact=True).click()
        expect(no_number).to_be_visible()
        assert no_number.get_by_label("Số quyết định").evaluate("e => !e.validity.valid")
        no_number.get_by_role("button", name="Hủy").click()
        expect(no_number).to_have_count(0)
        expect(budget_panel).to_contain_text("chưa ghi nhận")

        # Set budget to 10.000 -> recorded revision #1, remaining 6.000.
        dlg = open_dialog(qta_page, "Cập nhật tổng hạn mức tháng")
        dlg.get_by_label("Tổng hạn mức tháng (đơn vị hạn mức)").fill("10000")
        dlg.get_by_label("Số quyết định").fill("QD-Q5-01")
        save(dlg, "Ghi nhận tổng hạn mức")
        expect(budget_panel).to_contain_text("Đã ghi nhận")
        expect(budget_panel).to_contain_text("10.000 đơn vị hạn mức")
        expect(budget_panel).to_contain_text("6.000 đơn vị hạn mức")
        expect(budget_panel).to_contain_text("QD-Q5-01")

        # Attempt to lower budget to 2.500 (< 4.000 allocated) -> 409 alert with allocated & deficit!
        low_dlg = open_dialog(qta_page, "Cập nhật tổng hạn mức tháng")
        low_dlg.get_by_label("Tổng hạn mức tháng (đơn vị hạn mức)").fill("2500")
        low_dlg.get_by_label("Số quyết định").fill("QD-Q5-02")
        low_dlg.get_by_role("button", name="Ghi nhận tổng hạn mức", exact=True).click()
        alert = low_dlg.get_by_role("alert")
        expect(alert).to_be_visible()
        expect(alert).to_contain_text("4.000 đơn vị hạn mức")
        expect(alert).to_contain_text("1.500 đơn vị hạn mức")
        expect(alert).to_contain_text("Mã yêu cầu")
        low_dlg.get_by_role("button", name="Hủy").click()
        expect(low_dlg).to_have_count(0)
        assert_qta_dom_invariants(qta_page)

        # Lookup tab: exact two-month selector (current & next), additive 1.000 + 3.000 = 4.000, zero-group.
        qta_page.get_by_role("navigation", name="Mục hạn mức AI").get_by_role("link", name="Tra cứu cá nhân & tạm ngưng").click()
        cur_m, next_m = current_and_next_months()
        month_select = qta_page.get_by_label("Tháng tra cứu hạn mức cá nhân")
        expect(month_select).to_be_visible()
        option_values = month_select.locator("option").evaluate_all("opts => opts.map(o => o.value)")
        assert option_values == [cur_m, next_m], f"Expected exact 2-month selector {[cur_m, next_m]}, got {option_values}"

        qta_page.locator("tr", has_text="q5.stacked").get_by_role("button", name="Xem hạn mức").click()
        expect(qta_page.get_by_role("heading", name="Hạn mức cá nhân — Nguyễn Cộng Dồn (q5.stacked)")).to_be_visible()
        ext_row = qta_page.locator("tr", has_text="Mô hình Ngoài Pro")
        expect(ext_row).to_contain_text("4.000 đơn vị hạn mức")
        expect(ext_row).to_contain_text("1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn mức")
        expect(ext_row).to_contain_text("Được phép")
        expect(ext_row).to_contain_text("Chưa tích hợp đo tiêu thụ thực tế")
        assert_qta_dom_invariants(qta_page, check_consumption_cells=True)
        capture(qta_page, "qta-admin-lookup")

        # 375 px mobile viewport: zero horizontal page scroll.
        qta_page.set_viewport_size({"width": 375, "height": 812})
        qta_page.wait_for_timeout(150)
        overflow = qta_page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert overflow[0] <= overflow[1], f"Horizontal overflow at 375 px: {overflow}"
        capture(qta_page, "qta-lookup-mobile-375")
        qta_page.set_viewport_size({"width": 1280, "height": 900})

        # Zero-group user: 0 đơn vị hạn mức + NO_ENTITLEMENT.
        qta_page.locator("tr", has_text="q5.solo").get_by_role("button", name="Xem hạn mức").click()
        expect(qta_page.get_by_role("heading", name="Hạn mức cá nhân — Trần Chưa Nhóm (q5.solo)")).to_be_visible()
        expect(qta_page.locator("main")).to_contain_text("Tài khoản chưa thuộc nhóm hạn mức AI nào")
        solo_ext_row = qta_page.locator("tr", has_text="Mô hình Ngoài Pro")
        expect(solo_ext_row).to_contain_text("0 đơn vị hạn mức")
        expect(solo_ext_row).to_contain_text("NO_ENTITLEMENT")
        assert_qta_dom_invariants(qta_page, check_consumption_cells=True)
    finally:
        ctx.close()


def test_qta_killswitch_restore_reset_and_events(page, stack, browser):
    """Q5d: PAID_EXTERNAL_ONLY suspend (distinct operator vs ordered_by), restore, manual reset & events."""
    admin_session(page, stack)
    models = seed_mdl_models(stack)
    unit = api(page, stack, "POST", "/units", {"code": "Q5GD", "name": "Đơn vị D"})
    create_user_with_role(page, stack, unit["id"], "q5.adm.d", "Quản trị QTA D", "Q5-ADMD", "AI_QUOTA_ADMIN")
    target = api(
        page, stack, "POST", "/users",
        {
            "primary_unit_id": unit["id"], "username": "q5.target", "display_name": "Lê Đối Tượng",
            "code_type": "STAFF", "institutional_code": "DT-01", "temporary_password": TEMPORARY,
        },
    )

    ctx, qta_page = sign_in_new_browser(browser, stack, "q5.adm.d")
    try:
        grp = api(qta_page, stack, "POST", "/qta/groups", {"code": "AI_BOTH", "name": "Nhóm Hai Mô Hình"})
        api(qta_page, stack, "PUT", f"/qta/groups/{grp['id']}/members/{target['id']}")
        api(
            qta_page, stack, "PUT", f"/qta/groups/{grp['id']}/quotas",
            {
                "quotas": [
                    {"model_id": models["ext_id"], "enabled": True, "monthly_limit": 2000},
                    {"model_id": models["int_id"], "enabled": True, "monthly_limit": 1500},
                ]
            },
        )

        open_qta(qta_page)
        qta_page.get_by_role("navigation", name="Mục hạn mức AI").get_by_role("link", name="Tra cứu cá nhân & tạm ngưng").click()
        qta_page.locator("tr", has_text="q5.target").get_by_role("button", name="Xem hạn mức").click()
        expect(qta_page.get_by_role("heading", name="Hạn mức cá nhân — Lê Đối Tượng (q5.target)")).to_be_visible()

        # FR-QTA-040 AC3 (reviewer addition): missing reason or ordered_by -> not suspended.
        for filled, empty in (("Lý do tạm ngưng", "Người ra lệnh"), ("Người ra lệnh", "Lý do tạm ngưng")):
            bad_dlg = open_dialog(qta_page, "Cắt / tạm ngưng quyền AI")
            bad_dlg.get_by_label(filled).fill("Đã điền")
            bad_dlg.get_by_role("button", name="Xác nhận tạm ngưng", exact=True).click()
            expect(bad_dlg).to_be_visible()
            assert bad_dlg.get_by_label(empty).evaluate("e => !e.validity.valid"), empty
            bad_dlg.get_by_role("button", name="Hủy").click()
            expect(bad_dlg).to_have_count(0)
        expect(qta_page.get_by_role("button", name="Cắt / tạm ngưng quyền AI")).to_be_visible()

        # Suspend with PAID_EXTERNAL_ONLY: verify read-only operator != editable ordered_by.
        susp_dlg = open_dialog(qta_page, "Cắt / tạm ngưng quyền AI")
        expect(susp_dlg.get_by_test_id("qta-suspend-operator")).to_contain_text("Quản trị QTA D (q5.adm.d)")
        susp_dlg.get_by_label("Phạm vi tạm ngưng").select_option("PAID_EXTERNAL_ONLY")
        susp_dlg.get_by_label("Lý do tạm ngưng").fill("Kiểm tra tạm ngưng mô hình ngoài")
        susp_dlg.get_by_label("Người ra lệnh").fill("Hiệu trưởng")
        save(susp_dlg, "Xác nhận tạm ngưng")

        expect(qta_page.locator("main")).to_contain_text("Đang tạm ngưng")
        expect(qta_page.locator("main")).to_contain_text("Người ra lệnh: Hiệu trưởng")
        # EXTERNAL blocked, INTERNAL still allowed, base entitlements untouched!
        ext_row = qta_page.locator("tr", has_text="Mô hình Ngoài Pro")
        int_row = qta_page.locator("tr", has_text="Mô hình Nội bộ Base")
        expect(ext_row).to_contain_text("2.000 đơn vị hạn mức")
        expect(ext_row).to_contain_text("Tạm ngưng mô hình ngoài trường")
        expect(int_row).to_contain_text("1.500 đơn vị hạn mức")
        expect(int_row).to_contain_text("Được phép")
        assert_qta_dom_invariants(qta_page, check_consumption_cells=True)

        # Restore and confirm both models allowed again while base entitlement stays unchanged.
        rest_dlg = open_dialog(qta_page, "Khôi phục quyền AI")
        rest_dlg.get_by_label("Ghi chú khôi phục (tùy chọn)").fill("Đã hoàn tất rà soát")
        save(rest_dlg, "Xác nhận khôi phục")
        expect(qta_page.locator("tr", has_text="Mô hình Ngoài Pro")).to_contain_text("Được phép")
        expect(qta_page.locator("tr", has_text="Mô hình Ngoài Pro")).to_contain_text("2.000 đơn vị hạn mức")
        expect(qta_page.locator("section", has_text="Lịch sử tạm ngưng & khôi phục quyền AI")).to_contain_text("Đã hoàn tất rà soát")

        # Ledger & monthly reset tab: simulate manual reset once, verify events & append-only tables.
        qta_page.get_by_role("navigation", name="Mục hạn mức AI").get_by_role("link", name="Lịch sử & Làm mới tháng").click()
        expect(qta_page.get_by_role("heading", name="Làm mới hạn mức đầu tháng")).to_be_visible()
        expect(qta_page.locator("main")).to_contain_text("Chưa làm mới")
        assert qta_page.locator("input#qta-events-month[type='month']").count() == 1

        reset_dlg = open_dialog(qta_page, "Mô phỏng làm mới tháng hiện tại")
        save(reset_dlg, "Xác nhận làm mới tháng")
        expect(qta_page.locator("main")).to_contain_text("Đã làm mới")
        expect(qta_page.get_by_role("button", name="Mô phỏng làm mới tháng hiện tại")).to_be_disabled()

        events_section = qta_page.locator("section", has_text="Nhật ký sự kiện hạn mức AI")
        expect(events_section).to_contain_text("Làm mới đầu tháng")
        expect(events_section).to_contain_text("Khôi phục quyền AI")
        expect(events_section).to_contain_text("Tạm ngưng quyền AI")
        assert_qta_dom_invariants(qta_page)
        capture(qta_page, "qta-admin-ledger")
    finally:
        ctx.close()
