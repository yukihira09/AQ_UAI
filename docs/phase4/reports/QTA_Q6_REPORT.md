# AQ EduUAI — Phase 4 QTA Stage Q6 Report

## 1. Summary

**Status:** implemented, awaiting review.
Phase 4 Stage **Q6** (the final QTA stage, base commit `accf694`) delivered the end-to-end `FR-MDL-020 AC3` cross-module isolation proof with a populated QTA (`4.1`), automated populated `0006 → 0008` upgrade rehearsal (`4.2`), automated Q1–Q6 end-to-end `pg_dump`/`pg_restore` backup-and-restore browser test (`4.3`), the three Q5-review UI wording/timezone fixes (`4.4`), the Phase 4 operational handoff [qta-handoff.md](../qta-handoff.md) (`4.5`), and full Phase 4 documentation closure (`4.6`).
Full verification gate ([final-gate.log](q6/final-gate.log)): **API `583 passed, 1 skipped`** (+2 over baseline `581`) and **browser `21 passed`** (+1 over baseline `20`), exit `0`, plus **3/3 mutation proofs** passed with byte-identical post-restore SHA256 hashes.
Zero backend source (`apps/api/src/`), migration, `mdl.mjs`, or `apps/web/` edits were made; no Docker command, commit, push, or deployment was executed.
Technical verification is not formal acceptance: `docs/acceptance-matrix.md` remains **`0/33`** and `ADR-0004` remains **Proposed**.

---

## 2. Files

Every created or modified file stays strictly within `QTA_Q6_PROMPT.md` §3 and matches [changed-files.txt](q6/changed-files.txt) (plus root-level `CLAUDE.md`, which is in §3 and `git-status-after.txt` — see §10 `Q-l` on why the §2 `find` path list excludes root-level files):

| File | Action | Purpose |
| --- | --- | --- |
| `apps/api/tests/integration/test_q6_mdl_qta_isolation.py` | Created | **4.1 / R17:** `FR-MDL-020 AC3` populated-QTA isolation proof, positive control & reverse direction |
| `apps/api/tests/integration/test_q6_qta_upgrade.py` | Created | **4.2 / R18:** Populated `0006 → 0008` upgrade, idempotent re-run, privilege matrix & live post-upgrade API |
| `tests/browser/test_qta_operations.py` | Created | **4.3 / R18:** Full Q1–Q6 population, mode-600 `pg_dump`/`pg_restore`, restored `#qta` Chromium UI, post-restore write & constraints |
| `apps/admin/assets/qta.mjs` | Modified | **4.4 / R20:** Wording fixes (`NO_ENTITLEMENT` → `"Không có hạn mức"`, `ACTIVE` → `"Được dùng AI"`, `SUSPENDED` → `"ĐÃ CẮT"`) |
| `tests/browser/test_qta.py` | Modified | **4.4 / R20:** `timezone_id="Asia/Ho_Chi_Minh"`, updated label assertions + user-list `"ĐÃ CẮT"` assertion |
| `docs/phase4/qta-handoff.md` | Created | **4.5:** Complete Phase 4 operational handoff (sections 1–9, 26-row manual checklist, scheduler runbook, CRT notes, evidence table) |
| `docs/phase4/QTA_IMPLEMENTATION_PLAN.md` | Modified | **4.6:** Added `Q6 completion` and `Phase 4 technical closure` |
| `docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md` | Modified | **4.6:** Updated coverage table to Q6 technically verified status (formal acceptance stays `0/33`) |
| `docs/phase3/MDL_REQUIREMENTS_TRACEABILITY.md` | Modified | **4.6:** Updated `FR-MDL-020 AC3` rows only with populated-QTA proof (`test_q6_mdl_qta_isolation.py`) |
| `docs/phase4/QTA_OPEN_DECISIONS.md` | Modified | **4.6:** Recorded `Q-g` and `Q-h` defaults with provenance `"reviewer default, PO may override"` |
| `docs/architecture/ADR-0004-qta.md` | Modified | **4.6:** Updated status/date lines to Q0–Q6 implemented & technically verified (stays **Proposed**) |
| `docs/PROJECT_CONTEXT.md` | Modified | **4.6:** Updated QTA status and links to `qta-handoff.md` & `QTA_Q6_REPORT.md` |
| `docs/acceptance-matrix.md` | Modified | **4.6:** Recorded Q6 technical verification across `FR-QTA-001..050` and `FR-MDL-020 AC3`; formal acceptance stays `0/33` |
| `CLAUDE.md` | Modified | **4.6:** Updated current-work line to Q6 awaiting review (root-level file; verified in `git-status-after.txt`) |
| `docs/phase4/reports/QTA_Q6_REPORT.md` & `docs/phase4/reports/q6/*` | Created | Stage Q6 report, preflight/postflight manifests, focused/final/mutation logs |

