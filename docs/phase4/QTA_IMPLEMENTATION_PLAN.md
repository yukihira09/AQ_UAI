# QTA implementation plan (Phase 4 · Q0–Q6)

**Scope:** Complete end-to-end delivery of Module 2 (`AQ-FRD-UAI-QTA-001` — *Hạn mức AI theo Nhóm tài khoản*) inside the AQ EduUAI modular monolith, reusing Phase 2 identity/directory/RBAC/audit/transactions and Phase 3 MDL model catalogue without modifying `mdl/`.

Documents: [Architecture & decisions](QTA_ARCHITECTURE_AND_DECISIONS.md) · [Open decisions](QTA_OPEN_DECISIONS.md) · [Requirements traceability](QTA_REQUIREMENTS_TRACEABILITY.md) · [ADR-0004](../architecture/ADR-0004-qta.md) · [Q1 review](QTA_Q1_REVIEW.md) · [Canonical FRD](../frd/AQ-FRD-UAI-QTA-001.md).

```text
Q0 docs ─▶ Q1 schema/RBAC ─▶ Q1-R revision ─▶ Q2 registry/sync/quotas ─▶ Q3 entitlements/budgets ─▶ Q4 kill-switch/reset ─▶ Q5 Admin UI (#qta) ─▶ Q6 verification & handoff
```

## Rules common to every stage

1. Follow `AGENTS.md`: state phase, FRD IDs, and exact files in scope; smallest reviewable change; write tests alongside/before business rules.
2. Never modify `apps/web/` or its original SHA256 manifests.
3. Keep `mdl/` untouched and strictly isolated from `qta/` imports (`FR-MDL-020 AC3`, `PD-Q2`).
4. Every Alembic revision ID must be ≤ 32 characters; `alembic upgrade head && alembic check` must pass on both clean and populated `0006` databases.
5. Run the full verification gate (`verify_phase2.sh`, including static checks, Ruff, `node --check`, `alembic check`, API suite, and Playwright browser suite whenever UI/shared contracts change); report API and browser counts separately and never claim unexecuted tests.
6. Never read/print secrets from `.env`, never touch the developer's running `aq-uai-dev` stack, and never commit/push without explicit instruction.

---

## Q0 — Planning, analysis & traceability (documentation only)

- **FRs:** All 12 `FR-QTA-*` IDs and 5 `RULE-QTA-*` rules analyzed.
- **Files:** `docs/phase4/QTA_ARCHITECTURE_AND_DECISIONS.md`, `docs/phase4/QTA_IMPLEMENTATION_PLAN.md`, `docs/phase4/QTA_OPEN_DECISIONS.md`, `docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md`.
- **Status:** Completed (2026-11-26); revised in Q1-R.

---

## Q1 — Initial access catalog, shared contracts, schema & runtime privileges

- **FRs:** `FR-QTA-001` (RBAC foundation), schema/grant scaffolding for `FR-QTA-010..050`.
- **Delivered (2026-11-26):** `0007_qta_access_catalog`, initial `0008_qta_schema`, `qta/models.py`, `authorization/policy.py`, `db/identity.py`, `api/errors.py`, `db/audit.py`, `db/provision.py`, `db/schema.py`, `apps/api/migrations/env.py`, `apps/admin/assets/pages.mjs`, pinned test updates, `test_q1_contracts.py`, `test_q1_qta_schema.py`.
- **Reviewed in:** [QTA_Q1_REVIEW.md](QTA_Q1_REVIEW.md) (confirmed 495 API passed, 1 skipped; 16 browser passed; identified findings F1–F11 resolved in Q1-R below).

---

## Q1-R — Revision of Q0–Q1 before Q2 (schema, PO decisions, ADR & restaging)

- **Trigger:** Independent review [QTA_Q1_REVIEW.md](QTA_Q1_REVIEW.md) (findings F1–F11) and Project Owner decisions **PD-Q1..PD-Q6** (2026-11-26). Migrations `0007`/`0008` had never been applied to any persistent database (`aq-uai-dev` observed at `0006_mdl_routing_and_styles`), so `0008_qta_schema` was amended in place keeping head at `0008_qta_schema`.
- **FRs:** `FR-QTA-001`, `FR-QTA-010`, `FR-QTA-011`, `FR-QTA-020`, `FR-QTA-021`, `FR-QTA-022`, `FR-QTA-030`, `FR-QTA-032`, `FR-QTA-040`, `FR-QTA-041`, `FR-QTA-050` (schema, privilege, audit, and design contracts only — no Q2 routes/services/UI).
- **Exclusions:** No Q2 services/routes/UI; no `mdl/` edits; no additional migrations beyond `0008_qta_schema`; no `authorization/policy.py::require_group_management` code change yet (planned for Q2 with tests).

