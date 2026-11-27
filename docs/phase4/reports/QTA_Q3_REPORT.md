# QTA Stage Q3 completion report (Phase 4 · Module 2)

## 1. Summary

- **Status:** **implemented, awaiting review** (not formally accepted).
- Delivered QTA Stage Q3 under `/api/v1/qta`: institutional timezone & calendar-month helpers (`qta/periods.py`, `core/config.py`), single-source-of-truth additive entitlement and SQL allocation computation (`qta/entitlements.py`), GLOBAL/UNIT-scoped user lookup and personal additive entitlements (`GET /qta/users`, `GET /qta/users/{user_id}/entitlements`), and append-only institutional monthly budgets (`GET /qta/budgets`, `PUT /qta/budgets/{month}`) serialized under `QTA_BUDGET_NAMESPACE = 52001` with the `total_limit < allocated` `409` guard.
- Enforced honest non-integrated consumption (`actual_consumption: null`, `remaining_quota: null`, `consumption_status: "NOT_INTEGRATED"`) and `"đơn vị hạn mức"` wording (`PD-Q1`); zero fabricated usage, prices, or token/credit conversions.
- Verified via 24 new automated tests (4 unit in `test_q3_entitlements.py` + 20 PostgreSQL integration in `test_q3_qta_lookup_budgets.py`), 4 required mutation proofs with byte-identical post-restore hashes, and the full `scripts/verify_phase2.sh` gate (**API 549 passed, 1 skipped; browser 16 passed**).
- No new migrations (head stays `0008_qta_schema`), no edits to `mdl/`, `directory/`, `authorization/`, `db/audit.py`, or `apps/web/`, and zero weakening of existing tests.

---

## 2. Files

Every Q3-created or Q3-modified file under `apps`, `tests`, `scripts`, `infra`, `docs`, and `.github` matches [`docs/phase4/reports/q3/changed-files.txt`](q3/changed-files.txt) (`CLAUDE.md` is at the repository root outside the `find` roots, inside the Section 3 allowlist). One additional entry in `changed-files.txt` — `.github/workflows/context-snapshot.yml` — was added by the Project Owner's concurrent commit `c10c801` during the run (see §9) and was not created or modified by Q3. Nothing outside the Section 3 allowlist was touched by Q3.

