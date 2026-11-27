"""Shared monthly reset core and scheduled operator CLI: ``python -m aq_uai_api.qta.reset``.

Implements FR-QTA-032, RULE-QTA-01, RULE-QTA-04, PD-Q6, and reviewer decisions R7 & R8:
- Append-only ledger marker: records one ``qta_monthly_resets`` row and one ``qta_events``
  (``MONTHLY_REFRESH``) row per ``(institution_id, period_month)`` plus its typed audit event
  in the same transaction, serialized under ``QTA_RESET_NAMESPACE = 52003``.
- Never fabricates per-user balance rows, never backfills missed past months, and never alters
  configured group quotas, monthly budgets, directory memberships, or active suspensions.
- Zero rollover holds by construction while consumption is ``NOT_INTEGRATED`` because entitlements
  are derived live from current configuration.
"""

import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aq_uai_api.auth.service import database_lock
from aq_uai_api.authorization.writes import institution_key
from aq_uai_api.core.config import Settings
from aq_uai_api.db import audit
from aq_uai_api.db.identity import Institution
from aq_uai_api.db.session import write_transaction
from aq_uai_api.qta import periods, schemas
from aq_uai_api.qta.models import QtaEvent, QtaMonthlyReset

QTA_RESET_NAMESPACE = 52003


@dataclass(frozen=True)
class ResetRecordOutcome:
    recorded: bool
    reset: QtaMonthlyReset


@dataclass
class ScheduledResetResult:
    recorded: int = 0
    already: int = 0


def record_reset(
    db: Session,
    institution_id: UUID,
    month: date,
    trigger_mode: schemas.ResetTriggerMode,
    actor_id: UUID | None,
    request_id: UUID,
) -> ResetRecordOutcome:
    """Idempotently record the monthly reset marker for ``(institution_id, month)``."""
    database_lock(db, QTA_RESET_NAMESPACE, institution_key(institution_id), shared=False)
    existing = db.scalar(
        sa.select(QtaMonthlyReset).where(
            QtaMonthlyReset.institution_id == institution_id,
            QtaMonthlyReset.period_month == month,
        )
    )
    if existing is not None:
        return ResetRecordOutcome(recorded=False, reset=existing)

    reset_row = QtaMonthlyReset(
        institution_id=institution_id,
        period_month=month,
        trigger_mode=trigger_mode,
        triggered_by=actor_id,
    )
    db.add(reset_row)
    try:
        db.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise RuntimeError("Concurrent monthly reset conflict.") from None
        raise

    event_row = QtaEvent(
        institution_id=institution_id,
        period_month=month,
        event_type="MONTHLY_REFRESH",
        user_id=None,
        actor_id=actor_id,
        summary=f"Làm mới hạn mức đầu tháng {periods.format_month(month)}",
    )
    db.add(event_row)
    db.flush()

    audit_action = (
        audit.AuditAction.QTA_MONTHLY_RESET_SCHEDULED
        if trigger_mode == "SCHEDULED"
        else audit.AuditAction.QTA_MONTHLY_RESET_EXECUTED
    )
    audit.write_audit_event(
        db,
        action=audit_action,
        request_id=request_id,
        institution_id=institution_id,
        actor_id=actor_id,
        target_id=reset_row.id,
        changes=audit.MonthlyResetRecorded(
            period_month=month,
            trigger_mode=trigger_mode,
        ),
    )
    return ResetRecordOutcome(recorded=True, reset=reset_row)


def run_scheduled_resets(
    settings: Settings | None = None,
    transaction: Callable[[], AbstractContextManager[Session]] | None = None,
) -> ScheduledResetResult:
    """Record the current institution month for every institution (one transaction per tenant)."""
    cfg = Settings() if settings is None else settings
    tx = write_transaction if transaction is None else transaction
    month = periods.current_month(cfg)
    request_id = uuid4()
    result = ScheduledResetResult()

    with tx() as db:
        institution_ids = list(
            db.scalars(sa.select(Institution.id).order_by(Institution.id)).all()
        )

    for institution_id in institution_ids:
        with tx() as db:
            outcome = record_reset(db, institution_id, month, "SCHEDULED", None, request_id)
        if outcome.recorded:
            result.recorded += 1
        else:
            result.already += 1
    return result


def main() -> int:
    try:
        result = run_scheduled_resets()
    except Exception:
        print(
            "Monthly quota reset failed. Check the database connectivity and settings.",
            file=sys.stderr,
        )
        return 1
    print(f"recorded={result.recorded} already={result.already}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
