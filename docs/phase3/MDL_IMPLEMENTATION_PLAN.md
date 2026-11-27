# MDL implementation plan (M0–M7)

**Status:** M0 (documentation) is written; its approval gate is still recorded as pending. **M1–M7 were implemented on 2026-11-25/26 on the project owner's explicit instructions** (see the [M1](#m1-completion-2026-11-25), [M2](#m2-completion-2026-11-25), [M3](#m3-completion-2026-11-25), [M4](#m4-completion-2026-11-25), [M5](#m5-completion-2026-11-26), [M6](#m6-completion-2026-11-26) and [M7](#m7-completion-2026-11-26) sections). Phase 3 MDL is **technically complete**; it is **not formally accepted** (no Tech Lead / Product Owner sign-off). FR-MDL-020 is verified against the synthetic demo provider chosen by the Project Owner (D15); its AC3 waits for QTA/CRT. Decisions D1–D14 and the M7 record: [MDL_OPEN_DECISIONS](MDL_OPEN_DECISIONS.md#m7-decision-record-2026-11-26). Operations and manual checklist: [handoff](mdl-handoff.md).
Designs: [architecture](MDL_ARCHITECTURE_AND_DECISIONS.md) · requirements: [traceability](MDL_REQUIREMENTS_TRACEABILITY.md) · open items: [decisions](MDL_OPEN_DECISIONS.md) · FRD: [AQ-FRD-UAI-MDL-001](../frd/AQ-FRD-UAI-MDL-001.md).

The roadmap keeps the eight packages from the saved analysis. It is dependency-first: shared contracts, then storage, then APIs, then network behaviour, then routing, then UI, then acceptance.

```
M0 docs ─▶ M1 shared contracts ─▶ M2 schema+crypto ─▶ M3 provider/model APIs ─▶ M4 egress+test ─▶ M5 routing ─▶ M6 UI ─▶ M7 acceptance
```

## Rules common to every package

1. Before coding, state the phase, FRD IDs and exact files in scope.
2. Smallest reviewable change; preserve working UI/API behaviour; write tests before the business rule.
3. Never modify `apps/web/` or original manifests; keep the classic script order.
4. Run: `ruff check`, `node --check` on changed JS, `python scripts/verify_frontend_assets.py`, `alembic upgrade head && alembic check` on a clean database and on a `0002` database, `pytest apps/api/tests`. M6/M7 also run `bash scripts/verify_phase2.sh`.
5. Report passed, skipped and blocked tests separately (Docker, hosted CI, live provider are separate evidence categories).
6. No commits, pushes, remote changes or deployments without explicit instruction. Never read or print `.env`.
7. Distinguish SPEC / REC / PROV / APPR in every report; do not claim FRD acceptance from demo or mock-only behaviour.

## M0 — Planning and documentation

- **Scope:** create the project context, `CLAUDE.md`, the five Phase 3 documents, ADR-0003 (*Proposed*), and the local-deployment note. **Documentation only.**
- **Excluded:** any source code, models, migrations, dependencies, frontend assets, tests, `.env`, Docker configuration or Git history.
- **Tests:** link and consistency check only.
- **Gate:** developer and reviewer approve the packages, permissions, provisional decisions and security design. D13 remains open (decide before M5); D14 is reviewer-recommended and awaits TL confirmation.
- **Status:** documents written; gate **pending**.

## M1 — Access and shared-contract extensions

- **FRs:** FR-MDL-001 (partly). **Depends on:** M0 approval.
- **Files:** `authorization/policy.py` (enum, `_CENTRAL_PERMISSIONS`, `_ROLE_SCOPES`), `db/identity.py` (check constraints), migration `0003_mdl_access_catalog`, `db/schema.py`, `api/errors.py` (new codes, allowlisted `details`, private path `mdl`), shared extraction of `WriteContext`/`record` from `directory/service.py`, `apps/admin/assets/pages.mjs` labels, pinned catalog tests (`test_wp1_schema.py`, `test_wp2_database.py`, `test_wp5_contract.py`).
- **Scope:** permissions `mdl.read`, `mdl.manage`; role `AI_MODEL_ADMIN` only (no `AI_MODEL_VIEWER`).
- **Invariants:** MDL authority is direct and GLOBAL only; `FOUNDATION_ADMIN` and `AI_SPECIALIST` groups gain nothing; existing directory responses unchanged.
- **Tests:** policy unit and PostgreSQL tests for the new role shape and scope; migration on clean and `0002` databases, second upgrade a no-op; WP4/WP5 suites unchanged-green; `details` allowlist test.
- **Excluded:** any MDL table, route or UI.
- **Gate:** all existing tests (119 reported in WP7) plus new ones pass; reviewer confirms no behaviour change in directory APIs.

### M1 completion (2026-11-25)

**Status: implemented, awaiting independent review. Not accepted by the Tech Lead or Product Owner.** The developer authorized M1 explicitly although the M0 gate is still pending; this is recorded, not a sign-off.

- **Delivered:** `PermissionCode.MDL_READ/MDL_MANAGE` and both in `_CENTRAL_PERMISSIONS` (resolver ignores them unless a direct GLOBAL user grant); `_ROLE_SCOPES` entry for `AI_MODEL_ADMIN` (user, GLOBAL only; no group entry); migration `0003_mdl_access_catalog` (role, two permissions, two role-permission rows, constraints `ck_user_role_assignments_mdl_admin_global` and `ck_group_role_assignments_no_mdl_admin`, mirrored in `db/identity.py`); `REQUIRED_SCHEMA_REVISION` now `0003_mdl_access_catalog`; eleven additive `MDL_*` error codes appended after the generic ones, optional allowlisted `details` (only `used_in`, a short list of lowercase identifiers; other keys or free text raise `ValueError` at construction), private cache path `mdl`; `WriteContext`, `record` and a generic `protected(..., permission_hint=)` now live in `authorization/writes.py`, and `directory/service.py` re-exports them and keeps a thin `protected` wrapper for its group-kind lock hint; admin labels for `mdl.read`/`mdl.manage`, and the role form keeps `AI_MODEL_ADMIN` GLOBAL-only and out of group grants.
- **Not delivered (by design):** `AI_MODEL_VIEWER` (D7 viewer part unresolved), any MDL table, route, UI page, credential encryption or network code. `FOUNDATION_ADMIN` and the `AI_SPECIALIST` group gain nothing.
- **Visible side effects (additive):** `GET /roles` now lists `AI_MODEL_ADMIN`; `GET /directory/capabilities` now includes `mdl.read` and `mdl.manage` keys (empty scope unless granted). Existing keys, shapes and statuses are unchanged. Error bodies gain `details` only when a code supplies it; none does yet.
- **Existing tests edited (and why):** `test_wp5_directory.py` role set gains `AI_MODEL_ADMIN`; three white-box monkeypatch targets moved from `directory.service` to `authorization.writes` (`write_transaction`, `resolve_write_authority`) because those names moved with the extraction; `test_wp1_schema.py` head/catalog pins; `tests/browser/test_operations.py` head constant (browser suite **not run**, see report).
- **Evidence:** automated, disposable private PostgreSQL 18 only. See the M1 report for commands and counts. No Docker, hosted-CI or acceptance evidence.

