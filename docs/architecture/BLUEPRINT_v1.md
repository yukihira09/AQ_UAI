# AQ EduUAI — Architecture Decision & Implementation Blueprint

**Version:** proposed baseline v1.0, 19 November 2026  
**Inputs:** `aq_uai.zip` (current full frontend), `AQ-FRD-UAI-MDL-001`, `AQ-FRD-UAI-QTA-001`, `AQ-FRD-UAI-CRT-001` (17 November 2026), handover document, previous source audit.  
**Constraint:** The Tech Lead's actively developed product framework is unavailable. The project must be independently runnable and cannot assume access to that repository or its database. Preserve later integration by stable API/domain boundaries.  
**Scope of this blueprint:** Plan and architecture decisions only. **No existing project source was modified.**

## Executive decision

Build an **independently deployable, single-repository modular monolith** using:

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (synchronous ORM to start), Psycopg 3, Alembic.
- **Database:** PostgreSQL **18** (latest supported 18.x minor at installation time); one logical database, explicit FK/uniqueness/check constraints, ACID transactions, migration-controlled schema. Avoid PostgreSQL 19 RC before general availability and validation.
- **Frontend:** keep existing Vietnamese HTML/CSS/vanilla JS; move unchanged files under `apps/web/`, then incrementally introduce API client, per-module controllers and ES module imports. Vite (vanilla JS) is a *planned tooling upgrade*, not a prerequisite for the first backend endpoint. Do not rewrite into React/Vue merely for stack uniformity.
- **Development operations:** Git, `infra/compose.yaml`, PostgreSQL container, Python venv or `uv`, `.env.example`, smoke health endpoint, Ruff, pytest, Postgres-backed integration tests, JS lint/unit checks, API OpenAPI, CI. One-origin deployment through a reverse proxy; keep DB private.
- **Integration readiness:** all cross-product access through stable `/api/v1` contracts and an `identity`/directory integration boundary; do not lock the backend to any presumed company framework technology.
- **Not now:** microservices, Kubernetes, Redis/Celery, Kafka, vector DB, LLM/RAG chat, payment processing, persistent localStorage as source of truth, a complete enterprise framework rewrite.

## A. Review of existing frontend (verified)

Current ZIP:

```text
aq_uai/
  index.html
  shared/{base.css,core.js,dialogs.js,actions.js}
  module1/{module1.js,module1.css}
  module2/{module2.js,module2.css}
  module3/{module3.js,module3.css}
  docs/{IMPLEMENTATION_STATUS.md,MANUAL_TESTS.md,SCREENSHOT_MAPPING.md,screenshots/...}
  preview-module2-*.png
```

Six browser JavaScript files load sequentially as classic scripts. `shared/core.js` owns global `db` and `ui`, demo seed objects, `getQuota()` and `totals()`. `shared/actions.js` mutates shared objects and writes `aq_uai-demo-v1` to browser localStorage. Module renderers and CSS preserve the prototype. The ZIP includes no API, backend, DB, migrations, authenticated users, provider secrets or real AI integrations.

Previously verified issues to track during migration: reset leaves `tokenUsed` from the prior epoch, inactive groups still add entitlement (depends on semantics), DPA status can be stale after withdrawal, Module 2 has four hardcoded displayed model IDs, primary/backup route can survive invalidated provider DPA, and credit balances are unrelated to tokens. Avoid importing synthetic provider contracts, model status or balances into a live production database.

### Recommended transition (no big-bang rewrite)

**Checkpoint R0** — snapshot existing `aq_uai.zip` with SHA256 + Git commit/tag `frontend-baseline-2026-11-19`. Preserve original assets, including screenshots.

**Checkpoint R1** — make `aq_uai/` the repository root. Move the existing `index.html`, `shared/`, and `module1/2/3/` intact into `apps/web/`. Verify relative URLs, sidebar, forms, navigation, and existing localStorage demo behavior. Move existing project docs into `docs/prototype/` and keep a `docs/FRD/` folder for the FRDs. Do not run a mass rename/refactor simultaneously.

