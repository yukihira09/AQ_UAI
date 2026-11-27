# Prompt for the implementing agent — QTA Stage Q3

**Use:** the Project Owner pastes everything inside the fence below to the implementing agent (Google Antigravity). After it finishes, the reviewer (Claude Code) reads `docs/phase4/reports/QTA_Q3_REPORT.md` and the evidence folder `docs/phase4/reports/q3/` and verifies them independently.

**Reviewer decisions baked into this prompt** (recommendations within the PO's existing PD-Q1..PD-Q6; not new PO decisions). Antigravity must list them in report §8:
- R1: Past months are read-only and have no allocation snapshot (architecture §2.1 "PROV"). `GET /qta/budgets` for a past month returns its revision history, with `allocated`, `remaining` and `over_allocated` set to `null` and `allocation_status: "NOT_SNAPSHOTTED"`. The entitlement lookup accepts the current or next month only.
- R2: A month outside the allowed window gets a new error code `QTA_PERIOD_NOT_OPEN` (422). A malformed or non-month value keeps `QTA_INVALID_PERIOD` (422).
- R3: The API names the month field `month` (`"YYYY-MM"`), never `period_month`, because the Q2 contract test forbids "period" in API schemas.
- R4: The Q2 forbidden-word test is narrowed only so that response schemas may contain exactly `actual_consumption` and `consumption_status`. These two fields are required by architecture §2.3. Inputs stay fully strict.

~~~text
# AQ EduUAI — Phase 4 QTA, Stage Q3 (authorized by the Project Owner). Do Q3 only.

Stage Q3 = live entitlement computation + personal additive lookup + append-only school
monthly budgets with the "cannot go below allocated" guard.
FRs: FR-QTA-010 (AC1, AC2; AC3 API part = month-only), FR-QTA-011 (AC1),
FR-QTA-021 (AC2), FR-QTA-022 (AC2), FR-QTA-030 (AC1, AC2), FR-QTA-031 (AC1, AC2).
Rules: RULE-QTA-01 (month only), RULE-QTA-02 (additive, never max), RULE-QTA-04 / INV-18
(append-only).
NOT in Q3: kill-switch/suspension, check_ai_access, monthly reset, events, admin UI (Q4–Q5).
Never fabricate consumption: actual_consumption and remaining_quota are always null.

## 0. Read first (in this order)
AGENTS.md, CLAUDE.md, docs/PROJECT_CONTEXT.md, docs/frd/AQ-FRD-UAI-QTA-001.md (§3.1–§3.3),
docs/phase4/QTA_IMPLEMENTATION_PLAN.md (Q3), QTA_ARCHITECTURE_AND_DECISIONS.md
(§2.1 incl. the numerical example, §2.3, §4, §5), QTA_OPEN_DECISIONS.md (PD-Q1, PD-Q4,
PD-Q5), docs/phase4/QTA_Q3_PROMPT.md (the reviewer decisions R1–R4 above the fence),
docs/phase4/reports/QTA_Q2_REPORT.md (§9 and §10 review notes),
and the code you will extend: qta/{models,schemas,queries,service}.py, api/v1/qta.py,
authorization/policy.py (ScopeGrant.predicate, require_institution), authorization/writes.py,
auth/service.py (database_lock), directory/queries.py (user_query, page), db/audit.py
(BudgetRevisionRecorded), api/errors.py, core/config.py, and the Q2 tests as style examples.

## 1. Hard rules (any violation = stop and report, do not work around it)
- Never read, print or copy .env. Never edit apps/web/. No commits, pushes, deploys.
- Do not touch the developer's Docker stack (aq-uai-dev). Disposable PostgreSQL only.
- No new migration. Head stays 0008_qta_schema. Do not edit 0001–0008. If you believe the
  schema must change, STOP and explain why in the report.
- Do not change mdl/, directory/, authorization/ code or any MDL/directory/WP test.
- Do not weaken, skip, delete or xfail any existing test. The ONLY allowed existing-test
  edits are listed in section 3; explain each (file, line, before, after, why).
- Do not invent units, prices, conversions, consumption, usage numbers or institutional
  policy. All amounts are "đơn vị hạn mức" (PD-Q1). No field may be named or labelled
  token/credit/price.
- Only edit files in the allowlist (section 3). Anything else: stop and ask in the report.

## 2. Preflight evidence (before changing anything)
Create docs/phase4/reports/q3/ and save:
- git-status-before.txt: `git status --short`
- hashes-before.txt:
  `find apps tests scripts infra docs .github -type f -not -path '*/__pycache__/*' \
    -not -path '*/.ruff_cache/*' -not -path '*/node_modules/*' -print0 | sort -z | \
    xargs -0 sha256sum > docs/phase4/reports/q3/hashes-before.txt`
- baseline-gate.log: a full gate run before any change (command in section 6).
  Expected baseline: API 525 passed, 1 skipped; browser 16 passed. If different, stop.
  (One known timing flake: tests/browser/test_operations.py::
  test_backup_restores_history_and_runtime_writes may time out on API startup when the
  machine is loaded. If only that test fails, re-run the gate once and record both runs.
  Any other failure: stop.)

## 3. File allowlist
New:      apps/api/src/aq_uai_api/qta/entitlements.py   (computation, single source of truth)
          apps/api/src/aq_uai_api/qta/periods.py        (month parsing, window, clock)
          apps/api/tests/unit/test_q3_entitlements.py
          apps/api/tests/integration/test_q3_qta_lookup_budgets.py
          docs/phase4/reports/** (report and evidence)
Modified: apps/api/src/aq_uai_api/qta/{schemas,queries,service}.py, api/v1/qta.py
          apps/api/src/aq_uai_api/core/config.py  (add institution_timezone only)
          apps/api/src/aq_uai_api/api/errors.py   (append QTA_PERIOD_NOT_OPEN at the end
            of the QTA codes only)
          apps/api/tests/unit/test_q2_contracts.py:
            (a) add the Q3 routes to the pinned route inventory;
            (b) narrow the forbidden-word check per R4: request bodies and query/path
                parameters stay fully strict; response schemas may contain exactly the
                property names actual_consumption and consumption_status and nothing else
                matching the regex. Keep the regex itself unchanged.
          apps/api/tests/unit/test_q1_contracts.py (it pins the QTA error codes: add
            QTA_PERIOD_NOT_OPEN only), test_m3_contracts.py or other pinned-contract tests
            (only to add the new error code/routes to pinned lists, if they pin them)
          docs/phase4/QTA_IMPLEMENTATION_PLAN.md, QTA_REQUIREMENTS_TRACEABILITY.md,
          docs/PROJECT_CONTEXT.md, docs/acceptance-matrix.md, CLAUDE.md (status lines)
Not allowed in Q3: .env.example, infra/, scripts/, db/audit.py (BudgetRevisionRecorded and
QTA_MONTHLY_BUDGET_SET already exist; if they truly do not fit, STOP and report).

## 4. What to build
4.1 Settings & periods (qta/periods.py, core/config.py)
    - Settings.institution_timezone: str = "Asia/Ho_Chi_Minh" (env
      AQ_UAI_INSTITUTION_TIMEZONE, follow the existing env prefix), validated with
      zoneinfo.ZoneInfo at load time (invalid zone -> settings error).
    - utc_now() -> datetime: the ONLY clock QTA uses, so tests can monkeypatch it.
    - current_month(settings) -> date (first day, institution timezone);
      next_month(...); parse_month("YYYY-MM") -> date (first day).
      Strict regex ^\d{4}-(0[1-9]|1[0-2])$. Anything else (e.g. "2026-13", "2026-1",
      "HK1-2026", "semester", "exam", "2026-11-01") -> 422 QTA_INVALID_PERIOD.
    - require_open_month(month, settings): current or next month only, else
      422 QTA_PERIOD_NOT_OPEN (new code, message e.g. "Only the current or next month
      can be used here.").

4.2 Entitlement computation (qta/entitlements.py), follow architecture §2.1 exactly
    G(u) = enrolled groups (qta_quota_groups) with in_directory=true AND
           account_groups.active=true AND an active group_memberships row for u.
    q(g,m) = monthly_limit if the (g,m) quota row exists AND enabled AND model active,
             else 0.
    E_base(u,m) = SUM over G(u) of q(g,m)   (additive; NEVER max).
    User.state != 'ACTIVE' -> every E_base = 0 (show state transparently).
    - compute_user_entitlements(db, institution_id, user_id) -> per active model:
      base_entitlement, contributions [{group_id, code, name, kind, origin, enabled,
      monthly_limit, contributes (int)}]; plus memberships: every active membership of u in
      a SYSTEM or AI_SPECIALIST group with qualifies (bool) and excluded_reason in
      {NOT_ENROLLED, RETIRED, GROUP_INACTIVE, USER_NOT_ACTIVE} or null.
    - allocated_for_month(db, institution_id) -> int: SUM over ACTIVE users and active
      models of E_base, computed with ONE SQL aggregate (no per-user Python loop).
      Must equal the sum of compute_user_entitlements totals (tested, see section 5).
      Docstring must say Phase 5 CRT net grants will join through this function.
    - Both functions read live data (PD-Q5: mid-month changes take effect immediately).

4.3 Read API (GET; reuse page(), PageParams/SearchParams; Cache-Control no-store like Q2)
    GET /api/v1/qta/users            qta.read GLOBAL or UNIT. Scope with
        authority.scope_for(QTA_READ).predicate(User.institution_id, User.primary_unit_id)
        (same pattern as directory.queries.user_query). Paged, q search on username,
        display_name, institutional_code. Item: id, username, display_name,
        institutional_code, primary_unit_id, state. No group/quota data here.
    GET /api/v1/qta/users/{user_id}/entitlements?month=YYYY-MM   (month default = current)
        same scope rule; out of scope or other institution -> 404 (no existence leak).
        month must be open (current/next) per R1, else QTA_PERIOD_NOT_OPEN.
        Response: user summary (id, username, display_name, state), month "YYYY-MM",
        unit_label "đơn vị hạn mức", memberships[], models[] each with model_id,
        display_name, technical_id, provider_type, base_entitlement, contributions[],
        actual_consumption: null, remaining_quota: null,
        consumption_status: "NOT_INTEGRATED"; and base_entitlement_total.
        A user with no qualifying group: every base_entitlement 0 (FR-QTA-031 AC2).
    GET /api/v1/qta/budgets?month=YYYY-MM   GLOBAL qta.read only (UNIT viewer -> 403).
        month default = current; any well-formed month allowed for reading.
        Response: month, status "RECORDED" | "NOT_RECORDED", status_label
        ("chưa ghi nhận" when NOT_RECORDED), current (latest revision or null),
        revisions[] (newest first: revision, total_limit, decision_number, decision_date,
        recorded_by, recorded_at), allocation_status "LIVE" | "NOT_SNAPSHOTTED" (R1),
        allocated, remaining = max(0, total - allocated) or null,
        over_allocated = max(0, allocated - total) or null (warning, never an error).
        For an open month with no revision: allocated is live, remaining/over_allocated null.

4.4 Write API: PUT /api/v1/qta/budgets/{month}
    - GLOBAL qta.manage through the shared protected() path (session, Origin, CSRF,
      transaction-time re-authorization); changes_authority=False.
    - body (extra="forbid"): total_limit (int >= 1), decision_number (trimmed, 1..128),
      decision_date (date). Missing decision_number or decision_date -> 422 (FR-QTA-010 AC2,
      PD-Q4). No other fields (no cycle/semester/etc.).
    - month must be open (current or next), else QTA_PERIOD_NOT_OPEN; malformed ->
      QTA_INVALID_PERIOD.
    - take database_lock(db, QTA_BUDGET_NAMESPACE=52001, institution_key(tenant),
      shared=False) BEFORE reading max(revision) and allocated (architecture §4).
    - allocated = allocated_for_month(...). If total_limit < allocated ->
      409 QTA_BUDGET_BELOW_ALLOCATED with details {allocated, deficit = allocated -
      total_limit} (both already allowlisted). Equal is allowed.
    - INSERT a new qta_budget_revisions row (revision = max + 1, starting at 1); never
      UPDATE or DELETE (the DB has no such grant anyway). Audit
      QTA_MONTHLY_BUDGET_SET with BudgetRevisionRecorded (before_limit and
      before_decision_number from the previous revision or null) in the same transaction.
      Response 200 = the same shape as GET /qta/budgets for that month.
    - Every write is a new revision, even with the same numbers (each is a decision record).
    - Quota edits and directory growth are NEVER blocked by the budget (PD-Q1); do not
      add budget checks to Q2 write paths.

## 5. Tests (write them before or with the code; names are required)
tests/unit/test_q3_entitlements.py (no DB where possible):
  - test_parse_month_accepts_only_calendar_months (valid, and every invalid example in 4.1)
  - test_open_window_current_and_next_month_in_institution_timezone (frozen utc_now:
    2026-11-30T17:30Z is already 2026-12-01 in Asia/Ho_Chi_Minh, so current=December,
    next=January 2027; also year rollover December -> January)
  - test_settings_reject_invalid_timezone
  - test_q3_openapi_routes_and_month_only_inputs (no cycle/semester/period inputs; budget
    body rejects unknown fields; no PATCH/DELETE on budgets)
tests/integration/test_q3_qta_lookup_budgets.py (PostgreSQL, real routes, runtime login):
  - test_architecture_numerical_example: build EXACTLY the §2.1 example (G_GV SYSTEM via
    sync with Alice, Bob, Carol[DISABLED]; AI_LAB specialist with Alice; M1/M2 limits as
    written) and assert every row of the table: Alice M1 = 4000 (not 3000), Alice M2 =
    2000, Bob total 3000, Carol 0, allocated 9000, revision 1 = 10000 -> remaining 1000,
    7500 -> 409 {allocated 9000, deficit 1500}, deactivate AI_LAB -> allocated 6000,
    7500 now succeeds as revision 2 with remaining 1500, revision 1 still in history.
  - test_additive_not_max_1000_plus_3000 (FR-QTA-030 AC1, AC2: contributions list both
    groups and the sum)
  - test_no_group_user_has_zero_base (FR-QTA-031 AC2)
  - test_disabling_model_quota_removes_base_for_single_group_user (FR-QTA-021 AC2)
  - test_specialist_member_appears_in_additive_lookup (FR-QTA-022 AC2)
  - test_exclusions: retired SYSTEM group, inactive group, inactive membership, unenrolled
    group, inactive MDL model, disabled quota, limit 0, non-ACTIVE user -> contribute 0
    with the right excluded_reason
  - test_consumption_is_null_not_integrated (never 0, never a number)
  - test_allocated_equals_sum_of_user_entitlements (consistency check on a fixture with
    overlapping groups, a disabled user and a disabled quota)
  - test_lookup_scope: AI_QUOTA_VIEWER UNIT sees only own-unit users in /qta/users and gets
    404 for another unit's user entitlements; GLOBAL viewer sees all; FOUNDATION_ADMIN and
    AI_MODEL_ADMIN 403; anonymous 401; UNIT viewer 403 on /qta/budgets
  - test_budget_revisions_append_only (rev 1, rev 2, history preserved newest first, audit
    before/after, no UPDATE: rev 1 row bytes unchanged)
  - test_budget_requires_decision_number_and_date (each missing/blank -> 422, nothing
    written)
  - test_budget_month_window (past month PUT -> QTA_PERIOD_NOT_OPEN; month after next ->
    QTA_PERIOD_NOT_OPEN; malformed -> QTA_INVALID_PERIOD; current and next accepted;
    use the monkeypatched clock, never the real date)
  - test_unrecorded_month_shows_chua_ghi_nhan_while_quotas_apply
  - test_past_month_read_is_not_snapshotted (R1)
  - test_equal_to_allocated_is_allowed_and_below_is_409_with_details
  - test_over_allocation_is_a_warning_not_a_block (raise quotas / add members after a
    budget -> writes succeed, GET shows over_allocated > 0)
  - test_budget_rbac_and_csrf (viewer cannot PUT, missing CSRF refused, wrong Origin
    refused)
  - test_tenant_isolation (other institution users/budgets invisible; 404s)
  - test_budget_audit_failure_rolls_back (no revision row if the audit insert fails)
  - test_concurrent_budget_writes_serialize (two threads, same month: revisions 1 and 2,
    no duplicate revision number, no 500)
Mutation proof (required, record it in mutation-proof.log): for each rule, temporarily
break it, run the focused test, confirm it FAILS, restore, confirm it passes:
  (1) SUM replaced by MAX in the entitlement aggregate,
  (2) the total_limit < allocated guard removed,
  (3) the UNIT scope predicate removed from the user lookup,
  (4) the inactive-user exclusion removed from allocated_for_month.
Record the sha256 of each touched file before mutation and after restore (must match).

## 6. Verification commands
Focused:  pytest apps/api/tests/unit/test_q3_entitlements.py apps/api/tests/unit/test_q2_contracts.py
          pytest apps/api/tests/integration/test_q3_qta_lookup_budgets.py   (disposable PG)
          pytest apps/api/tests/integration/test_q2_qta_groups.py   (Q2 must stay green)
Full gate (save the whole output to docs/phase4/reports/q3/final-gate.log):
  AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv python> \
  AQ_NGINX=<nginx or wrapper> bash scripts/verify_phase2.sh
Never report a test you did not run. Report API and browser counts separately.
Browser suite must still be 16 passed (no UI in Q3).

## 7. Postflight evidence
Save in docs/phase4/reports/q3/:
- git-status-after.txt, hashes-after.txt (same commands as preflight; write
  hashes-after.txt to a temp path first, then move it in, so it does not hash itself),
- changed-files.txt: `diff hashes-before.txt hashes-after.txt` (every changed/added/
  removed file must appear in the report table, and nothing outside the allowlist),
- focused-tests.log, final-gate.log, mutation-proof.log.
No secret may appear in any saved file.
If the Project Owner commits during your run, note it in §9 and keep the hash evidence
authoritative (as in Q2).

## 8. The report: docs/phase4/reports/QTA_Q3_REPORT.md (exact sections)
1. Summary: what Q3 delivered in 5 lines; status "implemented, awaiting review".
2. Files: table of EVERY created/modified file (path, new/modified, why, FR/finding).
   Must match changed-files.txt exactly.
3. Computation: the SQL of allocated_for_month and of the per-user lookup, explained in
   plain words, and how the consistency test proves they agree.
4. API: every new route, permission/scope, status codes, error codes, audit action, and
   one example response body for entitlements and for budgets (synthetic test data only).
5. Tests: every new test name -> FR/AC/rule it proves; every edited existing test with
   file, line, before/after, why (only the section 3 edits are allowed).
6. Results: baseline vs final counts (API passed/skipped, browser passed), static checks,
   alembic check; paths to the logs.
7. Mutation proof: rule, how broken, failing test name + observed failure, restored, hashes.
8. Decisions and deviations: R1–R4 as applied, anything else you decided, and why
   (or "none").
9. Open questions / risks / anything not verified (e.g. hosted CI not run).
10. Implementer's review of the plan and this prompt (discussion, not decisions):
    your honest critique of QTA_IMPLEMENTATION_PLAN.md (Q3–Q6), the architecture, R1–R4
    and these instructions: what was unclear, wrong, risky or over-specified; better
    alternatives you see; and concrete suggestions for Q4 and later. For each point give
    reason, trade-off and a recommendation. These are proposals only: the Project Owner
    and the reviewer decide. Never apply a suggestion in Q3 that breaks sections 1–4;
    if you think a rule must change, follow it anyway and argue for the change here.
Also add a short "Q3 completion" section to QTA_IMPLEMENTATION_PLAN.md linking the report,
and update traceability for FR-QTA-010/011/021/022/030/031 (status: implemented in API,
UI in Q5). Formal acceptance stays unchanged.

## 9. Stop
After the report, stop. Q4 needs a separate instruction.
~~~
