# QTA Stage Q2 completion report (Phase 4 · Module 2)

## 1. Summary

- **Status:** **implemented, awaiting review** (not formally accepted).
- Delivered QTA Stage Q2 under `/api/v1/qta`: read-only active MDL model catalogue, enrolled group registry (`qta_quota_groups`, empty before first sync), serialized directory synchronization (`POST /qta/groups/sync`), AI-specialist group lifecycle/membership endpoints delegating to `directory.service`, and per-model monthly quota upsert (`PUT /qta/groups/{id}/quotas`).
- Extended `authorization/policy.py::require_group_management` so `AI_SPECIALIST` accepts `qta.manage` **or** `directory.manage` while leaving `SYSTEM` and `AUTHORIZATION` untouched; refactored `directory/service.py` group helpers into `*_in_tx` inner functions so Phase 2 directory behavior is unchanged.
- Verified via 30 new automated tests (16 unit cases in `test_q2_contracts.py` + 14 PostgreSQL integration tests in `test_q2_qta_groups.py`), 3 required mutation proofs with byte-identical post-restore hashes, and the full `scripts/verify_phase2.sh` gate (**API 525 passed, 1 skipped; browser 16 passed**).
- No new migrations (head stays `0008_qta_schema`), no `mdl/` or `apps/web/` changes, no existing tests edited, and no invented units/prices/conversions/consumption (all quantities are abstract `"đơn vị hạn mức"` per `PD-Q1`).

---

## 2. Files

Every created or modified file under `apps/`, `tests/`, `scripts/`, `infra/`, and `docs/` matches [`docs/phase4/reports/q2/changed-files.txt`](q2/changed-files.txt) exactly (`CLAUDE.md` is at the repository root outside the `find` roots, inside the Section 3 allowlist). Nothing outside the Section 3 allowlist was edited.

