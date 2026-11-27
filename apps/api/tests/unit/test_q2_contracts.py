"""Stage Q2 unit contracts without a database: RBAC group policy, OpenAPI, schemas, MDL isolation."""

import ast
import importlib.util
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
FORBIDDEN_WORDS = frozenset(
    {
        "period",
        "semester",
        "cycle",
        "price",
        "cost",
        "token",
        "tokens",
        "credit",
        "credits",
        "consumption",
        "conversion",
        "exam",
        "project",
    }
)
FORBIDDEN_ADJACENT_PAIRS = frozenset({("hoc", "ky"), ("de", "tai"), ("dot", "thi")})
ALLOWED_RESPONSE_PROPS = frozenset({"actual_consumption", "consumption_status"})
_CAMEL_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+")


def _split_identifier(name: str) -> list[str]:
    """Split an identifier on non-alphanumeric separators and camelCase boundaries."""
    tokens: list[str] = []
    for chunk in re.split(r"[^A-Za-z0-9]+", name):
        if not chunk:
            continue
        tokens.extend(tok.lower() for tok in _CAMEL_TOKEN.findall(chunk))
    return tokens


def _is_forbidden_identifier(name: str) -> bool:
    tokens = _split_identifier(name)
    if any(tok in FORBIDDEN_WORDS for tok in tokens):
        return True
    return any((tokens[i], tokens[i + 1]) in FORBIDDEN_ADJACENT_PAIRS for i in range(len(tokens) - 1))


def _collect_refs(node: object) -> set[str]:
    """Collect component schema names referenced via ``$ref`` without inspecting prose keys."""
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            refs.add(ref.removeprefix("#/components/schemas/"))
        for key, value in node.items():
            if key in {"description", "title", "summary"}:
                continue
            refs.update(_collect_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.update(_collect_refs(item))
    return refs


def _collect_enum_values(node: object) -> list[str]:
    """Collect string ``enum`` / ``const`` values without inspecting prose keys."""
    values: list[str] = []
    if isinstance(node, dict):
        if isinstance(node.get("enum"), list):
            values.extend(v for v in node["enum"] if isinstance(v, str))
        if isinstance(node.get("const"), str):
            values.append(node["const"])
        for key, value in node.items():
            if key in {"description", "title", "summary"}:
                continue
            values.extend(_collect_enum_values(value))
    elif isinstance(node, list):
        for item in node:
            values.extend(_collect_enum_values(item))
    return values


def _expand_refs(seed: set[str], all_schemas: dict[str, dict]) -> set[str]:
    seen: set[str] = set()
    queue = list(seed)
    while queue:
        name = queue.pop()
        if name in seen or name not in all_schemas:
            continue
        seen.add(name)
        queue.extend(_collect_refs(all_schemas[name]) - seen)
    return seen


def _schema_identifier_violations(
    name: str, schema: dict, *, is_response: bool
) -> list[tuple[str, str, str]]:
    """Return forbidden property-name or enum-value violations for one OpenAPI schema."""
    violations: list[tuple[str, str, str]] = []
    allowed = ALLOWED_RESPONSE_PROPS if is_response else frozenset()
    for prop in schema.get("properties", {}):
        if prop in allowed:
            continue
        if _is_forbidden_identifier(prop):
            violations.append((name, "property", prop))
    for enum_val in _collect_enum_values(schema):
        if _is_forbidden_identifier(enum_val):
            violations.append((name, "enum", enum_val))
    return violations


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
        "/api/v1/qta/users": {"get"},
        "/api/v1/qta/users/{user_id}/entitlements": {"get"},
        "/api/v1/qta/users/{user_id}/suspensions": {"get", "post"},
        "/api/v1/qta/users/{user_id}/restore": {"post"},
        "/api/v1/qta/budgets": {"get"},
        "/api/v1/qta/budgets/{month}": {"put"},
        "/api/v1/qta/events": {"get"},
        "/api/v1/qta/monthly-resets": {"get", "post"},
    }
    assert paths["/api/v1/qta/groups/sync-runs"] == {"get"}


def test_forbidden_identifier_check_semantics():
    """C5: identifier-segment check avoids substring false positives while catching real leaks."""
    assert _split_identifier("lifecycle_status") == ["lifecycle", "status"]
    assert not _is_forbidden_identifier("lifecycle_status")
    assert _is_forbidden_identifier("semester_id")
    assert _is_forbidden_identifier("hoc_ky")
    assert _is_forbidden_identifier("hocKy")
    assert _is_forbidden_identifier("de_tai")
    assert _is_forbidden_identifier("dot-thi")
    assert _is_forbidden_identifier("consumption_status")

    sample_schema = {
        "type": "object",
        "description": "Prose mentioning period, semester, cycle, token, credit, price, hoc ky.",
        "properties": {
            "lifecycle_status": {"type": "string"},
            "actual_consumption": {"type": "null"},
            "consumption_status": {"type": "string", "enum": ["NOT_INTEGRATED"]},
        },
    }
    assert _schema_identifier_violations("SampleOut", sample_schema, is_response=True) == []
    assert [
        (kind, ident)
        for _, kind, ident in _schema_identifier_violations("SampleIn", sample_schema, is_response=False)
    ] == [("property", "actual_consumption"), ("property", "consumption_status")]


def test_qta_openapi_has_no_forbidden_fields_and_rejects_unknown_inputs(openapi):
    # C5 / R4: inspect identifiers only (path segments, parameter names, enum values, and
    # reachable schema properties; never prose description/title/summary). Request schemas,
    # query/path parameters, and enum values stay strictly free of forbidden terms; response
    # schemas allow only actual_consumption and consumption_status from architecture §2.3.
    all_schemas = openapi["components"]["schemas"]
    request_roots: set[str] = set()
    response_roots: set[str] = set()
    violations: list[tuple[str, str, str]] = []

    for path, path_item in openapi["paths"].items():
        if "/qta" not in path:
            continue
        for segment in path.split("/"):
            cleaned = segment.strip("{}")
            if cleaned and _is_forbidden_identifier(cleaned):
                violations.append((path, "path_segment", cleaned))
        path_params = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or method == "parameters":
                continue
            for param in [*path_params, *operation.get("parameters", [])]:
                param_name = param.get("name", "")
                if _is_forbidden_identifier(param_name):
                    violations.append((f"{method.upper()} {path}", "parameter", param_name))
                for enum_val in _collect_enum_values(param.get("schema", {})):
                    if _is_forbidden_identifier(enum_val):
                        violations.append((f"{method.upper()} {path}", "param_enum", enum_val))
                request_roots.update(_collect_refs(param))
            if "requestBody" in operation:
                request_roots.update(_collect_refs(operation["requestBody"]))
            if "responses" in operation:
                response_roots.update(_collect_refs(operation["responses"]))

    request_schemas = _expand_refs(request_roots, all_schemas)
    response_schemas = _expand_refs(response_roots, all_schemas)
    # Also include every QTA schema exported from aq_uai_api.qta.schemas.
    for name in all_schemas:
        if name in dir(schemas):
            model = getattr(schemas, name, None)
            if isinstance(model, type) and issubclass(model, schemas.Output):
                response_schemas.add(name)
            else:
                request_schemas.add(name)

    assert request_schemas and response_schemas
    for name in sorted(request_schemas):
        violations.extend(_schema_identifier_violations(name, all_schemas[name], is_response=False))
    for name in sorted(response_schemas - request_schemas):
        violations.extend(_schema_identifier_violations(name, all_schemas[name], is_response=True))
    assert not violations, violations

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
