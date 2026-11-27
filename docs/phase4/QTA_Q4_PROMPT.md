# Prompt for the implementing agent — QTA Stage Q4 (+ whole-module review)

**Use:** the Project Owner pastes everything inside the fence below to the implementing agent (this time: Gemini Carbon in Google Antigravity). After it finishes, the reviewer (Claude Code) reads `docs/phase4/reports/QTA_Q4_REPORT.md` and the evidence folder `docs/phase4/reports/q4/` and verifies them independently.

**Before pasting:** commit the reviewed Q3 work first, so Q4 starts from a clean, committed tree.

**Reviewer decisions baked into this prompt** (recommendations within PD-Q1..PD-Q6; not new PO decisions). The agent must list them in report §8 and may argue against them in §10:
- R5: `check_ai_access` is fail-closed and uses one ordered decision table (§4.3). A user whose base entitlement for the model is 0 is blocked with `NO_ENTITLEMENT`. FR-QTA-031 AC2 allows "0 or blocked by policy"; because consumption is not integrated, blocking is the safe reading.
- R6: A model is *usable* for QTA only if `mdl_models.active AND mdl_providers.active`. This applies everywhere QTA says "active model" (carry-over C1).
- R7: The monthly reset is an honest append-only ledger marker. No balances exist yet (consumption NOT_INTEGRATED), so zero rollover holds by construction, because entitlements are always derived from current configuration. The reset must not fabricate any per-user balance rows.
- R8: The scheduled CLI only ever records the *current* month (institution timezone). It never backfills missed past months, and it is idempotent.
- R9: Access-decision and exclusion reason codes are UPPER_SNAKE (`SUSPENDED_ALL_MODELS`, ...). Architecture §2.2 currently shows lowercase and must be updated.

~~~text
# AQ EduUAI — Phase 4 QTA, Stage Q4 (authorized by the Project Owner) + whole-module review.

You are a strong model and this is a single-shot assignment. Do three things, in this order:
  PART A  Review the whole QTA module (Q0–Q3) critically before coding (write it into the
          report §10 as you go; do not change code because of it unless section 4.0 says so).
  PART B  Implement carry-over corrections C1–C4 (section 4.0) and Stage Q4 (sections 4.1–4.6).
  PART C  Report everything (section 8), including your opinions, and stop.
The Project Owner and the reviewer (Claude Code) remain the decision makers. Your opinions
are proposals: follow every rule below even if you disagree, and argue for changes in §10.

Stage Q4 = individual kill-switch / restore, check_ai_access, monthly reset (API + CLI),
append-only events. FRs: FR-QTA-032 (AC1, AC2), FR-QTA-040 (AC1–AC3), FR-QTA-041 (AC1, AC2),
FR-QTA-050 (AC2, API part). Rules: RULE-QTA-03, RULE-QTA-04, INV-17, INV-18.
NOT in Q4: admin UI (Q5), backup/restore rehearsal + handoff (Q6), CRT (Phase 5).

## 0. Read first
AGENTS.md, CLAUDE.md, docs/PROJECT_CONTEXT.md, docs/frd/AQ-FRD-UAI-QTA-001.md (all),
docs/architecture/ADR-0004-qta.md, docs/phase4/QTA_IMPLEMENTATION_PLAN.md (all stages),
QTA_ARCHITECTURE_AND_DECISIONS.md (all), QTA_OPEN_DECISIONS.md (all, esp. PD-Q2, PD-Q3,
PD-Q6), QTA_REQUIREMENTS_TRACEABILITY.md, QTA_Q1_REVIEW.md, QTA_Q2_PROMPT.md,
QTA_Q3_PROMPT.md, docs/phase4/QTA_Q4_PROMPT.md (R5–R9 above the fence),
reports/QTA_Q2_REPORT.md (§9, §10) and reports/QTA_Q3_REPORT.md (§9, §10, §11 reviewer
response). Code: everything under apps/api/src/aq_uai_api/qta/, api/v1/qta.py,
authorization/{policy,writes}.py, auth/service.py (database_lock), db/audit.py
(_OPERATOR_ACTIONS, write_audit_event), db/provision.py (QTA_RUNTIME_PRIVILEGES),
db/mdl_rewrap.py (operator-CLI style), mdl/models.py and mdl/routing.py (read only),
migrations 0007/0008, and the Q2/Q3 tests.