| Path | Status | Why | FR / Finding |
| --- | --- | --- | --- |
| `apps/api/src/aq_uai_api/authorization/policy.py` | Modified | Extended `require_group_management` so `AI_SPECIALIST` accepts `qta.manage` OR `directory.manage` (`SYSTEM` and `AUTHORIZATION` unchanged) | F4, QD5, `FR-QTA-022` |
| `apps/api/src/aq_uai_api/directory/service.py` | Modified | Refactored `create_group`, `update_group`, `set_group_active`, and `set_membership` into `*_in_tx` inner functions reused by QTA in one transaction | F4, QD5, `FR-QTA-022` |
| `apps/api/src/aq_uai_api/main.py` | Modified | Registered `qta_router` under `/api/v1` | `FR-QTA-001` |
| `apps/api/src/aq_uai_api/qta/schemas.py` | New | Strict `extra="forbid"` Pydantic inputs and public projections for models, enrolled groups, sync runs, specialist groups, and group × model quotas (zero forbidden field names) | `FR-QTA-020/021/022`, `PD-Q1` |
| `apps/api/src/aq_uai_api/qta/queries.py` | New | Read-side GLOBAL `qta.read` projections: active MDL models (read-only SQL), enrolled `qta_quota_groups` (empty before sync), live directory memberships & active-member counts, append-only sync history | `FR-QTA-001 AC2`, `FR-QTA-020/021/022` |
| `apps/api/src/aq_uai_api/qta/service.py` | New | Protected writes under `qta.manage`: serialized sync (`QTA_SYNC_NAMESPACE = 52000`), specialist-group lifecycle calling `directory.service.*_in_tx` + enrolling `qta_quota_groups`, and group × model quota upsert with per-row change auditing | `FR-QTA-020/021/022`, `RULE-QTA-05` |
| `apps/api/src/aq_uai_api/api/v1/qta.py` | New | 13 FastAPI endpoints across 10 routes under `/api/v1/qta` | `FR-QTA-001/020/021/022` |
| `apps/api/tests/unit/test_q2_contracts.py` | New | 16 unit test cases: `require_group_management` matrix, exact Q2 OpenAPI routes, forbidden-field & strict-input guards, MDL import-closure check | F4, `FR-MDL-020 AC3`, `FR-QTA-050` |
| `apps/api/tests/integration/test_q2_qta_groups.py` | New | 14 PostgreSQL integration tests covering RBAC matrix, empty-before-sync, sync lifecycle & `RULE-QTA-05`, specialist lifecycle & directory audits, directory compatibility, quota rules, tenant isolation, audit rollback, and concurrent sync serialization | `FR-QTA-001/020/021/022`, `RULE-QTA-05` |
| `docs/phase4/QTA_IMPLEMENTATION_PLAN.md` | Modified | Added `Q2 completion (2026-11-27)` section linking this report | Plan tracking |
| `docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md` | Modified | Updated status for `FR-QTA-001`, `FR-QTA-020`, `FR-QTA-021`, `FR-QTA-022`, `FR-QTA-050` (implemented in API; UI in Q5) | Traceability |
| `docs/PROJECT_CONTEXT.md` | Modified | Updated QTA status & repository map lines to Q2 | Onboarding docs |
| `docs/acceptance-matrix.md` | Modified | Updated QTA status banner with exact Q2 gate counts (formal acceptance unchanged: 0/33) | Acceptance integrity |
| `CLAUDE.md` | Modified *(repo root)* | Updated current work line to Q2 and linked `QTA_Q2_REPORT.md` | Agent onboarding |
| `docs/phase4/reports/QTA_Q2_REPORT.md` | New | This completion report | Section 8 |
| `docs/phase4/reports/q2/git-status-before.txt` | New | Preflight `git status --short` snapshot | Section 2 |
| `docs/phase4/reports/q2/hashes-before.txt` | New | Preflight SHA256 manifest of `apps`, `tests`, `scripts`, `infra`, `docs` | Section 2 |
| `docs/phase4/reports/q2/baseline-gate.log` | New | Full pre-Q2 `verify_phase2.sh` output (API 495 passed, 1 skipped; browser 16 passed) | Section 2 |
| `docs/phase4/reports/q2/focused-tests.log` | New | Focused Q2 test run output (30 passed) | Section 6–7 |
| `docs/phase4/reports/q2/mutation-proof.log` | New | Full log of all 3 mutation proofs + pre/post-restore SHA256 hashes | Section 5, 7 |
| `docs/phase4/reports/q2/final-gate.log` | New | Full post-Q2 `verify_phase2.sh` output (API 525 passed, 1 skipped; browser 16 passed) | Section 6–7 |
| `docs/phase4/reports/q2/git-status-after.txt` | New | Postflight `git status --short` snapshot | Section 7 |
| `docs/phase4/reports/q2/hashes-after.txt` | New | Postflight SHA256 manifest (written after scan so it does not self-hash) | Section 7 |
| `docs/phase4/reports/q2/changed-files.txt` | New | `diff hashes-before.txt hashes-after.txt` confirming exact allowlist adherence | Section 7 |

---

## 3. Shared-code changes

### 3.1 `apps/api/src/aq_uai_api/authorization/policy.py` (`require_group_management` only)

Only lines 289–303 (`require_group_management`) changed; nothing else in `policy.py` was touched:

- **Before:**
  - `group_kind == "AUTHORIZATION"` → `authority.require_institution(PermissionCode.AUTHORIZATION_MANAGE, institution_id)`
  - `group_kind in {"SYSTEM", "AI_SPECIALIST"}` → `authority.require_institution(PermissionCode.DIRECTORY_MANAGE, institution_id)`
  - Any other `group_kind` → `DomainError(ErrorCode.VALIDATION_FAILED)`
- **After:**
  - `group_kind == "AUTHORIZATION"` → unchanged (`AUTHORIZATION_MANAGE` institution-wide).
  - `group_kind == "SYSTEM"` → unchanged (`DIRECTORY_MANAGE` institution-wide).
  - `group_kind == "AI_SPECIALIST"` → checks `authority.scope_for(DIRECTORY_MANAGE).allows_institution(institution_id) or authority.scope_for(QTA_MANAGE).allows_institution(institution_id)`; raises `DomainError(ErrorCode.FORBIDDEN)` if neither holds.
  - Any other `group_kind` → unchanged (`DomainError(ErrorCode.VALIDATION_FAILED)`).

### 3.2 `apps/api/src/aq_uai_api/directory/service.py` (minimal `*_in_tx` extraction only)

Four functions (`create_group`, `update_group`, `set_group_active`, `set_membership`) were split into an inner `*_in_tx` helper and a thin public wrapper; no other function, query, lock hint, or permission helper in `directory/service.py` changed:

