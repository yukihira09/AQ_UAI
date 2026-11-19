# Screenshot mapping for Module 2 + Module 3 (v4)

| Reference screenshot | Implemented section | Code |
|---|---|---|
| Module 2: Bảng chi tiết hạn mức cộng dồn | Compact table inside personal lookup tab | `module2/module2.js` (`quotaLookup`), `module2/module2.css` (`.qta-audit-table`) |
| Module 3: Danh sách Đối tượng Cấp Mở rộng | Four KPI cards, filters, recipient table | `module3/module3.js` (`renderCredits`, `creditRecipients`) |
| Module 3: Sổ cái Lịch sử Phân bổ | Compliance banner, append-only-style table | `module3/module3.js` (`creditLedger`) |
| Module 3: Định mức Tiêu chuẩn Mặc định | Four editable policy cards | `module3/module3.js` (`creditDefaults`) |

Shared state and actions: `shared/core.js`, `shared/actions.js`; modal forms: `shared/dialogs.js`.

**Important:** Screenshots illustrate an interface; implemented flows are browser-local examples only. Data values should not be interpreted as official AQ policy or evidence that backend FRD acceptance criteria have been met.
