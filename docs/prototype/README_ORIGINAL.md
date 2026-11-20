# AQ EduUAI — Frontend starter (Module 1 + Module 2 + Module 3)

A small Vietnamese-language frontend learning prototype, organized by module. It is **not** a production service. It has **no backend APIs, authentication, database, actual LLM connection, credential storage, or automatic scheduled quota reset**. All demo data is synthetic and persisted in the browser's `localStorage`.

This project combines earlier Module 1 work (model catalog, Add/Edit Model dialog, gateway routing tab, DPA legal-record tab) with newly reconstructed Module 2 screens (six-group quota table and per-user cumulative quota audit). Module 3 is now screenshot-aligned across its recipient, audit-log, and default-policy views, with browser-only grant/reclaim interactions.

## 1. Run on Linux (no npm packages required)

After downloading and extracting the ZIP:

```bash
cd aq_uai
python3 -m http.server 8000
```

Open in your browser:

- **Module 1:** http://localhost:8000/#module1
- **Module 2:** http://localhost:8000/#module2
- **Module 3:** http://localhost:8000/#module3

Navigate between modules with the sidebar (use the ☰ icon to reveal or collapse it). Quit the local server using `Ctrl+C`.

To open the code in VS Code: `code .`

> You MUST serve the folder from `aq_uai/` because `index.html` references `shared/` and each module by relative paths. Don't open `module2/module2.js` as a webpage.

## 2. Project layout

```text
aq_uai/
├── index.html                  # Loads all CSS/JS files in the correct order
├── shared/
│   ├── base.css                # Common layout, sidebar, tables, forms, dialogs
│   ├── core.js                 # Synthetic data, shared state, lookup/calculation helpers, app shell
│   ├── dialogs.js              # Model, group, quota, grant/reclaim form dialogs
│   └── actions.js              # Navigation, user events, form handling, local demo mutations
├── module1/
│   ├── module1.css             # Screenshot-based Module 1 styling
│   └── module1.js              # Model catalog, routing, DPA screen
├── module2/
│   ├── module2.css             # New screenshot-based Module 2 styling
│   └── module2.js              # Group quota table and cumulative individual lookup
├── module3/
│   ├── module3.css             # Screenshot-based Module 3 responsive styling
│   └── module3.js              # Credit dashboard, recipients, ledger, default policies
└── docs/
    ├── IMPLEMENTATION_STATUS.md
    ├── MANUAL_TESTS.md
    └── screenshots/
        ├── module1-dpa.png
        ├── module2-groups.png
        └── module2-lookup.png
```

The `shared/` folder is intentional: all three modules use the same navigation, synthetic records, form helpers, and browser events, so those components are defined once.

The project intentionally uses browser-native `<script>` loading with no build step, transpiler, or frontend framework. Shared function/state declarations are loaded first; per-module renderers are loaded next; shared dialogs and delegated events are loaded last. **Preserve script order in `index.html`.**

## 3. What works in the demo

### Module 1 — Cấu hình Nhà cung cấp & Mô hình AI
- Search/filter model catalog, switch between grid/list view, add/edit model details.
- Demo connection-test status and primary/backup routing constraints.
- DPA legal-agreement table with synthetic records and editable provider details.
- API key field is visual-only: no real secrets are stored or transmitted.

### Module 2 — Hạn mức AI theo Nhóm tài khoản
- Six illustrative groups (system groups and specialized AI groups), model-specific quotas, source and status filters.
- Create/edit groups and memberships, edit model quotas, demonstrate group synchronization without deleting specialized groups.
- Per-person lookup with actual **sum across all groups for each model**. Example: `NS001` has `2,000 + 5,000 + 10,000 = 17,000` GPT-4o tokens and `5,000 + 10,000 + 25,000 = 40,000` Gemini tokens.
- Synthetic model usage progress bars. Demo suspend/restore status and a manual month reset action.
- School-wide monthly budget modal remains accessible below the Module 2 screens.

### Module 3 — Cấp / Thu hồi Hạn mức
- Demo supplementary grants and partial/full reclaim, required decision references, balance checks, and a browser-local read-only ledger.
- CSV export for the synthetic ledger.
- **Credits are deliberately not converted into Module 2 tokens**; no conversion policy has been approved.

## 4. Important non-production limitations

- `localStorage` can be edited by the user and does not provide security, immutability, or transaction guarantees.
- No authentication/authorization (RBAC), real synchronized user directory, API calls, or persistent server database.
- Provider tests, AI usage counts, synchronization, and monthly reset are simulated in the browser.
- Real business rules (token ↔ credit conversion, institutional allocation and ledger source-of-truth) require PO/Tech Lead decisions before implementing backend accounting.
- Styling is a close visual recreation, not a pixel-perfect copy. The UI has been tested at a large desktop viewport; smaller screens rely on responsive tables that may scroll horizontally.

## 5. Where to edit next

- Module 1 page/UI: `module1/module1.js`, `module1/module1.css`.
- Module 2 page/UI: `module2/module2.js`, `module2/module2.css`.
- Module 3 page/UI: `module3/module3.js`, `module3/module3.css` (currently uses common styles).
- Shared dialogs: `shared/dialogs.js`.
- Synthetic data, quotas and other shared functions: `shared/core.js`.
- Button actions and form validation: `shared/actions.js`.

To reset demo data manually, open your browser DevTools → Application/Storage → Local Storage, delete `aq_uai-demo-v1`, then reload. **This clears only this demo site's sample state**, not company data.

## 6. Update: Compact Module 2 audit + redesigned Module 3 (v4)

**Module 2:** the individual model-by-model cumulative quota table uses proportional column widths and wraps long formulas, rather than forcing a 1190px minimum table width. Switching to the individual audit tab automatically collapses the sidebar to give the table more room (you can reopen it). At narrow/mobile widths the table switches to stacked row cards rather than introducing horizontal scrolling. The seeded examples for NS001 are GPT-4o **17,000**, Gemini **40,000**, Claude **18,000**, and DeepSeek **80,000** tokens per month.

**Module 3:** the three prototype tabs are reconstructed with larger text and styles isolated in `module3/module3.css`:

1. **Danh sách Đối tượng Cấp Mở rộng**: four summary cards, search/category/status filters, a nine-column responsive table, progress bars, sample recipient context, and per-recipient grant/reclaim buttons.
2. **Sổ cái Lịch sử Phân bổ (Audit Log)**: a compliance banner, append-only-looking ledger, colored transaction badges, decision references, audit actor, notes, and CSV demo export.
3. **Định mức Tiêu chuẩn Mặc định**: four editable role-based allowance cards, a `Lưu quy chế` button storing browser-local reference values, and explicit clarification that those settings do not yet affect the real quota accounting model.

All three module pages use one shared application shell (`shared/`), and Module 1 is retained. Browser demo operations still use `localStorage`; this is **not a secure ledger** or real billing implementation. Tokens and credits are **not automatically converted**. Seeded figures may differ from reference screenshots because the demo totals are computed from the sample records instead of hardcoded dashboard values.

If you have used an earlier version of this starter, your browser may retain its earlier synthetic records. To see the new example values, use the demo reset control if accessible, or delete this local site's `aq_uai-demo-v1` key in the browser's local storage. This deletes only your locally saved demo changes.
