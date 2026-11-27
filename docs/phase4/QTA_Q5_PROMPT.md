# Prompt for the implementing agent — QTA Stage Q5 (Admin UI)

**Use:** the Project Owner pastes everything inside the fence below to the implementing agent (this time: Gemini Neon in Google Antigravity). After it finishes, the reviewer (Claude Code) reads `docs/phase4/reports/QTA_Q5_REPORT.md` and the evidence folder `docs/phase4/reports/q5/`, and verifies them independently.

**Before pasting:** commit the reviewed Q3 + Q4 work, so that Q5 starts from a clean, committed tree. (Q4 started on an uncommitted tree, which made the evidence harder to read.)

**Reviewer decisions baked into this prompt.** These are recommendations within PD-Q1..PD-Q6 and R1–R9; they are not new PO decisions. The agent must list them in report §8 and may argue against them in §10:
- R10: The screen is one admin section, key `qta`, titled with the FRD menu name **"Hạn mức AI theo Nhóm tài khoản"**. It is a flat sidebar entry, visible when the user holds any `qta.read` scope. The FRD menu tree (*Quản trị AI & Dữ liệu → Quản lý AI & Chi phí*) is **not** introduced as sidebar regrouping in Q5, because that would change navigation that existing browser tests rely on. The agent gives its opinion in §10.
- R11: Q5 is UI-only. The backend under `apps/api/src/` is frozen. The only Python changes are the test carry-overs C5–C7. If a UI acceptance criterion cannot be met with the current API, stop and ask; do not change the API.
- R12: Actors follow the MDL precedent (`mdl.mjs` history shows actor UUIDs in `<code>`). Show `suspended_by`, `restored_by`, `actor_id` and `recorded_by` as `<code>` UUIDs, or as the label "Bạn" when the UUID equals the signed-in user's id. In the suspend dialog, *Người thực hiện* is the signed-in user's display name, shown read-only. It is visibly separate from the required *Người ra lệnh* text input.
- R13: Month only, per R1. The personal lookup offers exactly two months: the current month and the next month (institution timezone `Asia/Ho_Chi_Minh`). Budgets and events use a single `<input type="month">`. No other period or cycle control exists anywhere.
- R14: Write controls (buttons, dialogs) are rendered only when `permission(caps, 'qta.manage')` is institution-wide. A GLOBAL `AI_QUOTA_VIEWER` sees everything read-only. A UNIT-scoped viewer sees only the personal lookup tab, because the other read endpoints are GLOBAL-only and answer 403.
- R15: Every amount is formatted with `Intl.NumberFormat('vi-VN')` and labelled **"đơn vị hạn mức"**. Consumption is shown only as the text **"Chưa tích hợp đo tiêu thụ thực tế"**: no progress bars, no percentages, no remaining amount.
- R16: Error text comes from a per-code Vietnamese map in `qta.mjs`, the same way `mdl.mjs` has `errorMessages`. `api.mjs` `safeDetails` gains exactly two numeric keys, `allocated` and `deficit`, each accepted only as a non-negative safe integer, so the budget-rejection message can state the exact shortfall.

~~~text
# AQ EduUAI — Phase 4 QTA, Stage Q5: Admin UI (authorized by the Project Owner).