| Path | Status | Why | FR / Finding |
| --- | --- | --- | --- |
| `apps/api/src/aq_uai_api/core/config.py` | Modified | Added `institution_timezone: str = "Asia/Ho_Chi_Minh"` (`AQ_UAI_INSTITUTION_TIMEZONE`) validated with `zoneinfo.ZoneInfo` at load time | QD2, `FR-QTA-010` |
| `apps/api/src/aq_uai_api/api/errors.py` | Modified | Appended `QTA_PERIOD_NOT_OPEN` (422) at the end of QTA error codes | R2, `FR-QTA-010` |
| `apps/api/src/aq_uai_api/qta/periods.py` | New | Single QTA clock seam `utc_now()`, strict `YYYY-MM` `parse_month()`, `current_month()` / `next_month()` in institution timezone, `require_open_month()` | R1, R2, `FR-QTA-010`, `RULE-QTA-01` |
| `apps/api/src/aq_uai_api/qta/entitlements.py` | New | Single source of truth for live additive `compute_user_entitlements()` (SUM, never MAX) and one-query SQL aggregate `allocated_for_month()` (Phase 5 CRT seam) | `PD-Q1`, `PD-Q5`, `FR-QTA-011/021/022/030/031`, `RULE-QTA-02` |
| `apps/api/src/aq_uai_api/qta/schemas.py` | Modified | Added strict `extra="forbid"` Q3 inputs (`MonthQuery`, `SetMonthlyBudget`) and response projections (`QtaUserOut`, `UserEntitlementsOut`, `MonthlyBudgetOut`, etc.) using `month` (R3) and `NOT_INTEGRATED` consumption fields (R4) | R1–R4, `PD-Q1`, `PD-Q4`, `FR-QTA-010/030/031` |
| `apps/api/src/aq_uai_api/qta/queries.py` | Modified | Added GLOBAL/UNIT-scoped `users()` and `user_entitlements()`, plus GLOBAL-only `budget()` / `budget_for_tenant()` with `LIVE` vs `NOT_SNAPSHOTTED` status | R1, `FR-QTA-001/010/030/031` |
| `apps/api/src/aq_uai_api/qta/service.py` | Modified | Added `QTA_BUDGET_NAMESPACE = 52001` and `record_budget_revision()` (append-only `qta_budget_revisions`, `total_limit < allocated` 409 guard with `{allocated, deficit}`, same-transaction `BudgetRevisionRecorded` audit; Q2 paths untouched) | `FR-QTA-010`, `FR-QTA-011`, `INV-18`, `RULE-QTA-04` |
| `apps/api/src/aq_uai_api/api/v1/qta.py` | Modified | Registered `GET /qta/users`, `GET /qta/users/{user_id}/entitlements`, `GET /qta/budgets`, `PUT /qta/budgets/{month}` | `FR-QTA-010/011/030/031` |
| `apps/api/tests/unit/test_q1_contracts.py` | Modified | Added `"QTA_PERIOD_NOT_OPEN"` to pinned `QTA_CODES` list (line 29) | R2 (allowlist §3) |
| `apps/api/tests/unit/test_q2_contracts.py` | Modified | Added the 4 Q3 routes to pinned OpenAPI inventory (lines 113–116) and narrowed output-schema check per R4 for `actual_consumption` / `consumption_status` only while keeping inputs/params fully strict and regex unchanged (lines 121–155) | R4 (allowlist §3) |
| `apps/api/tests/unit/test_q3_entitlements.py` | New | 4 unit tests: `parse_month`, timezone rollover window, invalid timezone settings rejection, Q3 OpenAPI month-only & strict input checks | `FR-QTA-010`, `RULE-QTA-01` |
| `apps/api/tests/integration/test_q3_qta_lookup_budgets.py` | New | 20 PostgreSQL integration tests covering §2.1 numerical example, additive `1000+3000=4000`, zero-group, model disablement, specialist lookup, all exclusion reasons, `NOT_INTEGRATED` consumption, SQL consistency, UNIT/GLOBAL scope, append-only revisions, required decision fields, month window, unrecorded month, past month R1, equal vs below 409, over-allocation warning, RBAC/CSRF/Origin, tenant isolation, audit rollback, concurrent budget serialization | `FR-QTA-010/011/021/022/030/031`, `RULE-QTA-01/02/04` |
| `docs/phase4/QTA_IMPLEMENTATION_PLAN.md` | Modified | Added `Q3 completion (2026-11-27)` section linking this report | Plan tracking |
| `docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md` | Modified | Updated status for `FR-QTA-001/010/011/021/022/030/031/050` (implemented in API; UI in Q5) | Traceability |
| `docs/PROJECT_CONTEXT.md` | Modified | Updated QTA status & repository map to Q3 | Onboarding docs |
| `docs/acceptance-matrix.md` | Modified | Updated QTA status banner with exact Q3 gate counts (formal acceptance unchanged: 0/33) | Acceptance integrity |
| `CLAUDE.md` | Modified *(repo root)* | Updated current work line to Q3 and linked `QTA_Q3_REPORT.md` | Agent onboarding |
| `docs/phase4/reports/QTA_Q3_REPORT.md` | New | This 10-section completion report | Section 8 |
| `docs/phase4/reports/q3/git-status-before.txt` | New | Preflight `git status --short` snapshot | Section 2 |
| `docs/phase4/reports/q3/hashes-before.txt` | New | Preflight SHA256 manifest of `apps`, `tests`, `scripts`, `infra`, `docs`, `.github` | Section 2 |
| `docs/phase4/reports/q3/baseline-gate.log` | New | Full pre-Q3 `verify_phase2.sh` output (API 525 passed, 1 skipped; browser 16 passed) | Section 2 |
| `docs/phase4/reports/q3/focused-tests.log` | New | Focused Q1/Q2/Q3 test output (62 passed) | Section 6–7 |
| `docs/phase4/reports/q3/mutation-proof.log` | New | Full log of all 4 mutation proofs + pre/post-restore SHA256 hashes | Section 5, 7 |
| `docs/phase4/reports/q3/final-gate.log` | New | Full post-Q3 `verify_phase2.sh` output (API 549 passed, 1 skipped; browser 16 passed) | Section 6–7 |
| `docs/phase4/reports/q3/git-status-after.txt` | New | Postflight `git status --short` snapshot | Section 7 |
| `docs/phase4/reports/q3/hashes-after.txt` | New | Postflight SHA256 manifest (written to temp first, moved in after scan) | Section 7 |
| `docs/phase4/reports/q3/changed-files.txt` | New | `diff hashes-before.txt hashes-after.txt` confirming exact allowlist adherence | Section 7 |

---

## 3. Computation

Both institutional allocation (`allocated_for_month`) and personal additive lookup (`compute_user_entitlements`) live in `apps/api/src/aq_uai_api/qta/entitlements.py` and execute live SQL against PostgreSQL without per-user Python loops (`PD-Q1`, `PD-Q5`).

### 3.1 Institutional allocation (`allocated_for_month`)

```sql
SELECT COALESCE(SUM(q.monthly_limit), 0)
FROM group_memberships AS gm
JOIN users AS u
  ON u.id = gm.user_id AND u.institution_id = gm.institution_id
JOIN qta_quota_groups AS reg
  ON reg.group_id = gm.group_id AND reg.institution_id = gm.institution_id
JOIN account_groups AS g
  ON g.id = reg.group_id AND g.institution_id = reg.institution_id AND g.kind = reg.group_kind
JOIN qta_group_model_quotas AS q
  ON q.group_id = reg.group_id AND q.institution_id = reg.institution_id
JOIN mdl_models AS m
  ON m.id = q.model_id AND m.institution_id = q.institution_id
WHERE gm.institution_id = :institution_id
  AND gm.active IS TRUE
  AND u.state = 'ACTIVE'
  AND reg.in_directory IS TRUE
  AND g.active IS TRUE
  AND q.enabled IS TRUE
  AND m.active IS TRUE;
```

