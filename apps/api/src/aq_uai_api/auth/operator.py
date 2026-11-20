"""Interactive operator commands for initial setup and local password recovery."""

import argparse
import getpass
import sys
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text

from aq_uai_api.auth.security import hash_password, normalize_username
from aq_uai_api.auth.service import (
    BOOTSTRAP_NAMESPACE,
    database_lock,
    lock_account,
    revoke_user_sessions,
)
from aq_uai_api.core.config import get_settings
from aq_uai_api.db.audit import AuditAction, RevocationCount, write_audit_event
from aq_uai_api.db.identity import Institution, Unit, User, UserCredential, UserRoleAssignment
from aq_uai_api.db.provision import DatabaseRoles
from aq_uai_api.db.session import get_engine, write_transaction


@dataclass(frozen=True)
class InitialAdmin:
    institution_code: str
    institution_name: str
    unit_code: str
    unit_name: str
    username: str
    display_name: str
    staff_code: str


class OperatorError(Exception):
    """A message safe to display to a local operator."""


def _required_text(value: str, max_length: int) -> str:
    field = value.strip()
    if not field or len(field) > max_length or "\x00" in field:
        raise OperatorError("A required field is empty or invalid.")
    return field


def _canonical(value: str) -> str:
    canonical = normalize_username(value)
    if canonical is None:
        raise OperatorError("Enter a valid ASCII username of up to 64 characters.")
    return canonical


def _hash_temporary(password: str) -> str:
    if password == get_settings().db_password:
        raise OperatorError("Choose a password different from the database login password.")
    try:
        return hash_password(password)
    except ValueError:
        raise OperatorError("Use a password of 12 to 128 characters.") from None


def bootstrap_admin(profile: InitialAdmin, password: str, request_id: UUID) -> UUID:
    canonical = _canonical(profile.username)
    password_hash = _hash_temporary(password)
    institution = Institution(
        code=_required_text(profile.institution_code, 64),
        name=_required_text(profile.institution_name, 255),
    )
    with write_transaction() as db:
        database_lock(db, BOOTSTRAP_NAMESPACE, 0)
        if db.scalar(select(Institution.id).limit(1)) is not None:
            raise OperatorError("Bootstrap requires an empty institution directory.")
        db.add(institution)
        db.flush()
        unit = Unit(
            institution_id=institution.id,
            code=_required_text(profile.unit_code, 64),
            name=_required_text(profile.unit_name, 255),
        )
        db.add(unit)
        db.flush()
        user = User(
            institution_id=institution.id,
            primary_unit_id=unit.id,
            username=canonical,
            display_name=_required_text(profile.display_name, 255),
            code_type="STAFF",
            institutional_code=_required_text(profile.staff_code, 64),
            state="ACTIVE",
        )
        db.add(user)
        db.flush()
        db.add(
            UserCredential(user_id=user.id, password_hash=password_hash, must_change_password=True)
        )
        db.add(
            UserRoleAssignment(
                institution_id=institution.id,
                user_id=user.id,
                role_code="FOUNDATION_ADMIN",
                scope="GLOBAL",
            )
        )
        write_audit_event(
            db,
            action=AuditAction.AUTH_ADMIN_BOOTSTRAPPED,
            request_id=request_id,
            institution_id=institution.id,
            target_id=user.id,
        )
        user_id = user.id
    return user_id


def reset_password(username: str, temporary_password: str, request_id: UUID) -> None:
    canonical = _canonical(username)
    password_hash = _hash_temporary(temporary_password)
    with write_transaction() as db:
        user_id = db.scalar(select(User.id).where(User.username == canonical))
        if user_id is None:
            raise OperatorError("Password recovery requires an active, provisioned account.")
        lock_account(db, user_id)
        user = db.get(User, user_id)
        credential = db.get(UserCredential, user_id)
        if (
            user is None
            or user.username != canonical
            or user.state != "ACTIVE"
            or credential is None
        ):
            raise OperatorError("Password recovery requires an active, provisioned account.")
        now = datetime.now(UTC)
        credential.password_hash = password_hash
        credential.must_change_password = True
        credential.updated_at = now
        count = revoke_user_sessions(db, user_id, now)
        write_audit_event(
            db,
            action=AuditAction.AUTH_OPERATOR_RESET,
            request_id=request_id,
            institution_id=user.institution_id,
            target_id=user_id,
            changes=RevocationCount(revoked_sessions=count),
        )


def _temporary_password() -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Temporary application password: ")
        confirmation = getpass.getpass("Confirm temporary password: ")
    if password != confirmation:
        raise OperatorError("The passwords do not match.")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("bootstrap", "reset-password"))
    args = parser.parse_args()
    request_id = uuid4()
    try:
        expected_login = DatabaseRoles().migration
        if get_settings().db_user != expected_login:
            raise OperatorError("Use the explicitly authorized schema-owner database connection.")
        if not sys.stdin.isatty():
            raise OperatorError("Use an interactive terminal for hidden password entry.")
        with get_engine().connect() as db:
            if db.scalar(text("SELECT current_user")) != expected_login:
                raise OperatorError(
                    "Use the explicitly authorized schema-owner database connection."
                )
        if args.operation == "bootstrap":
            profile = InitialAdmin(
                institution_code=input("Institution code: "),
                institution_name=input("Institution name: "),
                unit_code=input("Primary unit code: "),
                unit_name=input("Primary unit name: "),
                username=input("Administrator username: "),
                display_name=input("Administrator display name: "),
                staff_code=input("Administrator staff code: "),
            )
            bootstrap_admin(profile, _temporary_password(), request_id)
        else:
            username = input("Existing username: ")
            reset_password(username, _temporary_password(), request_id)
    except OperatorError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError, getpass.GetPassWarning):
        print(
            "Operator action cancelled. Use a terminal that supports hidden input.", file=sys.stderr
        )
        return 1
    except Exception:
        print(
            f"Operator action failed. Check database readiness. Request ID: {request_id}",
            file=sys.stderr,
        )
        return 1
    print(f"Operator action committed. Request ID: {request_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
