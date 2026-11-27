# QTA architecture and decisions (Phase 4 · Module 2)

**Status:** **Q0** (planning), **Q1** (initial RBAC catalog `0007` and schema `0008`), and **Q1-R** (schema and plan revision addressing [QTA_Q1_REVIEW.md](QTA_Q1_REVIEW.md) findings F1–F11 and Project Owner decisions **PD-Q1..PD-Q6**) are implemented in source. **No formal external Tech Lead or institutional sign-off is claimed.**

Canonical FRD: [AQ-FRD-UAI-QTA-001](../frd/AQ-FRD-UAI-QTA-001.md) · Plan: [QTA_IMPLEMENTATION_PLAN](QTA_IMPLEMENTATION_PLAN.md) · Open decisions: [QTA_OPEN_DECISIONS](QTA_OPEN_DECISIONS.md) · Traceability: [QTA_REQUIREMENTS_TRACEABILITY](QTA_REQUIREMENTS_TRACEABILITY.md) · ADR: [ADR-0004](../architecture/ADR-0004-qta.md).

Provenance labels:
- **SPEC** — directly mandated by the canonical FRD.
- **PO** — Project Owner decision (`PD-Q1..PD-Q6`, recorded 2026-11-26 for this standalone demo project; not an institutional accounting rule).
- **REC** — technical engineering recommendation.
- **PROV** — provisional engineering assumption.
- **NEEDS-INSTITUTION** — business, financial, or legal policy requiring institutional input (never invented in code).

---

## 1. Reuse of Phase 2 & Phase 3 foundations (no parallel stacks)

QTA extends the existing FastAPI + SQLAlchemy 2 + PostgreSQL 18 + Alembic modular monolith under `/api/v1/qta` and `#qta` in `apps/admin/`.

| Need | Reused foundation | Phase 4 extension |
| --- | --- | --- |
| Identity, users, units | `db/identity.py` (`Institution`, `Unit`, `User`) | None — composite `(institution_id, id)` FKs |
| System & AI-specialist groups | `db/identity.py` (`AccountGroup`, `GroupMembership`) | Single source of truth for group identity and live memberships; `0008` adds `UNIQUE(institution_id, id, kind)` on `account_groups` so `qta_quota_groups` enforces group-kind integrity at the DB layer |
| Group authorization & write path | `authorization/policy.py` (`require_group_management`), `directory/service.py` | **Planned Q2 (F4):** extend `require_group_management` so `AI_SPECIALIST` accepts `qta.manage` **or** `directory.manage` (`SYSTEM`/`AUTHORIZATION` unchanged); QTA specialist-group routes call existing `directory.service` functions (`create_group`, `update_group`, `set_group_active`, `set_membership`) with their existing audit actions and enroll the group in `qta_quota_groups` in the same transaction. Zero parallel group writer |
| Model catalogue | `mdl/models.py` (`MdlModel`, `MdlProvider`) | Read-only SQL reads from `qta/` to `mdl_models` + `mdl_providers`. **One-way dependency:** `mdl/` NEVER imports `qta/` (`FR-MDL-020 AC3`), and **no MDL schema or code changes** (`PD-Q2`) |
| Session, Origin, CSRF, locks | `authorization/dependencies.py`, `authorization/writes.py` (`WriteContext`, `protected`, `record`) | Reused verbatim on every QTA read and write; authenticated operator always comes from `authority.actor_id` |
| Permission catalog & RBAC | `authorization/policy.py`, `db/identity.py` | **Q1 done (`0007`):** `qta.read` (GLOBAL/UNIT), `qta.manage` (direct GLOBAL only); roles `AI_QUOTA_ADMIN` and `AI_QUOTA_VIEWER` |
| Audit trail | `db/audit.py` (`AuditAction`, `_EVENT_RULES`, `write_audit_event`) | **Q1-R done:** 7 typed `qta.*` audit actions (including `BudgetRevisionRecorded` with `revision` & `before_decision_number`, `GroupsSynced` with `groups_added`/`groups_retired`, optional `UserSuspended.expires_at`) committed in the same transaction as every mutation |
| Safe API errors | `api/errors.py` (`DomainError`, `ErrorCode`, `_DETAIL_VALIDATORS`, `_PRIVATE_API_PATHS`) | **Q1 done:** 8 `QTA_*` codes, non-negative int detail validators (`deficit`, `allocated`), `"qta"` private cache path |
| Migrations & DB privileges | `apps/api/migrations/`, `db/schema.py`, `db/provision.py` | **Q1-R done:** `0007_qta_access_catalog`, `0008_qta_schema` (8 QTA tables), `LEGACY_TABLES`, column-level `QTA_RUNTIME_PRIVILEGES` (zero `DELETE`, INSERT-only budget revisions/history/events, narrow registry updates) |
| Admin UI | `apps/admin/assets/{app,api,ui,pages}.mjs`, `admin.css` | **Q5:** `qta.mjs` (`#qta` section) under strict CSP using `"đơn vị hạn mức"` wording; `apps/web/` stays untouched |