**In plain words:** Starting from every active user–group membership in the institution, PostgreSQL keeps only rows where the user is `ACTIVE`, the group is enrolled in QTA (`qta_quota_groups`), still present in the directory (`in_directory = true`), and currently active (`account_groups.active = true`), and the group has an enabled quota rule for an active MDL model. Because `(group_id, user_id)` is unique in `group_memberships` and `(institution_id, group_id, model_id)` is unique in `qta_group_model_quotas`, each surviving row represents exactly one `(user, group, model)` entitlement piece with zero fan-out. Summing `monthly_limit` in one SQL aggregate yields the exact unweighted total across all active users and active models in `"đơn vị hạn mức"`. Phase 5 CRT net grants will join through this same function.

### 3.2 Per-user lookup (`compute_user_entitlements`)

1. **Membership visibility query:** Reads every active `group_memberships` row for `user_id` in `SYSTEM` or `AI_SPECIALIST` groups (`LEFT OUTER JOIN qta_quota_groups`) so both qualifying and non-qualifying memberships are returned transparently with `qualifies` and `excluded_reason` (`USER_NOT_ACTIVE` → `NOT_ENROLLED` → `RETIRED` → `GROUP_INACTIVE` → `null`). Inactive memberships and `AUTHORIZATION` groups are excluded.
2. **Active model list:** Reads all active `mdl_models` joined to `mdl_providers` for the institution.
3. **Per-model additive SQL aggregate:** Runs the **exact same 6-table join and `WHERE` predicates** as `allocated_for_month`, narrowed by `gm.user_id = :user_id` and grouped by `q.model_id`:
   ```sql
   SELECT q.model_id, COALESCE(SUM(q.monthly_limit), 0)
   FROM group_memberships AS gm
   JOIN users AS u ...
   JOIN qta_quota_groups AS reg ...
   JOIN account_groups AS g ...
   JOIN qta_group_model_quotas AS q ...
   JOIN mdl_models AS m ...
   WHERE gm.institution_id = :institution_id
     AND gm.user_id = :user_id
     AND gm.active IS TRUE AND u.state = 'ACTIVE'
     AND reg.in_directory IS TRUE AND g.active IS TRUE
     AND q.enabled IS TRUE AND m.active IS TRUE
   GROUP BY q.model_id;
   ```
4. **Per-group contributions query:** Loads `(qta_group_model_quotas, account_groups, qta_quota_groups)` for qualifying groups and active models so each model row displays the exact contributing breakdown (`enabled`, `monthly_limit`, `contributes`), while `actual_consumption` and `remaining_quota` are fixed to `null` with `consumption_status = "NOT_INTEGRATED"`.

### 3.3 Consistency proof

`test_allocated_equals_sum_of_user_entitlements` builds an institution with overlapping `SYSTEM` + `AI_SPECIALIST` memberships, two units, a `DISABLED` user (`sum3dis`), and a disabled model quota (`M2` on `G_SUM`), fetches every user's `base_entitlement_total` through `GET /api/v1/qta/users/{id}/entitlements`, sums them (`3,700`), and asserts exact equality with both `GET /api/v1/qta/budgets["allocated"]` and direct `entitlements.allocated_for_month(session, tenant)`. Mutation proof #4 confirms that removing `User.state == "ACTIVE"` from `allocated_for_month` immediately breaks this invariant (`4,900 != 3,700`).

---

## 4. API

All routes live under `/api/v1/qta` with `Cache-Control: no-store`.

| Method & Path | Permission / Scope | Status codes | Error codes | Audit action |
| --- | --- | --- | --- | --- |
| `GET /api/v1/qta/users` | `qta.read` (GLOBAL or exact-UNIT) | `200`, `401`, `403`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `VALIDATION_FAILED` | *(read)* |
| `GET /api/v1/qta/users/{user_id}/entitlements?month=YYYY-MM` | `qta.read` (GLOBAL or exact-UNIT) | `200`, `401`, `403`, `404`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `QTA_INVALID_PERIOD`, `QTA_PERIOD_NOT_OPEN`, `VALIDATION_FAILED` | *(read)* |
| `GET /api/v1/qta/budgets?month=YYYY-MM` | `qta.read` (GLOBAL only; UNIT → `403`) | `200`, `401`, `403`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `QTA_INVALID_PERIOD`, `VALIDATION_FAILED` | *(read)* |
| `PUT /api/v1/qta/budgets/{month}` | `qta.manage` (direct GLOBAL only + session/Origin/CSRF) | `200`, `401`, `403`, `409`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `QTA_BUDGET_BELOW_ALLOCATED` (`{allocated, deficit}`), `CONFLICT`, `QTA_INVALID_PERIOD`, `QTA_PERIOD_NOT_OPEN`, `VALIDATION_FAILED` | `qta.monthly_budget_set` (`BudgetRevisionRecorded`) |

### Example response: `GET /api/v1/qta/users/{alice_id}/entitlements?month=2026-11` *(synthetic test data)*

