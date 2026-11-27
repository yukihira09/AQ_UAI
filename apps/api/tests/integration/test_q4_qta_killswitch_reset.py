"""Stage Q4 against disposable PostgreSQL: individual kill-switch, check_ai_access, events & monthly reset.

All requests go through real FastAPI routes with session cookies, exact Origin, CSRF headers,
and the restricted ``aq_uai_runtime`` database login. All clock-dependent assertions control
``aq_uai_api.qta.periods.utc_now`` deterministically rather than reading the host wall clock.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from psycopg import sql

from aq_uai_api.qta import access, periods, reset

from .test_m1_mdl_access import sign_in
from .test_m2_mdl_schema import add_model, add_provider
from .test_q2_qta_groups import audit_rows, qta_get, qta_path, qta_send
from .test_wp2_database import connect
from .test_wp3_auth import ORIGIN_HEADER, client, csrf_headers
from .test_wp5_directory import (
    add_grant,
    create_unit,
    create_user,
)
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import directory as directory
from .test_wp5_directory import pytestmark as postgres_marks

pytestmark = postgres_marks


@pytest.fixture
def qta4(directory, monkeypatch):
    # Deterministic mutable clock anchored just ahead of PostgreSQL's real now() so
    # ck_qta_suspensions_expiry (expires_at > suspended_at) holds in every calendar year.
    base_utc = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=2)
    clock = {"now": base_utc}
    monkeypatch.setattr(periods, "utc_now", lambda: clock["now"])

    db = directory
    monkeypatch.setattr(reset, "write_transaction", db.runtime_factory.begin)
    db.clock = clock
    unit_a = create_unit(db.admin, "Q4UA")
    unit_b = create_unit(db.admin, "Q4UB")
    qta_admin_user = create_user(db.admin, unit_a["id"], "q4admin", active=True)
    global_viewer_user = create_user(db.admin, unit_a["id"], "q4gviewer", active=True)
    unit_viewer_user = create_user(db.admin, unit_a["id"], "q4uviewer", active=True)
    mdl_admin_user = create_user(db.admin, unit_a["id"], "q4mdladmin", active=True)

    add_grant(db.admin, f"/users/{qta_admin_user['id']}", "AI_QUOTA_ADMIN")
    add_grant(db.admin, f"/users/{global_viewer_user['id']}", "AI_QUOTA_VIEWER")
    add_grant(db.admin, f"/users/{unit_viewer_user['id']}", "AI_QUOTA_VIEWER", unit_a["id"])
    add_grant(db.admin, f"/users/{mdl_admin_user['id']}", "AI_MODEL_ADMIN")

    with connect(db.runtime, autocommit=True) as conn:
        ext_provider = add_provider(conn, db.tenant, "Q4 External", provider_type="EXTERNAL")
        int_provider = add_provider(conn, db.tenant, "Q4 Internal", provider_type="INTERNAL")
        m_ext = add_model(
            conn, db.tenant, ext_provider, "q4-ext", display_name="Q4 External Model", risk_level="LOW"
        )
        m_int = add_model(
            conn, db.tenant, int_provider, "q4-int", display_name="Q4 Internal Model", risk_level="LOW"
        )

    db.unit_a = unit_a["id"]
    db.unit_b = unit_b["id"]
    db.qta_admin_id = qta_admin_user["id"]
    db.m_ext = str(m_ext)
    db.m_int = str(m_int)

    db.qta_admin = sign_in(db, "q4admin")
    db.global_viewer = sign_in(db, "q4gviewer")
    db.unit_viewer = sign_in(db, "q4uviewer")
    db.mdl_admin = sign_in(db, "q4mdladmin")
    try:
        yield db
    finally:
        for browser in (db.qta_admin, db.global_viewer, db.unit_viewer, db.mdl_admin):
            browser.__exit__(None, None, None)


def _setup_entitled_user(db, username: str, *, ext_limit: int = 1000, int_limit: int = 2000):
    user = create_user(db.admin, db.unit_a, username, active=True)
    grp = qta_send(
        db.qta_admin,
        "POST",
        "/groups",
        {"code": f"AI_{username.upper()}", "name": f"Nhóm {username}"},
        201,
    )
    qta_send(db.qta_admin, "PUT", f"/groups/{grp['id']}/members/{user['id']}")
    qta_send(
        db.qta_admin,
        "PUT",
        f"/groups/{grp['id']}/quotas",
        {
            "quotas": [
                {"model_id": db.m_ext, "enabled": True, "monthly_limit": ext_limit},
                {"model_id": db.m_int, "enabled": True, "monthly_limit": int_limit},
            ]
        },
    )
    return user


def _by_model(entitlement_response: dict) -> dict[str, dict]:
    return {item["model_id"]: item for item in entitlement_response["models"]}


def _table_count(db, table: str) -> int:
    with connect(db.owner) as conn:
        return int(conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0])


def test_suspend_without_expiry_and_with_future_expiry(qta4):
    """FR-QTA-040 AC1–AC2, PD-Q3: suspend with NULL expiry (open-ended) and with finite future expiry."""
    db = qta4
    u_open = create_user(db.admin, db.unit_a, "uopen", active=True)
    u_timed = create_user(db.admin, db.unit_a, "utimed", active=False)  # PENDING state also accepted

    s_open = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{u_open['id']}/suspensions",
        {
            "scope": "ALL_MODELS",
            "reason": "  Lạm dụng tài nguyên  ",
            "ordered_by": "  Hiệu trưởng  ",
        },
        201,
    )
    assert s_open["status"] == "ACTIVE"
    assert s_open["expires_at"] is None
    assert s_open["reason"] == "Lạm dụng tài nguyên"
    assert s_open["ordered_by"] == "Hiệu trưởng"
    assert s_open["suspended_by"] == db.qta_admin_id
    assert s_open["restoration"] is None

    future_exp = (db.clock["now"] + timedelta(days=500)).isoformat()  # > 365 days allowed (PD-Q3 no cap)
    s_timed = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{u_timed['id']}/suspensions",
        {
            "scope": "PAID_EXTERNAL_ONLY",
            "reason": "Tạm khóa mô hình ngoài",
            "ordered_by": "Phòng CNTT",
            "expires_at": future_exp,
        },
        201,
    )
    assert s_timed["status"] == "ACTIVE"
    assert s_timed["expires_at"] is not None
    assert s_timed["scope"] == "PAID_EXTERNAL_ONLY"


def test_suspend_validation(qta4):
    """FR-QTA-040 AC3: blank reason/ordered_by, past/now/naive expires_at, bad scope, extra/suspended_by -> 422."""
    db = qta4
    target = create_user(db.admin, db.unit_a, "uval", active=True)
    before_susp = _table_count(db, "qta_suspensions")
    before_events = _table_count(db, "qta_events")

    base = {
        "scope": "ALL_MODELS",
        "reason": "Vi phạm nội quy",
        "ordered_by": "Trưởng phòng Đào tạo",
    }
    invalid_bodies = [
        {"scope": "ALL_MODELS", "ordered_by": "BGH"},
        {"scope": "ALL_MODELS", "reason": "Lý do"},
        base | {"reason": ""},
        base | {"reason": "   "},
        base | {"ordered_by": ""},
        base | {"ordered_by": "   "},
        base | {"expires_at": db.clock["now"].isoformat()},  # exact now
        base | {"expires_at": (db.clock["now"] - timedelta(minutes=1)).isoformat()},  # past
        base | {"expires_at": "2028-01-01T00:00:00"},  # naive datetime
        base | {"scope": "FREE_ONLY"},
        base | {"suspended_by": db.qta_admin_id},
        base | {"extra_field": "x"},
    ]
    for bad in invalid_bodies:
        err = qta_send(db.qta_admin, "POST", f"/users/{target['id']}/suspensions", bad, 422)
        assert err["code"] == "VALIDATION_FAILED", bad

    assert _table_count(db, "qta_suspensions") == before_susp
    assert _table_count(db, "qta_events") == before_events


def test_operator_is_session_actor_even_if_ordered_by_names_someone_else(qta4):
    """FR-QTA-040, PD-Q3: suspended_by, event.actor_id, and audit.actor_id always equal session actor."""
    db = qta4
    target = create_user(db.admin, db.unit_a, "uop", active=True)
    other_person = create_user(db.admin, db.unit_b, "rector", active=True)

    susp = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{target['id']}/suspensions",
        {
            "scope": "ALL_MODELS",
            "reason": "Theo văn bản khẩn",
            "ordered_by": f"Hiệu trưởng ({other_person['username']})",
        },
        201,
    )
    assert susp["suspended_by"] == db.qta_admin_id
    assert susp["suspended_by"] != other_person["id"]
    assert susp["ordered_by"] == f"Hiệu trưởng ({other_person['username']})"

    events = qta_get(db.qta_admin, "/events", {"user_id": target["id"]})["items"]
    assert len(events) == 1
    assert events[0]["actor_id"] == db.qta_admin_id

    audits = audit_rows(db, action_prefix="qta.user_suspended", target_id=susp["id"])
    assert len(audits) == 1
    assert str(audits[0][1]) == db.qta_admin_id
    assert audits[0][4]["ordered_by"] == f"Hiệu trưởng ({other_person['username']})"


def test_second_active_suspension_is_409_but_after_expiry_or_restore_allowed(qta4):
    """Single active suspension per user: second while active -> 409; allowed after expiry or restore."""
    db = qta4
    target = create_user(db.admin, db.unit_a, "udup", active=True)
    exp1 = db.clock["now"] + timedelta(days=2)

    s1 = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{target['id']}/suspensions",
        {
            "scope": "PAID_EXTERNAL_ONLY",
            "reason": "Lần 1",
            "ordered_by": "BGH",
            "expires_at": exp1.isoformat(),
        },
        201,
    )

    dup = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{target['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Lần 2 trùng", "ordered_by": "BGH"},
        409,
    )
    assert dup["code"] == "QTA_USER_ALREADY_SUSPENDED"

    # Advance frozen clock past exp1 -> lazy expiry lifts s1 -> new suspension succeeds.
    db.clock["now"] = exp1 + timedelta(seconds=5)
    s2 = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{target['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Sau khi hết hạn", "ordered_by": "BGH"},
        201,
    )
    assert s2["id"] != s1["id"] and s2["status"] == "ACTIVE"

    # While s2 is active, another suspend is 409; after explicit restore, s3 succeeds.
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{target['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Trùng lần nữa", "ordered_by": "BGH"},
        409,
    )
    qta_send(db.qta_admin, "POST", f"/users/{target['id']}/restore", {"note": "Mở lại"})
    s3 = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{target['id']}/suspensions",
        {"scope": "PAID_EXTERNAL_ONLY", "reason": "Sau khôi phục", "ordered_by": "BGH"},
        201,
    )
    assert s3["id"] not in {s1["id"], s2["id"]}

    history = qta_get(db.qta_admin, f"/users/{target['id']}/suspensions")["items"]
    assert [(h["id"], h["status"]) for h in history] == [
        (s3["id"], "ACTIVE"),
        (s2["id"], "RESTORED"),
        (s1["id"], "EXPIRED"),
    ]


def test_concurrent_suspends_one_wins(qta4):
    """QTA_SUSPENSION_NAMESPACE serializes concurrent suspends: exactly one 201 and one 409, zero 500."""
    db = qta4
    target = create_user(db.admin, db.unit_a, "urace", active=True)
    barrier = Barrier(2)
    headers = csrf_headers(db.qta_admin)
    cookies = dict(db.qta_admin.cookies)

    def _attempt(idx: int) -> tuple[int, dict]:
        with client(db) as browser:
            browser.cookies.update(cookies)
            barrier.wait(timeout=10)
            resp = browser.post(
                f"/api/v1/qta/users/{target['id']}/suspensions",
                json={
                    "scope": "ALL_MODELS",
                    "reason": f"Concurrent {idx}",
                    "ordered_by": "BGH",
                },
                headers=headers,
            )
            return resp.status_code, resp.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_attempt, (1, 2)))

    statuses = sorted(status for status, _ in results)
    assert statuses == [201, 409], results
    conflict_body = next(body for status, body in results if status == 409)
    assert conflict_body["code"] == "QTA_USER_ALREADY_SUSPENDED"


def test_paid_external_only_blocks_external_allows_internal_end_to_end(qta4):
    """FR-QTA-040 AC1, PD-Q2, RULE-QTA-03: PAID_EXTERNAL_ONLY blocks EXTERNAL and allows INTERNAL."""
    db = qta4
    user = _setup_entitled_user(db, "upaid")

    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "PAID_EXTERNAL_ONLY", "reason": "Giới hạn chi phí", "ordered_by": "BGH"},
        201,
    )

    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    assert ent["quota_status"] == "SUSPENDED"
    assert ent["suspension"]["scope"] == "PAID_EXTERNAL_ONLY"
    by_mid = _by_model(ent)
    assert by_mid[db.m_ext]["access"] == {"allowed": False, "reason": "SUSPENDED_PAID_EXTERNAL"}
    assert by_mid[db.m_int]["access"] == {"allowed": True, "reason": None}

    with db.runtime_factory() as session:
        ext_dec = access.check_ai_access(
            session, UUID(db.tenant), UUID(user["id"]), UUID(db.m_ext)
        )
        int_dec = access.check_ai_access(
            session, UUID(db.tenant), UUID(user["id"]), UUID(db.m_int)
        )
    assert ext_dec.allowed is False and ext_dec.reason == "SUSPENDED_PAID_EXTERNAL"
    assert int_dec.allowed is True and int_dec.reason is None


def test_all_models_blocks_both(qta4):
    """FR-QTA-040 AC1, RULE-QTA-03: ALL_MODELS blocks both EXTERNAL and INTERNAL models."""
    db = qta4
    user = _setup_entitled_user(db, "uall")

    susp = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Vi phạm nghiêm trọng", "ordered_by": "Hiệu trưởng"},
        201,
    )

    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    assert ent["quota_status"] == "SUSPENDED"
    assert ent["suspension"]["id"] == susp["id"]
    by_mid = _by_model(ent)
    assert by_mid[db.m_ext]["access"] == {"allowed": False, "reason": "SUSPENDED_ALL_MODELS"}
    assert by_mid[db.m_int]["access"] == {"allowed": False, "reason": "SUSPENDED_ALL_MODELS"}


def test_suspend_and_restore_do_not_change_entitlements_or_budgets(qta4):
    """FR-QTA-040, FR-QTA-041: neither suspend nor restore zeroes or adds quota or alters allocated."""
    db = qta4
    user = _setup_entitled_user(db, "unozero", ext_limit=1200, int_limit=1800)
    cur_month = periods.format_month(periods.current_month(access.periods.Settings()))
    qta_send(
        db.qta_admin,
        "PUT",
        f"/budgets/{cur_month}",
        {"total_limit": 5000, "decision_number": "QD-40", "decision_date": "2026-11-01"},
    )

    before_ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    before_budget = qta_get(db.qta_admin, "/budgets", {"month": cur_month})
    assert before_ent["base_entitlement_total"] == 3000
    assert before_budget["allocated"] == 3000

    # Suspend -> base_entitlement and institutional allocated stay 3000 (NOT zeroed!).
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Tạm khóa", "ordered_by": "BGH"},
        201,
    )
    mid_ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    mid_budget = qta_get(db.qta_admin, "/budgets", {"month": cur_month})
    assert mid_ent["base_entitlement_total"] == 3000
    assert _by_model(mid_ent)[db.m_ext]["base_entitlement"] == 1200
    assert _by_model(mid_ent)[db.m_int]["base_entitlement"] == 1800
    assert mid_budget["allocated"] == 3000

    # Restore -> base_entitlement and institutional allocated still stay 3000 (nothing added!).
    qta_send(db.qta_admin, "POST", f"/users/{user['id']}/restore", {"note": "Khôi phục"})
    after_ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    after_budget = qta_get(db.qta_admin, "/budgets", {"month": cur_month})
    assert after_ent["base_entitlement_total"] == 3000
    assert after_budget["allocated"] == 3000


def test_restore_returns_active_and_records_event(qta4):
    """FR-QTA-041 AC1, AC2: restore returns ACTIVE quota_status, records RESTORE event & audit."""
    db = qta4
    user = _setup_entitled_user(db, "urestore")
    susp = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Kiểm tra", "ordered_by": "BGH"},
        201,
    )

    restored = qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/restore",
        {"note": "  Đã xác minh xong  "},
    )
    assert restored["id"] == susp["id"]
    assert restored["status"] == "RESTORED"
    assert restored["restoration"]["restored_by"] == db.qta_admin_id
    assert restored["restoration"]["note"] == "Đã xác minh xong"

    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    assert ent["quota_status"] == "ACTIVE"
    assert ent["suspension"] is None
    assert all(m["access"] == {"allowed": True, "reason": None} for m in ent["models"])

    events = qta_get(
        db.qta_admin, "/events", {"user_id": user["id"], "event_type": "RESTORE"}
    )["items"]
    assert len(events) == 1 and events[0]["actor_id"] == db.qta_admin_id

    audits = audit_rows(db, action_prefix="qta.user_restored", target_id=susp["id"])
    assert len(audits) == 1 and audits[0][4]["suspension_id"] == susp["id"]


def test_restore_without_active_suspension_is_409(qta4):
    """FR-QTA-041: restore fails with 409 QTA_USER_NOT_SUSPENDED when none, expired, or already restored."""
    db = qta4
    user = create_user(db.admin, db.unit_a, "unotsusp", active=True)

    # 1. Never suspended -> 409.
    e1 = qta_send(db.qta_admin, "POST", f"/users/{user['id']}/restore", None, 409)
    assert e1["code"] == "QTA_USER_NOT_SUSPENDED"

    # 2. Suspended with future expiry, then expired -> 409.
    exp = db.clock["now"] + timedelta(days=1)
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Ngắn hạn", "ordered_by": "BGH", "expires_at": exp.isoformat()},
        201,
    )
    db.clock["now"] = exp + timedelta(seconds=1)
    e2 = qta_send(db.qta_admin, "POST", f"/users/{user['id']}/restore", {}, 409)
    assert e2["code"] == "QTA_USER_NOT_SUSPENDED"

    # 3. Suspended, restored once (200), then restored again -> 409.
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Mới", "ordered_by": "BGH"},
        201,
    )
    qta_send(db.qta_admin, "POST", f"/users/{user['id']}/restore")
    e3 = qta_send(db.qta_admin, "POST", f"/users/{user['id']}/restore", None, 409)
    assert e3["code"] == "QTA_USER_NOT_SUSPENDED"


def test_lazy_expiry_lifts_suspension_without_writes(qta4):
    """PD-Q3: advancing past expires_at restores access on read while writing zero DB rows."""
    db = qta4
    user = _setup_entitled_user(db, "ulazy")
    exp = db.clock["now"] + timedelta(hours=6)

    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {
            "scope": "ALL_MODELS",
            "reason": "Tạm khóa 6 giờ",
            "ordered_by": "BGH",
            "expires_at": exp.isoformat(),
        },
        201,
    )

    counts_before = {
        t: _table_count(db, t)
        for t in (
            "qta_suspensions",
            "qta_suspension_restorations",
            "qta_events",
            "audit_events",
        )
    }

    # Advance frozen clock past expiry and read users, entitlements, and suspensions.
    db.clock["now"] = exp + timedelta(seconds=1)
    users_page = qta_get(db.qta_admin, "/users", {"q": "ulazy"})["items"]
    assert users_page[0]["quota_status"] == "ACTIVE"

    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    assert ent["quota_status"] == "ACTIVE" and ent["suspension"] is None
    assert all(m["access"]["allowed"] is True for m in ent["models"])

    hist = qta_get(db.qta_admin, f"/users/{user['id']}/suspensions")["items"]
    assert len(hist) == 1 and hist[0]["status"] == "EXPIRED" and hist[0]["restoration"] is None

    counts_after = {t: _table_count(db, t) for t in counts_before}
    assert counts_after == counts_before


def test_events_append_only_and_filtered(qta4):
    """FR-QTA-050: SUSPEND/RESTORE/MONTHLY_REFRESH events filter by month/type/user; summary omits reason."""
    db = qta4
    db.clock["now"] = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    secret_reason = "SENSITIVE-REASON-DO-NOT-COPY-98765"
    user = create_user(db.admin, db.unit_a, "uevt", active=True)

    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "PAID_EXTERNAL_ONLY", "reason": secret_reason, "ordered_by": "BGH"},
        201,
    )
    qta_send(db.qta_admin, "POST", f"/users/{user['id']}/restore", {"note": "PRIVATE-NOTE-12345"})
    qta_send(db.qta_admin, "POST", "/monthly-resets", None, 201)

    nov_events = qta_get(db.qta_admin, "/events", {"month": "2026-11"})["items"]
    assert {e["event_type"] for e in nov_events} == {"SUSPEND", "RESTORE", "MONTHLY_REFRESH"}
    for e in nov_events:
        assert secret_reason not in e["summary"]
        assert "PRIVATE-NOTE-12345" not in e["summary"]
    suspend_evt = next(e for e in nov_events if e["event_type"] == "SUSPEND")
    assert "PAID_EXTERNAL_ONLY" in suspend_evt["summary"]

    # Filters: month, event_type, user_id; malformed month -> 422 QTA_INVALID_PERIOD.
    assert qta_get(db.qta_admin, "/events", {"month": "2026-10"})["items"] == []
    only_refresh = qta_get(
        db.qta_admin, "/events", {"month": "2026-11", "event_type": "MONTHLY_REFRESH"}
    )["items"]
    assert len(only_refresh) == 1 and only_refresh[0]["user_id"] is None

    only_user = qta_get(db.qta_admin, "/events", {"month": "2026-11", "user_id": user["id"]})["items"]
    assert {e["event_type"] for e in only_user} == {"SUSPEND", "RESTORE"}

    bad = qta_get(db.qta_admin, "/events", {"month": "HK1-2026"}, 422)
    assert bad["code"] == "QTA_INVALID_PERIOD"


def test_manual_reset_current_month_only_and_409_on_repeat(qta4):
    """FR-QTA-032 AC1, PD-Q6: manual reset records current month only, rejects body month, 409 on repeat."""
    db = qta4
    db.clock["now"] = datetime(2026, 11, 20, 5, 0, tzinfo=UTC)

    # Rejects any attempt to pass a month (e.g. next month) in the request body.
    bad = qta_send(db.qta_admin, "POST", "/monthly-resets", {"month": "2026-12"}, 422)
    assert bad["code"] == "VALIDATION_FAILED"

    before = qta_get(db.qta_admin, "/monthly-resets")
    assert before["current"] == {"month": "2026-11", "status": "PENDING", "reset": None}

    created = qta_send(db.qta_admin, "POST", "/monthly-resets", None, 201)
    assert created["month"] == "2026-11"
    assert created["trigger_mode"] == "MANUAL_SIMULATION"
    assert created["triggered_by"] == db.qta_admin_id

    after = qta_get(db.qta_admin, "/monthly-resets")
    assert after["current"]["status"] == "COMPLETED"
    assert after["current"]["reset"]["id"] == created["id"]

    # Repeat in the same month -> 409 QTA_RESET_ALREADY_EXECUTED.
    dup = qta_send(db.qta_admin, "POST", "/monthly-resets", None, 409)
    assert dup["code"] == "QTA_RESET_ALREADY_EXECUTED"


def test_reset_cli_idempotent_and_no_backfill(qta4):
    """R8, FR-QTA-032: CLI records current month once, is idempotent on re-run, and never backfills past months."""
    db = qta4
    # Simulate running late on Dec 3, 2026 (Nov 2026 was never reset).
    db.clock["now"] = datetime(2026, 12, 3, 2, 0, tzinfo=UTC)  # 2026-12-03 09:00 +07:00

    first = reset.run_scheduled_resets()
    assert first.recorded >= 1 and first.already == 0

    second = reset.run_scheduled_resets()
    assert second.recorded == 0 and second.already == first.recorded

    listing = qta_get(db.qta_admin, "/monthly-resets")
    months = [item["month"] for item in listing["items"]]
    assert months == ["2026-12"]  # Missed November 2026 was NOT backfilled!
    assert listing["items"][0]["trigger_mode"] == "SCHEDULED"
    assert listing["items"][0]["triggered_by"] is None

    audits = audit_rows(db, action_prefix="qta.monthly_reset_scheduled")
    assert len(audits) == first.recorded
    assert all(row[1] is None for row in audits)


def test_manual_then_scheduled_same_month_is_noop(qta4):
    """PD-Q6, R8: if manual simulation already ran for current month, scheduled CLI is a clean no-op."""
    db = qta4
    db.clock["now"] = datetime(2026, 11, 10, 5, 0, tzinfo=UTC)

    manual = qta_send(db.qta_admin, "POST", "/monthly-resets", None, 201)
    cli_res = reset.run_scheduled_resets()
    assert cli_res.recorded == 0 and cli_res.already >= 1

    listing = qta_get(db.qta_admin, "/monthly-resets")
    assert len(listing["items"]) == 1
    assert listing["items"][0]["id"] == manual["id"]
    assert listing["items"][0]["trigger_mode"] == "MANUAL_SIMULATION"


def test_zero_rollover_across_months(qta4):
    """FR-QTA-032 AC2, R7: crossing Nov -> Dec carries over zero budget or unused allowance."""
    db = qta4
    db.clock["now"] = datetime(2026, 11, 25, 5, 0, tzinfo=UTC)
    user = _setup_entitled_user(db, "urollover", ext_limit=1500, int_limit=2500)

    qta_send(
        db.qta_admin,
        "PUT",
        "/budgets/2026-11",
        {"total_limit": 50_000, "decision_number": "QD-NOV", "decision_date": "2026-11-01"},
    )
    qta_send(db.qta_admin, "POST", "/monthly-resets", None, 201)

    nov_ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements", {"month": "2026-11"})
    assert nov_ent["base_entitlement_total"] == 4000

    # Advance frozen clock into December 2026 (00:05 on Dec 1 in Asia/Ho_Chi_Minh = Nov 30 17:05 UTC).
    db.clock["now"] = datetime(2026, 11, 30, 17, 5, tzinfo=UTC)
    reset.run_scheduled_resets()

    # December has NO carried-over November budget ("chưa ghi nhận") and exact configured base 4000 (not 8000!).
    dec_budget = qta_get(db.qta_admin, "/budgets", {"month": "2026-12"})
    assert dec_budget["status"] == "NOT_RECORDED"
    assert dec_budget["status_label"] == "chưa ghi nhận"
    assert dec_budget["allocated"] == 4000

    dec_ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements", {"month": "2026-12"})
    assert dec_ent["base_entitlement_total"] == 4000
    assert _by_model(dec_ent)[db.m_ext]["base_entitlement"] == 1500
    assert _by_model(dec_ent)[db.m_int]["base_entitlement"] == 2500


def test_active_suspension_survives_reset(qta4):
    """QD8: monthly reset never lifts an active disciplinary suspension."""
    db = qta4
    user = _setup_entitled_user(db, "usurvive")
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Kỷ luật", "ordered_by": "Hiệu trưởng"},
        201,
    )

    qta_send(db.qta_admin, "POST", "/monthly-resets", None, 201)
    ent = qta_get(db.qta_admin, f"/users/{user['id']}/entitlements")
    assert ent["quota_status"] == "SUSPENDED"
    assert all(m["access"] == {"allowed": False, "reason": "SUSPENDED_ALL_MODELS"} for m in ent["models"])


def test_q4_rbac_and_csrf(qta4):
    """FR-QTA-001: full RBAC, UNIT scope, anonymous 401, CSRF & exact Origin enforcement on Q4 routes."""
    db = qta4
    user_a = create_user(db.admin, db.unit_a, "urbac_a", active=True)
    user_b = create_user(db.admin, db.unit_b, "urbac_b", active=True)
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{user_a['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Test RBAC", "ordered_by": "BGH"},
        201,
    )

    # UNIT viewer: sees own-unit user suspensions (200), gets 404 on other-unit user, 403 on events & resets.
    assert len(qta_get(db.unit_viewer, f"/users/{user_a['id']}/suspensions")["items"]) == 1
    qta_get(db.unit_viewer, f"/users/{user_b['id']}/suspensions", status=404)
    qta_get(db.unit_viewer, "/events", status=403)
    qta_get(db.unit_viewer, "/monthly-resets", status=403)

    # GLOBAL viewer: can read all Q4 GETs, cannot execute any Q4 write (403).
    assert len(qta_get(db.global_viewer, f"/users/{user_a['id']}/suspensions")["items"]) == 1
    assert qta_get(db.global_viewer, "/events", status=200)
    assert qta_get(db.global_viewer, "/monthly-resets", status=200)

    write_calls = [
        ("POST", f"/users/{user_b['id']}/suspensions", {"scope": "ALL_MODELS", "reason": "X", "ordered_by": "Y"}),
        ("POST", f"/users/{user_a['id']}/restore", {"note": "X"}),
        ("POST", "/monthly-resets", None),
    ]
    for caller in (db.global_viewer, db.unit_viewer, db.admin, db.mdl_admin):
        for method, path, body in write_calls:
            qta_send(caller, method, path, body, 403)

    for caller in (db.admin, db.mdl_admin):
        qta_get(caller, f"/users/{user_a['id']}/suspensions", status=403)
        qta_get(caller, "/events", status=403)
        qta_get(caller, "/monthly-resets", status=403)

    # Anonymous -> 401 on every Q4 route.
    with client(db) as anon:
        for path in (f"/api/v1/qta/users/{user_a['id']}/suspensions", "/api/v1/qta/events", "/api/v1/qta/monthly-resets"):
            assert anon.get(path).status_code == 401
        for method, path, body in write_calls:
            assert anon.request(method, "/api/v1" + qta_path(path), json=body, headers=ORIGIN_HEADER).status_code == 401

    # Missing CSRF and wrong Origin -> 403 even for AI_QUOTA_ADMIN.
    for method, path, body in write_calls:
        no_csrf = db.qta_admin.request(method, "/api/v1" + qta_path(path), json=body, headers=ORIGIN_HEADER)
        assert no_csrf.status_code == 403
        bad_origin = db.qta_admin.request(
            method,
            "/api/v1" + qta_path(path),
            json=body,
            headers=csrf_headers(db.qta_admin) | {"Origin": "http://evil.localhost:8000"},
        )
        assert bad_origin.status_code == 403


def test_q4_tenant_isolation(qta4):
    """Cross-tenant isolation: another institution's users, suspensions, events & resets are invisible."""
    db = qta4
    other_tenant = uuid4()
    with connect(db.owner, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO institutions (id, code, name) VALUES (%s, 'OTHERQ4', 'Trường Khác')",
            (other_tenant,),
        )
        other_unit = conn.execute(
            "INSERT INTO units (institution_id, code, name) VALUES (%s, 'MAIN2', 'Đơn vị 2') RETURNING id",
            (other_tenant,),
        ).fetchone()[0]
        other_user = conn.execute(
            "INSERT INTO users (institution_id, primary_unit_id, username, display_name, "
            "code_type, institutional_code, state) VALUES "
            "(%s, %s, 'otherq4u', 'Other User', 'STAFF', 'ST-Q4U', 'ACTIVE') RETURNING id",
            (other_tenant, other_unit),
        ).fetchone()[0]
        cur_m = periods.current_month(periods.Settings())
        conn.execute(
            "INSERT INTO qta_suspensions (institution_id, user_id, scope, reason, ordered_by, suspended_by) "
            "VALUES (%s, %s, 'ALL_MODELS', 'Other tenant reason', 'Other Rector', %s)",
            (other_tenant, other_user, other_user),
        )
        conn.execute(
            "INSERT INTO qta_monthly_resets (institution_id, period_month, trigger_mode, triggered_by) "
            "VALUES (%s, %s, 'MANUAL_SIMULATION', %s)",
            (other_tenant, cur_m, other_user),
        )
        conn.execute(
            "INSERT INTO qta_events (institution_id, period_month, event_type, user_id, actor_id, summary) "
            "VALUES (%s, %s, 'SUSPEND', %s, %s, 'Other tenant event')",
            (other_tenant, cur_m, other_user, other_user),
        )

    # Primary tenant sees 404 on other_user and sees zero other-tenant events or resets.
    qta_get(db.qta_admin, f"/users/{other_user}/suspensions", status=404)
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{other_user}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Cross", "ordered_by": "BGH"},
        404,
    )
    qta_send(db.qta_admin, "POST", f"/users/{other_user}/restore", None, 404)
    assert qta_get(db.qta_admin, "/events")["items"] == []
    assert qta_get(db.qta_admin, "/monthly-resets")["items"] == []
    assert qta_get(db.qta_admin, "/monthly-resets")["current"]["status"] == "PENDING"