## M2 — MDL schema, encryption, privileges

- **FRs:** FR-MDL-010 (storage), RULE-MDL-04. **Depends on:** M1.
- **Files:** `mdl/models.py`, migration `0004_mdl_schema`, `db/provision.py`, `mdl/credentials.py`, `core/config.py`, `.env.example`, `infra/compose.yaml` (key to `api` only), `scripts/verify_wp2_compose.py`, `pyproject.toml` (`cryptography`, `httpx`).
- **Invariants:** no `DELETE` grant anywhere; revisions and agreements append-only; AES-256-GCM with AAD; key outside PostgreSQL and never given to `migrate`/`provision`; tables empty after upgrade.
- **Tests:** constraints (primary≠fallback, cross-institution composite FK); privilege matrix; crypto round-trip, tamper, wrong key, wrong AAD, rotation; upgrade from `0002` with data.
- **Excluded:** routes, network calls.
- **Gate:** migrations and privileges proven on both database paths; crypto design reviewed by the Tech Lead.

### M2 completion (2026-11-25)

**Status: implemented, awaiting independent review. Not accepted by a Tech Lead or Product Owner.** D2, D8 and D14 were decided under the project owner's delegated authority ([decision record](MDL_OPEN_DECISIONS.md#m2-decision-record-2026-11-25)).

- **Delivered:** `mdl/credentials.py` (AES-256-GCM, length-prefixed AAD over tenant, provider, endpoint origin, credential version and key ID; key ring; rotation via `rewrap`; `SecretStr` output; no logging); `mdl/models.py` and migration `0004_mdl_schema` (seven empty tables, composite tenant foreign keys, checks for primary≠fallback, fallback-needs-primary, one `RUNNING` test per model, agreements external-only, token-character header names, http(s) endpoint without userinfo); `REQUIRED_SCHEMA_REVISION = "0004_mdl_schema"`; `MDL_RUNTIME_PRIVILEGES` in `db/provision.py` (no DELETE/TRUNCATE on any MDL table, history INSERT-only, immutable columns not updatable); `provision`/`migrate` refuse to run if they see the key ring; `core/config.py` settings; Compose passes the key ring to `api` only (empty default) and `verify_wp2_compose.py` enforces that; `.env.example` placeholder with generation and rotation notes; `cryptography>=44,<47`.
- **Changed from the plan:** `httpx` is **not** added to runtime dependencies (deferred to M4, no network code yet). Withdrawal columns, `risk_basis_reference` and `decision_reference` are not created (deferred, additive). The rewrap operator command is deferred to M3.
- **Defect found and fixed during M2:** the MDL tables were missing from provisioning's known-table list (`LEGACY_TABLES`), so a database **restored or migrated by the bootstrap owner** could no longer be provisioned (browser tests `test_backup_restores_history_and_runtime_writes` and `test_legacy_upgrade_…[0004_mdl_schema]` failed). Fixed, and a unit test now ties the list to the ORM metadata. A first draft of the endpoint check accepted `https://user:pw@host`; the integration test caught it before release.
- **Existing tests edited:** head pins in `test_wp1_schema.py` and `tests/browser/test_operations.py` (`0004_mdl_schema`).
- **Evidence (automated, disposable private PostgreSQL 18 only):** see "M2 verification" below. No hosted-CI or acceptance evidence.

#### M2 verification

| Check | Command | Result |
| --- | --- | --- |
| Full gate (assets, sidebar, `node --check`, Ruff ×2, Compose render, fresh cluster, `alembic upgrade head` + `check`, API and browser suites) | `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv>/bin/python AQ_NGINX=<wrapper> bash scripts/verify_phase2.sh` | Static checks PASS; `alembic check` "No new upgrade operations detected"; **API 218 passed**; **browser 12 passed, 1 failed** (pre-existing, below) |
| M1 baseline on an M1-only copy | same script | API **142 passed**; browser 12 passed, 1 failed (same pre-existing test) |
| M2 crypto unit tests | `pytest tests/unit/test_m2_credentials.py` | 70 passed (included in the 218) |
| M2 PostgreSQL tests | `pytest tests/integration/test_m2_mdl_schema.py` | 6 passed (included in the 218) |
| Live Compose (Docker evidence, separate disposable project `aq-m2-check`, synthetic `.env`, ports 58100–58102, removed with `down -v`) | `scripts/verify_wp2_compose.py --live` plus probes | Stack up; `alembic_version = 0004_mdl_schema`; `/ready` ready; API/migration credential isolation PASS; key ring usable in `api`; **not visible** in `migrate` or `provision`; `migrate` with an injected key exits 1 with "must be given to the api service only"; 0 containers/volumes left |

- **Pre-existing browser failure (not M1/M2):** `test_admin.py::test_account_unit_workflows_and_conflicts` fails identically on commit `2c909e3` (before M1): Playwright strict mode finds the text "Chờ kích hoạt" in both a status-filter `<option>` and a result badge. Likely cause: newer Chromium treats `<option>` text as visible. Suggested fix (not applied, outside M2): scope the locator to the results table.
- **Environment notes:** nginx is not installed on the host, so the browser suite used a wrapper running a throwaway `nginx:stable-alpine` container on host networking (`AQ_NGINX`). Python dependencies came from a private virtual environment outside the repository.

## M3 — Provider, model, DPA and risk APIs

- **FRs:** FR-MDL-001, 010, 011, 012 (guard seam), 030 (record), 031, 040. **Depends on:** M2.
- **Files:** `mdl/{schemas,service,queries}.py`, `api/v1/mdl.py`, `main.py`, audit actions and payloads, tests.
- **Scope:** provider create/edit/activate/deactivate; agreements including withdrawal (awaiting approval); models create/edit/activate/deactivate/risk; `GET /status`; where-used registry seam.
- **Invariants:** immutable `provider_type` and `technical_id`; origin change requires secret; blank secret keeps; no field named prompt/temperature/template.
- **Tests:** authorization matrix per route; blank-secret keep; canary secret scans of responses, audit and logs; duplicates; extras rejected; OpenAPI scan; audit pairing and rollback on audit failure; concurrent duplicate create.
- **Excluded:** network tests, routing.
- **Gate:** API-level ACs of FR-MDL-010/011/031/040 green.