1. `create_group_in_tx(db, authority, context, payload) -> AccountGroup`: runs `require_group_management`, inserts `AccountGroup`, flushes, writes `AuditAction.GROUP_CREATED`, returns `group`. Public `create_group` opens `protected(context, changes_authority=True)` and returns `schemas.GroupOut.model_validate(create_group_in_tx(...))`.
2. `update_group_in_tx(db, authority, context, group, payload) -> AccountGroup`: runs `require_group_management(authority, group.institution_id, group.kind)`; if `group.name != payload.name`, updates `name`/`updated_at` and writes `AuditAction.GROUP_UPDATED`. Public `update_group` opens `protected(context, changes_authority=False)`, resolves/locks `group = _group(db, authority, group_id, lock=True)`, and calls `update_group_in_tx`.
3. `set_group_active_in_tx(db, authority, context, group, active) -> AccountGroup`: runs `require_group_management`; raises `CONFLICT` on no-op state; updates `active`/`updated_at` and writes `AuditAction.GROUP_STATE_CHANGED`. Public `set_group_active` opens `protected(context, changes_authority=True)`, resolves `group = _group(db, authority, group_id)`, and calls `set_group_active_in_tx`.
4. `set_membership_in_tx(db, authority, context, group, user, active) -> schemas.MemberOut | None`: runs `require_group_management`, checks `user.institution_id == authority.institution_id`, rejects adding a member to an inactive group (`CONFLICT`), inserts/updates `GroupMembership`, writes `AuditAction.MEMBERSHIP_STATE_CHANGED`, and returns `queries.member_out(row, user) if active else None`. Public `set_membership` opens `protected(context, changes_authority=True, user_id=user_id, membership_group_id=group_id)`, resolves `_group` and `_user`, and calls `set_membership_in_tx`.

### 3.3 Proof that directory behaviour is unchanged

- All existing Phase 2 WP4 policy tests (`test_wp4_policy.py`), WP5 directory tests (`test_wp5_directory.py`), and all 16 Playwright browser tests (`tests/browser/`) passed without editing a single existing test (`final-gate.log`).
- New integration test `test_directory_behaviour_unchanged_for_specialist_groups` explicitly verifies `FOUNDATION_ADMIN` creating, renaming, adding/removing members, deactivating, and reactivating an `AI_SPECIALIST` group through `/api/v1/groups` with identical audit actions (`group.created`, `group.updated`, `membership.state_changed`, `group.state_changed`).

---

## 4. API

All routes live under `/api/v1/qta` with `Cache-Control: no-store`. All writes require session cookie, exact `Origin`, CSRF header, and transaction-time `qta.manage` re-check. All quantities represent abstract `"đơn vị hạn mức"` (`PD-Q1`).

| Method & Path | Permission | Status codes | Audit action |
| --- | --- | --- | --- |
| `GET /api/v1/qta/models` | GLOBAL `qta.read` | `200`, `401`, `403`, `422` | *(read)* |
| `GET /api/v1/qta/groups` | GLOBAL `qta.read` | `200`, `401`, `403`, `422` | *(read; empty before first sync)* |
| `POST /api/v1/qta/groups` | GLOBAL `qta.manage` | `201`, `401`, `403`, `409` (`QTA_DUPLICATE`), `422` | `group.created` *(via `directory.service`)* |
| `POST /api/v1/qta/groups/sync` | GLOBAL `qta.manage` | `200`, `401`, `403`, `422` | `qta.groups_synced` (`GroupsSynced`) |
| `GET /api/v1/qta/groups/sync-runs` | GLOBAL `qta.read` | `200`, `401`, `403`, `422` | *(read; newest first)* |
| `GET /api/v1/qta/groups/{group_id}` | GLOBAL `qta.read` | `200`, `401`, `403`, `404`, `422` | *(read)* |
| `PATCH /api/v1/qta/groups/{group_id}` | GLOBAL `qta.manage` | `200`, `401`, `403`, `404`, `422` (`QTA_GROUP_NOT_ELIGIBLE` / `VALIDATION_FAILED`) | `group.updated` *(via `directory.service`)* |
| `POST /api/v1/qta/groups/{group_id}/activate` | GLOBAL `qta.manage` | `200`, `401`, `403`, `404`, `409`, `422` | `group.state_changed` *(via `directory.service`)* |
| `POST /api/v1/qta/groups/{group_id}/deactivate` | GLOBAL `qta.manage` | `200`, `401`, `403`, `404`, `409`, `422` | `group.state_changed` *(via `directory.service`)* |
| `GET /api/v1/qta/groups/{group_id}/members` | GLOBAL `qta.read` | `200`, `401`, `403`, `404`, `422` | *(read; live `group_memberships`)* |
| `PUT /api/v1/qta/groups/{group_id}/members/{user_id}` | GLOBAL `qta.manage` | `200`, `401`, `403`, `404`, `409`, `422` | `membership.state_changed` *(via `directory.service`)* |
| `DELETE /api/v1/qta/groups/{group_id}/members/{user_id}` | GLOBAL `qta.manage` | `204`, `401`, `403`, `404`, `422` | `membership.state_changed` *(via `directory.service`)* |
| `PUT /api/v1/qta/groups/{group_id}/quotas` | GLOBAL `qta.manage` | `200`, `401`, `403`, `404`, `409` (`QTA_MODEL_NOT_ELIGIBLE`), `422` (`QTA_GROUP_NOT_ELIGIBLE` / `VALIDATION_FAILED`) | `qta.group_quota_updated` (`GroupQuotaUpdated`, only for changed rows) |

