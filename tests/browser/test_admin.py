"""Chromium checks for session and directory workflows served through nginx."""

import os
import re
from pathlib import Path

from playwright.sync_api import expect

from .conftest import PERSONAL, TEMPORARY, connect


def capture(page, screen):
    output = os.getenv("AQ_BROWSER_SCREENSHOTS")
    if output:
        directory = Path(output)
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=directory / f"{screen}.png", animations="disabled", full_page=True)


def login(page, username, password):
    page.get_by_label("Tên đăng nhập", exact=True).fill(username)
    page.get_by_label("Mật khẩu", exact=True).fill(password)
    page.get_by_role("button", name="Đăng nhập", exact=True).click()


def change_password(page, current, new):
    expect(page.get_by_role("heading", name="Đổi mật khẩu")).to_be_visible()
    page.get_by_label("Mật khẩu hiện tại").fill(current)
    page.get_by_label("Mật khẩu mới", exact=True).fill(new)
    page.get_by_label("Xác nhận mật khẩu mới").fill(new)
    page.get_by_role("button", name="Lưu mật khẩu").click()
    expect(page.get_by_role("heading", name="Đăng nhập")).to_be_visible()


def admin_session(page, stack):
    page.goto(stack.admin)
    login(page, "admin", TEMPORARY)
    change_password(page, TEMPORARY, PERSONAL)
    login(page, "admin", PERSONAL)
    expect(page.get_by_role("heading", name="Tổng quan")).to_be_visible()


def test_login_password_change_refresh_and_logout(page, stack):
    page.goto(stack.admin)
    expect(page.get_by_role("heading", name="Đăng nhập")).to_be_visible()
    capture(page, "01-login")
    login(page, "admin", "incorrect-password")
    expect(page.get_by_role("alert")).to_contain_text("Tên đăng nhập hoặc mật khẩu")
    login(page, "admin", TEMPORARY)
    expect(page.get_by_role("heading", name="Đổi mật khẩu")).to_be_visible()
    capture(page, "02-password-change")
    page.get_by_label("Mật khẩu hiện tại").fill("incorrect-password")
    page.get_by_label("Mật khẩu mới", exact=True).fill(PERSONAL)
    page.get_by_label("Xác nhận mật khẩu mới").fill(PERSONAL)
    page.get_by_role("button", name="Lưu mật khẩu").click()
    expect(page.get_by_role("alert")).to_contain_text("Mật khẩu hiện tại không đúng")
    expect(page.get_by_role("heading", name="Đổi mật khẩu")).to_be_visible()
    page.evaluate("location.hash = '#users'")
    expect(page.get_by_role("link", name="Tài khoản")).to_have_count(0)
    assert page.request.get(stack.admin + "/api/v1/users").status == 403
    change_password(page, TEMPORARY, PERSONAL)
    assert page.request.get(stack.admin + "/api/v1/auth/me").status == 401
    login(page, "admin", PERSONAL)
    expect(page.get_by_role("heading", name="Tổng quan")).to_be_visible()
    expect(page.get_by_text("Xin chào, Quản trị viên")).to_be_visible()
    capture(page, "03-overview")
    page.reload()
    expect(page.get_by_role("heading", name="Tổng quan")).to_be_visible()
    assert page.evaluate("[localStorage.length, sessionStorage.length]") == [0, 0]
    assert page.evaluate("indexedDB.databases().then(databases => databases.length)") == 0
    cookie = next(
        item for item in page.context.cookies(stack.admin) if item["name"] == "aq_uai_session"
    )
    assert (
        cookie["httpOnly"] and cookie["domain"] == "admin.localhost" and cookie["sameSite"] == "Lax"
    )
    assert not page.context.cookies(stack.demo)
    assert "aq_uai_session" not in page.evaluate("document.cookie")
    page.locator('summary[aria-label="Phiên đăng nhập"]').click()
    page.get_by_role("button", name="Đăng xuất").click()
    expect(page.get_by_role("heading", name="Đăng nhập")).to_be_visible()
    assert page.request.get(stack.admin + "/api/v1/auth/me").status == 401


