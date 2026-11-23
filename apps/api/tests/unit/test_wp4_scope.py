"""Policy-only cases independent of PostgreSQL fixtures."""

from uuid import uuid4

import pytest

from aq_uai_api.api.errors import DomainError, ErrorCode


def test_scope_fails_closed_for_missing_unit_and_cross_institution():
    from aq_uai_api.authorization.policy import PermissionScope

    institution, other, unit = uuid4(), uuid4(), uuid4()
    central = PermissionScope(institution, institution_wide=True)
    scoped = PermissionScope(institution, unit_ids=frozenset({unit}))

    assert central.allows_institution(institution)
    assert central.allows_unit(institution, unit)
    assert not central.allows_unit(institution, None)
    assert not central.allows_unit(other, unit)
    assert not scoped.allows_institution(institution)
    assert scoped.allows_unit(institution, unit)
    assert not scoped.allows_unit(institution, uuid4())


def test_profile_field_policy_rejects_every_authority_changing_field():
    from aq_uai_api.authorization.policy import validate_profile_fields

    validate_profile_fields({"display_name"})
    for fields in (
        set(),
        {"username"},
        {"display_name", "state"},
        {"roles"},
        {"primary_unit_id"},
        {"institutional_code"},
        {"institution_id"},
    ):
        with pytest.raises(DomainError) as exc:
            validate_profile_fields(fields)
        assert exc.value.code is ErrorCode.VALIDATION_FAILED
