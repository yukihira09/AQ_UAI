# Prompt for the implementing agent — QTA Stage Q6 (verification, isolation proof, handoff)

**Use:** the Project Owner pastes everything inside the fence below to the implementing agent (Gemini Neon in Google Antigravity). Afterwards, the reviewer (Claude Code) reads `docs/phase4/reports/QTA_Q6_REPORT.md` and `docs/phase4/reports/q6/`, and verifies them independently.

**Before pasting:** commit the reviewed Q5 work (including the reviewer fixes), so that Q6 starts from a clean, committed tree. Expected baseline: API 581 passed, 1 skipped; browser 20 passed.

**Project Owner decisions needed — reviewer defaults applied unless you change them before pasting:**
- **Q-g, actor names in history tables.** Default: **no API change in Phase 4.** Actors stay UUIDs (`<code>`, "Bạn" for yourself), consistent with MDL. This is documented as a known limitation in the handoff; adding names later is one server-side read join for QTA and MDL together. *To change it:* say so, and the reviewer will scope it as a separate small step.
- **Q-h, sidebar regrouping to the FRD menu tree.** Default: **no regrouping.** It is cosmetic and touches shared navigation and its tests. It is documented as a known deviation from the FRD menu path.

**Reviewer decisions baked in (R17–R20).** These are recommendations, not PO decisions. The agent lists them in §8 and may argue in §10:
- R17: FR-MDL-020 AC3 ("the tester's quota balance is unchanged after a test") is proven with a populated QTA. The MDL connection-test user is a member of a quota group with a non-zero entitlement. Their lookup and the school budget are byte-identical before and after. A statement-level write log proves that no `qta_*` table is written. Consumption is still NOT_INTEGRATED, so "balance" means base entitlement; the report says so plainly.
- R18: The populated upgrade (`0006 → 0008`) and the backup/restore rehearsals are **automated tests in the gate**, not one-off manual runs. The agent does **not** run Docker. Disposable Compose rehearsals are the reviewer's job, if wanted.
- R19: The `FOR SHARE` lock on `AccountGroup` (Q4 review 10.c.3) is **analysis only** in Q6. The agent maps the real lock order and recommends; it does not change `service.py`.
- R20: Q6 UI changes are limited to three wording fixes from the Q5 review (section 4.4). No new features.

~~~text
# AQ EduUAI — Phase 4 QTA, Stage Q6: verification, cross-module isolation, handoff
# (authorized by the Project Owner). This is the LAST QTA stage.

Stage Q6 = (A) prove FR-MDL-020 AC3 end to end with a populated QTA, (B) rehearse the
populated 0006 -> 0008 upgrade and a QTA backup/restore as automated tests, (C) three
small UI wording fixes, (D) write the Phase 4 handoff and close the documentation.
NOT in Q6: new features, API or schema changes, CRT (Phase 5), Docker, deploys,
commits. apps/web/ and mdl.mjs stay untouched.

The Project Owner and the reviewer (Claude Code) decide. Follow every rule even if you
disagree; argue in report §10.

IMPORTANT ABOUT THE REPORT (the Q5 report missed required sections): use EXACTLY the
section numbers and titles in section 8, answer every question with its exact ID and
wording, and if you cannot do something, write "NOT DONE: <reason>" in that place.

## 0. Read first
AGENTS.md, CLAUDE.md, docs/PROJECT_CONTEXT.md, docs/frd/AQ-FRD-UAI-QTA-001.md (all),
docs/frd/AQ-FRD-UAI-MDL-001.md (FR-MDL-020), docs/phase4/QTA_IMPLEMENTATION_PLAN.md
(Q6 section), QTA_ARCHITECTURE_AND_DECISIONS.md, QTA_OPEN_DECISIONS.md,
QTA_REQUIREMENTS_TRACEABILITY.md, docs/phase4/QTA_Q6_PROMPT.md (Q-g, Q-h, R17–R20 above
the fence), reports/QTA_Q4_REPORT.md (§10, §11) and reports/QTA_Q5_REPORT.md (§11).
Templates to copy the style from: docs/phase3/mdl-handoff.md (handoff),
MDL_IMPLEMENTATION_PLAN.md "M7 verification" table.
Tests to reuse (import helpers and fixtures; do not copy them):
  apps/api/tests/integration/test_m6_quota_isolation.py (install_write_log, written)
  apps/api/tests/integration/test_m4_connection_tests.py (m4, local_provider, add_model,
    run_test — a local fake provider, nothing leaves the machine)
  apps/api/tests/integration/test_wp2_database.py (alembic(), migrate(), the populated
    upgrade pattern in test_provisioning_is_repeatable_and_preserves_data)
  apps/api/tests/integration/test_q2..q5 files (qta3/qta4 fixtures, qta_get, qta_send)
  tests/browser/test_mdl_operations.py + test_operations.py (database_factory,
    pg_dump/pg_restore pattern, snapshot(), new_stack)