---

## 5. Tests

### 5.1 New unit tests (`apps/api/tests/unit/test_q2_contracts.py` — 16 collected cases)

| Test name | What it proves (FR / AC / Rule) |
| --- | --- |
| `test_require_group_management_matrix` (12 parametrized cases) | `{SYSTEM, AUTHORIZATION, AI_SPECIALIST}` × `{directory.manage, qta.manage, authorization.manage, none}` + cross-tenant denial (F4, QD5, `FR-QTA-022`) |
| `test_require_group_management_rejects_unknown_kind` | Unknown group kind rejected with `422 VALIDATION_FAILED` |
| `test_qta_openapi_routes_and_no_sync_run_mutation` | Exact Q2 route/method inventory; `sync-runs` has `GET` only (`FR-QTA-050 AC2`) |
| `test_qta_openapi_has_no_forbidden_fields_and_rejects_unknown_inputs` | Zero `period/semester/cycle/price/token/credit/consumption` fields in any QTA schema/op; `extra="forbid"` on every input; duplicate model, negative/bool limits, and out-of-range pct rejected (`FR-QTA-050`, `PD-Q1`) |
| `test_mdl_import_closure_reaches_no_qta_code` | Static import-closure proof that `mdl/` imports nothing from `qta/` (`FR-MDL-020 AC3`) |

### 5.2 New integration tests (`apps/api/tests/integration/test_q2_qta_groups.py` — 14 PostgreSQL tests)