---

## 2. Design decisions (Q1-R)

### 2.1 Quota calculation, unit & institutional allocation (`PD-Q1`, `PD-Q4`, `PD-Q5`, `QD3`, `QD6`, `QD7`)

1. **Single abstract unit (`PO` — `PD-Q1`):** Every QTA amount (school monthly total, group × model monthly limit, individual base entitlement, allocated total, deficit) is expressed in one abstract unit: **"đơn vị hạn mức"**. It is **never** labelled tokens or credits, and **no price or token↔credit conversion exists**. Valid for this standalone demo project; not an institutional accounting rule.
2. **Per-member, not shared (`SPEC`):** Each `qta_group_model_quotas` row `(group_id, model_id, enabled, monthly_limit)` defines a **per-member monthly allowance**, never a shared group pool (`FR-QTA-030`).
3. **Qualifying enrolled groups (`SPEC` + `REC` + `PROV`):** A user $u$ in institution $I$ receives base quota only from groups enrolled in `qta_quota_groups` that are currently active and present in the directory:
   $$G(u) = \{ g \in \text{qta\_quota\_groups} \mid g.\text{institution\_id} = I \land g.\text{in\_directory} = \text{true} \land \text{account\_groups}(g).\text{active} = \text{true} \land \text{active\_member}(g, u) \}$$
   - `AUTHORIZATION` groups can never be enrolled (`fk_qta_quota_groups_account_group` + `ck_qta_quota_groups_kind`).
   - Unenrolled `SYSTEM` groups (before sync), retired `SYSTEM` groups (`in_directory = false`), inactive groups (`account_groups.active = false`), and removed memberships (`group_memberships.active = false`) contribute `0`.
4. **Additive individual base entitlement (`SPEC`):** For user $u$ and active model $m \in M_{\text{active}}(I)$:
   $$q(g, m) = \begin{cases} \text{monthly\_limit} & \text{if } (g, m) \text{ exists, } \text{enabled} = \text{true}, \text{ and } \text{monthly\_limit} > 0 \\ 0 & \text{otherwise} \end{cases}$$
   $$E_{\text{base}}(u, m) = \sum_{g \in G(u)} q(g, m)$$
   - If $G(u) = \emptyset$, then $E_{\text{base}}(u, m) = 0$ for every active model (`FR-QTA-031 AC2`).
   - Users with `User.state != 'ACTIVE'` (`PENDING` or `DISABLED`) cannot invoke AI and contribute `0` to institutional allocation (`PROV`). Lookup still shows their account state and stored memberships transparently.
5. **Institutional allocation & append-only budget revisions (`SPEC` + `PO` — `PD-Q1`, `PD-Q4`, `F2`, `F8`):**
   - `allocated_for_month(db, institution_id, period_month)` computes:
     $$\text{Allocated}(M) = \sum_{u \in U_{\text{active}}(I)} \sum_{m \in M_{\text{active}}(I)} E_{\text{base}}(u, m) = \sum_{g \in G_{\text{enrolled,active}}(I)} \left( |U_{\text{active}}(g)| \times \sum_{m \in M_{\text{active}}(I)} q(g, m) \right)$$
     In Phase 5 (CRT), net individual grants join through the same `allocated_for_month` function (`PD-Q1`).
   - **Append-only budget revisions (`INV-18`, `F2`):** Each budget write appends a new row to `qta_budget_revisions` (`revision = max_revision + 1`), requiring both `decision_number` and `decision_date` (`PD-Q4`). Earlier decisions are never overwritten; the active total for a month is the highest revision.
   - **Month window & unset months (`SPEC` — `FR-QTA-010`, `F8`):** Only the **current or next month** (`Asia/Ho_Chi_Minh`) may receive a new budget revision; past months are read-only. A month without any revision shows **"chưa ghi nhận"** (group quotas still apply).
   - **Cap reduction guard (`SPEC` — `FR-QTA-011`, `PD-Q1`):** Recording a new revision with `total_limit < allocated` is rejected with `409 QTA_BUDGET_BELOW_ALLOCATED` and `details: {"allocated": allocated, "deficit": allocated - total_limit}`.
   - **Mid-month changes & overlapping memberships (`PO` — `PD-Q5`, `PD-Q1`):** Overlapping memberships are additive by design. Mid-month membership, group, and quota changes take effect **immediately**. Directory growth and quota edits are never blocked; if `allocated > total_limit`, `GET /qta/budgets` surfaces `over_allocated = allocated - total_limit` as a warning. Closed past months are not retroactively snapshotted in Phase 4 (`PROV`).

