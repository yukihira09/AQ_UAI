# WP1 identity schema

WP1 adds the tables that later packages will use to identify people, store sessions, evaluate scoped grants, and record changes. Alembic revision `0002_identity_foundation` extends `0001_phase1_metadata`. The upgrade creates new tables and seeds the role catalog. It preserves existing records and creates no operational identities or credentials.

## Tables and relationships

| Tables | Purpose |
|---|---|
| `institutions`, `units`, `users` | Each unit belongs to an institution. A person has one primary unit from that institution. The person's UUID is the long-lived reference used by later modules. |
| `user_credentials` | At most one local password hash record per person, with a password-change flag. A pending identity can exist before credentials are provisioned. |
| `account_groups`, `group_memberships` | One current row per user–group pair. The active flag supports removal and later reactivation of the same membership. Membership history will come from audit events. |
| `roles`, `permissions`, `role_permissions` | Seeded roles and permissions have stable codes and UUIDs. The join table links catalog entries by their unique codes. |
| `user_role_assignments`, `group_role_assignments` | Each grant pairs a role with a person or group and an institution-wide or exact-unit scope. |
| `auth_sessions` | Each session refers to a user and stores a unique 32-byte digest, issue time, expiry, and optional revocation time. |
| `auth_throttle_buckets` | One failure counter per login or address digest and window start. Authentication will compute the keys and apply limits in WP3. |
| `audit_events` | An event refers to an institution and actor when available. Its target type and UUID can describe different kinds of records. Its changes field is a JSON object. |

## Enforced by PostgreSQL

- Foreign keys associate units, users, groups, memberships, assignments, and audit actors with the correct institution. For example, a grant names both the institution and the target unit. PostgreSQL checks the pair together.
- Usernames must use the canonical ASCII format and are globally unique. Institutional codes cannot be blank or have leading or trailing whitespace and are unique by institution and staff/student code type. These constraints include disabled accounts.
- A user–group pair has one membership row. A global grant has no unit and a unit grant has a valid unit. Unique grant constraints use PostgreSQL's `NULLS NOT DISTINCT` so a second identical global grant with a null unit fails.
- A foundation administrator grant must be direct and global. Unit directory manager grants require a unit. User and group lifecycle values, session digest length, finite session timestamps, session chronology, and throttle bucket state also have database checks.
- Referenced identities cannot be deleted while history points to them. Audit actor IDs must identify a user in the event's institution. An unauthenticated event can have an absent actor.

## Rules for later services

WP2 supplies [restricted database roles, append-only runtime audit access, and transaction conventions](wp2-operations.md). WP3 will normalize login inputs, hash passwords, issue and revoke sessions, and apply throttle rules. WP4 and WP5 will enforce authorization-group eligibility, group-kind immutability, delegation, active-state and visibility checks, membership history, unit deactivation and transfers, and last-admin protection.

Group-kind eligibility and immutability require service checks. PostgreSQL validates the allowed values and the group's institution. A direct SQL write can still change a kind or attach a limited role to an ineligible group. Keeping those rules in the policy and directory services avoids duplicated category columns or database triggers. Group-derived authority must check eligibility at both assignment and evaluation time. The database already blocks group-derived foundation administrator grants.

The initial identity assumptions are provisional v1 decisions. Institution-wide user provisioning, real identity policies, multi-affiliation, and external directory sync require separate confirmation or scope. See the [approved plan](plan.md) for the complete role matrix and FRD boundaries.