```json
{
  "user": {
    "id": "11111111-1111-4111-8111-111111111111",
    "username": "alice",
    "display_name": "Alice",
    "state": "ACTIVE"
  },
  "month": "2026-11",
  "unit_label": "đơn vị hạn mức",
  "memberships": [
    {
      "group_id": "22222222-2222-4222-8222-222222222222",
      "code": "AI_LAB",
      "name": "AI Lab",
      "kind": "AI_SPECIALIST",
      "origin": "SPECIALIST",
      "active": true,
      "in_directory": true,
      "qualifies": true,
      "excluded_reason": null
    },
    {
      "group_id": "33333333-3333-4333-8333-333333333333",
      "code": "G_GV",
      "name": "Giảng viên",
      "kind": "SYSTEM",
      "origin": "SYNC",
      "active": true,
      "in_directory": true,
      "qualifies": true,
      "excluded_reason": null
    }
  ],
  "models": [
    {
      "model_id": "44444444-4444-4444-8444-444444444444",
      "display_name": "M1",
      "technical_id": "m1-tech",
      "provider_type": "EXTERNAL",
      "base_entitlement": 4000,
      "contributions": [
        {
          "group_id": "22222222-2222-4222-8222-222222222222",
          "code": "AI_LAB",
          "name": "AI Lab",
          "kind": "AI_SPECIALIST",
          "origin": "SPECIALIST",
          "enabled": true,
          "monthly_limit": 3000,
          "contributes": 3000
        },
        {
          "group_id": "33333333-3333-4333-8333-333333333333",
          "code": "G_GV",
          "name": "Giảng viên",
          "kind": "SYSTEM",
          "origin": "SYNC",
          "enabled": true,
          "monthly_limit": 1000,
          "contributes": 1000
        }
      ],
      "actual_consumption": null,
      "remaining_quota": null,
      "consumption_status": "NOT_INTEGRATED"
    }
  ],
  "base_entitlement_total": 6000
}
```

### Example response: `GET /api/v1/qta/budgets?month=2026-11` *(synthetic test data)*

```json
{
  "month": "2026-11",
  "unit_label": "đơn vị hạn mức",
  "status": "RECORDED",
  "status_label": "Đã ghi nhận",
  "current": {
    "id": "55555555-5555-4555-8555-555555555555",
    "revision": 2,
    "total_limit": 7500,
    "decision_number": "QD-02",
    "decision_date": "2026-11-10",
    "recorded_by": "66666666-6666-4666-8666-666666666666",
    "recorded_at": "2026-11-27T11:00:00+07:00"
  },
  "revisions": [
    {
      "id": "55555555-5555-4555-8555-555555555555",
      "revision": 2,
      "total_limit": 7500,
      "decision_number": "QD-02",
      "decision_date": "2026-11-10",
      "recorded_by": "66666666-6666-4666-8666-666666666666",
      "recorded_at": "2026-11-27T11:00:00+07:00"
    },
    {
      "id": "77777777-7777-4777-8777-777777777777",
      "revision": 1,
      "total_limit": 10000,
      "decision_number": "QD-01",
      "decision_date": "2026-11-01",
      "recorded_by": "66666666-6666-4666-8666-666666666666",
      "recorded_at": "2026-11-27T10:59:00+07:00"
    }
  ],
  "allocation_status": "LIVE",
  "allocated": 6000,
  "remaining": 1500,
  "over_allocated": 0
}
```

---

## 5. Tests

### 5.1 New unit tests (`apps/api/tests/unit/test_q3_entitlements.py` — 4 tests)

| Test name | What it proves (FR / AC / Rule) |
| --- | --- |
| `test_parse_month_accepts_only_calendar_months` | Strict `YYYY-MM` acceptance and `QTA_INVALID_PERIOD` on malformed / non-month strings (`FR-QTA-010`, `RULE-QTA-01`) |
| `test_open_window_current_and_next_month_in_institution_timezone` | Frozen `utc_now()` boundary (`2026-11-30T17:30Z` = `2026-12-01` in `Asia/Ho_Chi_Minh`), Dec → Jan 2027 rollover, `QTA_PERIOD_NOT_OPEN` outside current/next (R2, QD2) |
| `test_settings_reject_invalid_timezone` | `Settings.institution_timezone` defaults to `Asia/Ho_Chi_Minh` and rejects invalid/blank/padded IANA names at load time |
| `test_q3_openapi_routes_and_month_only_inputs` | Exact Q3 routes, zero `PATCH`/`DELETE` on budgets, zero cycle/semester/period/price/token/credit/consumption inputs, strict `SetMonthlyBudget` & `MonthQuery` validation (`FR-QTA-010 AC3`, `FR-QTA-050`, R3) |

### 5.2 New integration tests (`apps/api/tests/integration/test_q3_qta_lookup_budgets.py` — 20 PostgreSQL tests)

