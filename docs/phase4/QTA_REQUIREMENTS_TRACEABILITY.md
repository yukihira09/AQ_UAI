# QTA requirements traceability (`AQ-FRD-UAI-QTA-001`)

Maps every `Must` requirement, acceptance criterion (AC), `Should` item, and `RULE-QTA-*` invariant of [AQ-FRD-UAI-QTA-001](../frd/AQ-FRD-UAI-QTA-001.md) to its Phase 4 stage (**Q0–Q6**), implementation artifact, and verification tests.

## Coverage summary

| FR ID | Title | Priority | ACs | Stages | Status (2026-11-27, Q2) |
| --- | --- | --- | --- | --- | --- |
| `FR-QTA-001` | Truy cập theo quyền | Must | 2 | Q1, Q1-R, Q2, Q3, Q5 | Implemented in API (Q2 group routes & empty-before-sync verified); lookup scope in Q3, UI in Q5 |
| `FR-QTA-010` | Tổng hạn mức nhà trường theo tháng | Must | 3 | Q1-R, Q3, Q5 | Append-only `qta_budget_revisions` + required `decision_date` done; API in Q3, UI in Q5 |
| `FR-QTA-011` | Không giảm tổng dưới phần đã phân bổ | Must | 1 | Q1, Q1-R, Q3, Q5 | Error/details contract & `PD-Q1` unit rule done; service in Q3, UI in Q5 |
| `FR-QTA-020` | Đồng bộ nhóm & người dùng từ hệ thống | Must | 2 | Q1-R, Q2, Q5 | Implemented in API (Q2 verified); UI in Q5 |
| `FR-QTA-021` | Cấu hình hạn mức theo từng mô hình của nhóm | Must | 2 | Q1-R, Q2, Q3, Q5 | Implemented in API for AC1 config (Q2 verified); AC2 lookup check in Q3, UI in Q5 |
| `FR-QTA-022` | Nhóm AI chuyên biệt | Must | 2 | Q1-R, Q2, Q3, Q5 | Implemented in API for AC1 lifecycle/members (Q2 verified); AC2 lookup in Q3, UI in Q5 |
| `FR-QTA-030` | Quy tắc cộng dồn đa nhóm | Must | 2 | Q3, Q5 | Planned (Q3 service, Q5 UI) |
| `FR-QTA-031` | Tra cứu hạn mức thực hưởng cá nhân | Must | 2 | Q3, Q4, Q5 | Planned (Q3 base lookup, Q4 suspension status, Q5 UI) |
| `FR-QTA-032` | Làm mới đầu tháng | Must | 2 | Q1, Q4, Q5 | Append-only reset/event tables done; CLI/API in Q4, UI in Q5 |
| `FR-QTA-040` | Cắt / ngưng hạn mức cá nhân | Must | 3 | Q1-R, Q4, Q5 | Append-only `qta_suspensions` (optional `expires_at`, `PD-Q2`/`PD-Q3`) done; API in Q4, UI in Q5 |
| `FR-QTA-041` | Khôi phục hạn mức | Must | 2 | Q1, Q4, Q5 | Append-only `qta_suspension_restorations` done; API in Q4, UI in Q5 |
| `FR-QTA-050` | Không chu kỳ ngoài tháng; không sửa giao dịch cũ | Must | 2 | Q1-R, Q2, Q3, Q4, Q5 | DB day-1 checks, INSERT-only grants & Q2 OpenAPI checks verified; Q3–Q5 pending |
| **Total** | **12 Must requirements** | **Must** | **25 ACs** + 5 RULEs | Q1–Q6 | **Q0–Q2 implemented & verified (awaiting review); Q3–Q6 pending** |

---

## Detailed AC mapping

### `FR-QTA-001` — Truy cập theo quyền
- **AC1** (Unauthorized user cannot modify group quotas): Every QTA write uses `protected()` + `qta.manage` (direct GLOBAL only). Anonymous → 401; `FOUNDATION_ADMIN`, `AI_MODEL_ADMIN`, `AI_QUOTA_VIEWER`, and `AI_SPECIALIST` members → 403. UI hides write controls without `qta.manage`. *(Tests: `test_q1_qta_schema.py`, `test_q2_qta_groups.py`, `test_qta.py`)*
- **AC2** (Authorized account opens group list, even empty before sync): `GET /api/v1/qta/groups` reads enrolled groups from `qta_quota_groups` (empty before the first sync even when Phase 2 already has `SYSTEM` groups). UNIT-scoped `AI_QUOTA_VIEWER` can inspect personal lookup for users in its unit. *(Tests: `test_q2_qta_groups.py`, `test_q3_qta_lookup_budgets.py`, `test_qta.py`)*