| Test name | What it proves (FR / AC / Rule) |
| --- | --- |
| `test_rbac_matrix` | Every Q2 route × anonymous (401), `FOUNDATION_ADMIN` (403), `AI_MODEL_ADMIN` (403), `AI_QUOTA_VIEWER` UNIT (403), `AI_QUOTA_VIEWER` GLOBAL (reads 200 / writes 403), `AI_QUOTA_ADMIN` (200/201/204), plus missing CSRF refused (403) (`FR-QTA-001 AC1`) |
| `test_group_list_empty_before_first_sync` | Authorized user opens empty QTA group list before first sync even with Phase 2 `SYSTEM` groups (`FR-QTA-001 AC2`) |
| `test_sync_enrols_system_and_directory_specialist_groups` | Sync enrolls active `SYSTEM` (`origin='SYNC'`) and directory-created active `AI_SPECIALIST` (`origin='SPECIALIST'`), skips inactive pre-sync groups, reports exact counts & newest-first history (`FR-QTA-020 AC1`, 2026-11-27 review addition) |
| `test_sync_retires_and_restores_system_groups_without_deleting_quotas` | Deactivating a `SYSTEM` group sets `in_directory=false` & `groups_retired=1` without deleting quotas; repeated sync doesn't double-count; reactivating restores `in_directory=true` with quotas intact (`FR-QTA-020`) |
| `test_sync_preserves_specialist_groups_members_and_quotas` | Sync never touches active or inactive `origin='SPECIALIST'` rows (`in_directory`, `last_synced_at`, members, quotas unchanged; `FR-QTA-020 AC2`, `RULE-QTA-05`) |
| `test_sync_ignores_authorization_groups` | `AUTHORIZATION` groups are ignored by sync and invisible via `/qta/groups` |
| `test_specialist_group_lifecycle_uses_directory_audit_actions` | Create, rename, member add/remove/reactivate, deactivate/activate via `/qta/groups` writes `qta_quota_groups(origin='SPECIALIST')` in same transaction and emits Phase 2 directory audit actions (`group.created`, `group.updated`, `membership.state_changed`, `group.state_changed`; `FR-QTA-022 AC1`, F4) |
| `test_quota_admin_cannot_touch_system_or_authorization_groups` | `AI_QUOTA_ADMIN` gets 403 on `SYSTEM`/`AUTHORIZATION` groups via both `/qta/groups` and `/groups`, and 422 `QTA_GROUP_NOT_ELIGIBLE` on unenrolled specialist groups (F4) |
| `test_directory_behaviour_unchanged_for_specialist_groups` | `FOUNDATION_ADMIN` managing `AI_SPECIALIST` groups through `/api/v1/groups` behaves identically with identical directory audit trail (F4) |
| `test_two_models_two_limits_on_one_group` | Same group configures two distinct limits for two active models; partial update preserves unmentioned models (`FR-QTA-021 AC1`) |
| `test_quota_rules` | Unenrolled/AUTHORIZATION/inactive/retired group → `422 QTA_GROUP_NOT_ELIGIBLE`; inactive model → `409 QTA_MODEL_NOT_ELIGIBLE`; negative limit / pct 0 or 101 / duplicate model / unknown field → `422`; no-op writes nothing; changed rows audited with before/after (`FR-QTA-021`) |
| `test_tenant_isolation` | Another institution's groups, users, and models are absent from listings and return `404 NOT_FOUND` on every Q2 endpoint |
| `test_audit_failure_rolls_back` | Revoking `INSERT` on `audit_events` rolls back sync, specialist create (both `account_groups` and `qta_quota_groups`), and quota upsert cleanly (`500 DATABASE_ERROR`) |
| `test_concurrent_syncs_serialize` | Two synchronized threads calling `POST /qta/groups/sync` both return `200`, produce 2 sync runs (`groups_added` sorted `[0, 2]`), and enroll each group exactly once with zero `500`s (`QTA_SYNC_NAMESPACE`) |

### 5.3 Edited existing tests

**None.** Zero existing tests were modified, weakened, skipped, deleted, or xfailed.

---

## 6. Results

| Check | Baseline (`baseline-gate.log`) | Final (`final-gate.log`) | Delta / Notes |
| --- | --- | --- | --- |
| `scripts/verify_frontend_assets.py` | PASS (`10 assets exist`) | PASS (`10 assets exist`) | `apps/web/` untouched |
| `node --test scripts/test_sidebar_navigation.cjs` | `1 passed` | `1 passed` | Unchanged |
| `node --check` (`apps/web/**/*.js`, `apps/admin/assets/*.mjs`) | PASS | PASS | Unchanged |
| `ruff check` (API src/tests/migrations/scripts/demo-provider + `tests/browser`) | `All checks passed!` (×2) | `All checks passed!` (×2) | Clean |
| `scripts/verify_wp2_compose.py --env-file .env.example` | PASS | PASS | Unchanged |
| `alembic upgrade head` (`0001` → `0008_qta_schema`) & `alembic check` | `No new upgrade operations detected.` | `No new upgrade operations detected.` | Head unchanged (`0008_qta_schema`) |
| **Focused Q2 tests (`focused-tests.log`)** | — | **30 passed** in 121.02s | 16 unit + 14 PostgreSQL integration |
| **Full API suite (`apps/api/tests`)** | **495 passed, 1 skipped** (451.46s) | **525 passed, 1 skipped** (530.21s) | **+30 passed** (opt-in live provider stays skipped) |
| **Browser suite (`tests/browser`)** | **16 passed** (205.98s) | **16 passed** (207.40s) | Unchanged (no UI in Q2) |

Evidence log paths:
- Preflight baseline gate: `docs/phase4/reports/q2/baseline-gate.log`
- Focused Q2 tests: `docs/phase4/reports/q2/focused-tests.log`
- Mutation proofs: `docs/phase4/reports/q2/mutation-proof.log`
- Final full gate: `docs/phase4/reports/q2/final-gate.log`
- File manifests: `docs/phase4/reports/q2/git-status-before.txt`, `git-status-after.txt`, `hashes-before.txt`, `hashes-after.txt`, `changed-files.txt`

