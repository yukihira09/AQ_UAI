# AQ EduUAI — Source-Code Audit and Backend Readiness Baseline

**Audit date:** 19 November 2026  
**Source of truth:** User-uploaded `aq_uai.zip` (current full codebase)  
**Requirements:** Handover dated 17 November 2026; `AQ-FRD-UAI-MDL-001`, `AQ-FRD-UAI-QTA-001`, `AQ-FRD-UAI-CRT-001` (all v1.0, draft)  
**Status:** Frontend/browser-only working prototype; **not** a production application; no FRD Must item should be certified solely from the demo.  
**Method:** ZIP inventory; read all HTML/JS, core documentation, CSS responsive and updated sections, screenshot assets; Node `--check` on every JS file; executable Node VM state/logic tests. Attempted Chromium navigation was blocked by environment policy, so no fresh live-browser acceptance claim is made.

## 1. Audit scope / what is actually in the ZIP

- 32 ZIP entries including directories; 6 JavaScript files, 4 CSS files, 1 HTML entry point, 4 Markdown docs, 10 PNG screenshot/preview assets.
- `index.html` loads, in order: `shared/core.js` → `module1/module1.js` → `module2/module2.js` → `module3/module3.js` → `shared/dialogs.js` → `shared/actions.js`. CSS is loaded from shared/base and all three modules.
- There is no `package.json`, server project, test framework, database migration, API client, secrets management, Git history, or actual model invocation code.
- Root `README.md` describes the current work as a browser-only frontend demo and records a “v4” visual update. Later button and typography selectors appear in the CSS, but without a version history it is **not possible to certify** which prior v5/v6 patches were merged.
- Contents of `docs/screenshots/` are historical screenshots, not newly captured evidence from this environment.

### Map of the implementation

| Component | Function in current code | High-relevance lines |
|---|---|---|
| `shared/core.js` | `defaultData()`, localStorage persistence, shared entities, `totals()`, `getQuota()`, shell rendering | 6–100 |
| `shared/actions.js` | Delegated click/form/change/input handling; mutations; CSV export; mock reset/sync | 1–193 |
| `shared/dialogs.js` | Forms for model, provider, group, sync, school budget, suspend, grant, reclaim, reset | 1–73 |
| `module1/module1.js` | Model catalog, filtered grid/table, model routing, DPA record table | 1–80 |
| `module2/module2.js` | Group/model quotas, individual additive breakdown, suspension and reset event UI | 1–129 |
| `module3/module3.js` | KPI dashboard, individual recipient list, ledger, reference role defaults | 1–125 |
| `module1/module1.css`, `module2/module2.css`, `module3/module3.css` | Visual reconstruction and responsive layouts | Entire files |
| `shared/base.css` | Global shell/sidebar/tables/forms/modals | Entire file |

## 2. Actual data model and state flow

### Stored state

`let db=loadData()` loads a single JSON document from browser `localStorage` under key **`aq_uai-demo-v1`**. Seed state includes:

- `providers`: 4 (three illustrative external providers + one on-premise provider).
- `models`: 8 (including 4 models whose IDs are hardcoded into Module 2 summaries).
- `route`: primary/backup model IDs, and `routeHistory` as locally appended text snapshots.
- `users`: 6 sample identified people, with `id`, staff/student `code`, name, unit, and other display attributes.
- `groups`: 6 (four `Hệ thống`, two `AI chuyên biệt`), with `members` arrays and `quotas` keyed by model ID.
- `tokenUsed`: synthetic per-user/per-model consumption.
- `schoolBudget`: one amount/decision/date object; nominally a monthly budget.
- `suspensions` and `events`: simple arrays tracking browser-demo status/actions.
- `creditBase`, `creditUsed`, `ledger`, `epoch`: a **separate credit accounting simulation**.
- Optional `defaultCreditPolicies`: per-role reference values saved by Module 3's policy UI; **not applied** to balances or group/model entitlements.

`ui` is in-memory interaction state (page, active tab, selected user, search/filters, modal, sidebar); it is not stored as part of the `db` record.

### Actual arithmetic

**Module 2:** `getQuota(userId, modelId)` sums each positive `group.quotas[modelId]` for groups containing that user. It does not implement an active-group eligibility filter, and the lookup UI only iterates the four hardcoded IDs in `quotaModelIds`.

