# Prompt for the implementing agent — QTA Stage Q2

**Use:** the Project Owner pastes everything inside the fence below to the implementing agent (Google Antigravity). After it finishes, the reviewer (Claude Code) reads `docs/phase4/reports/QTA_Q2_REPORT.md` and the evidence folder `docs/phase4/reports/q2/` and verifies them independently.

~~~text
# AQ EduUAI — Phase 4 QTA, Stage Q2 (authorized by the Project Owner). Do Q2 only.

Stage Q2 = group registry + sync + AI-specialist groups + group × model quota configuration.
FRs: FR-QTA-001 (API part), FR-QTA-020 (AC1, AC2), FR-QTA-021 (AC1, configuration only),
FR-QTA-022 (AC1). Rules: RULE-QTA-05.
NOT in Q2: entitlement/allocation, personal lookup, school budgets, kill-switch, reset,
admin UI (Q3–Q5).

## 0. Read first (in this order)
AGENTS.md, CLAUDE.md, docs/PROJECT_CONTEXT.md, docs/frd/AQ-FRD-UAI-QTA-001.md,
docs/phase4/QTA_IMPLEMENTATION_PLAN.md (section Q2), QTA_ARCHITECTURE_AND_DECISIONS.md
(§1, §2.5, §3–§5), QTA_OPEN_DECISIONS.md (PD-Q1..PD-Q6, QD4, QD5, QD7),
QTA_Q1_REVIEW.md (section 6, "Points for the Q2 implementer"),
and the code you will reuse: authorization/policy.py, authorization/writes.py,
directory/service.py, directory/queries.py, api/v1/directory.py, db/audit.py,
api/errors.py, qta/models.py, mdl/models.py (read-only), api/v1/mdl.py (as a style example).

## 1. Hard rules (any violation = stop and report, do not work around it)
- Never read, print or copy .env. Never edit apps/web/. No commits, pushes, deploys.
- Do not touch the developer's Docker stack (aq-uai-dev). Disposable PostgreSQL only.
- No new migration. Head stays 0008_qta_schema. Do not edit 0007/0008 (they are final
  after Q1-R). If you believe the schema must change, STOP and explain why in the report.
- Do not change mdl/ code or any MDL test.
- Do not weaken, skip, delete or xfail any existing test. If an existing test must change,
  explain each change in the report (file, line, before, after, why).
- Do not invent units, prices, conversions, consumption or institutional policy.
  Quantities are "đơn vị hạn mức" (PD-Q1).
- Only edit files in the allowlist (section 3). Anything else: stop and ask in the report.

## 2. Preflight evidence (before changing anything)
Create docs/phase4/reports/q2/ and save:
- git-status-before.txt: `git status --short`
- hashes-before.txt: sha256 of every file under apps, tests, scripts, infra, docs
  (exclude __pycache__, .ruff_cache, node_modules):
  `find apps tests scripts infra docs -type f -not -path '*/__pycache__/*' \
    -not -path '*/.ruff_cache/*' -not -path '*/node_modules/*' -print0 | sort -z | \
    xargs -0 sha256sum > docs/phase4/reports/q2/hashes-before.txt`
- baseline-gate.log: a full gate run before any change (command in section 6).
  Expected baseline: API 495 passed, 1 skipped; browser 16 passed. If different, stop.