### `FR-QTA-010` — Tổng hạn mức nhà trường theo tháng
- **AC1** (Save monthly cap with decision number and date): `PUT /api/v1/qta/budgets/{YYYY-MM}` (current or next month only in `Asia/Ho_Chi_Minh`) appends a new `qta_budget_revisions` row (`revision = max + 1`, `INV-18`) + `BudgetRevisionRecorded` audit event. Active cap = highest revision; unset month displays `"chưa ghi nhận"`.
- **AC2** (Missing decision number or decision date refused): Pydantic validation + PostgreSQL `ck_qta_budget_revisions_decision_number` and `decision_date NOT NULL` (`PD-Q4`) reject missing/blank values (422).
- **AC3** (No non-Month cycle selector on UI): Schema accepts `YYYY-MM` only (`EXTRACT(DAY FROM period_month) = 1`); UI displays fixed Month input/label with zero Semester/Project/Exam dropdowns. *(Tests: `test_q1_qta_schema.py`, `test_q3_entitlements.py`, `test_q3_qta_lookup_budgets.py`, `test_qta.py`)*

### `FR-QTA-011` — Không giảm tổng dưới phần đã phân bổ
- **AC1** (New total < allocated → rejected with exact deficit): `PUT /api/v1/qta/budgets/{month}` acquires `QTA_BUDGET_NAMESPACE`, computes `allocated_for_month()` in *đơn vị hạn mức* (`PD-Q1`), and raises `409 QTA_BUDGET_BELOW_ALLOCATED` with `details: {"deficit": allocated - new_limit, "allocated": allocated}`. UI renders the exact deficit amount to recover. *(Tests: `test_q3_qta_lookup_budgets.py`, `test_qta.py`)*

### `FR-QTA-020` — Đồng bộ nhóm & người dùng từ hệ thống
- **AC1** (System groups appear after sync): `POST /api/v1/qta/groups/sync` enrolls active Phase 2 `SYSTEM` groups into `qta_quota_groups(origin='SYNC')`, marks inactive/gone `SYSTEM` groups `in_directory=false`, and appends an immutable `qta_group_sync_runs` row (with `groups_added`, `groups_retired`) + audit event. Memberships are read live from `group_memberships`.
- **AC2** (Sync never deletes or overwrites `AI_SPECIALIST` groups): Integration and browser tests verify existing `origin='SPECIALIST'` registry rows, their members, and their quotas remain untouched after sync. *(Tests: `test_q2_qta_groups.py`, `test_qta.py`)*

### `FR-QTA-021` — Cấu hình hạn mức theo từng mô hình của nhóm
- **AC1** (Same group can set two distinct limits for two models): `PUT /api/v1/qta/groups/{group_id}/quotas` stores one row per `(institution_id, group_id, model_id)` in `qta_group_model_quotas` (FK → `qta_quota_groups`) across all active MDL models. *(Stage Q2)*
- **AC2** (Disabling a model removes base quota for users only in that group): Setting `enabled=false` immediately sets that group's contribution to `0` in personal lookup (`PD-Q5`). *(Stage Q3, UI Q5; tests: `test_q2_qta_groups.py`, `test_q3_qta_lookup_budgets.py`, `test_qta.py`)*

