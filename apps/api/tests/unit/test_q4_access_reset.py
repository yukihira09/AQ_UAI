"""Stage Q4 unit tests without a database: access decision table, lazy expiry, OpenAPI & CLI."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aq_uai_api.main import create_app
from aq_uai_api.qta import access, periods, reset, schemas
from aq_uai_api.qta.models import QtaSuspension, QtaSuspensionRestoration


def _make_suspension(
    *,
    scope: str = "ALL_MODELS",
    expires_at: datetime | None = None,
    suspended_at: datetime | None = None,
) -> QtaSuspension:
    base = suspended_at or datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    return QtaSuspension(
        id=uuid4(),
        institution_id=uuid4(),
        user_id=uuid4(),
        scope=scope,
        reason="Vi phạm quy chế sử dụng AI",
        ordered_by="Hiệu trưởng",
        expires_at=expires_at,
        suspended_by=uuid4(),
        suspended_at=base,
    )


def _make_restoration(suspension: QtaSuspension, note: str | None = None) -> QtaSuspensionRestoration:
    return QtaSuspensionRestoration(
        suspension_id=suspension.id,
        institution_id=suspension.institution_id,
        restored_by=uuid4(),
        restored_at=datetime(2026, 11, 12, 0, 0, tzinfo=UTC),
        note=note,
    )


def test_access_decision_table_order(monkeypatch):
    """R5 / R9: verify all 7 outcomes and strict precedence when multiple failure conditions hold."""
    susp_all = _make_suspension(scope="ALL_MODELS")
    susp_paid = _make_suspension(scope="PAID_EXTERNAL_ONLY")

    # 1. USER_NOT_FOUND wins even when user inactive, model unavailable, suspended, and 0 entitlement.
    d1 = access.evaluate_access_rule(
        user_exists=False,
        user_state="DISABLED",
        model_usable=False,
        provider_type="EXTERNAL",
        active_suspension=susp_all,
        base_entitlement=0,
    )
    assert d1 == access.AccessDecision(allowed=False, reason="USER_NOT_FOUND", suspension_id=None)

    # 2. USER_NOT_ACTIVE wins over unavailable model, active suspension, and 0 entitlement.
    for state in ("PENDING", "DISABLED"):
        d2 = access.evaluate_access_rule(
            user_exists=True,
            user_state=state,
            model_usable=False,
            provider_type="EXTERNAL",
            active_suspension=susp_all,
            base_entitlement=0,
        )
        assert d2 == access.AccessDecision(
            allowed=False, reason="USER_NOT_ACTIVE", suspension_id=None
        )

    # 3. MODEL_UNAVAILABLE wins over active suspension and 0 entitlement.
    d3 = access.evaluate_access_rule(
        user_exists=True,
        user_state="ACTIVE",
        model_usable=False,
        provider_type="EXTERNAL",
        active_suspension=susp_all,
        base_entitlement=0,
    )
    assert d3 == access.AccessDecision(
        allowed=False, reason="MODEL_UNAVAILABLE", suspension_id=None
    )

    # 4. SUSPENDED_ALL_MODELS wins over 0 entitlement (and carries suspension_id).
    d4 = access.evaluate_access_rule(
        user_exists=True,
        user_state="ACTIVE",
        model_usable=True,
        provider_type="INTERNAL",
        active_suspension=susp_all,
        base_entitlement=0,
    )
    assert d4 == access.AccessDecision(
        allowed=False, reason="SUSPENDED_ALL_MODELS", suspension_id=susp_all.id
    )

    # 5. SUSPENDED_PAID_EXTERNAL wins over 0 entitlement on EXTERNAL, but falls through on INTERNAL.
    d5_ext = access.evaluate_access_rule(
        user_exists=True,
        user_state="ACTIVE",
        model_usable=True,
        provider_type="EXTERNAL",
        active_suspension=susp_paid,
        base_entitlement=0,
    )
    assert d5_ext == access.AccessDecision(
        allowed=False, reason="SUSPENDED_PAID_EXTERNAL", suspension_id=susp_paid.id
    )

    # 6. NO_ENTITLEMENT when PAID_EXTERNAL_ONLY meets an INTERNAL model with 0 base entitlement.
    d6 = access.evaluate_access_rule(
        user_exists=True,
        user_state="ACTIVE",
        model_usable=True,
        provider_type="INTERNAL",
        active_suspension=susp_paid,
        base_entitlement=0,
    )
    assert d6 == access.AccessDecision(allowed=False, reason="NO_ENTITLEMENT", suspension_id=None)

    # 7. ALLOWED when all checks pass and base_entitlement > 0.
    d7 = access.evaluate_access_rule(
        user_exists=True,
        user_state="ACTIVE",
        model_usable=True,
        provider_type="INTERNAL",
        active_suspension=susp_paid,
        base_entitlement=1500,
    )
    assert d7 == access.AccessDecision(allowed=True, reason=None, suspension_id=None)

    # Also verify check_ai_access short-circuits cleanly without writes.
    inst_id, uid, mid = uuid4(), uuid4(), uuid4()
    fake_db_missing = SimpleNamespace(scalar=lambda _stmt: None)
    assert access.check_ai_access(fake_db_missing, inst_id, uid, mid).reason == "USER_NOT_FOUND"

    fake_db_disabled = SimpleNamespace(scalar=lambda _stmt: "DISABLED")
    assert access.check_ai_access(fake_db_disabled, inst_id, uid, mid).reason == "USER_NOT_ACTIVE"

    fake_db_no_model = SimpleNamespace(
        scalar=lambda _stmt: "ACTIVE",
        execute=lambda _stmt: SimpleNamespace(one_or_none=lambda: None),
    )
    assert access.check_ai_access(fake_db_no_model, inst_id, uid, mid).reason == "MODEL_UNAVAILABLE"

    monkeypatch.setattr(access, "active_suspension_for_user", lambda *_a, **_k: None)
    monkeypatch.setattr(access.entitlements, "user_model_base_entitlement", lambda *_a: 2000)
    fake_provider = SimpleNamespace(provider_type="EXTERNAL")
    fake_db_ok = SimpleNamespace(
        scalar=lambda _stmt: "ACTIVE",
        execute=lambda _stmt: SimpleNamespace(one_or_none=lambda: (SimpleNamespace(id=mid), fake_provider)),
    )
    assert access.check_ai_access(fake_db_ok, inst_id, uid, mid) == access.AccessDecision(
        allowed=True, reason=None, suspension_id=None
    )


def test_paid_external_only_matrix():
    """RULE-QTA-03 & PD-Q2: PAID_EXTERNAL_ONLY blocks EXTERNAL and allows INTERNAL; ALL_MODELS blocks both."""
    susp_paid = _make_suspension(scope="PAID_EXTERNAL_ONLY")
    susp_all = _make_suspension(scope="ALL_MODELS")

    cases = [
        (None, "INTERNAL", True, None, None),
        (None, "EXTERNAL", True, None, None),
        (susp_paid, "INTERNAL", True, None, None),
        (susp_paid, "EXTERNAL", False, "SUSPENDED_PAID_EXTERNAL", susp_paid.id),
        (susp_all, "INTERNAL", False, "SUSPENDED_ALL_MODELS", susp_all.id),
        (susp_all, "EXTERNAL", False, "SUSPENDED_ALL_MODELS", susp_all.id),
    ]
    for susp, provider_type, expected_allowed, expected_reason, expected_susp_id in cases:
        decision = access.evaluate_access_rule(
            user_exists=True,
            user_state="ACTIVE",
            model_usable=True,
            provider_type=provider_type,
            active_suspension=susp,
            base_entitlement=1000,
        )
        assert decision == access.AccessDecision(
            allowed=expected_allowed,
            reason=expected_reason,
            suspension_id=expected_susp_id,
        ), (susp, provider_type)


def test_lazy_expiry_none_future_past(monkeypatch):
    """PD-Q3: suspension status is evaluated lazily against periods.utc_now() without DB writes."""
    frozen = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(periods, "utc_now", lambda: frozen)

    open_susp = _make_suspension(expires_at=None)
    future_susp = _make_suspension(expires_at=frozen + timedelta(seconds=1))
    exact_susp = _make_suspension(expires_at=frozen)
    past_susp = _make_suspension(expires_at=frozen - timedelta(seconds=1))

    assert access.suspension_status(open_susp, None) == "ACTIVE"
    assert access.suspension_status(future_susp, None) == "ACTIVE"
    assert access.suspension_status(exact_susp, None) == "EXPIRED"
    assert access.suspension_status(past_susp, None) == "EXPIRED"

    # Once restored, status is always RESTORED regardless of expires_at.
    for s in (open_susp, future_susp, past_susp):
        rest = _make_restoration(s, note="Đã khôi phục")
        out = access.suspension_out(s, rest)
        assert out.status == "RESTORED"
        assert out.restoration is not None and out.restoration.note == "Đã khôi phục"


def test_q4_openapi_routes_and_no_mutation_of_history(monkeypatch):
    """FR-QTA-050 AC2, PD-Q3, PD-Q6: exact Q4 routes, zero mutation of history, strict bodies."""
    frozen = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(periods, "utc_now", lambda: frozen)

    openapi = create_app().openapi()
    qta_paths = {path: set(ops) for path, ops in openapi["paths"].items() if "/qta" in path}

    assert qta_paths["/api/v1/qta/users/{user_id}/suspensions"] == {"get", "post"}
    assert qta_paths["/api/v1/qta/users/{user_id}/restore"] == {"post"}
    assert qta_paths["/api/v1/qta/events"] == {"get"}
    assert qta_paths["/api/v1/qta/monthly-resets"] == {"get", "post"}

    # No PATCH/PUT/DELETE on append-only resources.
    for append_only_keyword in ("suspensions", "restore", "events", "monthly-resets", "sync-runs"):
        for path, ops in qta_paths.items():
            if append_only_keyword in path:
                assert not (ops & {"patch", "put", "delete"}), (path, ops)

    # POST /monthly-resets accepts empty body only (no month field).
    reset_post = openapi["paths"]["/api/v1/qta/monthly-resets"]["post"]
    body_ref = reset_post["requestBody"]["content"]["application/json"]["schema"]
    if "$ref" in body_ref:
        ref_name = body_ref["$ref"].rsplit("/", 1)[-1]
        reset_schema = openapi["components"]["schemas"][ref_name]
    else:
        nested_ref = body_ref["anyOf"][0]["$ref"].rsplit("/", 1)[-1]
        reset_schema = openapi["components"]["schemas"][nested_ref]
    assert reset_schema.get("properties", {}) == {}
    assert reset_schema.get("additionalProperties") is False

    # SuspendUser accepts None or future aware datetime, rejects suspended_by / extra / naive / past.
    valid_base = {
        "scope": "PAID_EXTERNAL_ONLY",
        "reason": "  Cảnh báo chi phí  ",
        "ordered_by": "  Ban Giám hiệu  ",
    }
    parsed = schemas.SuspendUser.model_validate(valid_base)
    assert parsed.reason == "Cảnh báo chi phí" and parsed.ordered_by == "Ban Giám hiệu"
    assert parsed.expires_at is None

    parsed_future = schemas.SuspendUser.model_validate(
        valid_base | {"expires_at": "2026-11-25T10:00:00+07:00"}
    )
    assert parsed_future.expires_at == datetime(2026, 11, 25, 3, 0, tzinfo=UTC)

    for invalid in (
        valid_base | {"suspended_by": str(uuid4())},
        valid_base | {"actor_id": str(uuid4())},
        valid_base | {"extra": "nope"},
        valid_base | {"scope": "INTERNAL_ONLY"},
        valid_base | {"reason": "   "},
        valid_base | {"ordered_by": ""},
        valid_base | {"expires_at": "2026-11-25T10:00:00"},  # naive ISO
        valid_base | {"expires_at": frozen.isoformat()},  # exact now
        valid_base | {"expires_at": (frozen - timedelta(minutes=1)).isoformat()},  # past
        valid_base | {"expires_at": 1_800_000_000},  # integer epoch
    ):
        with pytest.raises(ValidationError):
            schemas.SuspendUser.model_validate(invalid)

    # RestoreUser accepts empty dict or trimmed note, rejects restored_by / blank note / extra.
    assert schemas.RestoreUser.model_validate({}).note is None
    assert schemas.RestoreUser.model_validate({"note": " Mở lại "}).note == "Mở lại"
    for bad_restore in (
        {"note": "   "},
        {"restored_by": str(uuid4())},
        {"extra": 1},
    ):
        with pytest.raises(ValidationError):
            schemas.RestoreUser.model_validate(bad_restore)


def test_reset_cli_output_has_no_secrets_and_counts_only(monkeypatch, capsys):
    """CLI prints only recorded=N already=M on stdout and leaks zero exception details on failure."""
    monkeypatch.setattr(
        reset,
        "run_scheduled_resets",
        lambda: reset.ScheduledResetResult(recorded=3, already=2),
    )
    assert reset.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "recorded=3 already=2\n"
    assert captured.err == ""

    def _boom():
        raise RuntimeError("postgresql://user:super-secret-pw-999@127.0.0.1/db sk-canary-777")

    monkeypatch.setattr(reset, "run_scheduled_resets", _boom)
    assert reset.main() == 1
    failed = capsys.readouterr()
    assert failed.out == ""
    assert "super-secret-pw-999" not in failed.err
    assert "sk-canary-777" not in failed.err
    assert "postgresql://" not in failed.err