**Checkpoint R2** — add backend and infrastructure alongside `apps/web/`; stand up database + health endpoint, leaving demo UI untouched. Document how to launch each independently.

**Checkpoint R3** — introduce `apps/web/shared/api-client.js` and `apps/web/shared/data-source.js` or equivalent. API access is through an explicit interface. Keep demo-only implementations behind a `DEMO_MODE` flag until each real endpoint is verified. Never silently fall back to demo data after a production API error.

**Checkpoint R4** — migrate one module at a time (MDL first) by moving submission/orchestration logic out of `shared/actions.js`, while retaining its existing view markup/CSS. Follow with ES module/Vite migration and only then optional JSDoc/TypeScript gradual typing. Each migration should have a UI smoke test.

**Target architecture (not a required one-shot move):**

```text
aq_uai/
├── README.md
├── .gitignore
├── .env.example
├── apps/
│   ├── web/
│   │   ├── index.html
│   │   ├── package.json                 # added when introducing Vite/tooling
│   │   ├── module1/                    # retain initially
│   │   ├── module2/
│   │   ├── module3/
│   │   ├── shared/
│   │   │   ├── base.css
│   │   │   ├── core.js                  # demo state, gradually retired
│   │   │   ├── dialogs.js
│   │   │   ├── actions.js               # event coordinator, progressively shrunk
│   │   │   ├── api-client.js            # new: fetch/error/auth adapter
│   │   │   └── data-source.js           # new: demo vs API switch
│   │   └── src/                        # target: ESM modules, populated incrementally
│   │       ├── main.js
│   │       ├── modules/{mdl,qta,crt}/
│   │       └── shared/{api,auth,ui,utils}/
│   └── api/
│       ├── pyproject.toml
│       ├── alembic.ini
│       ├── migrations/{env.py,versions/}
│       ├── src/aq_uai/
│       │   ├── main.py
│       │   ├── core/{config.py,security.py,errors.py,logging.py}
│       │   ├── db/{base.py,session.py}
│       │   ├── modules/
│       │   │   ├── identity/{models.py,schemas.py,repository.py,service.py,router.py}
│       │   │   ├── mdl/{models.py,schemas.py,repository.py,service.py,router.py}
│       │   │   ├── qta/{models.py,schemas.py,repository.py,service.py,router.py}
│       │   │   ├── crt/{models.py,schemas.py,repository.py,service.py,router.py}
│       │   │   ├── audit/{models.py,service.py,router.py}
│       │   │   └── settings/{models.py,service.py,router.py}
│       │   └── integrations/
│       │       ├── providers/{base.py,openai_compatible.py,anthropic.py,google.py}
│       │       └── directory/{base.py,local.py,external_future.py}
│       └── tests/{unit,integration,acceptance}/
├── infra/{compose.yaml,proxy/,postgres/}
├── docs/{FRD,architecture,api,decisions,prototype,testing}/
├── scripts/{dev-up.sh,dev-down.sh,seed-demo.sh,check.sh}
├── tests/e2e/
└── .github/workflows/ci.yml
```

`migrations/versions` is **the authoritative DB schema-change history**; `infra/postgres` is only the container/database setup, not a second schema authority. Avoid a standalone root `database/` service. Module names `mdl`, `qta`, `crt` match FRD identifiers; their user-visible Vietnamese titles remain unchanged.

## B. Why this stack

| Option | Benefits | Costs | Decision |
|---|---|---|---|
| Python/FastAPI | Strong fit for AI integrations, concise typed contracts, automatic OpenAPI, quick development | Need disciplined layering; Python dynamic semantics | **Choose** |
| TypeScript/NestJS | Unified JS language, mature patterns/decorators | Forces new server conventions and more boilerplate; frontend is vanilla anyway | Not chosen |
| C#/.NET | Strong enterprise stack; possible company compatibility | Actual company framework is unavailable and its stack is unverified; unnecessary speculative coupling | Not chosen now |
| PostgreSQL | FK/constraints, concurrency, transactions, JSONB where necessary | Requires configured DB service | **Choose** |
| SQLite | Ultra-simple local setup | Different concurrency/locking and migrations; not appropriate substitute for transactional grant/ledger tests | Unit fixtures only if needed; not system DB |
| Single modular monolith | Simple deployment, transaction boundaries across MDL/QTA/CRT, easier debugging | Requires enforced domain boundaries | **Choose** |
| Microservices | Independent scaling if justified later | Distributed consistency and operational burden | Defer |
| Keep vanilla JS | Preserves visually mature frontend, no rewrite | Globals are difficult to maintain | Keep short term, modularize |
| React/Vue rewrite | Component framework | High UI regression/learning cost without business necessity | Defer |

