# Phase 5 — CRT (Cấp / Thu hồi Hạn mức) implementation plan

**Status (2026-11-27):** plan, written by the reviewer (Claude Code). Nothing in Phase 5 is implemented. Each stage needs explicit PO authorization (see [operating rules](../agents/ANTIGRAVITY_OPERATING_RULES.md) R1).
**FRD:** [AQ-FRD-UAI-CRT-001](../frd/AQ-FRD-UAI-CRT-001.md): 9 Must FRs (001, 002, 010, 011, 012, 013, 020, 021, 022, 030, 040), 1 Should (031), RULE-CRT-01..05.
**Builds on:**
- QTA Phase 4: [handoff](../phase4/qta-handoff.md) §8 "Notes for Phase 5", [architecture](../phase4/QTA_ARCHITECTURE_AND_DECISIONS.md), PD-Q1 (one unit, "đơn vị hạn mức"), lock namespaces 52000–52003.
- Blueprint §"CRT" (permissions `crt.read`/`crt.grant`/`crt.reclaim`, gate G7: "parallel overgrant blocked; duplicate retry idempotent; no mutation of prior rows").

**How to use this plan:** the PO authorizes a stage, e.g. "Implement CRT stage C1", and pastes [CRT_STAGE_PROMPT.md](CRT_STAGE_PROMPT.md) with the stage filled in. The agent follows this plan's stage spec, the operating rules and `AGENTS.md`. Reports go to `docs/phase5/reports/`; log entries go to [AGENT_LOG.md](AGENT_LOG.md).

---

## 1. What CRT is, in plain words

QTA gives each person a **base** monthly amount per model: the sum of their groups' quotas. CRT adds **individual adjustments for the current month only**:
- **Cấp bổ sung (grant):** add an amount to one identified person for one model, with a decision number as the legal basis.
- **Thu hồi (revocation):** take an amount back from one person, up to what they still have, with a basis.

Every grant and revocation is one **append-only ledger row**. Balances are **computed** from base + ledger, never typed in. At month change, the new month simply has no grants yet. Nothing is rewritten.

Consumption is still **NOT_INTEGRATED**: nobody measures real AI usage yet. So "đã dùng" (used) is shown as "Chưa tích hợp đo tiêu thụ thực tế", never as a number.

## 2. Decisions to confirm before C1 (PD-C1..PD-C10)

These are **reviewer recommendations (REC)**. In stage C0 the agent records them in `CRT_OPEN_DECISIONS.md` and may argue against them. The PO then confirms by writing in the chat to the agent, e.g. "PD-C1..PD-C10 approved as recommended" or "PD-C5: central only". The agent records the PO's exact words and the date. **C1 must not start until every PD-C is `PO` or explicitly deferred.**