def test_q4_audit_failure_rolls_back(qta4):
    """Atomicity: revoking INSERT on audit_events rolls back suspend, restore, and manual reset completely."""
    db = qta4
    u_to_suspend = create_user(db.admin, db.unit_a, "uaudit1", active=True)
    u_suspended = create_user(db.admin, db.unit_a, "uaudit2", active=True)
    qta_send(
        db.qta_admin,
        "POST",
        f"/users/{u_suspended['id']}/suspensions",
        {"scope": "ALL_MODELS", "reason": "Setup", "ordered_by": "BGH"},
        201,
    )

    tables = (
        "qta_suspensions",
        "qta_suspension_restorations",
        "qta_monthly_resets",
        "qta_events",
    )
    before = {t: _table_count(db, t) for t in tables}

    runtime_role = sql.Identifier(db.roles.runtime)
    with connect(db.owner, autocommit=True) as conn:
        conn.execute(sql.SQL("REVOKE INSERT ON TABLE public.audit_events FROM {}").format(runtime_role))
    try:
        r1 = qta_send(
            db.qta_admin,
            "POST",
            f"/users/{u_to_suspend['id']}/suspensions",
            {"scope": "ALL_MODELS", "reason": "Must rollback", "ordered_by": "BGH"},
            500,
        )
        r2 = qta_send(db.qta_admin, "POST", f"/users/{u_suspended['id']}/restore", {"note": "Rollback"}, 500)
        r3 = qta_send(db.qta_admin, "POST", "/monthly-resets", None, 500)
        assert r1["code"] == r2["code"] == r3["code"] == "DATABASE_ERROR"
    finally:
        with connect(db.owner, autocommit=True) as conn:
            conn.execute(sql.SQL("GRANT INSERT ON TABLE public.audit_events TO {}").format(runtime_role))

    after = {t: _table_count(db, t) for t in tables}
    assert after == before