### Q1-R completion (2026-11-26)

**Status: implemented and verified via full `verify_phase2.sh` gate (API + browser). No `FR-QTA-*` requirement is complete or accepted yet.**

- **Files created:**
  - `docs/architecture/ADR-0004-qta.md` (*Proposed* architectural decision record for Phase 4 QTA in the style of `ADR-0003`, recording `PD-Q1..PD-Q6`).
- **Files modified (schema, models, privileges, audit & tests):**
  - `apps/api/src/aq_uai_api/db/identity.py` — Added `UNIQUE (institution_id, id, kind)` (`uq_account_groups_institution_id_kind`) on `account_groups` so `qta_quota_groups` can enforce group-kind integrity via composite FK (F3).
  - `apps/api/migrations/versions/0008_qta_schema.py` — Amended in place (head remains `0008_qta_schema`): added `uq_account_groups_institution_id_kind`; replaced mutable `qta_monthly_budgets` with append-only `qta_budget_revisions` (`revision >= 1`, `decision_date` NOT NULL; F2, PD-Q4); added `qta_quota_groups` registry with `SYSTEM`/`SYNC` & `AI_SPECIALIST`/`SPECIALIST` checks and composite FK to `account_groups(institution_id, id, kind)` (F3); pointed `qta_group_model_quotas` FK to `qta_quota_groups`; added `groups_added` and `groups_retired` to `qta_group_sync_runs`; made `qta_suspensions.expires_at` nullable with finite-future check (F5, PD-Q3).
  - `apps/api/src/aq_uai_api/qta/models.py` — Mirrored `0008_qta_schema` exactly (`QtaBudgetRevision`, `QtaQuotaGroup`, updated `QtaGroupModelQuota`, `QtaGroupSyncRun`, `QtaSuspension`).
  - `apps/api/src/aq_uai_api/db/provision.py` — Updated `LEGACY_TABLES` and `QTA_RUNTIME_PRIVILEGES` for all 8 QTA tables (`qta_budget_revisions` INSERT-only; `qta_quota_groups` UPDATE only on `in_directory, last_synced_at`; `qta_group_sync_runs` INSERT includes `groups_added, groups_retired`; zero `DELETE` anywhere).
  - `apps/api/src/aq_uai_api/db/audit.py` — Replaced `MonthlyBudgetSet` with `BudgetRevisionRecorded` (`revision`, `before_decision_number`, required `decision_date`), added `groups_added`/`groups_retired` to `GroupsSynced`, made `UserSuspended.expires_at` optional.
  - `apps/api/tests/unit/test_q1_contracts.py` — Verified `BudgetRevisionRecorded`, `GroupsSynced`, optional `UserSuspended.expires_at`, 8 QTA tables, `LEGACY_TABLES` coverage, and column-level privileges.
  - `apps/api/tests/integration/test_q1_qta_schema.py` — Verified `qta_budget_revisions` INSERT-only & required `decision_date`; `qta_quota_groups` grants, origin/kind consistency, refusal of `AUTHORIZATION` & cross-tenant groups; `qta_group_model_quotas` refusal of unenrolled groups; `qta_group_sync_runs` new counts; `qta_suspensions` NULL vs future vs past expiry; populated `0006 -> 0008` upgrade preserving `account_groups` and `group_memberships` rows unchanged.
- **Files modified (documentation):**
  - `docs/phase4/QTA_OPEN_DECISIONS.md` — Recorded `PD-Q1..PD-Q6` verbatim with provenance `"Project Owner decision, 2026-11-26"` and accurate `SPEC`/`PO`/`REC`/`PROV`/`NEEDS-INSTITUTION` labels (F1, F10).
  - `docs/phase4/QTA_ARCHITECTURE_AND_DECISIONS.md` — Updated unit wording to `"đơn vị hạn mức"`, removed all MDL-extension and duration-cap references, fixed §2.4 heading (`QD11`), documented `qta_budget_revisions`, `qta_quota_groups`, sync semantics, `directory.service` reuse, budget month window, and updated §3–§5.
  - `docs/phase4/QTA_IMPLEMENTATION_PLAN.md` — Restaged into Q2–Q6 (F11) and recorded Q1-R completion.
  - `docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md` — Updated table names, AC rules, and Q2–Q6 stage mappings.
  - `CLAUDE.md`, `docs/PROJECT_CONTEXT.md`, `docs/acceptance-matrix.md` — Updated status lines to Q1-R.
