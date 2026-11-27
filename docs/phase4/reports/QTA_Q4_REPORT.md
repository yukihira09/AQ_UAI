# QTA Stage Q4 completion report & whole-module review (Phase 4 · Module 2)

## 1. Summary

- **Status:** **implemented, awaiting review** (not formally accepted).
- Delivered carry-over fixes **C1–C4** (`usable_model_predicate` requiring `mdl_models.active AND mdl_providers.active` everywhere; single `_qualifying_quota_rows` selectable; `GroupQuotaUpdated.before_warning_threshold_pct`; 30s monotonic `wait_for_http` deadline) and **Stage Q4** under `/api/v1/qta`: individual kill-switch & restore (`POST /users/{id}/suspensions`, `POST /users/{id}/restore`, `GET /users/{id}/suspensions`), fail-closed `check_ai_access` (`R5`/`R9`), append-only QTA events (`GET /events`), and monthly resets (`GET/POST /monthly-resets` + `python -m aq_uai_api.qta.reset` CLI).
- Preserved honest non-integrated consumption (`actual_consumption: null`, `remaining_quota: null`, `consumption_status: "NOT_INTEGRATED"`), `"đơn vị hạn mức"` wording (`PD-Q1`), lazy expiry (`PD-Q3`), current-month-only manual reset (`PD-Q6`), and append-only ledger markers (`R7`/`R8`) with zero fabricated balances, prices, or conversions.
- Verified via **29 new automated tests** (`test_q4_access_reset.py` 5 unit + `test_q4_carryover.py` 3 integration + `test_q4_qta_killswitch_reset.py` 21 integration), two-run `aq_uai_runtime` CLI smoke (`recorded=1 already=0` → `recorded=0 already=1`), **5 required mutation proofs** with byte-identical post-restore SHA256 hashes, and the full `scripts/verify_phase2.sh` gate (**API 578 passed, 1 skipped; browser 16 passed**).
- Conducted an independent whole-module review of **QTA Q0–Q4** end to end (§10), answering `Q-a..Q-f` and proposing prioritized refinements before Q5/Q6 and Phase 5 CRT.

---

## 2. Files

Every created or modified file under `apps`, `tests`, `scripts`, `infra`, `docs`, and `.github` between `hashes-before.txt` and `hashes-after.txt` matches [`docs/phase4/reports/q4/changed-files.txt`](q4/changed-files.txt) (`CLAUDE.md` is at the repository root outside the `find` roots, inside the Section 3 allowlist). `docs/phase4/reports/QTA_Q3_REPORT.md` appears in `changed-files.txt` because the reviewer appended §11 (*Reviewer response*) to it after `hashes-before.txt` was captured (untouched by this Q4 agent; inside `docs/phase4/reports/**`). One existing test file — `apps/api/tests/integration/test_q3_qta_lookup_budgets.py` — was explicitly authorized as an allowlist amendment by the Project Owner during the run (see §6 & §8). **Confirming per Condition 5: no other file outside the Section 3 allowlist was modified.**

| Path | Status | Why | FR / Finding |
| --- | --- | --- | --- |
| `apps/api/src/aq_uai_api/qta/access.py` | New | `QTA_SUSPENSION_NAMESPACE = 52002`, lazy-expiry `suspension_status` / `suspension_out`, set-based `active_suspensions_for` (zero N+1), single ordered `evaluate_access_rule` & `check_ai_access` | `FR-QTA-031/040/041`, `RULE-QTA-03`, `PD-Q2/PD-Q3`, `R5/R6/R9` |
| `apps/api/src/aq_uai_api/qta/reset.py` | New | `QTA_RESET_NAMESPACE = 52003`, append-only `record_reset`, `run_scheduled_resets` (current month only, 1 tx per institution), and `python -m aq_uai_api.qta.reset` CLI | `FR-QTA-032`, `RULE-QTA-01/04`, `PD-Q6`, `R7/R8` |
| `apps/api/src/aq_uai_api/qta/entitlements.py` | Modified | Added `usable_model_predicate()` & `usable_models_query()` (C1), extracted single `_qualifying_quota_rows()` selectable & `user_model_base_entitlement()` (C2), attached `quota_status`, active `suspension`, and per-model `access` to `compute_user_entitlements` | C1, C2, `R5/R6`, `FR-QTA-030/031` |
| `apps/api/src/aq_uai_api/qta/schemas.py` | Modified | Added strict `extra="forbid"` Q4 inputs (`SuspendUser`, `RestoreUser`, `QtaEventFilters`) and projections (`SuspensionOut`, `ModelAccessOut`, `QtaEventOut`, `MonthlyResetsOut`, plus `quota_status`/`suspension`/`access` on lookup outputs) | `FR-QTA-031/032/040/041/050`, `PD-Q2/PD-Q3`, `R5/R9` |
| `apps/api/src/aq_uai_api/qta/queries.py` | Modified | Applied `usable_models_query` / `usable_model_predicate` in `models()` & `_quotas_by_group()` (C1); added batch `quota_status` in `users()` (zero N+1); updated `user_entitlements()`; added `user_suspensions()`, `events()`, `monthly_resets()` | C1, `FR-QTA-001/031/032/040/041/050` |
| `apps/api/src/aq_uai_api/qta/service.py` | Modified | Applied `usable_model_predicate` (C1) and `before_warning_threshold_pct` (C3) in `upsert_group_quotas`; added `suspend_user()`, `restore_user()`, and `simulate_monthly_reset()` | C1, C3, `FR-QTA-032/040/041`, `INV-17/18`, `PD-Q2/PD-Q3/PD-Q6` |
| `apps/api/src/aq_uai_api/api/v1/qta.py` | Modified | Registered `GET/POST /qta/users/{user_id}/suspensions`, `POST /qta/users/{user_id}/restore`, `GET /qta/events`, `GET/POST /qta/monthly-resets` | `FR-QTA-032/040/041/050` |
| `apps/api/src/aq_uai_api/db/audit.py` | Modified | Added optional `before_warning_threshold_pct: int \| None = None` to `GroupQuotaUpdated` (C3 only) | C3 |
| `tests/browser/conftest.py` | Modified | Replaced `100 × 0.1 s` loop bound in `wait_for_http` with a `30.0 s` monotonic deadline (C4 only) | C4 |
| `apps/api/tests/unit/test_q2_contracts.py` | Modified | Added the 4 new Q4 paths to pinned `/api/v1/qta` OpenAPI route inventory (lines 115–120) | Allowlist §3 |
| `apps/api/tests/integration/test_q3_qta_lookup_budgets.py` | Modified | Added `"quota_status"` (7 keys total) + `assert unit_users[0]["quota_status"] == "ACTIVE"` in `test_lookup_scope` (lines 450–460) | PO-authorized allowlist amendment (§6, §8) |
| `apps/api/tests/unit/test_q4_access_reset.py` | New | 5 unit tests covering the 7-row `R5` precedence table, `PAID_EXTERNAL_ONLY` matrix, lazy expiry, Q4 OpenAPI/input contracts, and secret-free CLI output | `FR-QTA-032/040/041/050`, `RULE-QTA-03`, `R5/R8/R9` |
| `apps/api/tests/integration/test_q4_carryover.py` | New | 3 PostgreSQL integration tests verifying C1 (deactivated provider via real MDL API), C2 (single `_qualifying_quota_rows` source), and C3 (`before_warning_threshold_pct` audit + legacy JSON projection) | C1, C2, C3, `R6` |
| `apps/api/tests/integration/test_q4_qta_killswitch_reset.py` | New | 21 PostgreSQL integration tests covering suspend/restore validation, operator identity, concurrency, scope enforcement, balance preservation, lazy expiry, event filtering, manual/CLI reset idempotency, zero rollover, RBAC/CSRF/Origin, tenant isolation, audit rollback, and bounded SQL count (no N+1) | `FR-QTA-001/031/032/040/041/050`, `RULE-QTA-01/03/04` |
| `docs/phase4/QTA_ARCHITECTURE_AND_DECISIONS.md` | Modified | Updated status line, §2.2 (`R5/R6/R9` `UPPER_SNAKE` table), §2.5 (`R7/R8` reset semantics), and §5 (implemented Q4 routes) | Section 4.6 |
| `docs/architecture/ADR-0004-qta.md` | Modified | Updated status line (`Q0–Q4` implemented) and kill-switch/reset bullets (`R5–R9`) | Section 4.6 |
| `docs/phase4/QTA_IMPLEMENTATION_PLAN.md` | Modified | Added `Q4 completion (2026-11-27)` section linking this report | Plan tracking |
| `docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md` | Modified | Updated status for `FR-QTA-001..050` (all implemented in API; UI in Q5) and `RULE-QTA-03` path | Traceability |
| `docs/PROJECT_CONTEXT.md` | Modified | Updated QTA status & repository map to Q4 | Onboarding docs |
| `docs/acceptance-matrix.md` | Modified | Updated QTA status banner with exact Q4 gate counts (formal acceptance unchanged: `0/33`) | Acceptance integrity |
| `CLAUDE.md` | Modified *(repo root)* | Updated current work line to Q4 and linked `QTA_Q4_REPORT.md` | Agent onboarding |
| `docs/phase4/reports/QTA_Q3_REPORT.md` | Modified *(external, reviewer)* | Reviewer appended §11 (*Reviewer response*) after Q4 preflight hash capture; untouched by Q4 agent | External review note (§9) |
| `docs/phase4/reports/QTA_Q4_REPORT.md` | New | This 11-section completion report & whole-module review | Section 8 |
| `docs/phase4/reports/q4/git-status-before.txt` | New | Preflight `git status --short` snapshot | Section 2 |
| `docs/phase4/reports/q4/hashes-before.txt` | New | Preflight SHA256 manifest of `apps`, `tests`, `scripts`, `infra`, `docs`, `.github` | Section 2 |
| `docs/phase4/reports/q4/baseline-gate.log` | New | Full pre-Q4 `verify_phase2.sh` output (API 549 passed, 1 skipped; browser 16 passed) | Section 2 |
| `docs/phase4/reports/q4/focused-tests.log` | New | Focused Q1–Q4 test output (91 passed) | Section 6–7 |
| `docs/phase4/reports/q4/cli-smoke.log` | New | Two-run `python -m aq_uai_api.qta.reset` output under restricted `aq_uai_runtime` | Section 6–7 |
| `docs/phase4/reports/q4/mutation-proof.log` | New | Full log of all 5 mutation proofs + pre/post-restore SHA256 hashes | Section 5, 7 |
| `docs/phase4/reports/q4/final-gate.log` | New | Full post-Q4 `verify_phase2.sh` output (API 578 passed, 1 skipped; browser 16 passed) | Section 6–7 |
| `docs/phase4/reports/q4/git-status-after.txt` | New | Postflight `git status --short` snapshot | Section 7 |
| `docs/phase4/reports/q4/hashes-after.txt` | New | Postflight SHA256 manifest (written to `/tmp` first, moved in after scan) | Section 7 |
| `docs/phase4/reports/q4/changed-files.txt` | New | `diff hashes-before.txt hashes-after.txt` confirming exact allowlist adherence | Section 7 |

