# MDL architecture and decisions

**Status:** proposed design (M0), with **M1–M7 implemented and technically verified, not formally accepted**: access (M1), schema, encryption and grants (M2), provider/model/agreement/risk APIs (M3), egress and real connection test (M4), routing and fail-closed use (M5), the admin UI (M6), and the M7 closeout (configuration history with diff, picker paging fix, backup/restore and upgrade rehearsals; see the [M7 completion](MDL_IMPLEMENTATION_PLAN.md#m7-completion-2026-11-26)). Decisions D1–D14 are taken under the project owner's delegated authority, with D6 and D11 as internal project policy ([decision records](MDL_OPEN_DECISIONS.md#m6-decision-record-2026-11-26)); no Tech Lead, Product Owner, legal or school sign-off exists. Operations and manual acceptance: [handoff](mdl-handoff.md). It extends the existing Phase 2 foundation and creates no second auth/authorization/audit stack. The shorter formal record is [ADR-0003](../architecture/ADR-0003-mdl.md). Sequencing is in the [implementation plan](MDL_IMPLEMENTATION_PLAN.md).

Labels: **SPEC** FRD-specified · **REC** technical recommendation · **PROV** provisional assumption · **APPR** needs Product Owner (PO) / Tech Lead (TL) approval. No formal TL or PO sign-off exists for any item.

## 1. Where MDL plugs into the existing code

| Need | Reuse (existing) | Required extension (hidden requirement) |
| --- | --- | --- |
| Session, CSRF, Origin | `require_authenticated_write`, `read_authority` (`authorization/dependencies.py`) | none |
| Transaction-time authority | `resolve_write_authority` → `ActorAuthority` (`authorization/writes.py`) | none |
| Permission catalog | `PermissionCode` enum, `policy.py` | Unknown catalog permissions are silently ignored: add `mdl.read`, `mdl.manage` to the enum |
| Scope rules | `_CENTRAL_PERMISSIONS`, `_ROLE_SCOPES` (`policy.py`) | Register MDL codes/role here so authority is direct and GLOBAL only |
| Role-assignment DB checks | role-specific `ck_*` constraints on both assignment tables (`db/identity.py`) | Additive constraint for `AI_MODEL_ADMIN`; keep SQLAlchemy metadata aligned so `alembic check` is clean |
| Audit | `write_audit_event`, `_EVENT_RULES` (`db/audit.py`) | MDL actions and typed payload models; Vietnamese labels in `pages.mjs` |
| Errors | `DomainError(ErrorCode)` (`api/errors.py`) | New MDL codes and an allowlisted `details` field (FR-MDL-012 must name where a model is used) |
| Write wrapper | `protected()`, `WriteContext`, `record()` in `directory/service.py` (module-private) | Move to a shared module and re-export; do not copy or import across modules; WP5 tests are the regression net |
| Cache headers | `_PRIVATE_API_PATHS` (`api/errors.py`) | Add `mdl` |
| Schema pin and grants | `db/schema.py::REQUIRED_SCHEMA_REVISION`, `db/provision.py` | Bump revision; column-level grants for MDL tables |
| Packaging | `pyproject.toml` | Runtime `cryptography` (M2) and `httpcore` (M4; used directly for the pinned network backend, see section 6). `httpx` stays dev-only |
| Admin UI | `formDialog`, `listing`, `field`, `facts`, `badge`, section registry in `apps/admin/assets/` | **M6:** `mdl.mjs`, one `#mdl` section with tabs and detail views; a small router extension for `#mdl/<tab>[/<id>]`; `formDialog` passes the form and an optional confirmation message; `RequestError` keeps allowlisted `details` |

Docker note (REC): inside the Compose network `http://localhost:11434` refers to the API container itself. On-premise providers need a reachable service name or `host.docker.internal` plus an explicit server-side allowlist (section 6).

## 2. Domain model and database

All tables follow the Phase 2 pattern: UUID primary keys, `institution_id` with composite foreign keys, `timestamptz`, named constraints, and **no `DELETE` grant**. Delivered as additive Alembic migrations `0003_mdl_access_catalog` (M1) and `0004_mdl_schema` (M2, ORM in `mdl/models.py`); tables are empty after upgrade (no seeded vendors). All of this is **REC** unless the FRD constrains it. Columns marked *deferred* are not in `0004`; they are additive when their decision is taken.

| Table | Purpose and key columns | Mutable columns |
| --- | --- | --- |
| `mdl_providers` | name (unique per institution, case-insensitive), `provider_type` `EXTERNAL`/`INTERNAL` (**immutable**), `api_style` (`OPENAI_COMPATIBLE`; `OPENAI_COMPATIBLE_V2` added in M5 / `0006`), `endpoint` (http/https, no userinfo or whitespace), `auth_scheme` (`BEARER`/`HEADER_KEY`/`NONE`, D2 decided), `auth_header_name` (only for `HEADER_KEY`), `active`, `connection_version` | name, endpoint, api_style, auth scheme and header, active, version |
| `mdl_provider_credentials` | one row per provider (primary key `provider_id`): `ciphertext`, `nonce` (12 bytes), `key_id`, `credential_version`, `updated_by`; never mapped to a response model | ciphertext, nonce, key ID, version |
| `mdl_provider_agreements` | `basis`, `document_number`, optional `signed_on`, recorded by/at; external providers only (composite FK on `provider_type`). Withdrawal lives in its own table (below) | **none** (INSERT-only) |
| `mdl_provider_agreement_withdrawals` | M3, migration `0005`: one row per withdrawn agreement (primary key `agreement_id`), withdrawn by/at. In force = latest agreement without a withdrawal (D5) | **none** (INSERT-only) |
| `mdl_models` | provider, `technical_id` (**immutable**, unique per provider), display name, capabilities as `supports_text/image/voice` (at least one), `max_output_tokens`, nullable `risk_level`, `active`. `risk_basis_reference` *deferred* (D6) | display name, capabilities, tokens, risk, active |
| `mdl_connection_tests` | status `RUNNING`/`PASSED`/`FAILED`, `error_code`, HTTP status class, latency, snapshot of connection and credential versions; no response body; one `RUNNING` per model | completion columns once |
| `mdl_routing` | institution-wide singleton (primary key `institution_id`, D8 decided): primary, fallback, `revision`, `updated_by`; `CHECK primary <> fallback`; fallback null if primary null | primary, fallback, revision |
| `mdl_routing_revisions` | append-only: revision number (unique per institution), actor, time, before/after IDs and display-name snapshots. `decision_reference` (optional, D13 decided, added in M5 / migration `0006`) | **none** (INSERT-only) |

State rules: provider and model are `active ↔ inactive`; a test moves `RUNNING → PASSED|FAILED` once; routing revisions are monotonic. "Current test" is derived: the latest finished test whose version snapshot equals the provider's present `connection_version` and `credential_version` (material changes: endpoint, API style, auth scheme, credential rotation). No cache flag that can drift.

Retention (D11, project policy since M6): audit, agreements, withdrawals and routing history for the life of the system; connection tests at least 24 months; credentials overwritten on rotation; no application deletion path. Statutory periods from the school override this; **no legal compliance is claimed**.

Honest limit (REC): the runtime database login must read ciphertext to decrypt it, so database-level secrecy rests on "ciphertext only in PostgreSQL, key elsewhere" plus application-layer isolation. A second database role for secrets was considered and rejected as disproportionate; recorded as an alternative.

Audit actions (REC): `mdl.provider_created/updated/state_changed/credential_rotated`, `mdl.agreement_recorded/withdrawn`, `mdl.model_created/updated/state_changed/risk_changed` (M3), `mdl.model_connection_tested` (M4: test ID, status, code, HTTP class, latency, version snapshot), `mdl.routing_changed` (M5: revision, before/after IDs, decision reference), operator event `mdl.credential_rewrapped` (M5). Payloads hold names, IDs and enum values only. The endpoint is logged as scheme+host+port. Never log secrets, endpoint userinfo, provider response text or key material (**SPEC**, RULE-MDL-04).

## 3. Permissions

- Two permissions only (**REC**, D7): `mdl.read` and `mdl.manage`. The Blueprint's five finer codes are rejected for now: the FRD asks for one edit-equivalent right, and finer splits add role-matrix, UI and test surface. A later split is additive.
- One role now: **`AI_MODEL_ADMIN`**, carrying both permissions, **direct GLOBAL grant only** (REC/APPR). Group-derived MDL authority is structurally impossible.
- **`FOUNDATION_ADMIN` and `AI_SPECIALIST` groups confer no MDL authority.** The first MDL admin is assigned by a `FOUNDATION_ADMIN` through the existing role-assignment UI (two-step bootstrap, intentional least privilege).
- **`AI_MODEL_VIEWER` is deferred beyond V1** (D7 decided under delegation in M6: no demonstrated need). `mdl.read` is still defined so the viewer role later needs only a new role row, not new code paths.
- Anonymous requests receive 401; authenticated without permission receive 403 (existing semantics). The UI hides write controls without `mdl.manage`, but the server is the authority.
- `audit.read` is GLOBAL-only and distinct, so MDL needs its own history endpoints (routing revisions, test history, agreements).

## 4. Credential encryption

Implemented in M2 (`mdl/credentials.py`); **decided under delegated authority (D14)**.

- **AES-256-GCM** through the maintained `cryptography` library (`AESGCM`), random 96-bit nonce, **AAD** binding, length-prefixed, `purpose/v1 | institution_id | provider_id | endpoint origin | credential_version | key_id`. A database-level tamper of the endpoint, a copy between providers or tenants, a version rollback or a key relabel therefore fails decryption closed. Fernet was considered (simpler, no AAD) and rejected. No custom primitives.
- **Key outside PostgreSQL:** key ring `AQ_UAI_MDL_CREDENTIAL_KEYS` (`key_id:base64(32 bytes)`, comma-separated) and `AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID`, supplied only to the `api` service. `provision` and `migrate` refuse to run if they can see either variable, and the Compose verifier fails if another service receives them. Placeholder values are rejected at use. `.env.example` carries a placeholder and a generation command; real keys are never committed.
- **Rotation:** add a key ID, move the active ID, keep old keys for reads, `KeyRing.rewrap` each stored row (runtime grants allow it), then retire the old key. The operator command that walks every row is deferred to M3. Admin credential rotation bumps `credential_version`.
- **Missing or invalid key:** the application still starts and `/ready` is unchanged (Phase 1 contract). Operations that need decryption return 503 `MDL_CREDENTIAL_UNAVAILABLE`; the provider shows `credential_status=UNREADABLE`.
- **Rotation command (M5):** `python -m aq_uai_api.db.mdl_rewrap` in the `api` container rewraps every credential not under the active key (operator audit event `mdl.credential_rewrapped`, counts-only output); afterwards the old key can be removed.
- **Key loss:** ciphertext is unrecoverable by design; recovery is re-entering each secret. Backups hold ciphertext only, so the key must be backed up separately and a restore must be rehearsed.
- Plaintext exists only inside the connection-test service's memory and is never placed in exceptions, return objects, logs or audit rows.
- Secret input uses `SecretStr`; edit forms never receive a stored secret (SPEC); blank on edit keeps the stored value (SPEC); a changed endpoint origin requires re-entering the secret, so a stored secret cannot be redirected to a new host (REC).

## 5. Provider adapters and the connection test

**Implemented in M4** (`mdl/adapters/`, `mdl/testing.py`, routes `GET`/`POST /models/{id}/connection-tests`). D1, D3 and D4 are decided under delegation; the exact choices, including the failure-code list, cooldown semantics, the `acknowledge_provider_charges` flag and the `ABORTED`/`EXPIRED`/`STALE_CONFIGURATION` states, are in the [M4 decision record](MDL_OPEN_DECISIONS.md#m4-decision-record-2026-11-25). The bullets below are the original design; where M4 refined them the decision record wins.


- **One adapter initially: `openai_compatible`** (POST `{endpoint}/chat/completions`, fixed one-message body, small `max_tokens`, no institutional data). This is a **provisional assumption** (D1, D2) chosen for broad compatibility, not a vendor decision. Adding another API style is one new class plus an `api_style` value.
- **Text-only test (PROV, D3).** Image and voice models can be registered but are `TEST_UNSUPPORTED` and therefore not routable initially. The system must not claim image or voice testing.
- PASS requires a 2xx status **and** a body of the expected shape, which proves model access rather than mere reachability. Provider response bodies are discarded. Failure classes: `AUTH_FAILED`, `MODEL_NOT_FOUND`, `RATE_LIMITED`, `TIMEOUT`, `NETWORK_ERROR`, `BAD_RESPONSE`, `ENDPOINT_BLOCKED`.
- **Single attempt, no automatic retries**, plus a per-model cooldown.
- **Cost disclosure (REC/APPR, D4):** the test does not consume the university's or any user's AQ EduUAI allowance (**SPEC**), but an external provider may bill the school's API account. The UI states this before the test.
- **No quota path:** the MDL code imports no quota or credit table (static import test now; functional proof after QTA/CRT exist).
- **Transaction shape:** transaction 1 authorizes, checks gates, decrypts and inserts a `RUNNING` row, then commits; the HTTP call runs **outside** any database transaction (deadline about 20 s, below nginx's 30 s); transaction 2 re-authorizes and finishes the row only if the version snapshot still matches, otherwise records stale. Orphaned `RUNNING` rows expire.
- **Evidence labelling:** tests against a controlled local server prove wire format and the quota-free path. They are **not** genuine provider verification. An opt-in `live_provider` marker (credentials from the operator's environment, minimal request, excluded from CI) provides the real check; FR-MDL-020 acceptance needs one recorded run, which depends on the PO/TL supplying a provider.

## 6. SSRF-resistant egress

**M5 amendments:** every internal allowlist entry names one port (`host:port`, `CIDR:port`, `[IPv6/n]:port`); a secret-bearing provider must use `https`, internal ones included (registration, connect time and eligibility); `AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE` adds an operator CA for internal https; DNS lookup threads are capped at 8; tests in flight are capped per institution in PostgreSQL. See the [M5 decision record](MDL_OPEN_DECISIONS.md#m5-decision-record-2026-11-26).

**Implemented in M4** (`mdl/egress.py`) with `httpcore` and a custom network backend that resolves, validates every address, connects to a validated literal and re-checks the peer; TLS verifies the original host name. Additions to the design below: Unicode host names and numeric host forms are refused instead of converted; IPv6 6to4/Teredo/NAT64 and IPv4-compatible forms are blocked for external providers; loopback for internal providers needs an explicit CIDR; an invalid allowlist blocks every internal destination; each socket operation is capped by the remaining total deadline; encoded (compressed) replies are refused; the `httpcore` logger is pinned to WARNING. Configuration: `AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST` (api service only). Residual risks are listed in the [M4 completion](MDL_IMPLEMENTATION_PLAN.md#m4-completion-2026-11-25).


The connection test makes the server call a URL that an administrator typed, so the policy is part of the design, not an afterthought (REC):

- **External providers:** `https` only; hostname, not IP literal; no userinfo, query or fragment; port 443. Every resolved address must be globally routable (`ipaddress.is_global`); explicitly reject loopback, private, link-local (including `169.254.169.254`), CGNAT, multicast, reserved, IPv4-mapped IPv6 and `0.0.0.0`.
- **Connect-time validation and pinning:** validate the resolved address at connect time and connect to that exact IP while keeping SNI, Host and certificate verification on the original hostname. This closes DNS-rebinding. If effort must shrink, the minimum acceptable fallback is a single resolution, validation, and connection to that IP via `sni_hostname`; a pre-check alone is rebinding-vulnerable.
- **Internal providers:** permitted only when the host or CIDR is on a **server-side allowlist** set by the operator in configuration, never by UI input alone. The metadata and link-local blocklist always wins. This stops the API container from reaching `db`, itself or cloud metadata. There is no test-mode bypass in production code; tests configure the allowlist like an operator would and include a negative test with it unset.
- **Bounded requests:** fixed method and path, **redirects disabled** (3xx is a failure), response read capped (about 64 KB), connect 5 s, read 15 s, total 20 s, **no automatic retries**.
- The credential is sent only to the validated origin, only in the adapter's header, and never logged.
- Tests: IPv4/IPv6/mapped/decimal/octal/hex/IDN/trailing-dot cases, redirect-to-internal, oversize body, slow response, rebinding (public first, private second).

## 7. Routing, DPA gate, risk and concurrency

**Implemented in M5** (`mdl/routing.py`, `queries.routing_issues`, migration `0006`). D5, D9 and D13 are decided under delegation, and the bullets below are amended by the [M5 decision record](MDL_OPEN_DECISIONS.md#m5-decision-record-2026-11-26): an unchanged slot *persists* without re-validation, but *use* is fail-closed: every read re-evaluates both slots, and the effective route is the usable primary, else the usable fallback, else none. After agreement withdrawal the slot stays configured but is unusable (`dpa_missing`). Lock order as listed, preceded by an institution advisory lock so the first configuration is serialized too.


- **Routing (SPEC + REC):** institution-wide singleton; `PUT /mdl/routing` with `expected_revision`. A **new** slot value must be: model and provider active, latest test PASSED and current, external provider has an in-force agreement, risk classified, TEXT capability, credential readable. Fallback differs from primary (service check and `CHECK`). A no-op PUT creates no revision. Every change inserts an append-only revision in the same transaction (actor, time, before/after, optional `decision_reference`). First configuration is revision 1 with `before = null`.
- **"Already being used validly" (PROV/APPR, D9):** a slot value unchanged by the PUT is not re-validated. **Existing-route behaviour after a failed retest is retained**: the route stays and a visible warning appears (no automatic failover exists). New selections always require a current PASSED test. The stricter alternative (always revalidate) is in the decision register.
- **`decision_reference` is provisional (D13)** until the PO approves it; because history is append-only it must be decided before M5.
- **DPA (SPEC + REC):** per external provider, basis `NO_TRAINING_COMMITMENT` or `SCHOOL_WRITTEN_AUTHORIZATION` plus a non-empty document number; no file upload. In force = latest record not withdrawn. **Withdrawal is permitted even when a model is routed (awaiting approval, D5).** It invalidates future eligibility (new tests and new routing selections) and the UI warns about the affected routing; it does not silently clear the route. *Change from the saved plan, which blocked withdrawal while routed.* Whether a routed external model may keep serving after withdrawal is a PO/Legal question (INV-11) and is not decided here. The system records only a document number and performs no legal review; **no legal approval is claimed.**
- **Risk (SPEC):** `HIGH`, `MEDIUM`, `LOW` or unclassified; no default; no vendor defaults; required before routing, not before testing. **M6 (D6):** internal operational criteria are shown in the UI and labelled as guidance, not legal classification; official criteria (OQ-09-01) remain external and will replace them.
- **Deactivation (SPEC + REC):** takes the routing lock, checks a where-used registry (routing only today; QTA/CRT register later, no stub), returns 409 `MDL_MODEL_IN_USE` with `details.used_in`. No hard delete.
- **Lock order (REC):** institution shared lock and account lock (existing) → `mdl_routing` row `FOR UPDATE` → provider rows ordered by ID → model rows. No database lock is held during network I/O.

## 8. API surface (proposed)

All under `/api/v1/mdl` (REC). `GET` needs `mdl.read`; every write needs `mdl.manage`. **M3 implemented** the provider, agreement, model and `/status` rows (`api/v1/mdl.py`, `mdl/service.py`, `mdl/queries.py`, `mdl/usage.py`); the M3 rules are in the [M3 decision record](MDL_OPEN_DECISIONS.md#m3-decision-record-2026-11-25).

| Path | Purpose |
| --- | --- |
| `/providers`, `/providers/{id}`; `PATCH`; `…/activate`, `…/deactivate` | List/detail (never a secret), create with secret, edit with optional secret rotation, state |
| `/providers/{id}/agreements`; `…/{aid}/withdraw` | DPA evidence |
| `/models`, `/models/{id}`; `PATCH` (including `risk_level`); `…/activate`, `…/deactivate` | Registry, filters by provider/active/risk/`routing_eligible` (M5); each model carries `connection_test` (M4) and `routing` eligibility (M5) |
| `/models/{id}/connection-tests` (POST run, GET history) | Real test (**M4 implemented**). `POST` returns 201 with the stored result (PASSED or FAILED); refused gates return 409/422/429/503 and create no row |
| `/routing` (GET, PUT), `/routing/revisions` | Primary/fallback and history (**M5 implemented**). GET adds per-slot `usable`/`issues` and `effective`; PUT needs `expected_revision` and returns 409 `MDL_NOT_ELIGIBLE` with `details.reasons` for ineligible new values |
| `/status` | Key availability and egress-policy summary (M4: allowlist `EMPTY`/`CONFIGURED`/`INVALID` and entry count, never the entries), no secrets |
| `/history` (GET) | **M7:** configuration history, newest first, filter by `target_type`/`target_id`. Rows are the institution's `mdl.*` audit events except connection tests (which have their own history), each with its typed before/after payload projected through `public_audit_changes`; needs `mdl.read` only. Endpoint values appear as origin only (plus `endpoint_changed`), never a secret |

A separate credential endpoint was dropped: edit and rotation happen in one atomic PATCH, avoiding a half-applied "endpoint changed, secret not yet" state. Planned error codes include (M4 added `MDL_TEST_UNSUPPORTED`, `MDL_TEST_COOLDOWN`, `MDL_CHARGES_NOT_ACKNOWLEDGED`) `MDL_DPA_REQUIRED`, `MDL_CREDENTIAL_REQUIRED`, `MDL_CREDENTIAL_UNAVAILABLE`, `MDL_ENDPOINT_BLOCKED`, `MDL_MODEL_IN_USE`, `MDL_NOT_ELIGIBLE`, `MDL_ROUTING_CONFLICT`, `MDL_FALLBACK_EQUALS_PRIMARY`, `MDL_TEST_IN_PROGRESS`, `MDL_DUPLICATE`, `MDL_RISK_REQUIRED`.

## 8a. Admin UI (M6, implemented)

`apps/admin/assets/mdl.mjs`, served under the existing admin CSP. Tabs: **Mô hình chính & dự phòng** (configured slots, `usable` and reasons, effective route, system status), **Nhà cung cấp** (list, create, detail with edit, state, agreements, models), **Mô hình** (list with eligibility filter, create, detail with edit, risk with D6 guidance, connection test and history), **Thỏa thuận dữ liệu**, **Lịch sử thay đổi** (routing revisions and, since M7, the configuration history with "field: before → after" lines; provider and model detail views show their own filtered history). Rules: write controls need `mdl.manage`; secrets are write-only fields; the external test requires the cost acknowledgement; error codes and allowlisted details map to fixed text; nothing is stored in browser storage. No prompt, temperature or template control exists (FR-MDL-040). **M7:** pickers (provider in "Thêm mô hình", eligible models and providers in the routing dialog) page through the API (`readAll`, 100 per request) instead of loading only the first 100 entries.

## 8b. Synthetic demo provider (D15)

`infra/demo-provider/server.py` is a stand-alone OpenAI-compatible HTTPS server used as the provider for demos and FR-MDL-020 verification, by the Project Owner's decision. It runs only when `infra/compose.demo-provider.yaml` is added (`bash scripts/dev-up.sh --demo-provider`): service `demo-provider` (API image, script mounted read-only, no published port), a fresh CA per start whose **public** certificate is shared with `api` through the volume `demo_provider_ca`, and an `api` override that sets the allowlist to `demo-provider:8443` and the CA file. The product code is unchanged: the provider is registered like any internal https provider and goes through the same egress policy, TLS verification, credential and eligibility rules. It is not part of the product and never a production dependency.

## 9. Prototype findings (do not edit `apps/web/`)

- The prototype model card and gateway pane show/enter **Temperature** (`apps/web/module1/module1.js:34`, `apps/web/shared/dialogs.js`, `apps/web/shared/actions.js:107`). FR-MDL-040 forbids it on the real menu. The demo is illustrative, not accepted.
- Sample data in `apps/web/shared/core.js` embeds vendor names, DPA numbers, legal citations and `localhost:11434`. These must never be seeded or hard-coded in live UI or database (FR-MDL-031 AC2).
- Prototype risk labels are Vietnamese strings; live data uses stable codes.

## 10. Challenges to this design

- Two migrations plus a shared-code extraction (M1) add front-loaded work; accepted because mixing catalog changes with new tables obscures review of already accepted WP5 code.
- Connect-time IP pinning needs a custom network backend; the simpler pre-check is rebinding-vulnerable.
- The `RUNNING` row and cooldown are extra machinery; justified by one-in-flight and cost control, droppable for a demo if the TL prefers.
- DPA withdrawal, `risk_basis_reference` and `decision_reference` exceed the literal FRD; each is PROV/APPR and removable without schema churn elsewhere (except `decision_reference`, which must be settled before M5).
- Dedicated MDL history endpoints partly duplicate audit data; needed because `audit.read` is a different right and FR-MDL-021 wants a trail independent of audit access.

## 11. Out of scope

Assistant prompts, temperature, templates; quotas; credits; knowledge base; masking; chat history; payments; model training; ordered multi-fallback (Could); automatic failover or gateway; actual AI invocation; vendor-specific adapters beyond D1; DPA file upload, expiry or approval workflow; QTA/CRT features; token↔credit conversion (undefined).
