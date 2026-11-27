# AQ EduUAI — Project context

**Audience:** a developer or reviewer (including an AI researcher new to backend work) opening this repository for the first time.
**Prepared:** 2026-11-25 (M0); **updated 2026-11-27 after Phase 4 Q5**. Repository state described: branch `main`; Phase 3 MDL (M1–M7) and Phase 4 QTA (Q0, Q1, Q1-R, Q2, Q3, Q4, Q5) are implemented and technically verified.
**Rule for this file:** it links to the detailed documents instead of copying them. If a linked document and this file disagree, the linked document wins; fix this file.

## 1. What / why

AQ EduUAI is a standalone, independently deployable **university AI-governance** product with three modules:

| Module | Meaning | FRD (canonical copy) | Server status |
| --- | --- | --- | --- |
| MDL | AI providers and models: registry, real connection test, primary/fallback routing, data-protection agreement (DPA) evidence, risk classification | [FRD MDL](frd/AQ-FRD-UAI-MDL-001.md) | **Implemented (M1–M7) and technically verified; not formally accepted; live-provider run pending** (see [Phase 3 plan](phase3/MDL_IMPLEMENTATION_PLAN.md), [handoff](phase3/mdl-handoff.md)) |
| QTA | Quotas (monthly institutional cap, group × model quotas, additive lookup, kill-switch, monthly reset) | [FRD QTA](frd/AQ-FRD-UAI-QTA-001.md) | **In progress (Phase 4 Q0–Q5 implemented & technically verified, awaiting Q5 review: RBAC `0007`, 8-table schema `0008`, Q2–Q4 API/CLI, Q5 `#qta` Admin UI + Playwright tests & C5–C7; Q6 cross-module proof & handoff next; formal acceptance 0/33)** (see [Phase 4 plan](phase4/QTA_IMPLEMENTATION_PLAN.md), [Q5 report](phase4/reports/QTA_Q5_REPORT.md)) |
| CRT | Credits (append-only ledger) | [FRD CRT](frd/AQ-FRD-UAI-CRT-001.md) | Not started (Phase 5) |

The company's shared framework is unavailable, so this repository supplies its own identity, permission, audit and directory foundation. Modules must stay adapter-friendly so a later framework can replace pieces.

Glossary used across the docs:

- **FRD** — Functional Requirements Document (requirements with IDs such as `FR-MDL-020` and acceptance criteria, "AC").
- **RBAC** — role-based access control: users get roles, roles carry permissions, each grant has a scope.
- **Scope** — where a permission applies (`GLOBAL`/institution-wide or one organizational unit).
- **Audit event** — an append-only row recording who did what and when, written in the same database transaction as the change.
- **CSRF** — a browser attack where another site makes your browser send an authenticated write; defended with a token plus an exact `Origin` check.
- **SSRF** — Server-Side Request Forgery: tricking the server into calling internal addresses. Relevant to the MDL connection test.

## 2. Architecture in one page

A synchronous **FastAPI modular monolith** on SQLAlchemy 2 / PostgreSQL 18 / Alembic, behind nginx, served on two browser origins:

- `http://localhost:8000` — the **frozen prototype** under `apps/web/` (browser-local synthetic data, never trusted by the server).
- `http://admin.localhost:8000` — the **real, authenticated administration UI** (`apps/admin/`) plus the versioned API `/api/v1`.

Request flow for a protected write:

1. Browser → nginx (admin CSP, request-size cap, proxy timeout) → FastAPI route in `apps/api/src/aq_uai_api/api/v1/`.
2. A dependency validates the cookie session, exact `Origin` and CSRF token (`authorization/dependencies.py`).
3. The service opens one write transaction, re-authenticates, takes the institution and account locks, and recomputes the actor's grants (`authorization/writes.py`).
4. The mutation and its audit event are written in the **same transaction**, then committed (`db/audit.py`).
5. Errors return `{code, message, request_id}` via `DomainError` (`api/errors.py`).

Component roles: HTML/CSS/JS present only (never decide access); FastAPI owns HTTP and business rules; Pydantic defines input/output contracts; SQLAlchemy/PostgreSQL hold durable state, constraints and column-level privileges; Alembic is the only schema history; Docker Compose is the local stack; pytest and Playwright verify.

Repository map:

| Path | Content |
| --- | --- |
| `apps/web/` | Preserved original prototype (14 hashed assets; do not edit) |
| `apps/admin/` | Real admin UI (`index.html`, `assets/{admin.css,api.mjs,app.mjs,pages.mjs,ui.mjs,mdl.mjs,qta.mjs}`; `mdl.mjs` is the MDL section M6; `qta.mjs` is the `#qta` QTA section Q5) |
| `apps/api/src/aq_uai_api/` | `api/`, `auth/`, `authorization/`, `core/`, `db/`, `directory/`, `mdl/` (Phase 3), `qta/` (Phase 4 Q1–Q4: models, periods, entitlements, access, reset, schemas, queries, service), `main.py` |
| `apps/api/migrations/versions/` | `0001`–`0002` (Phase 1–2), `0003`–`0006` (Phase 3 MDL), `0007_qta_access_catalog`, `0008_qta_schema` (current head, Phase 4 Q1) |
| `apps/api/tests/`, `tests/browser/` | pytest suites (`tests/live/` holds the opt-in, normally skipped live-provider check); Playwright/Chromium suites |
| `infra/` | Compose stack, nginx config, optional synthetic AI provider (`demo-provider/`, `compose.demo-provider.yaml`) |
| `scripts/` | Verification and dev helpers (`verify_phase2.sh`, `verify_frontend_assets.py`, …) |
| `docs/` | This documentation; `docs/frd/` holds canonical FRDs |

## 3. Completed phases and evidence

Evidence categories are kept **separate on purpose**. Never merge them into "tested".

| Phase / package | Delivered | Source of the claim |
| --- | --- | --- |
| Phase 0 | Preserved prototype, manifests, asset verification | [ADR-0001](decisions/ADR-0001-phase0-phase1.md), [verification report](setup/VERIFICATION_REPORT.md) |
| Phase 1 | FastAPI + PostgreSQL + Alembic baseline, diagnostics, Compose | [Phase 0–1 setup](setup/PHASE_0_1.md) |
| Phase 2 WP1–WP5 | Identity schema, transactions/privileges, authentication, RBAC policy, protected directory | [ADR-0002](architecture/ADR-0002-phase2-shared-foundation.md), `docs/phase2/wp1…wp5-report.md`; [AGENTS.md](../AGENTS.md) says "accepted for continued source development" |
| Phase 2 WP6–WP7 | Browser admin UI (33 operations), upgrade/restore/restart rehearsals | [WP6 report](phase2/wp6-report.md), [WP7 report](phase2/wp7-report.md), [handoff](phase2/phase2-handoff.md) |
| Phase 3 MDL M1–M7 | Access, schema and encryption, APIs, SSRF-resistant connection test, routing, admin UI; M7: configuration history with diff, picker fix, MDL backup/restore and Phase 2 → MDL upgrade rehearsals, handoff | [Implementation plan](phase3/MDL_IMPLEMENTATION_PLAN.md) completion sections, [traceability (M7 status)](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26), [handoff](phase3/mdl-handoff.md); **not formally accepted** |