Example from the code: user `u1` / `NS001`:
- GPT-4o 2,000 + 5,000 + 10,000 = **17,000 tokens**.
- Gemini 5,000 + 10,000 + 25,000 = **40,000 tokens**.
- Claude 3,000 + 15,000 = **18,000 tokens**.
- DeepSeek 10,000 + 20,000 + 50,000 = **80,000 tokens**.

**Module 3:** `totals(userId)` computes current demo credit balance as `max(0, base + grants − reclaimed − used)`. Grants/recoveries are summed only for ledger entries whose `epoch` equals the current `db.epoch`. `creditUsed` is included only for the initial `epoch===0`; thereafter usage is treated as 0. A school budget is checked against the sum of per-person `base + grants − recovered` in **credits**, not against cumulative token/model entitlements.

For seeded `u1`: 500,000 base + 1,500,000 granted − 820,000 used = **1,180,000 available credits**. The recipient table's `TỔNG KHẢ DỤNG` column actually prints *gross before consumption*, not remaining balance; label requires PO confirmation.

**No tokens-to-credits conversion** or cross-module accounting bridge exists or has been approved. It would be incorrect to treat the sample `creditBase` as derived from the Module 2 quotas.

### Mutation and UI workflow

Actions in `shared/actions.js` mutate `db` directly, call `save()`, then `render()`. `render()` replaces the app's HTML string with the appropriate module renderer and optional modal. Most navigation and actions use `data-action`; form handlers dispatch on form `id`. All protection is frontend-only. **Browser localStorage is not an append-only or tamper-resistant ledger.**

## 3. FRD traceability (33 requirement IDs)

**Legend:** “Demo” means a UI/browser-only behavior exists; “Partial” means some constraint/flow is unimplemented or inconsistent; “No backend” means there is no production enforcement. **None of the rows constitutes an FRD acceptance pass.**

### MDL — provider/model management (9 IDs)

| FR ID | Source implementation | Assessment / backend obligation |
|---|---|---|
| MDL-001 | Module 1 catalog/forms | Demo; no identity or RBAC, including write permissions. |
| MDL-010 | Provider form, DPA table | Demo provider create/update and endpoint; no secure secret storage or connection credentials. |
| MDL-011 | Model form | Demo model details, provider link, capability, max output; no assistant system prompt; includes an extra `temperature` field needing requirement review. |
| MDL-012 | `toggle-model` | Blocks deactivation when selected as primary or backup; does not check other mandatory references and has no server-side lifecycle/history protection. |
| MDL-020 | `test-model`, `test-model-draft` | Simulated success, no HTTP request, no fixed test payload or authenticated provider health result; no quota deduction in demo. |
| MDL-021 | Routing tab, `route-form`, `routeHistory` | Basic primary/backup checks and textual local history; no real router/failover; no durable audit/versioning. |
| MDL-030 | DPA fields + pretest checks | Demo gates for external providers; DPA status can become stale after approval withdrawal; genuine agreement validity not verified. |
| MDL-031 | Model `risk` select | 3-level manual classification exists as sample; no legal/evidence validation workflow. |
| MDL-040 | Model screen lacks assistant prompt | Potential ambiguity: a model-level `Temperature` input remains despite the FRD's exclusion of assistant creativity configuration. Confirm with PO. |

### QTA — group/model quotas (12 IDs)

