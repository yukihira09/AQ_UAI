"""M3 contracts without a database: OpenAPI surface, input rules and static guards."""

import ast
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from aq_uai_api.db import audit
from aq_uai_api.main import create_app
from aq_uai_api.mdl import schemas

MDL_PACKAGE = Path(schemas.__file__).parent
FORBIDDEN_FIELD = re.compile(r"prompt|temperature|template|creativ", re.IGNORECASE)


@pytest.fixture(scope="module")
def openapi():
    return create_app().openapi()


def test_routes_exist_under_one_versioned_prefix(openapi):
    paths = {path: set(ops) for path, ops in openapi["paths"].items() if "/mdl" in path}
    assert paths == {
        "/api/v1/mdl/status": {"get"},
        "/api/v1/mdl/providers": {"get", "post"},
        "/api/v1/mdl/providers/{provider_id}": {"get", "patch"},
        "/api/v1/mdl/providers/{provider_id}/activate": {"post"},
        "/api/v1/mdl/providers/{provider_id}/deactivate": {"post"},
        "/api/v1/mdl/providers/{provider_id}/agreements": {"get", "post"},
        "/api/v1/mdl/providers/{provider_id}/agreements/{agreement_id}/withdraw": {"post"},
        "/api/v1/mdl/models": {"get", "post"},
        "/api/v1/mdl/models/{model_id}": {"get", "patch"},
        "/api/v1/mdl/models/{model_id}/activate": {"post"},
        "/api/v1/mdl/models/{model_id}/deactivate": {"post"},
        "/api/v1/mdl/models/{model_id}/connection-tests": {"get", "post"},  # M4
        "/api/v1/mdl/routing": {"get", "put"},  # M5
        "/api/v1/mdl/routing/revisions": {"get"},  # M5
        "/api/v1/mdl/history": {"get"},  # M7
    }
    assert not any(op == "delete" for ops in paths.values() for op in ops)  # no hard delete


def test_openapi_has_no_assistant_prompt_configuration(openapi):
    """FR-MDL-040 / RULE-MDL-03: no prompt, temperature, creativity or template field."""
    mdl_schemas = {
        name: schema
        for name, schema in openapi["components"]["schemas"].items()
        if name in dir(schemas)
    }
    assert mdl_schemas
    for name, schema in mdl_schemas.items():
        assert not FORBIDDEN_FIELD.search(json.dumps(schema)), name
    for path, operations in openapi["paths"].items():
        if "/mdl" in path:
            assert not FORBIDDEN_FIELD.search(json.dumps(operations)), path


def test_no_response_schema_can_carry_a_secret(openapi):
    for name in dir(schemas):
        model = getattr(schemas, name)
        if isinstance(model, type) and issubclass(model, schemas.Output):
            fields = set(model.model_fields)
            assert not fields & {"secret", "ciphertext", "nonce", "key", "api_key", "password"}, name
    assert "secret" in schemas.CreateProvider.model_fields
    assert schemas.CreateProvider.model_json_schema()["properties"]["secret"]["anyOf"][0][
        "writeOnly"
    ]


@pytest.mark.parametrize("model", [schemas.CreateProvider, schemas.CreateModel, schemas.AgreementIn])
@pytest.mark.parametrize("field", ["prompt", "system_prompt", "temperature", "template", "id"])
def test_inputs_reject_unknown_fields(model, field):
    with pytest.raises(ValidationError):
        model.model_validate({field: "x"})


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://API.Example.test/v1/", "https://api.example.test/v1"),
        ("https://api.example.test:443", "https://api.example.test"),
        ("http://ollama:11434/v1", "http://ollama:11434/v1"),
        ("https://api.example.test/V1/Chat", "https://api.example.test/V1/Chat"),
    ],
)
def test_endpoints_are_canonical(endpoint, expected):
    assert schemas.canonical_endpoint(endpoint) == expected


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://x.test",
        "https://user:pw@x.test",
        "https://x.test/?a=1",
        "https://x.test/#f",
        "https://x.test/a b",
        "https://x.test/\x00",
        "x.test",
    ],
)
def test_unsafe_endpoints_are_rejected(endpoint):
    with pytest.raises(ValueError):
        schemas.canonical_endpoint(endpoint)


