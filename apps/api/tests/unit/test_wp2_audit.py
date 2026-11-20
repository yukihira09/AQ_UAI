"""Verify typed audit payloads before any database write is queued."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from aq_uai_api.db.audit import ActiveChange, AuditAction, write_audit_event


@pytest.mark.parametrize(
    "changes",
    [
        {"before": False, "after": True, "credentials": {"password": "synthetic-secret"}},
        ActiveChange.model_construct(before={"token": "synthetic-secret"}, after=True),
    ],
)
def test_unsupported_audit_payload_cannot_be_queued(changes):
    with Session() as session, session.begin():
        with pytest.raises(ValueError) as error:
            write_audit_event(
                session,
                action=AuditAction.UNIT_STATE_CHANGED,
                request_id=uuid4(),
                institution_id=uuid4(),
                actor_id=uuid4(),
                target_id=uuid4(),
                changes=changes,
            )
        assert "synthetic-secret" not in str(error.value)
        assert not session.new


def test_extra_audit_payload_fields_are_rejected():
    with pytest.raises(ValidationError):
        ActiveChange.model_validate({"before": False, "after": True, "session_token": "synthetic"})


def test_implicit_session_transaction_is_refused():
    with Session() as session:
        with pytest.raises(RuntimeError, match="explicit"):
            write_audit_event(session, action=AuditAction.AUTH_LOGIN_REJECTED, request_id=uuid4())