| Evidence category | Status (do not upgrade without a new report) |
| --- | --- |
| Automated tests, disposable infrastructure | WP7: 119 pytest and 13 browser/ops tests. **After M7 (2026-11-26):** see the [M7 verification](phase3/MDL_IMPLEMENTATION_PLAN.md#m7-verification) for exact counts (full `verify_phase2.sh` gate on private PostgreSQL 18, nginx and Chromium). |
| Docker Compose live run | WP7: pending. **Phase 3:** disposable Compose runs with synthetic configuration and a fake provider (M2, M5, M6, M7), including in M7 a clean install and a Phase 2 (`2c909e3`) → current upgrade on the same volume; recorded in the plan; not a production deployment. The developer's own `aq-uai-dev` stack was upgraded by the developer to `0006_mdl_routing_and_styles` (MDL, with the demo provider) on 2026-11-26 and was observed unchanged at `0006` on 2026-11-27: the QTA migrations `0007`/`0008` have **not** been applied to it ([MDL update steps](phase3/mdl-handoff.md#3-updating-your-existing-aq-uai-dev-stack-to-mdl)). |
| Hosted GitHub Actions CI | **Unverified** (outside the WP7 run). |
| Developer local deployment and manual testing | **Developer-reported**, "generally successful"; no repository evidence yet. See the note above. |
| AI provider | **Synthetic demo provider** by Project Owner decision D15: automated and Compose evidence recorded in the [runbook](phase3/MDL_LIVE_PROVIDER_VERIFICATION.md). No real vendor has been called; vendor compatibility is not claimed. |
| Tech Lead / Product Owner / company acceptance | **None recorded.** `docs/acceptance-matrix.md` still shows 0 of 33 FRs accepted, and that remains correct. Phase 3 decisions were taken under the owner's delegation, which is not acceptance. |

## 4. Shared foundations that modules must reuse

No module may create a second authentication, authorization, directory, audit, error or migration mechanism.

- **Auth/session:** `require_authenticated_write`, `read_authority` (`authorization/dependencies.py`).
- **Transaction-time authority:** `resolve_write_authority` → `ActorAuthority` (`authorization/writes.py`); permission checks in `authorization/policy.py`.
- **Audit:** `write_audit_event` with typed payloads (`db/audit.py`); payloads hold names, IDs and enum values, never secrets.
- **Errors:** `DomainError(ErrorCode)` (`api/errors.py`).
- **Schema conventions:** UUID keys, `institution_id` with composite foreign keys, named constraints, `timestamptz`, column-level runtime `GRANT`s and no `DELETE` on history (`db/identity.py`, `db/provision.py`).
- **One migration history** under `apps/api/migrations`; startup readiness pins the revision (`db/schema.py`).

## 5. Development conventions

Binding rules are in [AGENTS.md](../AGENTS.md); in short:

- Explain scope first, make the smallest reviewable change, write tests before business rules.
- Run `python scripts/verify_frontend_assets.py`, `node --check` on changed JS, and the relevant API tests. `verify_original_archive.py` is a Phase-0 historical check and is expected to fail after legitimate frontend edits.
- Keep the HTML classic `<script>` order; do not modify `apps/web/`; do not import prototype `localStorage` data.
- Never read, print or commit `.env`. No commits, pushes, remote changes or deployments without explicit instruction.
- Documentation answers what / why / how / how to verify.
- Statements are labelled as **specified** (FRD), **recommended** (technical advice), **provisional** (assumption to confirm) or **needs approval** (Product Owner or Tech Lead). See [MDL open decisions](phase3/MDL_OPEN_DECISIONS.md).

## 6. Security boundaries

Secrets stay out of source, logs, HTTP responses and Git. Host-published ports are localhost-only and the stack is for private development; production deployment needs its own review. Token/credit conversion is **undefined** and must not be invented. Do not invent PO approvals, legal documents, usage prices or model credentials.

## 7. Implemented versus prototype-only

Real, server-enforced: sign-in, sessions, RBAC grants, directory (units, users, groups, memberships), audit browsing, the admin UI, and MDL (providers, encrypted credentials, agreements, models, risk, real connection test, routing with fail-closed use, the MDL admin section). Prototype-only (browser simulation, **not** FRD acceptance): the three module screens on `localhost`. For MDL this includes a Temperature field and sample vendors/legal citations that the real implementation must never reproduce (see [architecture](phase3/MDL_ARCHITECTURE_AND_DECISIONS.md)).

## 8. Roadmap and boundaries for MDL / QTA / CRT

- **MDL (Phase 3):** packages M0–M7 in [`docs/phase3/`](phase3/MDL_IMPLEMENTATION_PLAN.md). **M1–M7 are implemented and technically verified; formal acceptance (Tech Lead / Product Owner) is not recorded.** A synthetic demo provider replaces a real vendor for this project (Project Owner decision D15, `bash scripts/dev-up.sh --demo-provider`). External inputs still open: official risk criteria (OQ-09-01), statutory retention periods, legal confirmation of the D5 reading, QTA/CRT for end-to-end quota proof. Decisions: [register](phase3/MDL_OPEN_DECISIONS.md); architecture: [ADR-0003](architecture/ADR-0003-mdl.md) (*Proposed*, with owner-delegated decisions recorded).
- **QTA (Phase 4):** stages Q0–Q6 in [`docs/phase4/`](phase4/QTA_IMPLEMENTATION_PLAN.md). **Q0–Q5 (RBAC `0007`, 8-table schema `0008`, PO decisions `PD-Q1..PD-Q6`, [ADR-0004](architecture/ADR-0004-qta.md), Q2–Q4 API/CLI, and Q5 `#qta` Admin UI + Playwright tests + C5–C7; [Q5 report](phase4/reports/QTA_Q5_REPORT.md)) are implemented and technically verified (API 581 passed, 1 skipped; browser 20 passed; awaiting Q5 review; formal acceptance 0/33).** Q6 (cross-module MDL isolation proof, backup/restore rehearsal & handoff) awaits separate authorization.
- **CRT (Phase 5):** append-only ledger; token/credit conversion undefined. Not started.
- Boundary rules between modules: MDL does not import quota or credit tables; a future QTA/CRT registers its own "where used" checks for model deactivation; no module bypasses the shared foundations in section 4.

## 9. Working with this repository

1. Read [README.md](../README.md), [AGENTS.md](../AGENTS.md), [Phase 0–1 setup](setup/PHASE_0_1.md), [BLUEPRINT_v1](architecture/BLUEPRINT_v1.md) and the relevant FRD.
2. For MDL, start at [MDL_IMPLEMENTATION_PLAN](phase3/MDL_IMPLEMENTATION_PLAN.md).
3. Canonical FRDs live in `docs/frd/`. Untracked copies at the repository root are duplicates; see the [M0 housekeeping note](phase3/MDL_IMPLEMENTATION_PLAN.md#housekeeping-findings).
