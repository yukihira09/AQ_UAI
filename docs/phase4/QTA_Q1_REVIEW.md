# QTA Q0–Q1 review and revision brief (2026-11-26)

**What:** an independent review of the Phase 4 plan (`QTA_IMPLEMENTATION_PLAN.md`, `QTA_OPEN_DECISIONS.md`, `QTA_ARCHITECTURE_AND_DECISIONS.md`, `QTA_REQUIREMENTS_TRACEABILITY.md`) and of the Q1 implementation produced by the Google Antigravity agent, against [AQ-FRD-UAI-QTA-001](../frd/AQ-FRD-UAI-QTA-001.md), [AGENTS.md](../../AGENTS.md) and the existing Phase 2/3 foundations.
**Who:** Claude Code (reviewer), for the Project Owner and the implementing agent.
**Verdict:** Q1 is **well built and does not regress anything**, but the plan contains four design problems that should be fixed **before Q2**. They are cheap to fix now: migrations `0007`/`0008` have never been applied to a persistent database (the developer's `aq-uai-dev` database was observed at `0006_mdl_routing_and_styles` on 2026-11-26). The revision is called **Q1-R** below; its prompt is in [section 5](#5-prompt-for-the-implementing-agent-q1-r).

## 1. Evidence checked

| Check | Result |
| --- | --- |
| Full gate on the Q1 tree (`bash scripts/verify_phase2.sh`, disposable PostgreSQL 18, nginx, Chromium), run by the reviewer | Static checks PASS; `alembic check` clean; **API 495 passed, 1 skipped** (opt-in live provider); **browser 16 passed**; exit 0. Antigravity's API count is confirmed; it had **not** run the browser suite although Q1 edited `apps/admin/assets/pages.mjs` and `tests/browser/test_operations.py` |
| Edits to existing MDL / Phase 2 tests | Legitimate pin updates only (role sets, head revision, error-code tail, `LEGACY_TABLES` import). `test_populated_m1_database_upgrades_to_m2_without_changes` now upgrades to head and expects +2 roles / +3 role-permission rows: correct, name slightly stale |
| RBAC | `qta.manage` is central (direct GLOBAL only); `AI_QUOTA_VIEWER` direct GLOBAL or UNIT; group grants refused by policy and DB checks; `FOUNDATION_ADMIN`/`AI_MODEL_ADMIN` get nothing. Sound |
| Schema / grants | Composite tenant FKs, day-1 month checks, trimmed-text checks, no DELETE anywhere, INSERT-only history tables. Sound, apart from the findings below |
| Prototype semantics (`apps/web/shared/core.js:84`, `actions.js:126-129`, `dialogs.js:48`) | The school total is entered in **credits**; "đã phân bổ" is the **credit ledger** (base + CRT grants − revocations). The dialog states "chưa có quy đổi từ tokens". Group × model quotas are per-model token figures. Reset = one institution-level "Làm mới" event. Suspension "Thời hạn đến" is optional |

## 2. What is good (keep)

- Reuse of Phase 2 groups/memberships as the single source of truth; no duplicate identity tables.
- Separate least-privilege roles, `qta.manage` central, viewer UNIT scope for unit heads (FRD Should).
- Honest consumption model: entitlement computed, consumption `null` / `NOT_INTEGRATED`, no fake usage (QD10).
- Operator identity always from the session; `ordered_by` kept as separate metadata (QD11).
- Month-only invariant at three layers (DB, API, UI planned); append-only grants; idempotent reset key.
- MDL isolation preserved (`mdl/` never imports `qta/`); Q1 tests are thorough on structure.

## 3. Findings

### Must fix before Q2

| # | Finding | Why it matters | Fix |
| --- | --- | --- | --- |
| **F1** | **FR-QTA-011 "allocated" invents a unit equivalence.** QD3 sums per-model limits across *different* models and compares the result with the school total, calling it an "unweighted 1:1 abstract unit" under *delegated/PROV* authority | That is financial semantics: the FRD lists a per-model conversion price as a separate *Should* item, the prototype keeps the total in credits and per-model quotas in tokens, and AGENTS.md forbids inventing conversion rules. Only the Project Owner can declare a common unit | PO decision **PD-Q1** (section 4). Relabel QD3 accordingly |
| **F2** | **The school monthly total is mutable.** `qta_monthly_budgets` allows `UPDATE (total_limit, decision_number, decision_date)`; the audit payload keeps no previous decision number | FR-QTA-010 cites **INV-18**; FR-QTA-050 / RULE-QTA-04 forbid rewriting recorded quota transactions. An overwrite loses which decision authorised the earlier total | Append-only `qta_budget_revisions` (current = highest revision) |
| **F3** | **Group sync has no effect.** QTA reads directory groups live, so groups are visible before any sync; `qta_group_sync_runs` stores only counts | FR-QTA-001 AC2 ("list, even empty before sync") and FR-QTA-020 AC1 ("after sync, system groups appear") cannot be demonstrated honestly; sync is cosmetic | A QTA group registry (`qta_quota_groups`) that sync fills; quotas reference the registry |
| **F4** | **Specialist-group write path conflicts with Phase 2.** QD5 lets `AI_QUOTA_ADMIN` create/edit `AI_SPECIALIST` groups via `/qta/groups`, but `authorization/policy.py::require_group_management` requires `directory.manage` for that kind | Either a second writer of `account_groups` with different rules (forbidden parallel implementation) or a silent permission escalation | Plan must state: extend `require_group_management` so `AI_SPECIALIST` accepts `qta.manage` **or** `directory.manage`; QTA routes call the existing `directory.service` functions (same audit actions) |

### Should fix (in Q1-R docs/schema)

| # | Finding | Fix |
| --- | --- | --- |
| F5 | Suspension `expires_at` mandatory with a 365-day cap: an invented policy (FRD lists "thời hạn"; prototype field optional) | PO decision **PD-Q3**; DB check allows `NULL` |
| F6 | `billing_tier` on `mdl_models` (planned `0009`) changes the accepted MDL module for a distinction the FRD does not require | PO decision **PD-Q2**: drop it |
| F7 | `decision_date` nullable, while FR-QTA-010 says "số / ngày quyết định" and the prototype requires the date | PO decision **PD-Q4** |
| F8 | Budget month window not specified (FRD: current or next month only); no rule for a month without a budget | State in plan; enforce in the budget service |
| F9 | Manual reset may target the *next* month, which pre-empts the real 00:00 run (unique key per month) | PO decision **PD-Q6**: current month only |
| F10 | Provenance: QD3, QD9, QD11 (cap) are policy choices labelled "DECIDED (delegated)"; the instruction was to resolve only *safe* ambiguities | Relabel; record PO decisions with their real provenance |
| F11 | Stage order: FR-QTA-021 AC2 ("no base quota after disabling") and FR-QTA-011 need the entitlement function, which the plan only builds in Q3 | Restage (section 5, item B5) |

### Minor

- Architecture §2.4 heading says QD9 (should be QD11).
- No ADR for QTA (MDL had ADR-0003): add `docs/architecture/ADR-0004-qta.md` (*Proposed*).
- Warning threshold supports percent only (FRD: percent or absolute); acceptable if documented.
- `qta_group_sync_runs` cannot show *which* groups were added or retired; add counts at least.

## 4. Project Owner decisions needed

Each is pre-filled with the reviewer's recommendation. **The Project Owner must confirm or edit them before sending the prompt**; once confirmed they are recorded as PO decisions, not delegated ones.

| ID | Question | Recommendation (for this demo project) |
| --- | --- | --- |
| PD-Q1 | Unit of the school total and of group × model limits; meaning of "allocated" | One abstract **"đơn vị hạn mức"** for every QTA amount; never labelled tokens or credits; no price or conversion. Allocated(M) = Σ base entitlement of every active member across models (= Σ over enrolled active groups of active members × enabled limits). CRT net grants join in Phase 5 through the same function. Quota edits and directory growth are not blocked; over-allocation is shown as a warning |
| PD-Q2 | Meaning of "chỉ mô hình bên ngoài mất phí" | All models of `EXTERNAL` providers. No `billing_tier`, no `0009`, no MDL change |
| PD-Q3 | Suspension duration | Optional `expires_at`; empty = until restored; if given, finite and in the future; no cap |
| PD-Q4 | Decision date for the school total | Required together with the decision number |
| PD-Q5 | Mid-month group/quota changes | Take effect immediately (QD6 as written) |
| PD-Q6 | Manual "simulate reset" | Current month only (`Asia/Ho_Chi_Minh`) |

## 5. Prompt for the implementing agent (Q1-R)

~~~text
# AQ EduUAI — Phase 4 QTA, stage Q1-R (revision of Q0–Q1). Do NOT start Q2.

You produced docs/phase4/* and implemented Q1 (migrations 0007_qta_access_catalog,
0008_qta_schema, qta/models.py, shared contract edits, tests). An independent review
(docs/phase4/QTA_Q1_REVIEW.md) found design problems that must be fixed before Q2.
Do exactly this revision, then stop and report.

## Read first
AGENTS.md, CLAUDE.md, docs/PROJECT_CONTEXT.md, docs/frd/AQ-FRD-UAI-QTA-001.md,
docs/phase4/QTA_Q1_REVIEW.md (findings F1–F11), all docs/phase4/*.md, and, read-only,
the prototype semantics in apps/web/shared/core.js (line ~84), actions.js (~126) and
dialogs.js (~48).

## Hard constraints
- Never read, print or copy .env. Never edit apps/web/. No commits, pushes or deploys.
- Do not touch the developer's running Docker stack (aq-uai-dev). Use disposable
  PostgreSQL only (scripts/verify_phase2.sh creates one).
- 0007/0008 have never been applied to a persistent database (developer DB observed at
  0006 on 2026-11-26). Amend 0008 (and 0007 only if required) IN PLACE; head stays
  0008_qta_schema. If you find evidence that 0007/0008 were applied anywhere persistent,
  stop and report instead of editing them.
- Do not invent units, prices, token/credit conversion, consumption or institutional
  policy. Do not change mdl/ code. No Q2 routes, services or UI.

## Project Owner decisions (recorded by the Project Owner, 2026-11-26)
Record these verbatim in QTA_OPEN_DECISIONS.md with provenance "Project Owner decision,
2026-11-26" (not "delegated"):
- PD-Q1 Unit & allocation (FR-QTA-011): every QTA amount (school monthly total, group ×
  model monthly limit) is one abstract unit, "đơn vị hạn mức". It is never labelled
  tokens or credits; no price or conversion exists. Allocated(month) = sum of the base
  entitlement of every ACTIVE user across all models = sum over enrolled, active groups
  of (active members in ACTIVE state × sum of enabled per-model limits). Reducing the
  total below allocated -> 409 QTA_BUDGET_BELOW_ALLOCATED with {allocated, deficit}.
  CRT net grants will be added to allocated in Phase 5 through the same function.
  Directory growth and quota edits are never blocked; over-allocation is shown as a
  warning. Valid for this demo project; not an institutional accounting rule.
- PD-Q2 PAID_EXTERNAL_ONLY = all models whose provider is EXTERNAL. Remove
  mdl_models.billing_tier and migration 0009 from every plan and document.
- PD-Q3 Suspension expires_at is optional (NULL = until restored); if given it must be
  finite and in the future. No 365-day cap. ordered_by stays mandatory text; the
  operator always comes from the session.
- PD-Q4 decision_date is required together with decision_number for the school total.
- PD-Q5 Mid-month membership/group/quota changes take effect immediately (QD6).
- PD-Q6 Manual reset simulation is allowed for the current month only
  (Asia/Ho_Chi_Minh); never for a future month.

## A. Schema changes (0008, qta/models.py, db/provision.py, db/audit.py, tests)
1. F2 — Replace qta_monthly_budgets with append-only qta_budget_revisions:
   id, institution_id, period_month (day 1), revision (>= 1), total_limit (> 0),
   decision_number (trimmed, NOT NULL), decision_date (NOT NULL), recorded_by (composite
   user FK), recorded_at; UNIQUE (institution_id, period_month, revision).
   Runtime grant: SELECT + INSERT only. The current total of a month = highest revision.
   Audit payload BudgetRevisionRecorded: period_month, revision, before_limit,
   after_limit, before_decision_number, decision_number, decision_date.
2. F3 — Add the QTA group registry qta_quota_groups:
   institution_id, group_id, group_kind, origin ('SYNC' | 'SPECIALIST'),
   in_directory (bool, maintained by sync), enrolled_by, enrolled_at, last_synced_at;
   PRIMARY KEY or UNIQUE (institution_id, group_id); CHECK group_kind IN ('SYSTEM',
   'AI_SPECIALIST'); CHECK origin/group_kind consistency (SYNC <-> SYSTEM,
   SPECIALIST <-> AI_SPECIALIST).
   Composite FK (institution_id, group_id, group_kind) -> account_groups(institution_id,
   id, kind). This needs an additive UNIQUE (institution_id, id, kind) on
   account_groups; the runtime role cannot UPDATE account_groups.kind (verified), so the
   FK is sound. Put that constraint in 0008 and mirror it in db/identity.py.
   Runtime grant: SELECT, INSERT, UPDATE (in_directory, last_synced_at) only; no DELETE.
   qta_group_model_quotas must reference the registry: FK (institution_id, group_id) ->
   qta_quota_groups, so only enrolled groups can have quotas (AUTHORIZATION groups can
   never be enrolled).
3. qta_group_sync_runs: add groups_added and groups_retired (>= 0) next to the counts.
4. F5 — qta_suspensions.expires_at nullable with
   CHECK (expires_at IS NULL OR (isfinite(expires_at) AND expires_at > suspended_at));
   UserSuspended.expires_at optional.
5. Update LEGACY_TABLES, QTA_RUNTIME_PRIVILEGES, REQUIRED_SCHEMA_REVISION stays 0008.

## B. Plan and decision documents
1. F10 — In QTA_OPEN_DECISIONS.md add PD-Q1..PD-Q6, and relabel every QD entry
   accurately: SPEC (FRD), REC (engineering recommendation), PROV (assumption),
   PO (Project Owner decision), or NEEDS-INSTITUTION. Nothing about units, money,
   suspension policy or accounting may be labelled "delegated".
2. F4 — Q2 group-management boundary: extend authorization/policy.py
   require_group_management so kind AI_SPECIALIST accepts qta.manage OR
   directory.manage (SYSTEM and AUTHORIZATION unchanged). QTA specialist-group routes
   call the existing directory.service functions (create_group, update_group,
   set_group_active, set_membership) with their existing audit actions, and enrol the
   group in qta_quota_groups in the same transaction. No parallel implementation.
   (Plan only; implement in Q2 with tests.)
3. F3 — Sync semantics: POST /qta/groups/sync enrols active SYSTEM groups not yet in the
   registry, sets in_directory=false for enrolled SYSTEM groups that are inactive or
   gone in the directory (never deletes; their quotas stop contributing), sets it back
   to true when they return, never touches SPECIALIST entries, and writes one
   qta_group_sync_runs row + audit event in the same transaction. Memberships are read
   live from the directory (documented). Before the first sync the QTA group list is
   empty.
4. F8 — Budgets: only the current or next month (Asia/Ho_Chi_Minh) may receive a new
   revision; past months are read-only. A month without a revision shows
   "chưa ghi nhận"; group quotas still apply.
5. F11 — Restage Q2–Q6 so each stage is testable end to end:
   Q2 registry + sync + specialist groups (via directory.service) + group × model quota
      configuration (FR-QTA-001 API part, 020, 021 config, 022);
   Q3 entitlement function + additive lookup + school total with the allocation guard
      (FR-QTA-010, 011, 021 AC2, 030, 031);
   Q4 kill-switch / restore (PAID_EXTERNAL_ONLY = EXTERNAL providers, check_ai_access
      seam) + monthly reset (FR-QTA-040, 041, 032, 050);
   Q5 admin UI #qta (all UI ACs, unit label "đơn vị hạn mức", no tokens/credits wording);
   Q6 full verification, backup/restore and 0006 -> head upgrade with QTA data,
      FR-MDL-020 AC3 end-to-end proof, handoff and manual checklist.
   For every stage list FRs, files, tests (names), exclusions and gate.
6. Remove every mention of billing_tier / 0009 and of the 365-day cap. Fix the §2.4
   heading (QD11). Update the numerical example to the "đơn vị hạn mức" wording.
7. Add docs/architecture/ADR-0004-qta.md (status Proposed) in the style of ADR-0003.
8. Update QTA_REQUIREMENTS_TRACEABILITY.md (new tables, new stage mapping) and
   QTA_ARCHITECTURE_AND_DECISIONS.md §3–§5 (schema, locks, API surface).
9. Add a "Q1-R completion" section to QTA_IMPLEMENTATION_PLAN.md listing every file
   changed and why, and the exact verification results. Update CLAUDE.md,
   docs/PROJECT_CONTEXT.md and docs/acceptance-matrix.md status lines.

## C. Tests
- Update tests/unit/test_q1_contracts.py and tests/integration/test_q1_qta_schema.py:
  budget revisions INSERT-only and unique per (institution, month, revision);
  decision_date required; registry grants (no DELETE, only in_directory/last_synced_at
  updatable); registry FK refuses an AUTHORIZATION group and a cross-tenant group;
  origin/kind consistency; quotas refuse a group that is not enrolled; NULL expiry
  accepted, past expiry refused; new audit payload shapes; LEGACY_TABLES covers the new
  table.
- Keep the populated 0006 -> head upgrade test and also assert account_groups rows and
  memberships are unchanged by the new UNIQUE constraint.
- Run the full gate, including the browser suite:
  AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv python> \
  AQ_NGINX=<nginx or wrapper> bash scripts/verify_phase2.sh
  Baseline measured on the current Q1 tree (2026-11-26): API 495 passed, 1 skipped
  (opt-in live provider); browser 16 passed. Report API and browser counts separately,
  explain any change, and never report tests you did not run.

## Final report
1. Changes made and every modified/created file. 2. Commands run and exact results
(API, browser, static checks, alembic check). 3. Anything blocked or unverified.
4. Remaining decisions or risks. Then stop: Q2 needs a separate instruction.
~~~

## 6. Q1-R verification (2026-11-27)

**Verdict: Q1-R is accepted by the reviewer as technically complete. Q2 may start once the Project Owner authorizes it.** (Reviewer verification, not formal acceptance.)

| Check | Result |
| --- | --- |
| Findings F1–F11 | All addressed. F1, F5–F7 and F9 via PD-Q1..PD-Q6 (recorded with Project Owner provenance; the PO sent the brief to the agent unchanged, which the reviewer treats as confirmation); F2 `qta_budget_revisions` (INSERT-only, decision date required); F3 `qta_quota_groups` registry with composite FK to `account_groups(institution_id, id, kind)`, quotas bound to the registry; F4 `require_group_management` extension planned for Q2 with `directory.service` reuse; F8 budget window; F10 provenance relabelled; F11 restaged Q2–Q6; ADR-0004 added (*Proposed*) |
| Schema review | `0008` amended in place (developer DB still at `0006` on 2026-11-27). Grants: zero DELETE; six INSERT-only tables; registry UPDATE only on `in_directory`, `last_synced_at`. ORM mirrors the migration (`alembic check` clean) |
| Tests | Registry refuses `AUTHORIZATION`, cross-tenant and mis-declared kinds (FK, not only CHECK); quotas refuse unenrolled groups; revision uniqueness; NULL/future/past expiry; populated `0006 → 0008` upgrade keeps `account_groups` and memberships byte-identical |
| Full gate re-run by the reviewer (`bash scripts/verify_phase2.sh`) | Static checks PASS; `alembic check` clean; **API 495 passed, 1 skipped**; **browser 16 passed**; exit 0. Matches the agent's report |
| Stale references | None to the old design outside deliberate history (ADR alternatives, change records) |

**Reviewer corrections applied on 2026-11-27 (documentation only):**

- Sync gap originating in this brief: `AI_SPECIALIST` groups created through the Phase 2 directory UI could never be enrolled (sync enrolled only `SYSTEM`; specialist enrolment only via QTA creation). Q2 sync must also enrol not-yet-enrolled active `AI_SPECIALIST` groups as `origin='SPECIALIST'` and never modify existing ones. Updated `QTA_ARCHITECTURE_AND_DECISIONS.md` §2.5, `QTA_OPEN_DECISIONS.md` QD4, `QTA_IMPLEMENTATION_PLAN.md` Q2 (service and tests).
- `docs/PROJECT_CONTEXT.md`: the developer stack note still said `0002`; it is `0006` (MDL), with `0007`/`0008` not applied.

**Points for the Q2 implementer to watch:**

- `require_group_management` is shared Phase 2 code: test that `qta.manage` still cannot touch `SYSTEM` or `AUTHORIZATION` groups, and that existing directory behaviour is unchanged.
- Budget revision numbers: serialize writers (`QTA_BUDGET_NAMESPACE`) and map a unique-violation race to 409, never 500.
- `in_directory` is a sync-time snapshot; entitlement must still check `account_groups.active` live (PD-Q5), as QD6 states.