| Test name | What it proves (FR / AC / Rule) |
| --- | --- |
| `test_architecture_numerical_example` | Reproduces every row of architecture §2.1: Alice `M1=4000`, `M2=2000`; Bob `3000`; Carol `0`; allocated `9000`; rev 1 `10000` (`remaining=1000`); `7500` → `409 {allocated: 9000, deficit: 1500}`; deactivate `AI_LAB` → allocated `6000`; `7500` succeeds as rev 2 (`remaining=1500`) with rev 1 preserved |
| `test_additive_not_max_1000_plus_3000` | `1000 + 3000 = 4000` additive stacking and per-group contribution list (`FR-QTA-030 AC1, AC2`, `RULE-QTA-02`) |
| `test_no_group_user_has_zero_base` | User in zero groups gets `0` base entitlement across all active models (`FR-QTA-031 AC2`) |
| `test_disabling_model_quota_removes_base_for_single_group_user` | Setting `enabled=false` immediately drops single-group member's base to `0` (`FR-QTA-021 AC2`, `PD-Q5`) |
| `test_specialist_member_appears_in_additive_lookup` | `AI_SPECIALIST` member appears in lookup with that group's quota (`FR-QTA-022 AC2`) |
| `test_exclusions` | Retired `SYSTEM` (`RETIRED`), inactive group (`GROUP_INACTIVE`), unenrolled group (`NOT_ENROLLED`), inactive membership (excluded), inactive MDL model, disabled quota, zero limit, and `PENDING` user (`USER_NOT_ACTIVE`) all contribute `0` |
| `test_consumption_is_null_not_integrated` | `actual_consumption` and `remaining_quota` are always `null` (never `0`) with `consumption_status == "NOT_INTEGRATED"` (QD10) |
| `test_allocated_equals_sum_of_user_entitlements` | Single-SQL `allocated_for_month` matches the exact sum of every user's `base_entitlement_total` |
| `test_lookup_scope` | UNIT `AI_QUOTA_VIEWER` sees only own-unit users, gets `404` on other units, and `403` on `/qta/budgets`; GLOBAL viewer sees all; `FOUNDATION_ADMIN`/`AI_MODEL_ADMIN` `403`; anonymous `401` (`FR-QTA-001`) |
| `test_budget_revisions_append_only` | Revisions 1, 2, 3 append newest-first, row 1 DB columns stay byte-identical, `BudgetRevisionRecorded` records `before_limit` & `before_decision_number` (`INV-18`, `RULE-QTA-04`) |
| `test_budget_requires_decision_number_and_date` | Missing/blank `decision_number` or `decision_date` → `422`, zero rows written (`FR-QTA-010 AC2`, `PD-Q4`) |
| `test_budget_month_window` | Frozen clock (`2026-11`, `2026-12` open): past/far-future → `QTA_PERIOD_NOT_OPEN`, malformed → `QTA_INVALID_PERIOD` (R1, R2) |
| `test_unrecorded_month_shows_chua_ghi_nhan_while_quotas_apply` | Unrecorded open month returns `status="NOT_RECORDED"`, `status_label="chưa ghi nhận"`, `allocated` live, `remaining/over_allocated` null, while group quotas still apply (F8) |
| `test_past_month_read_is_not_snapshotted` | Past month returns revision history with `allocation_status="NOT_SNAPSHOTTED"` and `allocated/remaining/over_allocated` null (R1) |
| `test_equal_to_allocated_is_allowed_and_below_is_409_with_details` | `total_limit == allocated` succeeds (`remaining=0`); `allocated - 1` fails `409 QTA_BUDGET_BELOW_ALLOCATED` with `{allocated, deficit: 1}` (`FR-QTA-011`) |
| `test_over_allocation_is_a_warning_not_a_block` | Raising group quotas and adding members above cap succeeds (never blocked) and surfaces `over_allocated > 0` (`PD-Q1`) |
| `test_budget_rbac_and_csrf` | Anonymous `401`, non-`qta.manage` roles `403`, missing CSRF `403`, wrong Origin `403` (`FR-QTA-001`) |
| `test_tenant_isolation` | Another institution's users and budget revisions are invisible (`404` on entitlements, absent from listings/budgets) |
| `test_budget_audit_failure_rolls_back` | Revoking `INSERT` on `audit_events` returns `500 DATABASE_ERROR` and commits zero `qta_budget_revisions` rows |
| `test_concurrent_budget_writes_serialize` | Two synchronized threads calling `PUT /qta/budgets/2026-11` produce revisions `1` and `2` with zero `500`s (`QTA_BUDGET_NAMESPACE`) |

### 5.3 Edited existing tests (strictly within Section 3 allowlist)

| File | Lines | Before | After | Why |
| --- | --- | --- | --- | --- |
| `apps/api/tests/unit/test_q1_contracts.py` | 20–30 | `QTA_CODES` ended at `"QTA_DUPLICATE"` (8 codes) | Appended `"QTA_PERIOD_NOT_OPEN"` (9 codes) | Mirrors the new `QTA_PERIOD_NOT_OPEN` error code appended to `ErrorCode` per R2 |
| `apps/api/tests/unit/test_q2_contracts.py` | 100–118 | Pinned 10 Q2 `/api/v1/qta` paths | Added the 4 new Q3 paths (`/qta/users`, `/qta/users/{user_id}/entitlements`, `/qta/budgets`, `/qta/budgets/{month}`) | Route inventory pin updated for Stage Q3 |
| `apps/api/tests/unit/test_q2_contracts.py` | 121–155 | Checked `FORBIDDEN_FIELD` uniformly against all QTA schemas | Kept `FORBIDDEN_FIELD` regex unchanged and all request bodies/query/path parameters 100% strict; allowed only the two exact output properties `actual_consumption` and `consumption_status` on `Output` subclasses | Implements reviewer decision R4 so architecture §2.3 `NOT_INTEGRATED` response fields pass without relaxing input checks |

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
| **Focused Q1/Q2/Q3 tests (`focused-tests.log`)** | — | **62 passed** in 282.85s | 28 unit + 34 PostgreSQL integration |
| **Full API suite (`apps/api/tests`)** | **525 passed, 1 skipped** (545.60s) | **549 passed, 1 skipped** (633.79s) | **+24 passed** (opt-in live provider stays skipped) |
| **Browser suite (`tests/browser`)** | **16 passed** (214.19s) | **16 passed** (198.67s) | Unchanged (no UI in Q3; zero flakes observed) |