- **Verification (2026-11-26, full `scripts/verify_phase2.sh` gate on disposable PostgreSQL 18, nginx, and Chromium — exit 0):**
  - `scripts/verify_frontend_assets.py`: `PASS: 10 assets exist; frontend JS load order unchanged` (`apps/web/` untouched)
  - `node --test scripts/test_sidebar_navigation.cjs`: `1 passed`
  - `node --check` on all `apps/web/shared/*.js`, `apps/web/module*/*.js`, `apps/admin/assets/*.mjs`: PASS
  - `ruff check` on `apps/api/src`, `apps/api/tests`, `apps/api/migrations/env.py`, `scripts/verify_wp2_compose.py`, `infra/demo-provider/server.py`, and `tests/browser`: `All checks passed!`
  - `scripts/verify_wp2_compose.py --env-file .env.example`: `PASS: rendered Compose config isolates all database credential sets.`
  - `alembic upgrade head` (`0001_phase1_metadata` → `0008_qta_schema`) & `alembic check`: `No new upgrade operations detected.`
  - **API suite (`apps/api/tests`):** **495 passed, 1 skipped** (opt-in `live_provider` test; same test count as Q1 baseline because the existing 8 unit + 5 integration Q1 tests were expanded in place for all Q1-R invariants; zero regressions, MDL isolation tests green) in 403.75s
  - **Browser suite (`tests/browser`):** **16 passed** in 187.45s
  - Not run / out of scope for Q1-R: hosted GitHub Actions CI, Docker Compose live run against persistent `aq-uai-dev`, opt-in live-provider test.

---

## Q2 — Group registry, sync, specialist groups & group × model quota configuration

- **FRs:** `FR-QTA-001` (API RBAC + empty group list before sync), `FR-QTA-020` (AC1–AC2), `FR-QTA-021` (AC1 config), `FR-QTA-022` (AC1).
- **Files in scope:**
  - `apps/api/src/aq_uai_api/core/config.py` (add `institution_timezone: str = "Asia/Ho_Chi_Minh"` validated with `zoneinfo.ZoneInfo`).
  - `apps/api/src/aq_uai_api/authorization/policy.py` (extend `require_group_management` so `kind == "AI_SPECIALIST"` accepts `qta.manage` **or** `directory.manage`; `SYSTEM` and `AUTHORIZATION` unchanged — F4).
  - `apps/api/src/aq_uai_api/qta/schemas.py` (strict `extra="forbid"` request/response models for models, enrolled groups, sync runs, specialist groups, members, and group × model quotas).
  - `apps/api/src/aq_uai_api/qta/queries.py` (active MDL models read-only; enrolled `qta_quota_groups` list/detail with live `group_memberships` counts and per-model quotas; sync run history).
  - `apps/api/src/aq_uai_api/qta/service.py` (`sync_system_groups` with `QTA_SYNC_NAMESPACE` lock: enroll active `SYSTEM`, retire inactive/gone `in_directory=false`, re-enable returning `SYSTEM`, enrol not-yet-enrolled active `AI_SPECIALIST` groups created in the Phase 2 directory with `origin='SPECIALIST'` (review 2026-11-27), never modify existing `SPECIALIST` rows or quotas, write `qta_group_sync_runs` + `qta.groups_synced`; specialist-group create/update/activate/deactivate/membership delegating to `directory.service` + enrolling `qta_quota_groups(origin='SPECIALIST')` in the same transaction; `upsert_group_quotas` requiring enrolled group and active MDL model).
  - `apps/api/src/aq_uai_api/api/v1/qta.py` (registered in `main.py`): `/qta/models`, `/qta/groups`, `/qta/groups/sync`, `/qta/groups/sync-runs`, `/qta/groups/{id}`, `/qta/groups/{id}/activate|deactivate`, `/qta/groups/{id}/members`, `/qta/groups/{id}/members/{user_id}`, `/qta/groups/{id}/quotas`.
