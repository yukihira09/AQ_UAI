"""M6: Chromium checks of "Cấu hình Nhà cung cấp & Mô hình AI" through nginx.

The internal provider is the loopback HTTPS fake from the API test suite. The external
provider's connection test is intercepted in the browser (Playwright route), so no DNS
lookup or request ever leaves the machine and nothing can be billed.
"""

import json
import re

from playwright.sync_api import expect

from .conftest import PERSONAL, TEMPORARY, connect
from .test_admin import admin_session, capture, change_password, login

SECRET = "sk-browser-canary-7d41c2aa"
ROTATED = "sk-browser-canary-rotated-19be"
EXCLUDED = re.compile(r"prompt|temperature|template|creativ|lời nhắc|độ sáng tạo", re.IGNORECASE)


def api(page, stack, method, path, body=None):
    csrf = page.request.get(stack.admin + "/api/v1/auth/me").json()["csrf_token"]
    response = page.request.fetch(
        stack.admin + "/api/v1" + path, method=method, data=body,
        headers={"Origin": stack.admin, "X-CSRF-Token": csrf},
    )
    assert response.ok, (path, response.status)
    return response.json() if response.status != 204 else None


def model_admin(page, stack, browser):
    """The foundation admin creates the MDL administrator (two-step bootstrap)."""
    admin_session(page, stack)
    expect(page.get_by_role("link", name="Cấu hình Nhà cung cấp & Mô hình AI")).to_have_count(0)
    page.evaluate("location.hash = '#mdl'")
    expect(page.get_by_role("alert")).to_contain_text("không có quyền")
    unit = api(page, stack, "POST", "/units", {"code": "AI", "name": "Phòng AI"})
    user = api(page, stack, "POST", "/users", {
        "primary_unit_id": unit["id"], "username": "ai.admin", "display_name": "Quản trị AI",
        "code_type": "STAFF", "institutional_code": "AI-01", "temporary_password": TEMPORARY,
    })
    api(page, stack, "POST", f"/users/{user['id']}/role-assignments",
        {"role_code": "AI_MODEL_ADMIN", "scope": "GLOBAL", "unit_id": None})
    context = browser.new_context(locale="vi-VN")
    mdl_page = context.new_page()
    mdl_page.goto(stack.admin)
    login(mdl_page, "ai.admin", TEMPORARY)
    change_password(mdl_page, TEMPORARY, PERSONAL)
    login(mdl_page, "ai.admin", PERSONAL)
    expect(mdl_page.get_by_role("heading", name="Tổng quan")).to_be_visible()
    return context, mdl_page


def open_dialog(page, name):
    page.get_by_role("button", name=name, exact=True).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    return dialog


def save(dialog, name):
    dialog.get_by_role("button", name=name, exact=True).click()
    try:
        expect(dialog).to_have_count(0)
    except AssertionError:
        alert = dialog.get_by_role("alert")
        state = dialog.evaluate("d => [d.querySelector('form').checkValidity(), d.querySelector('form').getAttribute('aria-busy'),"
                                " [...d.querySelectorAll('input,select')].map(e => e.name + ':' + e.validationMessage)]")
        raise AssertionError(alert.inner_text() if alert.is_visible() else f"dialog still open {state}") from None


def assert_no_excluded_fields(page):
    """FR-MDL-040: no prompt, temperature or template control anywhere on the page."""
    controls = page.evaluate(
        "[...document.querySelectorAll('input, select, textarea')].map(e =>"
        " [e.name, e.id, e.labels?.[0]?.textContent ?? ''].join(' '))"
    )
    assert not [text for text in controls if EXCLUDED.search(text)]


def assert_secret_never_shown(page):
    html = page.content()
    assert SECRET not in html and ROTATED not in html
    for value in page.evaluate("[...document.querySelectorAll('input')].map(e => e.value)"):
        assert SECRET not in value and ROTATED not in value


