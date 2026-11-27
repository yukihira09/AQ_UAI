"""M1 shared contracts: MDL catalog shape, additive error codes and the `details` allowlist."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization import policy
from aq_uai_api.authorization.policy import GrantScope, GrantSubject, PermissionCode
from aq_uai_api.authorization.writes import WriteContext, protected, record
from aq_uai_api.directory import service
from aq_uai_api.main import create_app

GENERIC = [
    "AUTH_REQUIRED",
    "FORBIDDEN",
    "NOT_FOUND",
    "CONFLICT",
    "VALIDATION_FAILED",
    "RATE_LIMITED",
    "SERVICE_UNAVAILABLE",
    "INTERNAL_ERROR",
    "DATABASE_ERROR",
]
MDL_CODES = [
    "MDL_DPA_REQUIRED",
    "MDL_CREDENTIAL_REQUIRED",
    "MDL_CREDENTIAL_UNAVAILABLE",
    "MDL_ENDPOINT_BLOCKED",
    "MDL_MODEL_IN_USE",
    "MDL_NOT_ELIGIBLE",
    "MDL_ROUTING_CONFLICT",
    "MDL_FALLBACK_EQUALS_PRIMARY",
    "MDL_TEST_IN_PROGRESS",
    "MDL_DUPLICATE",
    "MDL_RISK_REQUIRED",
    # M4 (connection test), appended.
    "MDL_TEST_UNSUPPORTED",
    "MDL_TEST_COOLDOWN",
    "MDL_CHARGES_NOT_ACKNOWLEDGED",
]


def test_mdl_permissions_are_central_and_the_role_is_direct_global_only():
    assert PermissionCode.MDL_READ == "mdl.read" and PermissionCode.MDL_MANAGE == "mdl.manage"
    assert {PermissionCode.MDL_READ, PermissionCode.MDL_MANAGE} <= policy._CENTRAL_PERMISSIONS
    valid = policy._valid_shape
    assert valid("AI_MODEL_ADMIN", GrantSubject.USER, GrantScope.GLOBAL, None)
    assert not valid("AI_MODEL_ADMIN", GrantSubject.USER, GrantScope.UNIT, uuid4())
    for scope, unit in ((GrantScope.GLOBAL, None), (GrantScope.UNIT, uuid4())):
        assert not valid("AI_MODEL_ADMIN", GrantSubject.GROUP, scope, unit)
    assert not any(role == "AI_MODEL_VIEWER" for role, _ in policy._ROLE_SCOPES)
    assert all(
        role != "AI_MODEL_ADMIN" or subject is GrantSubject.USER
        for role, subject in policy._ROLE_SCOPES
    )


def test_error_codes_are_additive_and_generic_status_mapping_is_unchanged():
    names = [code.name for code in ErrorCode]
    assert names[: len(GENERIC)] == GENERIC
    assert names[len(GENERIC) : len(GENERIC) + len(MDL_CODES)] == MDL_CODES
    assert len({code.value for code in ErrorCode}) == len(names)
    app = create_app()

    @app.get("/test-status/{status}")
    def raise_status(status: int):
        raise HTTPException(status)

    with TestClient(app) as browser:
        for status, expected in (
            (409, "CONFLICT"),
            (422, "VALIDATION_FAILED"),
            (503, "SERVICE_UNAVAILABLE"),
        ):
            assert browser.get(f"/test-status/{status}").json()["code"] == expected


def test_responses_without_details_keep_the_original_three_keys():
    app = create_app()

    @app.get("/test-plain")
    def plain():
        raise DomainError(ErrorCode.CONFLICT)

    with TestClient(app) as browser:
        body = browser.get("/test-plain").json()
    assert set(body) == {"code", "message", "request_id"}


def test_details_use_an_allowlist_and_are_emitted_only_when_present():
    app = create_app()

    @app.get("/test-in-use")
    def in_use():
        raise DomainError(ErrorCode.MDL_MODEL_IN_USE, {"used_in": ["routing.primary"]})

    with TestClient(app) as browser:
        response = browser.get("/test-in-use")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "MDL_MODEL_IN_USE"
    assert body["details"] == {"used_in": ["routing.primary"]}
    assert set(body) == {"code", "message", "request_id", "details"}
    assert DomainError(ErrorCode.CONFLICT, {}).details is None


@pytest.mark.parametrize(
    "details",
    [
        {"message": "free text"},
        {"used_in": "routing"},
        {"used_in": ["Routing Primary"]},
        {"used_in": ["secret sk-live-123"]},
        {"used_in": [1]},
        {"used_in": ["x"] * 17},
        {"used_in": ["a" * 65]},
        {"used_in": ["routing"], "extra": ["x"]},
    ],
)
def test_details_reject_unlisted_keys_and_free_form_values(details):
    with pytest.raises(ValueError):
        DomainError(ErrorCode.MDL_MODEL_IN_USE, details)


def test_mdl_path_is_private_and_unauthenticated_requests_are_not_cached():
    with TestClient(create_app()) as browser:
        response = browser.get("/api/v1/mdl/status")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_write_helpers_are_shared_and_reexported_by_the_directory_service():
    assert service.WriteContext is WriteContext
    assert service.record is record
    assert service.protected is not protected  # directory keeps its group-kind lock hint
    assert service.shared_protected is protected