---

## 3. Carry-over corrections C1–C4

1. **C1 (`R6` — usable model requires `MdlModel.active AND MdlProvider.active`):**
   - **What changed:** Defined `usable_model_predicate()` (`entitlements.py:39–41`) returning `sa.and_(MdlModel.active.is_(True), MdlProvider.active.is_(True))` and `usable_models_query(institution_id)` (`entitlements.py:44–59`) joining `MdlProvider` on `(institution_id, provider_id)`. Wired them into all five QTA surfaces:
     - `queries.models` (`queries.py:74`) — omits models of inactive providers from `GET /qta/models`.
     - `queries._quotas_by_group` (`queries.py:124, 154`) — keeps stored quota rows visible on group detail (`never deleted`) while reporting `model_active=bool(usable)`.
     - `service.upsert_group_quotas` (`service.py:381–402`) — rejects quota edits on models whose provider is inactive with `409 QTA_MODEL_NOT_ELIGIBLE`.
     - `entitlements._qualifying_quota_rows` (`entitlements.py:119–133`) & `compute_user_entitlements` (`entitlements.py:234–238`) — excludes inactive-provider models from `allocated_for_month`, personal lookup, and `user_model_base_entitlement`, and restores them automatically when the provider is re-activated (`PD-Q5`).
     - `access.check_ai_access` (`access.py:181–191`) — blocks with `MODEL_UNAVAILABLE`.
   - **Verified by:** `test_inactive_provider_models_are_not_usable_anywhere` (`test_q4_carryover.py`) + Mutation Proof #5.

2. **C2 (Single source of truth for qualifying `(user, group, model)` quota rows):**
   - **What changed:** Extracted `_qualifying_quota_rows(institution_id, *, user_id=None, model_id=None)` (`entitlements.py:62–140`), encapsulating the 7-table join (`group_memberships` → `users` → `qta_quota_groups` → `account_groups` → `qta_group_model_quotas` → `mdl_models` → `mdl_providers`) and all 7 eligibility predicates in one private selectable. Built `user_model_base_entitlement` (`entitlements.py:143–149`), `compute_user_entitlements` (`entitlements.py:243–250`), and `allocated_for_month` (`entitlements.py:331–343`) directly on top of `_qualifying_quota_rows`.
   - **Verified by:** `test_qualifying_rule_single_source` (`test_q4_carryover.py` — AST check + PostgreSQL numerical agreement) and all 20 Q3 integration tests.

3. **C3 (`GroupQuotaUpdated.before_warning_threshold_pct` audit fidelity):**
   - **What changed:** Added `before_warning_threshold_pct: int | None = Field(default=None, ge=1, le=100)` to `GroupQuotaUpdated` (`db/audit.py:271`), populated as `None` on initial insert (`qta/service.py:451`) and `row.warning_threshold_pct` before mutation on update (`qta/service.py:465, 486`). Optional default keeps `public_audit_changes` backward-compatible with pre-Q4 JSON rows.
   - **Verified by:** `test_quota_threshold_change_audits_before_and_after` (`test_q4_carryover.py`).

4. **C4 (Browser harness startup deadline):**
   - **What changed:** Replaced `for _ in range(100):` in `wait_for_http` (`tests/browser/conftest.py:157–170`) with `deadline = time.monotonic() + 30.0` and `while time.monotonic() < deadline:`, preserving `0.1 s` polling, early process-exit break, and the identical failure message.
   - **Verified by:** Both `baseline-gate.log` and `final-gate.log` (`16 passed` browser tests with zero startup timeouts under parallel CPU load).

---

## 4. Design *(in plain words)*

### 4.1 Individual kill-switch state machine & lazy expiry (`qta/access.py`)

Instead of editing or deleting rows when a user is suspended or restored (`INV-17`, `RULE-QTA-04`), QTA uses two **INSERT-only** tables:
1. **`qta_suspensions`** records when an admin suspends a user, the chosen `scope` (`ALL_MODELS` or `PAID_EXTERNAL_ONLY`), `reason`, `ordered_by` (*Người ra lệnh*, administrative text), `suspended_by` (*Người thực hiện*, always taken from the logged-in session), and an optional future `expires_at`.
2. **`qta_suspension_restorations`** records at most one restoration row (`suspension_id` PK) when an admin lifts an active suspension early.

At any instant `t = periods.utc_now()`, a suspension's status is computed on the fly (**lazy expiry** — zero background cron or database `UPDATE` needed when time passes):
- Has a row in `qta_suspension_restorations` → **`RESTORED`**
- Else `expires_at IS NULL` or `expires_at > t` → **`ACTIVE`**
- Else (`expires_at <= t`) → **`EXPIRED`**

Neither suspending nor restoring ever touches `qta_group_model_quotas`, `qta_budget_revisions`, or `group_memberships` — a user's configured base quota is never zeroed out on suspend or inflated on restore (`FR-QTA-040`, `FR-QTA-041`).

### 4.2 Ordered fail-closed `check_ai_access` decision table (`R5`, `R9`)

`check_ai_access(db, institution_id, user_id, model_id)` is a pure read function (no writes, no side effects) that evaluates 7 rules from top to bottom and stops at the first block:
1. **`USER_NOT_FOUND`** — user does not exist in `institution_id`.
2. **`USER_NOT_ACTIVE`** — user's directory account state is `PENDING` or `DISABLED`.
3. **`MODEL_UNAVAILABLE`** — model does not exist in `institution_id`, or `mdl_models.active` is false, or `mdl_providers.active` is false (`C1`/`R6`).
4. **`SUSPENDED_ALL_MODELS`** — user has an `ACTIVE` suspension with `scope = 'ALL_MODELS'` (returns `suspension_id`).
5. **`SUSPENDED_PAID_EXTERNAL`** — user has an `ACTIVE` suspension with `scope = 'PAID_EXTERNAL_ONLY'` **and** the model's provider has `provider_type = 'EXTERNAL'` (`PD-Q2`; `INTERNAL` models pass this step).
6. **`NO_ENTITLEMENT`** — user's live additive base entitlement for `(user, model)` is `0` (`FR-QTA-031 AC2`, `R5`).
7. **`ALLOWED`** — `allowed = True, reason = None, suspension_id = None`.

`compute_user_entitlements` calls the exact same `evaluate_access_rule` helper after loading the user's state, usable models, active suspension, and SQL `SUM` entitlements in bulk, so `GET /qta/users/{id}/entitlements` executes a constant number of SQL queries regardless of how many models exist.

### 4.3 Actual lock order used on writes

Every QTA write enters through `authorization.writes.protected(...)` and acquires locks in strict global order so two concurrent requests can never deadlock:
1. **Institution advisory lock** (`INSTITUTION_NAMESPACE = 41001`, shared for normal writes).
2. **Account advisory locks** (`ACCOUNT_NAMESPACE = 31002`, sorted by 32-bit key across `{actor_id, target_user_id}` when `user_id` is passed to `protected` on suspend/restore/membership writes).
3. **Module advisory lock** per institution (`QTA_SYNC_NAMESPACE = 52000`, `QTA_BUDGET_NAMESPACE = 52001`, `QTA_SUSPENSION_NAMESPACE = 52002`, or `QTA_RESET_NAMESPACE = 52003` — each write takes at most one of these).
4. **Row locks** (`FOR UPDATE` ordered by primary/group/model UUID where applicable).

Because `qta_suspensions` cannot enforce "at most one active suspension per user" with a PostgreSQL unique index (`expires_at > now()` is non-immutable and restorations live in a separate table), `QTA_SUSPENSION_NAMESPACE = 52002` serializes concurrent `suspend_user` / `restore_user` calls per institution so one wins (`201`) and the second deterministically receives `409 QTA_USER_ALREADY_SUSPENDED`.

### 4.4 Shared monthly reset core & scheduled CLI (`qta/reset.py`, `R7`, `R8`)