FastAPI APIRouter allows multi-file structured APIs and automatic OpenAPI; SQLAlchemy 2/Alembic allow transactional persistence and reviewed migrations. Vite's dev proxy can later forward `/api` to FastAPI while preserving the UI's origin during development.

## C. Logical architecture and boundaries

```text
Browser / AQ EduUAI web
    |
    | HTTPS /api/v1; cookie session; CSRF protection on mutations
    v
Reverse proxy (one public origin)
    |-- static frontend assets
    '-- /api/v1 -> FastAPI (single application)
                     |
          +----------+-----------+-------------+
          |          |           |             |
      Identity      MDL         QTA           CRT
     /RBAC/unit  providers   group-model    grants /
       scope       models       quota        reclaim
          |          |           |             |
          +----------+-----------+-------------+
                     |  shared audit & DB unit of work
                     v
                 PostgreSQL
                     |
           explicit provider connectors
          (HTTPS / internal endpoint allowlist)

Future AQ EduSmart / company framework integration:
    external adapter -> versioned API/directory bridge
    NOT direct reads/writes to each other's databases.
```

**Boundary:** UI never directly writes SQL, invokes third-party models with secrets, or makes final access decisions. Routers do HTTP parsing/responses and authorization dependencies; services enforce business invariants; repositories encapsulate SQL; integrations implement provider/directory-specific behavior. Avoid putting business logic in route handlers or ORM model hooks.

**Sessions/transaction model:** Start with synchronous SQLAlchemy sessions and `def` endpoints. For mutations, one database transaction commits the state change and its corresponding audit event together. Long-running external network calls must **not** hold DB row locks: record a pending test run, perform bounded network test, then persist its result in a short new transaction. Later async optimization is optional if profiling justifies it.

## D. Foundation to implement before module-specific code

### D1. Product scope and acceptance

The handover also mentions inherited framework features: account list, account groups, user/group authorization, parent organization, SMTP settings, email templates, counters, page content and unit directory. Since there is no framework to inherit, these capabilities do **not** magically exist. Separate them into:

- **Foundation required immediately:** users, organizational units, system groups, roles, permissions, login/sessions, admin bootstrap, audit actor, app config, minimal operational settings.
- **Later core shell features:** SMTP, email templates, counters, page content and comprehensive account admin screens. They remain outstanding obligations if the handover's full shell is part of final acceptance; do not quietly mark them done.
- **Three FRD modules:** MDL, QTA, CRT, implemented after the necessary foundation.

A `docs/acceptance-matrix.md` should map all **33** FR IDs to endpoint(s), UI screen(s), validation, tests and result. Treat Must vs Should vs Could accurately. Do not accept mock test connections or localStorage ledger as production completion.

### D2. Identity/permissions, from scratch

Define an internal `User`, `Institution`, `Unit`, `AccountGroup`, `GroupMembership`, `Role`, `Permission`, `RoleGrant`, `Session`. Group membership and user status must be authoritative. Use **Argon2id** for local bootstrap/password accounts, short-lived server-side opaque session tokens in `HttpOnly`, `Secure`, `SameSite` cookies, session rotation/invalidation, login throttling and CSRF protection for state-changing operations. A corporate OIDC/SSO integration is a future adapter, not a blocker today.

Minimum permission concepts:

- MDL: `mdl.read`, `mdl.write`, `mdl.connection_test`, `mdl.route`, `mdl.dpa_manage`.
- QTA: `qta.read`, `qta.configure`, `qta.sync`, `qta.suspend`, `qta.restore`.
- CRT: `crt.read`, `crt.grant`, `crt.reclaim`, `crt.export`.
- Directory and audit: `identity.read`, `identity.manage`, `audit.read`.