def test_throttling_and_session_expiry_feedback(page, stack):
    admin_session(page, stack)
    for index in range(6):
        with page.context.browser.new_context() as attempt:
            guest = attempt.new_page()
            guest.goto(stack.admin)
            login(guest, "khong-ton-tai", "incorrect-password")
            expect(guest.get_by_role("alert")).to_contain_text(
                "Quá nhiều lần" if index == 5 else "Tên đăng nhập hoặc mật khẩu"
            )
    with connect(stack.database.owner) as db:
        db.execute(
            "UPDATE auth_sessions SET issued_at = now() - interval '9 hours', expires_at = now() - interval '1 hour' WHERE revoked_at IS NULL"
        )
    page.get_by_role("navigation").get_by_role("link", name="Tài khoản", exact=True).click()
    expect(page.get_by_role("heading", name="Đăng nhập")).to_be_visible()
    expect(page.get_by_role("status")).to_contain_text("Phiên đăng nhập đã hết hạn")


def test_navigation_refreshes_identity_after_another_tab_replaces_cookie(page, stack):
    admin_session(page, stack)
    me = page.request.get(stack.admin + "/api/v1/auth/me").json()
    write_api(
        page,
        stack,
        "POST",
        "/users",
        {
            "primary_unit_id": me["primary_unit_id"],
            "username": "other",
            "display_name": "Người dùng khác",
            "code_type": "STAFF",
            "institutional_code": "OTHER",
            "temporary_password": TEMPORARY,
        },
    )
    other = page.context.new_page()
    other.goto(stack.admin)
    other.locator('summary[aria-label="Phiên đăng nhập"]').click()
    other.get_by_role("button", name="Đăng xuất").click()
    login(other, "other", TEMPORARY)
    change_password(other, TEMPORARY, PERSONAL)
    login(other, "other", PERSONAL)
    expect(other.get_by_text("Xin chào, Người dùng khác")).to_be_visible()
    page.evaluate("location.hash = '#users'")
    expect(page.get_by_text("Xin chào, Người dùng khác")).to_be_visible()
    expect(page.get_by_role("navigation").get_by_role("link", name="Tài khoản")).to_have_count(0)
    expect(page.get_by_text("Quản trị viên", exact=True)).to_have_count(0)


def test_separate_hosts_and_request_proof(page, stack):
    admin_session(page, stack)
    request = page.request
    for path in (
        "/api/v1/auth/me",
        "/api/v1/users",
        "/api/v1/directory/capabilities",
        "/assets/app.mjs",
    ):
        assert request.get(stack.demo + path).status == 404
    assert request.get(stack.admin + "/shared/core.js").status == 404
    assert request.get(stack.admin + "/dev/phase1.html").status == 404
    assert request.get(stack.demo + "/api/v1/system/info").json()["source"] == "postgresql"
    assert request.get(stack.admin, headers={"Host": "unrecognized.test"}).status == 404
    csp = request.get(stack.admin).headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    me = request.get(stack.admin + "/api/v1/auth/me").json()
    target = stack.admin + "/api/v1/users/" + me["id"] + "/profile"
    for headers in (
        {},
        {"Origin": stack.admin},
        {"Origin": stack.demo, "X-CSRF-Token": me["csrf_token"]},
    ):
        response = request.patch(target, headers=headers, data={"display_name": "Denied"})
        assert response.status == 403
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"] == response.json()["request_id"]
    expect(page).to_have_url(re.compile(r"admin\.localhost"))


def section(page, title):
    page.get_by_role("navigation", name="Quản trị").get_by_role(
        "link", name=title, exact=True
    ).click()
    expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()


def open_dialog(page, label):
    page.get_by_role("button", name=label, exact=True).click()
    return page.get_by_role("dialog")


def save_dialog(dialog, label):
    dialog.get_by_role("button", name=label, exact=True).click()
    expect(dialog).not_to_be_visible()


def create_named(page, label, code, name, *, kind=None):
    dialog = open_dialog(page, label)
    dialog.get_by_label("Mã", exact=True).fill(code)
    dialog.get_by_label("Tên", exact=True).fill(name)
    if kind:
        dialog.get_by_label("Loại nhóm").select_option(kind)
    save_dialog(dialog, label)
    expect(page.get_by_role("link", name=name, exact=True)).to_be_visible()


def account_form(page, username, name, unit, *, temporary=None):
    dialog = open_dialog(page, "Tạo tài khoản")
    if username == "student":
        capture(page, "06-create-user")
    dialog.get_by_label("Tên đăng nhập").fill(username)
    dialog.get_by_label("Tên hiển thị").fill(name)
    dialog.get_by_label("Mã định danh").fill(username.upper())
    dialog.get_by_label("Loại định danh").select_option("STUDENT")
    dialog.get_by_label("Đơn vị chính", exact=True).select_option(label=unit)
    if temporary is not None:
        dialog.get_by_label("Mật khẩu tạm thời").fill(temporary)
    return dialog