- **Tests:**
  - `apps/api/tests/unit/test_q2_contracts.py` (schema validation, `require_group_management` unit matrix for `SYSTEM`/`AUTHORIZATION`/`AI_SPECIALIST` across `directory.manage` vs `qta.manage` vs `authorization.manage`, timezone config validation).
  - `apps/api/tests/integration/test_q2_qta_groups.py` (RBAC matrix across all roles; group list empty before first sync; sync enrolls active `SYSTEM` groups and reports `groups_added`; deactivating a `SYSTEM` group in directory and re-syncing sets `in_directory=false` and reports `groups_retired` without deleting quotas; re-activating restores `in_directory=true`; an `AI_SPECIALIST` group created through the Phase 2 directory is enrolled by the next sync and counted in `groups_added`; sync preserves existing `AI_SPECIALIST` registry rows, members, and quotas; creating/editing/toggling specialist groups and members through QTA uses `directory.service` audit actions and enrolls in `qta_quota_groups`; `AI_QUOTA_ADMIN` refused on `SYSTEM`/`AUTHORIZATION` groups; distinct limits for two models on one group; unenrolled or `AUTHORIZATION` group rejected for quotas; audit-failure rollback).
- **Exclusions:** Entitlement calculation, personal lookup, school monthly budget revisions, kill-switch, monthly reset, Admin UI (Q3–Q5).
- **Gate:** `verify_phase2.sh` (static checks, Ruff, `alembic check`, full API suite including new Q2 tests, browser suite).

### Q2 completion (2026-11-27)

**Status: implemented, awaiting review.** Full evidence and verification report: [QTA_Q2_REPORT.md](reports/QTA_Q2_REPORT.md) (logs & hash manifest under `docs/phase4/reports/q2/`).

- **Delivered:** `require_group_management` updated for `AI_SPECIALIST` (`qta.manage` OR `directory.manage`); `directory/service.py` refactored minimally into `*_in_tx` inner functions reused by QTA; new `qta/{schemas,queries,service}.py` and `api/v1/qta.py` (13 operations across 10 paths under `/api/v1/qta`, registered in `main.py`); `test_q2_contracts.py` (16 unit cases) and `test_q2_qta_groups.py` (14 PostgreSQL integration tests); 3 required mutation proofs passed with byte-identical post-restore hashes. Zero migrations added (head stays `0008_qta_schema`), zero `mdl/` or `apps/web/` changes, zero existing tests edited. (`core/config.py` timezone setting deferred to Q3 per `QTA_Q2_PROMPT.md`.)
- **Verification (full `scripts/verify_phase2.sh` gate, `docs/phase4/reports/q2/final-gate.log`, exit 0):** static checks PASS, `alembic check` clean, **API 525 passed, 1 skipped** (+30 over baseline 495), **browser 16 passed**. No `FR-QTA-*` requirement is formally accepted yet (Admin UI arrives in Q5).

---

## Q3 — Entitlement computation, additive lookup & append-only school monthly budgets

- **FRs:** `FR-QTA-010` (AC1–AC3), `FR-QTA-011` (AC1), `FR-QTA-021` (AC2), `FR-QTA-022` (AC2), `FR-QTA-030` (AC1–AC2), `FR-QTA-031` (AC1–AC2).
- **Files in scope:**
  - `apps/api/src/aq_uai_api/qta/entitlements.py` (`compute_user_entitlements`, `allocated_for_month` per `PD-Q1`, `Asia/Ho_Chi_Minh` `YYYY-MM` period parser rejecting non-month cycles; includes only enrolled active groups with `in_directory=true`, active memberships, enabled quotas, active models; returns `base_entitlement`, per-group breakdown, `actual_consumption: null`, `remaining_quota: null`, `consumption_status: "NOT_INTEGRATED"`).
  - `apps/api/src/aq_uai_api/qta/schemas.py`, `qta/queries.py`, `qta/service.py`, `api/v1/qta.py`:
    - `GET /qta/budgets?month=YYYY-MM` (latest revision or `"chưa ghi nhận"`, revision history, `allocated`, `remaining`, `over_allocated` warning).
    - `PUT /qta/budgets/{month}` (current or next month only per F8; acquires `QTA_BUDGET_NAMESPACE`; rejects `total_limit < allocated` with `409 QTA_BUDGET_BELOW_ALLOCATED` + `{allocated, deficit}`; requires `decision_number` + `decision_date` per `PD-Q4`; appends new `qta_budget_revisions` row + `BudgetRevisionRecorded` audit event).
    - `GET /qta/users` & `GET /qta/users/{user_id}/entitlements?month=YYYY-MM` (GLOBAL or exact-UNIT `qta.read` scope).
