# MDL handoff (M7): operations, local update and manual acceptance

**Status (2026-11-26):** M1–M7 are implemented and technically verified by automated tests and disposable Docker Compose runs. **Nothing here is formal acceptance**: no Tech Lead, Product Owner, legal or school sign-off is recorded, and the live-provider run is still pending. Requirement-by-requirement status: [traceability, M7 acceptance status](MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26).

**Audience:** the developer operating the local `aq-uai-dev` stack and the person doing manual acceptance.

## 1. What is delivered

The admin section **Cấu hình Nhà cung cấp & Mô hình AI** (`http://admin.localhost:8000/#mdl`) and the API under `/api/v1/mdl`: providers with encrypted secrets, data-protection agreements, models, risk levels, a real SSRF-protected connection test, primary/fallback routing with an append-only history, and (M7) a configuration history with before → after values. Design: [architecture](MDL_ARCHITECTURE_AND_DECISIONS.md); decisions: [register](MDL_OPEN_DECISIONS.md).

## 2. How code reaches the running stack (hot reload)

| You changed | Does the running stack pick it up? | What to run |
| --- | --- | --- |
| `apps/admin/**` (admin UI) or `apps/web/**` | **Yes, immediately**: both folders are bind-mounted read-only into `web` (nginx) | Reload the browser tab (Ctrl+Shift+R to skip the cache) |
| `infra/nginx/default.conf` | No: nginx reads its configuration at start | `docker compose --env-file .env -f infra/compose.yaml exec web nginx -s reload` |
| API Python code, migrations, `pyproject.toml` | **No**: the code is copied into the image at build time and uvicorn runs without `--reload` | `bash scripts/dev-up.sh` (rebuild, then `provision` → `migrate` → new `api`) |
| `.env` values | No: environment is fixed when a container is created | `bash scripts/dev-up.sh` (recreates only containers whose configuration changed) |

`scripts/dev-up.sh` runs `docker compose --env-file .env -f infra/compose.yaml up --build -d` and then reloads nginx. **Why the reload:** nginx looks up the `api` container's address once at start; when `up` recreates `api` but not `web`, every API call through `http://admin.localhost:8000` returns **502 Bad Gateway** until nginx reloads (observed on 2026-11-26; pre-existing since Phase 2, fixed in the script in M7). If you ever see 502 after recreating `api` by hand: `docker compose --env-file .env -f infra/compose.yaml exec web nginx -s reload`. The Compose project name is fixed (`aq-uai-dev`), so the database volume `aq-uai-dev_postgres_data` is **kept**; `provision` and `migrate` are idempotent.

## 3. Updating your existing `aq-uai-dev` stack to MDL

**Observed on 2026-11-26 (read-only inspection, no restart):** the running `api` image and the database are both at `0002_identity_foundation` (Phase 2). The `api` container was created before the MDL variables existed. The admin UI files are already the new ones (bind mount), but the MDL menu stays hidden until the API is upgraded, because the old API reports no `mdl.*` capability.

