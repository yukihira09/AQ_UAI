# FRD-to-frontend progress (demo only)

| Document | Visible sample UI | Interactions implemented as browser demonstration | Missing production implementation |
|---|---|---|---|
| AQ-FRD-UAI-MDL-001 | Model cards/list, provider/model form, gateway routing, DPA agreement table | Search, filtering, model edits, simulated tests, role checks, DPA metadata | Auth/RBAC, secure API secret storage, real provider connectivity, server-side audit and history |
| AQ-FRD-UAI-QTA-001 | Six-group quotas, source/status filters, personal lookup with group contributions, consumption bars | Group edits, AI group creation, simulated sync, additive quotas, suspension state, monthly reset simulation | Server-side group sync, institution-wide accounting reconciliation, actual model-usage authorization, 00:00 scheduler, immutable audit |
| AQ-FRD-UAI-CRT-001 | People/allowances, grant & reclaim forms, history table | Grants, reclaim validation, demo balances, CSV export | Persistent append-only ledger, transactional/concurrency safety, real institution-level budget/credit conversion, RBAC |

**Do not mark FRD Must items as fully accepted based on this frontend demo.** Matching a screenshot is not proof of server-side behavior or data integrity.

## Architecture reminders
- Use `shared/core.js` for synthetic records/relationships. Avoid defining duplicate users/models in each module.
- `shared/actions.js` processes click/change/submit events across modules.
- HTML templates escape synthetic display strings using `esc()`.
- The visual DPA sample documents are not verified legal agreements.
- `tokenUsed` and the `creditUsed` / ledger values intentionally represent *different*, unconverted demonstration units.

## Visual update v4 (2026-11-19)

- Module 2: personal cumulative quota table is proportional-width and no longer requires horizontal scroll. The lookup tab automatically collapses the sidebar. Seed examples match all four totals shown in the latest user screenshot (17k / 40k / 18k / 80k tokens).
- Module 3: reconstructed all three prototype tab layouts, including four KPI cards, recipient filters, legible tables, append-only-style ledger with CSV export, and four default quota policy cards. The role policy save action is browser-local and **does not modify actual allocations**.
- Tests: syntax checks and Chromium browser tests for tab navigation, filters, grant, ledger addition, local policy saving, and no horizontal overflow at 1600 / 1366 / 1024 / 800 / 600 widths. Existing Module 1 DPA table still loads.
- Still not implemented: server-side permissions, durable database, real API connections, secure credentials, transactional or tamper-proof ledger, usage metering and actual scheduled resets.