| ID | Question | Recommendation (REC) | Why / trade-off |
| --- | --- | --- | --- |
| PD-C1 | Unit and granularity | Amounts are "đơn vị hạn mức" (PD-Q1), **per (person, model)**. | QTA entitlements and `check_ai_access` are per model. A model-agnostic pool could not be added to them without a conversion rule, which is forbidden. Cost: a grant targets one model at a time. |
| PD-C2 | Effective period | Always the **current institution month** (`Asia/Ho_Chi_Minh`). There is no month field in grant/revoke bodies (mirrors PD-Q6). Grants simply stop counting when the month changes: no reset write, no rollover. | FR-CRT-012, RULE-CRT-03. Back-dating or pre-granting next month is impossible by design. |
| PD-C3 | Balance formula | Per (user, model, month): `effective = max(0, base + Σgrants − Σrevocations)`. `used` = NOT_INTEGRATED (null). `revocable_max = effective`, labelled "chưa trừ phần đã dùng (chưa tích hợp đo tiêu thụ)". A revocation may reduce below base. This is needed for FR-CRT-031 "thu hồi toàn bộ số dư". | FR-CRT-021 requires the maximum to be computable. Alternative: revoke only the granted part. That is simpler, but FR-CRT-031 could then never revoke everything. Because base is live, if base later drops, effective clamps at 0 and the ledger is never edited. |
| PD-C4 | Ceiling for grants (FR-CRT-013) | `grant ≤ school remaining = current budget total_limit − allocated_for_month`, where allocated **includes** net grants. If no budget is recorded for the month → `409 CRT_BUDGET_NOT_RECORDED`. Serialized with QTA's `QTA_BUDGET_NAMESPACE = 52001`. The error returns `details.remaining`. | Reuses the QTA budget as the "sổ người cấp". FR-QTA-011 then automatically blocks reducing the budget below base + grants. Quota edits may still over-allocate (PD-Q1); this is documented. |
| PD-C5 | Unit heads (Trưởng đơn vị) | Must scope **includes** a UNIT-scoped grant/reclaim role, limited to users whose `primary_unit_id` is in scope, and bounded by the same school remaining. There is **no** separate unit sub-budget (two-ledger accounting is "Could", QD12). | FR-CRT-013 AC2 names the unit-head case. A unit sub-budget would invent policy. Alternative: central admins only (simpler; AC2 untestable). |
| PD-C6 | Basis fields | Grant and revoke: `decision_number` **required** (1–128 characters, trimmed). Optional: `decision_date`, `approver` (text), `fund_source` (text), `note`. | FRD §6 open point: "prototype Must ít nhất số tờ trình/quyết định". The optional fields avoid inventing a mandatory approval policy. |
| PD-C7 | Beneficiary identity (FR-CRT-010/020) | The target is an existing user of the institution with `state = ACTIVE`, a non-empty `institutional_code` and a primary unit. The ledger row **snapshots** `display_name`, `institutional_code`, unit code and unit name at write time, next to the `user_id` foreign key. | The person-level identification required by the FRD can never change afterwards (append-only), even if the directory is edited. Groups/units cannot be targets. |
| PD-C8 | Retries (blueprint G7) | The client sends a `request_key` (UUID). Unique per institution. Same key with the same payload → returns the original row (`200`, no new row). Same key with a different payload → `409 CRT_REQUEST_KEY_REUSED`. | Prevents double grants on a network retry; the admin UI generates one key per dialog. |
| PD-C9 | Should items | **Not in the Must stages.** FR-CRT-031 (auto-revoke on account disable) touches the directory disable flow; export (Excel/PDF); a user self-view. Each is offered as optional stage **C7** only if the PO authorizes it. Otherwise the C6 handoff records "Should chưa đạt" (allowed by FR-CRT-031 AC2). | Keeps the Must path small and reviewable. |
| PD-C10 | Names | API `/api/v1/crt`. Permissions `crt.read`, `crt.grant`, `crt.reclaim`. Roles: `AI_ALLOCATION_ADMIN` (direct GLOBAL: all three); `AI_ALLOCATION_UNIT_ADMIN` (direct UNIT: all three, PD-C5); `AI_ALLOCATION_VIEWER` (GLOBAL or UNIT: read). Tables `crt_*`. UI menu "Cấp / Thu hồi Hạn mức". **Never** "credit" or "Nạp" in UI labels (FR-CRT-002). | `crt.export` is added only with the export Should item. |

## 3. Architecture (target design; C0 turns it into `CRT_ARCHITECTURE_AND_DECISIONS.md`)

- **Module:** `apps/api/src/aq_uai_api/crt/` (`models.py`, `schemas.py`, `balances.py`, `queries.py`, `service.py`) plus `api/v1/crt.py`. Same patterns as `qta/`. MDL never imports `crt`. CRT may import QTA's read helpers (`entitlements`, `periods`, `access`).
- **Ledger table `crt_transactions` (INSERT-only for the runtime role):**
  - `id`, `institution_id`, `period_month` (day-1 CHECK), `kind` (`GRANT` | `REVOKE`);
  - `user_id`, `model_id` (composite FKs with `institution_id`), `amount` (int, `> 0`, `≤ 1 000 000 000`);
  - `decision_number` (NOT NULL, non-blank CHECK), `decision_date`, `approver`, `fund_source`, `note`;
  - beneficiary snapshot (`beneficiary_display_name`, `beneficiary_code`, `beneficiary_unit_id`, `beneficiary_unit_code`, `beneficiary_unit_name`);
  - `request_key` (UNIQUE with `institution_id`), `actor_id`, `created_at` (server default).
  - The runtime role gets `SELECT` plus column-level `INSERT` only: no UPDATE, no DELETE (like QTA).