## 1. Hard rules (any violation = stop and report, do not work around it)
- Never read, print or copy .env. Never edit apps/web/. No commits, pushes, deploys.
- Do not touch the developer's Docker stack (aq-uai-dev). Disposable PostgreSQL only.
- No new migration; head stays 0008_qta_schema; do not edit 0001–0008. The Q4 tables
  (qta_suspensions, qta_suspension_restorations, qta_monthly_resets, qta_events) already
  exist with INSERT-only grants. If you believe the schema must change, STOP and explain.
- Do not change mdl/, directory/, authorization/ code or any MDL/directory/WP test.
- Do not weaken, skip, delete or xfail any test. Only the existing-test edits listed in
  section 3 are allowed; explain each (file, line, before, after, why).
- Do not invent units, prices, conversions, consumption, balances or institutional policy.
  Amounts are "đơn vị hạn mức" (PD-Q1). actual_consumption/remaining_quota stay null.
- Only edit files in the allowlist (section 3). Anything else: stop and ask in the report.
- Never report a test you did not run.

## 2. Preflight evidence (before changing anything)
Create docs/phase4/reports/q4/ and save git-status-before.txt, hashes-before.txt
(`find apps tests scripts infra docs .github -type f -not -path '*/__pycache__/*'
-not -path '*/.ruff_cache/*' -not -path '*/node_modules/*' -print0 | sort -z |
xargs -0 sha256sum`), and baseline-gate.log (full gate, section 6).
Expected baseline: API 549 passed, 1 skipped; browser 16 passed. Known flake:
test_backup_restores_history_and_runtime_writes may time out on API startup under load;
if only that fails, re-run once and record both runs. Any other difference: stop.