- **Core (`record_reset`):** Acquires `QTA_RESET_NAMESPACE = 52003` for the institution and checks `qta_monthly_resets` for `(institution_id, month)`. If present, returns `recorded=False` without writing anything. Otherwise inserts one `qta_monthly_resets` row, one `qta_events(MONTHLY_REFRESH, user_id=NULL)` row, and one typed audit event (`qta.monthly_reset_executed` for manual admin simulation; `qta.monthly_reset_scheduled` with `actor_id=NULL` for the CLI) in the **same transaction**.
- **Manual API (`POST /api/v1/qta/monthly-resets`):** Accepts an empty body only, always resolves `current_month(settings)` in `Asia/Ho_Chi_Minh` (`PD-Q6`), returns `201` on first execution, and raises `409 QTA_RESET_ALREADY_EXECUTED` if already recorded for the current month.
- **CLI (`python -m aq_uai_api.qta.reset`):** Reads all institution IDs, then runs one `write_transaction` per institution for the current month only (never backfilling missed past months, `R8`). Prints only `recorded=N already=M` (`exit 0`, including when all institutions are already recorded) and prints a generic secret-free message to `stderr` (`exit 1`) on failure.

---

## 5. API

All routes live under `/api/v1/qta` with `Cache-Control: no-store`.

| Method & Path | Permission / Scope | Status codes | Error codes | Audit action | `qta_events` type |
| --- | --- | --- | --- | --- | --- |
| `GET /api/v1/qta/users` *(updated)* | `qta.read` (GLOBAL or exact-UNIT) | `200`, `401`, `403`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `VALIDATION_FAILED` | *(read)* | — |
| `GET /api/v1/qta/users/{user_id}/entitlements?month=YYYY-MM` *(updated)* | `qta.read` (GLOBAL or exact-UNIT) | `200`, `401`, `403`, `404`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `QTA_INVALID_PERIOD`, `QTA_PERIOD_NOT_OPEN`, `VALIDATION_FAILED` | *(read)* | — |
| `GET /api/v1/qta/users/{user_id}/suspensions` *(new)* | `qta.read` (GLOBAL or exact-UNIT) | `200`, `401`, `403`, `404`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_FAILED` | *(read)* | — |
| `POST /api/v1/qta/users/{user_id}/suspensions` *(new)* | `qta.manage` (direct GLOBAL + Origin/CSRF) | `201`, `401`, `403`, `404`, `409`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `QTA_USER_ALREADY_SUSPENDED`, `VALIDATION_FAILED` | `qta.user_suspended` (`UserSuspended`) | `SUSPEND` |
| `POST /api/v1/qta/users/{user_id}/restore` *(new)* | `qta.manage` (direct GLOBAL + Origin/CSRF) | `200`, `401`, `403`, `404`, `409`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `QTA_USER_NOT_SUSPENDED`, `VALIDATION_FAILED` | `qta.user_restored` (`UserRestored`) | `RESTORE` |
| `GET /api/v1/qta/events?month=YYYY-MM` *(new)* | `qta.read` (GLOBAL only; UNIT → `403`) | `200`, `401`, `403`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `QTA_INVALID_PERIOD`, `VALIDATION_FAILED` | *(read)* | — |
| `GET /api/v1/qta/monthly-resets` *(new)* | `qta.read` (GLOBAL only; UNIT → `403`) | `200`, `401`, `403`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `VALIDATION_FAILED` | *(read)* | — |
| `POST /api/v1/qta/monthly-resets` *(new)* | `qta.manage` (direct GLOBAL + Origin/CSRF; empty body) | `201`, `401`, `403`, `409`, `422` | `AUTH_REQUIRED`, `FORBIDDEN`, `QTA_RESET_ALREADY_EXECUTED`, `VALIDATION_FAILED` | `qta.monthly_reset_executed` (`MonthlyResetRecorded`) | `MONTHLY_REFRESH` |

### Example response: `POST /api/v1/qta/users/{user_id}/suspensions` (`201`, synthetic test data)

```json
{
  "id": "88888888-8888-4888-8888-888888888888",
  "user_id": "11111111-1111-4111-8111-111111111111",
  "scope": "PAID_EXTERNAL_ONLY",
  "reason": "Giới hạn chi phí mô hình thương mại",
  "ordered_by": "Ban Giám hiệu",
  "expires_at": "2026-12-05T05:00:00Z",
  "suspended_by": "66666666-6666-4666-8666-666666666666",
  "suspended_at": "2026-11-27T06:00:00Z",
  "status": "ACTIVE",
  "restoration": null
}
```

### Example response: `GET /api/v1/qta/users/{user_id}/entitlements?month=2026-11` *(synthetic test data)*

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
  "quota_status": "SUSPENDED",
  "suspension": {
    "id": "88888888-8888-4888-8888-888888888888",
    "user_id": "11111111-1111-4111-8111-111111111111",
    "scope": "PAID_EXTERNAL_ONLY",
    "reason": "Giới hạn chi phí mô hình thương mại",
    "ordered_by": "Ban Giám hiệu",
    "expires_at": "2026-12-05T05:00:00Z",
    "suspended_by": "66666666-6666-4666-8666-666666666666",
    "suspended_at": "2026-11-27T06:00:00Z",
    "status": "ACTIVE",
    "restoration": null
  },
  "memberships": [
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
      "display_name": "External GPT",
      "technical_id": "gpt-ext",
      "provider_type": "EXTERNAL",
      "base_entitlement": 1000,
      "contributions": [
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
      "access": {
        "allowed": false,
        "reason": "SUSPENDED_PAID_EXTERNAL"
      },
      "actual_consumption": null,
      "remaining_quota": null,
      "consumption_status": "NOT_INTEGRATED"
    },
    {
      "model_id": "55555555-5555-4555-8555-555555555555",
      "display_name": "Internal Llama",
      "technical_id": "llama-int",
      "provider_type": "INTERNAL",
      "base_entitlement": 2000,
      "contributions": [
        {
          "group_id": "33333333-3333-4333-8333-333333333333",
          "code": "G_GV",
          "name": "Giảng viên",
          "kind": "SYSTEM",
          "origin": "SYNC",
          "enabled": true,
          "monthly_limit": 2000,
          "contributes": 2000
        }
      ],
      "access": {
        "allowed": true,
        "reason": null
      },
      "actual_consumption": null,
      "remaining_quota": null,
      "consumption_status": "NOT_INTEGRATED"
    }
  ],
  "base_entitlement_total": 3000
}
```

### Example response: `GET /api/v1/qta/monthly-resets` *(synthetic test data)*