Enforce action and **institution/unit scope** inside services/queries, not just route-level role checks. A user may be `AI_ADMIN`, `INSTITUTION_VIEWER`, `UNIT_MANAGER` or `USER` by assignment; permission maps are configurable. Never trust `userId`, `unitId`, `by`, or `orderedBy` as proof of authority. Keep human-readable orderer/decision reference fields as metadata but use authenticated `actor_id` as the auditable identity.

### D3. Business terminology and period model

Designate a **calendar-month period** by its first day (DATE e.g. `2026-11-01`) in institution-local timezone, not an integer `epoch`. Store events in `timestamptz` UTC; present Vietnamese dates in `Asia/Ho_Chi_Minh` (or institution-configured IANA timezone). Month reset must be unique per institution/month, idempotent and retriable; historical entries remain and prior positive balances do not carry over.

Define precisely:
- `model_token_entitlement`: group × model × month, additive over memberships;
- `token_consumption`: account × model × month and request id (if model invocation is later supported);
- `institution_credit_budget` and `personal_credit_ledger`: internal credit units, governed by documents and period;
- `model_price/conversion_policy`: **undecided** and not silently assumed. Existing demo tokens and credits are independent.

Critically, until a conversion/allocation contract exists, QTA-011 and CRT-013 cannot be certified across these ledgers merely by adding two unlike units. Preserve a clear interface boundary and block cross-unit enforcement from being represented as implemented. Decide the currency/unit, precision and cost basis with PO before QTA/CRT financial enforcement.

### D4. PostgreSQL schema design principles

- Prefer UUID primary keys with separate unique business `code`; FKs and check constraints on all relationships.
- Fields to include: `institution_id` or the institution-specific scope for future portability, `created_at`, `updated_at`, actor IDs for changes, lifecycle status, `version` for concurrency when necessary.
- Use normalized relational core tables and JSONB only for provider-specific structured nonsecret options or sanitized change details.
- Store quota/count units as BIGINT; money/prices as `NUMERIC`, never floating-point; no mixed numeric column without an explicit unit/denomination.
- Use `UNIQUE(institution_id, period_month)` for monthly budgets and similarly appropriate unique keys for group-model-period policies.
- Never cascade-delete referenced ledger entries or audit history; use deactivation and append-only amendments.
- For grants/reclaims, lock the relevant budget/account rows or use a comparably safe transaction/isolation strategy; commit ledger entry and affected allocation atomically; require idempotency keys on retriable mutations.
- Use Alembic versions for all production schema changes, review every generated migration and test migrations on a clean database.

**Proposed logical entities** (not a frozen DDL):

| Domain | Entities | Important constraints |
|---|---|---|
| Identity | `institutions`, `units`, `users`, `account_groups`, `memberships`, `roles`, `permissions`, `role_grants`, `sessions` | Active users, group source/system vs specialized, unit scope |
| MDL | `ai_providers`, `provider_credentials`, `data_agreements`, `ai_models`, `model_test_runs`, `route_configs`, `route_revisions` | Provider FK; no returned raw secret; eligible tested model, DPA, distinct primary/backup, route history |
| QTA | `monthly_budgets`, `group_model_quotas`, `group_sync_runs`, `suspensions`, `usage_events`, `refresh_runs` | Month-only period, additive entitlement, suspend scope & expiry, reset idempotency |
| CRT | `quota_ledger_entries`, `allocation_accounts` (if necessary), `approval_references` | Immutable transaction rows, one identified person, signed amount/unit, proof, no over-recovery, atomicity |
| Audit | `audit_events` | Actor, action, target, timestamp, safe before/after or diff, request ID, no secret/PII dumping |

`provider_credentials`: encrypt secret at rest with an application envelope key stored outside the DB (`.env` locally, secret store in deployment), never echo the credential in GET responses, and treat blank update input as keep-previous. Build a rotation/update endpoint. Development fake secrets must be obviously dummy, not plausible production credentials. Restrict external HTTPS endpoints and SSRF/redirect behavior; allow internal IP ranges only for explicitly configured, approved on-prem providers.