Evidence log paths:
- Preflight baseline gate: `docs/phase4/reports/q3/baseline-gate.log`
- Focused tests: `docs/phase4/reports/q3/focused-tests.log`
- Mutation proofs: `docs/phase4/reports/q3/mutation-proof.log`
- Final full gate: `docs/phase4/reports/q3/final-gate.log`
- File manifests: `docs/phase4/reports/q3/git-status-before.txt`, `git-status-after.txt`, `hashes-before.txt`, `hashes-after.txt`, `changed-files.txt`

---

## 7. Mutation proof

Full log in [`docs/phase4/reports/q3/mutation-proof.log`](q3/mutation-proof.log).

| # | Rule | How temporarily broken | Failing test & observed failure | Restored & verified |
| --- | --- | --- | --- | --- |
| 1 | Additive `SUM` (never `MAX`) in entitlement aggregate (`RULE-QTA-02`) | Replaced `sa.func.sum(QtaGroupModelQuota.monthly_limit)` with `sa.func.max(...)` in `qta/entitlements.py::compute_user_entitlements` | `test_additive_not_max_1000_plus_3000` FAILED (`assert 3000 == 4000`, exit 1) | Restored byte-identically; PASSED (10.23s) |
| 2 | `total_limit < allocated` budget guard (`FR-QTA-011`) | Replaced `if payload.total_limit < allocated: raise ...` in `qta/service.py::record_budget_revision` with `pass` | `test_equal_to_allocated_is_allowed_and_below_is_409_with_details` FAILED (`assert 200 == 409`, exit 1) | Restored byte-identically; PASSED (12.21s) |
| 3 | `UNIT` scope predicate in user lookup (`FR-QTA-001`) | Replaced `scope.predicate(User.institution_id, User.primary_unit_id)` with `User.institution_id == authority.institution_id` in `qta/queries.py::_scoped_user_query` | `test_lookup_scope` FAILED (`assert user_b["id"] not in unit_ids`, exit 1) | Restored byte-identically; PASSED (8.43s) |
| 4 | Inactive-user exclusion in `allocated_for_month` (`PD-Q1`) | Removed `User.state == "ACTIVE"` from `qta/entitlements.py::allocated_for_month` | `test_allocated_equals_sum_of_user_entitlements` FAILED (`assert 4900 == 3700`, exit 1) | Restored byte-identically; PASSED (10.81s) |

Pre-mutation and post-restore SHA256 hashes match byte-for-byte:
- `apps/api/src/aq_uai_api/qta/entitlements.py`: `f06a2c38a755811448ae105357bbe5c213b62d3eeabfadd99183a878fa848b52`
- `apps/api/src/aq_uai_api/qta/service.py`: `859b3d56edbad903365c418386557326347755b9e46968556d9e45a47fe4c6b2`
- `apps/api/src/aq_uai_api/qta/queries.py`: `d4ed2ff29e2849077a7e8ac7b51d54dac09a6bc77af7f97913b97db7e20c3826`

---

## 8. Decisions and deviations

- **Reviewer decisions R1–R4 applied verbatim:**
  - **R1:** Past (and any non-open) months on `GET /qta/budgets` return revision history with `allocated: null`, `remaining: null`, `over_allocated: null`, and `allocation_status: "NOT_SNAPSHOTTED"`. `GET /qta/users/{id}/entitlements` accepts only open months (current or next).
  - **R2:** Appended `QTA_PERIOD_NOT_OPEN` (422) for well-formed months outside the open window, distinct from `QTA_INVALID_PERIOD` (422) for malformed or non-month strings.
  - **R3:** Named the API field/parameter `month` (`"YYYY-MM"`) everywhere in QTA schemas and routes (never `period_month`).
  - **R4:** Narrowed `test_q2_contracts.py` output-schema check strictly to allow `actual_consumption` and `consumption_status` on `Output` subclasses while keeping `FORBIDDEN_FIELD` regex and all request/parameter checks unchanged.
- **Minor implementation choices within spec (no deviations):**
  - `excluded_reason` precedence in `compute_user_entitlements` is `USER_NOT_ACTIVE` → `NOT_ENROLLED` → `RETIRED` → `GROUP_INACTIVE` → `None`, which cleanly distinguishes a deactivated-and-synced `SYSTEM` group (`RETIRED`, `in_directory=false`) from a deactivated `AI_SPECIALIST` group (`GROUP_INACTIVE`, `in_directory=true, active=false`).
  - `SetMonthlyBudget.decision_date` uses `StrictCalendarDate` rejecting booleans, integers, and datetimes so only pure ISO calendar dates (`YYYY-MM-DD`) are accepted.
  - Far-future months beyond `next_month` on `GET /qta/budgets` also return `allocation_status: "NOT_SNAPSHOTTED"` (consistent with R1: only open months compute live allocation).

---

## 9. Open questions, risks & unverified items