def write_api(page, stack, method, path, body=None, status=201):
    me = page.request.get(stack.admin + "/api/v1/auth/me").json()
    response = page.request.fetch(
        stack.admin + "/api/v1" + path,
        method=method,
        headers={"Origin": stack.admin, "X-CSRF-Token": me["csrf_token"]},
        data=body,
    )
    assert response.status == status, response.text()
    return response.json() if status in (200, 201) else None


def test_account_unit_workflows_and_conflicts(page, stack):
    admin_session(page, stack)
    section(page, "Đơn vị")
    create_named(page, "Tạo đơn vị", "A", "Khoa Nghiên cứu")
    create_named(page, "Tạo đơn vị", "B", "Khoa Đào tạo")
    capture(page, "04-units")
    page.get_by_role("link", name="Khoa Đào tạo").click()
    dialog = open_dialog(page, "Sửa đơn vị")
    dialog.get_by_label("Mã", exact=True).fill("A")
    dialog.get_by_role("button", name="Lưu thay đổi").click()
    expect(dialog.get_by_role("alert")).to_contain_text("Mã đơn vị đã được sử dụng")
    expect(dialog.get_by_role("alert")).to_contain_text("Mã yêu cầu")
    dialog.get_by_label("Mã", exact=True).fill("B2")
    dialog.get_by_label("Tên", exact=True).fill("Khoa Đào tạo mới")
    save_dialog(dialog, "Lưu thay đổi")
    expect(page.get_by_role("heading", name="Khoa Đào tạo mới")).to_be_visible()
    save_dialog(open_dialog(page, "Ngừng hoạt động"), "Ngừng hoạt động")
    expect(page.get_by_text("Ngừng hoạt động", exact=True)).to_be_visible()
    save_dialog(open_dialog(page, "Kích hoạt"), "Kích hoạt")
    section(page, "Tài khoản")
    save_dialog(
        account_form(page, "student", "Nguyễn Minh Ánh", "A · Khoa Nghiên cứu"), "Tạo tài khoản"
    )
    save_dialog(
        account_form(page, "temp", "Tạ Anh", "A · Khoa Nghiên cứu", temporary=TEMPORARY),
        "Tạo tài khoản",
    )
    expect(page.get_by_role("link", name="Tạ Anh")).to_be_visible()
    capture(page, "05-users")
    page.get_by_role("link", name="Nguyễn Minh Ánh").click()
    expect(page.get_by_text("Chờ kích hoạt", exact=True)).to_be_visible()
    dialog = open_dialog(page, "Kích hoạt tài khoản")
    dialog.get_by_label("Mật khẩu tạm thời").fill(TEMPORARY)
    save_dialog(dialog, "Kích hoạt")
    dialog = open_dialog(page, "Sửa hồ sơ")
    dialog.get_by_label("Tên hiển thị").fill("Nguyễn Minh Ánh · Đã cập nhật")
    save_dialog(dialog, "Lưu thay đổi")
    dialog = open_dialog(page, "Sửa định danh")
    dialog.get_by_label("Tên đăng nhập").fill("student.new")
    dialog.get_by_label("Mã định danh").fill("ST-001")
    save_dialog(dialog, "Lưu thay đổi")
    expect(page.get_by_text("student.new", exact=True)).to_be_visible()
    dialog = open_dialog(page, "Chuyển đơn vị")
    dialog.get_by_label("Đơn vị mới", exact=True).select_option(label="B2 · Khoa Đào tạo mới")
    save_dialog(dialog, "Xác nhận chuyển")
    with page.context.browser.new_context() as member_context:
        member = member_context.new_page()
        member.goto(stack.admin)
        login(member, "student.new", TEMPORARY)
        change_password(member, TEMPORARY, PERSONAL)
        login(member, "student.new", PERSONAL)
        expect(member.get_by_role("heading", name="Tổng quan")).to_be_visible()
        save_dialog(open_dialog(page, "Vô hiệu hóa tài khoản"), "Vô hiệu hóa")
        expect(page.get_by_text("Đã vô hiệu hóa", exact=True)).to_be_visible()
        member.reload()
        expect(member.get_by_role("heading", name="Đăng nhập")).to_be_visible()
    save_dialog(open_dialog(page, "Kích hoạt tài khoản"), "Kích hoạt")
    expect(page.get_by_text("Đang hoạt động", exact=True)).to_be_visible()
    section(page, "Tài khoản")
    page.get_by_role("link", name="Quản trị viên", exact=True).click()
    dialog = open_dialog(page, "Vô hiệu hóa tài khoản")
    dialog.get_by_role("button", name="Vô hiệu hóa", exact=True).click()
    expect(dialog.get_by_role("alert")).to_contain_text("ít nhất một quản trị viên")
    dialog.get_by_role("button", name="Hủy").click()
    grant = open_dialog(page, "Thu hồi vai trò")
    grant.get_by_role("button", name="Thu hồi", exact=True).click()
    expect(grant.get_by_role("alert")).to_contain_text("không còn quản trị viên")
    grant.get_by_role("button", name="Hủy").click()
    section(page, "Đơn vị")
    page.get_by_role("link", name="Khoa Đào tạo mới").click()
    dialog = open_dialog(page, "Ngừng hoạt động")
    dialog.get_by_role("button", name="Ngừng hoạt động", exact=True).click()
    expect(dialog.get_by_role("alert")).to_contain_text("còn tài khoản hoạt động")


