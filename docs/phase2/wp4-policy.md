# WP4 authorization and scope guide

WP3 authenticates the requester. WP4 determines which actions that person can perform and which database rows each permission covers. Future directory and module services apply business rules after both checks. The existing PostgreSQL role catalog supplies the permissions, and WP4 applies the approved grant-shape and resource-scope rules.

## Reusable interfaces

| Interface | Use |
|---|---|
| `read_authority` | FastAPI dependency. Requires a current unrestricted WP3 session, then resolves the actor's grants for this request. |
| `resolve_effective_grants(db, principal)` | Policy entry point without HTTP dependencies. Supply a freshly authenticated WP3 principal. It reads the actor's current institution, state, credential restriction, and grants from PostgreSQL in one statement. |
| `ActorAuthority` | Holds typed effective grants with their role, originating assignment, permission, institution, scope, unit, and optional group. Use `has_permission`, `scope_for`, `require_permission`, `require_institution`, or `require_unit`. |
| `PermissionScope.predicate(institution_column, unit_column=None)` | Returns a SQLAlchemy filter. Supply a unit column for unit-scoped resources. Omit it for institution-wide resources, which require a GLOBAL grant. |
| `validate_profile_fields`, `require_group_management`, `validate_role_assignment` | Shared checks for profile payloads, group management, and proposed grants. These are policy checks. WP5 owns the mutations. |
| `require_authenticated_write`, `resolve_write_authority` | Precheck a browser write and resolve the actor again in the actual service transaction. These use WP3's Origin and session-bound CSRF functions. |

A direct grant applies to its user and institution. An inherited grant requires an active membership, an active same-institution `AUTHORIZATION` group, and an eligible role. Only `DIRECTORY_READER` and `UNIT_DIRECTORY_MANAGER` may be inherited. `FOUNDATION_ADMIN` requires a direct GLOBAL grant. `DIRECTORY_READER` allows GLOBAL or UNIT. `UNIT_DIRECTORY_MANAGER` requires UNIT. Unknown roles and permission codes fail closed. Central directory administration, delegation, and audit reading require direct GLOBAL permissions even if the catalog drifts.

GLOBAL covers the actor's institution. UNIT covers exactly its named active unit. The actor's primary unit provides no permission. Multiple grants may contribute units for the **same** permission. A GLOBAL read grant and a Unit A profile grant permit reading Unit B and editing Unit A. Editing Unit B needs a separate applicable profile permission. A missing unit fails a unit check even with a GLOBAL grant. Check unitless resources through institution-wide authorization.

An institution-wide read can include records from inactive units. Account state affects authentication. It does not remove pending or disabled people from authorized directory queries. WP5 must apply any further target-eligibility and field-value rules for mutations.

## Examples for future services

These snippets use synthetic IDs or values already resolved by the service. None adds a public endpoint.

**Institution-wide administration**

```python
from aq_uai_api.authorization.policy import PermissionCode as P

authority.require_institution(P.DIRECTORY_MANAGE, target_institution_id)
```

Use `DIRECTORY_MANAGE` for creating users and units, profile fields beyond display name, account state, transfers, unit changes, and institution-wide ordinary groups. Use `require_group_management` with a persisted group kind for existing groups. Authorization groups, their membership and state, and role assignment or removal require `AUTHORIZATION_MANAGE` across the institution. Group kind is a WP5 immutable field. Audit reads require institution-wide `AUDIT_READ`.

**Exact-unit profile modification**

```python
from aq_uai_api.authorization.policy import validate_profile_fields

validate_profile_fields({"display_name"})
authority.require_unit(P.PROFILE_UPDATE, target.institution_id, target.primary_unit_id)
```

Use the institution and unit from the same persisted target row. For a unit itself, first query with the visibility predicate using `Unit.institution_id` and `Unit.id`. The profile payload accepts only the display-name field. Roles, units, usernames, institutional codes, and account state require their central operations. WP5 owns payload schemas, value validation, and the typed audit event.

**Scoped search, pagination, and count**

```python
from sqlalchemy import func, select
from aq_uai_api.db.identity import User

scope = authority.require_permission(P.DIRECTORY_READ)
visibility = scope.predicate(User.institution_id, User.primary_unit_id)
search = User.display_name.contains("Sinh", autoescape=True)
filters = (visibility, search)

page = db.scalars(select(User).where(*filters).order_by(User.id).offset(20).limit(20))
total = db.scalar(select(func.count()).select_from(User).where(*filters))
```

Use the same filters for detail queries, lists, searches, and totals. A missing permission produces `403` through `require_permission`. An empty scope predicate produces zero rows. For object writes, check the operation permission, look up the target through its visibility predicate, then check the operation's scope against the row. An invisible or nonexistent target produces the same `404`. A visible target outside the operation scope produces `403`.

**Revalidate a mutation in its transaction**