- **Project Owner commit during run:** While Q3 was finishing, the Project Owner committed `c10c801a7be0116572aa59fb157a2a433f251de4` (`ci: add automated AI context snapshot workflow`, `2026-11-27 11:18:21 +0700`), adding `.github/workflows/context-snapshot.yml`. Consequently, `.github/workflows/context-snapshot.yml` appears in `docs/phase4/reports/q3/changed-files.txt` (between `hashes-before.txt` and `hashes-after.txt`) even though it is clean in `git-status-after.txt` and untouched by Q3. Per Section 7, the hash manifests remain authoritative and unmodified.
- **Not verified in Q3:** hosted GitHub Actions CI (workflow pinned to `ubuntu-24.04` in Q2 review, not yet observed on GitHub); live Docker Compose deployment against the developer's persistent `aq-uai-dev` stack (intentionally untouched); opt-in live external AI provider check (`1 skipped`).
- **Remaining stages:** Q4 (kill-switch/restore + `check_ai_access` + monthly reset CLI & API), Q5 (`#qta` Admin UI), and Q6 (cross-module MDL isolation proof, backup/restore rehearsal & handoff) await separate authorization.

---

## 10. Implementer's review of the plan and this prompt *(discussion, not decisions)*

Below are six concrete engineering observations and proposals for the Project Owner and reviewer to consider before authoring Q4–Q6 prompts. None of these altered Q3 behavior.

1. **Raw-JSON forbidden-word regex (`period`, `consumption`) is outliving its usefulness vs. targeted name checks**
   - *Reason:* Scanning `json.dumps(schema)` for `period|semester|cycle|price|token|credit|consumption` catches accidental slips cheaply, but it also scans Pydantic's exported OpenAPI `"description"` strings (class docstrings) and collides with legitimate domain words (`period_month` in DB/audit vs `month` in API per R3; `actual_consumption`/`consumption_status` per R4; `QTA_INVALID_PERIOD`/`QTA_PERIOD_NOT_OPEN`). In Q4 (`qta_events`, `qta_monthly_resets`) and especially Phase 5 CRT (which literally has a credits ledger), this regex will require further ad-hoc exemptions.
   - *Trade-off:* Keeping the broad regex gives a loud tripwire, at the cost of API/DB naming drift (`month` vs `period_month`) and fragile docstring constraints.
   - *Recommendation:* Keep strict scanning on **parameter and property names only** (ignoring prose `description`), drop the generic word `period` from the QTA regex, and keep the genuinely forbidden cycle/financial words (`semester|hoc_ky|project|de_tai|exam|dot_thi|cycle|price|cost|rate|conver|token|credit`).

