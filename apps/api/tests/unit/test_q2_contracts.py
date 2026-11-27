"""Stage Q2 unit contracts without a database: RBAC group policy, OpenAPI, schemas, MDL isolation."""

import ast
import importlib.util
import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization.policy import (
    ActorAuthority,
    EffectiveGrant,
    GrantScope,
    PermissionCode,
    require_group_management,
)
from aq_uai_api.main import create_app
from aq_uai_api.qta import schemas

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "aq_uai_api"
FORBIDDEN_FIELD = re.compile(
    r"period|semester|cycle|price|token|credit|consumption", re.IGNORECASE
)


def _authority(institution_id: UUID, permissions: tuple[PermissionCode, ...]) -> ActorAuthority:
    grants = tuple(
        EffectiveGrant(
            assignment_id=uuid4(),
            role_code="TEST_ROLE",
            permission=perm,
            institution_id=institution_id,
            scope=GrantScope.GLOBAL,
            unit_id=None,
            group_id=None,
        )
        for perm in permissions
    )
    return ActorAuthority(actor_id=uuid4(), institution_id=institution_id, grants=grants)


@pytest.fixture(scope="module")
def openapi():
    return create_app().openapi()


@pytest.mark.parametrize(
    ("kind", "permission", "allowed"),
    [
        # SYSTEM: directory.manage only
        ("SYSTEM", PermissionCode.DIRECTORY_MANAGE, True),
        ("SYSTEM", PermissionCode.QTA_MANAGE, False),
        ("SYSTEM", PermissionCode.AUTHORIZATION_MANAGE, False),
        ("SYSTEM", None, False),
        # AUTHORIZATION: authorization.manage only
        ("AUTHORIZATION", PermissionCode.DIRECTORY_MANAGE, False),
        ("AUTHORIZATION", PermissionCode.QTA_MANAGE, False),
        ("AUTHORIZATION", PermissionCode.AUTHORIZATION_MANAGE, True),
        ("AUTHORIZATION", None, False),
        # AI_SPECIALIST: directory.manage OR qta.manage
        ("AI_SPECIALIST", PermissionCode.DIRECTORY_MANAGE, True),
        ("AI_SPECIALIST", PermissionCode.QTA_MANAGE, True),
        ("AI_SPECIALIST", PermissionCode.AUTHORIZATION_MANAGE, False),
        ("AI_SPECIALIST", None, False),
    ],
)
def test_require_group_management_matrix(kind, permission, allowed):
    tenant = uuid4()
    other_tenant = uuid4()
    perms = () if permission is None else (permission,)
    authority = _authority(tenant, perms)

    if allowed:
        require_group_management(authority, tenant, kind)
        # Never allows another institution even with a valid permission.
        with pytest.raises(DomainError) as cross:
            require_group_management(authority, other_tenant, kind)
        assert cross.value.code is ErrorCode.FORBIDDEN
    else:
        with pytest.raises(DomainError) as denied:
            require_group_management(authority, tenant, kind)
        assert denied.value.code is ErrorCode.FORBIDDEN


def test_require_group_management_rejects_unknown_kind():
    tenant = uuid4()
    authority = _authority(
        tenant,
        (PermissionCode.DIRECTORY_MANAGE, PermissionCode.AUTHORIZATION_MANAGE, PermissionCode.QTA_MANAGE),
    )
    with pytest.raises(DomainError) as invalid:
        require_group_management(authority, tenant, "PROJECT")
    assert invalid.value.code is ErrorCode.VALIDATION_FAILED


def test_qta_openapi_routes_and_no_sync_run_mutation(openapi):
    paths = {path: set(ops) for path, ops in openapi["paths"].items() if "/qta" in path}
    assert paths == {
        "/api/v1/qta/models": {"get"},
        "/api/v1/qta/groups": {"get", "post"},
        "/api/v1/qta/groups/sync": {"post"},
        "/api/v1/qta/groups/sync-runs": {"get"},
        "/api/v1/qta/groups/{group_id}": {"get", "patch"},
        "/api/v1/qta/groups/{group_id}/activate": {"post"},
        "/api/v1/qta/groups/{group_id}/deactivate": {"post"},
        "/api/v1/qta/groups/{group_id}/members": {"get"},
        "/api/v1/qta/groups/{group_id}/members/{user_id}": {"put", "delete"},
        "/api/v1/qta/groups/{group_id}/quotas": {"put"},
    }
    assert paths["/api/v1/qta/groups/sync-runs"] == {"get"}