- **Balance engine (`crt/balances.py`):** one SQL aggregate `net_adjustments(db, institution, month, user_id=None, model_id=None)` returns Σgrants − Σrevocations per (user, model). Per-person views use `effective = max(0, base + net)`.
- **QTA integration (stage C3, the only stage allowed to edit `qta/`):**
  - `entitlements.allocated_for_month(db, institution_id, month)` gains the month parameter and returns `Σ over (user, model) of max(0, base + net)`. Base pairs and grant-only pairs are both included.
  - `check_ai_access` step 6 (`NO_ENTITLEMENT`) uses `effective` instead of base.
  - The QTA lookup's per-model row gains `individual_adjustment` (net, signed) and `effective_entitlement`. The C5 identifier test must stay green: no forbidden words in these names.
  - Pinned QTA key-set tests are updated only where the C3 spec lists them.
- **Locks (global order, extends QTA §4.3):** institution (41001, shared) → account locks (target user + actor, sorted) → `QTA_BUDGET_NAMESPACE` 52001 (**grants only**) → row locks. Revocations need no budget lock: they only lower allocation, and the target-user account lock serializes concurrent grant/revoke on the same person. No new namespace unless C4 proves one is needed; if so, use `53000` and document it.
- **Errors (new codes):**

  | Code | HTTP | Meaning / details |
  | --- | --- | --- |
  | `CRT_BUDGET_NOT_RECORDED` | 409 | No school budget recorded for the month |
  | `CRT_EXCEEDS_REMAINING` | 409 | `details.remaining` |
  | `CRT_EXCEEDS_BALANCE` | 409 | `details.revocable` |
  | `CRT_TARGET_NOT_ELIGIBLE` | 422 | Not ACTIVE, no code, or outside the unit scope → 404 for scope |
  | `CRT_REQUEST_KEY_REUSED` | 409 | Same `request_key`, different payload |
  | `QTA_MODEL_NOT_ELIGIBLE` | — | Reused for an unusable model |

- **Audit:** `crt.granted` and `crt.revoked` (typed payloads: user, model, amount, month, `decision_number`; no free-text note). Same transaction as the ledger row.

## 4. Stages

Each stage lists: scope, allowlist, tests, mutation proofs and exit criteria. The expected baseline is the previous stage's final gate (after Phase 4 Q6 review: **API 583 passed, 1 skipped; browser 21 passed**; the reviewer confirms in `QTA_Q6_REPORT.md` §11).

### C0 — Design documents and decisions (docs only)
- **Scope:** create the following, plus traceability for all CRT FRs/ACs/RULEs (`CRT_REQUIREMENTS_TRACEABILITY.md`) and an `AGENT_LOG.md` entry:
  - `docs/phase5/CRT_ARCHITECTURE_AND_DECISIONS.md`, turning §3 into a full design with a numerical example: base 1.000; grant 500 → 1.500; revoke 1.300 → 200; budget 10.000 with allocated 9.800 → a grant of 300 is refused with remaining 200;
  - `CRT_OPEN_DECISIONS.md` (PD-C1..10 with status and provenance);
  - `docs/architecture/ADR-0005-crt.md` (status Proposed).

  The agent critiques PD-C1..10 in report §10.
- **Allowlist:** `docs/phase5/**`, `docs/architecture/ADR-0005-crt.md`, the CRT row of `docs/PROJECT_CONTEXT.md` and `docs/acceptance-matrix.md`, status line in `CLAUDE.md`. **No code.**
- **Exit:** the PO has confirmed or changed every PD-C in writing, and it is recorded in `CRT_OPEN_DECISIONS.md` with the date. The gate is unchanged (docs only: static checks are enough; say so).