#### Numerical example (`đơn vị hạn mức`)

Assume Institution $I$ has two active models (`M1`, `M2`), two `ACTIVE` users (`Alice`, `Bob`), one `DISABLED` user (`Carol`), and two enrolled active groups:
- `G_GV` (`SYSTEM`, enrolled via `SYNC`, members: `Alice`, `Bob`, `Carol [DISABLED]`): `M1 = 1,000`, `M2 = 2,000` (both enabled).
- `AI_LAB` (`AI_SPECIALIST`, enrolled via `SPECIALIST`, member: `Alice`): `M1 = 3,000` (enabled), `M2 = 5,000` (**disabled**, `enabled = false`).

| Calculation | Formula | Result (`đơn vị hạn mức`) |
| --- | --- | --- |
| **Alice's base entitlement on `M1`** | `1,000 (G_GV) + 3,000 (AI_LAB)` (additive, **not** `MAX = 3,000`) | **4,000** |
| **Alice's base entitlement on `M2`** | `2,000 (G_GV) + 0 (AI_LAB disabled)` | **2,000** |
| **Bob's base entitlement** | `M1 = 1,000 (G_GV)`, `M2 = 2,000 (G_GV)` | **3,000** total |
| **Carol (`DISABLED`)** | Contributes `0` to institutional commitment | **0** |
| **Institutional `Allocated(M)`** | By user: `(4,000 + 2,000) + (1,000 + 2,000)` · By group: `G_GV (2 active × 3,000) + AI_LAB (1 active × 3,000)` | **9,000** |
| **Budget revision 1 (`total_limit = 10,000`)** | Recorded with `QD-01` + `decision_date` | `revision = 1`, `remaining = 1,000` |
| **Budget revision 2 attempt (`total_limit = 7,500`)** | `7,500 < 9,000` → `409 QTA_BUDGET_BELOW_ALLOCATED` | `allocated = 9,000`, `deficit = 1,500` |
| **Mid-month: `AI_LAB` deactivated (`PD-Q5`)** | Alice drops to `M1 = 1,000`, `M2 = 2,000`; `Allocated(M)` drops immediately to `6,000` | Revision 2 (`7,500`, `QD-02`) now succeeds (`remaining = 1,500`) while Revision 1 (`10,000`, `QD-01`) stays preserved in history |

---

### 2.2 Paid external model scope (`PD-Q2`, `QD9`)

- Per **Project Owner decision `PD-Q2`** (2026-11-26), `PAID_EXTERNAL_ONLY` (*chỉ mô hình bên ngoài mất phí*) applies to **all models whose provider has `provider_type == 'EXTERNAL'`**.
- **No MDL schema or code change is made** (read-only access to `mdl_models` and `mdl_providers`).
- **Enforcement matrix under `check_ai_access(db, institution_id, user_id, model_id)` (Stage Q4):**

| Active suspension scope | Model `provider_type` | Access decision | Reason code |
| --- | --- | --- | --- |
| *(None / expired / restored)* | `INTERNAL` or `EXTERNAL` | **ALLOWED** | — |
| `ALL_MODELS` | `INTERNAL` or `EXTERNAL` | **BLOCKED** | `suspended_all_models` |
| `PAID_EXTERNAL_ONLY` | `INTERNAL` | **ALLOWED** | — |
| `PAID_EXTERNAL_ONLY` | `EXTERNAL` | **BLOCKED** | `suspended_paid_external` |