- **Tests:**
  - `apps/api/tests/unit/test_q3_entitlements.py` (additive stacking `1,000 + 3,000 = 4,000`, zero groups = `0`, disabled quota / inactive group / retired `in_directory=false` / disabled user exclusion, month-only parser rejecting Semester/Project/Exam, current/next budget window checks).
  - `apps/api/tests/integration/test_q3_qta_lookup_budgets.py` (all numerical cases from architecture §2.1 in *đơn vị hạn mức*; disabling model removes base quota for single-group user `FR-QTA-021 AC2`; specialist group member appears in additive lookup `FR-QTA-022 AC2`; `actual_consumption` & `remaining_quota` are `null` / `NOT_INTEGRATED`; UNIT-scoped `AI_QUOTA_VIEWER` sees only own unit users & 404 on other units; budget revision 1 & revision 2 preserve history without overwrite; missing `decision_number` or `decision_date` rejected 422; past month or > next+1 month rejected; unset month returns `"chưa ghi nhận"` while quotas apply; `total_limit < allocated` returns `409` + exact `{allocated, deficit}`; directory growth & quota edits not blocked and surface `over_allocated`; concurrent budget writes serialized).
- **Exclusions:** Kill-switch/restore, monthly reset, Admin UI (Q4–Q5).
- **Gate:** `verify_phase2.sh` (static checks, Ruff, `alembic check`, full API + browser suites).

---

## Q4 — Kill-switch / restore (`check_ai_access`) & monthly reset

- **FRs:** `FR-QTA-032` (AC1–AC2), `FR-QTA-040` (AC1–AC3), `FR-QTA-041` (AC1–AC2), `FR-QTA-050` (AC1–AC2).
- **Files in scope:**
  - `apps/api/src/aq_uai_api/qta/entitlements.py` (add lazy active-suspension lookup `expires_at IS NULL OR expires_at > now()`, reusable `check_ai_access(db, institution_id, user_id, model_id)` enforcing `ALL_MODELS` vs `PAID_EXTERNAL_ONLY = EXTERNAL providers` per `PD-Q2`, and include active suspension + per-model access evaluation in `GET /qta/users/{id}/entitlements`).
  - `apps/api/src/aq_uai_api/qta/service.py` (suspend user under `QTA_SUSPENSION_NAMESPACE` with operator from `authority.actor_id`, mandatory `reason` & `ordered_by`, optional finite future `expires_at` per `PD-Q3`, balance untouched; restore user without adding quota; execute/simulate idempotent monthly reset under `QTA_RESET_NAMESPACE`, manual simulation restricted to current month only per `PD-Q6`).
  - `apps/api/src/aq_uai_api/qta/reset.py` (CLI `python -m aq_uai_api.qta.reset` for `00:00` day-1 `Asia/Ho_Chi_Minh` scheduled / catch-up runs; idempotent no-op if already recorded).
  - `apps/api/src/aq_uai_api/api/v1/qta.py` (`POST /qta/users/{id}/suspensions`, `POST /qta/users/{id}/restore`, `GET /qta/events`, `GET /qta/monthly-resets`, `POST /qta/monthly-resets`; zero `PATCH`/`PUT`/`DELETE` on events/resets/suspensions/sync-runs).
- **Tests:**
  - `apps/api/tests/unit/test_q4_access_reset.py` (`check_ai_access` matrix for `ALL_MODELS` vs `PAID_EXTERNAL_ONLY` across `INTERNAL`/`EXTERNAL`, lazy expiry with `None` vs future vs past, current-month-only manual reset guard, OpenAPI check confirming zero edit/delete endpoints on append-only resources and zero non-month cycle parameters).
  - `apps/api/tests/integration/test_q4_qta_killswitch_reset.py` (suspend with `expires_at=None` and with future `expires_at`; past `expires_at` / blank `reason` / blank `ordered_by` rejected 422; `suspended_by` always equals session actor even when `ordered_by` names someone else; `PAID_EXTERNAL_ONLY` blocks `EXTERNAL` models and allows `INTERNAL` models; `ALL_MODELS` blocks both; balances unchanged after suspend and restore; restore returns `ACTIVE` and records `RESTORE` event; lazy expiry auto-lifts suspension; concurrent suspend race returns 409 for second request; monthly reset CLI idempotent on retry; admin manual reset succeeds for current month, returns 409 on repeat, and rejects next/past month; catch-up after missed 00:00 works without backdating; zero rollover across months; active suspension survives monthly reset).