### C1 — Access catalog (RBAC)
- **Scope:**
  - migration `0009_crt_access_catalog`: 3 permissions, 3 roles per PD-C10, CHECK constraints (admin direct GLOBAL only; unit admin direct UNIT only; no inheritance through authorization groups, like `0007`);
  - `PermissionCode` and `authorization/policy.py` entries (`crt.grant`/`crt.reclaim` must be grantable at UNIT scope, so they must **not** go into `_CENTRAL_PERMISSIONS`; verify how UNIT-scoped write permissions are resolved before choosing);
  - `/directory/capabilities` exposes them;
  - role labels in `apps/admin/assets/pages.mjs` (label map only).
- **Allowlist:**
  - new: `apps/api/migrations/versions/0009_*.py`, `apps/api/tests/unit/test_c1_contracts.py`, `apps/api/tests/integration/test_c1_crt_access.py`;
  - modified: `db/identity.py` (enum), `authorization/policy.py`, the `pages.mjs` label map, permission-catalog pin tests (list each);
  - docs.
- **Tests:** role constraints (GLOBAL/UNIT/no group inheritance), the permission matrix, capabilities, existing roles unchanged, upgrade `0008 → 0009` keeps data, `alembic check`.
- **Mutation proofs:** drop one CHECK constraint → a test fails; put `crt.grant` in central-only → the UNIT test fails.
- **Exit:** gate green; no CRT routes yet.

### C2 — Ledger schema
- **Scope:**
  - migration `0010_crt_ledger`: `crt_transactions` per §3, with all CHECKs, composite FKs and the unique `request_key`;
  - ORM `crt/models.py`;
  - `db/provision.py` runtime grants (SELECT + column INSERT only) and the `LEGACY_TABLES`/ownership list, so backup/restore provisioning works;
  - `db/audit.py`: `crt.granted`, `crt.revoked` actions and typed payloads.
- **Allowlist:** new migration, `crt/__init__.py`, `crt/models.py`, `db/provision.py`, `db/audit.py`, privilege pin tests (list each), new `tests/integration/test_c2_crt_schema.py`, docs.
- **Tests:**
  - runtime cannot UPDATE or DELETE; can INSERT only the listed columns;
  - every CHECK constraint (amount ≤ 0, blank decision, non-day-1 month, bad kind);
  - cross-tenant foreign keys rejected; `request_key` unique;
  - `0009 → 0010` upgrade on populated data; `alembic check`.
- **Mutation proofs:** grant DELETE in provision → test fails; remove the `amount > 0` CHECK → test fails.
- **Exit:** gate green; still no CRT routes.

### C3 — Balance engine and QTA integration (the only stage that edits `qta/`)
- **Scope:**
  - `crt/balances.py`;
  - `qta/entitlements.py`: `allocated_for_month` with month and net adjustments; `compute_user_entitlements` with `individual_adjustment` and `effective_entitlement`;
  - `qta/access.py` step 6 on effective;
  - `qta/schemas.py` (two new output fields);
  - `qta/service.py` `record_budget_revision` passes the month.
- **Allowlist:**
  - those QTA files plus `crt/balances.py`;
  - new `tests/unit/test_c3_balances.py` and `tests/integration/test_c3_qta_crt_integration.py`;
  - edits to QTA tests **only** where a pinned key set or a recomputed number must change: list file, line, before/after;
  - `apps/admin/assets/qta.mjs` (show adjustment and effective in the lookup formula: `1.000 (G1) + 500 (cấp bổ sung) = 1.500 đơn vị hạn mức`);
  - `tests/browser/test_qta.py` only if a label assertion changes;
  - docs.
- **Tests:** ledger rows are inserted directly with the owner role, because there is no API yet.
  - Formula cases: grant-only user with no group; revoke below base; clamp at 0 when base later drops.
  - Month isolation: November grants are invisible in December.
  - `allocated` includes grants, and FR-QTA-011 now refuses reducing the budget below base + grants.
  - `check_ai_access`: a grant-only user is ALLOWED; a fully revoked user gets NO_ENTITLEMENT.
  - **The whole QTA suite stays green.** The C5 forbidden-identifier test stays green.