def choose(select, text):
    """Select the option whose visible text contains ``text``."""
    value = select.locator("option", has_text=text).first.get_attribute("value")
    select.select_option(value)


def tab(page, name):
    """Open a tab and wait until the new view (not the previous one) is rendered."""
    link = page.get_by_role("navigation", name="Mục cấu hình AI").get_by_role("link", name=name, exact=True)
    link.click()
    expect(link).to_have_attribute("aria-current", "page")
    expect(page.locator(".content")).not_to_have_attribute("aria-busy", "true")


def test_internal_provider_model_test_routing_and_guards(page, mdl_stack, browser):
    stack = mdl_stack
    context, mdl = model_admin(page, stack, browser)
    try:
        mdl.get_by_role("link", name="Cấu hình Nhà cung cấp & Mô hình AI").first.click()
        expect(mdl.get_by_role("heading", name="Cấu hình Nhà cung cấp & Mô hình AI")).to_be_visible()
        expect(mdl.get_by_text("Chưa cấu hình", exact=True).first).to_be_visible()
        expect(mdl.get_by_text("Sẵn sàng", exact=True)).to_be_visible()  # key ring
        capture(mdl, "m6-01-routing-empty")

        # Providers: empty state, then an internal provider with a secret (https only).
        tab(mdl, "Nhà cung cấp")
        expect(mdl.get_by_text("Không tìm thấy bản ghi phù hợp.")).to_be_visible()
        dialog = open_dialog(mdl, "Thêm nhà cung cấp")
        secret_input = dialog.get_by_label("Bí mật kết nối")
        assert secret_input.get_attribute("type") == "password"
        assert secret_input.get_attribute("autocomplete") == "new-password"
        dialog.get_by_label("Tên nhà cung cấp").fill("Máy chủ AI nội bộ")
        dialog.get_by_label("Loại", exact=True).select_option("INTERNAL")
        dialog.get_by_label("Địa chỉ kết nối (URL gốc của API)").fill("http://127.0.0.1:1/v1")
        secret_input.fill(SECRET)
        dialog.get_by_role("button", name="Thêm nhà cung cấp").click()
        expect(dialog.get_by_role("alert")).to_contain_text("phải dùng https")  # no secret over http
        assert secret_input.input_value() == ""  # cleared after submit
        dialog.get_by_label("Địa chỉ kết nối (URL gốc của API)").fill(stack.provider.url())
        secret_input.fill(SECRET)
        save(dialog, "Thêm nhà cung cấp")
        expect(mdl.get_by_text("Đã lưu (được ẩn)")).to_be_visible()
        assert_secret_never_shown(mdl)
        mdl.get_by_role("link", name="Máy chủ AI nội bộ").click()
        expect(mdl.get_by_text("Nhà cung cấp nội bộ không cần thỏa thuận này.")).to_be_visible()

        # FR-MDL-010 AC2: reopened form has an empty secret; saving keeps the old one.
        dialog = open_dialog(mdl, "Sửa nhà cung cấp")
        assert dialog.get_by_label("Bí mật kết nối").input_value() == ""
        assert_secret_never_shown(mdl)
        dialog.get_by_label("Tên nhà cung cấp").fill("Máy chủ AI nội bộ 2")
        save(dialog, "Lưu thay đổi")
        expect(mdl.get_by_role("heading", name="Máy chủ AI nội bộ 2")).to_be_visible()

        # Models: create, not eligible until tested and classified.
        dialog = open_dialog(mdl, "Thêm mô hình")
        dialog.get_by_label("Mã kỹ thuật của mô hình").fill("local-llm")
        dialog.get_by_label("Tên hiển thị").fill("Mô hình nội bộ")
        assert dialog.get_by_label("Văn bản").is_checked()
        assert_no_excluded_fields(mdl)
        save(dialog, "Thêm mô hình")
        mdl.get_by_role("link", name="Mô hình nội bộ").click()
        expect(mdl.get_by_text("Chưa thử kết nối", exact=True)).to_be_visible()
        expect(mdl.get_by_text("Chưa phân loại rủi ro", exact=True)).to_be_visible()

        # Connection test (internal: no cost acknowledgement), real request to the fake.
        dialog = open_dialog(mdl, "Thử kết nối")
        expect(dialog.get_by_text("Thông báo chi phí")).to_have_count(0)
        save(dialog, "Thử kết nối")
        expect(mdl.get_by_role("status").filter(has_text="Thử kết nối thành công.")).to_be_visible()
        assert stack.provider.requests[-1]["headers"]["authorization"] == f"Bearer {SECRET}"

        # Risk classification with internal guidance (D6); then eligible.
        dialog = open_dialog(mdl, "Phân loại rủi ro")
        dialog.get_by_text("Tiêu chí phân loại rủi ro (hướng dẫn nội bộ)").click()
        expect(dialog.get_by_text("không phải phân loại pháp lý")).to_be_visible()
        dialog.get_by_label("Mức rủi ro").select_option("LOW")
        save(dialog, "Lưu thay đổi")
        expect(mdl.get_by_text("Đủ điều kiện", exact=True)).to_be_visible()
        capture(mdl, "m6-02-model-detail")

        # An image-only model cannot be tested and is never offered for routing.
        tab(mdl, "Mô hình")
        dialog = open_dialog(mdl, "Thêm mô hình")
        dialog.get_by_label("Mã kỹ thuật của mô hình").fill("image-only")
        dialog.get_by_label("Tên hiển thị").fill("Mô hình ảnh")
        dialog.get_by_label("Văn bản").uncheck()
        dialog.get_by_label("Hình ảnh").check()
        save(dialog, "Thêm mô hình")
        mdl.get_by_role("link", name="Mô hình ảnh").click()
        expect(mdl.get_by_role("button", name="Thử kết nối")).to_be_disabled()

        # Routing: only eligible models are offered (FR-MDL-021 AC1).
        tab(mdl, "Mô hình chính & dự phòng")
        dialog = open_dialog(mdl, "Đổi mô hình chính / dự phòng")
        primary = dialog.get_by_label("Mô hình chính")
        expect(primary.locator("option")).to_have_count(2)  # "none" + the eligible model
        assert "Mô hình ảnh" not in primary.inner_text()
        choose(primary, "Mô hình nội bộ")
        choose(dialog.get_by_label("Mô hình dự phòng"), "Mô hình nội bộ")
        dialog.get_by_role("button", name="Lưu cấu hình").click()
        expect(dialog.get_by_role("alert")).to_contain_text("phải khác mô hình chính")
        dialog.get_by_label("Mô hình dự phòng").select_option("")
        dialog.get_by_label("Số văn bản quyết định (nếu có)").fill("QĐ-15/2026")
        save(dialog, "Lưu cấu hình")
        expect(mdl.get_by_text("Đang dùng mô hình chính", exact=True)).to_be_visible()
        capture(mdl, "m6-03-routing")

        # FR-MDL-012: a routed model cannot be deactivated; the message says where.
        tab(mdl, "Mô hình")
        mdl.get_by_role("link", name="Mô hình nội bộ").click()
        dialog = open_dialog(mdl, "Ngừng hoạt động")
        dialog.get_by_role("button", name="Ngừng hoạt động").click()
        expect(dialog.get_by_role("alert")).to_contain_text("mô hình chính")
        dialog.get_by_role("button", name="Hủy").click()

        # Rotation makes the test outdated: the route persists but is not used (D9).
        mdl.get_by_role("link", name="Máy chủ AI nội bộ 2").click()
        dialog = open_dialog(mdl, "Sửa nhà cung cấp")
        dialog.get_by_label("Bí mật kết nối").fill(ROTATED)
        save(dialog, "Lưu thay đổi")
        tab(mdl, "Mô hình chính & dự phòng")
        expect(mdl.get_by_text("Không có mô hình nào được phép dùng")).to_be_visible()
        expect(mdl.get_by_text(re.compile("Kết quả thử đã cũ"))).to_be_visible()
        assert_secret_never_shown(mdl)

        # History keeps the decision reference.
        tab(mdl, "Lịch sử thay đổi")
        expect(mdl.get_by_role("cell", name="QĐ-15/2026", exact=True)).to_be_visible()

        # M7 configuration history: field-by-field before/after, never the secret.
        changes = mdl.locator("section.panel", has=mdl.get_by_role("heading", name="Lịch sử cấu hình (so sánh trước / sau)"))
        expect(changes.get_by_text("Tên: Máy chủ AI nội bộ → Máy chủ AI nội bộ 2")).to_be_visible()
        expect(changes.get_by_text("Mức rủi ro: — → Thấp")).to_be_visible()
        expect(changes.get_by_role("cell", name="Thay bí mật kết nối", exact=True)).to_be_visible()
        assert_secret_never_shown(mdl)
        capture(mdl, "m7-01-configuration-history")
        assert_no_excluded_fields(mdl)

        # Mobile width: no page-level horizontal overflow.
        mdl.set_viewport_size({"width": 390, "height": 844})
        tab(mdl, "Mô hình chính & dự phòng")
        expect(mdl.get_by_text("Mô hình đang được dùng")).to_be_visible()
        # A long section title must wrap instead of pushing the session menu off screen.
        assert mdl.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        capture(mdl, "m6-04-mobile")
    finally:
        context.close()