def test_secret_input_is_masked_and_blank_means_keep():
    created = schemas.CreateProvider(
        name="A", provider_type="EXTERNAL", endpoint="https://a.test", auth_scheme="BEARER",
        secret="sk-unit-canary",
    )
    assert "sk-unit-canary" not in repr(created) and "sk-unit-canary" not in str(created.model_dump())
    for blank in ("", "   ", None):
        assert schemas.ProviderPatch(secret=blank).secret is None
    with pytest.raises(ValidationError):
        schemas.CreateProvider(
            name="A", provider_type="EXTERNAL", endpoint="https://a.test", auth_scheme="BEARER",
            secret="x" * 4097,
        )


@pytest.mark.parametrize("header", ["Host", "content-length", "Cookie", "X-Forwarded-For", "a b"])
def test_dangerous_credential_headers_are_rejected(header):
    with pytest.raises(ValidationError):
        schemas.CreateProvider(
            name="A", provider_type="EXTERNAL", endpoint="https://a.test",
            auth_scheme="HEADER_KEY", auth_header_name=header, secret="x",
        )


def test_header_name_only_with_header_key():
    base = {"name": "A", "provider_type": "EXTERNAL", "endpoint": "https://a.test"}
    with pytest.raises(ValidationError):
        schemas.CreateProvider(**base, auth_scheme="HEADER_KEY")
    with pytest.raises(ValidationError):
        schemas.CreateProvider(**base, auth_scheme="BEARER", auth_header_name="X-Key")
    assert schemas.CreateProvider(**base, auth_scheme="HEADER_KEY", auth_header_name="X-Key", secret="s")


def test_patches_need_a_field_and_cannot_null_required_ones():
    for patch in (schemas.ProviderPatch, schemas.ModelPatch):
        with pytest.raises(ValidationError):
            patch()
    with pytest.raises(ValidationError):
        schemas.ProviderPatch(endpoint=None)
    with pytest.raises(ValidationError):
        schemas.ModelPatch(capabilities=None)
    assert schemas.ModelPatch(risk_level=None).model_fields_set == {"risk_level"}
    assert schemas.ModelPatch(max_output_tokens=None).model_fields_set == {"max_output_tokens"}


def test_capabilities_are_distinct_and_ordered():
    body = {"provider_id": "00000000-0000-0000-0000-000000000001", "technical_id": "m", "display_name": "M"}
    assert schemas.CreateModel(**body, capabilities=["VOICE", "TEXT"]).capabilities == ["TEXT", "VOICE"]
    for invalid in ([], ["TEXT", "TEXT"], ["AUDIO"]):
        with pytest.raises(ValidationError):
            schemas.CreateModel(**body, capabilities=invalid)


def test_audit_payloads_carry_no_endpoint_path_or_secret():
    for model in (audit.ProviderCreated, audit.ProviderChange, audit.CredentialRotated):
        text = json.dumps(model.model_json_schema())
        assert "secret" not in text and '"endpoint"' not in text
    with pytest.raises(ValidationError):
        audit.CredentialRotated(credential_version=1, secret="x")


def test_mdl_code_has_no_quota_or_credit_path():
    """FR-MDL-020 groundwork: MDL never imports quota or credit code (static check)."""
    for source in MDL_PACKAGE.rglob("*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] + [getattr(node, "module", "") or ""]
                assert not any(re.search(r"quota|credit|qta|crt", name) for name in names), source


def test_mdl_code_never_logs():
    for source in MDL_PACKAGE.rglob("*.py"):
        text = source.read_text()
        assert "import logging" not in text and "print(" not in text, source