```json
{
  "current": {
    "month": "2026-11",
    "status": "COMPLETED",
    "reset": {
      "id": "99999999-9999-4999-8999-999999999999",
      "month": "2026-11",
      "trigger_mode": "MANUAL_SIMULATION",
      "triggered_by": "66666666-6666-4666-8666-666666666666",
      "executed_at": "2026-11-27T06:05:00Z"
    }
  },
  "items": [
    {
      "id": "99999999-9999-4999-8999-999999999999",
      "month": "2026-11",
      "trigger_mode": "MANUAL_SIMULATION",
      "triggered_by": "66666666-6666-4666-8666-666666666666",
      "executed_at": "2026-11-27T06:05:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

## 6. Tests

### 6.1 New unit tests (`apps/api/tests/unit/test_q4_access_reset.py` — 5 tests)

| Test name | What it proves (FR / AC / Rule) |
| --- | --- |
| `test_access_decision_table_order` | All 7 outcomes (`USER_NOT_FOUND` → `USER_NOT_ACTIVE` → `MODEL_UNAVAILABLE` → `SUSPENDED_ALL_MODELS` → `SUSPENDED_PAID_EXTERNAL` → `NO_ENTITLEMENT` → `ALLOWED`) and strict precedence when multiple failure conditions hold (`R5`, `R9`) |
| `test_paid_external_only_matrix` | `PAID_EXTERNAL_ONLY` blocks `EXTERNAL` and allows `INTERNAL`; `ALL_MODELS` blocks both (`FR-QTA-040 AC1`, `RULE-QTA-03`, `PD-Q2`) |
| `test_lazy_expiry_none_future_past` | Frozen-clock evaluation of `None`, future, exact-now, and past `expires_at`, plus `RESTORED` precedence (`PD-Q3`) |
| `test_q4_openapi_routes_and_no_mutation_of_history` | Exact Q4 routes; zero `PATCH`/`PUT`/`DELETE` on `suspensions`/`restore`/`events`/`monthly-resets`/`sync-runs`; `POST /monthly-resets` body has no `month` field; `SuspendUser` & `RestoreUser` reject `suspended_by`/`restored_by` and unknown fields (`FR-QTA-050 AC2`, `PD-Q3`, `PD-Q6`) |
| `test_reset_cli_output_has_no_secrets_and_counts_only` | `qta.reset.main()` prints only `recorded=N already=M` on success and leaks zero URLs/passwords/secrets on failure (`R8`) |

### 6.2 New carry-over integration tests (`apps/api/tests/integration/test_q4_carryover.py` — 3 tests)

| Test name | What it proves (FR / AC / Rule) |
| --- | --- |
| `test_inactive_provider_models_are_not_usable_anywhere` | Deactivating an unrouted provider via the real MDL API removes its models from `/qta/models`, `allocated`, and lookup, rejects quota upserts with `409 QTA_MODEL_NOT_ELIGIBLE`, blocks `check_ai_access` with `MODEL_UNAVAILABLE`, preserves stored quota rows, and restores everything on provider re-activation (`C1`, `R6`, `PD-Q5`) |
| `test_qualifying_rule_single_source` | AST + PostgreSQL runtime proof that `compute_user_entitlements`, `allocated_for_month`, and `user_model_base_entitlement` all derive from `_qualifying_quota_rows` and agree numerically (`C2`) |
| `test_quota_threshold_change_audits_before_and_after` | Changing only `warning_threshold_pct` emits `qta.group_quota_updated` with `before_warning_threshold_pct` and `warning_threshold_pct`, and legacy JSON rows still project cleanly (`C3`) |

### 6.3 New Stage Q4 integration tests (`apps/api/tests/integration/test_q4_qta_killswitch_reset.py` — 21 tests)

| Test name | What it proves (FR / AC / Rule) |
| --- | --- |
| `test_suspend_without_expiry_and_with_future_expiry` | Open-ended (`expires_at=None`) and >365-day finite future `expires_at` suspensions succeed (`FR-QTA-040 AC1–AC2`, `PD-Q3`) |
| `test_suspend_validation` | Missing/blank `reason` or `ordered_by`, naive/now/past `expires_at`, invalid `scope`, and extra fields including `suspended_by` fail `422` with zero DB rows written (`FR-QTA-040 AC3`, `PD-Q3`) |
| `test_operator_is_session_actor_even_if_ordered_by_names_someone_else` | `suspended_by`, `qta_events.actor_id`, and `audit_events.actor_id` always equal `authority.actor_id` even when `ordered_by` names another user (`FR-QTA-040`, `PD-Q3`) |
| `test_second_active_suspension_is_409_but_after_expiry_or_restore_allowed` | Duplicate active suspension returns `409 QTA_USER_ALREADY_SUSPENDED`; new suspension succeeds after lazy expiry or explicit restore, with full `ACTIVE`/`RESTORED`/`EXPIRED` history preserved |
| `test_concurrent_suspends_one_wins` | Two synchronized threads suspending the same user produce one `201` and one `409 QTA_USER_ALREADY_SUSPENDED` with zero `500`s (`QTA_SUSPENSION_NAMESPACE = 52002`) |
| `test_paid_external_only_blocks_external_allows_internal_end_to_end` | `PAID_EXTERNAL_ONLY` blocks `EXTERNAL` (`SUSPENDED_PAID_EXTERNAL`) and allows `INTERNAL` (`allowed: true`) in both HTTP lookup and `check_ai_access` (`FR-QTA-040 AC1`, `RULE-QTA-03`, `PD-Q2`) |
| `test_all_models_blocks_both` | `ALL_MODELS` blocks both `EXTERNAL` and `INTERNAL` models with `SUSPENDED_ALL_MODELS` (`FR-QTA-040 AC1`, `RULE-QTA-03`) |
| `test_suspend_and_restore_do_not_change_entitlements_or_budgets` | `base_entitlement` and institutional `allocated` stay identical before suspend, during suspend, and after restore (`FR-QTA-040`, `FR-QTA-041`) |
| `test_restore_returns_active_and_records_event` | Restore returns `RESTORED` suspension with restoration metadata, flips `quota_status` back to `ACTIVE`, and appends `RESTORE` event + `qta.user_restored` audit (`FR-QTA-041 AC1–AC2`) |
| `test_restore_without_active_suspension_is_409` | Restore returns `409 QTA_USER_NOT_SUSPENDED` when never suspended, after lazy expiry, or when already restored (`FR-QTA-041`) |
| `test_lazy_expiry_lifts_suspension_without_writes` | Advancing frozen `periods.utc_now()` past `expires_at` lifts suspension across `/users`, `/entitlements`, and `/suspensions` (`EXPIRED`) with zero DB writes (`PD-Q3`) |
| `test_events_append_only_and_filtered` | `SUSPEND`, `RESTORE`, and `MONTHLY_REFRESH` events filter by `month`, `event_type`, and `user_id`; `summary` contains scope but excludes free-text `reason` and `note` (`FR-QTA-050`) |
| `test_manual_reset_current_month_only_and_409_on_repeat` | `POST /qta/monthly-resets` rejects `{month: ...}` (`422`), records current month (`201`), updates `current.status` to `COMPLETED`, and returns `409 QTA_RESET_ALREADY_EXECUTED` on repeat (`FR-QTA-032 AC1`, `PD-Q6`) |
| `test_reset_cli_idempotent_and_no_backfill` | `run_scheduled_resets()` records current month once, is idempotent on repeat (`recorded=0, already=N`), and never backfills missed past months (`FR-QTA-032`, `R8`) |
| `test_manual_then_scheduled_same_month_is_noop` | Running the scheduled CLI after a manual simulation in the same month is a clean no-op preserving the original row (`PD-Q6`, `R8`) |
| `test_zero_rollover_across_months` | Advancing frozen clock from November into December resets carries over zero November budget or allowance; December base entitlement equals configured group quotas (`FR-QTA-032 AC2`, `R7`) |
| `test_active_suspension_survives_reset` | Monthly reset leaves an active suspension intact (`QD8`) |
| `test_q4_rbac_and_csrf` | UNIT viewer scoped to own-unit user suspensions (`404` on other unit, `403` on `/events` and `/monthly-resets`); GLOBAL viewer read-only (`403` on writes); `FOUNDATION_ADMIN`/`AI_MODEL_ADMIN` `403`; anonymous `401`; missing CSRF and wrong Origin `403` (`FR-QTA-001`) |
| `test_q4_tenant_isolation` | Another institution's users, suspensions, events, and monthly resets are completely invisible (`404` / omitted) |
| `test_q4_audit_failure_rolls_back` | Revoking `INSERT` on `audit_events` rolls back suspend, restore, and manual reset completely with zero surviving rows in `qta_suspensions`, `qta_suspension_restorations`, `qta_monthly_resets`, or `qta_events` |
| `test_users_list_and_lookup_show_quota_status_without_n_plus_1` | SQLAlchemy `before_cursor_execute` counter proves fetching 20 users (half suspended) executes the exact same bounded query count (`<= 6`) as fetching 2 users |

### 6.4 Edited existing tests

| File | Lines | Before | After | Why |
| --- | --- | --- | --- | --- |
| `apps/api/tests/unit/test_q2_contracts.py` | 113–122 | Pinned 14 Q2–Q3 `/api/v1/qta` paths | Added the 4 new Q4 paths (`/qta/users/{user_id}/suspensions`, `/qta/users/{user_id}/restore`, `/qta/events`, `/qta/monthly-resets`) | Allowlisted in Section 3 for Q4 route inventory pin |
| `apps/api/tests/integration/test_q3_qta_lookup_budgets.py` | 450–460 | Comment `# Item shape contains no group/quota keys.` and 6-key `assert set(unit_users[0]) == {"id", "username", "display_name", "institutional_code", "primary_unit_id", "state"}` | Comment `# Item shape: identity + quota_status only — no group, budget or entitlement amounts.`, 7-key set adding `"quota_status"`, plus `assert unit_users[0]["quota_status"] == "ACTIVE"` | **PO-authorized allowlist amendment** (see §8): reconciles Q3's exact key-set pin with Q4 §4.4 (`GET /qta/users` items gain `quota_status`). Zero other lines in that file touched |

---

## 7. Results & Mutation proof

### 7.1 Verification summary

| Check | Baseline (`baseline-gate.log`) | Final (`final-gate.log`) | Delta / Notes |
| --- | --- | --- | --- |
| `scripts/verify_frontend_assets.py` | PASS (`10 assets exist`) | PASS (`10 assets exist`) | `apps/web/` untouched |
| `node --test scripts/test_sidebar_navigation.cjs` | `1 passed` | `1 passed` | Unchanged |
| `node --check` (`apps/web/**/*.js`, `apps/admin/assets/*.mjs`) | PASS | PASS | Unchanged |
| `ruff check` (API src/tests/migrations/scripts/demo-provider + `tests/browser`) | `All checks passed!` (×2) | `All checks passed!` (×2) | Clean |
| `scripts/verify_wp2_compose.py --env-file .env.example` | PASS | PASS | Unchanged |
| `alembic upgrade head` (`0001` → `0008_qta_schema`) & `alembic check` | `No new upgrade operations detected.` | `No new upgrade operations detected.` | Head unchanged (`0008_qta_schema`) |
| **CLI smoke (`cli-smoke.log`, restricted `aq_uai_runtime`)** | — | Run 1: `recorded=1 already=0` (`exit 0`); Run 2: `recorded=0 already=1` (`exit 0`) | Verified least-privilege scheduled reset execution |
| **Focused Q1–Q4 suite (`focused-tests.log`)** | — | **91 passed** in 483.07s | 33 unit + 58 PostgreSQL integration |
| **Full API suite (`apps/api/tests`)** | **549 passed, 1 skipped** (662.73s) | **578 passed, 1 skipped** (993.07s) | **+29 passed** (opt-in live provider stays skipped) |
| **Browser suite (`tests/browser`)** | **16 passed** (215.31s) | **16 passed** (217.53s) | Unchanged (no UI in Q4; zero startup flakes) |

Evidence log paths:
- Preflight baseline gate: [`docs/phase4/reports/q4/baseline-gate.log`](q4/baseline-gate.log)
- Focused Q1–Q4 suite: [`docs/phase4/reports/q4/focused-tests.log`](q4/focused-tests.log)
- CLI smoke log: [`docs/phase4/reports/q4/cli-smoke.log`](q4/cli-smoke.log)
- Mutation proofs: [`docs/phase4/reports/q4/mutation-proof.log`](q4/mutation-proof.log)
- Final full gate: [`docs/phase4/reports/q4/final-gate.log`](q4/final-gate.log)
- File manifests: [`git-status-before.txt`](q4/git-status-before.txt), [`git-status-after.txt`](q4/git-status-after.txt), [`hashes-before.txt`](q4/hashes-before.txt), [`hashes-after.txt`](q4/hashes-after.txt), [`changed-files.txt`](q4/changed-files.txt)

### 7.2 Mutation proof (`docs/phase4/reports/q4/mutation-proof.log`)