- **Mutation proofs:** drop the `max(0, …)` clamp → test fails; sum grants across months → the month-isolation test fails; base-only in `check_ai_access` → test fails.
- **Exit:** gate green, with the QTA counts unchanged except for the listed edits.

### C4 — CRT API (grant, revoke, balances, ledger)
- **Scope:** `api/v1/crt.py`, `crt/schemas.py`, `crt/queries.py`, `crt/service.py`, error codes in `api/errors.py`, router registration in `main.py`/`api/v1/__init__`. Routes:
  - `GET /crt/users?q=`: beneficiary picker, scoped, ACTIVE with code only (FR-CRT-010/020);
  - `GET /crt/users/{id}/balances`: per usable model: base, grants, revocations, net, effective, `used: null` + `consumption_status`, `revocable_max`;
  - `POST /crt/grants` and `POST /crt/revocations` (`201`; `200` on an idempotent replay);
  - `GET /crt/ledger?month=&kind=&user_id=&model_id=` (newest first, scoped);
  - `GET /crt/budget`: current month total, allocated, remaining (read-only mirror of the QTA budget for the CRT screen).

  No PUT/PATCH/DELETE anywhere.
- **Rules:**
  - PD-C2: the month is server-side current only, and any `month` field in a body is rejected with 422;
  - PD-C4: the ceiling is checked under 52001;
  - PD-C3: the revocable check uses a balance read **after** taking the target's account lock;
  - PD-C5: UNIT scope → out-of-unit target returns 404;
  - PD-C7 snapshot; PD-C8 idempotency; typed audit in the same transaction.
- **Allowlist:**
  - the files above;
  - new `tests/unit/test_c4_contracts.py` (OpenAPI: exact routes, no mutation verbs, strict inputs, a forbidden-word identifier rule on `/crt` like C5, allowing only the consumption fields);
  - new `tests/integration/test_c4_crt_api.py`;
  - `test_mdl_import_closure…` extended to assert MDL never reaches `crt`;
  - docs.
- **Tests (minimum):**
  - every FR-CRT AC that is testable in the API;
  - **parallel over-grant:** two threads that each fit alone but not together → exactly one 201 and one `CRT_EXCEEDS_REMAINING`;
  - parallel revoke over balance → one succeeds;
  - idempotent replay, and key reuse with a different payload;
  - budget not recorded; UNIT scope; RBAC/CSRF/Origin; tenant isolation;
  - audit rollback (revoke audit INSERT → nothing persists);
  - the FR-CRT-021 example: balance 1.300 → `revocable_max` 1.300; revoking 1.301 is refused; revoking 300 leaves 1.000;
  - a counted-query test for the ledger and users lists.
- **Mutation proofs:** remove the 52001 lock → the parallel test fails; drop the revocable check → test fails; ignore `request_key` → the replay test fails; skip the unit-scope check → test fails.
- **Exit:** gate green.

### C5 — Admin UI `#crt`
- **Scope:** `apps/admin/assets/crt.mjs` (one module like `qta.mjs`), route and section registration in `app.mjs`/`pages.mjs`, `api.mjs` `safeDetails` gains `remaining` and `revocable` (non-negative safe integers), and `admin.css` (append-only). Screen:
  - a budget strip (total / allocated / remaining for the current month);
  - **Cấp bổ sung** dialog: person picker showing name, code and unit; model; amount; decision number required; optional fields; "Hiệu lực: tháng MM/YYYY — hết hiệu lực khi làm mới ngày 01", read-only; one `request_key` per dialog;
  - **Thu hồi** dialog: person picker limited to people with `revocable > 0`; a summary of base, grants, revocations and effective; "Đã dùng: Chưa tích hợp…"; amount defaulted to `revocable_max` and editable downward; decision number required;
  - ledger table: read-only, no Sửa/Xóa, filters by month, kind and person.

  Write controls are gated on scope; a UNIT admin only sees own-unit people.