## 3. File allowlist
New:      apps/api/src/aq_uai_api/qta/access.py      (check_ai_access + suspension state)
          apps/api/src/aq_uai_api/qta/reset.py       (shared reset core + CLI __main__)
          apps/api/tests/unit/test_q4_access_reset.py
          apps/api/tests/integration/test_q4_qta_killswitch_reset.py
          apps/api/tests/integration/test_q4_carryover.py   (C1–C3 tests)
          docs/phase4/reports/** (report and evidence)
Modified: apps/api/src/aq_uai_api/qta/{entitlements,schemas,queries,service}.py,
          api/v1/qta.py
          apps/api/src/aq_uai_api/db/audit.py  (C3 only: one optional field)
          tests/browser/conftest.py            (C4 only: wait_for_http deadline)
          apps/api/tests/unit/test_q2_contracts.py (add Q4 routes to the pinned inventory)
          docs/phase4/QTA_IMPLEMENTATION_PLAN.md, QTA_REQUIREMENTS_TRACEABILITY.md,
          QTA_ARCHITECTURE_AND_DECISIONS.md (§2.2 table + R5–R9 text, §2.5 reset text,
          §5 API table), docs/architecture/ADR-0004-qta.md (status line + Q4 bullets only),
          docs/PROJECT_CONTEXT.md, docs/acceptance-matrix.md, CLAUDE.md (status lines)
Not allowed: .env.example, infra/, scripts/, apps/admin/, migrations, mdl/, directory/,
authorization/, api/errors.py (all Q4 codes already exist: QTA_USER_ALREADY_SUSPENDED,
QTA_USER_NOT_SUSPENDED, QTA_RESET_ALREADY_EXECUTED, QTA_PERIOD_NOT_OPEN, ...).

## 4. What to build
4.0 Carry-over corrections (from the reviewer's Q2/Q3 review; do these first, with tests
    in test_q4_carryover.py)
  C1 (R6, real defect): QTA ignores mdl_providers.active. MDL can deactivate a provider
     while its models stay active=true, so today a deactivated provider's models are still
     listed by GET /qta/models, still accept quotas, and still count in allocated and the
     lookup. Define ONE usable-model predicate in qta/entitlements.py
     (MdlModel.active AND MdlProvider.active, joined on (institution_id, provider_id)) and
     use it in: queries.models, service.upsert_group_quotas (inactive provider ->
     409 QTA_MODEL_NOT_ELIGIBLE), compute_user_entitlements, allocated_for_month and
     check_ai_access. Group quota rows for such models stay stored (never deleted) and
     count again when the provider is re-activated (PD-Q5 immediate effect).
     Test: create a provider not used by MDL routing, model + quota, then deactivate the
     provider through the real MDL API -> allocated drops, the lookup omits the model,
     /qta/models omits it, quota upsert 409; re-activate -> everything returns.
  C2 (maintainability): compute_user_entitlements and allocated_for_month currently repeat
     the same 6-table join and WHERE clause. Extract one private base selectable
     (e.g. _qualifying_quota_rows(institution_id)) and build both aggregates from it, so
     the rule exists once. Behaviour must not change: the Q3 consistency test and all Q3
     tests stay green unchanged.
  C3 (audit fidelity): add before_warning_threshold_pct: int | None = None to
     db/audit.py GroupQuotaUpdated (optional, backward compatible) and fill it in
     service.upsert_group_quotas. Test: changing only the threshold produces an audit row
     with before/after threshold.
  C4 (test infrastructure flake): tests/browser/conftest.py wait_for_http polls 100×0.1 s.
     Replace the loop bound with a monotonic deadline of 30 s (same polling, same failure
     message). No assertion changes anywhere.

4.1 Suspension state (qta/access.py)
  - A suspension s of user u is ACTIVE at time t iff it has no restoration row AND
    (s.expires_at IS NULL OR s.expires_at > t). Otherwise it is RESTORED or EXPIRED.
    Expiry is lazy (evaluated on read; nothing is written when it expires).
  - At most one ACTIVE suspension per user (no DB constraint exists: enforce it under the
    QTA_SUSPENSION_NAMESPACE = 52002 advisory lock, architecture §4).
  - Use periods.utc_now() as the only clock (tests freeze it).
  - Provide set-based helpers so lists never do N+1 queries
    (e.g. active_suspensions_for(db, institution_id, user_ids) -> dict).

4.2 Kill-switch writes (qta/service.py; shared protected() path: session, exact Origin,
    CSRF, transaction-time re-authorization; audit + event in the SAME transaction)
  POST /api/v1/qta/users/{user_id}/suspensions      GLOBAL qta.manage
    body (extra="forbid"): scope ("ALL_MODELS" | "PAID_EXTERNAL_ONLY"), reason (trimmed,
    1..500), ordered_by (trimmed, 1..255), expires_at (optional, timezone-aware ISO
    datetime; naive -> 422; must be > utc_now() else 422; no upper cap per PD-Q3).
    - target user must belong to the caller's institution (else 404); any account state
      is accepted (quota status is independent of account state; say so in §8).
    - protected(context, changes_authority=False, user_id=user_id,
      permission=P.QTA_MANAGE) so the target account is locked in the standard order, then
      take the QTA_SUSPENSION_NAMESPACE lock, then check for an ACTIVE suspension ->
      409 QTA_USER_ALREADY_SUSPENDED.
    - suspended_by = authority.actor_id ALWAYS (never from the body; ordered_by is
      non-authoritative metadata, FR-QTA-040 / PD-Q3).
    - INSERT qta_suspensions; INSERT qta_events (event_type SUSPEND, period_month = current
      month in the institution timezone, user_id, actor_id, summary = a fixed template
      that contains the scope but NOT the free-text reason); audit QTA_USER_SUSPENDED
      (UserSuspended).
    - Never touch quotas, budgets or memberships (no "set to 0", FR-QTA-040).
    Response 201: the suspension object (id, user_id, scope, reason, ordered_by, expires_at,
    suspended_by, suspended_at, status "ACTIVE").
  POST /api/v1/qta/users/{user_id}/restore           GLOBAL qta.manage
    body (extra="forbid"): note (optional, trimmed 1..500).
    - same locking; no ACTIVE suspension (none, expired or already restored) ->
      409 QTA_USER_NOT_SUSPENDED.
    - INSERT qta_suspension_restorations (restored_by = session actor); INSERT qta_events
      RESTORE; audit QTA_USER_RESTORED (UserRestored). Adds no quota (FR-QTA-041).
    Response 200: the suspension object with status "RESTORED" and restoration fields.

4.3 check_ai_access(db, institution_id, user_id, model_id) -> AccessDecision
    (qta/access.py; pure read, no writes, no side effects, fail closed). Ordered table (R5):
      1 USER_NOT_FOUND        user missing or in another institution
      2 USER_NOT_ACTIVE       User.state != 'ACTIVE'
      3 MODEL_UNAVAILABLE     model missing / other institution / not usable (C1)
      4 SUSPENDED_ALL_MODELS  active suspension with scope ALL_MODELS
      5 SUSPENDED_PAID_EXTERNAL active PAID_EXTERNAL_ONLY and provider_type == 'EXTERNAL'
      6 NO_ENTITLEMENT        base entitlement for (user, model) == 0
      7 ALLOWED
    AccessDecision: allowed (bool), reason (code or null), suspension_id (or null).
    Docstring: a future AI gateway must call BOTH mdl.routing.effective_model_id (which
    model) and check_ai_access (may this user use it); consumption is not checked while
    consumption_status is NOT_INTEGRATED. Reuse the C2 base selectable for step 6.
    No HTTP route of its own in Q4 (it is exposed through the lookup, 4.4).

4.4 Read API additions (GET; same scope rules as Q3; no N+1)
  - GET /qta/users items gain quota_status "ACTIVE" | "SUSPENDED".
  - GET /qta/users/{user_id}/entitlements gains quota_status, suspension (the ACTIVE one
    or null), and per model access: {allowed, reason} from check_ai_access.
  - GET /qta/users/{user_id}/suspensions   (GLOBAL or exact-UNIT qta.read, paged, newest
    first): every suspension with computed status ACTIVE | EXPIRED | RESTORED and its
    restoration (restored_by, restored_at, note) if any.
  - GET /qta/events?month=YYYY-MM          (GLOBAL qta.read; any well-formed month,
    default current; optional event_type and user_id filters; paged newest first).
  - GET /qta/monthly-resets                (GLOBAL qta.read): history newest first plus
    current: {month, status "COMPLETED" | "PENDING", reset (row or null)}.
  - No PATCH/PUT/DELETE on suspensions, restorations, events or resets (FR-QTA-050).

4.5 Monthly reset (R7, R8; PD-Q6; FR-QTA-032)
  - Shared core in qta/reset.py: record_reset(db, institution_id, month, trigger_mode,
    actor_id | None, request_id) under QTA_RESET_NAMESPACE = 52003: if a row exists for
    (institution, month) -> already executed; else INSERT qta_monthly_resets, INSERT one
    qta_events MONTHLY_REFRESH (user_id NULL, actor_id = actor or NULL), and audit
    (QTA_MONTHLY_RESET_EXECUTED for manual with the actor; QTA_MONTHLY_RESET_SCHEDULED for
    the CLI with actor NULL — it is already in _OPERATOR_ACTIONS).
  - POST /api/v1/qta/monthly-resets   GLOBAL qta.manage, empty body only (no month field;
    the month is ALWAYS the current institution month, PD-Q6) -> 201 with the reset row;
    repeat in the same month -> 409 QTA_RESET_ALREADY_EXECUTED. trigger MANUAL_SIMULATION.
  - CLI: `python -m aq_uai_api.qta.reset` — for every institution, its current month; one
    transaction per institution; prints only counts (recorded=N already=M), exit 0 on
    success (including all-already), non-zero on error; never backfills past months; no
    secrets in output. Follow db/mdl_rewrap.py style and the shared write_transaction.
  - Reset never changes quotas, budgets, memberships or suspensions; active suspensions
    survive it. Zero rollover: after a December reset, December entitlements equal the
    configured values and nothing from November (budget, suspension history) is added.

4.6 Docs
  - Architecture §2.2: replace the lowercase reason table with the R5/R9 table; §2.5:
    reset semantics per R7/R8; §5: mark Q4 routes. ADR-0004 status line: Q4 implemented.
  - Plan: "Q4 completion" section linking the report. Traceability: FR-QTA-032/040/041/050
    (implemented in API; UI in Q5). Formal acceptance stays unchanged.

## 5. Tests (names required; write them before or with the code)
unit/test_q4_access_reset.py:
  - test_access_decision_table_order (each of the 7 outcomes; when several apply, the
    earlier one wins)
  - test_paid_external_only_matrix (INTERNAL allowed, EXTERNAL blocked; ALL_MODELS blocks
    both)
  - test_lazy_expiry_none_future_past (frozen clock)
  - test_q4_openapi_routes_and_no_mutation_of_history (exact Q4 routes; no PATCH/PUT/DELETE
    on suspensions/events/monthly-resets; monthly-resets body has no month field;
    suspension body rejects unknown fields and suspended_by)
  - test_reset_cli_output_has_no_secrets_and_counts_only
integration/test_q4_qta_killswitch_reset.py (PostgreSQL, real routes, runtime login):
  - test_suspend_without_expiry_and_with_future_expiry
  - test_suspend_validation (blank reason, blank ordered_by, past/now expires_at, naive
    datetime, unknown scope, extra field incl. suspended_by -> 422; nothing written)
  - test_operator_is_session_actor_even_if_ordered_by_names_someone_else
  - test_second_active_suspension_is_409_but_after_expiry_or_restore_allowed
  - test_concurrent_suspends_one_wins (two threads: one 201, one 409, no 500)
  - test_paid_external_only_blocks_external_allows_internal_end_to_end (via lookup access)
  - test_all_models_blocks_both
  - test_suspend_and_restore_do_not_change_entitlements_or_budgets (FR-QTA-040/041)
  - test_restore_returns_active_and_records_event (FR-QTA-041 AC1, AC2)
  - test_restore_without_active_suspension_is_409 (none, expired, already restored)
  - test_lazy_expiry_lifts_suspension_without_writes (row counts unchanged)
  - test_events_append_only_and_filtered (SUSPEND/RESTORE/MONTHLY_REFRESH; month filter;
    summary excludes the free-text reason)
  - test_manual_reset_current_month_only_and_409_on_repeat (FR-QTA-032 AC1)
  - test_reset_cli_idempotent_and_no_backfill (run twice -> recorded then already; a missed
    past month is NOT created; executed after the 1st at 00:00 still records the current
    month)
  - test_manual_then_scheduled_same_month_is_noop
  - test_zero_rollover_across_months (FR-QTA-032 AC2; frozen clock Nov -> Dec)
  - test_active_suspension_survives_reset
  - test_q4_rbac_and_csrf (viewer cannot write; UNIT viewer: suspensions of own-unit users
    only, 404 otherwise, 403 on events/resets; FOUNDATION_ADMIN/AI_MODEL_ADMIN 403;
    anonymous 401; missing CSRF / wrong Origin refused)
  - test_q4_tenant_isolation
  - test_q4_audit_failure_rolls_back (suspend, restore, manual reset: no suspension,
    restoration, event or reset row survives)
  - test_users_list_and_lookup_show_quota_status_without_n_plus_1 (bounded query count for
    a page of 20 users, e.g. with a SQLAlchemy before_cursor_execute counter)
integration/test_q4_carryover.py:
  - test_inactive_provider_models_are_not_usable_anywhere (C1)
  - test_qualifying_rule_single_source (C2: both aggregates built from the same selectable;
    the Q3 consistency test still passes)
  - test_quota_threshold_change_audits_before_and_after (C3)
Mutation proof (record in mutation-proof.log with sha256 before mutation and after restore):
  (1) PAID_EXTERNAL_ONLY also blocks INTERNAL, (2) lazy expiry ignored (expired treated as
  active), (3) duplicate-active-suspension check removed, (4) manual reset allows the next
  month, (5) provider.active removed from the usable-model predicate.

## 6. Verification commands
Focused: pytest the three new Q4 files + test_q2_contracts.py + test_q3_entitlements.py
         + test_q2_qta_groups.py + test_q3_qta_lookup_budgets.py (disposable PG)
CLI smoke: run `python -m aq_uai_api.qta.reset` twice against the disposable database
         and save both outputs to cli-smoke.log.
Full gate (save to docs/phase4/reports/q4/final-gate.log):
  AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv python> \
  AQ_NGINX=<nginx or wrapper> bash scripts/verify_phase2.sh
Report API and browser counts separately. Browser must stay 16 passed (no UI in Q4).

## 7. Postflight evidence (docs/phase4/reports/q4/)
git-status-after.txt, hashes-after.txt (write to a temp path, then move in),
changed-files.txt (`diff hashes-before.txt hashes-after.txt`; every entry explained in the
report; nothing outside the allowlist), focused-tests.log, cli-smoke.log, final-gate.log,
mutation-proof.log. No secret in any file. If the Project Owner commits during your run,
note it in §9 and keep the hash evidence authoritative.

## 8. The report: docs/phase4/reports/QTA_Q4_REPORT.md (exact sections)
1. Summary (5 lines; status "implemented, awaiting review").
2. Files: table of EVERY created/modified file (path, new/modified, why, FR/finding);
   must match changed-files.txt.
3. Carry-over corrections C1–C4: what changed, line-level explanation, tests.
4. Design: suspension state machine, check_ai_access table, lock order actually used,
   reset core + CLI flow; plain words for a beginner.
5. API: every new/changed route, permission/scope, status and error codes, audit action,
   event type; one example body each for suspension, entitlement-with-access and
   monthly-resets (synthetic data only).
6. Tests: every new test -> FR/AC/rule; every edited existing test with before/after/why.
7. Results: baseline vs final (API passed/skipped, browser passed), static checks,
   alembic check, CLI smoke; log paths. Mutation proof table with hashes.
8. Decisions and deviations: R5–R9 as applied, anything else you decided, and why.
9. Open questions / risks / not verified (hosted CI, live Compose, real scheduler).
10. Whole-module review (PART A) — your independent assessment of QTA Q0–Q4 end to end:
    a. Requirements coverage: for every FR-QTA-* and RULE-QTA-*, is it really met by the
       code and tests (not just claimed)? Name any gap.
    b. Architecture and decisions: PD-Q1..PD-Q6, R1–R9, ADR-0004 — what you would keep,
       change or reverse, with reasons and trade-offs.
    c. Code quality and risks across qta/: correctness, concurrency and lock order,
       tenant isolation, N+1, error and audit consistency, naming, dead code.
    d. Test quality: weak or missing tests, over-mocking, flaky patterns.
    e. Readiness for Q5 (Admin UI) and Q6 (handoff): the exact API contract the UI will
       rely on, gaps to close first, and a recommended Q5 scope.
    f. Answers to the reviewer's open questions:
       Q-a Should decision_date be validated (e.g. not after today, not before some date)?
       Q-b Should a UNIT-scoped viewer see the free-text suspension reason?
       Q-c Scheduling the reset CLI: cron/systemd on the host, a Compose service, or only
           documented in the Q6 handoff? Recommend one.
       Q-d Should GET /qta/users include PENDING/DISABLED accounts (today: yes)?
       Q-e The forbidden-word contract test (Q3 report §10.1): keep, narrow to names only,
           or replace? Propose the exact rule.
       Q-f Next-month budgets are checked against today's live allocation. Is that the
           right guard, or should next month be unchecked until it starts?
    g. Anything we should modify now (prioritized list: must / should / could), each with
       file(s), effort estimate, and risk.
11. (Leave empty: the reviewer writes "Reviewer response" here.)
Also add a short "Q4 completion" section to QTA_IMPLEMENTATION_PLAN.md linking the report.

## 9. Stop
After the report, stop. Q5 needs a separate instruction.
~~~