### `FR-QTA-022` — Nhóm AI chuyên biệt
- **AC1** (Create specialist group + assign at least one member): `POST /api/v1/qta/groups` and `PUT /api/v1/qta/groups/{id}/members/{user_id}` call existing `directory.service` functions (`require_group_management` accepts `qta.manage` or `directory.manage` for `AI_SPECIALIST`) and enroll the group in `qta_quota_groups(origin='SPECIALIST')` in the same transaction. *(Stage Q2)*
- **AC2** (Member appears in additive lookup with that group's quota): Verified via `GET /api/v1/qta/users/{id}/entitlements` (Q3) and UI lookup tab (Q5). *(Tests: `test_q2_qta_groups.py`, `test_q3_qta_lookup_budgets.py`, `test_qta.py`)*

### `FR-QTA-030` — Quy tắc cộng dồn đa nhóm
- **AC1** (Group 1,000 + Group 3,000 on same model → base = 4,000, not MAX): `qta/entitlements.py` sums all enabled positive limits across enrolled active groups (`in_directory=true`, `account_groups.active=true`) with active memberships.
- **AC2** (Lookup displays group list and exact addition formula): API returns `contributions: [{group_id, group_code, group_name, group_kind, amount}]` + `base_entitlement`; UI renders `"1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn mức"`. *(Tests: `test_q3_entitlements.py`, `test_q3_qta_lookup_budgets.py`, `test_qta.py`)*

### `FR-QTA-031` — Tra cứu hạn mức thực hưởng cá nhân
- **AC1** (Select a specific person and view additive model table + suspension status): `GET /api/v1/qta/users` + `GET /api/v1/qta/users/{user_id}/entitlements?month=YYYY-MM`. Returns `base_entitlement` (in *đơn vị hạn mức* with per-group contributions), `actual_consumption: null`, `remaining_quota: null`, `consumption_status: "NOT_INTEGRATED"` (`QD10`), plus (Q4) active suspension and per-model access evaluation.
- **AC2** (User in zero enrolled groups → base quota 0): Returns `groups: []` and `base_entitlement: 0` for every active model. *(Tests: `test_q3_qta_lookup_budgets.py`, `test_q4_qta_killswitch_reset.py`, `test_qta.py`)*

### `FR-QTA-032` — Làm mới đầu tháng
- **AC1** (Run/simulate reset → append-only `"Làm mới"` event recorded): CLI `python -m aq_uai_api.qta.reset` (for `00:00` day-1 in `Asia/Ho_Chi_Minh` + safe catch-up) and `POST /api/v1/qta/monthly-resets` (current month only, `PD-Q6`) insert immutable `qta_monthly_resets` + `qta_events(event_type='MONTHLY_REFRESH')` rows + audit event. Strict idempotency via `UNIQUE(institution_id, period_month)`.
- **AC2** (Prior-month unused balance does not increase next month's quota): Entitlements, budget revisions, and future CRT top-ups are scoped strictly by `period_month` (automatic zero rollover at `00:00` day 1 even if a scheduled run is missed); monthly reset does not lift active suspensions. *(Tests: `test_q4_access_reset.py`, `test_q4_qta_killswitch_reset.py`, `test_qta.py`)*

### `FR-QTA-040` — Cắt / ngưng hạn mức cá nhân
- **AC1** (After suspend → `SUSPENDED` / `ĐÃ CẮT` badge; blocked in selected scope; balance NOT zeroed): `check_ai_access` blocks all models under `ALL_MODELS`, and blocks all models of `EXTERNAL` providers under `PAID_EXTERNAL_ONLY` while allowing `INTERNAL` models (`PD-Q2`). `base_entitlement` stays unchanged. Lazy expiry (`expires_at IS NULL OR expires_at > now()`, `PD-Q3`).
- **AC2** (Append-only suspend event/record): `qta_suspensions` and `qta_events(event_type='SUSPEND')` are INSERT-only (`provision.py` grants zero `UPDATE`/`DELETE`). Authenticated operator (`suspended_by`, `audit_events.actor_id`) is derived strictly from the session, never from `ordered_by` (`QD11`).
- **AC3** (Missing reason or authorizer, or past/non-finite expiry → rejected): Validated by Pydantic and PostgreSQL `CHECK` constraints (422); `expires_at` is optional (`NULL` = until restored, `PD-Q3`). *(Tests: `test_q1_qta_schema.py`, `test_q4_access_reset.py`, `test_q4_qta_killswitch_reset.py`, `test_qta.py`)*

### `FR-QTA-041` — Khôi phục hạn mức
- **AC1** (Restore → returns `ACTIVE` without adding new quota): `POST /api/v1/qta/users/{user_id}/restore` inserts into `qta_suspension_restorations`; balances before and after restore are identical.
- **AC2** (Append-only restore event/record): Inserts `qta_events(event_type='RESTORE')` + `qta.user_restored` audit event. *(Tests: `test_q4_qta_killswitch_reset.py`, `test_qta.py`)*

### `FR-QTA-050` — Không chu kỳ ngoài tháng; không sửa giao dịch cũ
- **AC1** (No Semester/Project/Exam selector on UI or API): OpenAPI scan, Pydantic schema tests, PostgreSQL `EXTRACT(DAY) = 1` check, and Playwright DOM scan.
- **AC2** (No Edit/Delete routes or buttons on recorded revisions/events/resets/suspensions): No `PATCH`/`PUT`/`DELETE` routes on `/qta/events`, `/qta/monthly-resets`, `/qta/suspensions`, `/qta/groups/sync-runs`, or existing budget revisions; PostgreSQL runtime role has zero `DELETE` on all 8 QTA tables and zero `UPDATE` on all 6 append-only tables (`qta_budget_revisions`, `qta_group_sync_runs`, `qta_suspensions`, `qta_suspension_restorations`, `qta_monthly_resets`, `qta_events`); DOM scan confirms no Edit/Delete controls. *(Tests: `test_q1_qta_schema.py`, `test_q4_access_reset.py`, `test_q4_qta_killswitch_reset.py`, `test_qta.py`)*

---

## Cross-cutting `RULE-QTA-*` verification

| Rule | Enforcement layer | Test |
| --- | --- | --- |
| `RULE-QTA-01` (Month-only cycle) | DB `EXTRACT(DAY) = 1` + Pydantic `YYYY-MM` + UI | `test_q1_qta_schema.py`, `test_q3_entitlements.py`, `test_qta.py` |
| `RULE-QTA-02` (Additive sum, never MAX) | `qta/entitlements.py` | `test_q3_entitlements.py`, `test_q3_qta_lookup_budgets.py` |
| `RULE-QTA-03` (`SUSPENDED` blocks by scope) | `qta/entitlements.py::check_ai_access` | `test_q4_access_reset.py`, `test_q4_qta_killswitch_reset.py` |
| `RULE-QTA-04` (Append-only transactions) | PostgreSQL column grants (INSERT-only on 6 tables, zero DELETE on all 8) + no edit/delete API | `test_q1_qta_schema.py`, `test_q3_qta_lookup_budgets.py`, `test_q4_qta_killswitch_reset.py` |
| `RULE-QTA-05` (Sync preserves `AI_SPECIALIST`) | `qta/service.py::sync_system_groups` + `qta_quota_groups.origin` | `test_q2_qta_groups.py`, `test_qta.py` |