```python
from sqlalchemy import select
from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization.writes import resolve_write_authority
from aq_uai_api.db.session import write_transaction

# The route obtains proof with Depends(require_authenticated_write).
with write_transaction() as db:
    authority = resolve_write_authority(db, proof, settings)
    authority.require_permission(P.PROFILE_UPDATE)
    visibility = authority.scope_for(P.DIRECTORY_READ).predicate(
        User.institution_id, User.primary_unit_id
    )
    target = db.scalar(select(User).where(User.id == target_user_id, visibility))
    if target is None:
        raise DomainError(ErrorCode.NOT_FOUND)
    authority.require_unit(P.PROFILE_UPDATE, target.institution_id, target.primary_unit_id)
    validate_profile_fields({"display_name"})
    # WP5 applies the validated change and writes its typed audit event here.
```

Call `validate_role_assignment` after transaction-time authorization for an authority-changing operation. It requires global `AUTHORIZATION_MANAGE`, validates the role and scope shape, and checks tenant-matched user, eligible active authorization group, and active unit as applicable. Group creation and membership authority still use `require_group_management`. Both checks must precede writes. Authority removal and last-active-admin protection belong to WP5 and must run under the authority-change lock.

## Revocation and lock order

An HTTP write precheck verifies the exact Origin, active unrestricted session, and one session-specific CSRF header. The existing WP3 password-change and logout flows still accept restricted sessions. Keep the proof local to the request. The protected mutation opens an explicit `write_transaction()` and calls `resolve_write_authority` before authorizing or updating any data. Call the guard once per outer transaction with the complete lock set and final lock mode. The guard rejects savepoints and repeat calls. It validates the proof, takes an institution lock, locks the accounts, then checks the proof again and reads committed authority. The API returns success after commit.

Future WP5 services must follow this order:

1. Choose the lock mode from the server operation. Scope-stable writes take a shared institution lock. Writes that change grants, group eligibility or membership, unit activity, account state, or the organizational scope of a resource must take the exclusive institution lock at the start using `changes_authority=True`. Scope changes include transfers. Start with the required mode so the transaction never needs to upgrade it.
2. Supply affected existing account UUIDs as `related_account_ids` for multi-account operations that need WP3 account coordination. Pass the operation's permission as `related_account_permission`. The service applies its provisional scope in SQL before waiting on account locks, then acquires the allowed locks in sorted lock-key order. Resolve and authorize the actual target rows separately. A transaction holds its institution lock before taking any account lock.
3. Reauthenticate and resolve authority while holding the locks. For grant and membership changes, check the appropriate central permission. For transfers, check the source and destination rules. For disablement, change state and revoke sessions in the same transaction using WP3's `revoke_user_sessions`. Apply the last-admin check under the exclusive institution lock before the proposed change.
4. Write typed audit and commit in the same transaction. Retain the existing WP2 transaction and error handling. WP5 must choose an unambiguous membership event target containing both the group and user IDs.

The exclusive lock serializes authority changes within an institution. Ordinary protected writes can share the institution lock across different accounts. Existing WP3 login, reset, password-change, and logout operations use account locks. WP3 login takes throttle locks before the account lock. WP5 services must never try to take a throttle or institution lock after obtaining an account lock.

Requests starting after a committed revocation read the new state. A read already in progress can finish with the scope it obtained earlier. A protected mutation that acquired its locks first can commit before a cooperating revoker. When revocation holds the lock first, the waiting mutation checks the committed state and denies the old permission or session. This uses PostgreSQL READ COMMITTED and cooperating callers. Run schema-owner catalog maintenance with the application stopped. SQL issued outside the locking protocol is outside the in-flight guarantee.

## FRD boundaries and outstanding work

- **FR-MDL-001** can use a future institution-wide configuration permission that requires edit-equivalent access. Any leadership read-only surface needs the existing Product Owner decision. Real quota-free tests and configuration revisions remain MDL work. [MDL](../frd/AQ-FRD-UAI-MDL-001.md)
- **FR-QTA-001, FR-QTA-020, FR-QTA-022, and FR-QTA-030** can use separate read and manage permissions and scoped directory lookups. SYSTEM and AI_SPECIALIST group membership remains available to future entitlement calculation without contributing authorization grants. Additive quotas remain QTA work. [QTA](../frd/AQ-FRD-UAI-QTA-001.md)
- **FR-CRT-001, FR-CRT-010, FR-CRT-013, and FR-CRT-030** can use independent view, grant, and recovery permissions and exact-unit recipient checks. The ledger and its transaction-time attribution are CRT responsibilities. WP4 introduces no accounting policy or conversion. [CRT](../frd/AQ-FRD-UAI-CRT-001.md)

WP5 must integrate these checks with directory writes and reads, role assignment and removal, audits, last-admin protection, and membership history. Live Compose verification, deployment, and manual browser testing remain deferred. GitHub authentication remains a separate developer task.