| FR ID | Source implementation | Assessment / backend obligation |
|---|---|---|
| QTA-001 | Module 2 open to everyone | No RBAC or scoped read/write authorization. |
| QTA-010 | School-budget modal | Month-only UI + decision number/date; one shared mutable budget object, not persisted monthly periods. |
| QTA-011 | Budget validation in `budget-form` | Compares credit-based `totalAllocated()` with school budget, **not** model quotas/groups or institution/unit allocation books. Accounting contract unresolved. |
| QTA-020 | `sync-groups`, `confirm-sync` | Adds synthetic `G_BGH` group while preserving specialized groups; no product-directory integration, delta detection, or sync provenance. |
| QTA-021 | Group form quotas keyed per model | Quota editing for active models exists; table and personal lookup are restricted to four hardcoded model IDs, so newly created models lack full QTA display coverage. |
| QTA-022 | Group creation / member checkboxes | Specialized groups supported in local data; cannot establish identity/group integrity without server directory. |
| QTA-030 | `getQuota()` | Correct additive arithmetic on seeded records; does not exclude inactive groups; needs eligibility and temporal policy decisions. |
| QTA-031 | `quotaLookup()` | Per-user membership/breakdown and simulated usage UI; missing real user scopes, metering and enforcement. |
| QTA-032 | `confirm-reset` | Demo increments `epoch`, excludes old credit grants, appends an event; **does not reset `tokenUsed`**; no 00:00 scheduler, calendar period, idempotent reset, or durable refresh ledger transaction. |
| QTA-040 | Suspend form | Captures scope, ordered by, reason, optional until; records a flag + event; no actual AI request denial, scope enforcement or expiry processing. |
| QTA-041 | `restore` | Browser state change with event; no added quota; no server enforcement/reconciliation. |
| QTA-050 | Fixed month and no edit/delete ledger UI | Appears to respect the UI prohibition; direct localStorage changes can rewrite or erase any ledger record. |

### CRT — individual grant and recovery (12 IDs)

| FR ID | Source implementation | Assessment / backend obligation |
|---|---|---|
| CRT-001 | Unrestricted Module 3 actions | No RBAC or institution/unit delegation. |
| CRT-002 | Buttons/form labels | Uses internal grant/reclaim language, no fintech wallet/top-up flow. |
| CRT-010 | `grant-form` person picker | Only identified users selected; sample identity is hardcoded and not matched to active system accounts. |
| CRT-011 | Required `doc` | Decision/tờ trình field validated; fund is reference text; approval source is not authenticated or validated. |
| CRT-012 | Month label, `epoch` | Month-only display; simulated reset but no actual calendar-month expiry or scheduled service. |
| CRT-013 | `schoolBudget.amount-totalAllocated()` | Rejects over-budget grant in demo; missing scoped delegated budgets, reconciled ledger and transactional race protection. |
| CRT-020 | Reclaim eligible user list | Only users with positive calculated balance; no actual account lifecycle. |
| CRT-021 | Reclaim form | Autofills full balance, permits partial recovery, rejects excess in demo. |
| CRT-022 | Required `doc` for reclaim | Browser validation and ledger annotation; no verification of decision authority. |
| CRT-030 | `db.ledger.push` and derived balance | Append operations exist in UI, but JSON/localStorage is user-editable, no atomicity, locking, idempotency or true immutability. |
| CRT-031 (Should) | Not implemented | No automated recovery on inactive/left-school account. |
| CRT-040 | No payment/extra cycle UI | Consistent with prototype boundary; production operations still absent. |

## 4. Executable verification

### Performed

1. `node --check` on each of 6 JS files: **6/6 PASS** (syntax only).
2. Executed a controlled Node `vm` harness loading all six JS files in browser script order with stubbed DOM and localStorage, verifying render string generation and state functions: **18/21 PASS**.
3. Verified initial seed data, expected per-model group addition, grant/reclaim ledger entry creation, balance arithmetic, over-reclaim rejection, local persistence, simulated epoch advancement and credit grant exclusion.
4. Read CSS responsive breakpoints and available historical screenshots, but could not certify fresh live visual behavior.

### Failed logic checks (verified against the submitted code)

| Check | Expected | Observed | Source |
|---|---|---|---|
| QTA monthly reset clears current usage | New period must not inherit previous period usage | `tokenUsed.u1.m_gpt` remains **5,950** after reset, while `epoch` increments | `shared/actions.js:78-81`; `shared/core.js:49`; `module2/module2.js:88` |
| Inactive group no longer grants its quota | Conditional on group inactive semantics being a true access suspension | After setting `G_GV.active=false`, `u1` GPT group quota remains **17,000** rather than 15,000 | `shared/core.js:73,84-86`; `module2/module2.js:28-31` |
| DPA status updates after agreement/approval is withdrawn | Status should reflect latest DPA data | With `p_openai` document cleared and approval revoked, `dpaStatus` remains **“Đang hiệu lực”** | `shared/actions.js:115`; `module1/module1.js:57-59` |

The second check has an **open business-semantics dependency**: the FRD establishes a group status/list but does not define every consequence of setting a group inactive. It is a likely implementation inconsistency, not a certified contractual defect until the status meaning is established.