| # | Rule | How temporarily broken | Failing test & observed failure | Restored & verified |
| --- | --- | --- | --- | --- |
| 1 | `PAID_EXTERNAL_ONLY` allows `INTERNAL` (`RULE-QTA-03`, `PD-Q2`) | Removed `and provider_type == "EXTERNAL"` in `qta/access.py::evaluate_access_rule` | `test_paid_external_only_blocks_external_allows_internal_end_to_end` FAILED (`{'allowed': False, 'reason': 'SUSPENDED_PAID_EXTERNAL'} != {'allowed': True, 'reason': None}`, exit 1) | Restored byte-identically; PASSED (8.19s) |
| 2 | Lazy expiry lifts expired suspension (`PD-Q3`) | Replaced expiry checks in `qta/access.py::suspension_status` and `active_suspensions_for` with `True` / `sa.true()` | `test_lazy_expiry_lifts_suspension_without_writes` FAILED (`assert 'SUSPENDED' == 'ACTIVE'`, exit 1) | Restored byte-identically; PASSED (8.10s) |
| 3 | Duplicate-active-suspension check (`409`) | Replaced active-suspension guard in `qta/service.py::suspend_user` with `pass` | `test_second_active_suspension_is_409_but_after_expiry_or_restore_allowed` FAILED (`assert 201 == 409`, exit 1) | Restored byte-identically; PASSED (8.50s) |
| 4 | Manual reset restricted to current month only (`PD-Q6`) | Allowed optional `MonthQuery` body on `POST /qta/monthly-resets` (`api/v1/qta.py` + `qta/service.py`) resolving `open_only=True` | `test_manual_reset_current_month_only_and_409_on_repeat` FAILED (`assert 201 == 422` on `{"month": "2026-12"}`, exit 1) | Restored byte-identically; PASSED (8.34s) |
| 5 | `MdlProvider.active` in usable-model predicate (`C1`, `R6`) | Changed `usable_model_predicate()` in `qta/entitlements.py` to `MdlModel.active.is_(True)` only | `test_inactive_provider_models_are_not_usable_anywhere` FAILED (`assert model["id"] not in listed_after`, exit 1) | Restored byte-identically; PASSED (10.36s) |

Pre-mutation and post-restore SHA256 hashes match byte-for-byte:
- `apps/api/src/aq_uai_api/qta/access.py`: `8417a5be0debe627c4b1f0288d3c6fb30045f015f1f42670054df8d73c2182da`
- `apps/api/src/aq_uai_api/qta/service.py`: `5466a06b2896c850749ae209fe73c426dc064bae223851861cbca05009436410`
- `apps/api/src/aq_uai_api/api/v1/qta.py`: `54ec03f99ddcf7983e94ad6f43a67bb6a3fcccf645eb9511ab649ea1c43723c6`
- `apps/api/src/aq_uai_api/qta/entitlements.py`: `96d390018c7e3dd27442078c9965b271f49f8f86fc3d722a6c0b383181331cf1`

---

## 8. Decisions and deviations

- **Reviewer decisions `R5–R9` applied verbatim:**
  - **`R5`:** `check_ai_access` is fail-closed with the exact 7-step ordered decision table (`USER_NOT_FOUND` → `USER_NOT_ACTIVE` → `MODEL_UNAVAILABLE` → `SUSPENDED_ALL_MODELS` → `SUSPENDED_PAID_EXTERNAL` → `NO_ENTITLEMENT` → `ALLOWED`).
  - **`R6` (`C1`):** Single `usable_model_predicate()` (`MdlModel.active AND MdlProvider.active`) applied across `queries.models`, `queries._quotas_by_group`, `service.upsert_group_quotas`, `compute_user_entitlements`, `allocated_for_month`, and `check_ai_access`.
  - **`R7`:** Monthly reset writes an honest append-only ledger marker (`qta_monthly_resets` + `qta_events(MONTHLY_REFRESH)` + audit) without fabricating per-user balance rows.
  - **`R8`:** Scheduled CLI `python -m aq_uai_api.qta.reset` records only the current institution month (1 transaction per institution), never backfills missed past months, and exits `0` idempotently.
  - **`R9`:** All access-decision and exclusion reason codes use `UPPER_SNAKE` (`SUSPENDED_ALL_MODELS`, `SUSPENDED_PAID_EXTERNAL`, `NO_ENTITLEMENT`, etc.); updated `QTA_ARCHITECTURE_AND_DECISIONS.md` §2.2 accordingly.
- **Target account state on suspend/restore (§4.2):** Any account state (`PENDING`, `ACTIVE`, `DISABLED`) in the caller's institution is accepted for `POST /qta/users/{id}/suspensions` and `POST /qta/users/{id}/restore`, because quota status (`ACTIVE` | `SUSPENDED`) is independent of directory account state (e.g., an admin can place a quota suspension on a `PENDING` or `DISABLED` user before their account is activated). Note: `QTA_ARCHITECTURE_AND_DECISIONS.md` §2.4 line 123 and `QD11` still carry the earlier Q1-R `PROV` sentence (`User.state == 'ACTIVE'`); kept untouched because §2.4 and `QTA_OPEN_DECISIONS.md` were outside the §3 doc-edit list, and flagged in §10.g below for cleanup.
- **PO-authorized allowlist amendment (`test_q3_qta_lookup_budgets.py`):**
  - *Conflict found:* Q4 §4.4 adds `"quota_status"` to `GET /qta/users` items, while `test_q3_qta_lookup_budgets.py::test_lookup_scope` pinned the exact pre-Q4 6-key set on `GET /qta/users` items and was omitted from the §3 allowlist.
  - *Resolution:* Paused before touching the file and requested explicit Project Owner authorization. Authorized on 2026-11-27 under five conditions, all satisfied: (1) changed only the pinned key set in `test_lookup_scope` (`6 -> 7` keys adding `"quota_status"`), (2) updated the comment to `# Item shape: identity + quota_status only — no group, budget or entitlement amounts.`, (3) added `assert unit_users[0]["quota_status"] == "ACTIVE"`, (4) documented here and in §6 + `changed-files.txt`, and (5) confirmed zero other files outside the §3 allowlist were modified.
- **Minor implementation details within spec (no deviations):**
  - `POST /qta/users/{id}/restore` accepts omitted body, `{}`, or `{"note": "..."}` via `Body(default=None)` while still rejecting unknown fields or blank whitespace notes (`422`).
  - `qta_events.summary` on `SUSPEND` and `RESTORE` uses fixed Vietnamese templates (`f"Tạm ngưng quyền dùng AI ({row.scope})"` and `"Khôi phục quyền dùng AI"`), containing the scope on `SUSPEND` and excluding all free-text `reason` / `note` content.

---

## 9. Open questions, risks & unverified items

- **Working-tree baseline & concurrent reviewer note:** Stage Q3 had not yet been committed to `git` when Q4 began (`HEAD` remained at `c10c801`), and while Q4 was running the reviewer saved §11 (*Reviewer response*) into `docs/phase4/reports/QTA_Q3_REPORT.md`. Consequently, `git-status-before.txt` and `git-status-after.txt` list both Q3 and Q4 working-tree files, while `hashes-before.txt` → `hashes-after.txt` (`changed-files.txt`) authoritatively isolates every file created or modified during the Q4 window.
- **Not verified for Q4:** hosted GitHub Actions CI on Q4 changes (earlier commits `d01e75e` and `c10c801` passed on `ubuntu-24.04` per `QTA_Q3_REPORT.md` §11, while Q4 remains uncommitted locally); live Docker Compose run against the developer's persistent `aq-uai-dev` stack (intentionally untouched at `0006`); real OS cron / `systemd` timer invocation (the CLI itself was verified directly against disposable PostgreSQL under `aq_uai_runtime`); opt-in live external AI provider check (`1 skipped`).
- **Remaining stages:** Q5 (`#qta` Admin UI in `apps/admin/`) and Q6 (cross-module `FR-MDL-020 AC3` runtime proof, backup/restore & `0006 -> 0008` populated QTA upgrade rehearsal, and handoff) await separate authorization.

---

## 10. Whole-module review (PART A — Independent assessment of QTA Q0–Q4)

### 10.a Requirements coverage (`FR-QTA-001..050` & `RULE-QTA-01..05`)

Every `Must` requirement in `AQ-FRD-UAI-QTA-001` is now **genuinely enforced at the database and API layers with automated PostgreSQL and mutation-proof evidence**, while **every UI acceptance criterion remains open until Stage Q5** (so `0/12` QTA FRs are complete end-to-end today):

