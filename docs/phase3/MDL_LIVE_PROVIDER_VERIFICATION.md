# MDL provider verification (FR-MDL-020 AC1)

**Status (2026-11-26, D15):** the Project Owner decided that this demo project verifies FR-MDL-020 against a **synthetic provider** instead of a real vendor ([D15 record](MDL_OPEN_DECISIONS.md#d15-record-synthetic-demo-provider-2026-11-26)). That verification is **done** (section "Demo scope" below). The real-vendor procedure further down is kept as an **optional** step for anyone who later needs vendor compatibility; it has not been run, and the opt-in test `tests/live/test_live_provider.py` stays skipped unless explicitly authorized.

## Demo scope: synthetic provider (D15)

**What:** `infra/demo-provider/server.py`, an OpenAI-compatible HTTPS server with its own throwaway CA, started by `bash scripts/dev-up.sh --demo-provider` (adds `infra/compose.demo-provider.yaml`). Nothing leaves your machine and nothing can be billed.

**How to use it in the admin UI** (after setting `AQ_DEMO_PROVIDER_API_KEY` in `.env`, see the [handoff](mdl-handoff.md#3a-start-the-synthetic-demo-provider)):

| Field | Value |
| --- | --- |
| Loại | Nội bộ |
| Địa chỉ kết nối | `https://demo-provider:8443/v1` |
| Kiểu API | Tương thích OpenAI (either style works) |
| Kiểu xác thực | Bearer token (or "Khóa trong header riêng" with header `X-Api-Key`) |
| Bí mật kết nối | the value of `AQ_DEMO_PROVIDER_API_KEY` |
| Mã kỹ thuật của mô hình | `demo-chat` or `demo-chat-mini` (anything else → "Không tìm thấy mô hình") |

**Recorded synthetic runs** (evidence category: automated, synthetic provider; not a real vendor):

| Date | Where | Result |
| --- | --- | --- |
| 2026-11-26 | `apps/api/tests/unit/test_demo_provider.py` (real adapter + egress path, loopback) | 9 passed: Bearer, V2 style, header key PASSED; wrong key `AUTH_FAILED`; no key `AUTH_FAILED`; unknown model `MODEL_NOT_FOUND`; no CA `TLS_ERROR`; CA file public only; short key refused |
| 2026-11-26 | Disposable Compose project `aq-m7-demo` with the override, through nginx and the real API (`~/.cache/aqm7/compose-demo.sh`, outside the repository) | 13/13 PASS: status shows allowlist and CA configured; Bearer provider over https stored; `demo-chat` and `demo-chat-mini` PASSED; unknown model `MODEL_NOT_FOUND`; selection list = the two PASSED models; primary + fallback saved, effective PRIMARY; wrong key `AUTH_FAILED`; header key PASSED; secret absent from responses; after a provider restart with a **new** CA the retest PASSED (after the 30 s cooldown) and routing stayed PRIMARY; key absent from `api` and `demo-provider` logs; removed with `down -v` |

## Optional: real-vendor verification (not required by D15)

### What and why

Automated tests use a loopback fake provider. They prove the wire format, the network policy and the transaction shape, but not that a real provider accepts the request. This runbook records one genuine call against a provider the school chooses.

### Preconditions (all required)

1. The Product Owner names the provider and model, and **explicitly authorizes a possibly billed call** (one request, `max_tokens`/`max_completion_tokens` 16).
2. For an external provider: a data-protection agreement number exists and is recorded in the system first (FR-MDL-030).
3. The secret is supplied through the operator's environment or typed into the admin UI. It is never written to a file in the repository, a ticket or this document.
4. For an internal provider: the operator sets `AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST` (with the port) and, for a private CA, `AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE`.

### Option A — recorded run through the product (preferred)

1. In **Cấu hình Nhà cung cấp & Mô hình AI → Nhà cung cấp**, add the provider and its secret; record the agreement (external).
2. Add the model with the TEXT capability and open it.
3. Click **Thử kết nối**, read the cost notice, tick the acknowledgement, submit.
4. Record below: date, provider name (no secret), model technical ID, result, failure code if any, HTTP status class, latency, and the test ID from **Lịch sử thử kết nối**. The audit event `mdl.model_connection_tested` (with `charges_acknowledged`) is the system's own record.
5. Optional evidence of the routing consequence: after a PASSED result and a risk level, the model appears in the routing dialog; after a deliberate failure (for example a wrong technical ID) it does not.

### Option B — wire check without the database

Same request and policy, outcome printed only (no secret, no provider text):

~~~bash
AQ_UAI_LIVE_PROVIDER_AUTHORIZED=I-ACCEPT-A-POSSIBLY-BILLED-CALL \
AQ_UAI_LIVE_PROVIDER_TYPE=EXTERNAL AQ_UAI_LIVE_ENDPOINT=https://<provider>/v1 \
AQ_UAI_LIVE_MODEL=<model> AQ_UAI_LIVE_AUTH_SCHEME=BEARER AQ_UAI_LIVE_SECRET=<from a secret store> \
python -m pytest -q -s -m live_provider apps/api/tests/live
~~~

Without the authorization variable the test is **skipped** (it is part of the normal suite only as a skip).

### How to read the result

`PASSED` needs a 2xx reply with a chat-completion shape. Failure codes are listed in the [M4 decision record](MDL_OPEN_DECISIONS.md#m4-decision-record-2026-11-25). Common first-run issues: `AUTH_FAILED` (key), `MODEL_NOT_FOUND` (technical ID), `REQUEST_REJECTED` with newer models (switch the provider to `OPENAI_COMPATIBLE_V2`), `ENDPOINT_BLOCKED` (policy: external needs https on port 443 with a public name).

### Recorded runs

| Date | Provider (no secret) | Model | Result | Code | HTTP class | Latency | Test ID / evidence | Authorized by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | not run (optional since D15) | — | — | — | — | — |