## 3. File allowlist
New:      apps/api/src/aq_uai_api/qta/{schemas.py,queries.py,service.py}
          apps/api/src/aq_uai_api/api/v1/qta.py
          apps/api/tests/unit/test_q2_contracts.py
          apps/api/tests/integration/test_q2_qta_groups.py
          docs/phase4/reports/** (report and evidence)
Modified: apps/api/src/aq_uai_api/main.py (register the router only)
          apps/api/src/aq_uai_api/authorization/policy.py (require_group_management only)
          apps/api/src/aq_uai_api/directory/service.py (only the refactor in 4.3)
          apps/api/src/aq_uai_api/db/audit.py (only if a new typed payload is needed)
          apps/api/src/aq_uai_api/api/errors.py (only if a new error code is needed;
            append at the end)
          apps/api/tests/unit/test_m3_contracts.py or other pinned-contract tests
            (only to add new routes/codes to pinned lists)
          docs/phase4/QTA_IMPLEMENTATION_PLAN.md, QTA_REQUIREMENTS_TRACEABILITY.md,
          docs/PROJECT_CONTEXT.md, docs/acceptance-matrix.md, CLAUDE.md (status lines)
Not needed in Q2: core/config.py (the timezone setting belongs to Q3; leave it).

## 4. What to build
4.1 Permission boundary (F4, QD5). In authorization/policy.py, require_group_management:
    kind AI_SPECIALIST accepts qta.manage OR directory.manage. SYSTEM and AUTHORIZATION
    are unchanged. Nothing else in policy.py changes.

4.2 Read API (GET needs qta.read GLOBAL; return 401/403 like MDL):
    GET /api/v1/qta/models          active MDL models of the institution, with
                                    provider name and provider_type (read-only SQL).
    GET /api/v1/qta/groups          enrolled groups only (qta_quota_groups), paged,
                                    filters kind/origin/active; each item: group id, code,
                                    name, kind, origin, account_groups.active, in_directory,
                                    last_synced_at, live active-member count, configured
                                    per-model quotas. EMPTY before the first sync.
    GET /api/v1/qta/groups/{id}     detail (404 if not enrolled or other institution).
    GET /api/v1/qta/groups/{id}/members   live members from group_memberships (paged).
    GET /api/v1/qta/groups/sync-runs      append-only history, newest first.

4.3 Write API (qta.manage, shared protected() path: session, Origin, CSRF,
    transaction-time re-authorization; audit in the same transaction):
    POST /api/v1/qta/groups/sync
      - enrol active SYSTEM groups not yet enrolled (origin SYNC, in_directory true);
      - enrol active AI_SPECIALIST groups not yet enrolled (origin SPECIALIST)
        (created through the Phase 2 directory);
      - enrolled SYSTEM groups now inactive -> in_directory false; back active -> true;
      - never modify existing SPECIALIST rows or any quota row; ignore AUTHORIZATION;
      - one qta_group_sync_runs row + qta.groups_synced audit with exact counts
        (groups_added = all newly enrolled, groups_retired = set to false this run);
      - serialize with an institution advisory lock (new namespace constant in qta).
    POST   /api/v1/qta/groups                      create an AI_SPECIALIST group
    PATCH  /api/v1/qta/groups/{id}                 rename (AI_SPECIALIST only)
    POST   /api/v1/qta/groups/{id}/activate|deactivate   (AI_SPECIALIST only)
    PUT    /api/v1/qta/groups/{id}/members/{user_id}     add/reactivate (AI_SPECIALIST)
    DELETE /api/v1/qta/groups/{id}/members/{user_id}     mark inactive (AI_SPECIALIST)
      REUSE RULE: directory/service.py functions (create_group, update_group,
      set_group_active, set_membership) each open their own protected() transaction.
      Do NOT copy their logic into qta/. Instead, refactor each one minimally into
      (a) an inner function that takes (db, authority, context, ...) and does the work
      and audit, and (b) the existing public function that opens protected() and calls
      the inner one. Directory routes must behave exactly as before (WP5 tests unchanged
      and green). QTA calls the inner functions inside its own protected() transaction
      and inserts the qta_quota_groups row (origin SPECIALIST) in that same transaction.
      SYSTEM/AUTHORIZATION group or a non-enrolled group -> 422 QTA_GROUP_NOT_ELIGIBLE
      (or 403 where the permission is missing); never let qta.manage touch them.
    PUT /api/v1/qta/groups/{id}/quotas
      body: list of {model_id, enabled, monthly_limit >= 0, warning_threshold_pct 1..100
      or null}; upsert the listed models only, never delete rows (no DELETE grant);
      one qta.group_quota_updated audit per row that actually changed (before/after);
      a no-op writes nothing. Model must be an ACTIVE MDL model of the same institution
      (else 409 QTA_MODEL_NOT_ELIGIBLE). Group must be enrolled, in_directory true and
      account_groups.active true (else 422 QTA_GROUP_NOT_ELIGIBLE). Duplicate model in one
      body -> 422. Works for SYSTEM and AI_SPECIALIST groups.
    All inputs: Pydantic extra="forbid". No field named period, semester, cycle, price,
    token, credit. Responses never include another institution's data.

## 5. Tests (write them before or with the code; names are required)
tests/unit/test_q2_contracts.py:
  - require_group_management matrix: {SYSTEM, AUTHORIZATION, AI_SPECIALIST} ×
    {directory.manage, qta.manage, authorization.manage, none}.
  - OpenAPI: exact set of /api/v1/qta routes and methods; no PATCH/PUT/DELETE on
    sync-runs; no forbidden field names (period/semester/cycle/price/token/credit/
    consumption) in any QTA schema; inputs reject unknown fields.
  - mdl/ still imports nothing from qta/ (import-closure check).
apps/api/tests/integration/test_q2_qta_groups.py (PostgreSQL, real routes, runtime login):
  - test_rbac_matrix: every Q2 route × {anonymous 401, FOUNDATION_ADMIN 403,
    AI_MODEL_ADMIN 403, AI_QUOTA_VIEWER (GLOBAL) reads 200 / writes 403,
    AI_QUOTA_VIEWER (UNIT) 403 on group routes, AI_QUOTA_ADMIN allowed};
    writes without CSRF refused.
  - test_group_list_empty_before_first_sync (FR-QTA-001 AC2).
  - test_sync_enrols_system_and_directory_specialist_groups (FR-QTA-020 AC1; counts).
  - test_sync_retires_and_restores_system_groups_without_deleting_quotas.
  - test_sync_preserves_specialist_groups_members_and_quotas (FR-QTA-020 AC2, RULE-QTA-05).
  - test_sync_ignores_authorization_groups.
  - test_specialist_group_lifecycle_uses_directory_audit_actions (FR-QTA-022 AC1:
    create + at least one member; audit actions group.created, membership.state_changed;
    qta_quota_groups row with origin SPECIALIST in the same transaction).
  - test_quota_admin_cannot_touch_system_or_authorization_groups.
  - test_directory_behaviour_unchanged_for_specialist_groups (FOUNDATION_ADMIN via
    /api/v1/groups still works exactly as before).
  - test_two_models_two_limits_on_one_group (FR-QTA-021 AC1).
  - test_quota_rules: inactive model 409, other-institution model 409/404, unenrolled
    or retired or inactive group 422, negative limit / pct 0 or 101 / duplicate model 422,
    no-op writes nothing, changed rows audited with before/after.
  - test_tenant_isolation: another institution's groups/models are 404 everywhere.
  - test_audit_failure_rolls_back (sync, specialist create, quota upsert).
  - test_concurrent_syncs_serialize (two threads: one run each, no duplicate enrolment,
    no 500).
Mutation proof (required, record it): for each of these rules, temporarily break it,
run the focused test, confirm it FAILS, restore the code, confirm it passes again:
  (1) sync skipping SPECIALIST protection, (2) quota model-eligibility check,
  (3) qta.manage acceptance limited to AI_SPECIALIST.
After restoring, hashes of the touched files must equal your final version (section 7).

## 6. Verification commands
Focused:  pytest apps/api/tests/unit/test_q2_contracts.py
          pytest apps/api/tests/integration/test_q2_qta_groups.py   (disposable PG)
Full gate (save the whole output to docs/phase4/reports/q2/final-gate.log):
  AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv python> \
  AQ_NGINX=<nginx or wrapper> bash scripts/verify_phase2.sh
Never report a test you did not run. Report API and browser counts separately.
The browser suite must still be 16 passed (no UI in Q2).

## 7. Postflight evidence
Save in docs/phase4/reports/q2/:
- git-status-after.txt, hashes-after.txt (same commands as preflight),
- changed-files.txt: `diff hashes-before.txt hashes-after.txt` (every changed/added/
  removed file must appear in the report table, and nothing outside the allowlist),
- focused-tests.log, final-gate.log, mutation-proof.log.
No secret may appear in any saved file.

## 8. The report: docs/phase4/reports/QTA_Q2_REPORT.md (exact sections)
1. Summary: what Q2 delivered in 5 lines; status "implemented, awaiting review".
2. Files: table of EVERY created/modified file (path, new/modified, why, FR/finding).
   Must match changed-files.txt exactly.
3. Shared-code changes: policy.py and directory/service.py diffs explained line by line;
   proof that directory behaviour is unchanged.
4. API: every route, permission, status codes, audit action.
5. Tests: every new test name -> FR/AC it proves; every edited existing test with
   before/after/why.
6. Results: baseline vs final counts (API passed/skipped, browser passed), static checks,
   alembic check; paths to the logs.
7. Mutation proof: rule, how broken, failing test name, restored.
8. Deviations from the plan or this prompt, and why (or "none").
9. Open questions / risks / anything not verified.
Also add a short "Q2 completion" section to QTA_IMPLEMENTATION_PLAN.md linking the report,
and update traceability for FR-QTA-001/020/021/022 (status: implemented in API, UI in Q5).

## 9. Stop
After the report, stop. Q3 needs a separate instruction.
~~~