### Not performed

Fresh Chromium browser navigation failed with `ERR_BLOCKED_BY_ADMINISTRATOR` for local HTTP and `file://` URLs in this environment. Therefore, **no new browser visual, accessibility, responsive overflow or download test is claimed**. The ZIP includes its own screenshots and documentation about previous tests; these are supplied historical artifacts, not independently repeated tests.

## 5. Additional critical observations

1. **Fixed four-model view:** `module2/module2.js:5` defines `quotaModelIds` as GPT/Gemini/Claude/DeepSeek. `shared/dialogs.js:40` permits quotas for all active models. A newly added active model can be configured but does not appear in the current group chips or personal quota table.
2. **Temporal accounting split:** `db.epoch` is an integer, not a `YYYY-MM` key. Reset can run repeatedly in the same calendar month, while the month label still displays the actual current date. The simulated credit usage condition (`epoch===0`) is not a period-aware usage ledger.
3. **Gateway DPA reconciliation:** Editing a provider's agreement can invalidate eligibility while leaving an existing primary/backup route assigned. Production routing must re-evaluate the policy and block invalid use even if configuration records become stale.
4. **DPA compliance claims are synthetic:** The UI includes official-looking DPA record numbers and legal references. None of those records is verified evidence of a real contract. Legal wording and current statutes should be validated with PO/legal before deployment.
5. **Suspension only changes presentation:** `isSuspended()` checks a boolean flag; it does not consider `until` or selected external-only scope when authorizing a request because there are no real requests.
6. **Recipient table semantics:** The column `TỔNG KHẢ DỤNG` is computed from `base + grants − revoked`, without subtracting usage. The reclaim modal uses the *remaining* `balance` correctly. Recommend distinguish “gross assigned” from “available remaining”.
7. **No real account lifecycle:** User/group data and role descriptions are samples, and `creditCategories` maps `u1`…`u6` to illustrative contextual labels. Need real ID references and unit scope from Dev framework.
8. **Saved credit policy cards are non-operative:** `defaultCreditPolicies` affects only reference UI; it does not modify token allocations or balances. Do not convert these cards into authoritative policies without business approval.
9. **Model configuration validation is browser-only:** `model-form` uses `novalidate`, and handler has incomplete numeric/domain checks. Backend must revalidate every field and secret handling on every mutation.
10. **Navigation history:** `updatePage()` updates location hashes but there is no `hashchange` handler to keep `ui.page` in sync with browser Back/Forward. This is a frontend follow-up, not a blocker to backend domain design.
11. **Data migrations:** `loadData()` minimally checks for arrays but does not migrate schema between prototype versions. Avoid importing raw localStorage blobs as production records.
12. **No cost authority:** No real usage metering, model-price table, audited token accounting or credit exchange policy. Numeric demo values must not determine live charges or limits.

## 6. Backend implementation boundary and proposed domain split

### What can be reused

- Existing Vietnamese UI structure and module-specific CSS.
- Form field names and visible workflows as an initial frontend integration reference.
- Models of the relationships: provider → model; group ↔ person; group × model quota; person × period ledger; school budget by period; model route/history.
- UI acceptance journeys and FRD IDs as the test-plan foundation.

### What must not be reused as authoritative production logic

- `db` / localStorage as source of truth.
- `uid()` and demo `epoch` as server identity/period design.
- Client-only validation and `dispatch()` as authorization.
- `tokenUsed`, `creditUsed`, `creditBase` seed values, fabricated DPA contracts, or role-default policy values.
- “Test connection success” simulation.
- Role/action identity string `Admin demo`.

### Proposed backend services (design recommendation, not an existing implementation)

1. **Identity/RBAC adapter** to the product framework's users, user groups, organizational units, privileges, and account status. Resolve authorization on the server for every read/write and unit-scoped operation.
2. **Provider/model registry** with encrypted credentials and secret references, agreement metadata, risk labels, tested state + test execution records, active status, and primary/backup routing versions.
3. **Month/entitlement engine** with explicit `YYYY-MM` periods, group/model assignments, membership snapshots or a policy to resolve historic memberships, additive entitlements, usage accounting, suspension decisions, and idempotent month rollover.
4. **Credit/grant ledger** with immutable transaction IDs and server-computed balances, documentary basis, actors, atomic budget reservations, and append-only reversal/adjustment records. Clarify the credit↔token contract before integrating Module 2 and CRT.
5. **Audit and integration layer** for model tests, gateway usage, policy changes, and future EduSmart products, including tenant/school scope as applicable.