---

## 7. Mutation proof

Full log in [`docs/phase4/reports/q2/mutation-proof.log`](q2/mutation-proof.log).

| # | Rule | How temporarily broken | Failing test(s) & observed failure | Restored & verified |
| --- | --- | --- | --- | --- |
| 1 | Sync skipping `SPECIALIST` protection (`RULE-QTA-05`) | Replaced `if reg.origin != "SYNC": continue` in `qta/service.py::sync_groups` with `pass` | `test_sync_preserves_specialist_groups_members_and_quotas` FAILED (`assert run["groups_retired"] == 0` → `1 == 0`, exit 1) | Restored byte-identically; test PASSED (8.26s) |
| 2 | Quota model-eligibility check (`FR-QTA-021`) | Replaced `if not model.active: raise DomainError(ErrorCode.QTA_MODEL_NOT_ELIGIBLE)` in `qta/service.py::upsert_group_quotas` with `pass` | `test_quota_rules` FAILED (`assert 200 == 409` on inactive model, exit 1) | Restored byte-identically; test PASSED (9.18s) |
| 3 | `qta.manage` acceptance limited to `AI_SPECIALIST` (F4) | Changed `elif group_kind == "SYSTEM":` in `authorization/policy.py::require_group_management` to merge `SYSTEM` with `AI_SPECIALIST` (`qta.manage` accepted for `SYSTEM`) | `test_require_group_management_matrix[SYSTEM-qta.manage-False]` FAILED (`DID NOT RAISE DomainError`, exit 1) **and** `test_quota_admin_cannot_touch_system_or_authorization_groups` FAILED (`assert 422 == 403` on `PATCH /qta/groups/{sys}`, exit 1) | Restored byte-identically; both PASSED (0.96s & 10.41s) |

Pre-mutation and post-restore SHA256 hashes match byte-for-byte:
- `apps/api/src/aq_uai_api/qta/service.py`: `e3d3da7d50fe422a068ab8e6f36598ad4766e18a50171e1ce5fb6eff52c504fc`
- `apps/api/src/aq_uai_api/authorization/policy.py`: `ec8edb420de5174531e87b33b3bd94ba410be111ffb7662ba60f4c737409c7af`

---

## 8. Deviations from the plan or prompt

1. **`core/config.py` untouched:** `QTA_IMPLEMENTATION_PLAN.md` §Q2 originally mentioned adding `institution_timezone` to `core/config.py`, while `QTA_Q2_PROMPT.md` §3 explicitly instructed: *"Not needed in Q2: core/config.py (the timezone setting belongs to Q3; leave it)."* Followed the prompt and left `core/config.py` untouched.
2. **`db/audit.py` and `api/errors.py` untouched:** Both already contained all required Q2 audit actions/payloads (`QTA_GROUPS_SYNCED`/`GroupsSynced`, `QTA_GROUP_QUOTA_UPDATED`/`GroupQuotaUpdated`) and error codes (`QTA_GROUP_NOT_ELIGIBLE`, `QTA_MODEL_NOT_ELIGIBLE`, `QTA_DUPLICATE`) from Q1-R, so no edits were needed.
3. **Unknown / other-institution `model_id` on `PUT /qta/groups/{id}/quotas`:** Returns `404 NOT_FOUND` (matching Prompt §5 `other-institution model 409/404` and `test_tenant_isolation: another institution's groups/models are 404 everywhere`, avoiding cross-tenant existence leakage), while an inactive same-institution model returns `409 QTA_MODEL_NOT_ELIGIBLE`.
4. **Live `active_member_count` definition:** Counts live `GroupMembership.active = true` rows whose `User.state == 'ACTIVE'` (matching `PD-Q1` and `QTA_ARCHITECTURE_AND_DECISIONS.md` §2.1 so Q2 group counts stay consistent with Q3 allocation). `GET /qta/groups/{id}/members` still returns all stored memberships filtered by `MemberFilters` (`active=true` by default), matching `directory.queries.members`.

---

## 9. Open questions, risks & unverified items