def test_external_cost_acknowledgement_agreements_and_fail_closed_withdrawal(page, mdl_stack, browser):
    stack = mdl_stack
    context, mdl = model_admin(page, stack, browser)
    try:
        mdl.evaluate("location.hash = '#mdl/providers'")
        dialog = open_dialog(mdl, "Thêm nhà cung cấp")
        dialog.get_by_label("Tên nhà cung cấp").fill("Nhà cung cấp ngoài")
        dialog.get_by_label("Địa chỉ kết nối (URL gốc của API)").fill("https://api.example.invalid/v1")
        dialog.get_by_label("Bí mật kết nối").fill(SECRET)
        save(dialog, "Thêm nhà cung cấp")
        expect(mdl.get_by_text("Chưa có — chưa thử / dùng được")).to_be_visible()
        mdl.get_by_role("link", name="Nhà cung cấp ngoài").click()

        # DPA: record (with the "no legal review" notice).
        dialog = open_dialog(mdl, "Ghi nhận thỏa thuận")
        expect(dialog.get_by_text("không thẩm định giá trị pháp lý")).to_be_visible()
        dialog.get_by_label("Số văn bản thỏa thuận").fill("HĐ-DPA-01")
        save(dialog, "Ghi nhận")
        expect(mdl.get_by_role("cell", name="HĐ-DPA-01")).to_be_visible()

        # M7: pickers load every page. With 100 providers sorted before this one, the
        # earlier single 100-item request omitted it and preselected the wrong provider.
        provider_id = mdl.url.rsplit("/", 1)[1]
        for number in range(100):
            api(mdl, stack, "POST", "/mdl/providers", {
                "name": f"Bulk {number:03d}", "provider_type": "INTERNAL",
                "endpoint": "http://bulk-model-server:8080/v1", "auth_scheme": "NONE",
            })
        dialog = open_dialog(mdl, "Thêm mô hình")
        picker = dialog.get_by_label("Nhà cung cấp")
        expect(picker.locator("option")).to_have_count(101)
        assert picker.input_value() == provider_id
        dialog.get_by_label("Mã kỹ thuật của mô hình").fill("vendor-model")
        dialog.get_by_label("Tên hiển thị").fill("Mô hình ngoài")
        dialog.get_by_label("Mức rủi ro").select_option("MEDIUM")
        save(dialog, "Thêm mô hình")
        mdl.get_by_role("link", name="Mô hình ngoài").click()

        # D4: the cost notice must be acknowledged before a potentially billed call.
        sent = []

        def intercept(route):
            sent.append(json.loads(route.request.post_data or "{}"))
            route.fulfill(status=201, content_type="application/json", body=json.dumps({
                "id": "00000000-0000-0000-0000-000000000001", "model_id": "00000000-0000-0000-0000-000000000002",
                "status": "FAILED", "error_code": "DNS_FAILED", "http_status_class": None, "latency_ms": 3,
                "connection_version": 1, "credential_version": 1, "current": True,
                "started_by": "00000000-0000-0000-0000-000000000003",
                "started_at": "2026-11-26T00:00:00Z", "finished_at": "2026-11-26T00:00:01Z",
            }))

        mdl.route("**/api/v1/mdl/models/*/connection-tests", intercept)
        dialog = open_dialog(mdl, "Thử kết nối")
        expect(dialog.get_by_text("Thông báo chi phí")).to_be_visible()
        notice = dialog.get_by_role("note")
        expect(notice).to_contain_text("có thể tính phí")
        expect(notice).to_contain_text("không trừ hạn mức")
        dialog.get_by_role("button", name="Thử kết nối").click()  # unchecked: blocked by the form
        expect(dialog).to_be_visible()
        assert sent == []
        dialog.get_by_role("checkbox").check()
        save(dialog, "Thử kết nối")
        assert sent == [{"acknowledge_provider_charges": True}]
        expect(mdl.get_by_role("status").filter(has_text="Không phân giải được tên máy chủ")).to_be_visible()
        mdl.unroute("**/api/v1/mdl/models/*/connection-tests")

        # A prior successful test (as left by an authorized live run) makes it eligible.
        model_id = mdl.url.rsplit("/", 1)[1]
        with connect(stack.database.owner) as db:
            tenant, user = db.execute(
                "SELECT institution_id, id FROM users WHERE username = 'ai.admin'"
            ).fetchone()
            db.execute(
                "INSERT INTO mdl_connection_tests (institution_id, model_id, connection_version,"
                " credential_version, started_by, status, http_status_class, latency_ms, started_at,"
                " finished_at) VALUES (%s, %s, 1, 1, %s, 'PASSED', 2, 5, now() - interval '1 minute',"
                " now() - interval '59 seconds')",
                (tenant, model_id, user),
            )
        mdl.reload()
        expect(mdl.get_by_text("Đủ điều kiện", exact=True)).to_be_visible()
        api(mdl, stack, "PUT", "/mdl/routing", {"expected_revision": 0, "primary_model_id": model_id})

        # D5: withdrawal warns, keeps configuration and history, and stops use.
        mdl.get_by_role("link", name="Nhà cung cấp ngoài").click()
        dialog = open_dialog(mdl, "Thu hồi")
        expect(dialog.get_by_text(re.compile("sẽ KHÔNG được dùng"))).to_be_visible()
        save(dialog, "Thu hồi thỏa thuận")
        expect(mdl.get_by_role("status").filter(has_text="hiện không được dùng")).to_be_visible()
        tab(mdl, "Mô hình chính & dự phòng")
        expect(mdl.get_by_text("Không có mô hình nào được phép dùng")).to_be_visible()
        expect(mdl.get_by_text("Chưa có thỏa thuận dữ liệu còn hiệu lực")).to_be_visible()
        expect(mdl.get_by_role("link", name="Mô hình ngoài")).to_be_visible()  # still configured
        tab(mdl, "Thỏa thuận dữ liệu")
        expect(mdl.get_by_text("Chưa có — chưa thử / dùng được")).to_be_visible()
        assert_secret_never_shown(mdl)
        assert_no_excluded_fields(mdl)
        capture(mdl, "m6-05-withdrawn")
    finally:
        context.close()