---

### 2.3 Usage versus entitlement (`QD10`)

QTA strictly separates four concepts and **never fabricates consumption or deductions** before a real AI invocation gateway exists (`FRD §1.3`):

| Concept | Meaning | Phase 4 (QTA) behavior |
| --- | --- | --- |
| **Configured quota** (`group_model_quota`) | Per-member monthly limit in *đơn vị hạn mức* on `(enrolled_group, model)` (`enabled`, `monthly_limit`, optional `warning_threshold_pct`). | Stored in `qta_group_model_quotas`. |
| **Individual entitlement** (`base_entitlement`) | Additive monthly base quota $E_{\text{base}}(u, m)$ across qualifying enrolled groups. Never modified by suspension. | Computed live on read; returned with per-group breakdown. |
| **Actual consumption** (`actual_consumption`) | Real metered usage from an AI gateway in `period_month`. | Returned as **`null`** with `consumption_status: "NOT_INTEGRATED"`. Never faked as `0` or seeded with synthetic numbers. |
| **Remaining quota** (`remaining_quota`) | Entitlement minus verified actual consumption (once metering exists). | Returned as **`null`** while `consumption_status == "NOT_INTEGRATED"`. UI displays *"Chưa tích hợp đo tiêu thụ thực tế"* rather than a synthetic progress bar. |

---

### 2.4 Suspension scope, duration, expiry & authorization (`PD-Q3`, `QD11`)

- **Authorization (`SPEC` + `REC`):**
  - Only an authenticated `AI_QUOTA_ADMIN` (direct `GLOBAL` `qta.manage`) may suspend or restore a user, via `protected(context, changes_authority=False, user_id=target_user_id, permission=P.QTA_MANAGE)` + `QTA_SUSPENSION_NAMESPACE`.
  - **Authenticated operator (`suspended_by`, `restored_by`, `audit_events.actor_id`):** Derived exclusively from `authority.actor_id` — **never** accepted from client input.
  - **Authorizer (`ordered_by`):** Mandatory trimmed text (1–255 chars, `FR-QTA-040`) stored strictly as **non-authoritative administrative metadata** (*Người ra lệnh*), displayed separately from *Người thực hiện*.
- **Duration & lazy expiry (`PO` — `PD-Q3`):**
  - `expires_at` (`TIMESTAMPTZ NULL`) is **optional**: `NULL` means active until explicitly restored. If provided, it must be finite and strictly greater than `suspended_at` (no maximum duration cap).
  - **Lazy expiry enforcement:** A suspension is active iff it has no row in `qta_suspension_restorations` **and** `(expires_at IS NULL OR expires_at > now())`.
- **Target & balance preservation (`SPEC` + `PROV`):**
  - Target must belong to the same institution and have `User.state == 'ACTIVE'` (`PROV`).
  - Single active suspension per user (`409 QTA_USER_ALREADY_SUSPENDED`).
  - Restore (`FR-QTA-041`) requires an active suspension (`409 QTA_USER_NOT_SUSPENDED`), inserts an immutable `qta_suspension_restorations` row + `qta_events(RESTORE)` + `qta.user_restored`, and never adds quota. Neither suspend nor restore alters balances.

---

### 2.5 Monthly reset & group synchronization (`PD-Q6`, `QD2`, `QD4`, `QD8`, `F3`, `F4`)

1. **Monthly reset (`FR-QTA-032`, `FR-QTA-050`, `RULE-QTA-01`, `PD-Q6`):**
   - **Timezone (`REC`):** Institution calendar month uses **`Asia/Ho_Chi_Minh` (UTC+07:00)** (configurable via `AQ_UAI_INSTITUTION_TIMEZONE`, validated with `zoneinfo.ZoneInfo`). DB timestamps stay UTC `timestamptz`.
   - **Scheduled CLI:** `python -m aq_uai_api.qta.reset` (`trigger_mode='SCHEDULED'`, `triggered_by=NULL`) records `qta_monthly_resets` + `qta_events(MONTHLY_REFRESH)` + operator audit `qta.monthly_reset_scheduled`. Idempotent no-op (exit 0) if the month is already recorded.
   - **Manual simulation (`PO` — `PD-Q6`):** `POST /api/v1/qta/monthly-resets` (`trigger_mode='MANUAL_SIMULATION'`, `triggered_by=authority.actor_id`) is permitted for the **current month only** (`Asia/Ho_Chi_Minh`) — never a future month, so it cannot pre-empt the real `00:00` day-1 run. Repeat returns `409 QTA_RESET_ALREADY_EXECUTED`.
   - **Idempotency, missed resets & zero rollover:** Enforced structurally by `UNIQUE(institution_id, period_month)` + `QTA_RESET_NAMESPACE`. Crossing `00:00` day 1 automatically scopes queries to the new `period_month` (zero rollover even if cron missed); late catch-up writes real `executed_at` without backdating; `GET /qta/monthly-resets` reports current-month `COMPLETED` vs `PENDING`. Monthly resets never lift active disciplinary suspensions.