Stage Q5 = the browser screen "Hạn mức AI theo Nhóm tài khoản" (#qta) in apps/admin/, on
top of the finished /api/v1/qta backend, plus three small test carry-overs (C5–C7) from
the Q4 review. FRs: the UI acceptance criteria of FR-QTA-001, 010, 011, 020, 021, 022,
030, 031, 032, 040, 041, 050 (see the "- [ ]" lines in the FRD).
NOT in Q5: any backend source change, migrations, backup/restore rehearsal and handoff
(Q6), CRT (Phase 5), apps/web/ (frozen prototype), mdl.mjs.

The Project Owner and the reviewer (Claude Code) are the decision makers. Follow every
rule below even if you disagree, and argue for changes in report §10.

## 0. Read first
AGENTS.md, CLAUDE.md, docs/PROJECT_CONTEXT.md, docs/frd/AQ-FRD-UAI-QTA-001.md (all, esp.
every "- [ ]" acceptance line), docs/phase4/QTA_IMPLEMENTATION_PLAN.md (Q5 section),
QTA_ARCHITECTURE_AND_DECISIONS.md (§2, §5 API table), QTA_OPEN_DECISIONS.md (PD-Q1..PD-Q6),
docs/phase4/QTA_Q5_PROMPT.md (R10–R16 above the fence), reports/QTA_Q4_REPORT.md
(§5 API with example bodies, §10.e UI mapping, §11 reviewer response).
Frontend code to learn the patterns from (read fully before writing anything):
apps/admin/index.html, apps/admin/assets/{app,pages,ui,api,mdl}.mjs, admin.css.
mdl.mjs is the closest model: tabs object, errorMessages map, listing(), formDialog(),
permission() gating, history tables without edit/delete. Reuse ui.mjs helpers; do not
build a parallel framework.
Browser tests to learn from: tests/browser/conftest.py, test_admin.py (admin_session,
login, change_password, capture), test_mdl.py (api() helper, second browser context for
a role-holding user, open_dialog).
API contract: GET http://<test api>/api/v1/openapi.json or apps/api/src/aq_uai_api/qta/
schemas.py + api/v1/qta.py (23 operations). Do not guess field names; read them.

## 1. Hard rules (any violation = stop and report; do not work around it)
- Never read, print or copy .env. Never edit apps/web/ or apps/admin/assets/mdl.mjs.
  No commits, pushes or deploys.
- Do not touch the developer's Docker stack (aq-uai-dev). Disposable environments only.
- No backend change: nothing under apps/api/src/, no migration, no infra/, scripts/,
  .env.example, nginx or CSP change. If the UI truly needs an API change, STOP and ask.
- Do not weaken, skip, delete or xfail any test. The only existing-test edit allowed is
  C5 in test_q2_contracts.py (section 4.0). Explain it with before/after/why.
- No invented units, prices, conversions, consumption, balances or policy. Amounts are
  "đơn vị hạn mức". Never show tokens, credits, prices or a consumption number.
- No innerHTML with API data. Build DOM with ui.mjs el() (text nodes), as the other
  pages do. Never render error details other than the allowlisted keys.
- Only edit files in the allowlist (section 3). Anything else: stop and ask.
- Never report a test you did not run.

## 2. Preflight evidence (before changing anything)
Create docs/phase4/reports/q5/ and save git-status-before.txt, hashes-before.txt
(`find apps tests scripts infra docs .github -type f -not -path '*/__pycache__/*'
-not -path '*/.ruff_cache/*' -not -path '*/node_modules/*' -print0 | sort -z |
xargs -0 sha256sum`), and baseline-gate.log (full gate, section 6).
Expected baseline: API 578 passed, 1 skipped; browser 16 passed. Any difference: stop
and report it before coding.

## 3. File allowlist
New:      apps/admin/assets/qta.mjs                     (the whole #qta screen)
          tests/browser/test_qta.py                     (Playwright, section 5)
          apps/api/tests/integration/test_q5_carryover.py (C6, C7)
          docs/phase4/reports/** (report and evidence)
Modified: apps/admin/assets/app.mjs     (route parsing for #qta only)
          apps/admin/assets/pages.mjs   (register the qta section, dispatch to qtaPage)
          apps/admin/assets/api.mjs     (R16: safeDetails numeric allocated/deficit only)
          apps/admin/assets/admin.css   (QTA styles; append-only, no edits to old rules)
          apps/admin/assets/ui.mjs      (ONLY if a small additive helper is unavoidable;
                                         never change an existing export's behaviour)
          apps/api/tests/unit/test_q2_contracts.py (C5 only)
          docs/phase4/QTA_IMPLEMENTATION_PLAN.md (Q5 completion section),
          QTA_REQUIREMENTS_TRACEABILITY.md (UI status per FR),
          docs/PROJECT_CONTEXT.md, docs/acceptance-matrix.md, CLAUDE.md (status lines)
Not allowed: everything else, including apps/web/, mdl.mjs, apps/api/src/, migrations,
infra/, scripts/, tests/browser/conftest.py, other existing tests.

## 4. What to build

4.0 Test carry-overs from the Q4 review (do these first)
  C5 Replace the forbidden-word check in test_q2_contracts.py
     (test_qta_openapi_has_no_forbidden_fields_and_rejects_unknown_inputs). Today it
     regex-searches json.dumps() of whole schemas, so prose trips it: "lifecycle"
     contains "cycle". New rule, applied to every /api/v1/qta operation:
       - Collect identifiers only: path segments, parameter names, enum values, and the
         property names of every component schema reachable from those operations.
         Never scan description/title/summary prose.
       - Split each identifier into lowercase words on "_", "-", "/", "{", "}" and
         camelCase boundaries.
       - Forbidden words: period, semester, cycle, price, cost, token, tokens, credit,
         credits, consumption, conversion, exam, project. Forbidden adjacent pairs:
         (hoc, ky), (de, tai), (dot, thi). Compare whole words, never substrings, so
         "generate" or "example" can never match.
       - Request schemas and parameters: zero hits. Response schemas: hits allowed only
         for the properties actual_consumption and consumption_status (R4).
       - Keep the existing strict-input part of the test (bad_key loop, invalid quota
         payloads) unchanged. "period" stays forbidden: it is what keeps the API on
         "month" (R3).
     Add a unit test proving the splitter: "lifecycle_status" -> no hit;
     "semester_id" -> hit; "hoc_ky" -> hit; "consumption_status" in a response -> allowed.
  C6 New test in test_q5_carryover.py: for several users with overlapping groups, a
     disabled quota row, an inactive group and a disabled user, assert for every model
     in GET /qta/users/{id}/entitlements that
     sum(c["contributes"] for c in contributions) == base_entitlement.
     (The breakdown is computed separately from the SQL total; this pins them together.)
  C7 New test in test_q5_carryover.py: call access.check_ai_access with a real
     PostgreSQL session (runtime role) and prove the three branches that are only
     unit-tested today: USER_NOT_FOUND (random UUID, and a user of another institution),
     USER_NOT_ACTIVE (disabled user), NO_ENTITLEMENT (active user in no quota group).
  Reuse fixtures/helpers from test_q3_qta_lookup_budgets.py and test_q4_*.py by import;
  do not copy them.

4.1 Routing and section (app.mjs, pages.mjs)
  - Section key "qta", title "Hạn mức AI theo Nhóm tài khoản", visible when
    hasScope(caps, 'qta.read') (R10). Flat sidebar entry; do not regroup the sidebar.
  - Routes: #qta, #qta/<tab>, #qta/groups/<uuid>. Tab keys: groups, lookup, ledger.
    Parse #qta exactly the way #mdl is parsed; anything else -> existing "not found".
  - A UNIT-scoped viewer lands on the lookup tab and sees only that tab (R14).
  - pages.mjs already labels all 7 qta.* audit actions (checked by the reviewer); do not
    change them. Only register the section and dispatch `route === 'qta'` to qtaPage.

4.2 Header: school monthly budget (FR-QTA-010, FR-QTA-011)
  - Month picker (<input type="month">, default current month). GET /qta/budgets?month=.
  - Show: total_limit with "đơn vị hạn mức", or status_label ("chưa ghi nhận") when
    status is NOT_RECORDED; allocated, remaining; a warning banner when
    over_allocated > 0; the decision number and date of the current revision.
  - Revision history table (newest first): revision, total, decision number, decision
    date, recorded_by (R12), recorded_at. No edit or delete control on any row.
  - Manage only: "Ghi nhận tổng hạn mức tháng" dialog -> PUT /qta/budgets/{month} with
    total_limit, decision_number (required), decision_date (required). Only the current
    and next month are writable (server enforces; disable the button otherwise and say
    why). On 409 QTA_BUDGET_BELOW_ALLOCATED show:
    "Tổng mới thấp hơn phần đã phân bổ (<allocated>). Cần giảm phân bổ ít nhất <deficit>
    đơn vị hạn mức." using error.details.allocated / deficit (R16).

4.3 Tab "groups" — Nhóm & Hạn mức Mô hình (FR-QTA-001, 020, 021, 022)
  - GET /qta/groups. Empty before sync: an explicit empty state ("Chưa có nhóm nào. Hãy
    đồng bộ từ Quản lý nhóm tài khoản."), never an error.
  - Manage only: "Đồng bộ nhóm" (POST /qta/groups/sync), then show the sync run summary;
    a "Lịch sử đồng bộ" table from GET /qta/groups/sync-runs.
  - Manage only: "Tạo nhóm AI chuyên biệt" (POST /qta/groups).
  - Group list: code, name, kind badge (SYSTEM / AI_SPECIALIST), origin, active,
    in_directory (show retired groups as "Đã ngừng trong danh bạ"), member count.
  - Detail #qta/groups/<id>: facts; members (GET .../members); for AI_SPECIALIST and
    manage only: rename (PATCH), activate/deactivate, add member (reference picker over
    GET /qta/users) and remove member (DELETE .../members/{user_id}).
  - Per-model quota editor (manage only): one row per model from GET /qta/models with
    enabled checkbox, monthly_limit, optional warning_threshold_pct; save with
    PUT .../quotas. Stored rows whose model_active is false get the badge
    "Mô hình / nhà cung cấp đang tắt" and are shown read-only.
  - SYSTEM groups: name/members are owned by the directory; show that, offer no
    rename/member controls.

4.4 Tab "lookup" — Tra cứu Cộng dồn Cá nhân & Cắt/Ngưng (FR-QTA-030, 031, 040, 041)
  - Search users: GET /qta/users?q= (paged), each row shows state and a quota_status
    badge: ACTIVE -> "Hoạt động", SUSPENDED -> "ĐÃ CẮT".
  - Pick a user -> GET /qta/users/{id}/entitlements?month= with a selector offering
    only the current and next month (R13).
  - Per model: the additive formula, e.g. "1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn
    mức" built from contributions; groups contributing 0 shown with why (enabled false);
    the access badge (allowed / reason mapped to Vietnamese for every reason code:
    USER_NOT_ACTIVE, MODEL_UNAVAILABLE, SUSPENDED_ALL_MODELS, SUSPENDED_PAID_EXTERNAL,
    NO_ENTITLEMENT); and the text "Chưa tích hợp đo tiêu thụ thực tế" (R15).
  - Memberships table with qualifies / excluded_reason in Vietnamese.
  - A user with no groups shows base 0 and the NO_ENTITLEMENT badge (FR-QTA-031 AC2).
  - Active suspension card: scope (ALL_MODELS -> "Tất cả mô hình", PAID_EXTERNAL_ONLY ->
    "Chỉ mô hình trả phí bên ngoài"), reason, Người ra lệnh (ordered_by), Người thực hiện
    (suspended_by, R12), suspended_at, expires_at or "Đến khi khôi phục".
  - Manage only: "Cắt / ngưng hạn mức" dialog -> POST /qta/users/{id}/suspensions with
    scope (radio), reason (required), ordered_by (required, label "Người ra lệnh"),
    optional expiry (<input type="datetime-local">, converted to an ISO string with the
    browser's offset; leave empty for "until restored"). Show "Người thực hiện: <your
    display name>" read-only above the inputs (R12). 409 QTA_USER_ALREADY_SUSPENDED ->
    clear Vietnamese message.
  - Manage only, when SUSPENDED: "Khôi phục" dialog -> POST /qta/users/{id}/restore with
    optional note.
  - Suspension history (GET /qta/users/{id}/suspensions): status ACTIVE / RESTORED /
    EXPIRED in Vietnamese, restoration details; no edit/delete controls.

4.5 Tab "ledger" — Làm mới Đầu tháng & Nhật ký (FR-QTA-032, 050)
  - GET /qta/monthly-resets: current month card (COMPLETED -> "Đã làm mới tháng
    MM/YYYY", with trigger mode MANUAL_SIMULATION -> "Giả lập thủ công" or SCHEDULED ->
    "Tự động theo lịch"); PENDING -> "Chưa làm mới tháng MM/YYYY"; history table.
  - Manage only: "Giả lập làm mới tháng hiện tại" -> POST /qta/monthly-resets with no
    body. Disabled when the current month is COMPLETED. Explain in one line that the
    previous month's unused amount never carries over (FR-QTA-032 AC2).
  - Events: month picker + event_type filter (SUSPEND / RESTORE / MONTHLY_REFRESH, in
    Vietnamese) -> GET /qta/events; columns time, type, user, actor (R12), summary.
    Read-only: no edit or delete control on any row (FR-QTA-050 AC2).

4.6 Shared plumbing
  - api.mjs: R16 only (allocated, deficit: Number.isSafeInteger && >= 0).
  - qta.mjs errorMessages for every QTA_* code in api/errors.py, plus NOT_FOUND and
    VALIDATION_FAILED in QTA wording. Unknown codes fall back to the generic message.
  - admin.css: chips, formula line, banner; must work at 375 px width (no horizontal
    page scroll) and pass the existing CSP (no inline styles or scripts).

4.7 Docs: traceability UI status per FR; plan "Q5 completion" section; status lines in
  PROJECT_CONTEXT.md, acceptance-matrix.md, CLAUDE.md. Formal acceptance stays 0 — do
  not mark any FR accepted.

## 5. Required tests

5.1 tests/browser/test_qta.py (Playwright through nginx, like test_mdl.py)
  Setup notes:
  - The browser tests run a real server, so the clock is real. Compute the current and
    next month in Asia/Ho_Chi_Minh inside the test; never hard-code "2026-11" (the next
    month crosses a year boundary in December). Open role-holder contexts with
    locale="vi-VN" and timezone_id="Asia/Ho_Chi_Minh".
  - Create units/users/groups/role assignments through the admin API (api() helper).
  - MDL models: insert one EXTERNAL and one INTERNAL provider + one active model each
    directly in the disposable database (as the API fixtures add_provider/add_model do;
    read their SQL), so no provider is ever contacted.
  - Keep the number of browser tests small (each starts a stack): at most 4 tests.
  Must prove (group the checks into ≤4 tests):
  a. Access: FOUNDATION_ADMIN has no #qta entry and gets the 403 page on #qta;
     GLOBAL AI_QUOTA_VIEWER sees all tabs with zero write buttons; UNIT viewer sees only
     the lookup tab and only own-unit users (FR-QTA-001).
  b. Groups: empty state before sync; sync shows SYSTEM groups and keeps an existing
     AI_SPECIALIST group; specialist group create + add member; two different limits
     for two models in the same group; disabling a model's quota drops that user's base
     for that model in the lookup (FR-QTA-020/021/022 UI ACs).
  c. Budget + lookup: record a budget with decision number (missing number -> blocked
     with a message); reduce below allocated -> rejection shows the exact deficit;
     a user in G1 (1.000) and G2 (3.000) on the same model shows
     "1.000 (G1) + 3.000 (G2) = 4.000" and the not-integrated consumption text; a user
     with no group shows 0 / NO_ENTITLEMENT (FR-QTA-010/011/030/031 UI ACs).
  d. Kill-switch + ledger: suspend PAID_EXTERNAL_ONLY with reason + ordered_by (missing
     either -> blocked); list badge "ĐÃ CẮT"; per-model badges: EXTERNAL blocked,
     INTERNAL allowed; Người thực hiện shows the admin, distinct from Người ra lệnh;
     restore -> "Hoạt động"; simulate reset -> "Đã làm mới", button disabled; events
     table shows SUSPEND, RESTORE, MONTHLY_REFRESH rows (FR-QTA-032/040/041 UI ACs).
  In every test, DOM checks over the whole #qta content:
  - wording: the text contains "đơn vị hạn mức" wherever amounts appear, and matches
    none of /token|credit|tín dụng|học kỳ|đề tài|đợt thi|đơn giá|quy đổi|semester|exam/i
  - zero <select>/<input> offering a cycle other than month (FR-QTA-010 AC3, 050 AC1)
  - zero buttons/links named Sửa/Xóa/Edit/Delete inside revision, suspension, reset or
    event history tables (FR-QTA-050 AC2)
  - no consumption number, percentage or progress bar is rendered.
5.2 Python: C5 (unit), C6 and C7 (integration) as described in 4.0.

5.3 Mutation proofs (break, run the named test, see it fail, restore byte-identically,
    record before/after sha256 in mutation-proof.log):
  1. Render the suspend button without the qta.manage check -> test a fails.
  2. Change one amount label to "tokens" -> the wording check fails.
  3. In qta.mjs, offer a third month in the lookup selector -> the month check fails
     (or the API 422 surfaces; say which).
  4. Temporarily add a property semester_id to one QTA Output schema -> C5 fails, and
     a property "lifecycle_status" does NOT fail C5 (prove both).
  5. In entitlements.compute_user_entitlements, make contributes ignore `enabled` ->
     C6 fails. (Temporary edit of a backend file for the proof only; restore and show
     the hash.)

## 6. Verification commands
Static: python scripts/verify_frontend_assets.py; node --check on every changed .mjs
        (node --check works on .mjs files); ruff on the Python tests.
Focused: pytest test_q2_contracts.py + test_q5_carryover.py (disposable PG);
         pytest tests/browser/test_qta.py.
Full gate (save to docs/phase4/reports/q5/final-gate.log):
  AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv python> \
  AQ_NGINX=<nginx or wrapper> bash scripts/verify_phase2.sh
Report API and browser counts separately. Expected: API 578 + your new Python tests
passed, 1 skipped; browser 16 + your new browser tests passed.
If a known startup-timing flake appears in an old browser test, re-run once and record
both runs; never hide a failure.

## 7. Postflight evidence (docs/phase4/reports/q5/)
git-status-after.txt, hashes-after.txt (write to a temp path, then move in),
changed-files.txt (`diff hashes-before.txt hashes-after.txt`; every entry explained;
nothing outside the allowlist), focused-tests.log, final-gate.log, mutation-proof.log,
and screenshots/ with one PNG per tab for the admin and for the UNIT viewer (desktop),
plus one 375 px-wide PNG of the lookup tab. Synthetic data only; no secret anywhere.

## 8. The report: docs/phase4/reports/QTA_Q5_REPORT.md (exact sections)
1. Summary (5 lines; status "implemented, awaiting review").
2. Files: table of EVERY created/modified file (path, new/modified, why, FR);
   must match changed-files.txt.
3. Carry-overs C5–C7: what changed, tests.
4. Screen design in plain words: tabs, what each role sees, which endpoint feeds each
   element, how errors are shown. Link the screenshots.
5. FR-QTA UI acceptance table: every "- [ ]" line of the FRD -> the browser test and
   assertion that proves it, or "not covered" with the reason.
6. Tests: every new test -> FR/AC; the C5 before/after/why.
7. Results: baseline vs final (API, browser), static checks, mutation table with hashes.
8. Decisions and deviations: R10–R16 as applied, anything else you decided, and why.
9. Open questions / risks / not verified (hosted CI, live Compose, real browsers other
   than Chromium, screen readers).
10. Implementer's review of the plan and this prompt (discussion, not decisions):
    what was unclear, wrong or missing; what you would change for Q6. Also answer:
    Q-g Actors are shown as UUIDs (R12). Should Q6 add display-name projections for
        suspended_by / restored_by / actor_id / recorded_by (and MDL's changed_by) in one
        consistent change? What would it cost?
    Q-h Should the sidebar be regrouped to match the FRD menu tree (*Quản trị hệ
        thống* vs *Quản lý AI & Chi phí*)? What would break?
11. (Leave empty: the reviewer writes "Reviewer response" here.)
Also add a short "Q5 completion" section to QTA_IMPLEMENTATION_PLAN.md linking the report.

## 9. Stop
After the report, stop. Q6 needs a separate instruction.
~~~