### D5. API design and error contracts

Prefix endpoints with `/api/v1`. Provide OpenAPI, predictable JSON, stable machine error codes, pagination/filtering and role-filtered read results. Suggested groups:

```http
GET    /health/live
GET    /health/ready
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/me
GET    /api/v1/users
GET    /api/v1/groups
GET    /api/v1/units

GET    /api/v1/providers
POST   /api/v1/providers
GET    /api/v1/providers/{provider_id}
PATCH  /api/v1/providers/{provider_id}
PUT    /api/v1/providers/{provider_id}/credential
POST   /api/v1/providers/{provider_id}/agreements
GET    /api/v1/models
POST   /api/v1/models
GET    /api/v1/models/{model_id}
PATCH  /api/v1/models/{model_id}
POST   /api/v1/models/{model_id}/connection-tests
GET    /api/v1/models/{model_id}/connection-tests
POST   /api/v1/models/{model_id}/deactivate
GET    /api/v1/routing
PUT    /api/v1/routing
GET    /api/v1/routing/revisions
GET    /api/v1/audit-events

GET    /api/v1/monthly-budgets?month=YYYY-MM
PUT    /api/v1/monthly-budgets/{month}
POST   /api/v1/groups/sync
GET    /api/v1/groups/{id}/model-quotas?month=YYYY-MM
PUT    /api/v1/groups/{id}/model-quotas?month=YYYY-MM
GET    /api/v1/users/{id}/entitlements?month=YYYY-MM
POST   /api/v1/users/{id}/suspensions
POST   /api/v1/users/{id}/restorations
POST   /api/v1/monthly-refresh-runs

POST   /api/v1/grants
POST   /api/v1/reclaims
GET    /api/v1/users/{id}/credit-balance?month=YYYY-MM
GET    /api/v1/ledger?month=YYYY-MM
```

These are **proposed contracts**, not claims that routes exist. Use `GET` read, `POST` command, `PATCH` partial update, `PUT` replace/update declarative state. Expose validation/authorization conflicts with meaningful 400/401/403/404/409/422 codes and structured `code`, `message`, `details`, `request_id` fields. Do not leak provider secrets through errors. E.g. `MODEL_ALREADY_IN_ROUTING`, `DPA_REQUIRED`, `MODEL_CONNECTION_TEST_REQUIRED`, `QUOTA_INSUFFICIENT`, `INSUFFICIENT_PERMISSION`, `IDEMPOTENCY_CONFLICT`.

### D6. Deployment/security/quality

- Docker Compose for PostgreSQL and optionally API/reverse proxy; avoid publishing Postgres port outside localhost; use persistent named volumes.
- Development: localhost web and API; production: HTTPS with reverse proxy, one public origin, DB internal only. Restrict CORS rather than enabling `*` with cookie credentials.
- `.env.example` without secrets; `.env`, keys, database dumps, logs containing tokens, backups and venv excluded from Git; pre-commit secret scanning recommended.
- JSON structured logs with request ID and PII/secret scrubbing; separate immutable business audit table from operational logs.
- Encrypted backups, documented restore verification and migrations before deployment; add DB health and graceful shutdown.
- Unit tests for business services and policies; PostgreSQL-backed integration tests for FK/transactions/locks; API contract tests for permissions; frontend tests for rendering/error states; browser E2E for 3 module journeys.
- CI: Ruff, pytest, JavaScript lint/build, security checks, migrations on clean Postgres, acceptance traceability.

## E. Module boundaries and dependencies

1. **Identity + audit:** prerequisite for legitimate admin actions and authenticated logs.
2. **MDL:** providers → DPA → models → real connection-test records → primary/fallback route. Can be implemented while token/credit conversion remains unresolved. A successful test does not consume a **user's** quota; note that actual provider calls could still incur provider charges.
3. **QTA:** directory groups/memberships → monthly group-model quota → additive per-person result → usage/suspension/refresh. Group synchronization initially reconciles against *our own identity directory*, preserving AI-specific groups; external company directory is a later adapter.
4. **CRT:** monthly institution budget → grant and recovery commands for an identified person → append-only ledger → balances/reports. Needs agreed unit/budget model and transactional invariants.
5. **Gateway:** actual user AI requests, real token metering and billable inference are outside current MDL/CRT FRDs. Implement reusable policy check/enforcement contracts, but do not claim end-to-end user AI blocking without a request boundary or a test gateway harness. The gateway may be a later iteration.