2. **Group registry, synchronization & specialist-group reuse (`FR-QTA-001 AC2`, `FR-QTA-020`, `FR-QTA-022`, `RULE-QTA-05`, `F3`, `F4`):**
   - **Before the first sync:** `qta_quota_groups` is empty, so `GET /qta/groups` honestly returns an empty list (`FR-QTA-001 AC2`).
   - **Sync (`POST /api/v1/qta/groups/sync`):** Inside one `protected()` transaction (`qta.manage`), reconciles `qta_quota_groups` against Phase 2 `account_groups(kind='SYSTEM')`:
     - Enrolls active `SYSTEM` groups not yet in `qta_quota_groups` (`origin='SYNC'`, `in_directory=true`, `last_synced_at=now()`), incrementing `groups_added`.
     - Sets `in_directory=false` and `last_synced_at=now()` on enrolled `SYSTEM` groups that became inactive in `account_groups` (never deletes them; their quotas stop contributing immediately), incrementing `groups_retired`.
     - Restores `in_directory=true` and `last_synced_at=now()` if a previously retired `SYSTEM` group becomes active again.
     - Enrolls active `AI_SPECIALIST` groups that exist in the directory but are not yet in `qta_quota_groups` (for example, created by a `directory.manage` holder through the Phase 2 directory UI) with `origin='SPECIALIST'`, also counted in `groups_added` (`REC`, added in the 2026-11-27 review: otherwise such groups could never receive quotas).
     - **Never modifies existing `origin='SPECIALIST'` rows** or existing `qta_group_model_quotas` rows (`RULE-QTA-05`); a deactivated specialist group stops contributing through `account_groups.active`.
     - **Ignores `AUTHORIZATION` groups completely.**
     - Appends one immutable `qta_group_sync_runs` row (with `system_group_count`, `active_member_count`, `specialist_group_count`, `groups_added`, `groups_retired`) + `qta.groups_synced` audit event in the same transaction.
   - **Live memberships:** Memberships are read live from Phase 2 `group_memberships` (no duplicated membership table).
   - **Specialist groups (`F4`):** In Q2, `authorization/policy.py::require_group_management` is extended so `AI_SPECIALIST` accepts `qta.manage` **or** `directory.manage`. QTA specialist-group endpoints call existing `directory.service` functions (`create_group`, `update_group`, `set_group_active`, `set_membership`) with their existing audit actions and insert the matching `qta_quota_groups(origin='SPECIALIST')` row in the same transaction.

---

## 3. Database schema (Q1-R delivered: `0008_qta_schema`)

Every QTA table is empty after migration, includes `institution_id` + composite FKs, uses `BIGINT` for quota quantities, and has **zero `DELETE` grant** for `aq_uai_runtime`. Migration `0008_qta_schema` also adds one additive `UNIQUE (institution_id, id, kind)` constraint on `account_groups` (mirrored in `db/identity.py`) without altering existing rows.