- **Not verified in Q2:** hosted GitHub Actions CI; live Docker Compose deployment against the developer's persistent `aq-uai-dev` stack (intentionally untouched); opt-in live external AI provider check (`1 skipped`).
- **Git commit observed externally:** While `final-gate.log` was executing, commit `ee9229d` appeared on `main` (created externally, not by this agent), so `git-status-after.txt` reflects only edits made after `ee9229d` while `changed-files.txt` (`diff hashes-before.txt hashes-after.txt`) captures the complete pre-Q2 → post-Q2 file delta accurately.
- **Note for Q3 reviewer:** Because `require_group_management` now accepts `qta.manage` for `AI_SPECIALIST` (per F4 / Prompt 4.1), `AI_QUOTA_ADMIN` could theoretically call `POST /api/v1/groups` with `kind='AI_SPECIALIST'` (creating an unenrolled specialist group that the next sync would enroll), whereas `SYSTEM` and `AUTHORIZATION` remain strictly `403 FORBIDDEN` on both `/api/v1/groups` and `/api/v1/qta/groups`.
- **Remaining stages:** Q3 (entitlement computation, additive lookup, append-only school monthly budget revisions with allocation guard), Q4 (kill-switch/restore & monthly reset), Q5 (`#qta` Admin UI), and Q6 (cross-module MDL isolation proof, backup/restore rehearsal & handoff) await separate authorization.

---

## 10. Independent review (Claude Code, 2026-11-27)

**Verdict: Q2 approved for continued development, with one fix applied.** Not formal FRD acceptance.

**What was checked**
- File control: the current tree matches `hashes-after.txt` exactly. `changed-files.txt` stays inside the §3 allowlist: no `mdl/`, `apps/web/`, migration or existing-test edits.
- `directory/service.py`: diffed against the Phase 2 originals (`2c909e3`). The `*_in_tx` split preserves logic, lock order and audit actions. The only additions are a redundant re-check (`require_group_management`) and a same-institution user check in the inner functions.
- Policy: only `AUTHORIZATION` groups confer permissions, so adding members to a specialist group through QTA cannot escalate anyone's access.
- QTA service and queries:
  - Every query is scoped to the caller's institution.
  - Sync is serialized by an advisory lock and never touches `origin='SPECIALIST'` rows (`RULE-QTA-05`).
  - The quota upsert locks the registry row, rejects ineligible groups and models, and audits only rows that changed.
  - MDL is read through its ORM models only; `mdl/` does not import `qta/`.

**Fix applied (F-Q2-1)**
- Problem: the new `require_group_management` rule meant `AI_QUOTA_ADMIN` could `POST /api/v1/groups` with `kind=AI_SPECIALIST`. That created an *unenrolled* group through the Phase 2 surface, bypassing `/qta/groups`. Rename, activate and member routes on `/groups` were already blocked by `_require_group_administration`; create was not. The report's §9 flagged this.
- Fix: the public `directory.service.create_group` wrapper now calls `_require_group_administration(authority)`. QTA's `create_group_in_tx` path is unchanged.
- Test: `test_quota_admin_cannot_touch_system_or_authorization_groups` now also asserts 403 for `AI_SPECIALIST` on `/api/v1/groups`.

**Independent gate (`scripts/verify_phase2.sh`, disposable PostgreSQL)**
- Run 1:
  - API: 525 passed, 1 skipped.
  - Browser: 15 passed, 1 failed. `test_backup_restores_history_and_runtime_writes` timed out waiting for the restored API's startup while the two suites ran in parallel. The API log shows "startup complete", and no Q2 code is involved.
- Run 2 (unchanged code): **API 525 passed, 1 skipped; browser 16 passed; exit 0.** Treated as a timing flake; noted, not hidden.

**Notes for Q3**
- Commit `ee9229d` (made during Antigravity's final gate run) already contains the final Q2 source and tests. The follow-up commit adds the F-Q2-1 fix, the CI pin and the Q2 docs and reports.
- The audit payload `GroupQuotaUpdated` has no `before` value for `warning_threshold_pct`. This is a minor nit; consider adding it when Q3 touches the audit contracts.
- Hosted CI: the earlier failures were the runner moving to Ubuntu 26.04, where Playwright 1.59 has no Chromium. `.github/workflows/ci.yml` is now pinned to `ubuntu-24.04`. This is not yet verified on GitHub.
