# ADR-0002 · Phase 2 shared foundation

**Status:** Architectural direction approved. WP1 through WP5 accepted for continued development. WP6 and WP7 implemented. Live operational acceptance remains pending. [Implementation specification](../phase2/plan.md)

## Context

MDL, QTA, and CRT need a shared directory, authenticated actors, scoped permissions, and auditable changes. AQ EduUAI must work independently of the unavailable company framework. Phase 1 already supplies a synchronous FastAPI application, SQLAlchemy, PostgreSQL, Alembic, and a preserved browser demo.

## Decision

- Extend the modular monolith and its one Alembic history. Preserve Phase 1 diagnostics and the original assets.
- Start with one institution, flat units, and one primary unit per person. Use stable UUIDs, canonical usernames, separate institutional codes, and retained deactivated identities. Identity normalization and code ownership are provisional v1 policies pending institutional confirmation.
- Separate system groups, authorization groups, and AI-specialist groups. Reserve permission-bearing group changes for central authorization administration. Each role grant carries its own institution or exact-unit scope.
- Separate runtime privileges from schema ownership. Commit successful privileged changes and their audit events together. Use PostgreSQL-backed opaque sessions, expiration and revocation, exact origin and CSRF validation, and login throttling.
- Serve admin and its API from one browser origin and the preserved demo from a separate hostname. Deliver schema first, then audit and errors, authentication, RBAC, protected directory, browser integration, and verification.

## Consequences

Database constraints reject invalid references and scope shapes regardless of the calling code. Later services still enforce active state, delegation, and visibility. Separate database roles and browser hostnames add provisioning work while reducing the authority of the runtime connection and isolating the demo's scripts. Defer SSO, multi-affiliation, hierarchy, and module-specific accounting. Phase 2 supplies prerequisites for the three FRDs, whose acceptance remains with their respective module implementations.

WP2 uses the database's original bootstrap owner for provisioning, a non-superuser schema owner for migration, and a restricted runtime login. Compose passes each service an explicit environment. See the [privilege matrix and rollout](../phase2/wp2-operations.md).

WP4 resolves current grants from the PostgreSQL catalog and binds each permission to its originating scope. A scope-sensitive write reauthenticates and checks authority under an institution lock and WP3 account locks. An exclusive institution lock coordinates membership, grant, and other authority changes with protected writes. See the [WP4 policy and locking contract](../phase2/wp4-policy.md).

WP5 applies that policy to the protected directory. It tests the proposed administrator state inside the same transaction as a disablement or grant removal. It records the group UUID and user UUID for membership changes and uses column-level runtime write privileges with no new schema revision. [WP5 API and rollout contract](../phase2/wp5-api.md)

WP6 serves standalone admin files from a read-only nginx root. The browser reloads session identity and permission-specific scopes, holds CSRF proof in memory, and uses relative API URLs. WP7 exercises separate hosts, restricted writes, legacy upgrades, and recovery using actual PostgreSQL, FastAPI, nginx, and Chromium. [Browser contract and coverage](../phase2/wp6-report.md) · [Operational handoff](../phase2/phase2-handoff.md)