## F. Module 1 design handshake (first vertical slice)

**FRD MDL:** nine requirements; only actual server-enforced behavior can be considered complete.

**Essential entities:** `ai_providers`, `provider_credentials`, `data_agreements`, `ai_models`, `model_test_runs`, `route_configs`/`route_revisions`, `audit_events`.

**State machine (recommendation):**

```text
Provider: DRAFT -> CONFIGURED -> ACTIVE / DISABLED
External provider eligibility: documented, approved DPA required to test or route
Model: REGISTERED -> TESTED_OK / TESTED_FAILED -> ACTIVE -> DISABLED
Route: NONE -> PRIMARY + optional BACKUP (distinct, eligible)
```

One model can be registered but not test-eligible until its provider has a valid connection credential and, if external, approved agreement. On credential/provider endpoint/model ID changes, prior test success should be invalidated until re-tested. DPA revocation/expiry immediately makes the route ineligible; the service must block subsequent actual use and surface configuration remediation even if a stale route reference exists. Disallow disabling a model still primary/backup or otherwise bound by required references. Historical models remain readable.

**Core MDL acceptance scenarios:**

1. Unauthorized user cannot mutate a provider/model, even by direct API call.
2. Create internal and external providers with endpoint+credential; GET/edit never returns the secret; blank secret update preserves prior credential.
3. External provider without approval and decision reference cannot be connection-tested/routed.
4. Create a model linked to its provider; no assistant system prompt/creativity controls on MDL page (remove/clarify existing Temperature field).
5. Run an actual safe fixed-payload connection test using a mock provider adapter in CI; store successes/failures and zero user-quota charges.
6. Successfully tested active model can become PRIMARY; untested/failed cannot; BACKUP must differ.
7. Changing primary twice creates two retrievable route revisions with actor/date/before/after values.
8. Cannot disable active primary/backup; can disable former primary after updating route.
9. Risk classification is recorded and displayed at three levels; sample values not mandatory defaults.
10. No password, API secret, student data or full token in logs/audit/response.

Start provider connectors with **an injectable interface** and deterministic fake connector for tests, then one real integration (OpenAI-compatible API or on-prem service) to prove the API boundary. Add Anthropic/Vertex-specific adapters later only with credentials and approved endpoints; avoid pretending all providers follow the same payload or authentication contract.

**Frontend integration rules:** keep MDL CSS/layout; replace only MDL read/write/test/route handlers as API endpoints become verified; display real status/error messages, loading states and permissions. Preserve `DEMO_MODE` only for demo/dev, and fail closed in production.

## G. Delivery sequence with hard verification gates

| Gate | Implementation | Evidence to accept |
|---|---|---|
| **G0 — Baseline** | Git init/branch, existing frontend moved intact, FRDs/snapshots under docs, `.gitignore` | UI screenshot/navigation equivalence; no data loss; original ZIP retained |
| **G1 — Tooling** | Environment, Python package, FastAPI health, Docker Postgres, CI, test skeleton | One-command local setup; health/ready; clean test DB; no committed secrets |
| **G2 — DB/identity/audit** | Alembic initial schema, demo seed, account/session auth, RBAC/unit scope, audit trail | Migration reproducible, unauthorized API test 403, audited actor correct, tests green |
| **G3 — MDL backend** | Provider/model/DPA/credential/test/route/revision APIs | 9 MDL FRDs mapped to passing tests where in scope; no fake-success assertions |
| **G4 — MDL frontend** | Replace MDL demo data/actions through API adapter | Full browser CRUD, test, route, DPA, logout, errors; no secret exposure |
| **G5 — QTA semantics** | PO-approved quota units/budget contract, group sync, month/entitlement/kill switch | Additive multi-group tests, inactive semantics test, 00:00 rollover/idempotency tests |
| **G6 — QTA integrated** | UI integration and authorization policy enforcement | Person lookup correct for all configured models, simulated request denied on suspension |
| **G7 — CRT backend** | Grants, reclaim, ledger, concurrent budget constraints, approval records | Parallel overgrant blocked; duplicate retry idempotent; no mutation of prior rows |
| **G8 — CRT UI + final review** | UI forms, exports, unit-scope, 33 FRD matrix and demo | End-to-end acceptance, audit, backup/restore, full Must coverage or documented exception |
| **G9 — Product shell obligations** | SMTP/templates/counter/page content/account admin as agreed in acceptance scope | Independent requirement tests; no assumption inherited framework exists |