def test_users_list_and_lookup_show_quota_status_without_n_plus_1(qta4):
    """Set-based suspension lookup keeps SQL query count constant across a 20-user page and multi-model lookup."""
    db = qta4
    created_users = []
    for idx in range(20):
        u = create_user(db.admin, db.unit_a, f"un1_{idx:02d}", active=True)
        created_users.append(u)
        if idx % 2 == 0:
            qta_send(
                db.qta_admin,
                "POST",
                f"/users/{u['id']}/suspensions",
                {"scope": "ALL_MODELS", "reason": "Batch test", "ordered_by": "BGH"},
                201,
            )

    statements: list[str] = []

    def _count_sql(_conn, _cursor, statement, _params, _context, _executemany):
        statements.append(statement)

    sa.event.listen(sa.engine.Engine, "before_cursor_execute", _count_sql)
    try:
        statements.clear()
        small_page = qta_get(db.qta_admin, "/users", {"q": "un1_", "limit": 2})
        small_count = len(statements)

        statements.clear()
        full_page = qta_get(db.qta_admin, "/users", {"q": "un1_", "limit": 20})
        full_count = len(statements)

        statements.clear()
        ent = qta_get(db.qta_admin, f"/users/{created_users[0]['id']}/entitlements")
        lookup_count = len(statements)
    finally:
        sa.event.remove(sa.engine.Engine, "before_cursor_execute", _count_sql)

    assert len(small_page["items"]) == 2 and len(full_page["items"]) == 20
    by_username = {item["username"]: item["quota_status"] for item in full_page["items"]}
    assert by_username["un1_00"] == "SUSPENDED"
    assert by_username["un1_01"] == "ACTIVE"
    assert ent["quota_status"] == "SUSPENDED"

    # Zero N+1: fetching 20 users uses the exact same bounded query count as fetching 2 users.
    assert full_count == small_count and full_count <= 6
    assert lookup_count <= 8
