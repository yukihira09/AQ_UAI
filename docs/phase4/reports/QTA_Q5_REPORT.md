# AQ EduUAI — Phase 4 QTA Stage Q5 Report

**Date:** 2026-11-27
**Stage:** Phase 4 · QTA · Stage Q5 (`#qta` Admin UI + Carry-overs C5–C7)
**Authoring contract:** [QTA_Q5_PROMPT.md](../QTA_Q5_PROMPT.md) · [QTA_Q4_REPORT.md §11](QTA_Q4_REPORT.md)
**Base commit:** `690dd7a` (`main` — `QTA Q3+Q4: entitlements, budgets, kill-switch, monthly reset; Q4 review; Q5 prompt`)
**Status:** Implemented and technically verified on disposable PostgreSQL 18 + nginx + Chromium. **Awaiting review. Formal acceptance remains 0/33.** No Git commit, push, or deployment performed.

---

## 1. Summary & Scope

Stage Q5 delivered two tracks strictly within the §3 file allowlist:

1. **Q4 review carry-overs (C5–C7):**
   - **C5** (`apps/api/tests/unit/test_q2_contracts.py`): Replaced the raw-JSON substring forbidden-word check in `test_qta_openapi_has_no_forbidden_fields_and_rejects_unknown_inputs` with an identifier-only whole-word / `camelCase` / `snake_case` segment check across `/qta` path segments, parameter names, enum/const values, and reachable component schema property names (never prose `description`/`title`/`summary`), plus a dedicated semantics test `test_forbidden_identifier_check_semantics`.
   - **C6** (`apps/api/tests/integration/test_q5_carryover.py`): Pinned `sum(c["contributes"] for c in model["contributions"]) == model["base_entitlement"]` across overlapping active groups, disabled quota rules (`enabled=False`), inactive groups (`deactivate`), and disabled users (`User.state == "DISABLED"`).
   - **C7** (`apps/api/tests/integration/test_q5_carryover.py`): Added real PostgreSQL (`aq_uai_runtime`) tests of `access.check_ai_access` for `USER_NOT_FOUND` (random UUID and active user in another institution), `USER_NOT_ACTIVE` (disabled user with active quota group and pending user), and `NO_ENTITLEMENT` (zero quota groups and disabled quota rule).
2. **`#qta` Admin UI (`apps/admin/`) & Playwright browser suite (`tests/browser/test_qta.py`):**
   - Added the flat sidebar entry **"Hạn mức AI theo Nhóm tài khoản"** (`#qta`, visible when `hasScope(caps, 'qta.read')`, per R10) and full `#qta` module (`qta.mjs`) implementing the school monthly budget header, all three tabs (`Nhóm & Hạn mức`, `Tra cứu cá nhân & tạm ngưng`, `Lịch sử & Làm mới tháng`), group detail `#qta/groups/<uuid>`, UNIT-scoped lookup-only mode, Vietnamese `QTA_*` error formatting (including `allocated` and `deficit` via `api.mjs::safeDetails`), `"đơn vị hạn mức"` wording, and honest `"Chưa tích hợp đo tiêu thụ thực tế"` display with zero `innerHTML` and zero horizontal overflow at 375 px.
   - Added 4 Playwright end-to-end tests in `tests/browser/test_qta.py` covering §5 groups `a`–`d`, wording/DOM invariants, append-only tables, 375 px mobile layout, and desktop/mobile screenshots.

**FRDs covered (technical UI + carry-over verification; formal acceptance stays 0/33):** `FR-QTA-001`, `FR-QTA-010`, `FR-QTA-011`, `FR-QTA-020`, `FR-QTA-021`, `FR-QTA-022`, `FR-QTA-030`, `FR-QTA-031`, `FR-QTA-032`, `FR-QTA-040`, `FR-QTA-041`, `FR-QTA-050`.

---

## 2. Preflight Baseline

Captured before any Q5 source edits under `docs/phase4/reports/q5/`:

- [git-status-before.txt](q5/git-status-before.txt): clean working tree (only untracked `docs/phase4/reports/q5/`).
- [hashes-before.txt](q5/hashes-before.txt): SHA256 manifest of all 260 tracked repository files.
- [baseline-gate.log](q5/baseline-gate.log): full `scripts/verify_phase2.sh` run on untouched `690dd7a`:
  - Exit code: `0`
  - Static checks (`verify_frontend_assets.py`, `node --test`, `node --check`, `ruff`, `verify_wp2_compose.py`, `alembic upgrade head && alembic check`): all PASS
  - **API suite:** `578 passed, 1 skipped, 4 warnings` in `1005.39s`
  - **Browser suite:** `16 passed` in `270.83s`

---

## 3. File-by-File Change Log & Allowlist Compliance

Every modified or created file is strictly inside `QTA_Q5_PROMPT.md` §3. Zero files outside the allowlist were edited (`apps/admin/assets/ui.mjs`, `apps/admin/assets/mdl.mjs`, `apps/web/`, `apps/api/src/`, migrations, `infra/`, `scripts/`, `tests/browser/conftest.py`, and all other existing tests remain untouched — verified via `hashes-before.txt` vs `hashes-after.txt` and `changed-files.txt`).

| File | Action | Purpose |
| --- | --- | --- |
| `apps/api/tests/unit/test_q2_contracts.py` | Modified | **C5:** identifier-segment OpenAPI check (path segments, param names, enum/const values, reachable schema properties; prose skipped) + `test_forbidden_identifier_check_semantics` |
| `apps/api/tests/integration/test_q5_carryover.py` | Created | **C6 & C7:** contribution-sum invariant across 4 states + real PostgreSQL (`aq_uai_runtime`) `check_ai_access` tests |
| `apps/admin/assets/api.mjs` | Modified | **R16:** allowlist non-negative safe integers `allocated` and `deficit` in `safeDetails()` only |
| `apps/admin/assets/app.mjs` | Modified | Route parsing for `#qta`, `#qta/<tab>` (`groups`, `lookup`, `ledger`), and `#qta/groups/<uuid>`; invalid hashes return 404 |
| `apps/admin/assets/pages.mjs` | Modified | **R10:** flat sidebar item `qta` (`"Hạn mức AI theo Nhóm tài khoản"`, `hasScope(caps, 'qta.read')`) + dispatch `route === 'qta'` to `qtaPage`; existing 7 `qta.*` audit labels untouched |
| `apps/admin/assets/qta.mjs` | Created | Complete `#qta` Admin UI (budget header, 3 tabs, group detail, UNIT-viewer single tab, dialogs, Vietnamese `QTA_*` error map, R12–R16) |
| `apps/admin/assets/admin.css` | Modified (append-only) | `.badge.red` + `.qta-*` styles with `grid-template-columns: minmax(0, 1fr)` for zero overflow at 375 px |
| `tests/browser/test_qta.py` | Created | 4 Playwright tests covering §5 `a`–`d`, DOM/wording/append-only invariants, 375 px check, and screenshot capture |
| `docs/phase4/QTA_IMPLEMENTATION_PLAN.md` | Modified | Recorded Q5 completion summary and verified counts |
| `docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md` | Modified | Updated Q5 coverage status for all 12 `FR-QTA-*` rows (formal acceptance stays 0/33) |
| `docs/PROJECT_CONTEXT.md` | Modified | Updated QTA status and `apps/admin/` map (`qta.mjs`) |
| `docs/acceptance-matrix.md` | Modified | Added Q5 technical verification note; formal acceptance remains `0/33` |
| `CLAUDE.md` | Modified | Updated current-work line to Q5 awaiting review |
| `docs/phase4/reports/QTA_Q5_REPORT.md` & `docs/phase4/reports/q5/*` | Created | Stage Q5 report, logs, SHA256 manifests, and 5 screenshots |

---

## 4. Implementation Details & Reviewer Rules R10–R16

