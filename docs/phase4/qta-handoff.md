# QTA handoff (Q6): operations, local update, scheduling and manual acceptance

**Status (2026-11-27):** Phase 4 Stages **Q0–Q6** (Module 2 — *Hạn mức AI theo Nhóm tài khoản*, `AQ-FRD-UAI-QTA-001`) are implemented and technically verified by automated PostgreSQL 18, API, CLI, and Chromium/nginx tests. **Nothing here is formal acceptance**: no Tech Lead, Product Owner, legal, or institutional sign-off is recorded (`docs/acceptance-matrix.md` remains `0/33`). Requirement-by-requirement status: [QTA requirements traceability](QTA_REQUIREMENTS_TRACEABILITY.md).

**Audience:** the developer operating the local `aq-uai-dev` stack, the operator scheduling monthly resets, and the person performing manual acceptance.

---

## 1. What is delivered

- **Admin UI:** **Hạn mức AI theo Nhóm tài khoản** (`http://admin.localhost:8000/#qta`), flat sidebar entry visible to `qta.read` holders (`apps/admin/assets/qta.mjs`), with:
  - School monthly budget header (`GET/PUT /api/v1/qta/budgets`, append-only revision history, 409 deficit/allocated reporting);
  - Tab 1 **Nhóm & Hạn mức** (`#qta` / `#qta/groups`, group detail `#qta/groups/<uuid>`, directory sync + sync-run history, `AI_SPECIALIST` create/rename/activate/deactivate/members, per-model monthly quota editor);
  - Tab 2 **Tra cứu cá nhân & tạm ngưng** (`#qta/lookup`, exact two-month current/next selector, searchable scoped user picker, live additive group breakdown, honest `"Chưa tích hợp đo tiêu thụ thực tế"` state, individual kill-switch & restore dialogs with distinct read-only *Người thực hiện* vs editable *Người ra lệnh*, append-only suspension history; UNIT-scoped viewers see **only** this tab with zero 403 calls);
  - Tab 3 **Lịch sử & Làm mới tháng** (`#qta/ledger`, current-month manual reset simulation, append-only reset history, month-filtered append-only events ledger).
- **Backend API (`/api/v1/qta`, 22 operations across 18 paths):** strict `extra="forbid"` schemas, `Asia/Ho_Chi_Minh` calendar-month period parsing, single `_qualifying_quota_rows` SQL selectable for additive entitlements and institutional allocation, fail-closed `qta.access.check_ai_access`, column-level least-privilege PostgreSQL grants (`0007_qta_access_catalog`, `0008_qta_schema`), and same-transaction typed audit events.
- **Scheduled CLI:** `python -m aq_uai_api.qta.reset` (idempotent current-month marker under `aq_uai_runtime`, zero secrets on stdout/stderr).
- **Stage reports & design docs:** [Architecture](QTA_ARCHITECTURE_AND_DECISIONS.md) · [Open decisions (`PD-Q1..PD-Q6`)](QTA_OPEN_DECISIONS.md) · [ADR-0004](../architecture/ADR-0004-qta.md) · [Q1 review](QTA_Q1_REVIEW.md) · [Q2 report](reports/QTA_Q2_REPORT.md) · [Q3 report](reports/QTA_Q3_REPORT.md) · [Q4 report](reports/QTA_Q4_REPORT.md) · [Q5 report](reports/QTA_Q5_REPORT.md) · [Q6 report](reports/QTA_Q6_REPORT.md).

---

## 2. How code reaches the running stack