- **Exclusions:** Admin UI (Q5); backup/restore rehearsal & handoff (Q6).
- **Gate:** `verify_phase2.sh` (static checks, Ruff, `alembic check`, full API + browser suites).

---

## Q5 — Admin UI (`#qta` in `apps/admin/`)

- **FRs:** UI acceptance criteria of `FR-QTA-001` through `FR-QTA-050`.
- **Files in scope:**
  - `apps/admin/assets/qta.mjs` (3 tabs: *Nhóm & Hạn mức Mô hình*, *Tra cứu Cộng dồn Cá nhân*, *Làm mới tháng & Nhật ký*; detail view `#qta/groups/<id>`; dialogs for append-only monthly budget revision with required decision number + date, group sync, specialist group & members, per-model quotas, suspend with distinct *Người thực hiện* vs *Người ra lệnh* and optional expiry picker, restore, current-month manual reset; every quantity labelled **"đơn vị hạn mức"** with zero tokens/credits wording; honest *"Chưa tích hợp đo tiêu thụ thực tế"* state instead of fake progress bars; over-allocation warning banner; unset budget shows *"chưa ghi nhận"*).
  - `apps/admin/assets/app.mjs` (route `#qta[/<tab>[/<uuid>]]`).
  - `apps/admin/assets/pages.mjs` (register `qta` section + sidebar grouping into *Quản trị hệ thống* and *Quản lý AI & Chi phí*).
  - `apps/admin/assets/api.mjs` (allowlist numeric `deficit` & `allocated` in `safeDetails`, Vietnamese error messages for `QTA_*` codes).
  - `apps/admin/assets/admin.css` (QTA chips, formula breakdown, KPI/banner styles — CSP-compliant, mobile-responsive).
- **Tests:**
  - `tests/browser/test_qta.py` (Playwright end-to-end: unauthorized/`FOUNDATION_ADMIN` blocked; `AI_QUOTA_VIEWER` read-only & unit-scoped; empty group list before sync; sync populates `SYSTEM` groups while preserving `AI_SPECIALIST`; group × model distinct limits & disablement; additive `1.000 + 3.000 = 4.000` display with `NOT_INTEGRATED` consumption notice; monthly budget revision history & deficit rejection; kill-switch optional expiry & restore; current-month reset simulation; DOM checks proving `"đơn vị hạn mức"` wording with zero tokens/credits labels, zero non-Month cycle selectors, and zero Edit/Delete controls on recorded events/revisions).
- **Exclusions:** `apps/web/` (frozen prototype), `mdl.mjs` (unchanged per `PD-Q2`).
- **Gate:** `verify_phase2.sh` (static checks, `node --check`, Ruff, `alembic check`, full API + Playwright browser suites including `test_qta.py`).

---

## Q6 — Full verification, cross-module MDL isolation proof & Phase 4 handoff

- **FRs:** Cross-module `FR-MDL-020 AC3` proof + end-to-end technical verification of `FR-QTA-001` through `FR-QTA-050`.
- **Files in scope:**
  - `apps/api/tests/integration/test_q6_mdl_qta_isolation.py` (end-to-end proof that running an MDL connection test leaves a user's QTA entitlements, budget revisions, and QTA events completely untouched; backup/restore & `0006 -> 0008` upgrade rehearsal with populated QTA data).
  - `docs/phase4/qta-handoff.md` (runbook, manual acceptance checklist, known limitations, upgrade notes for `aq-uai-dev`).
  - `docs/acceptance-matrix.md`, `docs/PROJECT_CONTEXT.md`, `CLAUDE.md`, `docs/architecture/ADR-0004-qta.md` (status updates keeping technical verification distinct from formal PO/TL acceptance).
- **Exclusions:** No Phase 5 CRT implementation; no production deploy; no Git commit/push without explicit instruction.
- **Gate:** Full `verify_phase2.sh` (disposable PostgreSQL 18, nginx, Chromium), `alembic check`, backup/restore rehearsal, and exact report of API, browser, static, and Compose config check results.