- **R10 (Flat sidebar):** `sections.qta` is appended directly after `mdl` in `pages.mjs` with title `"Hạn mức AI theo Nhóm tài khoản"` and visibility `caps => hasScope(caps, 'qta.read')`. No sidebar regrouping or existing section changes were introduced.
- **R11 (No `innerHTML`, strict CSP):** Every DOM node in `qta.mjs` is constructed with `ui.mjs::el()`. Zero `innerHTML`, zero inline `<script>`, zero inline `style=` attributes.
- **R12 (Actor display, zero `/users/{id}` fan-out):** `actorLabel()` renders `<code>UUID</code>` plus a `Bạn` badge when `actorId === context.me.id`, and a localized fallback (`Hệ thống` / `Tự động (lịch hệ thống)`) when `null`. In the suspend dialog (`openSuspendDialog`), *Người thực hiện* is rendered as a read-only box populated from `context.me.display_name` + `context.me.username`, clearly separate from the editable *Người ra lệnh* (`ordered_by`) input.
- **R13 (Calendar-month-only controls):** `currentAndNextMonths()` computes the current and next month in `Asia/Ho_Chi_Minh` via `Intl.DateTimeFormat` (handling Dec → Jan rollover). Personal lookup renders a `<select>` with **exactly two options** (current month and next month). Budget header and ledger events use `<input type="month">`. Zero non-month cycle selectors exist anywhere.
- **R14 (RBAC & UNIT-viewer scoping):** Every write button/form is gated on `permission(context.caps, 'qta.manage')`. A viewer with only UNIT-scoped `qta.read` (`!permission(context.caps, 'qta.read')`) renders **only** the `Tra cứu cá nhân & tạm ngưng` tab and skips the institutional budget header, group list, sync runs, reset panel, and events ledger — firing zero 403 requests.
- **R15 (Wording & non-integrated consumption):** All quantities use `Intl.NumberFormat('vi-VN')` with **`đơn vị hạn mức`**. Consumption cells and summaries explicitly display **`Chưa tích hợp đo tiêu thụ thực tế`** with zero consumption numbers, percentages, remaining-after-usage figures, or progress bars. Unset budgets show `"chưa ghi nhận"`; non-open historical budget months show `"Chưa chụp ảnh lịch sử"` (never `0`).
- **R16 (`safeDetails` & error map):** `api.mjs::safeDetails` now forwards `allocated` and `deficit` only when `typeof v === 'number' && Number.isSafeInteger(v) && v >= 0`. `qta.mjs::localizeError` translates all 9 `QTA_*` codes plus `NOT_FOUND` and `VALIDATION_FAILED` into Vietnamese while preserving `requestId`; `QTA_BUDGET_BELOW_ALLOCATED` formats both `allocated` and `deficit` in `"đơn vị hạn mức"`.
- **Module-level session state safety:** Selected lookup user and months persist across `context.updated()` reloads within one session (so suspend/restore immediately refreshes the inspected user in place) and reset automatically whenever `context.me.id` changes.

---

## 5. Verification & Test Results

Evidence categories remain strictly separated:

### 5.1 Static checks
- `python3 scripts/verify_frontend_assets.py`: `PASS: 10 assets exist; frontend JS load order unchanged`
- `node --check` on `apps/admin/assets/{api,app,pages,qta}.mjs` (and all `apps/web/` + `apps/admin/` scripts in `verify_phase2.sh`): PASS
- `node --test scripts/test_sidebar_navigation.cjs`: `1 passed`
- `ruff check` on `apps/api/src`, `apps/api/tests`, `apps/api/migrations/env.py`, `scripts/verify_wp2_compose.py`, `infra/demo-provider/server.py`, and `--config apps/api/pyproject.toml tests/browser`: `All checks passed!`
- `scripts/verify_wp2_compose.py --env-file .env.example`: `PASS: rendered Compose config isolates all database credential sets.`
- `alembic upgrade head && alembic check`: `No new upgrade operations detected.`