| ID | API / DB status | Real gaps remaining |
| --- | --- | --- |
| `FR-QTA-001` (RBAC & empty before sync) | **Met in API/DB:** `0007` role checks, `_CENTRAL_PERMISSIONS`, `qta_quota_groups` empty before sync, UNIT scope on `/users`, `/entitlements`, `/suspensions`. | **Q5 UI:** hide write controls for `AI_QUOTA_VIEWER`; block `#qta` navigation without `qta.read`. |
| `FR-QTA-010` (Monthly school cap + decision) | **Met in API/DB:** `qta_budget_revisions` INSERT-only, day-1 check, `decision_number` + `decision_date` NOT NULL, open current/next month window. | **Q5 UI (`AC3`):** UI must have zero Semester/Project/Exam cycle selectors and display `"chưa ghi nhận"` when unset. |
| `FR-QTA-011` (Cannot reduce below allocated) | **Met in API/DB:** `409 QTA_BUDGET_BELOW_ALLOCATED` with `{allocated, deficit}` serialized under `QTA_BUDGET_NAMESPACE`. | **Q5 UI:** render exact `deficit` to recover. **Phase 5 CRT:** join net individual grants into `allocated_for_month`. |
| `FR-QTA-020` (Sync groups & members) | **Met in API/DB:** `POST /qta/groups/sync` reconciles `SYSTEM` + unenrolled directory `AI_SPECIALIST` groups without touching existing `SPECIALIST` rows or quotas; live memberships from `group_memberships`. | **Q5 UI:** sync button + sync run summary. |
| `FR-QTA-021` (Group × model monthly quota) | **Met in API/DB:** distinct per-model limits, `enabled=false` immediately drops base entitlement (`PD-Q5`), C1 usable-model check, C3 threshold before/after audit. | **Q5 UI:** matrix/per-group editor + disabled-provider badge (`model_active=false`). *(Note: `warning_threshold_pct` supports `%` `1..100` only; FRD §4 allows `%` or absolute — acceptable as documented in QD7.)* |
| `FR-QTA-022` (Specialist AI groups) | **Met in API/DB:** reuses `directory.service` `*_in_tx` + `qta_quota_groups(SPECIALIST)`; `F-Q2-1` blocks quota admins on `/api/v1/groups`. | **Q5 UI:** create/rename/activate/member management screens. |
| `FR-QTA-030` (Additive multi-group stacking) | **Met in API/DB:** SQL `SUM` (mutation-tested against `MAX`) + contributing group breakdown from single `_qualifying_quota_rows` selectable. | **Q5 UI:** render `"1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn mức"`. |
| `FR-QTA-031` (Personal lookup) | **Met in API/DB:** scoped `/qta/users` + `/entitlements` with `quota_status`, active `suspension`, per-model `access`, zero-group `0` / `NO_ENTITLEMENT`, and `NOT_INTEGRATED` consumption. | **Q5 UI:** searchable user picker, formula breakdown, and honest *"Chưa tích hợp đo tiêu thụ thực tế"* state. |
| `FR-QTA-032` (Monthly reset & zero rollover) | **Met in API/CLI/DB:** `POST /qta/monthly-resets`, `GET /qta/monthly-resets`, `python -m aq_uai_api.qta.reset`, `UNIQUE(institution_id, period_month)`, zero rollover across months. | **Q5 UI:** reset status card & current-month simulation button. **Ops (Q6):** scheduler wiring/runbook. |
| `FR-QTA-040` (Individual kill-switch) | **Met in API/DB:** `ALL_MODELS` vs `PAID_EXTERNAL_ONLY`, mandatory `reason` & `ordered_by`, session `suspended_by`, optional future `expires_at` with lazy expiry, balance untouched. | **Q5 UI:** `ĐÃ CẮT` badge, suspend dialog separating *Người thực hiện* vs *Người ra lệnh*. |
| `FR-QTA-041` (Restore quota) | **Met in API/DB:** `qta_suspension_restorations` + `RESTORE` event + audit; balance untouched. | **Q5 UI:** restore dialog & suspension history table. |
| `FR-QTA-050` (Month-only; no edit/delete of history) | **Met in API/DB:** DB day-1 checks, zero `DELETE` on all 8 tables, INSERT-only on 6 history tables, zero `PATCH`/`PUT`/`DELETE` routes on history resources. | **Q5 UI (`AC1`, `AC2`):** Playwright DOM proof of zero non-Month cycle controls and zero Edit/Delete buttons on recorded revisions/events/resets/suspensions. |
| `RULE-QTA-01..05` | **All 5 enforced in DB + service + OpenAPI** and backed by dedicated unit, integration, and mutation tests. | UI layer verification in Q5; cross-module `FR-MDL-020 AC3` live connection-test isolation proof in Q6. |

### 10.b Architecture and decisions (`PD-Q1..PD-Q6`, `R1–R9`, `ADR-0004`)

- **Keep strongly (`PD-Q1..PD-Q6`, `R2`, `R5–R9`, `ADR-0004`):**
  - Separating the explicit QTA registry (`qta_quota_groups`) from Phase 2 `account_groups` while reusing `directory.service` `*_in_tx` and live `group_memberships` is the cleanest architectural decision in Phase 4: zero duplicate identity state, DB-enforced `AUTHORIZATION` exclusion, and honest empty-before-sync behavior.
  - Column-level PostgreSQL grants (`aq_uai_runtime` having zero `DELETE` and INSERT-only access on 6 tables) turn `INV-17`/`INV-18`/`RULE-QTA-04` from an application convention into a hard database guarantee.
  - `R5` (`NO_ENTITLEMENT` blocking `base_entitlement == 0`), `R6` (`MdlModel.active AND MdlProvider.active`), `R7` (honest reset marker without fake per-user balance rows), `R8` (current-month-only CLI, no historical backfill), and `R9` (`UPPER_SNAKE` codes) are all sound, fail-closed, and internally consistent.
- **Refine / watch closely (`R1` & `R3/R4`):**
  - **`R1` (open-month-only on `GET /entitlements` vs any month on `GET /budgets` and `GET /events`):** Returning `NOT_SNAPSHOTTED` on past budgets is honest because Phase 4 stores no historical membership/quota snapshots. Keep `R1` for Phase 4; in Q5 UI, ensure switching the budget/event month viewer to a past month does **not** simultaneously pass that past month to `GET /users/{id}/entitlements` (which would `422 QTA_PERIOD_NOT_OPEN`).
  - **`R3`/`R4` (`month` in API vs `period_month` in DB/audit):** Clean in API responses (`month: "YYYY-MM"` is actually nicer for JSON consumers than a `YYYY-MM-01` date), so **keep `month` in the REST API**, while narrowing the contract test per `Q-e` below so docstrings and Phase 5 CRT do not fight substring false positives.

### 10.c Code quality and risks across `qta/`

1. **DB clock vs application clock in `ck_qta_suspensions_expiry` *(subtle risk found during Q4)*:**
   - `qta_suspensions` has `CHECK (expires_at IS NULL OR (isfinite(expires_at) AND expires_at > suspended_at))`, and `aq_uai_runtime` does **not** have `INSERT` privilege on `suspended_at` (`db/provision.py:144`), so PostgreSQL populates `suspended_at = now()` (DB transaction timestamp) while Python validates `expires_at > periods.utc_now()`.
   - In production on synchronized NTP clocks, PostgreSQL `now()` (transaction start) is `<= datetime.now(UTC)` so any `expires_at > utc_now()` satisfies `expires_at > suspended_at`. However, if an API container's clock ever drifted behind the DB server's clock (or in tests that freeze `utc_now()` into the past), an `expires_at` valid in Python would hit `ck_qta_suspensions_expiry` (`23514`). In Q4 `service.suspend_user` (`service.py:587–593`), I explicitly caught `ck_qta_suspensions_expiry` and mapped it to `422 VALIDATION_FAILED` so it can never leak a `500 DATABASE_ERROR`.
2. **Cross-operation concurrency between budget revisions (`52001`) and quota/membership writes:**
   - `record_budget_revision` takes `QTA_BUDGET_NAMESPACE = 52001`, whereas `upsert_group_quotas` and directory membership mutations do not. Under `PD-Q1`, quota/membership increases are intentionally allowed to exceed the budget cap (producing `over_allocated > 0`), so concurrent execution is equivalent to serial execution (`budget PUT` followed immediately by `quota PUT`).
   - **Important Phase 5 CRT warning:** When implementing `FR-CRT-013` (*individual credit grant cannot exceed remaining school budget*), CRT grant writes **must** acquire the **same** `QTA_BUDGET_NAMESPACE = 52001` lock as `record_budget_revision`; otherwise a concurrent budget reduction and CRT grant under `READ COMMITTED` could pass each other's checks and violate `FR-CRT-013`!
3. **Minor lock symmetry in `upsert_group_quotas` (`service.py:360–376`):**
   - `upsert_group_quotas` reads `AccountGroup` unlocked before locking `QtaQuotaGroup` `FOR UPDATE`. Even if `set_specialist_group_active(False)` commits concurrently, `PD-Q5` live evaluation ensures `AccountGroup.active == False` immediately contributes `0` everywhere, so no invariant breaks — adding `.with_for_update(read=True)` (`FOR SHARE`) on `AccountGroup` would make the `422 QTA_GROUP_NOT_ELIGIBLE` check strictly serialized too.
4. **Documentation drift in `QTA_ARCHITECTURE_AND_DECISIONS.md` §2.4 & `QTA_OPEN_DECISIONS.md` `QD11`:**
   - Line 123 of `QTA_ARCHITECTURE_AND_DECISIONS.md` and `QD11` in `QTA_OPEN_DECISIONS.md` still state `User.state == 'ACTIVE'` is required to suspend a user (`PROV`), whereas Q4 §4.2 rightly accepts any account state (`PENDING`/`ACTIVE`/`DISABLED`). Left untouched due to the §3 allowlist; listed in §10.g to align before Q5.
5. **Tenant isolation, N+1, error/audit consistency & dead code:**
   - Every table and query in `qta/` filters on `institution_id` and joins composite `(institution_id, <fk>)` keys.
   - Zero N+1 queries on `GET /qta/groups` (`_active_member_counts` + `_quotas_by_group` batch queries), `GET /qta/users` (`active_suspensions_for` batch query), `GET /qta/users/{id}/entitlements` (constant 5 queries regardless of model/group count), and `GET /qta/users/{id}/suspensions` (single `OUTER JOIN` query).
   - Zero dead code across `qta/{models,periods,entitlements,access,reset,schemas,queries,service}.py`.

### 10.d Test quality