def grant_dialog(page, *, scope, group=False):
    dialog = open_dialog(page, "Cấp vai trò")
    role = dialog.get_by_label("Vai trò", exact=True)
    role.select_option("DIRECTORY_READER")
    if group:
        expect(role.locator('option[value="FOUNDATION_ADMIN"]')).to_have_count(0)
    dialog.get_by_label("Phạm vi").select_option(scope)
    unit = dialog.get_by_label("Đơn vị áp dụng", exact=True)
    if scope == "UNIT":
        unit.select_option(label="MAIN · Đơn vị chính")
    else:
        expect(unit).not_to_be_visible()
    if group:
        capture(page, "08-assignment")
    save_dialog(dialog, "Cấp vai trò")
    expect(page.get_by_text("DIRECTORY_READER", exact=True)).to_be_visible()


def test_groups_assignments_and_audit(page, stack):
    admin_session(page, stack)
    section(page, "Vai trò")
    expect(page.get_by_text("FOUNDATION_ADMIN", exact=True)).to_be_visible()
    expect(page.get_by_text("authorization.manage", exact=True)).to_be_visible()
    section(page, "Tài khoản")
    save_dialog(
        account_form(page, "member", "Thành viên mới", "MAIN · Đơn vị chính", temporary=TEMPORARY),
        "Tạo tài khoản",
    )
    page.get_by_role("link", name="Thành viên mới").click()
    grant_dialog(page, scope="UNIT")
    save_dialog(open_dialog(page, "Thu hồi vai trò"), "Thu hồi")
    section(page, "Nhóm tài khoản")
    create_named(page, "Tạo nhóm", "SYS", "Nhóm hệ thống", kind="SYSTEM")
    create_named(page, "Tạo nhóm", "AI", "Nhóm Trí tuệ", kind="AI_SPECIALIST")
    create_named(page, "Tạo nhóm", "AUTH", "Nhóm xét duyệt", kind="AUTHORIZATION")
    page.get_by_role("link", name="Nhóm hệ thống").click()
    expect(page.get_by_role("button", name="Cấp vai trò")).to_have_count(0)
    section(page, "Nhóm tài khoản")
    page.get_by_role("link", name="Nhóm xét duyệt").click()
    dialog = open_dialog(page, "Đổi tên nhóm")
    expect(dialog.get_by_label("Loại nhóm")).to_have_count(0)
    dialog.get_by_label("Tên", exact=True).fill("Nhóm Đọc danh bạ")
    save_dialog(dialog, "Lưu thay đổi")
    grant_dialog(page, scope="GLOBAL", group=True)
    for _ in range(2):
        dialog = open_dialog(page, "Thêm thành viên")
        dialog.get_by_label("Tài khoản", exact=True).select_option(label="Thành viên mới · member")
        save_dialog(dialog, "Thêm thành viên")
    expect(page.get_by_role("link", name="Thành viên mới")).to_have_count(1)
    capture(page, "07-membership")
    with page.context.browser.new_context() as member_context:
        member = member_context.new_page()
        member.goto(stack.admin)
        login(member, "member", TEMPORARY)
        change_password(member, TEMPORARY, PERSONAL)
        login(member, "member", PERSONAL)
        section(member, "Tài khoản")
        save_dialog(open_dialog(page, "Gỡ thành viên"), "Gỡ thành viên")
        member.reload()
        expect(member.get_by_role("alert")).to_contain_text("không có quyền")
        page.get_by_label("Tư cách thành viên").select_option("false")
        page.get_by_role("heading", name="Thành viên", exact=True).locator("..").get_by_role(
            "button", name="Áp dụng"
        ).click()
        save_dialog(open_dialog(page, "Thêm lại"), "Thêm lại")
        save_dialog(open_dialog(page, "Ngừng hoạt động"), "Ngừng hoạt động")
        expect(page.get_by_role("button", name="Thêm thành viên")).to_have_count(0)
        assert member.request.get(stack.admin + "/api/v1/users").status == 403
        save_dialog(open_dialog(page, "Kích hoạt"), "Kích hoạt")
        assert member.request.get(stack.admin + "/api/v1/users").status == 200
        save_dialog(open_dialog(page, "Thu hồi vai trò"), "Thu hồi")
        assert member.request.get(stack.admin + "/api/v1/users").status == 403
    section(page, "Nhật ký")
    page.get_by_label("Hành động").select_option("membership.state_changed")
    page.get_by_role("button", name="Áp dụng").click()
    expect(page.get_by_role("link", name="Đổi trạng thái thành viên", exact=True)).to_have_count(3)
    page.get_by_role("link", name="Đổi trạng thái thành viên", exact=True).first.click()
    expect(page.get_by_text('"user_id"', exact=False)).to_be_visible()
    expect(page.get_by_text("Mã yêu cầu", exact=True)).to_be_visible()
    capture(page, "09-audit")