See [MDL handoff §2 — How code reaches the running stack (hot reload)](../phase3/mdl-handoff.md#2-how-code-reaches-the-running-stack-hot-reload). The same container layout, read-only `apps/admin` bind mount, API image rebuild (`bash scripts/dev-up.sh`), and automatic `nginx -s reload` apply to QTA.

---

## 3. Updating your existing `aq-uai-dev` stack from `0006` to `0008`

> [!IMPORTANT]
> **Rehearsal scope:** This upgrade path (`0006_mdl_routing_and_styles` → `0008_qta_schema` with populated pre-QTA data) was rehearsed **only** by the automated disposable PostgreSQL test `apps/api/tests/integration/test_q6_qta_upgrade.py` (Stage Q6 §4.2), **not** on the developer's live `aq-uai-dev` stack. The implementing agent did **not** run Docker and did **not** touch `aq-uai-dev`.

Run from the repository root when you are ready to upgrade your local `aq-uai-dev` stack:

```bash
# 1. Back up the database first (read-only; file stays on your machine with mode 600).
umask 077
docker compose --env-file .env -f infra/compose.yaml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > ~/aq-uai-dev-before-qta.dump
chmod 600 ~/aq-uai-dev-before-qta.dump

# 2. Rebuild and run idempotent provision + migrate (0007_qta_access_catalog -> 0008_qta_schema).
#    Keep --demo-provider if you currently run the MDL synthetic demo provider!
bash scripts/dev-up.sh --demo-provider
#    (Or `bash scripts/dev-up.sh` if you are not using the synthetic demo provider.)

# 3. Verify: services up, Alembic at 0008_qta_schema, API ready.
docker compose --env-file .env -f infra/compose.yaml ps -a
docker compose --env-file .env -f infra/compose.yaml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select version_num from alembic_version"'
#    expected: 0008_qta_schema
curl -s http://localhost:8000/api/v1/ready
```

4. Open `http://admin.localhost:8000/`, grant a QTA role (section 4 below), and reload (`Ctrl+Shift+R`) to confirm **Hạn mức AI theo Nhóm tài khoản** (`#qta`) appears and starts with an empty group list before the first sync.
5. Never run `down -v` during an upgrade (it deletes `aq-uai-dev_postgres_data`). To roll back using the step-1 dump, follow [Restore and verify a backup](../phase2/phase2-handoff.md#restore-and-verify-a-backup).

---

## 4. Granting QTA roles (`#users` / `#roles`)

Migrations `0007_qta_access_catalog` and `0008_qta_schema` never assign QTA roles implicitly. `FOUNDATION_ADMIN` and `AI_MODEL_ADMIN` have **zero** QTA access by design.

| Role | Scope allowed | Capabilities | How to grant |
| --- | --- | --- | --- |
| `AI_QUOTA_ADMIN` | Direct user, **Toàn trường (`GLOBAL`)** only | `qta.read`, `qta.manage` (all 3 `#qta` tabs, budget revisions, sync, specialist groups, quotas, kill-switch/restore, manual current-month reset) | Sign in as `FOUNDATION_ADMIN` → **Tài khoản** → pick user → **Cấp vai trò** → `AI_QUOTA_ADMIN`, scope **Toàn trường** |
| `AI_QUOTA_VIEWER` (Board) | Direct user, **Toàn trường (`GLOBAL`)** | Read-only `qta.read` across all 3 tabs and budget header; zero write buttons | Same path → `AI_QUOTA_VIEWER`, scope **Toàn trường** |
| `AI_QUOTA_VIEWER` (Unit Head) | Direct user, **Một đơn vị (`UNIT`)** | Scoped read-only `qta.read` on **Tra cứu cá nhân & tạm ngưng** for users in that exact unit only | Same path → `AI_QUOTA_VIEWER`, scope **Một đơn vị** → pick unit |

*(Verify role definitions at `#roles`; group-level assignments of `AI_QUOTA_ADMIN` and `AI_QUOTA_VIEWER` are refused by both the API and database constraints.)*

---

## 5. Scheduling the monthly reset (`documented, not executed`)

> [!NOTE]
> **Status: documented, not executed.** The CLI `python -m aq_uai_api.qta.reset` was verified directly against disposable PostgreSQL 18 (`aq_uai_runtime`) in Stage Q4 (`test_reset_cli_idempotent_and_no_backfill`, `cli-smoke.log`), **not** via a live host `systemd` timer or `cron` daemon.

### Operational semantics
- Records **only** the current calendar month in `AQ_UAI_INSTITUTION_TIMEZONE` (`Asia/Ho_Chi_Minh`); **never** backfills missed historical months.
- Strictly idempotent (`UNIQUE(institution_id, period_month)`): safe to run multiple times; prints only `recorded=<n> already=<m>` with zero secrets.
- **Zero rollover holds automatically** at `00:00` on day 1 of the new month even if the scheduled job never runs (entitlements, budgets, and events are scoped strictly by `period_month`). Active suspensions survive monthly resets.

### Option A (recommended): Host `systemd` timer with explicit time zone

Create `/etc/systemd/system/aq-uai-qta-reset.service`:
```ini
[Unit]
Description=AQ EduUAI monthly QTA reset marker
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/path/to/aq_uai
ExecStart=/usr/bin/docker compose --env-file .env -f infra/compose.yaml exec -T api python -m aq_uai_api.qta.reset
```

Create `/etc/systemd/system/aq-uai-qta-reset.timer`:
```ini
[Unit]
Description=Run AQ EduUAI monthly QTA reset at 00:05 Asia/Ho_Chi_Minh on day 1

[Timer]
OnCalendar=*-*-01 00:05:00 Asia/Ho_Chi_Minh
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with `sudo systemctl daemon-reload && sudo systemctl enable --now aq-uai-qta-reset.timer` and inspect with `systemctl list-timers aq-uai-qta-reset.timer`.

### Option B: Host `crontab` alternative

> [!WARNING]
> **`CRON_TZ` is NOT honoured by every `cron` implementation** (Debian and Ubuntu's default Vixie `cron` ignores `CRON_TZ`). Before adding a crontab line, check the host time zone with `timedatectl` and choose a host wall-clock time that is **already day 1 in `Asia/Ho_Chi_Minh`** (for example, on a UTC host, `00:05 UTC` on the 1st = `07:05 Asia/Ho_Chi_Minh` on the 1st — never `17:00 UTC` on day 31/28/30):

```cron
# Example for a UTC host (00:05 UTC on day 1 = 07:05 Asia/Ho_Chi_Minh on day 1):
5 0 1 * * cd /path/to/aq_uai && docker compose --env-file .env -f infra/compose.yaml exec -T api python -m aq_uai_api.qta.reset
```

---

## 6. Manual acceptance checklist

**Prerequisites:** stack upgraded to `0008_qta_schema` (section 3); at least 2 active MDL models (one `EXTERNAL`, one `INTERNAL`); accounts for `FOUNDATION_ADMIN`, `AI_MODEL_ADMIN`, `AI_QUOTA_ADMIN` (`GLOBAL`), `AI_QUOTA_VIEWER` (`GLOBAL`), `AI_QUOTA_VIEWER` (`UNIT` on Unit A), plus test users in Unit A and Unit B.

Every `- [ ]` acceptance line of [AQ-FRD-UAI-QTA-001](../frd/AQ-FRD-UAI-QTA-001.md) (25 lines) plus `FR-MDL-020 AC3`:

| # | FR / AC | FRD acceptance criterion | Manual steps in `#qta` / `#mdl` | Expected result | Automated test coverage |
| --- | --- | --- | --- | --- | --- |
| 1 | `FR-QTA-001` AC1 | Không đủ quyền → không sửa được hạn mức nhóm | Sign in as `AI_MODEL_ADMIN` and open `#qta`; sign in as `AI_QUOTA_VIEWER` (`GLOBAL` & `UNIT`) and open `#qta` | `AI_MODEL_ADMIN` has no QTA menu and gets 403 on `#qta`; viewers see zero write/save/sync/suspend buttons | `test_q2_qta_groups.py`, `test_qta.py::test_qta_access_rbac_and_unit_viewer` |
| 2 | `FR-QTA-001` AC2 | Đủ quyền → mở được danh sách nhóm (kể cả trống sau khi chưa đồng bộ) | Sign in as `AI_QUOTA_ADMIN` on a freshly upgraded DB before clicking Sync | **Hạn mức AI theo Nhóm tài khoản** opens cleanly; group list shows empty state (`0 / 0 bản ghi`) | `test_q6_qta_upgrade.py`, `test_q2_qta_groups.py`, `test_qta.py` |
| 3 | `FR-QTA-010` AC1 | Lưu được tổng hạn mức kèm số quyết định | Click **Cập nhật tổng hạn mức tháng**, enter `10000`, `QD-01`, and today's date; save | Header shows **Đã ghi nhận**, `10.000 đơn vị hạn mức`, `QD-01`, and revision `#1` in history | `test_q3_qta_lookup_budgets.py`, `test_qta.py::test_qta_budget_deficit_additive_and_mobile` |
| 4 | `FR-QTA-010` AC2 | Thiếu số quyết định → không lưu | Open **Cập nhật tổng hạn mức tháng**, enter amount, leave **Số quyết định** blank, click save | Dialog stays open with validation error; budget remains unchanged | `test_q3_qta_lookup_budgets.py`, `test_qta.py::test_qta_budget_deficit_additive_and_mobile` |
| 5 | `FR-QTA-010` AC3 | Không có lựa chọn chu kỳ ngoài Tháng trên UI nghiệm thu | Inspect all 3 tabs and dialogs of `#qta` | Only calendar-month controls (`<input type="month">` and 2-month current/next `<select>`); zero Semester/Project/Exam selectors | `test_q2_contracts.py`, `test_q3_entitlements.py`, `test_qta.py::assert_qta_dom_invariants` |
| 6 | `FR-QTA-011` AC1 | Tổng mới < đã phân bổ → từ chối kèm số chênh lệch | With `4.000` allocated, try setting monthly budget to `2500` with `QD-02` | Rejected (`409`); alert displays `4.000 đơn vị hạn mức` allocated, `1.500 đơn vị hạn mức` deficit, and `Mã yêu cầu` | `test_q3_qta_lookup_budgets.py`, `test_qta.py::test_qta_budget_deficit_additive_and_mobile` |
| 7 | `FR-QTA-020` AC1 | Sau đồng bộ, danh sách nhóm hệ thống xuất hiện trên màn hình hạn mức | Ensure a `SYSTEM` group exists in **Nhóm tài khoản**; click **Đồng bộ nhóm từ Hệ thống** on `#qta` | Synced `SYSTEM` group appears in the list; a new row appears in **Lịch sử đồng bộ nhóm hệ thống** | `test_q2_qta_groups.py`, `test_qta.py::test_qta_groups_sync_specialist_and_quotas` |
| 8 | `FR-QTA-020` AC2 | Đồng bộ không xóa mất nhóm AI chuyên biệt đã tạo | Create an `AI_SPECIALIST` group, then click **Đồng bộ nhóm từ Hệ thống** again | Specialist group, its members, and its quotas remain completely intact | `test_q2_qta_groups.py`, `test_qta.py::test_qta_groups_sync_specialist_and_quotas` |
| 9 | `FR-QTA-021` AC1 | Cùng một nhóm đặt được hai mức khác nhau cho hai mô hình | Open a group detail (`#qta/groups/<id>`), enable Model 1 = `1000` and Model 2 = `2000`; save | Both distinct limits persist on reload and reflect in the group summary | `test_q2_qta_groups.py`, `test_qta_operations.py` |
| 10 | `FR-QTA-021` AC2 | Tắt quyền mô hình → người chỉ thuộc nhóm đó không còn hạn mức cơ sở cho mô hình đó | Uncheck Model 2 on that group, save, then look up a single-group member on **Tra cứu cá nhân & tạm ngưng** | Member's base entitlement for Model 2 drops immediately to `0 đơn vị hạn mức` (`quy tắc đang tắt`) | `test_q3_qta_lookup_budgets.py`, `test_qta.py::test_qta_groups_sync_specialist_and_quotas` |
| 11 | `FR-QTA-022` AC1 | Tạo nhóm chuyên biệt + thêm ít nhất một thành viên thành công | Click **Tạo nhóm AI chuyên biệt**, create `AI_LAB`, open detail, click **Thêm thành viên** and add a user | Group is created (`AI chuyên biệt`) and member appears in the members table | `test_q2_qta_groups.py`, `test_qta.py::test_qta_groups_sync_specialist_and_quotas` |
| 12 | `FR-QTA-022` AC2 | Thành viên đó xuất hiện trong tra cứu cộng dồn với hạn mức nhóm này | Configure a quota on `AI_LAB` (`3000`), then open **Tra cứu cá nhân & tạm ngưng** and view that member | `AI_LAB` appears in the user's memberships and contributes `3.000 đơn vị hạn mức` | `test_q3_qta_lookup_budgets.py`, `test_qta.py::test_qta_budget_deficit_additive_and_mobile` |
| 13 | `FR-QTA-030` AC1 | Thuộc nhóm 1 000 + nhóm 3 000 cùng mô hình → cơ sở = 4 000 | Assign an active user to `G1` (`1000`) and `G2` (`3000`) on the same model; look up the user | Base entitlement equals **`4.000 đơn vị hạn mức`** (never `3.000`) | `test_q3_qta_lookup_budgets.py`, `test_q5_carryover.py`, `test_qta.py` |
| 14 | `FR-QTA-030` AC2 | Tra cứu cá nhân hiện đúng danh sách nhóm và phép cộng | Inspect the model row for that multi-group user on **Tra cứu cá nhân & tạm ngưng** | Breakdown displays `1.000 (G1) + 3.000 (G2) = 4.000 đơn vị hạn mức` and lists both groups | `test_q3_qta_lookup_budgets.py`, `test_qta.py::test_qta_budget_deficit_additive_and_mobile` |
| 15 | `FR-QTA-031` AC1 | Chọn được một người cụ thể và thấy bảng cộng dồn | Search and click **Xem hạn mức** for a user on **Tra cứu cá nhân & tạm ngưng** | Shows user state, quota status (`Được dùng AI` / `ĐÃ CẮT`), group list, per-model additive table, and `"Chưa tích hợp đo tiêu thụ thực tế"` | `test_q3_qta_lookup_budgets.py`, `test_qta.py`, `test_qta_operations.py` |
| 16 | `FR-QTA-031` AC2 | Người không thuộc nhóm nào → hạn mức cơ sở 0 hoặc trạng thái bị chặn | Look up an active user in zero groups | Shows `"Tài khoản chưa thuộc nhóm hạn mức AI nào"`, `0 đơn vị hạn mức`, and **Không có hạn mức** (`NO_ENTITLEMENT` in `check_ai_access`) | `test_q3_qta_lookup_budgets.py`, `test_q5_carryover.py`, `test_qta.py` |
| 17 | `FR-QTA-032` AC1 | Giả lập / chạy làm mới → có giao dịch “Làm mới” | On **Lịch sử & Làm mới tháng**, click **Mô phỏng làm mới tháng hiện tại** and confirm | Status flips to **Đã làm mới**, button disables, reset history records `Mô phỏng thủ công`, and events ledger records **Làm mới đầu tháng** | `test_q4_qta_killswitch_reset.py`, `test_qta.py::test_qta_killswitch_restore_reset_and_events` |
| 18 | `FR-QTA-032` AC2 | Dư tháng trước không làm tăng hạn mức tháng mới | Compare current month vs next month in **Tra cứu cá nhân & tạm ngưng** (and automated month-rollover check) | Next month equals configured group base quotas only; zero carryover from prior month | `test_q4_qta_killswitch_reset.py::test_zero_rollover_across_months` |
| 19 | `FR-QTA-040` AC1 | Sau cắt → trạng thái / huy hiệu ĐÃ CẮT; không gọi AI được trong phạm vi cắt | Click **Cắt / tạm ngưng quyền AI**, pick `Chỉ mô hình ngoài trường (trả phí)`, enter reason & *Người ra lệnh*, submit | User list & detail show **`ĐÃ CẮT`**; external model shows **Tạm ngưng mô hình ngoài trường**; internal model stays **Được phép**; `base_entitlement` is unchanged (not zeroed) | `test_q4_qta_killswitch_reset.py`, `test_qta.py::test_qta_killswitch_restore_reset_and_events` |
| 20 | `FR-QTA-040` AC2 | Có giao dịch / nhật ký Cắt chỉ ghi thêm | Inspect **Lịch sử tạm ngưng & khôi phục quyền AI** and **Lịch sử & Làm mới tháng** → events | Suspension row & **Tạm ngưng quyền AI** event appear with distinct operator (`Bạn`) and `ordered_by`; zero Edit/Delete buttons | `test_q4_qta_killswitch_reset.py`, `test_qta.py`, `test_qta_operations.py` |
| 21 | `FR-QTA-040` AC3 | Thiếu lý do hoặc người ra lệnh → không cắt được | Open **Cắt / tạm ngưng quyền AI**, leave *Lý do tạm ngưng* or *Người ra lệnh* empty, submit | Dialog stays open with invalid-field prompt; user remains **Được dùng AI** | `test_q4_qta_killswitch_reset.py`, `test_qta.py::test_qta_killswitch_restore_reset_and_events` |
| 22 | `FR-QTA-041` AC1 | Khôi phục → trạng thái hoạt động lại | Click **Khôi phục quyền AI**, enter optional note, confirm | Quota status returns to **Được dùng AI**; both models become **Được phép**; `base_entitlement` is unchanged | `test_q4_qta_killswitch_reset.py`, `test_qta.py::test_qta_killswitch_restore_reset_and_events` |
| 23 | `FR-QTA-041` AC2 | Có giao dịch / nhật ký Khôi phục | Inspect suspension history & **Lịch sử & Làm mới tháng** → events | Restoration note/timestamp appears in suspension history and **Khôi phục quyền AI** appears in events ledger | `test_q4_qta_killswitch_reset.py`, `test_qta.py`, `test_qta_operations.py` |
| 24 | `FR-QTA-050` AC1 | Không còn UI chọn Học kỳ/Đề tài/Đợt thi cho hạn mức | Check every form/filter in `#qta` and unit wording | Zero non-month cycle controls; every amount uses `đơn vị hạn mức` (never tokens/credits/currency) | `test_q2_contracts.py`, `test_qta.py::assert_qta_dom_invariants` |
| 25 | `FR-QTA-050` AC2 | Không có nút Sửa/Xóa trên dòng giao dịch đã ghi | Inspect budget revisions, sync runs, suspension history, monthly resets, and events tables | Zero Edit/Delete controls in UI; PostgreSQL `aq_uai_runtime` rejects `DELETE` on all 8 QTA tables and `UPDATE` on 6 history tables | `test_q1_qta_schema.py`, `test_q6_qta_upgrade.py`, `test_qta.py`, `test_qta_operations.py` |
| 26 | `FR-MDL-020` AC3 | Thử kết nối không trừ hạn mức của người thử | Give an `AI_MODEL_ADMIN` a non-zero QTA base entitlement, run **Thử kết nối** in `#mdl`, then re-check their lookup & school budget in `#qta` | Entitlement lookup, school budget, and QTA events are identical before and after; zero `qta_*` tables written | `test_q6_mdl_qta_isolation.py`, `test_m6_quota_isolation.py` |

Record date, browser, account names (never passwords), and any deviation; manual evidence stays separate from automated results and is not formal sign-off until PO/TL record acceptance in [acceptance-matrix.md](../acceptance-matrix.md).

---

## 7. Known limitations and open items

1. **Consumption metering (`NOT_INTEGRATED`, `QD10`):** No AI invocation gateway exists yet. `actual_consumption` and `remaining_quota` are always `null` (`consumption_status: "NOT_INTEGRATED"`), and `#qta` explicitly shows `"Chưa tích hợp đo tiêu thụ thực tế"`. In `FR-MDL-020 AC3`, "balance unchanged" therefore refers to live additive `base_entitlement` and institutional `allocated`.
2. **Actor UUIDs in history tables (`Q-g` default — *reviewer default, PO may override*):** Budget revisions, sync runs, suspensions, restorations, resets, and events display actor UUIDs (`<code>`, with a `Bạn` badge for the signed-in user), consistent with MDL and avoiding client `/users/{id}` fan-out. Adding human names later is one shared read-side join across MDL and QTA.
3. **Flat sidebar navigation (`Q-h` default — *reviewer default, PO may override*):** **Hạn mức AI theo Nhóm tài khoản** is a flat top-level entry in the admin sidebar rather than the FRD's nested *Quản trị AI & Dữ liệu → Quản lý AI & Chi phí* tree (known cosmetic deviation preserving shared navigation and existing browser tests).
4. **Past months not snapshotted (`QD6`, `PROV`):** Historical closed budget months return `allocation_status: "NOT_SNAPSHOTTED"` (`"Chưa chụp ảnh lịch sử"`) because Phase 4 does not store frozen end-of-month membership snapshots.
5. **Quota matrix page cap:** `#qta/groups/<uuid>` loads `GET /qta/models?limit=100`. Institutions registering more than 100 active models will need pagination in the quota editor.
6. **Suspending `PENDING` accounts (`QD11`, `NEEDS-INSTITUTION`):** Quota status is currently independent of directory account state (`PENDING`/`ACTIVE`/`DISABLED` can all be suspended/restored). Confirm institutional policy if `PENDING` accounts should be excluded.
7. **`decision_date` range validation (`Q-a`, `NEEDS-INSTITUTION`):** Any valid calendar date `YYYY-MM-DD` is accepted today without a min/max year or future-date cap.
8. **`UNIT` viewer visibility of suspension `reason` (`Q-b`, `PROV`):** Unit-scoped `AI_QUOTA_VIEWER` users see the free-text suspension `reason` on accounts in their own unit (`GET /qta/users/{id}/suspensions` and `/entitlements`), while `qta_events.summary` never stores free-text `reason` or `note`. Confirm institutional HR privacy policy before production use.

---

## 8. Notes for Phase 5 CRT

When implementing Phase 5 (`AQ-FRD-UAI-CRT-001` — *Cấp bổ sung & thu hồi hạn mức*):

1. **Mandatory budget lock (`QTA_BUDGET_NAMESPACE = 52001`):** Any CRT write checked against the monthly school budget (`FR-CRT-013`) **must** acquire `database_lock(db, QTA_BUDGET_NAMESPACE, institution_key(tenant), shared=False)` in the **same** transaction as its budget check and ledger insert. Without it, a concurrent `PUT /qta/budgets/{month}` and a concurrent CRT grant under `READ COMMITTED` could both pass their checks and exceed the monthly ceiling.
2. **Single institutional allocation source (`entitlements.allocated_for_month`):** Net CRT monthly grants must join `allocated_for_month` (scoped to `period_month`) so `FR-QTA-011` (`409 QTA_BUDGET_BELOW_ALLOCATED`) and `FR-CRT-013` compute the exact same allocated total.
3. **Consumption & remaining integration seam:** `ModelEntitlementOut` already exposes `actual_consumption`, `remaining_quota`, and `consumption_status` (`"NOT_INTEGRATED"`). Keep token-to-credit conversion undefined unless formally authorized, and keep `mdl/` free of `crt/` and `qta/` imports.

---

## 9. Verification evidence (Q6 closure)

Evidence categories are strictly separated. All automated runs below executed on disposable private PostgreSQL 18, loopback fake providers, nginx, and Chromium.

| Check | Command / log | Result |
| --- | --- | --- |
| Baseline (start of Q6, commit `accf694`) | `bash scripts/verify_phase2.sh` ([baseline-gate.log](reports/q6/baseline-gate.log)) | Static checks PASS; `alembic check` clean; **API 581 passed, 1 skipped**; **browser 20 passed**; exit 0 |
| Focused Q6 checks (static, Ruff ×2, 4.1 isolation, 4.2 upgrade, 4.4 wording, 4.3 backup/restore) | [focused-tests.log](reports/q6/focused-tests.log) | Static & Ruff PASS; **2 API integration passed** (`test_q6_mdl_qta_isolation.py`, `test_q6_qta_upgrade.py`); **5 Playwright browser passed** (`test_qta.py` ×4, `test_qta_operations.py` ×1) |
| Mutation proofs (3 required) | [mutation-proof.log](reports/q6/mutation-proof.log) | 3/3 failed on target assertions (`DELETE` on `qta_events`, `ĐÃ CẮT` wording, isolation positive control); all 3 files restored byte-identically (SHA256 verified) |
| **Final full gate** (assets, sidebar, `node --check`, Ruff ×2, Compose render, fresh cluster, `alembic upgrade head` + `check`, full API & browser suites) | `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv>/bin/python AQ_NGINX=<wrapper> bash scripts/verify_phase2.sh` ([final-gate.log](reports/q6/final-gate.log)) | Static checks PASS; `alembic check` "No new upgrade operations detected"; **API 583 passed, 1 skipped** (+2 over baseline); **browser 21 passed** (+1 over baseline); exit 0 |
| Migrations (`0006 → 0008` populated) | `test_populated_0006_upgrades_to_0008_preserves_data_and_enables_qta` | Passed (all 12 pre-QTA tables byte-identical, 8 QTA tables empty before sync, `0007` roles without implicit grants, exact `QTA_RUNTIME_PRIVILEGES`, idempotent second run, live sync/quotas/lookup/allocated) |
| Backup / restore (`pg_dump` / `pg_restore`) | `test_qta_backup_restore_preserves_state_ui_writes_and_constraints` | Passed (all 8 `qta_*` tables row-for-row identical, restored `#qta` UI renders revisions/lookup/suspensions/reset, post-restore write & `ĐÃ CẮT` work, runtime `DELETE` denied, repeat reset 409) |
| **NOT verified in Q6** | — | Hosted GitHub Actions CI on Q6; disposable Docker Compose rehearsal; live upgrade on the developer's `aq-uai-dev` stack (untouched); live OS `systemd`/cron scheduler execution; browsers other than Chromium; opt-in live external AI provider (`1 skipped`); **formal Tech Lead / Product Owner acceptance (`0/33`)** |
