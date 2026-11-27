"""M5 contracts without a database: routing input rules, error details, migrations."""

import re
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.db import audit
from aq_uai_api.mdl import queries, routing, schemas
from aq_uai_api.mdl.models import API_STYLES

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def test_every_revision_id_fits_alembic_version_column():
    """alembic_version.version_num is VARCHAR(32); a longer ID fails only at upgrade."""
    for source in MIGRATIONS.glob("*.py"):
        revision = re.search(r'^revision = "([^"]+)"', source.read_text(), re.MULTILINE).group(1)
        assert len(revision) <= 32 and source.stem == revision, source.name


def test_worst_case_refusal_fits_the_reasons_detail():
    reasons = [f"{slot}.{code}" for slot in routing.SLOTS for code in queries.ROUTING_ISSUE_CODES]
    assert DomainError(ErrorCode.MDL_NOT_ELIGIBLE, {"reasons": reasons}).details == {
        "reasons": reasons
    }
    for invalid in (["Primary.X"], ["primary.dpa missing"], "primary.dpa_missing", ["x"] * 49):
        with pytest.raises(ValueError):
            DomainError(ErrorCode.MDL_NOT_ELIGIBLE, {"reasons": invalid})


def test_routing_input_rules():
    model = uuid4()
    assert schemas.RoutingIn(expected_revision=0, primary_model_id=None).fallback_model_id is None
    parsed = schemas.RoutingIn(
        expected_revision=3, primary_model_id=model, decision_reference="  QĐ-1  "
    )
    assert parsed.decision_reference == "QĐ-1"
    for invalid in (
        {"expected_revision": 0, "primary_model_id": None, "fallback_model_id": model},
        {"expected_revision": "1", "primary_model_id": None},
        {"expected_revision": True, "primary_model_id": None},
        {"expected_revision": -1, "primary_model_id": None},
        {"primary_model_id": None},
        {"expected_revision": 0, "primary_model_id": None, "decision_reference": ""},
        {"expected_revision": 0, "primary_model_id": None, "decision_reference": "a\nb"},
        {"expected_revision": 0, "primary_model_id": None, "decision_reference": "x" * 129},
        {"expected_revision": 0, "primary_model_id": None, "prompt": "x"},
    ):
        with pytest.raises(ValidationError):
            schemas.RoutingIn.model_validate(invalid)


def test_routing_audit_payload_holds_ids_and_reference_only():
    fields = set(audit.RoutingChanged.model_fields)
    assert fields == {"revision", "before", "after", "decision_reference"}
    with pytest.raises(ValidationError):
        audit.RoutingChanged(
            revision=1,
            before=audit.RoutingSlots(primary_model_id=None, fallback_model_id=None),
            after=audit.RoutingSlots(primary_model_id=None, fallback_model_id=None),
            secret="x",
        )


def test_api_styles_agree_everywhere():
    from typing import get_args

    from aq_uai_api.mdl.adapters import ADAPTERS

    assert set(API_STYLES) == set(get_args(schemas.ApiStyle)) == set(ADAPTERS)
    migration = (MIGRATIONS / "0006_mdl_routing_and_styles.py").read_text()
    assert all(f"'{style}'" in migration for style in API_STYLES)


def test_provisioning_grants_only_existing_columns():
    """prepare runs before migrate: a column from a later migration must not abort it."""
    from aq_uai_api.db.provision import MDL_RUNTIME_PRIVILEGES, present_privileges

    for table, privileges in MDL_RUNTIME_PRIVILEGES.items():
        assert present_privileges(privileges, set(re.findall(r"[a-z_]+", privileges))) == (
            privileges
        ), table
    before_0006 = present_privileges(
        MDL_RUNTIME_PRIVILEGES["mdl_routing_revisions"], {"institution_id", "revision", "changed_by"}
    )
    assert before_0006 == "SELECT, INSERT (institution_id, revision, changed_by)"
    assert present_privileges("SELECT, UPDATE (gone)", set()) == "SELECT"


def test_mdl_import_closure_reaches_no_quota_or_credit_code():
    """FR-MDL-020 AC3 (static, M6): follow every aq_uai_api import reachable from MDL."""
    import ast
    import importlib.util

    seen, queue = set(), ["aq_uai_api.mdl", "aq_uai_api.api.v1.mdl"]
    queue += [f"aq_uai_api.mdl.{path.stem}" for path in (MIGRATIONS.parents[1] / "src/aq_uai_api/mdl").glob("*.py")]
    while queue:
        name = queue.pop()
        if name in seen or not name.startswith("aq_uai_api"):
            continue
        seen.add(name)
        try:
            spec = importlib.util.find_spec(name)
        except (ModuleNotFoundError, AttributeError):
            continue  # "module.ClassName": not a module
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
    assert "aq_uai_api.mdl.testing" in seen and "aq_uai_api.mdl.routing" in seen
    assert not [name for name in seen if re.search(r"quota|credit|qta|crt|ledger", name)]