- **Allowlist:** the files above, `tests/browser/test_crt.py` (≤ 4 tests, real clock, months computed in Asia/Ho_Chi_Minh, `timezone_id` set), docs. **Not** `qta.mjs`, `mdl.mjs`, `ui.mjs` (unless an additive helper is unavoidable; justify it), `apps/web/`.
- **Tests:**
  - every UI AC of FR-CRT-001/002/010/011/012/013/020/021/022/030/040;
  - DOM checks over `#crt`: no `Nạp`/`credit`/`token`/`ví`/`học kỳ`/`đề tài`/`đợt thi`; only the current month shown for grants; no Sửa/Xóa in the ledger; no "số dư = …" input; no consumption number;
  - 375 px layout; screenshots.
- **Mutation proofs:** render the grant button without scope → test fails; default the revoke amount to 0 → the FR-CRT-021 test fails; a "Nạp credit" label → the wording check fails.
- **Exit:** gate green.

### C6 — Verification, isolation, upgrade, backup/restore, handoff
- **Scope (mirrors QTA Q6):**
  - Extend the MDL isolation proof: an MDL connection test leaves `crt_transactions` and the tester's effective balance untouched. Positive control and reverse direction included.
  - Populated `0008 → 0010` upgrade test.
  - `pg_dump`/`pg_restore` browser test with CRT data: rows identical, UI renders, append-only enforced, a `request_key` replay still idempotent.
  - `docs/phase5/crt-handoff.md` (copy the `qta-handoff.md` structure: upgrade steps for `aq-uai-dev` 0008 → 0010, role grants, a manual acceptance checklist for every FRD line, known limitations, Should items status).
  - Phase 5 closure docs; an acceptance matrix covering all 33 FRs with **formal acceptance unchanged**.
- **Allowlist:** new C6 tests, the handoff, docs. No `src/` changes.
- **Exit:** gate green; the handoff is complete. The reviewer then runs the Docker rehearsal (`0008 → 0010` on the developer's real path) independently.

### C7 (optional, only if the PO authorizes) — Should items
- FR-CRT-031 auto-revoke on account disable. This touches `directory/service.py` `set_user_state`: one revocation row per (model with effective > 0), with the reason "Nghỉ việc / thôi học", in the same transaction, idempotent.
- Ledger export (CSV first; Excel/PDF needs a new dependency → PO decision).

## 5. Phase-level rules specific to CRT (in addition to the operating rules)

1. **Money-like language is banned in UI:** no "Nạp", "credit", "ví", "coin", "nạp tiền", prices or currency. Amounts are "đơn vị hạn mức".
2. **Balances are derived, never stored.** No balance column, no "set balance" endpoint.
3. **One person per row.** There are no group, unit or project beneficiaries anywhere: API, DB or UI.
4. **Current month only** for every write. Reads may show past months as history.
5. **QTA stays green.** Only C3 may edit `qta/`. Any QTA number change outside C3's listed edits is a STOP condition.
6. **Concurrency is tested, not assumed:** every ceiling or balance invariant has a parallel-request test.

## 6. Stage order, batching and review checkpoints (recommended)

| Batch the PO may authorize in one message | Why | Reviewer checkpoint after |
| --- | --- | --- |
| C0 alone | Decisions must be confirmed by the PO before any code | PO confirms PD-C in chat (no reviewer needed) |
| C1 + C2 | Schema-only, low coupling; each with its own report | Optional |
| C3 alone | Touches QTA; highest regression risk | **Recommended** (or at least the PO checks the QTA counts) |
| C4 alone | Concurrency and security core | **Recommended** |
| C5 + C6 | UI + closure | **Required** before Phase 5 is called technically complete |

When the reviewer is unavailable, the PO can still run batches. The operating rules make each stage self-contained and stop on red. The reviewer later reviews stage by stage from `AGENT_LOG.md` and the per-stage evidence. **Please commit after each stage**, either yourself or by telling the agent "commit after each stage". The reviewer can then diff, bisect and revert one stage at a time.