### M3 plan review (2026-11-25)

The planned scope was kept. Changes made before implementation (rationale in the [M3 decision record](MDL_OPEN_DECISIONS.md#m3-decision-record-2026-11-25)):

1. Withdrawal needs storage that M2 deliberately omitted, so M3 adds migration **`0005_mdl_agreement_withdrawals`** (INSERT-only table) instead of mutable columns. The plan's M3 file list had no migration.
2. D10 decided: provider deactivation is blocked only while one of its models is routed.
3. Registration-time endpoint rules (https for external; no userinfo, query or fragment) and a credential-header denylist were added; connect-time egress stays in M4.
4. A routed model cannot be unclassified or lose TEXT (keeps current routes valid until M5 brings full eligibility).
5. `/mdl/status` reports key availability only; its egress summary is added in M4. The rewrap operator command moves to M7 operations.

### M3 completion (2026-11-25)

**Status: implemented, awaiting independent review. Not accepted by a Tech Lead or Product Owner.** No FR-MDL acceptance criterion is fully satisfied yet (UI, connection-test and routing parts remain); see the [traceability M3 evidence](MDL_REQUIREMENTS_TRACEABILITY.md#m3-evidence-2026-11-25-automated-awaiting-independent-review).

- **Delivered:** `api/v1/mdl.py` (16 operations under `/api/v1/mdl`, registered in `main.py`); `mdl/schemas.py` (forbid-extra inputs, `SecretStr` secrets, canonical endpoints, header denylist, outputs without any secret field); `mdl/service.py` (provider create/edit/activate/deactivate with sealed credentials, agreement record/withdraw, model create/edit/activate/deactivate/risk, each write audited in the same transaction); `mdl/queries.py` (tenant-scoped reads, credential status without decryption, agreement in force); `mdl/usage.py` (where-used seam over routing; lock order routing → provider → model); ten `mdl.*` audit actions with typed payloads in `db/audit.py` (endpoint as origin only); migration `0005_mdl_agreement_withdrawals` with the model class, runtime grant (SELECT, INSERT only) and provisioning entry; `REQUIRED_SCHEMA_REVISION = "0005_mdl_agreement_withdrawals"`; Vietnamese labels for the new audit actions in `apps/admin/assets/pages.mjs` (no MDL page yet, that is M6).
- **Not delivered (by design):** connection tests and egress (M4), routing writes and revisions (M5), MDL admin page (M6), `AI_MODEL_VIEWER` (D7), `risk_basis_reference` (D6), rewrap operator command (M7).
- **Existing tests edited:** head pins in `test_wp1_schema.py` and `tests/browser/test_operations.py`; `test_m2_mdl_schema.py` table lists gain the withdrawals table and its version assertion now uses `REQUIRED_SCHEMA_REVISION`.
- **New tests:** `tests/integration/test_m3_mdl_api.py` (8 PostgreSQL tests: authorization matrix over every route, credential rules, key-ring outage, agreements, models and where-used guards, tenant isolation, audit-failure rollback, concurrent duplicate create, canary-secret scan of every response and audit row); `tests/unit/test_m3_contracts.py` (OpenAPI surface, FR-MDL-040 scan, no secret in outputs, input rules, no quota/credit imports, no logging).

#### M3 verification

| Check | Command | Result |
| --- | --- | --- |
| Full gate | `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv>/bin/python AQ_NGINX=<wrapper> bash scripts/verify_phase2.sh` | Static checks PASS (assets, sidebar, `node --check`, Ruff ×2, Compose render); `alembic check` "No new upgrade operations detected"; **API 267 passed**; **browser 12 passed, 1 failed** (the pre-existing `test_account_unit_workflows_and_conflicts`, see M2) |
| M3 PostgreSQL tests | `pytest tests/integration/test_m3_mdl_api.py` | 8 passed (included in the 267) |
| Unit suite | `pytest tests/unit` | 150 passed (included in the 267) |

Evidence category: automated, disposable private PostgreSQL 18. No live Compose run was repeated for M3 (Compose configuration unchanged since the M2 live run). No hosted CI, live provider or acceptance evidence.

## M4 — Egress policy, adapter and real connection test

- **FRs:** FR-MDL-020, FR-MDL-030 (gate). **Depends on:** M3. **Needs:** D1–D4 positions confirmed.
- **Files:** `mdl/egress.py`, `mdl/adapters/*`, `mdl/testing.py`, connection-test routes.
- **Invariants:** HTTPS-only for external; connect-time IP validation and pinning; server-side internal allowlist; redirects disabled; bounded response and time; **no retries**; no database lock during I/O; one `RUNNING` per model; text-only test; no quota/credit import.
- **Tests:** the egress case table; transaction shape; stale snapshot discard; orphan expiry; failed ⇒ not eligible; header-equality check for kept secret; static no-quota test; optional `live_provider` run.
- **Excluded:** routing.
- **Gate:** pure-library and PostgreSQL tests green; one recorded live-provider run **or** an explicit "pending" entry (requires PO/TL-supplied provider and credentials). Controlled-server results are not labelled genuine verification.

### M4 plan review (2026-11-25)

The planned scope was kept. Changes made before or during implementation (rationale in the [M4 decision record](MDL_OPEN_DECISIONS.md#m4-decision-record-2026-11-25)):

1. **D1, D3, D4 decided** under delegation instead of waiting for "positions confirmed": generic OpenAI-compatible adapter; text-only tests; external tests allowed with an enforced charge acknowledgement, cooldown and process cap.
2. **`httpcore` instead of `httpx`** as the runtime dependency: it exposes the network backend needed for connect-time pinning and has no proxy-environment or redirect behaviour to disable.
3. **No migration.** The M2 table already had the snapshot columns, the one-`RUNNING` index and a format-only `error_code` check. Because the runtime grant allows INSERT of the snapshot columns only, the service inserts with an explicit column list (a default ORM insert was refused by PostgreSQL during development; the grant was kept, not widened).
4. **Additions:** three error codes (`MDL_TEST_UNSUPPORTED`, `MDL_TEST_COOLDOWN`, `MDL_CHARGES_NOT_ACKNOWLEDGED`), a longer failure-code list, `ABORTED` / `EXPIRED` / `STALE_CONFIGURATION` states, a derived `connection_test` field on every model response (needed by M5 eligibility and the M6 UI), and the `/mdl/status` egress summary deferred from M3.
5. **Files beyond the plan's list** (all additive): `api/errors.py` (codes), `core/config.py` (allowlist setting), `db/audit.py` (`mdl.model_connection_tested`), `main.py` (pin the `httpcore` logger), `mdl/schemas.py`, `mdl/queries.py`, `mdl/service.py` (`model_out` now derives test state), `pyproject.toml`, `infra/compose.yaml`, `scripts/verify_wp2_compose.py`, `.env.example`, `apps/admin/assets/pages.mjs` (audit label only).

### M4 completion (2026-11-25)

**Status: implemented, awaiting independent review. Not accepted by a Tech Lead or Product Owner.** No FR-MDL acceptance criterion is fully satisfied (routing selection is M5, UI is M6, and **no live-provider run exists**); see the [traceability M4 evidence](MDL_REQUIREMENTS_TRACEABILITY.md#m4-evidence-2026-11-25-automated-controlled-server-awaiting-independent-review).

- **Delivered:** `mdl/egress.py` (static URL policy, external public-only rule, operator allowlist for internal hosts, resolve-validate-pin network backend with peer re-check, TLS on the host name, no redirects/retries/proxies, 64 KiB cap, per-operation and 20 s total deadlines); `mdl/adapters/` (contract, `OPENAI_COMPATIBLE` adapter: fixed request and shape-checked PASS); `mdl/testing.py` (two transactions around the network call, DPA/charge/capability/state gates, cooldown, process cap, stale detection, `ABORTED` and `EXPIRED` handling, audit in transaction 2); routes `GET`/`POST /api/v1/mdl/models/{id}/connection-tests`; `ModelOut.connection_test`; `/mdl/status.egress`; setting `AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST` (api service only, empty default, enforced by the Compose verifier); `httpcore>=1.0.5,<2`.
- **Not delivered (by design):** routing and eligibility enforcement (M5), UI and the cost-notice text (M6), live-provider run (no provider supplied; no live request was made), vendor-specific adapters, per-capability probes, custom CA configuration for internal HTTPS.
- **Existing tests edited (and why):** `test_m1_contracts.py` (pinned error-code list gains the three appended M4 codes); `test_m3_contracts.py` (route set gains the connection-test path; static no-quota and no-logging scans now recurse into `adapters/`); `test_m3_mdl_api.py` (`/status` assertions compare the key fields only, since the response gained `egress`).
- **New tests:** `tests/unit/test_m4_egress.py` (148, no database: address, endpoint and allowlist tables; real loopback sockets for pinning, rebinding, redirects, size, slow replies, retries, proxies, TLS/SNI and certificate failures; adapter build/classify; outcome mapping; log hygiene); `tests/integration/test_m4_connection_tests.py` (12, PostgreSQL: authorization, lifecycle with blank-secret and rotation proof, failure classes, egress failures, gates, transaction shape, stale results, orphan expiry, lost authority, cooldown and cap, stored-row contents).

#### M4 review findings

| Finding | Kind | Action |
| --- | --- | --- |
| Baseline before M4 (same gate as below): API 267 passed; browser 12 passed, 1 failed (`test_account_unit_workflows_and_conflicts`, pre-existing since `2c909e3`, see M2) | Baseline | Recorded |
| M2/M3: no blocking integration or security defect found. The runtime INSERT grant on `mdl_connection_tests` is narrower than a default ORM insert | Integration constraint | M4 inserts explicit columns; grant kept |
| `httpcore` DEBUG traces include provider response headers (provider text in logs if DEBUG is enabled) | Security (in scope) | Fixed: logger pinned to WARNING in the app factory; test added |
| Cooldown also blocked a retest right after a configuration fix | Usability (in scope) | Fixed: cooldown applies to the same configuration snapshot only; test added |
| Registration (M3) accepts endpoints the egress policy will always refuse (Unicode hosts, internal hosts not on the allowlist) | Observation | Not changed: the test records `ENDPOINT_BLOCKED`; earlier feedback can be added in M6 |

#### M4 residual risks (not fixed in M4; **status after M5 in brackets**)

- **Internal HTTP** sends a stored secret unencrypted on the internal network (allowed for on-premise servers). Prefer `https` or `NONE` internally. **[Fixed in M5: secrets require https everywhere.]**
- **No port restriction for internal hosts**: an MDL administrator can make the API connect to any port of an allowlisted host and learn reachability from the failure class (no response body is ever returned). Keep the allowlist to dedicated model servers; never list `db`, `api` or `nginx`. **[Fixed in M5: entries are port-scoped.]**
- External tests reveal reachability of public hosts on port 443 to an MDL administrator (failure class and latency only).
- The process cap is per API worker; several workers multiply it. A timed-out DNS lookup thread is abandoned, not killed (bounded by cap and cooldown). **[Fixed in M5: institution-wide cap in PostgreSQL; at most 8 lookup threads.]**
- Python cannot wipe the plaintext secret from memory; references are dropped right after the request.
- Internal HTTPS with a private CA fails with `TLS_ERROR` (no CA setting yet); some models reject `max_tokens` (`REQUEST_REJECTED`; needs another adapter). **[Fixed in M5: `AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE`; style `OPENAI_COMPATIBLE_V2`.]**
- If an agreement is withdrawn or a model/provider deactivated **while** a test runs, the result is still recorded; M5 eligibility must check those conditions at selection time. **[Resolved in M5: selection and use re-check every condition.]**
- **Genuine provider verification is pending** (FR-MDL-020 AC1 evidence): needs a PO/TL-supplied provider and explicit authorization for a live, possibly billed, call.

#### M4 verification

| Check | Command | Result |
| --- | --- | --- |
| Baseline before M4 | `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv>/bin/python AQ_NGINX=<wrapper> bash scripts/verify_phase2.sh` | Static checks PASS; **API 267 passed**; browser 12 passed, 1 failed (pre-existing) |
| Full gate with M4 (assets, sidebar, `node --check`, Ruff ×2, Compose render, fresh cluster, `alembic upgrade head` + `check`, API and browser suites) | same | Static checks PASS (Compose render includes the new api-only variable); `alembic check` "No new upgrade operations detected" (M4 has no migration); **API 426 passed** (267 + 147 egress unit + 12 PostgreSQL); **browser 12 passed, 1 failed**: the same pre-existing `test_account_unit_workflows_and_conflicts` (Playwright strict mode, "Chờ kích hoạt" in an `<option>` and a badge), **not an M4 regression** |
| Unit suite after the final added test | `pytest apps/api/tests/unit` | **298 passed** (includes `test_m4_egress.py`: 148) |
| M3 + M4 PostgreSQL tests (focused) | `pytest tests/integration/test_m3_mdl_api.py tests/integration/test_m4_connection_tests.py` on a disposable cluster | 20 passed |

Evidence category: automated, disposable private PostgreSQL 18, loopback-only fake providers. **No live provider call** (pending; needs a supplied provider and explicit authorization). No live Compose run was repeated for M4 (only an environment variable was added; the rendered-configuration check passes). No hosted CI and no acceptance evidence.

## M5 — Routing, versions and deactivation guards

- **FRs:** FR-MDL-021, FR-MDL-012. **Depends on:** M4. **Needs:** D9 and D13 approved.
- **Files:** `mdl/routing.py`, routes, revisions.
- **Invariants:** `expected_revision` optimistic control; lock order from the architecture; revision and audit in the same transaction; no-op PUT creates no revision; failed retest does not silently change an existing route; DPA withdrawal keeps the route but invalidates future eligibility and warns.
- **Tests:** eligibility matrix; unchanged-slot rule; no-op; conflict; two-thread races (PUT vs PUT, PUT vs deactivate, rotation vs PUT); atomicity; two changes → two readable revisions; deactivate-after-switch.
- **Excluded:** multi-fallback, diff UI, gateway.
- **Gate:** race tests stable over repeated runs.

### M5 plan review (2026-11-26)

The planned scope was kept and extended on the owner's instruction to resolve every open M3/M4 problem. Changes (rationale in the [M5 decision record](MDL_OPEN_DECISIONS.md#m5-decision-record-2026-11-26)):

1. **D5, D9, D13 decided** under delegation. D9 is split into *route persistence* (no automatic change; unchanged slots are not re-validated) and *permission to use* (fail closed, re-evaluated on every read, with an `effective` route). D5 serving after withdrawal: fail closed.
2. **Migration `0006_mdl_routing_and_styles`**: `decision_reference` column plus a widened `api_style` check for `OPENAI_COMPATIBLE_V2`. The plan's M5 file list had no migration.
3. **One eligibility function** (`queries.routing_issues`) feeds the selection list (`routing_eligible` filter, `ModelOut.routing`), `PUT /routing` and slot usability. Eligibility adds a readable credential and the present egress policy to the architecture's list.
4. **New allowlisted error detail** `reasons` for `MDL_NOT_ELIGIBLE`.
5. **M3/M4 fixes** folded in: https for every secret-bearing provider, port-scoped allowlist, institution-wide test cap, audited charge acknowledgement, DNS thread cap, internal CA file, V2 API style, stricter registration endpoint check, rewrap operator command (was M7), provisioning column-subset grants, and the pre-existing browser test race.

### M5 completion (2026-11-26)

**Status: implemented, awaiting independent review. Not accepted by a Tech Lead or Product Owner.** No FR-MDL acceptance criterion is fully satisfied (UI parts are M6; no live-provider run exists); see the [traceability M5 evidence](MDL_REQUIREMENTS_TRACEABILITY.md#m5-evidence-2026-11-26-automated-and-docker-smoke-awaiting-independent-review).

- **Delivered:** `mdl/routing.py` (`GET`/`PUT /routing`, `GET /routing/revisions`, `effective_model_id` for a future gateway); `queries.routing_issues`, `ModelOut.routing`, `?routing_eligible=`; `usage.lock_routing` with an institution advisory lock; audit `mdl.routing_changed`; migration `0006`; error detail `reasons`; `mdl/rewrap.py` + CLI `python -m aq_uai_api.db.mdl_rewrap` with operator audit `mdl.credential_rewrapped`; egress changes (port-scoped allowlist, credential-requires-TLS, CA file, lookup-thread cap); `testing.py` institution-wide cap and acknowledgement audit; `service.py` transport and endpoint checks at registration; `provision.present_privileges`; setting `AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE` (Compose api only, verifier, `.env.example`); admin audit labels.
- **Not delivered (by design):** UI (M6); per-assistant routing (D8 decided institution-wide); ordered multi-fallback (Could); version diff view (Should); an AI gateway (only the `effective_model_id` entry point exists).
- **Existing tests edited (and why):** head pins (`test_wp1_schema.py`, `tests/browser/test_operations.py`) to `0006`; `test_m3_contracts.py` route set; `test_m4_egress.py` allowlist entries now carry ports, the TLS seam takes the optional CA file, and new cases were added; `test_m4_connection_tests.py` now uses the shared HTTPS fake provider (`integration/fake_provider.py`) because a secret is no longer sent over plain HTTP; `tests/browser/test_admin.py` now waits for the user detail heading before checking the status badge (pre-existing failure since `2c909e3`: the assertion raced the navigation; passed in 3 consecutive isolated runs).
- **New tests:** `tests/integration/test_m5_routing.py` (15), `tests/unit/test_m5_contracts.py` (6), and new cases in `test_m4_egress.py`.

#### M5 review findings

| Finding | Kind | Action |
| --- | --- | --- |
| A refusal could list 16 reasons, exactly the `used_in` detail limit; one more issue code would have turned a 409 into a 500 | Defect (in scope) | Fixed: `reasons` has its own bound (48); a unit test builds the worst case from the code list |
| `provision prepare` failed on a `0005` database because a grant named the not-yet-created `decision_reference` column (it runs before `migrate`) | Defect (found by the new upgrade test) | Fixed: `present_privileges` grants existing columns only; populated-upgrade and unit tests added |
| Revision ID `0006_mdl_routing_reference_styles` was 33 characters; `alembic_version.version_num` holds 32 | Defect (caught before release) | Renamed `0006_mdl_routing_and_styles`; a unit test now checks every revision ID |
| Mutation check: disabling new-slot validation or slot usability makes 3 M5 tests fail | Test strength | Recorded |
| The pre-M5 baseline gate run in this session was invalidated by editing the migration while it ran | Process | The last M4 gate (same code) is used as baseline; no edits during later gate runs |

#### M5 residual risks

- **No live provider has been called** (FR-MDL-020 AC1 genuine evidence pending; needs a supplied provider and authorization for a possibly billed call).
- Eligibility is computed per model on reads (several queries per model). Fine for a registry of tens of models; revisit if an institution registers hundreds.
- `effective` is advisory until a gateway exists; any future AI call path **must** use `routing.effective_model_id()` and must not read `mdl_routing` directly.
- Fail-closed use means an outage of the primary's provider (failed retest) or a key-ring mistake stops AI use when no usable fallback is configured. This is intended; operators should configure a fallback on a different provider.
- Python cannot wipe plaintext secrets from memory (unchanged).
- D6, D7 (viewer), D11 and the legal confirmation of D5 remain PO/Legal matters.

#### M5 verification

| Check | Command | Result |
| --- | --- | --- |
| Baseline (pre-M5 code = final M4 code) | last M4 gate, `verify_phase2.sh` | API 426 passed (unit 298 after the last M4 test); browser 12 passed, 1 failed (pre-existing). A re-run started at the beginning of M5 was **invalid** (files edited during the run) and is not used |
| Full gate with M5 (assets, sidebar, `node --check`, Ruff ×2, Compose render, fresh cluster, `alembic upgrade head` + `check`, API and browser suites) | `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv>/bin/python AQ_NGINX=<wrapper> bash scripts/verify_phase2.sh` | Static checks PASS; `alembic check` "No new upgrade operations detected"; **API 469 passed**; **browser 13 passed, 0 failed**; exit 0 |
| Unit suite | `pytest apps/api/tests/unit` | 325 passed (included above) |
| M5 PostgreSQL tests | `pytest tests/integration/test_m5_routing.py` | 15 passed (included above); mutation check: 3 fail when validation or usability is disabled |
| Fixed browser test, isolated | `pytest tests/browser/test_admin.py -k test_account_unit_workflows_and_conflicts` | passed 3 of 3 runs |
| Docker Compose smoke (disposable project `aq-m5-check`, synthetic `.env`, fake provider container, removed with `down -v`) | `~/.cache/aqm5/compose-smoke.sh` (outside the repository) | `up` 0; `verify_wp2_compose.py --live` PASS; bootstrap ok; 14/14 driver checks PASS (connection test PASSED over the Compose network; egress refused `db`, `api`, `169.254.169.254` and an unlisted port; secret over HTTP refused; routing revision 1; effective PRIMARY; deactivation guard); rewrap CLI exit 0; schema `0006_mdl_routing_and_styles`; `down` 0 |

Evidence categories: automated tests (disposable PostgreSQL 18, loopback fake providers) and a local Docker smoke run. **No live provider call, no hosted CI and no acceptance.** The smoke run pulled the public `python:3.12-slim` image for the fake provider.

## M6 — Admin UI

- **FRs:** FR-MDL-001 UI and every screen. **Depends on:** M5.
- **Files:** `apps/admin/assets/mdl.mjs`, registration in `pages.mjs`/`app.mjs`, `api.mjs` messages, `admin.css`. Menu title "Cấu hình Nhà cung cấp & Mô hình AI"; tabs for providers, models, routing and fallback, data-protection agreements, history.
- **Invariants:** secret field never prefilled and `autocomplete="new-password"`; cost notice; "no legal review" notice; where-used message; empty states; no excluded fields (FR-MDL-040); CSP unchanged; `apps/web` untouched.
- **Tests:** Playwright (capability-driven navigation, empty list, no excluded fields, blank-secret edit, test result, routing conflict, mobile width, keyboard dialogs); `node --check`; asset verifier.
- **Gate:** browser suite and Chrome captures reviewed.

### M5 closeout (2026-11-26)

Re-verified at the start of M6 with no code change since the M5 gate: full `verify_phase2.sh` **API 469 passed, browser 13 passed, exit 0**. No blocking defect was found in M1–M5. Outstanding decisions were resolved in the [M6 decision record](MDL_OPEN_DECISIONS.md#m6-decision-record-2026-11-26): D6 (internal risk criteria), D7 (viewer deferred beyond V1), D11 (retention policy per category), D12 (no framework dependency), D5 wording (project policy, not legal approval). Quota-isolation evidence was strengthened and live-provider verification prepared ([runbook](MDL_LIVE_PROVIDER_VERIFICATION.md), not run).

### M6 plan review (2026-11-26)

Scope kept (one `#mdl` page, tabs, dialogs). Changes:

1. **Small router extension** (`#mdl/<tab>[/<uuid>]`) instead of "no router change": provider and model details need addressable views (back links, browser history).
2. **Shared UI helpers extended minimally:** `formDialog` passes the form (checkbox groups) and may return a confirmation message; submitted `secret` values are cleared like passwords; `RequestError` keeps only allowlisted error `details`.
3. **Browser test harness:** `Stack.api_env` and an `mdl_stack` fixture (key ring, port-scoped allowlist, test CA, loopback HTTPS fake provider loaded from the API test helper, so there is one copy).
4. **External test in the browser is intercepted** (Playwright route) so the cost-acknowledgement contract is verified with no DNS lookup or outbound request.

### M6 completion (2026-11-26)

**Status: implemented, awaiting independent review. Not accepted by a Tech Lead or Product Owner.** See the [traceability M6 evidence](MDL_REQUIREMENTS_TRACEABILITY.md#m6-evidence-2026-11-26-automated-api-and-browser-awaiting-independent-review).

- **Delivered:** `apps/admin/assets/mdl.mjs` (routing status and change dialog with eligibility reasons, effective route and system status; providers with create/edit/state, write-only secret, agreements with record/withdraw and the "no legal review" notice; models with create/edit/state, risk with D6 guidance, connection test with mandatory cost acknowledgement for external providers, test history; agreements overview; routing history); registration in `pages.mjs`, router in `app.mjs`, error details in `api.mjs`, `formDialog`/secret handling in `ui.mjs`, styles in `admin.css`. Opt-in `tests/live/test_live_provider.py`; quota write-set test; import-closure test; runbook.
- **Not delivered (by design):** a read-only viewer experience (D7 deferred); diff view of versions (Should); multi-fallback (Could); live-provider evidence (pending authorization).
- **Existing files edited (and why):** `admin.css` top bar (`.session { flex: none }`, title may shrink) because long section titles pushed the session menu off narrow screens (latent Phase 2 defect, found by the M6 mobile check); home-page wording made generic (no longer "directory only"); `tests/browser/conftest.py` (`api_env`, `mdl_stack`); `pyproject.toml` (`live_provider` marker).

#### M6 review findings

| Finding | Kind | Action |
| --- | --- | --- |
| Agreement "Căn cứ" select had no initial value, so the form could never be submitted | Defect (found by the browser test) | Fixed: defaults to the first basis |
| At 390 px the long section title pushed the session menu 7 px beyond the screen | Usability defect (shell, latent since Phase 2) | Fixed in `admin.css`; regression check in the M6 browser test |
| CSP blocks injected inline styles (confirmed while diagnosing) | Security check | Kept unchanged; no inline styles or `innerHTML` in M6 code |
| Secret handling: no prefill, cleared after submit, never in page HTML or input values after save/edit/rotation | Security check | Covered by `assert_secret_never_shown` |
| Error details: only allowlisted identifier lists reach the UI and are mapped to fixed text | Security check | `safeDetails` in `api.mjs` |
| Routing and provider pickers load at most 100 entries | Usability limit | Recorded (registries are small; paging can be added if needed) |

#### M6 residual risks and external dependencies

- **Live provider run pending** (FR-MDL-020 AC1 genuine evidence).
- **Quota end-to-end proof** needs QTA/CRT; current evidence is static plus the database write-set test.
- **Legal / school inputs:** official risk criteria (OQ-09-01), statutory retention periods, legal confirmation of the D5 reading. Current behaviour is project policy.
- No viewer role: Board members need an MDL administrator to show the configuration (D7).
- UI pickers are capped at 100 items.

#### M6 verification

| Check | Command | Result |
| --- | --- | --- |
| Baseline (start of M6, code = M5) | `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv>/bin/python AQ_NGINX=<wrapper> bash scripts/verify_phase2.sh` | Static checks PASS; API **469 passed**; browser **13 passed**; exit 0 |
| First full gate with M6 | same | API 471 passed, 1 skipped (opt-in live check); browser 14 passed, **1 failed**: `test_scoped_roles_filters_navigation_and_safe_text` pinned the home-page sentence I had reworded. **Regression introduced in M6, fixed** by restoring the original sentence |
| Browser suite rerun (isolated) | `pytest tests/browser` | 14 passed, 1 setup **error**: the bootstrap seed subprocess timed out (30 s) under host load (editor, Chrome and a separate developer Compose stack were running). Environmental; no application code had run |
| **Final full gate** | same as baseline | Static checks PASS (assets, sidebar, `node --check` on all admin modules, Ruff ×2, Compose render); `alembic check` "No new upgrade operations detected"; **API 471 passed, 1 skipped**; **browser 15 passed, 0 failed**; exit 0 |
| M6 browser tests | `pytest tests/browser/test_mdl.py` | 2 passed (included above) |
| Quota write-set test | `pytest tests/integration/test_m6_quota_isolation.py` | 1 passed (included above) |
| Docker Compose smoke (disposable project `aq-m6-check`, synthetic `.env`, fake provider container, `down -v`) | `~/.cache/aqm6/compose-smoke.sh` (outside the repository) | `up` 0; live credential isolation PASS; 16/16 driver checks PASS, including nginx serving `mdl.mjs` as JavaScript and the unchanged admin CSP; rewrap CLI 0; schema `0006_mdl_routing_and_styles`; `down` 0; no containers left |

Evidence categories: automated tests (disposable PostgreSQL 18, loopback fake providers, Chromium through nginx) and a local Docker smoke run. **No live provider call, no hosted CI, no acceptance.** Browser screenshots are produced only when `AQ_BROWSER_SCREENSHOTS` is set (not set in these runs).

## M7 — Acceptance, security review and handoff

- **Scope:** fill the traceability and acceptance matrices with evidence; full PostgreSQL, browser, upgrade and restore runs (including key loss and restore with ciphertext); optional Docker Compose run when Docker is available; `docs/phase3/mdl-handoff.md` (including the rewrap command delivered in M5); security review of SSRF, encryption and logs; promote ADR-0003 only after approval.
- **Gate:** Tech Lead acceptance recorded **separately** from developer acceptance. Until then the acceptance matrix stays "not accepted".

### M7 plan review (2026-11-26)

Scope kept. Adjustments: (1) the FRD §6 "Should" history/diff item was **implemented** instead of documented as a limitation, because the typed audit payloads already hold every before/after value (no migration); (2) the M6 "100-entry picker" observation was **fixed** (it was a correctness defect, not only usability); (3) the "restore with ciphertext and key loss" item had no test and got one; (4) the Docker run includes the upgrade path of the developer's real stack (Phase 2 `2c909e3` → current, same volume). ADR-0003 is **not** promoted (needs TL/PO approval).

### M7 completion (2026-11-26)

**Status: implemented and technically verified. Not accepted by a Tech Lead or Product Owner.** Per-requirement status: [traceability, M7 acceptance status](MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26).

- **Delivered:** `mdl/history.py` + `GET /api/v1/mdl/history` (`mdl.read`, own institution, configuration events with typed before/after; schemas `HistoryFilters`, `ConfigurationEventOut`); admin UI configuration history with "field: before → after" lines (history tab, provider and model detail views) and `readAll` paging for pickers (`mdl.mjs`, two CSS rules in `admin.css`); [handoff](mdl-handoff.md); documentation updates (this plan, traceability, decisions, architecture, ADR-0003, project context, acceptance matrix, live-provider runbook).
- **New tests:** `apps/api/tests/integration/test_m7_history.py` (2); `tests/browser/test_mdl_operations.py` (1: `pg_dump`/`pg_restore` of MDL data, restore with the same key, key loss fails closed with nothing sent, recovery by re-entering the secret, backup contains neither secret nor key); `tests/browser/test_mdl.py` extended (history diff assertions; 101-provider picker). Existing test edited: `test_m3_contracts.py` route set gains `/mdl/history`.
- **No migration**, no dependency, no Compose or nginx change; `apps/web/` untouched.

#### M7 review (M1–M6)

| Area | Finding | Action |
| --- | --- | --- |
| Authorization, tenancy | Every route re-checks `mdl.read`/`mdl.manage` at the institution; writes use the shared protected path; foreign rows 404 | No defect |
| Credentials, rotation | AES-GCM with AAD; no plaintext in responses, audit, logs; validation errors never echo input; rewrap per row with operator audit | No defect. Residual: after switching a provider to `NONE` its old ciphertext stays stored (encrypted, unused) until overwritten (M7 decision record) |
| Egress / SSRF, connection test | Pinning, allowlist with ports, https for secrets, no redirects/retries, bounded; DPA and charge gates before any lookup; two transactions | No defect. Gate order: cooldown is checked before decryption (a key-loss refusal can appear as `MDL_TEST_COOLDOWN` within 30 s of a test of the same configuration; harmless) |
| Routing, deactivation guard | Routing lock before provider/model rows; deactivation of a routed model or provider refused with `used_in`; routed model cannot lose TEXT or risk | No defect |
| Audit, retention | Same-transaction typed audit; no DELETE grant on MDL tables | No defect |
| Frontend | Pickers requested one page of 100: entries beyond it were missing, and "Thêm mô hình" from a provider beyond the first 100 preselected a **different** provider | **Defect, fixed** (`readAll`) and tested |
| FRD §6 Should | History/diff not offered (only routing revisions) | **Implemented** |
| Backup/restore | Phase 2 tables only; MDL ciphertext and key loss untested | **Test added** |
| Local stack | Developer's `aq-uai-dev` observed at `0002` (Phase 2 image and database); MDL menu therefore hidden | Not changed by the agent; [update steps](mdl-handoff.md#3-updating-your-existing-aq-uai-dev-stack-to-mdl) |

#### M7 verification

| Check | Command | Result |
| --- | --- | --- |
| Baseline | Last M6 gate; code unchanged since (checked with `find -newer` on the M6 gate log: only this plan changed) | API 471 passed, 1 skipped; browser 15 passed |
| Focused (disposable PostgreSQL 18) | `pytest apps/api/tests/integration/test_m7_history.py`; `pytest tests/browser/test_mdl.py`; `pytest tests/browser/test_mdl_operations.py` | 2 passed; 2 passed; 1 passed (first run failed on the 30 s cooldown inside the test itself; the test now ages test timestamps, product unchanged) |
| **Full gate** (assets, sidebar, `node --check` on all JS, Ruff ×2, Compose render, fresh cluster, `alembic upgrade head` + `check`, API and browser suites) | `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv>/bin/python AQ_NGINX=<wrapper> bash scripts/verify_phase2.sh` | Static checks PASS; "No new upgrade operations detected"; **API 473 passed, 1 skipped**; **browser 16 passed**; exit 0. Delta vs baseline: +2 API (history), +1 browser (restore); no regression |
| Skipped test | `pytest -rs apps/api/tests/live` | `test_live_provider.py`: "Live provider call not authorized (possible provider charges)", as designed |
| Migrations | Included in the API suite: clean database; populated `0001`/`0002` → head (`test_provisioning_is_repeatable_and_preserves_data`); populated `0003` → `0004`, `0005` → `0006`; browser legacy upgrade from `0001` and from head | All passed |
| Backup / restore | `test_backup_restores_history_and_runtime_writes` (Phase 2), `test_restore_keeps_ciphertext_usable_and_key_loss_fails_closed` (MDL) | Passed |
| Docker Compose A: clean install (disposable `aq-m7-clean`, synthetic env, fake provider container, `down -v`) | `~/.cache/aqm7/compose-m7.sh` (outside the repository) | `up` 0; live credential isolation PASS; 20/20 driver checks PASS (MDL flow, egress refusals for `db`, `api`, metadata, other port; history; foundation admin 403; CSP); rewrap CLI 0; schema `0006`; `down` 0 |
| Docker Compose B: **Phase 2 → M7 upgrade** on one volume (`aq-m7-upgrade`) | same script, `SKIP_A=1` | Phase 2 stack `0002`, bootstrap and a unit created; current tree `up --build` 0 → schema `0006`; credential isolation PASS; Phase 2 unit, password and audit preserved; 22/22 checks PASS; second `up` keeps `0006`; `down` 0; no container or volume left. A first attempt failed because the rehearsal script extracted the old tree with mode 600 files (non-root image user could not read them); fixed in the script, not a product issue |
| Developer stack | `docker ps`, read-only queries | `aq-uai-dev` untouched (containers from 2026-11-25, still `0002`) |

Evidence categories: automated tests (disposable PostgreSQL 18, loopback fake providers, Chromium through nginx) and local Docker runs. **No live provider call, no hosted CI, no acceptance.**

#### M7 addendum: synthetic demo provider (D15, 2026-11-26)

The Project Owner decided that this demo project needs no real AI vendor ([D15 record](MDL_OPEN_DECISIONS.md#d15-record-synthetic-demo-provider-2026-11-26)).

- **Delivered:** `infra/demo-provider/server.py` (OpenAI-compatible HTTPS server, own CA per start, key check by Bearer or `X-Api-Key`, models `demo-chat`/`demo-chat-mini`, 401/404 failure replies, logs method/path/status only); `infra/compose.demo-provider.yaml` (opt-in service, no published port, public CA shared read-only with `api`, allowlist `demo-provider:8443`); `scripts/dev-up.sh --demo-provider`; `scripts/dev-down.sh` now uses `--remove-orphans`; `.env.example` documents `AQ_DEMO_PROVIDER_API_KEY`; `verify_phase2.sh` lints the server; handoff section 3a and a manual checklist built on it. **No product code changed.**
- **Tests:** `apps/api/tests/unit/test_demo_provider.py` (9: the real adapter + egress path gives PASSED for Bearer, V2 style and header key; `AUTH_FAILED` for a wrong or missing key; `MODEL_NOT_FOUND`; `TLS_ERROR` without the CA; CA file public only; short keys refused).
- **Compose (disposable `aq-m7-demo`, base + override, `~/.cache/aqm7/compose-demo.sh`):** 13/13 PASS (see the [runbook](MDL_LIVE_PROVIDER_VERIFICATION.md#demo-scope-synthetic-provider-d15)); first attempt reported a failure only because the driver retested within the 30 s cooldown after restarting the provider (429, product behaviour correct); the driver now waits it out.
- **Developer stack (2026-11-26, with the owner's go-ahead):** `bash scripts/dev-up.sh --demo-provider` on `aq-uai-dev` → exit 0; `provision` and `migrate` exited 0; schema `0006`; `demo-provider` healthy; the API holds the allowlist `demo-provider:8443` and the CA path; a TLS-verified probe from `api` reached the provider (401 without a key, as intended). **Found:** every API call through nginx returned 502 because nginx kept the old `api` address after `api` was recreated (pre-existing Phase 2 behaviour; `web` is never recreated by `up`). Fixed now with `nginx -s reload` (`/ready` → ready) and permanently in `scripts/dev-up.sh` (reload after every `up`).
- **Full gate after the addendum** (same command as the M7 full gate; Ruff now also checks `infra/demo-provider/server.py`): static checks PASS; "No new upgrade operations detected"; **API 482 passed, 1 skipped** (473 + 9 demo-provider tests; the skip is still the opt-in real-vendor test); **browser 16 passed**; exit 0.

#### M7 residual risks and external dependencies

- Compatibility with a real vendor is **not** verified and not required (D15); the optional procedure stays in the [runbook](MDL_LIVE_PROVIDER_VERIFICATION.md#optional-real-vendor-verification-not-required-by-d15).
- FR-MDL-020 AC3 end to end needs QTA/CRT; future AI calls must use `routing.effective_model_id()`, and QTA/CRT must register where-used checks.
- Official risk criteria (OQ-09-01), statutory retention periods, legal confirmation of the D5 reading.
- Key ring custody is operational: losing it loses stored secrets (recovery = re-entry, rehearsed).
- No viewer role (D7); Python cannot wipe plaintext secrets from memory; stale ciphertext after a switch to `NONE`.
- Eligibility is computed per model on reads (fine for tens of models).

## Housekeeping findings

- Three **untracked** root-level files `AQ-FRD-UAI-CRT-001.md`, `AQ-FRD-UAI-MDL-001.md`, `AQ-FRD-UAI-QTA-001.md` are byte-identical to the tracked `docs/frd/` copies (checked with `cmp` on 2026-11-25). `docs/frd/` is canonical. M0 **preserved** them unchanged; the developer decides whether to delete or ignore them.
- `docs/acceptance-matrix.md` and `README.md` were not edited in M0 (outside the document list); update the matrix when M1+ produce evidence.
- `AGENTS.md` was not edited; it still requires separate authorization for Phase 3 server logic.
- The local deployment evidence gap is recorded in the [local deployment note](../phase2/local-deployment-note.md).