---

## 3. FR-MDL-020 AC3 isolation proof

Implemented in `apps/api/tests/integration/test_q6_mdl_qta_isolation.py::test_mdl_connection_tests_and_routing_leave_populated_qta_untouched` (**R17**):

- **What "balance" means while consumption is `NOT_INTEGRATED`:** Because AI invocation metering is out of scope in Phase 4 (`actual_consumption: null`, `remaining_quota: null`, `consumption_status: "NOT_INTEGRATED"`), "the tester's quota balance is unchanged" means the tester's live additive `base_entitlement` (and `base_entitlement_total`), institutional `allocated`, QTA events, and every row in all 8 `qta_*` tables remain unchanged.
- **Populated QTA setup:** Using the `m4` loopback HTTPS fake provider (zero external traffic), the MDL admin (`db.manager_id`) is placed in both a synced `SYSTEM` group (`G_Q6_SYS`, `1,000`) and an `AI_SPECIALIST` group (`AI_Q6_SPEC`, `3,000`) on `q6-primary`, giving a live additive `base_entitlement` of **`4,000`** `đơn vị hạn mức` (`allocated = 4,000`). Setup also records a monthly budget revision (`QD-Q6-ISO-01`), suspends and restores another user, and executes a manual monthly reset so **all 8 `qta_*` tables** have `>= 1` row (asserted before step b).
- **Snapshots compared BEFORE and AFTER:** (1) `GET /qta/users/{manager_id}/entitlements?month=2026-11`, (2) `GET /qta/budgets?month=2026-11`, (3) `GET /qta/events?month=2026-11`, and (4) an ordered full-column `to_jsonb(t)` dump of all 8 `qta_*` tables.
- **MDL operations executed under `install_write_log(db)`:**
  1. Failing connection test (`db.provider.mode = "auth"` → `FAILED` / `AUTH_FAILED`) on `q6-primary`.
  2. Passing connection test (`db.provider.mode = "ok"` → `PASSED`) on `q6-primary`.
  3. Primary + fallback routing change (`PUT /api/v1/mdl/routing`, `primary=q6-primary`, `fallback=q6-fallback`, `decision_reference="QD-MDL-Q6-01"`).