def test_scoped_roles_filters_navigation_and_safe_text(page, stack):
    admin_session(page, stack)
    unit_a = write_api(page, stack, "POST", "/units", {"code": "A", "name": "Khoa Một"})
    unit_b = write_api(page, stack, "POST", "/units", {"code": "B", "name": "Khoa Hai"})
    name = "<script>window.aqTestMarker=true</script> · Trần Nguyễn " + "Á" * 160

    def user(username, unit, display_name=None, active=True):
        return write_api(
            page,
            stack,
            "POST",
            "/users",
            {
                "primary_unit_id": unit["id"],
                "username": username,
                "display_name": display_name or username,
                "code_type": "STAFF",
                "institutional_code": username,
                **({"temporary_password": TEMPORARY} if active else {}),
            },
        )

    outsider = user("outsider", unit_b, "Người ngoài khoa")
    target = user("target", unit_a, name)
    for index in range(11):
        user(f"extra-{index:02}", unit_a, active=False)
    for username, roles in {
        "reader": [("DIRECTORY_READER", None)],
        "exact": [("DIRECTORY_READER", unit_a)],
        "manager": [("UNIT_DIRECTORY_MANAGER", unit_a)],
        "mixed": [("DIRECTORY_READER", None), ("UNIT_DIRECTORY_MANAGER", unit_a)],
        "none": [],
    }.items():
        actor = user(username, unit_b)
        for role, unit in roles:
            write_api(
                page,
                stack,
                "POST",
                f"/users/{actor['id']}/role-assignments",
                {
                    "role_code": role,
                    "scope": "UNIT" if unit else "GLOBAL",
                    **({"unit_id": unit["id"]} if unit else {}),
                },
            )
        with page.context.browser.new_context() as context:
            view = context.new_page()
            view.goto(stack.admin)
            login(view, username, TEMPORARY)
            change_password(view, TEMPORARY, PERSONAL)
            login(view, username, PERSONAL)
            expect(view.get_by_role("heading", name="Tổng quan")).to_be_visible()
            expect(
                view.get_by_role("navigation").get_by_role("link", name="Vai trò")
            ).to_have_count(0)
            if username == "none":
                expect(
                    view.get_by_text("Tài khoản này chưa được cấp quyền danh bạ.")
                ).to_be_visible()
                view.goto(stack.admin + "/#users")
                expect(view.get_by_role("alert")).to_contain_text("không có quyền")
                continue
            section(view, "Tài khoản")
            expect(view.get_by_role("button", name="Tạo tài khoản")).to_have_count(0)
            if username == "exact":
                expect(view.get_by_text("1–10 / 12 bản ghi")).to_be_visible()
                view.get_by_role("button", name="Trang sau").click()
                expect(view.get_by_text("11–12 / 12 bản ghi")).to_be_visible()
                view.get_by_label("Tìm kiếm").fill("Người ngoài khoa")
                view.get_by_role("button", name="Áp dụng").click()
                expect(view.get_by_text("0 / 0 bản ghi")).to_be_visible()
                capture(view, "10-read-only")
            view.goto(stack.admin + "/#users/" + target["id"])
            expect(view.get_by_role("heading", name=name, exact=True)).to_be_visible()
            assert view.evaluate("window.aqTestMarker") is None
            expect(view.get_by_role("button", name="Sửa hồ sơ")).to_have_count(
                int(username in {"manager", "mixed"})
            )
            view.goto(stack.admin + "/#users/" + outsider["id"])
            if username in {"exact", "manager"}:
                expect(view.get_by_role("alert")).to_contain_text("Không tìm thấy")
                view.goto(stack.admin + "/#users/11111111-1111-4111-8111-111111111111")
                expect(view.get_by_role("alert")).to_contain_text("Không tìm thấy")
            else:
                expect(view.get_by_role("heading", name="Người ngoài khoa")).to_be_visible()
                expect(view.get_by_role("button", name="Sửa hồ sơ")).to_have_count(0)
                write_api(
                    view,
                    stack,
                    "PATCH",
                    f"/users/{outsider['id']}/profile",
                    {"display_name": "Denied"},
                    status=403,
                )
    section(page, "Tài khoản")
    sidebar = page.locator(".sidebar").bounding_box()
    section(page, "Đơn vị")
    page.go_back()
    expect(page.get_by_role("heading", name="Tài khoản", exact=True)).to_be_visible()
    assert page.locator(".sidebar").bounding_box()["width"] == sidebar["width"]
    page.go_forward()
    expect(page.get_by_role("heading", name="Đơn vị", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 360, "height": 720})
    toggle = page.get_by_role("button", name="Danh mục")
    expect(toggle).to_be_visible()
    expect(page.get_by_role("navigation")).not_to_be_visible()
    toggle.click()
    section(page, "Tài khoản")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(page.get_by_role("region", name="Bảng kết quả")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    capture(page, "11-mobile")
    trigger = page.get_by_role("button", name="Tạo tài khoản")
    trigger.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("dialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).not_to_be_visible()
    expect(trigger).to_be_focused()


def test_uncertain_write_warns_and_never_retries(page, stack):
    admin_session(page, stack)
    section(page, "Đơn vị")
    posts = []

    def drop_response(route):
        if route.request.method != "POST":
            route.continue_()
            return
        response = route.fetch()
        posts.append(response.status)
        route.abort()

    page.route("**/api/v1/units", drop_response)
    dialog = open_dialog(page, "Tạo đơn vị")
    dialog.get_by_label("Mã", exact=True).fill("UNCERTAIN")
    dialog.get_by_label("Tên", exact=True).fill("Đã ghi dữ liệu")
    dialog.get_by_role("button", name="Tạo đơn vị").click()
    expect(dialog.get_by_role("alert")).to_contain_text("tải lại dữ liệu để kiểm tra kết quả")
    assert posts == [201]
    dialog.get_by_role("button", name="Hủy").click()
    page.reload()
    expect(page.get_by_role("link", name="Đã ghi dữ liệu")).to_be_visible()
    assert posts == [201]


def test_reference_search_and_pagination_reaches_later_units(page, stack):
    admin_session(page, stack)
    for index in range(11):
        write_api(
            page, stack, "POST", "/units", {"code": f"REF{index:02}", "name": f"Phòng {index:02}"}
        )
    section(page, "Tài khoản")
    dialog = open_dialog(page, "Tạo tài khoản")
    unit = dialog.get_by_label("Đơn vị chính", exact=True)
    expect(unit.locator("option")).to_have_count(11)
    expect(unit.get_by_text("REF10 · Phòng 10")).to_have_count(0)
    expect(dialog.get_by_label("Tìm trong đơn vị chính")).not_to_be_visible()
    dialog.get_by_text("Tìm hoặc xem thêm", exact=True).click()
    dialog.get_by_role("button", name="Sau", exact=True).click()
    unit.select_option(label="REF10 · Phòng 10")
    dialog.get_by_label("Tìm trong đơn vị chính").fill("Phòng 02")
    dialog.get_by_role("button", name="Tìm", exact=True).click()
    expect(unit.get_by_text("REF02 · Phòng 02")).to_have_count(1)
    expect(unit.locator("option:checked")).to_have_text("REF10 · Phòng 10")