2. **`allocated_for_month` signature for Phase 5 CRT readiness**
   - *Reason:* In Q3, `allocated_for_month(db, institution_id)` takes no `period_month` argument because group base quotas are live and timeless. In Phase 5 CRT, however, ad-hoc grants are strictly scoped to one `period_month` (`FR-QTA-032` zero rollover: November grants must NOT count toward December's `allocated`). Changing `allocated_for_month` to accept `period_month: date` later will touch callers and tests across Q3 + CRT.
   - *Trade-off:* Passing an unused `period_month` in Q3 would look redundant today, whereas adding it in Phase 5 is a small refactor.
   - *Recommendation:* Keep Q3 as built; when opening Phase 5 CRT, extend `allocated_for_month(db, institution_id, period_month: date)` so CRT net grants filter cleanly by `period_month`.

3. **Explicit `check_ai_access` reason precedence & `UserEntitlementsOut` shape for Q4**
   - *Reason:* Q4 adds kill-switch/restore (`FR-QTA-040`, `FR-QTA-041`) and extends `GET /qta/users/{id}/entitlements` with active suspension status and per-model access evaluation. Ambiguities will arise immediately in Q4 if not specified upfront: what should `check_ai_access(db, institution_id, user_id, model_id)` return when `User.state != 'ACTIVE'`, `MdlModel.active == False`, `base_entitlement == 0`, or an active `PAID_EXTERNAL_ONLY` suspension applies?
   - *Trade-off:* Over-coupling `check_ai_access` to quota-zero checks might surprise callers that only want suspension enforcement, whereas ignoring `User.state`/`MdlModel.active` risks unsafe fail-open decisions if a gateway calls it directly.
   - *Recommendation:* In `QTA_Q4_PROMPT.md`, define an explicit ordered decision table for `check_ai_access` (e.g., `USER_NOT_ACTIVE` → `MODEL_INACTIVE` → `SUSPENDED_ALL_MODELS` / `SUSPENDED_PAID_EXTERNAL` → `NO_QUOTA_ENTITLEMENT` → `ALLOWED`) and pin the exact `suspension` + per-model `access_status` / `blocked_reason` fields on `UserEntitlementsOut` so Q5 UI consumes a stable contract.

4. **Q4 `POST /qta/monthly-resets` manual simulation UX when already executed for the current month**
   - *Reason:* Under `PD-Q6`, manual simulation is restricted to the current month and enforced by `UNIQUE(institution_id, period_month)` (`409 QTA_RESET_ALREADY_EXECUTED` on repeat). That cleanly prevents colliding with next month's real `00:00` day-1 scheduled run. However, in an interactive demo/evaluation, once the evaluator clicks "Simulate monthly reset" once for the current month, clicking it again returns `409`, and they cannot demonstrate a second reset without advancing time or seeding a fresh database.
   - *Trade-off:* Allowing duplicate resets in the same month would break idempotency (`QD8`). Keeping strict uniqueness is structurally sound, so the UI (Q5) should clearly show the current month's `COMPLETED` status, disable the button with an explanation (*"Đã thực hiện làm mới cho tháng MM/YYYY"*), and display the recorded `MONTHLY_REFRESH` row right below it.
   - *Recommendation:* Keep `PD-Q6` and `UNIQUE(institution_id, period_month)` unchanged, and include that explicit disabled/completed UI state in the Q5 prompt and `test_qta.py`.

5. **Verification gate runtime (~19 min for preflight + final) and the `test_operations.py` parallel startup flake**
   - *Reason:* Running `scripts/verify_phase2.sh` twice per stage (`baseline-gate.log` + `final-gate.log`) takes ~18–20 minutes on this machine (API 549 tests ~10.5 min + Browser 16 tests ~3.3 min running concurrently on one PostgreSQL cluster). As observed during Q2 review Run 1, parallel CPU contention occasionally causes `test_backup_restores_history_and_runtime_writes` to time out waiting for restored API boot.
   - *Trade-off:* Running API and browser tests sequentially in `verify_phase2.sh` adds ~3 min on idle hardware, while eliminating startup-timeout flakes under load. Skipping a redundant preflight full gate when `hashes-before.txt` matches the last verified commit's `hashes-after.txt` saves ~10 min without losing integrity.
   - *Recommendation:* Keep full `final-gate.log` mandatory on every stage. Consider allowing a fast preflight check (git/hash verification + `alembic check`) when starting from a freshly gated commit, and in Q6 (or a small infra ticket) increase the restored-API startup wait or serialize the browser suite in `verify_phase2.sh`.

6. **Minor audit payload symmetry (`GroupQuotaUpdated.before_warning_threshold_pct`)**
   - *Reason:* Echoing the Q2 review note, `BudgetRevisionRecorded` captures both before/after limit and decision number, while `GroupQuotaUpdated` records `warning_threshold_pct` without a `before_warning_threshold_pct` field.
   - *Trade-off:* Adding an optional `before_warning_threshold_pct: int | None = None` field to `GroupQuotaUpdated` in Q4/Q5 is backwards-compatible with existing audit rows via `public_audit_changes` and gives complete diff fidelity in `#audit` / QTA history.
   - *Recommendation:* Add `before_warning_threshold_pct: int | None = None` the next time `db/audit.py` is in the allowlist (Q4 or Q6).

---

## 11. Reviewer response (Claude Code, 2026-11-27)

**Verdict: Q3 approved for continued development.** This is not formal FRD acceptance.

**Independent verification**
- The current tree matches `hashes-after.txt`. Every entry in `changed-files.txt` is in the §3 allowlist. The only exception is `.github/workflows/context-snapshot.yml`, which came from the Project Owner's commit `c10c801`, as §9 states.
- My own `scripts/verify_phase2.sh` run gave **API 549 passed, 1 skipped; browser 16 passed; exit 0**. This is identical to `final-gate.log`.
- Hosted CI passed on GitHub (`d01e75e`, `c10c801`). This is the first green hosted run, and it confirms the `ubuntu-24.04` pin.
- Code read in full:
  - `periods.py` and `entitlements.py`.
  - The Q3 diffs in `service.py` and `queries.py`.
  - The `config.py` and `errors.py` diffs.
- Correct:
  - Strict month regex.
  - Timezone validation.
  - The budget advisory lock is taken before `max(revision)` and `allocated` are read.
  - Same-transaction audit.
  - UNIT scope applied through `ScopeGrant.predicate`.
  - Past months return `NOT_SNAPSHOTTED`.

**Findings (carried into Q4 as corrections, see `QTA_Q4_PROMPT.md` §4.0)**
- **F-Q3-1 (real defect, C1):** QTA treats `mdl_models.active` as "usable" but ignores `mdl_providers.active`. `mdl.service.set_provider_active` deactivates a provider without touching its models. As a result, a deactivated provider's models still appear in `/qta/models`, still accept quotas, and still count in `allocated` and the lookup. The fix is one usable-model predicate used everywhere (R6).
- **F-Q3-2 (maintainability, C2):** the qualifying 6-table join and WHERE clause are duplicated between the per-user aggregate and `allocated_for_month`. The consistency test catches divergence today, but the rule should exist once.
- **F-Q2-nit (C3):** `GroupQuotaUpdated` has no `before_warning_threshold_pct`.

**Response to §10 (implementer's review)**
1. Forbidden-word regex: **deferred as an open question** (Q-e in the Q4 prompt). Q3 worked within it. The Q4 implementer must propose the exact replacement rule before anyone changes the test.
2. `allocated_for_month(period_month)` for CRT: **agreed, deferred to Phase 5.** No dead parameter now.
3. Explicit `check_ai_access` decision table and pinned response fields: **accepted** as R5/R9 and Q4 §4.3–4.4.
4. Reset button UX once a month is completed: **accepted for Q5.** The API in Q4 exposes `current.status` (`COMPLETED`/`PENDING`).
5. Gate runtime and browser flake: **partly accepted.** C4 replaces the ~10 s startup poll with a 30 s deadline. The full preflight gate stays mandatory, because integrity outweighs the extra ~10 minutes.
6. Audit threshold symmetry: **accepted** as C3.