- **Written-table sets observed:**
  - After MDL operations: subset of `{"mdl_connection_tests", "mdl_routing", "mdl_routing_revisions", "audit_events", "auth_sessions"}` (containing `mdl_connection_tests`, `mdl_routing`, `mdl_routing_revisions`, `audit_events`) and **zero `qta_*` tables**. All four BEFORE/AFTER QTA snapshots are byte-identical (`==`).
  - **Positive control (step d):** With the same triggers installed, suspending `other_user_2` records `qta_suspensions` and `qta_events` in `written(db)` (proven non-vacuous by Mutation Proof #3).
  - **Reverse direction (step e):** Advancing frozen `periods.utc_now` to `2026-12-01`, clearing `zz_write_log`, and executing a QTA write burst (`PUT /qta/budgets/2026-12`, `PUT /qta/groups/{id}/quotas`, suspend, restore, `POST /qta/monthly-resets`) records `{"qta_budget_revisions", "qta_group_model_quotas", "qta_suspensions", "qta_suspension_restorations", "qta_monthly_resets", "qta_events"}` in `written(db)` and **zero `mdl_*` tables**.

---

## 4. Upgrade and backup/restore rehearsals

### 4.1 Populated `0006 → 0008` upgrade (`apps/api/tests/integration/test_q6_qta_upgrade.py`, R18)
- **Steps:** Upgraded a fresh disposable PostgreSQL 18 DB to `0006_mdl_routing_and_styles` only; seeded 12 pre-QTA tables (`app_metadata`, `institutions`, `units`, `users` in `ACTIVE`/`PENDING`/`DISABLED` states, `user_credentials`, `account_groups` of kinds `SYSTEM`/`AI_SPECIALIST`/`AUTHORIZATION`, `group_memberships`, `user_role_assignments`, `mdl_providers`, `mdl_models`, `mdl_routing`, `audit_events`); dumped all 12 tables; ran `prepare` → `migrate` (`0006 → 0008_qta_schema`) → `alembic check`; ran `prepare` + `migrate` + `alembic check` a second time (idempotency); mounted the real FastAPI app under `aq_uai_runtime` and exercised role grant → empty `/qta/groups` check → sync → quotas → lookup → budget `allocated`.
- **Compared & verified:**
  - All 12 pre-QTA tables are row-for-row byte-identical after both the first and second upgrade runs.
  - `alembic_version == "0008_qta_schema"` and `alembic check` passes cleanly.
  - All 8 `qta_*` tables exist and hold `0` rows before sync (`FR-QTA-001 AC2`).
  - `qta.read`, `qta.manage`, `AI_QUOTA_ADMIN`, and `AI_QUOTA_VIEWER` exist from `0007`; zero users or groups received QTA roles implicitly.
  - `aq_uai_runtime` holds **exact** `QTA_RUNTIME_PRIVILEGES` at table and column level (zero `DELETE` on all 8 tables, zero `UPDATE` on the 6 INSERT-only tables, live `DELETE` denied with `InsufficientPrivilege`).
  - Post-upgrade API sync enrolled both `G_GV_PRE` (`SYNC`) and `AI_LAB_PRE` (`SPECIALIST`) while ignoring `AUTH_PRE`; additive lookup returned `4,000` (`1,000 + 3,000`) and institutional `allocated == 4,000` (with `PENDING` and `DISABLED` members contributing `0`).

### 4.2 QTA backup / restore (`tests/browser/test_qta_operations.py`, R18)
- **Steps:** Populated the full Q1–Q5 journey through the live nginx + FastAPI stack (sync, `G1` + `G2` specialist group, per-model quotas, 409 deficit check `{allocated: 4500, deficit: 1500}`, 2 append-only school budget revisions `QD-Q6-BK-01` & `QD-Q6-BK-02`, suspension + restoration, manual monthly reset, and events); snapshotted all 8 `qta_*` tables (each `>= 1` row, `qta_budget_revisions == 2`); ran `pg_dump --format=custom` to a mode-`0600` file under `tmp_path`; restored via `pg_restore --no-owner --no-privileges --single-transaction --exit-on-error` into a brand-new database; ran `provision`, `migrate`, `alembic check`; booted a fresh API + nginx stack against the restored database; verified `#qta` in Chromium and deleted the dump file in `finally`.
- **Compared & verified:**
  - All 8 `qta_*` tables are row-for-row SHA256-identical before dump and after restore.
  - Restored `#qta` UI renders `8.000 đơn vị hạn mức`, `4.500 đơn vị hạn mức` allocated, `3.500 đơn vị hạn mức` remaining, both revisions (`QD-Q6-BK-02`, `QD-Q6-BK-01`), additive `1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn mức`, `"Chưa tích hợp đo tiêu thụ thực tế"`, restored suspension history (`Khôi phục trước khi sao lưu`), and `Đã làm mới` (`COMPLETED`) with disabled reset button.
  - Post-restore runtime write succeeds (`POST /qta/users/{stacked}/suspensions` → `201` and user list shows **`ĐÃ CẮT`**).
  - Append-only survives restore (`DELETE FROM qta_events` as `restored.runtime` raises `InsufficientPrivilege`).
  - Uniqueness survives restore (`POST /qta/monthly-resets` returns `409 QTA_RESET_ALREADY_EXECUTED`).

---

## 5. UI wording fixes

Applied strictly to `apps/admin/assets/qta.mjs` and `tests/browser/test_qta.py` (**R20**):

### Label changes (`apps/admin/assets/qta.mjs`)
| Constant / key | Before | After | Why |
| --- | --- | --- | --- |
| `quotaStatusLabels.ACTIVE` | `'Đang hoạt động'` | `'Được dùng AI'` | Disambiguates quota status column from account state column (`'Đang hoạt động'`) |
| `quotaStatusLabels.SUSPENDED` | `'Đang tạm ngưng'` | `'ĐÃ CẮT'` | Matches canonical FRD (`FR-QTA-040 AC1`) badge wording |
| `accessReasonLabels.NO_ENTITLEMENT` | `'Không có hạn mức (NO_ENTITLEMENT)'` | `'Không có hạn mức'` | Drops raw internal enum code from user-facing UI |

### Edited assertions (`tests/browser/test_qta.py`)
| Line(s) | Before | After | Why |
| --- | --- | --- | --- |
| 118 (`sign_in_new_browser`) | `browser.new_context(locale="vi-VN")` | `browser.new_context(locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")` | Aligns role-holder Chromium context timezone with `AQ_UAI_INSTITUTION_TIMEZONE` |
| 499 (`test_qta_budget_deficit_additive_and_mobile`) | `expect(solo_ext_row).to_contain_text("NO_ENTITLEMENT")` | `expect(solo_ext_row).to_contain_text("Không có hạn mức")` + `expect(solo_ext_row).not_to_contain_text("NO_ENTITLEMENT")` | Verifies clean Vietnamese label and absence of raw code |
| 558–559 (`test_qta_killswitch_restore_reset_and_events`) | `expect(qta_page.locator("main")).to_contain_text("Đang tạm ngưng")` | `expect(qta_page.locator("main")).to_contain_text("ĐÃ CẮT")` + `expect(qta_page.locator("tr", has_text="q5.target")).to_contain_text("ĐÃ CẮT")` | Verifies `ĐÃ CẮT` in both detail panel and user list row |

---

## 6. Tests

| Test file & name | Status | FR / AC / Rule covered |
| --- | --- | --- |
| `apps/api/tests/integration/test_q6_mdl_qta_isolation.py::test_mdl_connection_tests_and_routing_leave_populated_qta_untouched` | New (PASS) | `FR-MDL-020 AC3` (end-to-end with populated QTA, positive control & reverse direction) |
| `apps/api/tests/integration/test_q6_qta_upgrade.py::test_populated_0006_upgrades_to_0008_preserves_data_and_enables_qta` | New (PASS) | `FR-QTA-001 AC2`, `FR-QTA-020`, `FR-QTA-021`, `FR-QTA-030`, `FR-QTA-050 AC2`, `RULE-QTA-04` (populated `0006→0008` upgrade, idempotency, grants, live API) |
| `tests/browser/test_qta_operations.py::test_qta_backup_restore_preserves_state_ui_writes_and_constraints` | New (PASS) | `FR-QTA-010`, `FR-QTA-011`, `FR-QTA-020..050`, `RULE-QTA-01..05` (full Q1–Q6 end-to-end + `pg_dump`/`pg_restore` + restored `#qta` UI + post-restore write & append-only/uniqueness guards) |
| `tests/browser/test_qta.py` (4 existing tests, wording/timezone updates in §4.4) | Edited (4 PASS) | `FR-QTA-001..050` UI ACs (including `FR-QTA-031 AC2` clean `"Không có hạn mức"` and `FR-QTA-040 AC1` `"ĐÃ CẮT"` in user list & detail) |

---

## 7. Results

### 7.1 Baseline vs Final Gate

| Check | Baseline (`baseline-gate.log`, `accf694`) | Final (`final-gate.log`) | Delta / Notes |
| --- | --- | --- | --- |
| `scripts/verify_frontend_assets.py` | PASS (`10 assets exist`) | PASS (`10 assets exist`) | `apps/web/` untouched |
| `node --test scripts/test_sidebar_navigation.cjs` | `1 passed` | `1 passed` | Unchanged |
| `node --check` (`apps/web/**/*.js`, `apps/admin/assets/*.mjs`) | PASS | PASS | Clean |
| `ruff check` (API src/tests/migrations/scripts/demo-provider + `tests/browser`) | `All checks passed!` (×2) | `All checks passed!` (×2) | Clean |
| `scripts/verify_wp2_compose.py --env-file .env.example` | PASS | PASS | Unchanged |
| `alembic upgrade head` (`0001 → 0008_qta_schema`) & `alembic check` | `No new upgrade operations detected.` | `No new upgrade operations detected.` | Head unchanged (`0008_qta_schema`) |
| Focused Q6 suite (`focused-tests.log`) | — | **2 API + 5 browser passed** (exit 0) | `18.05s` API + `90.09s` browser |
| **Full API suite (`apps/api/tests`)** | **581 passed, 1 skipped** (931.24s) | **583 passed, 1 skipped** (958.55s) | **+2 passed** (`test_q6_mdl_qta_isolation.py`, `test_q6_qta_upgrade.py`) |
| **Full Browser suite (`tests/browser`)** | **20 passed** (255.10s) | **21 passed** (279.33s) | **+1 passed** (`test_qta_operations.py`; zero flakes) |

### 7.2 Mutation Proofs ([mutation-proof.log](q6/mutation-proof.log))

| # | Mutated file & temporary break | Test run | Observed failure | Pre-mutation == Post-restore SHA256 |
| --- | --- | --- | --- | --- |
| 1 | `apps/api/src/aq_uai_api/db/provision.py`: added `DELETE` to `qta_events` in `QTA_RUNTIME_PRIVILEGES` | `test_q6_qta_upgrade.py` | **FAIL (exit 1, 8.06s):** `AssertionError: ('qta_events', 'DELETE') — assert (True,) == (False,)` | `d619576cf610c5ba2e12cb783f44f633050293549f0cd67e221f26e318a61af1` |
| 2 | `apps/admin/assets/qta.mjs`: reverted `quotaStatusLabels.SUSPENDED` to `'Đang tạm ngưng'` | `test_qta.py -k test_qta_killswitch_restore_reset_and_events` | **FAIL (exit 1, 20.37s):** `AssertionError: Locator expected to contain text 'ĐÃ CẮT'` | `99188624ccd4cdff340e3221c70b91e3f730e31cff7a0c54f3fb7fb92e0fc909` |
| 3 | `apps/api/tests/integration/test_q6_mdl_qta_isolation.py`: removed positive-control QTA suspend write in step d | `test_q6_mdl_qta_isolation.py` | **FAIL (exit 1, 10.02s):** `AssertionError: set()` on `assert any(name.startswith("qta_") for name in control_written)` | `c0f599d81b0ce0e3ee73ef083be545bcef844a77a79d6afc50be555babcf0872` |

---

## 8. Decisions and deviations

- **Q-g (actor names in history tables — *reviewer default, PO may override*):** Applied default — zero API change in Phase 4; actors stay UUIDs (`<code>`, `"Bạn"` for self), consistent with MDL and documented in `qta-handoff.md` §7 and `QTA_OPEN_DECISIONS.md`.
- **Q-h (sidebar regrouping — *reviewer default, PO may override*):** Applied default — flat sidebar kept, documented as a known cosmetic deviation from the FRD menu path in `qta-handoff.md` §7 and `QTA_OPEN_DECISIONS.md`.
- **R17 (FR-MDL-020 AC3):** Proven end-to-end with all 8 `qta_*` tables populated, a `4,000`-entitlement MDL tester, statement-level write triggers, positive control, and reverse-direction burst; explicitly states that "balance" means `base_entitlement` while consumption is `NOT_INTEGRATED`.
- **R18 (Automated rehearsals, no Docker):** Both `0006 → 0008` populated upgrade and `pg_dump`/`pg_restore` are automated gate tests; no Docker commands were executed.
- **R19 (`FOR SHARE` lock analysis only):** `qta/service.py` was not modified; full lock-order map and recommendation are in §10 `Q-i`.
- **R20 (Wording fixes only):** Limited strictly to the three label fixes and `timezone_id` + matching assertions in `qta.mjs` and `test_qta.py`.
- **No deviations** from the §3 file allowlist or §1 hard rules.

---

## 9. Open questions / risks / NOT verified

The following items were **NOT verified** in Q6 and remain separate evidence categories:

- **Hosted GitHub Actions CI:** Not run on Q6 (changes are local and uncommitted).
- **Docker Compose rehearsal on a disposable stack:** Explicitly excluded for the implementing agent by `R18` (reviewer's option).
- **Live upgrade on the developer's `aq-uai-dev` stack:** Untouched per §1 hard rules (`0006 → 0008` rehearsed only by `test_q6_qta_upgrade.py`; manual runbook in `qta-handoff.md` §3).
- **Real OS scheduler (`systemd` timer / `cron`):** Documented in `qta-handoff.md` §5, **not executed** on a host scheduler (CLI itself verified directly in Q4).
- **Browsers other than Chromium** (Firefox, Safari/WebKit) and assistive-technology screen-reader testing.
- **Opt-in live external AI provider check:** Skipped (`1 skipped` in API suite, matching baseline).
- **Formal PO / Tech Lead / institutional acceptance:** None recorded (`0/33` in `docs/acceptance-matrix.md`; `ADR-0004` stays **Proposed**).
- **Institutional policy items still open (`NEEDS-INSTITUTION` / `PROV`):** real consumption metering & pricing (`QD3`/`QD10`), `PENDING`-account suspension policy (`QD11`), `decision_date` bounds (`Q-a`), `UNIT` viewer visibility of free-text suspension `reason` (`Q-b`), and pagination beyond 100 active models in the `#qta` quota matrix.

---

## 10. Implementer's review

- **`Q-i` (R19 — lock-order map and `FOR SHARE` on `AccountGroup` in `upsert_group_quotas`):**
  - **Actual lock order across the four write paths (with `file:line`):**
    1. **`upsert_group_quotas`** (`apps/api/src/aq_uai_api/qta/service.py:356-491`):
       - `qta/service.py:363` → `authorization/writes.py:59` (`INSTITUTION_NAMESPACE = 41001`, **SHARED**) → `authorization/writes.py:74` (`lock_accounts` on `{actor_id}`, **EXCLUSIVE**)
       - `qta/service.py:365-371` (`AccountGroup` read — currently unlocked; proposed `FOR SHARE`)
       - `qta/service.py:372-379` (`QtaQuotaGroup` **`FOR UPDATE`**)
       - `qta/service.py:412-420` (`QtaGroupModelQuota` **`FOR UPDATE`**, ordered by `model_id`)
       - `qta/service.py:437, 472` (`INSERT`/`UPDATE QtaGroupModelQuota`, implicit FK `FOR KEY SHARE` on `QtaQuotaGroup` and `MdlModel`)
    2. **`set_specialist_group_active`** (`apps/api/src/aq_uai_api/qta/service.py:325-334`) and directory **`set_group_active`** (`apps/api/src/aq_uai_api/directory/service.py:457-462`):
       - `qta/service.py:329` / `directory/service.py:458` → `authorization/writes.py:59` (`INSTITUTION_NAMESPACE = 41001`, **EXCLUSIVE** because `changes_authority=True`!) → `authorization/writes.py:74` (`lock_accounts` on `{actor_id}`, **EXCLUSIVE**)
       - `qta/service.py:331` (`_load_specialist_for_qta` at `qta/service.py:63-76`, unlocked reads) / `directory/service.py:459` (`_group` unlocked)
       - `directory/service.py:451-452` + flush (`qta/service.py:333` / commit): `UPDATE AccountGroup` acquires row lock **`FOR NO KEY UPDATE`** on `AccountGroup`.
    3. **`sync_groups`** (`apps/api/src/aq_uai_api/qta/service.py:82-268`):
       - `qta/service.py:93` → `authorization/writes.py:59` (`41001`, **SHARED**) → `authorization/writes.py:74` (`{actor_id}`, **EXCLUSIVE**)
       - `qta/service.py:95` (`QTA_SYNC_NAMESPACE = 52000`, **EXCLUSIVE**)
       - `qta/service.py:98-106` (unlocked `SELECT AccountGroup`)
       - `qta/service.py:110-116` (`QtaQuotaGroup` **`FOR UPDATE`**, ordered by `group_id`)
       - `qta/service.py:165` (`db.flush()` on new `QtaQuotaGroup` inserts acquires PostgreSQL FK **`FOR KEY SHARE`** on `AccountGroup`).
    4. **Directory & specialist membership writes** (`directory/service.py:512-520` `set_membership`, `qta/service.py:337-353` `set_specialist_membership`):
       - `directory/service.py:515` / `qta/service.py:341` → `authorization/writes.py:59` (`41001`, **EXCLUSIVE** because `changes_authority=True`!) → `authorization/writes.py:74` (sorted `lock_accounts` on `{actor_id, user_id}`, **EXCLUSIVE**)
       - `directory/service.py:496-500` (`INSERT`/`UPDATE GroupMembership`, implicit FK `FOR KEY SHARE` on `AccountGroup` and `User`).
    5. *(Related shared-institution writers checked too:* `directory/service.py:430-437` `update_group` and `qta/service.py:307-322` `update_specialist_group` both take `41001` **SHARED** → `AccountGroup` **`FOR UPDATE`** (`directory/service.py:119`, `qta/service.py:68`) and never lock `QtaQuotaGroup`.)
  - **Safety (lock-order inversion):** Adding `FOR SHARE` on `AccountGroup` in `upsert_group_quotas` would be **deadlock-free (safe)**: (a) `set_specialist_group_active`, `directory.set_group_active`, and membership writes all hold `41001` **EXCLUSIVE** so they cannot run concurrently with `upsert_group_quotas` (`41001` **SHARED**); (b) `sync_groups` acquires only implicit FK `FOR KEY SHARE` on `AccountGroup`, which PostgreSQL treats as compatible with `FOR SHARE`; and (c) `update_group` / `update_specialist_group` lock `AccountGroup` (`FOR UPDATE`) and never take any lock on `QtaQuotaGroup`.
  - **Recommendation: No — do not add `FOR SHARE` on `AccountGroup` in `upsert_group_quotas`.** Tracing the real lock graph proves that `INSTITUTION_NAMESPACE = 41001` (`SHARED` vs `EXCLUSIVE`) **already strictly serializes every mutation of `AccountGroup.active`** against `upsert_group_quotas`. Adding `FOR SHARE` provides zero additional correctness protection today while introducing unnecessary blocking against concurrent harmless `PATCH` group renames (`changes_authority=False`). Only revisit if `set_group_active` is ever relaxed to `changes_authority=False`.

- **`Q-j` (Is anything in QTA still missing for the FRD's `Must` scope — API, UI, or tests?):**
  - **Nothing found.** All 12 `Must` requirements (`FR-QTA-001`..`FR-QTA-050`, 25 ACs), all 5 `RULE-QTA-*` invariants, and cross-module `FR-MDL-020 AC3` have real DB/API/CLI/UI implementation and automated verification (unit, integration, concurrency, upgrade, backup/restore, Playwright, and 15 cumulative mutation proofs across Q2–Q6). Remaining open items (`Should` exceptions/prices, `Could` two-ledger accounting, real consumption metering, actor display names, sidebar tree regrouping, institutional policy inputs) are outside `Must` scope and documented in `qta-handoff.md` §7.

- **`Q-k` (What should Phase 5 CRT watch out for when building on QTA? — 5 points):**
  1. **Acquire `QTA_BUDGET_NAMESPACE = 52001` on `FR-CRT-013` writes:** Every CRT top-up/grant checked against the monthly school cap must take `52001` exclusive in the same transaction as its check and insert, matching `qta/service.py::record_budget_revision`.
  2. **Join net CRT monthly grants into `entitlements.allocated_for_month`:** Parameterize `allocated_for_month(db, institution_id, period_month)` so `FR-QTA-011` (`409 QTA_BUDGET_BELOW_ALLOCATED`) and `FR-CRT-013` evaluate recurring QTA base entitlements + month-scoped CRT grants atomically, with zero rollover across months.
  3. **Respect `RULE-QTA-01` / `INV-18` immutability at the DB grant layer:** Keep CRT ledger tables INSERT-only (`zero DELETE`, `zero UPDATE`) for `aq_uai_runtime` in `db/provision.py`, add every new `crt_*` table to `LEGACY_TABLES` so `pg_restore` provisioning takes ownership, and pin `period_month` to day 1.
  4. **Never invent token/credit conversion or fake consumption:** Keep `actual_consumption` / `remaining_quota` at `null` (`consumption_status: "NOT_INTEGRATED"`) unless an authorized gateway & institutional pricing policy are explicitly introduced, and keep `mdl/` completely isolated from `crt/` imports.
  5. **Keep `/api/v1/qta` C5 OpenAPI identifier hygiene intact:** `test_q2_contracts.py` strictly forbids `credit`/`credits`/`token`/`tokens`/`period`/`semester`/`cycle`/`price`/`cost`/`conversion`/`exam`/`project` on `/qta` identifiers — keep CRT endpoints under `/api/v1/crt` and avoid leaking CRT terms into `/qta` schemas unless explicitly authorized and updated in C5.

- **`Q-l` (What in this prompt was unclear or wrong?):**
  1. **§2 `hashes-before.txt` command vs §3 `CLAUDE.md` allowlist:** The exact `find` command in §2 (`find apps tests scripts infra docs .github -type f ...`) does not include repository-root files, whereas `CLAUDE.md` is in the §3 allowlist. Because we followed §2 verbatim for both `hashes-before.txt` and `hashes-after.txt`, `CLAUDE.md` appears in `git-status-after.txt` (and §2 of this report) but not in `changed-files.txt`. Adding `CLAUDE.md` explicitly to the `find` arguments in future prompts would make `changed-files.txt` 100% 1-to-1 with `git status`.
  2. **Pre-existing untracked prompt file:** The note above the fence expected a completely clean committed tree before Q6, while `docs/phase4/QTA_Q6_PROMPT.md` itself was untracked (`??`) in the working tree at start; harmless and cleanly isolated by `git-status-before.txt` and `hashes-before.txt`.

---

## 11. Reviewer response

*Reviewer: Claude Code, 2026-11-27. This is a technical review, not formal acceptance (formal acceptance stays 0/33; ADR-0004 stays Proposed).*

### 11.1 Verdict

**Approved. QTA (Phase 4) is technically complete.** Q6 met every requirement of the prompt, with no defects found. This is the cleanest stage report of the module: exact section structure, honest NOT-verified list, and a real lock-order analysis. No reviewer fixes were needed.

### 11.2 Independent verification

| Check | Result |
| --- | --- |
| `sha256sum -c q6/hashes-after.txt` (repo root) | All files match |
| Changed files vs the §3 allowlist | Within the allowlist; no `apps/api/src/`, migration, `mdl.mjs` or `apps/web/` change |
| Full gate, reviewer run | **API 583 passed, 1 skipped; browser 21 passed; exit 0** — identical to `final-gate.log` |
| Test hygiene | No `skip`, `xfail` or `sleep` in the new tests |
| Docs | Every FR still "not accepted"; the FR-MDL-020 AC3 row changed only as allowed |
| **Docker Compose rehearsal (reviewer, separate evidence)** | The developer's real path: a stack on the `aq-uai-dev` 0006 images, populated through the API (SYSTEM group + member, MDL provider/model, PASSED connection test, routing rev 1) → `up --build` from the committed tree `accf694`. Results: schema `0006 → 0008`; 20/23 pre-existing tables byte-identical, and the other 3 (`permissions`, `roles`, `role_permissions`) grew by exactly the rows `0007` seeds (+2/+2/+3); 8 `qta_*` tables empty; the runtime role has no DELETE on any `qta_*` table and no UPDATE on `qta_events`; live credential isolation PASS; 19/19 driver checks PASS (including the lookup being identical across an MDL connection test); `python -m aq_uai_api.qta.reset` in the container prints `recorded=0 already=1` twice; a second `up` keeps 0008 and changes no data; all disposable containers, volumes and images removed; the `aq-uai-dev` containers are unchanged (same IDs). Script and output: `~/.cache/aqm7/compose-q6.sh`, `compose-q6.txt` (outside the repository). |
| Not verified | Hosted CI on Q6 (uncommitted); the real `aq-uai-dev` upgrade (the PO's decision, runbook in `qta-handoff.md` §3); a real scheduler; browsers other than Chromium |

### 11.3 Response to §10

- **Q-i (lock order):** **Agree with "No".** Verified: `set_specialist_group_active` (`qta/service.py:329`) and `directory.set_group_active` (`directory/service.py:458`) both use `changes_authority=True`, so they take the institution lock **exclusive**, which already serializes them against `upsert_group_quotas` (shared). This closes the Q4 10.c.3 item: no change.
- **Q-j (nothing missing for Must):** Agree for QTA. The remaining items are Should/Could or institutional inputs, all listed in `qta-handoff.md` §7.
- **Q-k (CRT notes):** All five are adopted in `docs/phase5/CRT_IMPLEMENTATION_PLAN.md` (52001 for grants, month-aware `allocated_for_month`, INSERT-only grants plus `LEGACY_TABLES`, no invented consumption, a `/crt` identifier rule).
- **Q-l (hash command excludes root files):** Correct. Fixed for Phase 5: the hash command in `docs/agents/ANTIGRAVITY_OPERATING_RULES.md` R4.1 now includes `AGENTS.md`, `CLAUDE.md` and `README.md`.

### 11.4 Phase 4 closure

QTA Q0–Q6 is implemented and technically verified:
- API, UI, CLI and DB;
- populated upgrade, by automated test and by a Docker rehearsal;
- backup/restore;
- cross-module isolation.

The remaining inputs are PO or institutional:
- formal acceptance;
- Q-a decision-date bounds;
- Q-b reason visibility;
- the QD11 PENDING policy;
- the Q-g/Q-h defaults, which the PO may override;
- real consumption metering.

Next: Phase 5 CRT per `docs/phase5/CRT_IMPLEMENTATION_PLAN.md`, starting with C0.