| Table | Purpose & key columns | Runtime grants (`aq_uai_runtime`) |
| --- | --- | --- |
| `qta_budget_revisions` | `id`, `institution_id`, `period_month` (day=1), `revision >= 1`, `total_limit > 0`, `decision_number`, `decision_date` (NOT NULL), `recorded_by`, `recorded_at`; `UNIQUE(institution_id, period_month, revision)`. Active total = highest revision | `SELECT`, `INSERT (...)` (**INSERT-only**) |
| `qta_quota_groups` | PK `(institution_id, group_id)`, `group_kind` (`SYSTEM` \| `AI_SPECIALIST`), `origin` (`SYNC` \| `SPECIALIST`, paired with kind), `in_directory`, `enrolled_by`, `enrolled_at`, `last_synced_at`; composite FK to `account_groups(institution_id, id, kind)` | `SELECT`, `INSERT (...)`, `UPDATE (in_directory, last_synced_at)` |
| `qta_group_model_quotas` | `id`, `institution_id`, `group_id` (FK → `qta_quota_groups`), `model_id` (FK → `mdl_models`), `enabled`, `monthly_limit >= 0`, `warning_threshold_pct` (1–100, nullable), `updated_by`, timestamps; `UNIQUE(institution_id, group_id, model_id)` | `SELECT`, `INSERT (...)`, `UPDATE (enabled, monthly_limit, warning_threshold_pct, updated_by, updated_at)` |
| `qta_group_sync_runs` | `id`, `institution_id`, `system_group_count`, `active_member_count`, `specialist_group_count`, `groups_added`, `groups_retired`, `synced_by`, `synced_at` | `SELECT`, `INSERT (...)` (**INSERT-only**) |
| `qta_suspensions` | `id`, `institution_id`, `user_id`, `scope` (`ALL_MODELS` \| `PAID_EXTERNAL_ONLY`), `reason`, `ordered_by`, `expires_at` (nullable; if set, finite & `> suspended_at`), `suspended_by`, `suspended_at` | `SELECT`, `INSERT (...)` (**INSERT-only**) |
| `qta_suspension_restorations` | `suspension_id` (PK), `institution_id`, `restored_by`, `restored_at`, `note` (nullable) | `SELECT`, `INSERT (...)` (**INSERT-only**) |
| `qta_monthly_resets` | `id`, `institution_id`, `period_month` (day=1, unique per institution), `trigger_mode` (`SCHEDULED` \| `MANUAL_SIMULATION`), `triggered_by` (nullable), `executed_at` | `SELECT`, `INSERT (...)` (**INSERT-only**) |
| `qta_events` | `id`, `institution_id`, `period_month` (day=1), `event_type` (`MONTHLY_REFRESH` \| `SUSPEND` \| `RESTORE`), `user_id` (null iff `MONTHLY_REFRESH`), `actor_id` (nullable), `summary`, `occurred_at` | `SELECT`, `INSERT (...)` (**INSERT-only**) |

No consumption-deduction, pricing, or conversion table is created in Phase 4, and `mdl_*` tables are untouched.

---

## 4. Locking protocol & concurrency safety

Lock order: institution advisory lock (`INSTITUTION_NAMESPACE = 41001`) → account locks (`lock_accounts`) → QTA advisory lock → row locks (`FOR UPDATE` / `FOR SHARE` in UUID order).

- `QTA_SYNC_NAMESPACE = 52000` — serializes system-group sync and registry updates per institution.
- `QTA_BUDGET_NAMESPACE = 52001` — serializes budget revision numbering (`max(revision) + 1`) with `allocated_for_month` reads.
- `QTA_SUSPENSION_NAMESPACE = 52002` — serializes suspend/restore per institution so concurrent duplicate suspensions cannot both commit.
- `QTA_RESET_NAMESPACE = 52003` — serializes monthly reset execution per institution.

---

## 5. Planned REST API surface (`/api/v1/qta`)

All `GET` routes require `qta.read` (GLOBAL for budgets/groups/models/events/resets; GLOBAL or exact-UNIT for user lookup). All writes require direct GLOBAL `qta.manage` + session + exact Origin + CSRF.