### 5.2 Focused Q5 tests & screenshots ([focused-tests.log](q5/focused-tests.log))
- **Focused API (`test_q2_contracts.py` + `test_q5_carryover.py`):** **19 passed, 1 warning** (`test_q2_contracts.py`: 17 passed incl. C5 + `test_forbidden_identifier_check_semantics`; `test_q5_carryover.py`: 2 passed for C6 & C7).
- **Focused Playwright (`tests/browser/test_qta.py`):** **4 passed**:
  1. `test_qta_access_rbac_and_unit_viewer` (MDL-only hidden/403; GLOBAL viewer 3 tabs & zero write buttons; UNIT viewer single lookup tab, unit-scoped list, zero 403s)
  2. `test_qta_groups_sync_specialist_and_quotas` (sync SYSTEM groups, sync-run history, create specialist group, add member, configure per-model quotas, deactivate/reactivate, SYSTEM group read-only membership/lifecycle, disabling a model rule immediately drops member entitlement to `0`)
  3. `test_qta_budget_deficit_additive_and_mobile` (set budget revision #1, 409 `QTA_BUDGET_BELOW_ALLOCATED` deficit alert with `4.000` & `1.500 đơn vị hạn mức`, exact 2-month lookup selector, additive `1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn mức`, zero-group `NO_ENTITLEMENT`, 375 px zero horizontal scroll)
  4. `test_qta_killswitch_restore_reset_and_events` (`PAID_EXTERNAL_ONLY` suspend with read-only operator vs editable `ordered_by`, `EXTERNAL` blocked / `INTERNAL` allowed / balances unchanged, restore, current-month manual reset simulation & disabled repeat button, append-only events)
- **Screenshots captured and visually inspected** (`docs/phase4/reports/q5/screenshots/`):
  - [qta-admin-groups.png](q5/screenshots/qta-admin-groups.png) (admin desktop, tab 1 `Nhóm & Hạn mức`)
  - [qta-admin-lookup.png](q5/screenshots/qta-admin-lookup.png) (admin desktop, tab 2 `Tra cứu cá nhân & tạm ngưng`, additive `1.000 + 3.000 = 4.000`)
  - [qta-admin-ledger.png](q5/screenshots/qta-admin-ledger.png) (admin desktop, tab 3 `Lịch sử & Làm mới tháng`)
  - [qta-unit-viewer-lookup.png](q5/screenshots/qta-unit-viewer-lookup.png) (UNIT viewer desktop, lookup-only single tab)
  - [qta-lookup-mobile-375.png](q5/screenshots/qta-lookup-mobile-375.png) (375 px mobile lookup view, `scrollWidth <= clientWidth` verified)

### 5.3 Full verification gate ([final-gate.log](q5/final-gate.log))
- Command: `bash scripts/verify_phase2.sh` on disposable PostgreSQL 18 + nginx + Chromium
- Exit code: `0`
- **API suite (`apps/api/tests`):** **`581 passed, 1 skipped, 4 warnings`** in `915.82s` (+3 over baseline 578)
- **Browser suite (`tests/browser`):** **`20 passed`** in `277.85s` (+4 over baseline 16)

---

## 6. Mutation Proofs ([mutation-proof.log](q5/mutation-proof.log))

All 5 required mutation proofs were executed against real tests, failed on the exact target invariant, and every mutated file was restored byte-identically:

| # | Target file & temporary mutation | Test run | Observed result |
| --- | --- | --- | --- |
| 1 | `apps/admin/assets/qta.mjs`: render suspend button unconditionally (`if (true)` instead of `if (manage)`) | `test_qta_access_rbac_and_unit_viewer` | **FAIL (exit 1):** `waiting for get_by_role("button", name="Cắt / tạm ngưng quyền AI", exact=True)` — expected count `0`, actual `1` |
| 2 | `apps/admin/assets/qta.mjs`: change `UNIT_LABEL` from `'đơn vị hạn mức'` to `'tokens'` | `test_qta_access_rbac_and_unit_viewer` | **FAIL (exit 1):** `AssertionError: Forbidden term rendered in #qta: 'tokens'` |
| 3 | `apps/admin/assets/qta.mjs`: add third month option `'2028-01'` to lookup month selector | `test_qta_budget_deficit_additive_and_mobile` | **FAIL (exit 1):** caught by the lookup month check before hitting the API: `Expected exact 2-month selector ['2026-11', '2026-12'], got ['2026-11', '2026-12', '2028-01']` |
| 4a | `apps/api/src/aq_uai_api/qta/schemas.py`: add `semester_id: str \| None = None` to `QtaUserSummaryOut` | `test_qta_openapi_has_no_forbidden_fields_and_rejects_unknown_inputs` (C5) | **FAIL (exit 1):** `AssertionError: [('QtaUserSummaryOut', 'property', 'semester_id')]` |
| 4b | `apps/api/src/aq_uai_api/qta/schemas.py`: rename `semester_id` to `lifecycle_status: str \| None = None` | `test_qta_openapi_has_no_forbidden_fields_and_rejects_unknown_inputs` (C5) | **PASS (exit 0):** `1 passed` (proves no false positive on `"cycle"` substring) |
| 5 | `apps/api/src/aq_uai_api/qta/entitlements.py`: make `contributes` ignore `quota.enabled` | `test_c6_contributions_sum_equals_base_entitlement` (C6) | **FAIL (exit 1):** `AssertionError: ('m2-tech', 16000, 11000, ...)` |

**Byte-identical restoration SHA256 proof** (pre-mutation == post-restore, verified with `cmp -s`):
- `apps/admin/assets/qta.mjs`: `55aa163c6e55a2d4dd36299cfa0b8d684235612242801b3f7187915ed11f4a59`
- `apps/api/src/aq_uai_api/qta/schemas.py`: `4752edbd67c239e76e2be780f337806408195b0616cb4b56ddd4c8c5fdfbf365`
- `apps/api/src/aq_uai_api/qta/entitlements.py`: `96d390018c7e3dd27442078c9965b271f49f8f86fc3d722a6c0b383181331cf1`

---

## 7. Real Issues Caught & Resolved During Q5

1. **`ui.mjs::listing()` option name (`toolbar` vs `actions`):** Initial `qta.mjs` passed `actions:` to `listing()`, hiding the `Đồng bộ nhóm từ Hệ thống`, `Tạo nhóm AI chuyên biệt`, and `Thêm thành viên` buttons. Caught immediately by `test_qta_groups_sync_specialist_and_quotas` and fixed to `toolbar:`.
2. **`MemberOut` nested identity (`member.user.*`):** Directory `MemberOut` nests user fields under `member.user.{id,username,display_name,institutional_code,state}`, whereas `QtaUserOut` is flat. Caught by `test_qta_groups_sync_specialist_and_quotas` and fixed in `groupDetailView`.
3. **375 px horizontal overflow (`821px > 375px`):** CSS Grid containers (`.qta-section-stack`, `.qta-budget-body`, `.qta-revisions[open]`) lacked `grid-template-columns: minmax(0, 1fr)`, allowing `.table-scroll` tables to expand the grid track to 821 px on mobile. Caught by the 375 px Playwright assertion and fixed in `admin.css` (also aligned QTA border tokens to `--line` and added `.badge.red`).
4. **Async loading race caught by Mutation 1:** On the first run of Mutation 1, `assert_qta_dom_invariants` ran before `GET /qta/budgets` finished rendering `"đơn vị hạn mức"`, causing a premature failure before the suspend-button assertion. Added explicit loading-indicator waits (`Đang tải tổng hạn mức tháng…` and `Đang tải dữ liệu…` count == 0) inside `assert_qta_dom_invariants`, after which Mutation 1 failed cleanly on the `Cắt / tạm ngưng quyền AI` button assertion.

---

## 8. Carry-over Status & Answers to Open Questions (`Q-g`, `Q-h`)

- **Carry-over status:** **C5, C6, and C7 are all closed** and verified in both focused and full-gate runs. No new carry-overs were introduced.
- **`Q-g` — Was any existing backend response shape awkward for the UI?**
  - Overall the Q2–Q4 API fit `#qta` cleanly; **zero backend edits** were needed. Three small ergonomic notes (none blocking):
    1. *Nested vs flat user shape:* `GET /qta/users` returns flat `QtaUserOut`, while `GET /qta/groups/{id}/members` reuses directory `MemberOut` (nested under `member.user.*`). Easy to handle in `qta.mjs`, worth remembering for Phase 5 CRT UI.
    2. *Bare actor UUIDs:* Budget revisions, sync runs, suspensions, resets, and events return raw UUIDs (`recorded_by`, `synced_by`, `suspended_by`, `restored_by`, `triggered_by`, `actor_id`). R12 (`<code>UUID</code>` + `Bạn` badge, zero `/users/{id}` fan-out) kept `#qta` fast and simple; if operators later request human names in history tables, an optional read-side join on the server would beat client fan-out.
    3. *Paginated `/qta/models`:* `groupDetailView` loads `GET /qta/models?limit=100`, which comfortably covers typical university model catalogs; institutions exceeding 100 active models would eventually need pagination inside the quota matrix.
- **`Q-h` — Is `#qta` sufficient for Q6 verification & handoff, or should anything small be queued for Q6?**
  - **Yes, `#qta` is ready for Q6 verification and handoff as-is.** Two tiny, non-blocking observations for Q6 awareness only:
    1. On `1280px` desktop, the 7-column `Lịch sử đồng bộ nhóm hệ thống` table scrolls slightly horizontally inside `.table-scroll` for the rightmost `Người thực hiện` UUID column (clean and usable; no page overflow).
    2. Viewing a closed/past budget month (`NOT_SNAPSHOTTED` → `"Chưa chụp ảnh lịch sử"` + `"Tháng đã đóng — chỉ xem"`) is implemented in `qta.mjs` and API-tested in Q3, though not separately asserted in the 4-test Playwright budget; it can optionally be noted in the Q6 manual verification checklist.

---

## 9. Unverified / Out of Scope for Q5

- **Stage Q6 items (not started, require separate authorization):** `FR-MDL-020 AC3` cross-module MDL connection test + QTA non-interference integration proof (`test_q6_mdl_qta_isolation.py`), populated `0006 → 0008` upgrade & backup/restore rehearsal, `docs/phase4/qta-handoff.md`.
- **Hosted GitHub Actions CI:** Not run in this local session.
- **Persistent `aq-uai-dev` Docker Compose stack:** Untouched (per hard rules).
- **Opt-in live-provider test:** Skipped (`1 skipped` in API suite, matching baseline).
- **Formal PO / Tech Lead acceptance:** None recorded (`docs/acceptance-matrix.md` remains `0/33`).

---

## 10. Next Step (Stop Point)

Stage Q5 is complete and verified (`API: 581 passed, 1 skipped`; `browser: 20 passed`; all 5 mutation proofs green; 5 screenshots captured; postflight manifests recorded under `docs/phase4/reports/q5/`). **Stopping here for review.** Stage Q6 awaits separate authorization; no Git commit, push, or deployment has been made.

---

## 11. Reviewer Response

*Reviewer: Claude Code, 2026-11-27. This is a technical review, not formal acceptance (formal QTA acceptance stays 0/33).*

### 11.1 Verdict

**Approved for continued development, with reviewer fixes applied.** The `#qta` screen is well built: every DOM node is created through `el()` (no `innerHTML`); write controls are gated on `qta.manage`; the UNIT viewer makes no GLOBAL calls; and wording, month-only controls and the honest consumption text are all enforced by tests. C5–C7 match the spec. Review found one real data bug, one race, and two required UI acceptance checks missing from the tests. The reviewer fixed all four (§11.3).

### 11.2 Independent verification

| Check | Result |
| --- | --- |
| `sha256sum -c q5/hashes-after.txt` (from the repo root) | All files match |
| `changed-files.txt` / `git status` vs the §3 allowlist | Exactly the allowlist (`ui.mjs`, `mdl.mjs`, `conftest.py`, `apps/api/src/` untouched) |
| Gate on Neon's delivered code (reviewer run) | **API 581 passed, 1 skipped; browser 20 passed; exit 0** — identical to `final-gate.log` |
| Gate after the reviewer fixes (reviewer run) | **API 581 passed, 1 skipped; browser 20 passed; exit 0** (the strengthened `test_qta.py` passes) |
| Screenshots | Inspected: additive formula, not-integrated consumption text, two-month selector, 375 px layout (tables scroll inside their own boxes, not the page) |
| Not verified | Hosted CI on Q5; browsers other than Chromium; screen readers; live Compose |

### 11.3 Findings and fixes

| ID | Severity | Finding | Fix (reviewer) |
| --- | --- | --- | --- |
| F-Q5-1 | **Real (data integrity)** | The quota editor sent a row for **every** usable model on save. Each untouched model got a permanent `enabled=false, monthly_limit=0` row plus a `qta.group_quota_updated` audit event saying the admin configured it. Quota rows are never deleted. | `qta.mjs`: send a model only if it already has a rule, or is enabled, or has a limit or threshold; an empty payload shows a message instead of calling the API. `test_qta.py` now asserts the specialist group stores **only** the configured model. |
| F-Q5-2 | Medium (UI race) | `loadUserDetail` and `loadBudget` had no stale-response guard: clicking user A then B (or switching month) quickly could let A's slower response render under B's selection, with A's suspend/restore buttons. | Per-panel load counter: only the newest request may render (both the success and error paths). |
| F-Q5-3 | Test gap vs prompt §5 | FR-QTA-010 AC2 (missing decision number → not saved) and FR-QTA-040 AC3 (missing reason or *Người ra lệnh* → not suspended) were not browser-tested. The traceability rows claimed UI verification anyway. | Added both negative checks to `test_qta.py` (the dialog stays open, the empty field is invalid, nothing is recorded). The traceability claim is now true. |
| F-Q5-4 | Nit | Inactive quota rules were identified as "missing from the first 100 models" instead of by the server's `model_active` flag. | Now uses `rule.model_active === false`. |
| F-Q5-5 | Report | Required §5 (FR acceptance table) and §10 (implementer's review of the plan and prompt) are missing. Q-g was paraphrased, and Q-h (sidebar regrouping) was replaced by a different question, so it is unanswered. §7 is a useful addition. | Recorded here; Q-h carries to Q6. |

Wording nits for Q6 polish (not fixed):
- The access badge shows the raw code ("Không có hạn mức (NO_ENTITLEMENT)").
- The account state and quota status columns both read "Đang hoạt động", which is ambiguous next to each other. "ĐÃ CẮT" was requested; "Đang tạm ngưng" counts as "tương đương" under the FRD.
- Role-holder test contexts do not set `timezone_id`. This is harmless today because no test sets an expiry, but it matters if one is added.
- `seed_mdl_models` inserts an active EXTERNAL provider through the schema owner without an agreement — acceptable test fixture data, but state that it bypasses MDL rules.

### 11.4 Response to §8 answers

- **Q-g (actor names):** Agree with Neon. If people later need to see names, a single server-side read join is better than having the browser look up each person one by one. Schedule it for Q6 together with MDL's `changed_by`, or leave it as is — this is a PO decision, since it changes the API.
- **Q-h (sidebar regrouping):** Not answered. It carries to Q6: the regrouping would touch `app.mjs` navigation and the existing navigation tests, so it is a PO cosmetic choice, not an acceptance requirement.
- The observations on `/qta/models?limit=100` (page cap) and the past-month budget view are accepted as Q6 checklist items.

### 11.5 Carried forward to Q6

- **From the Q4 review:**
  - `FOR SHARE` on `AccountGroup` (after a lock-order check).
  - Scheduler runbook with an explicit `Asia/Ho_Chi_Minh` time zone.
  - CRT must take the `52001` budget lock (Phase 5 note).
  - Optional template-database fixtures.
- **From the Q5 review:** the wording nits above, the Q-g/Q-h PO decisions, and pagination for the quota matrix if a catalog can exceed 100 models.
- **Already in the plan:** the FR-MDL-020 AC3 cross-module proof, the populated `0006 → 0008` upgrade plus backup/restore rehearsal, and `qta-handoff.md`.