### Candidate entities (not yet approved database design)

`User`, `OrganizationUnit`, `AccountGroup`, `GroupMembership`, `AIProvider`, `ProviderCredentialReference`, `DataProtectionAgreement`, `AIModel`, `ModelTestRun`, `GatewayRouteVersion`, `MonthlyBudget`, `GroupModelMonthlyQuota`, `Suspension`, `MonthlyUsage`, `QuotaLedgerTransaction`, `AuditEvent`, `MonthlyResetExecution`.

**Non-negotiable engineering properties:** server-side validation, RBAC, atomic ledger + budget updates, transactional concurrency control, idempotent commands, period-specific accounting, no hard deletes of financial history, audit actor/identity from authenticated context, secret masking, and replay-safe usage metering.

## 7. Decisions to obtain before implementing real quota accounting

1. **Unit of account:** Are `credits` an independent institutional budget unit or derived from provider/model token costs? If converted, confirm rates, input/output token treatment, provider differences, rounding, and versions.
2. **Budget invariant:** Is school “total allocation” based on per-person *effective* entitlement (which duplicates pooled group assignments), a pool reservation per group/model, actual credit ledger commitments, or separate institution/unit and user books?
3. **Group status:** Does an inactive group immediately cease to grant quota? What happens to quotas already used and to member access during a period?
4. **Model availability:** Should every active model be allocatable by QTA, or is there an explicit subset of quota-managed models?
5. **Month boundary:** Timezone, period identification, reset idempotency, carryover prohibition, history preservation, handling of changes to group membership mid-month.
6. **DPA governance:** Actual minimum evidence/approval, expiry semantics, and whether agreement change mandates re-testing/automatic route removal.
7. **Account framework:** Actual user/group/unit schema, authentication flow, permission codes and Tech Lead's intended framework repository.
8. **Gateway scope:** Whether real provider calls are required in phase one beyond the FRD `Test Connection` action, and which connection protocols must be supported first.
9. **FRD versus prototype extras:** Whether model-level `temperature` and Module 3 role-default cards are sanctioned, given the written FRD boundaries.

## 8. Suggested implementation order

- **Stage 0 — Architecture integration:** Acquire Tech Lead's real product framework; map user identity, organizational scopes, authorization, backend stack, database and deploy conventions. Build contract tests for 33 FR IDs.
- **Stage 1 — MDL vertical slice:** Real provider/model CRUD, vault or encrypted credential storage, DPA gating, model risk, real fixed-payload connection test, route assignment/history, RBAC and audit. Preserve Module 1 visuals while replacing demo state with APIs.
- **Stage 2 — QTA vertical slice:** Model-aware group allocations (all eligible models, not fixed four), real account group sync, additive entitlements, person lookup, suspension enforcement, monthly reset/rollover and institution budget constraints once unit/budget semantics are agreed.
- **Stage 3 — CRT vertical slice:** Verified person identity and approval documents, grant/reclaim transaction endpoints, immutable ledger, default-full/partial reclaim, concurrency/idempotency and delegated authorization.
- **Stage 4 — End-to-end hardening:** Cross-module consistency, multi-user access, ledger invariants, negative/overflow cases, reset races, DPA expiration, auth bypass tests, audit export and acceptance demonstration.

## 9. Audit verdict

**Frontend state:** A substantial, coherent, screenshot-led vanilla JS prototype of three related administration modules, including working calculation/interaction patterns. **Backend state:** Not started in the inspected archive. **Production acceptance:** Not demonstrated. **Recommended next move:** integrate Module 1 with the actual Dev product framework and obtain the minimal backend architecture information, while treating the outstanding unit-of-account and school budget invariants as design blockers for financial enforcement—not blockers for building secure model registry endpoints.

**Codebase preservation:** No file inside the user-supplied ZIP was modified. Analysis/testing scripts were created separately under `/mnt/data/aq_uai_review/`, and this report is a distinct deliverable.