def test_qta_openapi_has_no_forbidden_fields_and_rejects_unknown_inputs(openapi):
    qta_schemas = {
        name: schema
        for name, schema in openapi["components"]["schemas"].items()
        if name in dir(schemas)
    }
    assert qta_schemas
    for name, schema in qta_schemas.items():
        props = list(schema.get("properties", {}).keys())
        assert not [key for key in props if FORBIDDEN_FIELD.search(key)], (name, props)
        assert not FORBIDDEN_FIELD.search(json.dumps(schema)), name
    for path, operations in openapi["paths"].items():
        if "/qta" in path:
            assert not FORBIDDEN_FIELD.search(json.dumps(operations)), path

    for model, valid_data in (
        (schemas.CreateSpecialistGroup, {"code": "AI_LAB", "name": "AI Lab"}),
        (schemas.UpdateSpecialistGroup, {"name": "AI Lab 2"}),
        (
            schemas.GroupQuotaItemIn,
            {"model_id": str(uuid4()), "enabled": True, "monthly_limit": 1000},
        ),
        (
            schemas.UpsertGroupQuotas,
            {"quotas": [{"model_id": str(uuid4()), "enabled": True, "monthly_limit": 1000}]},
        ),
    ):
        assert model.model_validate(valid_data)
        for bad_key in ("period", "semester", "cycle", "price", "token", "credit", "consumption", "extra"):
            with pytest.raises(ValidationError):
                model.model_validate(valid_data | {bad_key: "x"})

    model_id = str(uuid4())
    # Duplicate model_id, negative limits, booleans as ints, and out-of-range pct rejected.
    for invalid in (
        {"quotas": []},
        {
            "quotas": [
                {"model_id": model_id, "enabled": True, "monthly_limit": 100},
                {"model_id": model_id, "enabled": False, "monthly_limit": 0},
            ]
        },
        {"quotas": [{"model_id": model_id, "enabled": True, "monthly_limit": -1}]},
        {"quotas": [{"model_id": model_id, "enabled": True, "monthly_limit": True}]},
        {"quotas": [{"model_id": model_id, "enabled": "yes", "monthly_limit": 100}]},
        {"quotas": [{"model_id": model_id, "enabled": True, "monthly_limit": 100, "warning_threshold_pct": 0}]},
        {"quotas": [{"model_id": model_id, "enabled": True, "monthly_limit": 100, "warning_threshold_pct": 101}]},
    ):
        with pytest.raises(ValidationError):
            schemas.UpsertGroupQuotas.model_validate(invalid)


def test_mdl_import_closure_reaches_no_qta_code():
    """FR-MDL-020 AC3 (static): every aq_uai_api module reachable from MDL never touches QTA."""
    seen: set[str] = set()
    queue = ["aq_uai_api.mdl", "aq_uai_api.api.v1.mdl"]
    queue += [f"aq_uai_api.mdl.{path.stem}" for path in (SRC_ROOT / "mdl").glob("*.py")]
    while queue:
        name = queue.pop()
        if name in seen or not name.startswith("aq_uai_api"):
            continue
        seen.add(name)
        try:
            spec = importlib.util.find_spec(name)
        except (ModuleNotFoundError, AttributeError):
            continue
        if spec is None or spec.origin is None:
            continue
        tree = ast.parse(Path(spec.origin).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                queue += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                queue.append(node.module)
                queue += [f"{node.module}.{alias.name}" for alias in node.names]
        if spec.submodule_search_locations:
            queue += [f"{name}.{path.stem}" for path in Path(spec.origin).parent.glob("*.py")]
    assert not [mod for mod in seen if re.search(r"qta|quota|credit|crt", mod)]
