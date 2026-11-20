# ADR-0002 · Phase 2 shared foundation

**Status:** Architectural direction approved. [Implementation specification](../phase2/plan.md) approved through WP2. Later packages require gate approval.

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
