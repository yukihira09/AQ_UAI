# ADR-0001 — Independent AQ EduUAI foundations

**Status:** Adopted as a working engineering decision, not PO/Tech Lead business sign-off.
**Date:** 2026-11-19
**Scope:** Phase 0 and Phase 1 only.

## Why

AQTech's ongoing shared framework is not available for cloning at this time. The team must develop a self-contained system that can be integrated later through stable APIs.

## Decision

- Preserve the supplied browser prototype *exactly* under `apps/web/`.
- Create one Git monorepo containing `apps/web/`, `apps/api/`, `infra/`, `docs/`, and `scripts/`.
- Implement the backend as a modular monolith using Python 3.12 + FastAPI + SQLAlchemy + Alembic + Psycopg 3 with PostgreSQL 18.
- Use Docker Compose only for local development: PostgreSQL, migration job, FastAPI and nginx (same-origin static UI + `/api` proxy).
- Do not introduce real identity/auth, permissions, provider/model, quota, billing, or ledger operations in Phase 1.
- Do not change the demo prototype's localStorage data; it remains untrusted and synthetic.
- Later functionality must use approved FRD business rules and server-authoritative data, never import synthetic balances into a production environment.

## Trade-offs

Pros: readable project, repeatable setup, stable frontend, low deployment complexity, clear migration path.
Cons: separate frontend/backend technologies; migration/auth/design work remains; production deployment is not covered.

## Verification

- `scripts/verify_frontend_baseline.py` compares SHA256 hashes of 14 original frontend assets to the uploaded ZIP manifest.
- `scripts/verify_frontend_assets.py` checks all relative JS/CSS references and script load order.
- `pytest` verifies Phase-1 API contracts; a PostgreSQL integration test is opt-in or run in CI.
- `scripts/phase1_smoke.py` proves the real HTTP/API/DB read after local containers start.

## Deferred decisions

Identity/RBAC, provider adapters, token/credit conversion, budgets, actual DPA approval, scheduled monthly refresh, full AQ EduSmart shell feature coverage, and production infrastructure.