| Method & Path | Permission | Stage | Purpose |
| --- | --- | --- | --- |
| `GET /qta/models` | `qta.read` | Q2 | Active models from `mdl_models` (with `provider_type`) |
| `GET /qta/groups` | GLOBAL `qta.read` | Q2 | List enrolled groups in `qta_quota_groups` (empty before first sync) with `origin`, `in_directory`, active member counts, and per-model quotas |
| `POST /qta/groups/sync` | GLOBAL `qta.manage` | Q2 | Reconcile `SYSTEM` groups from Phase 2 directory into `qta_quota_groups`; preserve `SPECIALIST` groups & existing quotas (`FR-QTA-020`) |
| `GET /qta/groups/sync-runs` | GLOBAL `qta.read` | Q2 | Append-only sync history (`groups_added`, `groups_retired`, counts) |
| `POST /qta/groups` | GLOBAL `qta.manage` | Q2 | Create `AI_SPECIALIST` group via `directory.service.create_group` and enroll in `qta_quota_groups` (`FR-QTA-022`) |
| `GET /qta/groups/{group_id}` | GLOBAL `qta.read` | Q2 | Enrolled group detail + configured per-model quotas |
| `PATCH /qta/groups/{group_id}` | GLOBAL `qta.manage` | Q2 | Rename `AI_SPECIALIST` group via `directory.service.update_group` |
| `POST /qta/groups/{group_id}/activate` / `deactivate` | GLOBAL `qta.manage` | Q2 | Toggle `AI_SPECIALIST` group active flag via `directory.service.set_group_active` |
| `GET /qta/groups/{group_id}/members` | GLOBAL `qta.read` | Q2 | Paginated live directory memberships for an enrolled group |
| `PUT /qta/groups/{group_id}/members/{user_id}` | GLOBAL `qta.manage` | Q2 | Add/reactivate member in an active `AI_SPECIALIST` group via `directory.service.set_membership` |
| `DELETE /qta/groups/{group_id}/members/{user_id}` | GLOBAL `qta.manage` | Q2 | Deactivate member in an `AI_SPECIALIST` group via `directory.service.set_membership` |
| `PUT /qta/groups/{group_id}/quotas` | GLOBAL `qta.manage` | Q2 | Upsert per-model monthly quota rules (`enabled`, `monthly_limit`, `warning_threshold_pct`) for an enrolled group (`FR-QTA-021`) |
| `GET /qta/budgets?month=YYYY-MM` | GLOBAL `qta.read` | Q3 | Current (highest-revision) monthly cap or `"chưa ghi nhận"`, revision history, `allocated`, `remaining`, `over_allocated` warning |
| `PUT /qta/budgets/{month}` | GLOBAL `qta.manage` | Q3 | Append a new `qta_budget_revisions` row for current or next month only, with required `decision_number` + `decision_date`; rejects `total_limit < allocated` (`409` + `{allocated, deficit}`) |
| `GET /qta/users` | In-scope `qta.read` | Q3 | Search users in caller's GLOBAL or UNIT scope for lookup |
| `GET /qta/users/{user_id}/entitlements?month=YYYY-MM` | In-scope `qta.read` | Q3 | Enrolled qualifying groups, additive per-model breakdown & `base_entitlement` (*đơn vị hạn mức*), `actual_consumption: null`, `remaining_quota: null`, `consumption_status: "NOT_INTEGRATED"`, plus (from Q4) active suspension & per-model access evaluation |
| `POST /qta/users/{user_id}/suspensions` | GLOBAL `qta.manage` | Q4 | Kill-switch (`ALL_MODELS` \| `PAID_EXTERNAL_ONLY`), mandatory `reason` & `ordered_by`, optional finite future `expires_at`; operator from session; preserves balance (`FR-QTA-040`) |
| `POST /qta/users/{user_id}/restore` | GLOBAL `qta.manage` | Q4 | Restore suspended user to `ACTIVE` without adding quota (`FR-QTA-041`) |
| `GET /qta/events?month=YYYY-MM` | GLOBAL `qta.read` | Q4 | Append-only QTA events (`MONTHLY_REFRESH`, `SUSPEND`, `RESTORE`); no edit/delete (`FR-QTA-050`) |
| `GET /qta/monthly-resets` | GLOBAL `qta.read` | Q4 | Append-only monthly reset history + current-month `COMPLETED`/`PENDING` status |
| `POST /qta/monthly-resets` | GLOBAL `qta.manage` | Q4 | Manual monthly reset simulation for **current month only** (`Asia/Ho_Chi_Minh`, `PD-Q6`, `FR-QTA-032`) |

---

## 6. Out of scope for Phase 4 (QTA)

- Ad-hoc individual grants, revocations, and credit ledger (`AQ-FRD-UAI-CRT-001` — Phase 5).
- Token-to-credit conversion, commercial pricing, or usage billing (`AGENTS.md`, `PD-Q1`).
- Live AI invocation gateway and actual consumption deduction (`FRD §1.3`).
- Semester / Research Project / Exam quota cycles (forbidden by `FR-QTA-010`, `FR-QTA-050`).
- Any edits to `apps/web/`, `mdl/`, or prototype `localStorage` import.
