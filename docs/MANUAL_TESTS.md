# Manual regression checklist (browser-only)

Open `http://localhost:8000/#module2` after starting the server in the project root.

## Modules and shared shell
- [ ] Sidebar navigates between Modules 1, 2 and 3.
- [ ] The ☰ button collapses/expands the sidebar.
- [ ] Module 1 still shows its model catalog, Add Model dialog and DPA tab (three example agreement rows).
- [ ] Module 3 still shows grant/reclaim recipients and the ledger.

## Module 2 — group quota table
- [ ] Group tab shows **six** demo groups.
- [ ] The first row is `G_GV`, with GPT-4o 2.000 tok, Gemini 5.000 tok, Claude disabled, DeepSeek 10.000 tok.
- [ ] Search by `G_GV` filters to one group; clearing search restores six.
- [ ] Filter for specialized AI groups displays `AI_NCKH_GENOM` and `AI_LAB`.
- [ ] Editing a group and saving a quota updates its displayed chips.
- [ ] Add a specialized AI group and assign a member. It appears in the list and in that user's lookup.
- [ ] Sync Groups shows a demo synchronization workflow and doesn't remove AI-specific groups.

## Module 2 — personal audit
- [ ] Select `TS. Nguyễn Văn A (NS001)`.
- [ ] The person belongs to groups `G_GV`, `G_QLCT`, and `AI_NCKH_GENOM`.
- [ ] GPT-4o is `2.000 + 5.000 + 10.000 = 17.000` tokens.
- [ ] Gemini 1.5 Pro is `5.000 + 10.000 + 25.000 = 40.000` tokens.
- [ ] Usage bars show synthetic consumed values, including 5.950 GPT-4o tokens at 35%.
- [ ] Click `Cắt / Dừng Hạn mức Ngay`, enter authority and reason, save: state becomes suspended.
- [ ] Click `Khôi phục`: state becomes active again without granting extra allowance.
- [ ] Click simulated monthly reset: a demo event appears.

## Limitations / safety
- [ ] Refresh preserves browser-local changes, but this is not server persistence.
- [ ] Do not input real provider API keys or real student information.
- [ ] Do not infer quota-to-credit conversion from synthetic sample values.

## Screenshot layout update tests (v4)

- [ ] Module 2 → Tra cứu & Kiểm toán: 6 columns are visible at desktop width without left/right scrolling, and NS001 shows 17,000 / 40,000 / 18,000 / 80,000 tokens.
- [ ] Module 2 lookup collapses the sidebar automatically; clicking ☰ can expand it again.
- [ ] Module 3 → Danh sách: 4 KPI cards, search, type/status filters, full recipient list, grant/reclaim actions.
- [ ] Module 3 → Sổ cái: ledger records remain read-only; CSV export works; creating a new grant adds a new record.
- [ ] Module 3 → Định mức: four large policy cards appear; updating a value and selecting Lưu quy chế persists that browser-local reference value.
- [ ] At narrower window widths, Module 3 rows reflow into cards; no browser-wide horizontal scrollbar.
- [ ] Module 1 → DPA still displays three example agreements.