Code (read only): apps/api/src/aq_uai_api/qta/*, db/provision.py
(QTA_RUNTIME_PRIVILEGES), migrations 0007/0008, mdl/ connection-test code.

## 1. Hard rules (any violation = stop and report; do not work around it)
- Never read, print or copy .env. Never edit apps/web/ or mdl.mjs. No commits, pushes,
  deploys. Do NOT run Docker or touch the developer's aq-uai-dev stack in any way.
- No change under apps/api/src/ or migrations/ (except temporary mutation proofs that
  you restore byte-identically). No new dependency.
- Never make a real provider request. Use the existing local fake provider only.
- Do not weaken, skip, delete or xfail any test. Existing-test edits are allowed ONLY in
  tests/browser/test_qta.py and only for the section 4.4 wording changes (before/after/
  why in the report).
- Do not invent prices, conversions, consumption, balances or institutional policy.
  Do not mark any FR as formally accepted.
- Only edit files in the allowlist (section 3). Anything else: stop and ask.
- Never report a test you did not run.

## 2. Preflight evidence (before changing anything)
Create docs/phase4/reports/q6/ and save git-status-before.txt, hashes-before.txt
(`find apps tests scripts infra docs .github -type f -not -path '*/__pycache__/*'
-not -path '*/.ruff_cache/*' -not -path '*/node_modules/*' -print0 | sort -z |
xargs -0 sha256sum`; run from the repository root), and baseline-gate.log (full gate).
Expected baseline: API 581 passed, 1 skipped; browser 20 passed. Any difference: stop.

## 3. File allowlist
New:      apps/api/tests/integration/test_q6_mdl_qta_isolation.py   (4.1)
          apps/api/tests/integration/test_q6_qta_upgrade.py         (4.2)
          tests/browser/test_qta_operations.py                      (4.3)
          docs/phase4/qta-handoff.md                                (4.5)
          docs/phase4/reports/** (report and evidence)
Modified: apps/admin/assets/qta.mjs            (4.4 wording only)
          tests/browser/test_qta.py            (4.4 wording assertions + timezone_id)
          docs/phase4/QTA_IMPLEMENTATION_PLAN.md, QTA_REQUIREMENTS_TRACEABILITY.md,
          QTA_OPEN_DECISIONS.md (record Q-g/Q-h outcome), docs/architecture/ADR-0004-qta.md
          (status line), docs/phase3/MDL_REQUIREMENTS_TRACEABILITY.md (FR-MDL-020 AC3
          row only), docs/PROJECT_CONTEXT.md, docs/acceptance-matrix.md, CLAUDE.md
Not allowed: everything else (apps/api/src/, migrations, infra/, scripts/,
tests/browser/conftest.py, apps/admin/assets/{app,pages,api,ui,mdl}.mjs, admin.css).

## 4. What to build

4.1 test_q6_mdl_qta_isolation.py — FR-MDL-020 AC3 with a populated QTA (R17)
  Setup: an MDL admin user who is ALSO a member of a synced SYSTEM group and of an
  AI_SPECIALIST group, both with enabled quotas on the model under test, so the
  tester's base entitlement is non-zero (e.g. 1.000 + 3.000 = 4.000). Also record a
  budget revision, one suspension of a different user, and one monthly reset, so every
  qta_* table has at least one row (assert that).
  Then:
  a. Snapshot BEFORE: the tester's GET /qta/users/{id}/entitlements, GET /qta/budgets,
     GET /qta/events (current month), and a row-level dump (ordered, all columns) of
     every qta_* table.
  b. install_write_log; run a successful connection test on the model (local fake
     provider) AND a failing one (e.g. provider returns an error); change routing
     primary/fallback once.
  c. AFTER: the same four snapshots must be EXACTLY equal; the written tables must be a
     subset of MDL tables + audit_events + session tables (reuse the M6 allowed set),
     and must contain no qta_* table.
  d. Positive control (proves the log can see QTA writes): with the log still
     installed, perform one QTA write (e.g. suspend someone) and assert a qta_* table
     now appears in written(). Without this the test could pass vacuously.
  e. Reverse direction: clear the log, run a QTA write burst (budget revision, quota
     upsert, suspend, restore, manual reset) and assert NO mdl_* table was written.

4.2 test_q6_qta_upgrade.py — populated 0006 -> 0008 upgrade (R18)
  Using the test_wp2_database pattern: upgrade a fresh database to 0006 only; insert
  realistic pre-QTA data through SQL (institution, units, users in each state, SYSTEM
  and AI_SPECIALIST groups with memberships, an MDL provider + model, an MDL routing
  row, audit rows); provision; upgrade to head; then assert:
  - every pre-existing row is preserved (compare before/after row dumps of the
    pre-QTA tables you populated);
  - alembic check reports no pending operations;
  - all 8 qta_* tables exist and are EMPTY (FR-QTA-001 AC2: empty before sync);
  - QTA permissions/roles from 0007 exist and no user received a QTA role implicitly;
  - the runtime role has exactly QTA_RUNTIME_PRIVILEGES (no DELETE on any qta table,
    INSERT-only on the history tables);
  - through the API after upgrade: sync, a group quota, and a lookup work, and
    allocated equals the expected sum.
  Also run the upgrade a second time (idempotent: no error, no data change).

4.3 tests/browser/test_qta_operations.py — QTA backup / restore (R18)
  Follow test_mdl_operations.py: populate QTA through the API (sync, quotas, budget
  with two revisions, a suspension + restore, a manual reset, events), pg_dump
  (custom format, file mode 600, under tmp_path), pg_restore into a NEW database with
  --single-transaction --exit-on-error, provision, alembic check, then:
  - every qta_* table is row-for-row identical to the source;
  - the restored stack serves #qta: budget revisions, the additive lookup, the
    suspension history and the reset COMPLETED state render;
  - runtime writes still work after restore (a new suspension succeeds) and append-only
    is still enforced (DELETE on qta_events as the runtime role is denied);
  - repeating the manual reset in the restored database still returns 409
    QTA_RESET_ALREADY_EXECUTED (the uniqueness survived restore).
  Delete the dump file at the end of the test (synthetic data only).

4.4 UI wording fixes from the Q5 review (R20) — qta.mjs + test_qta.py only
  - accessReasonLabels.NO_ENTITLEMENT: "Không có hạn mức" (drop the raw code).
  - quotaStatusLabels: ACTIVE -> "Được dùng AI", SUSPENDED -> "ĐÃ CẮT" (FRD wording), so
    the quota column no longer reads the same as the account-state column.
  - In test_qta.py: open every role-holder browser context with
    timezone_id="Asia/Ho_Chi_Minh" (sign_in_new_browser), and update only the
    assertions that check these exact labels. Add one assertion that the user list
    shows "ĐÃ CẮT" for the suspended user. Change nothing else in the test.

4.5 docs/phase4/qta-handoff.md (copy the structure of docs/phase3/mdl-handoff.md)
  1. What is delivered (screen, API, CLI) — links to the reports Q1–Q6.
  2. How code reaches the running stack (link to mdl-handoff §2, do not repeat it).
  3. Updating the developer's aq-uai-dev stack from 0006 to 0008: backup first
     (pg_dump command, mode 600), then `bash scripts/dev-up.sh`, then how to verify
     (alembic version, #qta visible for a QTA role). State that this was rehearsed only
     by the automated test in 4.2, not on the real stack, and that the agent did not
     run it. Do not run it.
  4. Granting QTA roles (AI_QUOTA_ADMIN / AI_QUOTA_VIEWER, GLOBAL vs UNIT) via #roles.
  5. Scheduling the monthly reset (Q4 Q-c decision): a host systemd timer with an
     explicit time zone, e.g.
       OnCalendar=*-*-01 00:05:00 Asia/Ho_Chi_Minh, Persistent=true, running
       docker compose --env-file .env -f infra/compose.yaml exec -T api
         python -m aq_uai_api.qta.reset
     plus a crontab alternative. Warn that CRON_TZ is not honoured by every cron
     (Debian/Ubuntu's default cron may ignore it), so with crontab check the host time
     zone (`timedatectl`) and pick a time that is already the 1st in Asia/Ho_Chi_Minh,
     e.g. 00:05 UTC on the 1st = 07:05 local. Explain: it records only
     the current month, never backfills, is safe to repeat (prints recorded=/already=),
     and zero rollover holds even if it never runs. Mark it "documented, not executed".
  6. Manual acceptance checklist: one row per FRD acceptance line (all "- [ ]" lines of
     QTA-001 plus FR-MDL-020 AC3) with the steps a person performs in #qta and the
     expected result, and the automated test that already covers it.
  7. Known limitations and open items: consumption NOT_INTEGRATED (no real balances);
     actors shown as UUIDs (Q-g default); flat sidebar (Q-h default); past months show
     NOT_SNAPSHOTTED; quota matrix shows the first 100 models; PENDING-account
     suspension policy (QD11 NEEDS-INSTITUTION); decision_date not range-checked (Q-a,
     NEEDS-INSTITUTION); UNIT viewers see the suspension reason (Q-b, PROV).
  8. Notes for Phase 5 CRT: any write checked against the school budget (FR-CRT-013)
     must take QTA_BUDGET_NAMESPACE (52001) in the same transaction; CRT grants must
     join allocated_for_month; the lookup's consumption fields are where integration
     lands.
  9. Evidence: a verification table in the style of "M7 verification" (baseline, focused,
     full gate, migrations, backup/restore, what was NOT verified).

4.6 Close the docs: traceability (Q6 status per FR; formal acceptance stays 0),
  MDL traceability FR-MDL-020 AC3 row (now proven end to end, technically), plan
  "Q6 completion" and a short "Phase 4 technical closure" paragraph, ADR-0004 status
  line, QTA_OPEN_DECISIONS (record Q-g and Q-h outcomes as defaults applied, with
  provenance "reviewer default, PO may override"), PROJECT_CONTEXT, acceptance-matrix,
  CLAUDE.md.

## 5. Required tests and proofs
- 4.1: one or more tests covering a–e. 4.2: one test (plus the idempotent re-run).
  4.3: one browser test. 4.4: updated assertions.
- Mutation proofs (break, run, see it fail, restore byte-identically, sha256 before/after
  in mutation-proof.log):
  1. In db/provision.py, temporarily add DELETE to qta_events in QTA_RUNTIME_PRIVILEGES
     -> the 4.2 privilege assertion (and/or 4.3 append-only check) fails.
  2. In qta.mjs, revert SUSPENDED back to "Đang tạm ngưng" -> the new "ĐÃ CẮT" assertion
     fails.
  3. In test_q6_mdl_qta_isolation.py itself, temporarily remove the positive-control
     QTA write in step d -> that step must fail. This proves the control is real.

## 6. Verification commands
Static: python scripts/verify_frontend_assets.py; node --check apps/admin/assets/qta.mjs;
        ruff on the new and changed Python tests (both configs, as the gate does).
Focused: pytest the two new integration files; pytest tests/browser/test_qta.py
         tests/browser/test_qta_operations.py.
Full gate (save to docs/phase4/reports/q6/final-gate.log):
  AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv python> \
  AQ_NGINX=<nginx or wrapper> bash scripts/verify_phase2.sh
Expected: API 581 + your new tests passed, 1 skipped; browser 20 + 1 passed.
If an old browser test hits a startup-timing flake, re-run once and record both runs.

## 7. Postflight evidence (docs/phase4/reports/q6/)
git-status-after.txt, hashes-after.txt (temp path, then move in), changed-files.txt
(diff of the manifests; every entry explained; nothing outside the allowlist),
focused-tests.log, final-gate.log, mutation-proof.log. No dump files, no secrets.

## 8. The report: docs/phase4/reports/QTA_Q6_REPORT.md (EXACT sections, these titles)
1. Summary (5 lines; status "implemented, awaiting review").
2. Files (table of every created/modified file; must match changed-files.txt).
3. FR-MDL-020 AC3 isolation proof (4.1): setup, what was compared, written-table sets
   before/after, positive control, reverse direction. Say plainly what "balance" means
   while consumption is NOT_INTEGRATED.
4. Upgrade and backup/restore rehearsals (4.2, 4.3): steps, what was compared, results.
5. UI wording fixes (4.4): before/after per label; every edited assertion.
6. Tests: every new or edited test -> FR/AC.
7. Results: baseline vs final (API, browser), static checks, mutation table with hashes.
8. Decisions and deviations: Q-g and Q-h defaults as applied, R17–R20, anything else.
9. Open questions / risks / NOT verified (hosted CI; Docker Compose rehearsal on a
   disposable stack; the real aq-uai-dev upgrade; a real scheduler; browsers other
   than Chromium).
10. Implementer's review (discussion, not decisions). Answer each by its ID:
    Q-i  R19: map the actual lock order of upsert_group_quotas, set_specialist_group_
         active, sync_groups and directory membership writes (file:line for each lock).
         Would FOR SHARE on AccountGroup in upsert_group_quotas be safe (no lock-order
         inversion)? Recommend yes/no with the reason.
    Q-j  Is anything in the QTA module, in your view, still missing for the FRD's Must
         scope (API, UI or tests)? Name it or write "nothing found".
    Q-k  What should Phase 5 (CRT) watch out for when it builds on QTA? (max 5 points)
    Q-l  What in this prompt was unclear or wrong?
11. (Leave empty: "Reviewer response".)
Also add the "Q6 completion" section to QTA_IMPLEMENTATION_PLAN.md linking the report.

## 9. Stop
After the report, stop. Phase 5 (CRT) needs a separate authorization.
~~~