The upgrade applies migrations `0003`–`0006` to your existing data. It was rehearsed on a disposable copy of exactly this path (Phase 2 commit `2c909e3` → current tree on the same volume, see the [M7 verification](MDL_IMPLEMENTATION_PLAN.md#m7-verification)).

Run from the repository root:

```bash
# 1. Back up the database first (reads only; the file stays on your machine, mode 600).
umask 077
docker compose --env-file .env -f infra/compose.yaml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > ~/aq-uai-dev-before-mdl.dump

# 2. Create a credential key (prints one new random key; nothing is written anywhere).
python3 -c "import base64,os; print('AQ_UAI_MDL_CREDENTIAL_KEYS=k1:' + base64.b64encode(os.urandom(32)).decode())"
```

3. Open `.env` in your editor and add the printed line plus `AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID=k1`. If `.env` already contains the `CHANGE_THIS` MDL placeholders from `.env.example`, replace them. **Save a copy of the key outside the repository and separately from database backups**: without it, stored provider secrets cannot be recovered (re-entering each secret is the only recovery). Optional for internal providers: `AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST=host:port` (see `.env.example`).

```bash
# 4. Rebuild and migrate (keeps the volume).
bash scripts/dev-up.sh

# 5. Check: all services up, migrate exited 0, schema at the new head, API ready.
docker compose --env-file .env -f infra/compose.yaml ps -a
docker compose --env-file .env -f infra/compose.yaml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select version_num from alembic_version"'
#    expected: 0006_mdl_routing_and_styles
curl -s http://localhost:8000/api/v1/ready
```

Then open `http://admin.localhost:8000/` (use your `WEB_HOST_PORT` if it is not 8000). If something fails, `docker compose --env-file .env -f infra/compose.yaml logs migrate api` shows why; **do not** run `down -v` (it deletes the database volume). Restoring the step 1 backup follows [Restore and verify a backup](../phase2/phase2-handoff.md#restore-and-verify-a-backup) in the Phase 2 handoff.

## 3a. Start the synthetic demo provider

By the Project Owner's decision D15 this project uses a **synthetic** AI provider instead of a real vendor ([details](MDL_LIVE_PROVIDER_VERIFICATION.md#demo-scope-synthetic-provider-d15)). It runs as one more container on the Compose network, speaks the OpenAI-compatible API over https with its own throwaway certificate authority, and never contacts the internet.

```bash
# 1. Create a demo key (prints one line; nothing is written anywhere).
python3 -c "import secrets; print('AQ_DEMO_PROVIDER_API_KEY=demo-' + secrets.token_urlsafe(24))"
```

2. Add the printed line to `.env` (the MDL key ring from section 3 must be there too). You will type the same value as the provider's secret in the admin UI.

```bash
# 3. Start (or upgrade) the stack with the demo provider. Keeps the database volume.
bash scripts/dev-up.sh --demo-provider

# 4. Check: demo-provider is healthy and serves the synthetic models.
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.demo-provider.yaml ps
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.demo-provider.yaml logs demo-provider | tail -3
#    expected: "Synthetic demo provider on https://demo-provider:8443/v1 models=demo-chat,demo-chat-mini"
```

While the override is in use, the API may reach **only** `demo-provider:8443` as an internal destination (it replaces any `AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST` from `.env`). Use `bash scripts/dev-up.sh --demo-provider` every time you rebuild; a plain `bash scripts/dev-up.sh` recreates the API without the demo settings (existing configuration stays, but tests then fail with "Địa chỉ bị chính sách mạng chặn"). `bash scripts/dev-down.sh` stops it too.

In the admin UI, register the provider with: Loại **Nội bộ**, address `https://demo-provider:8443/v1`, **Bearer token**, secret = your `AQ_DEMO_PROVIDER_API_KEY`; models `demo-chat` and `demo-chat-mini`.

## 4. Operations reference

| Task | How |
| --- | --- |
| First MDL administrator | A `FOUNDATION_ADMIN` opens **Tài khoản** → a user → **Cấp vai trò** → `AI_MODEL_ADMIN`, scope **Toàn trường**. The foundation administrator itself has no MDL access (by design) |
| Key rotation | Append `k2:<new key>` to `AQ_UAI_MDL_CREDENTIAL_KEYS`, set `AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID=k2`, `bash scripts/dev-up.sh`, then `docker compose --env-file .env -f infra/compose.yaml exec -T api python -m aq_uai_api.db.mdl_rewrap` (prints counts only; exit 1 if a row is unreadable). Remove `k1` only after `rewrapped` + `already_current` covers every credential |
| Key lost | Stored secrets are unreadable (status *Không đọc được*; routing fails closed). Configure a new key, then re-enter each provider secret in the UI and re-test. History and configuration are kept (rehearsed in `test_restore_keeps_ciphertext_usable_and_key_loss_fails_closed`) |
| Backups | `pg_dump` contains ciphertext only, never a secret or key (checked by the same test). Back up the key ring separately |
| Internal provider | Add `host:port` to `AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST`; a provider that sends a secret must use `https` (private CA: `AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE`, file mounted read-only) |
| Demo provider | Section 3a. Restarting it creates a new certificate; the API reads the new CA on the next test, so nothing needs re-entering |
| Real vendor (optional) | [Runbook](MDL_LIVE_PROVIDER_VERIFICATION.md#optional-real-vendor-verification-not-required-by-d15); needs your explicit authorization of a possibly billed call |

## 5. Manual acceptance checklist

**Prerequisites:** the stack started as in sections 3 and 3a (key ring and `AQ_DEMO_PROVIDER_API_KEY` in `.env`, `bash scripts/dev-up.sh --demo-provider`); a `FOUNDATION_ADMIN` account; a second account that you grant `AI_MODEL_ADMIN`.

| # | FR | Steps | Expected result |
| --- | --- | --- | --- |
| 1 | 001 | Sign in as the foundation admin; open `#mdl` by URL | No MDL menu entry; page says you have no permission |
| 2 | 001 | Grant `AI_MODEL_ADMIN` (Toàn trường) to the second account; sign in with it | Menu **Cấu hình Nhà cung cấp & Mô hình AI**; empty lists show "Chưa cấu hình" / "Không tìm thấy bản ghi phù hợp."; system status shows "1 địa chỉ được cho phép" and the extra certificate "Đã cấu hình" |
| 3 | 010 | Try **Thêm nhà cung cấp**: Nội bộ, `http://demo-provider:8443/v1`, Bearer, your demo key | Refused: a provider that sends a secret must use https |
| 4 | 010 | Same with `https://demo-provider:8443/v1`, name "Demo AI" | Saved; secret shows only "Đã lưu (được ẩn)" |
| 5 | 011 / 040 | Open Demo AI → **Thêm mô hình**: `demo-chat` (Văn bản); then `demo-chat-mini`; then `no-such-model` | Three models listed; no prompt, temperature or template field anywhere |
| 6 | 020 | `demo-chat` → **Thử kết nối** | "Thử kết nối thành công." (no cost notice: internal provider); repeat for `demo-chat-mini` |
| 7 | 020 | `no-such-model` → **Thử kết nối** | "Thử kết nối thất bại: Không tìm thấy mô hình"; it never becomes eligible |
| 8 | 010 | **Sửa nhà cung cấp** on Demo AI: secret field is empty; change only the name and save; test `demo-chat` again (wait 30 s if told to) | Still PASSED: the blank field kept the stored secret |
| 9 | 020 | Add provider "Demo wrong key" (same address, Bearer, any other 16+ character value) and a `demo-chat` model; test it | "Nhà cung cấp từ chối thông tin xác thực" (AUTH_FAILED) |
| 10 | 031 | `demo-chat` and `demo-chat-mini` → **Phân loại rủi ro** → Thấp | Guidance labelled internal, not legal; both show "Đủ điều kiện" |
| 11 | 021 | **Mô hình chính & dự phòng → Đổi**: list contains only the two eligible models; pick the same model twice | Refused ("phải khác mô hình chính"); with `demo-chat` primary, `demo-chat-mini` fallback and a decision number: saved, "Đang dùng mô hình chính" |
| 12 | 012 | **Ngừng hoạt động** on `demo-chat` | Refused, says it is the primary model |
| 13 | 021 | Swap primary and fallback, then swap back; open **Lịch sử thay đổi** | Three revisions with before/after and decision numbers |
| 14 | Should | Same tab, **Lịch sử cấu hình** | Each change shows "field: before → after" (name change from step 8, risk, routing); no secret anywhere |
| 15 | 021 / D9 | Edit Demo AI and enter a new secret equal to the old key | Both slots show "Kết quả thử đã cũ", effective "Không có mô hình nào được phép dùng"; retest both → "Đang dùng mô hình chính" again |
| 16 | 012 | Set `demo-chat-mini` as primary with no fallback, then deactivate `demo-chat` | Allowed |
| 17 | 030 | Add an External provider `https://api.example.invalid/v1` with a model; **Thử kết nối** | Refused until an agreement is recorded (**Ghi nhận thỏa thuận**, "không thẩm định giá trị pháp lý" shown); then the cost notice and checkbox appear; the test fails with a DNS error (nothing billable is sent). Withdrawal of a *routed* external model is covered by automated tests only (an external model cannot pass a test without a real vendor) |

Record date, browser, account names (no passwords) and any deviation; this is **developer-performed manual evidence**, kept separate from automated results.