- **Strengths:** Real disposable PostgreSQL 18 under the restricted `aq_uai_runtime` role (not SQLite or superuser); real session/Origin/CSRF HTTP calls; concurrency barrier tests on both budget revisions and suspensions; audit-rollback tests revoking `INSERT ON audit_events`; SQL statement counting via `before_cursor_execute`; and 12 total mutation proofs across Q2 (3), Q3 (4), and Q4 (5).
- **Gaps to watch:**
  1. In `test_q4_access_reset.py::test_access_decision_table_order`, `check_ai_access` short-circuiting is unit-tested with `SimpleNamespace` session stubs, while real SQL execution of `check_ai_access` is covered in `test_q4_carryover.py` and `test_q4_qta_killswitch_reset.py` for `ALLOWED`, `MODEL_UNAVAILABLE`, `SUSPENDED_PAID_EXTERNAL`, and `SUSPENDED_ALL_MODELS`. Adding one compact PostgreSQL assertion covering `USER_NOT_FOUND`, `USER_NOT_ACTIVE`, and `NO_ENTITLEMENT` directly through `check_ai_access(real_session, ...)` in Q6 would make DB-backed coverage of all 7 branches 100% explicit.
  2. Full gate runtime is now ~16.5 minutes for the 578-test API suite because every integration test provisions and migrates a fresh PostgreSQL database from `0001` to `0008`. Cloning from a pre-migrated template database (`CREATE DATABASE ... TEMPLATE aq_migrated_template`) in test fixtures could cut integration suite runtime by 60–70% without sacrificing per-test DB isolation.

### 10.e Readiness for Q5 (Admin UI) and Q6 (handoff)

The `/api/v1/qta` backend contract (22 operations across 18 paths) is **complete and ready for Q5 (`#qta` in `apps/admin/`)** with zero backend blockers:

- **Exact Q5 UI ↔ API mapping:**
  - **Header / School Monthly Budget bar & dialog:** `GET /qta/budgets?month=YYYY-MM` + `PUT /qta/budgets/{month}` (display `status_label` `"chưa ghi nhận"` when `status == "NOT_RECORDED"`, `over_allocated > 0` warning banner, revision history drawer, and `409 QTA_BUDGET_BELOW_ALLOCATED` deficit message using `details.allocated` & `details.deficit`).
  - **Tab 1 — *Nhóm & Hạn mức Mô hình*:** `GET /qta/models`, `GET /qta/groups`, `POST /qta/groups/sync`, `GET /qta/groups/sync-runs`, `POST /qta/groups`, `#qta/groups/<id>` (`GET/PATCH /qta/groups/{id}`, `POST .../activate|deactivate`, `GET/PUT/DELETE .../members`, `PUT .../quotas`). Show empty-before-sync state cleanly and badge stored quota rules where `model_active == false` (*"Mô hình / nhà cung cấp đang tắt"*).
  - **Tab 2 — *Tra cứu Cộng dồn Cá nhân & Cắt/Ngưng*:** `GET /qta/users` (shows `quota_status` badge right in the search list!), `GET /qta/users/{id}/entitlements?month=YYYY-MM` (open months only: current or next!), `GET/POST /qta/users/{id}/suspensions`, `POST /qta/users/{id}/restore`. Render additive formula breakdown, `"Chưa tích hợp đo tiêu thụ thực tế"` (`consumption_status == "NOT_INTEGRATED"`), per-model `access` badge, and distinct *Người ra lệnh* (`ordered_by`) vs *Người thực hiện* (`suspended_by`).
  - **Tab 3 — *Làm mới Đầu tháng & Nhật ký Giao dịch*:** `GET /qta/monthly-resets`, `POST /qta/monthly-resets` (when `current.status == "COMPLETED"`, disable the simulate button with *"Đã thực hiện làm mới cho tháng MM/YYYY"*), and `GET /qta/events?month=YYYY-MM&event_type=...` (read-only table with zero Edit/Delete buttons).