Do not assign durations until the environment, available provider credentials and accounting decisions are known. Each gate is a separate reviewable Git milestone; every change should maintain a runnable prior slice.

## H. Questions requiring an explicit business decision (not coding guesses)

**Blocking before QTA/CRT accounting:**

1. What exactly is `credit` (quantity, money, abstract consumption unit)? Which token-to-credit conversion or weighted model-cost policy, if any, is authoritative? May credits top up all models or a specific model?
2. Does the institution's total monthly budget constrain group allocations, person-level grants, or both? How to count users in overlapping groups without double counting? Do inactive groups lose entitlement immediately?
3. When a group membership or its quota changes midmonth, does entitlement recompute immediately and how is already consumed allowance handled?
4. Is an individual grant tied to one model, all model entitlements, or a separate global credit ledger? Which source of funding and approval roles are required?
5. How will the intended **unit-level** (khoa/phòng) budget delegation behave when an institution-level admin grants credits?

**Blocking before live MDL provider onboarding:**

6. Which model/provider endpoint can actually be used for the initial real connection test? What are permitted network destinations and credentials? Who verifies the external DPA documents?
7. Should primary/backup be one global routing configuration, one per modality, or one per institution? The current FRD illustrates a general primary/backup; start with per-institution global routing unless product owner specifies otherwise.

**Scope/ownership decisions:**

8. Does the three-FRD Dev acceptance also require operational SMTP, mail templates, counters and page content, or can they be a clearly documented subsequent product-shell tranche?
9. Which audit retention, backup/restore, personally identifying data, and institutional deployment policies are prescribed by AQTech?

Document answers in `docs/decisions/ADR-*.md` with status Proposed/Accepted, owner, date and the FRD IDs affected. Do not fabricate organizational approval; explicit user instructions can inform our working architecture while PO decisions remain pending.

## I. Decisions locked vs deferred

**Locked for independent implementation:** Python/FastAPI modular monolith; PostgreSQL 18; SQLAlchemy/Alembic; directory/auth/RBAC ourselves; Git monorepo with `apps/web`, `apps/api`, `infra`, `docs`; preserve current frontend; REST `/api/v1`; test-first acceptance; secure secret handling; append-only transactions; monthly period keys; future adapter compatibility.

**Deliberately deferred:** credit-to-token conversion; precise institution-group-unit budget mathematics; real model usage cost charging; actual legal DPA approvals; production organization auth integration; provider roster; user-facing gateway/chat; whole inherited system-config shell schedule; eventual company framework merge; frontend framework rewrite.

## Verified current external references

- FastAPI multi-file `APIRouter`: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- SQLAlchemy 2 session transactions: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
- Alembic autogenerate and required manual review: https://alembic.sqlalchemy.org/en/latest/autogenerate.html
- PostgreSQL support policy: https://www.postgresql.org/support/versioning/
- PostgreSQL release status, 12 Nov 2026: https://www.postgresql.org/about/news/postgresql-187-1712-1616-1520-1425-and-19-rc-2-released-3442/
- Vite dev proxy options: https://vite.dev/config/server-options
- OWASP API Top 10, including broken object-level authorization: https://owasp.org/projects/api-security-project

**Implementation policy:** This is the architecture planning artifact. Do not claim the backend, database schema, API routes, auth or production integrations have been implemented yet. Begin coding only after reviewing this blueprint with the project owner and preserving the existing frontend baseline.