- **Shared frontend plumbing needed in Q5 allowlist:**
  - `apps/admin/assets/api.mjs`: allowlist numeric `allocated` and `deficit` in error `details`, and map all 9 `QTA_*` error codes to clear Vietnamese messages.
  - `apps/admin/assets/pages.mjs` & `app.mjs`: gate `#qta` visibility on `qta.read` (and hide write controls unless `qta.manage` is in the actor's permissions), and group sidebar items under *Quản trị hệ thống* vs *Quản lý AI & Chi phí*.

### 10.f Answers to the reviewer's open questions (`Q-a` .. `Q-f`)

- **`Q-a` Should `decision_date` be validated (e.g. not after today, not before some date)?**
  - *Answer:* **Validate sanity bounds only (`2000-01-01 <= decision_date <= current_local_date + 60 days`), do NOT forbid near-future dates (`> today`).**
  - *Why:* In Vietnamese university administration, a rectorate decision for next month's budget may be post-dated to the 1st of next month (or signed weeks before taking effect), whereas typos like `0026-11-01` or `2999-11-01` are genuine data-entry bugs. If institutional policy is unknown (`NEEDS-INSTITUTION`), a wide typo-guard (`year BETWEEN 2000 AND 2100`) avoids inventing business policy while catching fat-fingered years.

- **`Q-b` Should a `UNIT`-scoped viewer see the free-text suspension `reason`?**
  - *Answer:* **Yes, keep `reason` visible to the `UNIT`-scoped `AI_QUOTA_VIEWER` on own-unit users (current Q4 behavior), while keeping `qta_events.summary` free of `reason` (also current Q4 behavior).**
  - *Why:* The `UNIT`-scoped viewer represents *Trưởng đơn vị* (Dean / Department Head, `FRD` Actor phụ) overseeing staff and students in their own unit. If a lecturer in Faculty A is suspended from AI access, the Dean of Faculty A needs to know *why* and *who ordered it* (`ordered_by`) to manage the unit, whereas global event logs (`GET /qta/events`) stay scrubbed of sensitive disciplinary prose. *Trade-off:* if HR disciplinary privacy later requires redacting `reason` for unit heads (`NEEDS-INSTITUTION`), projecting `reason: str | None` as `None` for non-GLOBAL readers is a 3-line change in `queries.py`.

- **`Q-c` Scheduling the reset CLI: cron/systemd on the host, a Compose service, or only documented in the Q6 handoff? Recommend one.**
  - *Answer:* **Document a host `systemd` timer (plus equivalent `crontab` one-liner) calling `docker compose exec -T api python -m aq_uai_api.qta.reset` in the Q6 handoff — do NOT add a sleeping loop container to `infra/compose.yaml`.**
  - *Why:* `AGENTS.md` and `BLUEPRINT_v1.md` explicitly favor minimal operational moving parts over extra background daemons. Furthermore, because `R7`/`R8` enforce zero rollover structurally by calendar month even when the CLI has not run yet, a developer running `docker compose up` locally does not need an extra daemon container burning memory, and production Linux deployments strongly prefer auditable `systemd` timers (`OnCalendar=*-*-01 00:00:00`, `Persistent=true` for automatic catch-up after downtime!).

- **`Q-d` Should `GET /qta/users` include `PENDING`/`DISABLED` accounts (today: yes)?**
  - *Answer:* **Yes — keep `PENDING` and `DISABLED` accounts in `GET /qta/users`, with an optional `state` query filter if Q5 wants a quick toggle.**
  - *Why:* Excluding non-`ACTIVE` accounts from `/qta/users` would create a blind spot: an administrator could not look up why `Carol [DISABLED]` contributes `0` to `allocated` (§2.1 numerical example!), could not inspect a `DISABLED` user's past suspension history, and could not pre-suspend or restore a `PENDING`/`DISABLED` user (§4.2). Showing all unit-scoped accounts with explicit `state` and `quota_status` badges is transparent and self-explanatory.

- **`Q-e` The forbidden-word contract test (Q3 report §10.1): keep, narrow to names only, or replace? Propose the exact rule.**
  - *Answer:* **Narrow to schema property names, query/path parameter names, and enum values only (ignoring OpenAPI `description` / `title` prose), and drop the generic word `period`.** *(Q4 proved this again: writing `"computed lifecycle status"` in `SuspensionOut`'s docstring tripped `FORBIDDEN_FIELD` because `lifecycle` contains `cycle`!)*
  - *Exact proposed rule for `test_q2_contracts.py`:*
    1. Keep regex `FORBIDDEN_IDENTIFIER = re.compile(r"semester|hoc_ky|project|de_tai|exam|dot_thi|cycle|price|cost|rate|conver|token|credit|consumption", re.IGNORECASE)`.
    2. Walk every `/api/v1/qta` operation's path segments, `parameters[*].name`, `enum` values, and referenced component schema `properties.keys()`:
       - On request schemas & parameters: **zero** matches allowed.
       - On response (`Output`) schemas: allow **only** `{"actual_consumption", "consumption_status"}`; **zero** other matches allowed.
    3. Never regex-scan free-text `description` docstrings.

- **`Q-f` Next-month budgets are checked against today's live allocation. Is that the right guard, or should next month be unchecked until it starts?**
  - *Answer:* **Checking next month against today's live allocation is the RIGHT guard in Phase 4 — keep it.**
  - *Why:* Base group × model quotas (`qta_group_model_quotas`) are timeless recurring monthly rules (`FR-QTA-021`): unless an admin changes group quotas or memberships before the 1st, next month's base allocation at `00:00` on day 1 *will equal* today's live base allocation! Leaving next month unchecked would let an admin record `total_limit = 100` for next month when recurring group quotas already commit `9,000`, immediately putting next month into violation on day 1. *(Phase 5 CRT nuance: when CRT adds month-scoped ad-hoc grants to `allocated_for_month(db, institution_id, period_month)`, December's budget check will naturally include recurring base quotas + December CRT grants, excluding November CRT grants!)*

### 10.g Prioritized modifications recommended (`Must` / `Should` / `Could`)

- **Must (before or at the start of Q5 — tiny doc alignment):**
  1. **Align `QTA_ARCHITECTURE_AND_DECISIONS.md` §2.4 line 123 & `QTA_OPEN_DECISIONS.md` `QD11` with Q4 §4.2** (replace `User.state == 'ACTIVE'` target requirement with *"any account state in the institution; quota status is independent of directory account state"*). *Files:* `docs/phase4/QTA_ARCHITECTURE_AND_DECISIONS.md`, `docs/phase4/QTA_OPEN_DECISIONS.md`. *Effort:* 5 min. *Risk:* Zero (docs only).
- **Should (in Q5 or Q6):**
  2. **Replace raw-JSON docstring scanning in `test_q2_contracts.py` with the identifier/enum rule in `Q-e`.** *File:* `apps/api/tests/unit/test_q2_contracts.py`. *Effort:* 15 min. *Risk:* Low (strictly tighter on real identifiers, eliminates substring traps like `lifecycle`).
  3. **Add `FOR SHARE` on `AccountGroup` in `service.upsert_group_quotas`.** *File:* `apps/api/src/aq_uai_api/qta/service.py`. *Effort:* 5 min. *Risk:* Very low (lock order `AccountGroup` → `QtaQuotaGroup` matches `sync_groups` / `_load_specialist_for_qta`).
  4. **Add an optional `state: AccountState | None = None` filter to `GET /qta/users` (`QtaUserFilters(SearchParams)`)** if Q5 UI benefits from filtering `ACTIVE` users while keeping all states searchable by default (`Q-d`). *Files:* `qta/schemas.py`, `qta/queries.py`, `api/v1/qta.py`. *Effort:* 10 min. *Risk:* Low (purely additive optional query parameter).
- **Could (in Q6 or test-infra cleanup):**
  5. **Template-database cloning (`CREATE DATABASE ... TEMPLATE`) in PostgreSQL integration fixtures** to cut the 16.5-minute full-gate runtime by >60% while keeping full per-test DB & role isolation. *File:* `apps/api/tests/integration/test_wp2_database.py` (when allowlisted). *Effort:* 30 min. *Risk:* Medium (touches shared test harness; do only in a dedicated infra/Q6 step).

---

## 11. Reviewer response

*Reviewer: Claude Code, 2026-11-27. This is a technical review, not formal acceptance (formal QTA acceptance stays 0).*

### 11.1 Verdict

**Approved for continued development.** Q4 and carry-overs C1–C4 are correct, stayed inside the allowlist, and are reproduced independently. One documentation finding (mine, now fixed) and two test nits carry into Q5.

### 11.2 Independent verification

| Check | Result |
| --- | --- |
| `sha256sum -c hashes-after.txt` against the working tree | All files match (evidence matches what is on disk) |
| `changed-files.txt` vs the §3 allowlist | Every entry is allowlisted, except `test_q3_qta_lookup_budgets.py` (PO-authorized amendment; the edit is limited to the key set, comment and one `ACTIVE` assertion, as authorized) and `QTA_Q3_REPORT.md` (the reviewer's own §11) |
| Mutation-proof hashes | The four post-restore hashes in §7.2 equal `hashes-after.txt` |
| Full gate, reviewer's run (`~/.cache/aqm7/gate.sh`, disposable PostgreSQL) | **API 578 passed, 1 skipped; browser 16 passed; exit 0** — identical to `final-gate.log` |
| CLI smoke | Not re-run by the reviewer. Covered indirectly by `test_reset_cli_idempotent_and_no_backfill` and `test_manual_then_scheduled_same_month_is_noop` in the gate; `cli-smoke.log` remains implementer-reported |
| Not verified | Hosted CI on Q4 (uncommitted), live Compose, a real OS scheduler |

### 11.3 Code review notes (what was checked)

- `access.py`: the decision table is one function (`evaluate_access_rule`), used by both `check_ai_access` and the lookup, so the two cannot drift. Lazy expiry uses the single `periods.utc_now()` seam. `active_suspensions_for` is one set-based query.
- `service.suspend_user` / `restore_user`: the lock order is institution (shared) → account locks (`user_id` + `P.QTA_MANAGE` passed to `protected`, so the target is scope-checked before waiting) → `52002` exclusive → insert. The operator always comes from `authority.actor_id`. `ck_qta_suspensions_expiry` is mapped to 422. The restore unique-violation is mapped to 409.
- `reset.py`: the manual path holds `41001` (shared) then `52003`; the CLI holds only `52003`, so there is no lock-order inversion. One transaction per institution; month computed once; generic stderr on failure. The `IntegrityError → RuntimeError` branch is unreachable under the lock (harmless).
- C1 is applied at all five call sites. C2: totals and `allocated` both come from `_qualifying_quota_rows`. C3: the optional field keeps old audit JSON readable. C4: the deadline is now wall-clock bounded.
- `db/provision.py` grants confirm `suspended_at` is not insertable by the runtime role, so Carbon's §10.c.1 reasoning is correct.

### 11.4 Findings

| ID | Severity | Finding | Action |
| --- | --- | --- | --- |
| F-Q4-1 | Doc (reviewer's own error) | The Q4 prompt §4.2 changed the PROV rule to "any account state may be suspended", but did not allowlist `QTA_ARCHITECTURE_AND_DECISIONS.md` §2.4 or `QTA_OPEN_DECISIONS.md` QD11, which still said "target must be ACTIVE". | **Fixed by the reviewer** in both files (provenance: PROV, reviewer decision in the Q4 prompt; the QD11 NEEDS-INSTITUTION question about PENDING accounts is kept). |
| F-Q4-2 | Nit (test) | The lookup `contributions` breakdown decides group eligibility in Python (`_excluded_reason`), separately from the SQL total. Today they agree, but no test pins `sum(contributes) == base_entitlement`. | Q5 carry-over **C6**. |
| F-Q4-3 | Nit (test) | `USER_NOT_FOUND`, `USER_NOT_ACTIVE` and `NO_ENTITLEMENT` are proven through `check_ai_access` only with stubs (Carbon's §10.d.1). | Q5 carry-over **C7**. |

Process note: Q3 was not committed before Q4 started, against the Q4 prompt's "Before pasting" note. Carbon handled this correctly (the hash manifests isolate the Q4 delta, §9). Q3 + Q4 should be committed together before Q5.

Carbon's allowlist stop (test key-set conflict) was exactly the intended behaviour; the gap was in the prompt, not the implementation.

### 11.5 Response to §10 (whole-module review)

| Item | Reviewer position |
| --- | --- |
| 10.a coverage | **Agree.** API/DB for all Must FRs is done; every UI AC is open until Q5 — matches the acceptance matrix. |
| 10.b keep R1–R9 | **Agree.** The R1 UI caution (do not pass a past month to `/entitlements`) is built into Q5 as R13. |
| 10.c.1 DB vs app clock | **Agree.** The 422 mapping is the right safety net. No further change. |
| 10.c.2 CRT must take `52001` | **Agree, important.** Record it in the Q6 handoff and the Phase 5 CRT plan: any write that checks against the school budget (FR-CRT-013) must take `QTA_BUDGET_NAMESPACE` in the same transaction. |
| 10.c.3 `FOR SHARE` on `AccountGroup` | **Accept for Q6, after a lock-order check.** The lock order of `set_specialist_group_active` and `sync_groups` must be confirmed first, so the new lock cannot invert it; no invariant is broken today (PD-Q5 live evaluation). |
| 10.c.4 doc drift | **Done** (F-Q4-1). |
| 10.d.1 DB-backed access branches | **Accept** → C7 in Q5. |
| 10.d.2 template-database cloning | **Defer (Could, Q6 or later).** Worthwhile (the gate is ~15–17 min), but it changes the shared test harness and must be its own reviewed step. |
| 10.e Q5 readiness and mapping | **Agree; adopted** as the basis of `QTA_Q5_PROMPT.md`. The sidebar regrouping is deferred (R10, Q-h) because it changes navigation that existing browser tests rely on. |
| Q-a `decision_date` | **Partly agree.** A "today + 60 days" bound is an institutional rule we must not invent. At most a typo guard (year 2000–2100), recorded as NEEDS-INSTITUTION; not scheduled until the PO asks. |
| Q-b UNIT viewer sees `reason` | **Agree** (current behaviour, PROV). Privacy of disciplinary text stays a NEEDS-INSTITUTION question. |
| Q-c scheduling | **Agree:** a host systemd timer (or crontab) documented in the Q6 handoff, no daemon container. Addition: state the time zone explicitly (`OnCalendar=*-*-01 00:05:00 Asia/Ho_Chi_Minh`), so the run never depends on the host time zone. |
| Q-d all account states in `/qta/users` | **Agree.** The optional `state` filter only if the Q5 UI proves it needs one (it is not in Q5 scope). |
| Q-e forbidden-word test | **Agree with narrowing, with two corrections:** (1) match **whole words** of the snake_case and camelCase identifiers, not substrings — Carbon's proposed regex would hit `rate` in "generate" and `exam` in "example"; (2) **keep `period` forbidden** in API identifiers, since that is what enforces R3 (`month`). Exact rule → Q5 carry-over **C5**. |
| Q-f next-month check | **Agree.** Keep it. |
| 10.g Must/Should/Could | Must 1 done (F-Q4-1). Should 2 → C5 (Q5). Should 3 → Q6 after the lock-order check. Should 4 → not scheduled. Could 5 → deferred. |

### 11.6 Backlog carried forward

- **Q5** (`QTA_Q5_PROMPT.md`): C5 (forbidden-word rule), C6 (breakdown = total), C7 (DB-backed access branches), plus the Admin UI.
- **Q6:**
  - `FOR SHARE` on `AccountGroup` (after the lock-order check).
  - Scheduler runbook with an explicit time zone.
  - CRT `52001` lock note.
  - Q-g actor display names (if adopted).
  - Optional template-database fixtures.
  - The Q6 items already in the plan: the FR-MDL-020 AC3 runtime proof, backup/restore, the `0006 → 0008` populated-upgrade rehearsal, and the handoff.
