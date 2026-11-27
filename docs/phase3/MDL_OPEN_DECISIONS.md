# MDL open decisions (D1–D14)

**Status:** no decision below has formal Product Owner (PO) or Tech Lead (TL) sign-off. On 2026-11-25 the sole project owner **delegated technical and architectural decision authority** to the coding agent for M1 review and M2, and again for M3, M4, M5, M6 and M7; decisions taken under that delegation are marked **Decided (delegated, 2026-11-25)** and recorded in the [M2 decision record](#m2-decision-record-2026-11-25). They are owner-delegated engineering decisions, not TL or PO sign-off, and remain open to review. "Recommendation" is the engineering suggestion; "Reviewer position" records refinements the reviewer supplied for M0 (these are recommendations incorporated into the documents, **not** sign-off). Used by the [architecture](MDL_ARCHITECTURE_AND_DECISIONS.md), [plan](MDL_IMPLEMENTATION_PLAN.md) and [traceability](MDL_REQUIREMENTS_TRACEABILITY.md).

Status values: **Provisional** (work may proceed on the assumption) · **Awaiting approval** · **Unresolved** (blocks a named milestone) · **Reviewer-recommended** · **Decided (delegated)** (taken under the project owner's delegation; see the decision record).

| # | Decision | Source | Recommendation (minimal) | Alternatives | Risk if wrong | Status | Approver | Needed by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | Approved provider types / initial integrations | FR-MDL-010, FRD §1.1 | One generic `OPENAI_COMPATIBLE` adapter; no vendor list | Vendor-specific adapters | Wasted adapter work | **Decided (delegated, 2026-11-25, M4)**: one generic OpenAI-compatible chat-completions adapter behind an `api_style` registry; no vendor list, no vendor defaults. Vendor or other wire formats are additive (one adapter module + one `api_style` value). See the [M4 decision record](#m4-decision-record-2026-11-25) | Project owner (delegated) | M4 (done) |
| D2 | Provider authentication and connection format | FR-MDL-010 | Bearer, header-key (with an operator-named header) or none, plus base URL; one sealed secret per provider | OAuth, cloud IAM | Rework of credential schema | **Decided (delegated, 2026-11-25)**: `BEARER` / `HEADER_KEY` / `NONE`; OAuth and cloud IAM rejected for now (additive later as new `auth_scheme` values) | Project owner (delegated) | M2 (done) |
| D3 | Test semantics for text/image/voice | FR-MDL-020 | **Text only**; image/voice registerable but untestable, hence not routable; no image/voice test claimed | Per-capability probes | Non-text models unusable | **Decided (delegated, 2026-11-25, M4)**: only TEXT-capable models are tested (one fixed text request); a model without TEXT gets 409 `MDL_TEST_UNSUPPORTED` and shows `UNSUPPORTED`; a mixed TEXT+IMAGE model's PASSED result proves text only. No image or voice verification is claimed anywhere | Project owner (delegated); PO may still widen it | M4 (done) |
| D4 | External test cost policy | FR-MDL-020 | Allow; minimal request; cooldown; UI discloses that external tests may incur provider charges although AQ allowance is untouched | Block external tests; spend cap | Unexpected provider charges | **Decided (delegated, 2026-11-25, M4)**: external tests allowed; one minimal request (`max_tokens` 16), single attempt, no retries; 30 s cooldown per model and configuration; at most 4 tests in flight per API process; the API refuses an external test unless the request carries `acknowledge_provider_charges: true` (422 `MDL_CHARGES_NOT_ACKNOWLEDGED`), so every client must show the notice. No spend cap (no prices may be invented) | Project owner (delegated); PO may tighten it | M4 (done; UI notice text M6) |
| D5 | DPA evidence model and withdrawal | FR-MDL-030 | Basis + document number only; no upload, expiry or approver. **Withdrawal permitted even when routed**, invalidating future eligibility and warning about affected routing | Block withdrawal while routed (earlier draft); require approver; expiry | Under/over-building; a routed external model may continue to serve after withdrawal, a legal question for PO/Legal | **Decided (delegated): recording 2026-11-25 (M3); serving 2026-11-26 (M5) = fail closed**: after withdrawal the routed slot stays in the configuration and history, but it is **not usable** (`dpa_missing`) until an agreement is in force again; the fallback is used if it is usable. Legal confirmation of this conservative reading is still advisable (no legal approval claimed) | Project owner (delegated) | M3, M5 (done) |
| D6 | Risk classification evidence (OQ-09-01) | FR-MDL-031 | Three levels + optional `risk_basis_reference`; **no criteria and no vendor defaults invented** | Mandatory basis text | Legal gap | **Decided (delegated, 2026-11-26, M6) as internal operational guidance**: HIGH / MEDIUM / LOW criteria shown in the UI (see the [M6 decision record](#m6-decision-record-2026-11-26)); explicitly *not* a legal classification; unclassified models stay ineligible; no default, no vendor-derived value; `risk_basis_reference` not added (no stored evidence field until official criteria exist). OQ-09-01 (official criteria) remains an **external** dependency | Project owner (delegated); school/legal for official criteria | M6 (done) |
| D7 | Permission mapping and Board read access | FR-MDL-001 | `mdl.read` + `mdl.manage`; role `AI_MODEL_ADMIN` direct GLOBAL only; **`AI_MODEL_VIEWER` deferred** until Board read access is approved; `FOUNDATION_ADMIN`/`AI_SPECIALIST` confer nothing | Five finer permissions; viewer role now | Authorization rework | **Decided (delegated, 2026-11-26, M6)**: two permissions and `AI_MODEL_ADMIN` as built; **`AI_MODEL_VIEWER` deferred beyond V1** (no demonstrated requirement: the FRD has the Board decide outside the system and only the document number is recorded, which the MDL administrator enters as `decision_reference`). Adding it later is additive (role row + `mdl.read` grant; the UI already hides writes without `mdl.manage`) | Project owner (delegated) | V1 (done); viewer: future, on demonstrated need |
| D8 | Routing scope | FR-MDL-021 | Institution-wide singleton | Per-assistant or per-unit | Schema rework | **Decided (delegated, 2026-11-25)**: one `mdl_routing` row per institution (primary key `institution_id`) | Project owner (delegated) | M2 (done) |
| D9 | "Already being used validly" | FR-MDL-021 | Unchanged slot is not re-validated; **existing route is kept after a failed retest** with a visible warning; new selection needs a current PASSED test | Always revalidate; auto-clear route | Behaviour surprise | **Decided (delegated, 2026-11-26, M5)**: two separate rules. *Persistence*: a slot unchanged by a PUT is kept without re-validation, and nothing changes routing automatically. *Permission to use*: every configured slot is re-evaluated on each read with the full eligibility rules; a failed or outdated retest (or any other issue) makes it unusable at once, and the usable fallback, if any, becomes the effective route (fail closed). See the [M5 decision record](#m5-decision-record-2026-11-26) | Project owner (delegated) | M5 (done) |
| D10 | Provider deactivation with active models | FRD §1.2 (silent) | Block while any of its models is routed; otherwise allow | Require children inactive; cascade | Orphans | **Decided (delegated, 2026-11-25)**: 409 `MDL_MODEL_IN_USE` with `details.used_in` while routed; otherwise allowed, models keep their own state | Project owner (delegated) | M3 (done) |
| D11 | History retention | FR-MDL-021/012 | Append-only; **no application delete path; no retention period promised** | Defined retention limit | Audit gap or unbounded growth | **Decided (delegated, 2026-11-26, M6) as a project retention policy per data category** (see the M6 record): audit, agreements, withdrawals and routing history are kept for the life of the system with no application deletion; connection tests are kept at least 24 months; credentials are overwritten on rotation and never archived. **No legal-compliance claim**: the institution's legal retention periods, once known, override this | Project owner (delegated); school/legal for statutory periods | M6 (done); legal periods external |
| D12 | Company-framework dependency | brief | None; keep adapter seams | Align with framework schema | Later migration | **Decided (delegated, 2026-11-26, M6)**: no framework dependency in V1; module boundaries (shared auth/audit/errors, `mdl` package, `/api/v1/mdl`) remain the seams for a later migration | Project owner (delegated) | — |
| D13 | Routing `decision_reference` | FR-MDL-021 actor phụ | Optional nullable field, **provisional until approved**; must be settled first because history is append-only and cannot be backfilled | Omit | Cannot backfill | **Decided (delegated, 2026-11-26, M5)**: optional, 1–128 printable characters, stored on the revision row (migration `0006`) and in the audit event; INSERT-only for the runtime login; not required for a change | Project owner (delegated) | M5 (done) |
| D15 | Provider used for FR-MDL-020 verification | FR-MDL-020 AC1, D1 | — | A commercial or school provider with a recorded live run | Demo evidence mistaken for vendor compatibility | **Decided by the Project Owner (2026-11-26)**: this is a demo/capability project, so no real provider is needed. FR-MDL-020 is verified against a **synthetic OpenAI-compatible provider** shipped in the repository (`infra/demo-provider/server.py`, opt-in via `infra/compose.demo-provider.yaml`). See the [D15 record](#d15-record-synthetic-demo-provider-2026-11-26) | Project Owner (stated directly, not delegated) | Done |
| D14 | Encryption primitive, AAD, key custody, rotation | RULE-MDL-04 | **AES-256-GCM with AAD**, key outside PostgreSQL, rotation supported | Fernet/MultiFernet (simpler, no AAD); KMS/Vault; database `pgcrypto` | Minor | **Decided (delegated, 2026-11-25)**; details in the decision record | Project owner (delegated) | M2 (done) |

## Additional approvals implied by the plan

| Topic | Recommendation | Status | Approver |
| --- | --- | --- | --- |
| Eight-package roadmap; M1 may touch shared accepted code | Keep M0–M7 | Awaiting approval | Developer + reviewer |
| Egress policy: HTTPS-only external, connect-time IP validation, server-side internal allowlist, no redirects, no retries, bounded I/O | Adopt | **Implemented in M4 under delegation** (see the M4 decision record); TL confirmation not recorded | TL |
| Dropping a separate credential endpoint (atomic PATCH instead) | Adopt | Awaiting approval | TL |
| Root FRD duplicates | Preserved; `docs/frd/` canonical | Developer to decide on removal | Developer |

## Explicit non-decisions

- No legal approval, DPA validity opinion or risk-classification criterion is asserted anywhere.
- Token↔credit conversion remains undefined and out of scope.
- No real provider, endpoint or credential is used. By D15 the Project Owner chose a synthetic provider for this demo project; compatibility with any real vendor is **not** claimed.
- No formal TL or PO sign-off is recorded.

## True Must-blockers

None. All D1–D14 are decided (D1–D5, D8–D14 under the owner's delegation; D6 and D11 as internal project policy). **External dependencies that no decision here can replace:** official risk criteria (OQ-09-01), statutory retention periods, legal confirmation of the D5 fail-closed reading, and QTA/CRT for end-to-end quota proof. (The live-provider run is no longer required: D15.)

## M2 decision record (2026-11-25)

**Authority:** the sole project owner delegated technical and architectural decisions for M1 review and M2 to the coding agent. The decisions below were taken under that delegation. **No Tech Lead or Product Owner sign-off is claimed**, and each can be reopened. Decisions for M3–M7 (D1, D3–D7, D9–D13) stay as listed above.

### D14 — credential encryption (decided)

| Topic | Decision | Rationale | Alternatives rejected |
| --- | --- | --- | --- |
| Primitive | AES-256-GCM via `cryptography` (`AESGCM`), random 96-bit nonce per seal, 128-bit tag | Authenticated encryption from a maintained library; supports associated data (AAD) | Fernet/MultiFernet (no AAD, so no binding to provider or endpoint); `pgcrypto` (key would have to be sent to PostgreSQL); custom constructions |
| AAD | Length-prefixed fields: purpose label `aq-uai/mdl/provider-credential/v1`, `institution_id`, `provider_id`, canonical endpoint origin (`scheme://host[:port]`, lower-case, default port omitted), `credential_version`, `key_id` | A database-level copy, endpoint redirect, version rollback or key relabel fails closed. `institution_id` was **added** to the earlier design for tenant binding. Length prefixes prevent field-boundary ambiguity | Delimiter-joined string (ambiguous); also binding `auth_scheme` (forces secret re-entry for a same-host change, little gain) |
| Key custody | Key ring in the **api** process environment only. Never in PostgreSQL, never given to `provision` or `migrate`; both refuse to run if they can see it | Database compromise or a backup alone does not reveal secrets | KMS/Vault (no such service in this private stack; can replace the environment source later without schema change) |
| Configuration names | `AQ_UAI_MDL_CREDENTIAL_KEYS` = comma-separated `key_id:base64(32 bytes)`; `AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID`. `key_id` = 1–32 of `[a-z0-9_-]` | Follows the existing `AQ_UAI_` prefix; the ring form supports rotation | Single-key variable (no rotation) |
| Invalid configuration | Rejected when empty, a `CHANGE_THIS` placeholder, not base64, not 32 bytes, a single repeated byte, a duplicate ID or duplicate material, or an active ID not in the ring. The API **still starts** and `/ready` is unchanged; MDL credential operations will return 503 `MDL_CREDENTIAL_UNAVAILABLE` (M3) | Preserves the Phase 1 readiness contract | Fail startup (would couple unrelated features to MDL configuration) |
| API-only availability (Compose) | Both variables are set on the `api` service only, with empty defaults so an existing `.env` keeps working. `scripts/verify_wp2_compose.py` fails if any other service receives them | Least privilege; existing development stacks are not broken | Required (`:?`) variables (would stop the current stack from starting) |
| Rotation | Add a key, move the active ID, `KeyRing.rewrap` re-encrypts each row (same binding, new `key_id`), and the old key is removed only after every row has moved. An admin secret change bumps `credential_version` | Old rows stay readable during rotation | Re-encrypt in a migration (the migration role must never hold the key) |
| Plaintext handling | Returned only as `SecretStr`; 1–4096 bytes; control characters (including CR/LF) refused; fixed exception messages; no logging in the module; key ring not picklable | RULE-MDL-04; avoids header injection at M4 | — |
| Key loss | Unrecoverable by design; recovery is re-entering each provider secret. Back up the key ring separately from database backups | Inherent to keeping the key out of the database | — |

**Deferred (not M2):** the operator command that rewraps every stored row (needs the M3 service layer; the primitive and the runtime grants exist) and `/mdl/status` reporting (M3).

### D2 — provider authentication (decided)

`auth_scheme` ∈ {`BEARER`, `HEADER_KEY`, `NONE`}. `HEADER_KEY` requires `auth_header_name` (token characters only, enforced by a database check); other schemes forbid it. At most one sealed credential row per provider (`mdl_provider_credentials`, primary key `provider_id`). M3 enforces "credential required unless `NONE`" and a header-name denylist (for example `Host`, `Content-Length`).

### D8 — routing scope (decided)

Institution-wide singleton: `mdl_routing` has primary key `institution_id`. Per-assistant or per-unit routing would be a new table later (additive).

### Other M2 schema decisions (decided)

| Topic | Decision | Rationale |
| --- | --- | --- |
| Provisional optional columns | **Not created in M2**: agreement withdrawal columns (D5), `risk_basis_reference` (D6), routing `decision_reference` (D13) | Adding a nullable column later is additive and leaves earlier rows NULL, which is exactly what creating it now and leaving it unused would give. So D13's "must decide before M5" deadline stands, but M2 does not prejudge it |
| Immutability | Enforced by **column-level grants**: the runtime login cannot UPDATE `provider_type`, `technical_id`, `provider_id`, `institution_id` or test snapshots | Database-level guarantee without triggers |
| Append-only history | Agreements and routing revisions are INSERT-only; **no DELETE** on any MDL table | FR-MDL-012 (no hard delete), FR-MDL-021 (trail) |
| Agreements on external providers only | Composite foreign key `(institution_id, provider_id, provider_type)` plus `CHECK provider_type = 'EXTERNAL'` | Structural, not just service logic |
| Capabilities | Three booleans (`supports_text/image/voice`), at least one true | Simpler constraints than an array; D3 semantics remain open for M4 |
| Connection-test error codes | Format check only (`^[A-Z][A-Z_]{0,39}$`); the code list belongs to M4 | Avoids a migration if M4 refines the list |
| `httpx` runtime dependency | **Deferred to M4** (no network code in M2) | Smallest change; the plan listed it under M2 |

## M3 decision record (2026-11-25)

**Authority:** the project owner asked for the M3 plan to be reviewed, adjusted where needed and implemented. The decisions below were taken under that delegation. **No Tech Lead or Product Owner sign-off is claimed.** D1, D3, D4, D6, D7, D9, D11 and D13 remain as listed above.

| Topic | Decision | Rationale | Alternatives rejected |
| --- | --- | --- | --- |
| D5 withdrawal storage | New **INSERT-only** table `mdl_provider_agreement_withdrawals` (migration `0005`), at most one row per agreement | Agreements stay immutable; a withdrawal cannot be silently undone by an UPDATE | `withdrawn_at/by` columns on agreements (would need UPDATE, so they could be cleared again) |
| D5 "in force" | The most recent agreement that has no withdrawal | Recording a new agreement supersedes older ones; withdrawing the latest falls back to the previous valid record | Latest record only (would ignore a still-valid older record) |
| D10 provider deactivation | Blocked (409 `MDL_MODEL_IN_USE`, `details.used_in`) while any of its models is routed; otherwise allowed | Same rule as model deactivation, one where-used seam (`mdl/usage.py`) | Require all models inactive first; cascade deactivation |
| Routed-model edits | A routed model cannot lose its risk level (422 `MDL_RISK_REQUIRED`) or its TEXT capability (409 `MDL_MODEL_IN_USE`) | Keeps an existing route routable (FR-MDL-031); full eligibility arrives in M5 | Allow and let M5 detect it later |
| Endpoint at registration | Canonical `scheme://host[:port]/path`; http/https only; no userinfo, query, fragment or whitespace; **https required for EXTERNAL** (422 `MDL_ENDPOINT_BLOCKED`) | Rejects obviously unsafe values early; API keys in query strings are refused | Leave everything to M4 (would store unsafe values) |
| Credential rules | Secret required on create unless `NONE`; secret with `NONE` refused; blank on edit keeps; **new secret required when the endpoint origin changes or the scheme changes to a secret-bearing one**; each secret write bumps `credential_version`; endpoint, API-style, scheme or header changes bump `connection_version` | FR-MDL-010 AC2, and a stored secret can never be redirected to a new host | Allow origin change without a secret (the AAD would make the old secret unreadable anyway) |
| Credential headers | `HEADER_KEY` names exclude framing, hop-by-hop, cookie and forwarding headers (`Host`, `Content-Length`, `Cookie`, `X-Forwarded-*` and others) | Prevents a secret being placed where it changes routing or framing | Free-form header names |
| Credential status | `NOT_REQUIRED` / `MISSING` / `STORED` / `UNREADABLE`, derived from the row and key ID **without decrypting** | Listing never puts plaintext in memory; tamper detection happens at use (M4) | Trial decryption on every read |
| `/mdl/status` | Reports key-ring availability and active key ID only; egress summary added in M4 | M3 has no egress policy yet | — |
| Key-ring unavailable | Secret-writing requests return 503 `MDL_CREDENTIAL_UNAVAILABLE` and change nothing; other edits keep working | Partial availability without silent data loss | Fail all MDL writes |
| Deferred | Rewrap operator command (moved to M7 operations), `routing_eligible` filter (M5), `risk_basis_reference` (D6) | Not needed for M3 acceptance criteria | — |

## M4 decision record (2026-11-25)

**Authority:** the sole project owner delegated M4 review, technical decisions and plan improvements to the coding agent, explicitly including D1, D3 and D4. The decisions below were taken under that delegation. **No Tech Lead or Product Owner sign-off is claimed**; each can be reopened. D5 (serving question), D6, D7 (viewer), D9, D11, D12 and D13 remain open as listed above.

| Topic | Decision | Rationale | Alternatives rejected |
| --- | --- | --- | --- |
| D1 adapter | One `OPENAI_COMPATIBLE` adapter: `POST {endpoint}/chat/completions`, one fixed user message, `max_tokens` 16, `stream: false`; registry `mdl/adapters/ADAPTERS` keyed by `api_style` | Most self-hosted servers (vLLM, Ollama, llama.cpp, LM Studio) and many vendors expose this format; no provider list has been approved, so none is hard-coded | Vendor-specific adapters now (no approved vendor; more code to secure); OpenAI "Responses" API (narrower compatibility). **Known limit:** some models reject `max_tokens` (they expect `max_completion_tokens`); such a model fails with `REQUEST_REJECTED` and needs a new adapter/style later |
| PASS criterion | 2xx **and** a JSON object with a non-empty `choices` list whose first item has a `message` object; an `error` key fails | Proves credential + model access, not mere reachability (architecture section 5) | Any 2xx (a captive portal or proxy would pass) |
| D3 text only | See the D3 row | No image/voice probe is specified, and a probe would add cost and adapter surface; routing already needs TEXT | Per-capability probes |
| D4 cost control (**M5 added an institution-wide cap and audit of the acknowledgement**) | See the D4 row. Cooldown applies only to a retest of the **same** configuration snapshot; a version bump (new endpoint, new secret) may be tested at once | Limits accidental repeated billing without blocking a fix-and-retest cycle | Block external tests (contradicts FR-MDL-020); spend cap (needs prices, which must not be invented); disclosure in the UI only (not enforceable for other clients) |
| Failure codes | `AUTH_FAILED`, `MODEL_NOT_FOUND`, `RATE_LIMITED`, `REQUEST_REJECTED`, `PROVIDER_ERROR`, `REDIRECT_REFUSED`, `BAD_RESPONSE`, `RESPONSE_TOO_LARGE`, `TIMEOUT`, `DNS_FAILED`, `TLS_ERROR`, `NETWORK_ERROR`, `ENDPOINT_BLOCKED`, `TEST_ERROR`, `STALE_CONFIGURATION`, `ABORTED`, `EXPIRED` | Extends the architecture's seven classes so an administrator can tell a redirect, TLS or 5xx problem apart; codes only, never provider text (the M2 format check already allows them, so no migration) | Free-text provider messages (could carry provider or institutional data) |
| Egress library | `httpcore` used directly (new runtime dependency `httpcore>=1.0.5,<2`); `httpx` stays dev-only | `httpcore` lets the code supply the network backend (resolve-validate-connect in one step), never follows redirects, never retries with `retries=0` and ignores proxy environment variables. `httpx` would need private attributes to pin connections and has proxy/redirect behaviour to disable | `httpx` with a custom transport (private API); `urllib3` (no supported pinning hook without subclassing internals); pre-resolve check only (DNS-rebinding window) |
| Pinning model | Resolve once inside the connection step; **all** returned addresses must pass; connect only to those literals; confirm the socket's peer equals the validated address; TLS SNI and certificate verification use the original host name; the backend refuses any other host/port and UNIX sockets | Closes DNS rebinding and mixed-answer tricks; keeps normal certificate checks | Validate one address only (a mixed answer could still route privately) |
| External destinations | `https`, port 443, a DNS name with at least one dot (no IP literals, no `localhost`/`*.localhost`, no Unicode host names), every address public: `is_global` plus an explicit list (private, loopback, link-local/metadata, CGNAT, documentation, benchmarking, multicast, reserved, IPv4-mapped/compatible, 6to4, Teredo, NAT64, ULA, site-local) | Explicit list keeps the rule stable across Python versions and blocks IPv6 forms that reach IPv4 | Allow IP literals (no TLS name, easy SSRF) |
| Internal allowlist (**amended in M5: every entry needs a port; see the M5 record**) | `AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST` (api service only, empty default): host names (exact) and CIDRs. Link-local, `0.0.0.0/8`, multicast and reserved are refused **always**; loopback only through an explicit CIDR; an invalid, over-broad (shorter than /8 or /16) or always-blocked entry makes the whole list **invalid = nothing internal allowed** (`/mdl/status` shows `INVALID`). External providers ignore the list | Operator-only control; fail closed; a typo cannot silently widen access | Per-provider allowlist in the UI (an MDL admin could open internal access); port lists (more configuration; recorded as a residual risk) |
| Bounds | connect 5 s, read 15 s, write 5 s, **total 20 s** (each socket operation is capped by the remaining total, so a slow drip cannot extend it), response cap 64 KiB, `Accept-Encoding: identity` and encoded replies refused, 3xx never followed | Below nginx's 30 s; no decompression bombs | — |
| Transaction shape | T1 (`protected`): provider `FOR SHARE` → model `FOR UPDATE` → gates → close abandoned rows → in-progress and cooldown checks → decrypt → explicit-column INSERT of the `RUNNING` row; commit. Network with no transaction. T2 (`protected` again): same locks, versions compared, row finished once, audit `mdl.model_connection_tested` | Matches architecture section 5 and the M2 grant (INSERT limited to snapshot columns, so a row can only start as `RUNNING`) | One long transaction (would hold locks during network I/O) |
| Lost authority / crash | If T2 cannot re-authorize, the row is closed as `ABORTED` without an audit actor and the request fails 403/401. A `RUNNING` row older than 120 s is closed as `EXPIRED` by the next test of that model; it never blocks for longer | No dangling "in progress" state; no result recorded for someone who lost the right | Leave the row for manual repair |
| Stale results | If the provider's connection or credential version changed during the call, the result is stored as `FAILED / STALE_CONFIGURATION` | A result for a configuration that no longer exists must never look PASSED | Store PASSED with the old snapshot (correct but confusing in history) |
| Derived test state | `ModelOut.connection_test` = latest finished test whose snapshot equals the provider's present versions: `PASSED`/`FAILED`, else `OUTDATED` or `NOT_TESTED`; `UNSUPPORTED` without TEXT; plus `running` | Architecture section 2 ("no cache flag that can drift"); M5 eligibility will reuse it | Cached flag on the model |
| Logging | The app factory pins the `httpcore` logger to WARNING (its DEBUG traces include provider response headers) | RULE-MDL-04 / architecture section 2: no provider text in logs at any level | Rely on the default level |
| Live provider run | **Pending.** No provider, endpoint or credential has been supplied; no live request was made and none is authorized | FR-MDL-020 AC1 genuine verification needs a PO/TL-supplied provider | — |

## M5 decision record (2026-11-26)

**Authority:** the sole project owner delegated M5 review, decisions and plan improvements to the coding agent, explicitly including D5, D9 and D13 and the outstanding M4 risks, and asked for fail-closed eligibility after agreement withdrawal. **No Tech Lead, Product Owner or legal sign-off is claimed.** D6, D7 (viewer), D11 and D12 stay open.

### Routing (D5, D9, D13)

| Topic | Decision | Rationale | Alternatives rejected |
| --- | --- | --- | --- |
| Eligibility rule set (one, shared) | A model may be selected, **and a configured slot may be used**, only if: model active; provider active; TEXT capability; risk recorded; latest *current* connection test PASSED; external provider has an agreement in force; a secret-bearing provider has a credential readable with the present key ring; the endpoint passes the present egress policy (and uses https when it sends a secret). Codes: `model_inactive`, `provider_inactive`, `text_unsupported`, `risk_unclassified`, `not_tested`, `test_outdated`, `test_failed`, `dpa_missing`, `credential_unavailable`, `endpoint_blocked` | FR-MDL-020/021/030/031, RULE-MDL-01/02; one function (`queries.routing_issues`) so the selection list, PUT and usability cannot disagree | Separate rules for selection and use (they would drift) |
| D9 persistence | `PUT /routing` validates **only new slot values** (a model newly placed in a slot, including a swap between slots). An unchanged slot is kept as is. Nothing ever rewrites routing automatically | The FRD's "hoặc đang dùng hợp lệ": an administrator can change the fallback without first fixing the primary; history always shows decisions, not system side effects | Re-validate every slot on every PUT (blocks unrelated changes during an outage); auto-clear unusable slots (silent history change) |
| D9 permission to use | Each read of `GET /routing` re-evaluates both slots: `usable` + `issues`; `effective` = primary if usable, else fallback if usable, else `UNAVAILABLE` (or `NOT_CONFIGURED`). `routing.effective_model_id()` is the single entry point a future AI gateway must use | Fail closed: a failed or outdated retest, key loss or policy change stops use immediately without waiting for an administrator | Keep serving a failed primary with only a warning (the earlier provisional reading; unsafe once a gateway exists) |
| D5 serving after withdrawal | Fail closed (see the D5 row). Withdrawal is still allowed while routed (M3) and returns `affected_routing` | Requested by the owner; avoids sending school data to a provider without a recorded agreement | Block withdrawal while routed (would force keeping a known-invalid record) |
| D13 | See the D13 row. A reference supplied with an otherwise unchanged PUT is ignored (a no-op writes nothing) | A document number describes a change; a no-op has none | Required reference (FRD makes the Board actor optional) |
| Concurrency | `expected_revision` (0 when never configured) → 409 `MDL_ROUTING_CONFLICT`; an institution advisory lock (`lock_routing`) serializes even the first configuration; then provider rows and model rows `FOR SHARE` in ID order; revision row, routing row and audit event in one transaction | Lost-update and check-then-act races (PUT vs PUT, PUT vs deactivation, PUT vs credential rotation) are excluded by locks, not timing | Row lock only (no row exists before the first configuration) |
| Refusal details | 409 `MDL_NOT_ELIGIBLE` with `details.reasons` such as `primary.dpa_missing` (new allowlisted detail key, fixed identifiers, at most 48) | The UI must say *why*; still no free text | Free-text messages |
| Selection list | `GET /models?routing_eligible=true|false` and a `routing` object (`eligible`, `issues`) on every model | FR-MDL-021 AC1 ("not in the selection list"); filtered in Python because eligibility is derived | Cached eligibility column (would drift) |
| History | `mdl_routing_revisions` INSERT-only (no UPDATE/DELETE grant), display names snapshotted; `GET /routing/revisions` needs only `mdl.read` | FR-MDL-021 AC3; readable without audit rights | — |

### Fixes to M3/M4 made in M5 (owner asked to resolve all open M3/M4 problems)

| Problem (where recorded) | Decision | Rationale | Alternative rejected |
| --- | --- | --- | --- |
| Secret could travel over internal plain HTTP (M4 risk) | A provider using `BEARER` or `HEADER_KEY` must use `https`, internal ones included: refused at registration/edit (422 `MDL_ENDPOINT_BLOCKED`) and, as defence in depth, at connect time (`ENDPOINT_BLOCKED`) and in eligibility. `NONE` over internal `http` stays allowed | RULE-MDL-04 spirit; on-premise servers without auth (Ollama) are unaffected | Operator opt-in for plaintext secrets (more configuration, easy to leave on) |
| Allowlist allowed any port (M4 risk) | Every allowlist entry names exactly one port: `host:port`, `IPv4[/n]:port`, `[IPv6[/n]]:port`; an entry without a valid port makes the whole list `INVALID` (nothing internal allowed) | Stops an MDL administrator probing other ports of an allowed host; fails loudly | Port denylist (incomplete by nature) |
| Test cap was per process (M4 risk) | Plus an institution-wide cap of 4 tests in flight, counted in PostgreSQL under an advisory lock (429 `RATE_LIMITED`); the per-process cap stays to protect threads | Holds across workers and containers | — |
| Charge acknowledgement left no trace (M4 review) | `charges_acknowledged` stored in the `mdl.model_connection_tested` audit event | Accountability for possible provider charges | New table column (audit is enough) |
| Abandoned DNS threads unbounded (M4 risk) | At most 8 lookup threads, counting abandoned ones; beyond that a test fails fast with `TIMEOUT` | Bounded resources under a hanging resolver | — |
| Internal HTTPS with a private CA failed (M4 risk) | `AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE` (api only): a PEM bundle trusted **in addition to** the system store, for internal providers only; `/mdl/status` reports `NONE`/`CONFIGURED`/`UNREADABLE`; unreadable ⇒ `TLS_ERROR` | Lets on-premise TLS work without disabling verification | Option to disable verification (never) |
| Models rejecting `max_tokens` (M4 risk) | New `api_style` `OPENAI_COMPATIBLE_V2`: same request with `max_completion_tokens` (migration `0006` widens the check) | Covers newer and reasoning models; still one fixed small request | Sending both fields (some servers reject unknown or conflicting fields) |
| Registration accepted endpoints egress always refuses (M3 observation) | Unicode, numeric and malformed hosts refused at registration; external endpoints must also pass the static external rules (port 443, DNS name, not `localhost`) | Early, clear feedback | — |
| Key-rotation rewrap command deferred (M2/M3) | `python -m aq_uai_api.db.mdl_rewrap` (api container): rewraps rows not under the active key, one transaction per row, operator audit event `mdl.credential_rewrapped`, counts-only output, exit 1 if a row is unreadable; `credential_version` unchanged so tests stay current | Makes key retirement possible | Rewrap inside a migration (the migration role must never hold the key) |
| Provisioning on an older database could fail when a grant names a column added by a later migration (found in M5 testing) | `present_privileges` grants only existing columns during `prepare`; `migrate` grants again afterwards | `provision prepare` runs before `migrate` in Compose | — |
| Pre-existing browser failure (since `2c909e3`) | The test now waits for the user detail heading before checking the status badge (test-only change; the UI was correct) | The check raced the navigation: while the list was still shown, its status-filter `<option>` and row badge both matched. Scoping to the results table was tried first and failed once navigation completed | Scope to the list table (checks the wrong view) |

**Still open (not resolvable by the coding agent):** a live-provider run (needs a PO/TL-supplied provider and authorization for a possibly billed call); D6 risk criteria (external, OQ-09-01); D7 Board read access; D11 retention period; functional quota proof (needs QTA/CRT).

## M6 decision record (2026-11-26)

**Authority:** the sole project owner delegated the M5 closeout and M6 decisions to the coding agent, naming D5, D6, D7 and D11. **No Tech Lead, Product Owner, legal or school sign-off is claimed.** Project policy below is distinguished from external approval wherever it matters.

### D6 — risk criteria (internal operational guidance)

Shown in the model dialogs under "Tiêu chí phân loại rủi ro (hướng dẫn nội bộ)". They classify the model **for its intended use at the school**, not the vendor.

| Level | Use when (any applies) |
| --- | --- |
| **HIGH (Cao)** | Output can significantly affect learners or staff (assessment, grading, admissions, discipline); the model processes sensitive personal data; or the provider does not publish enough information about the model |
| **MEDIUM (Trung bình)** | The model produces supporting content that a person reviews before use (drafting, summarising, general Q&A) and may see ordinary personal data |
| **LOW (Thấp)** | No personal data, and the output does not directly affect anyone's rights or interests (formatting, wording suggestions, internal trials) |

Rules: no default level and no vendor-derived level (FR-MDL-031 AC2); **unclassified ⇒ not eligible** for routing (enforced since M5); changes are audited (`mdl.model_risk_changed`). Status: **internal guidance, not a legal classification**. When the school adopts official criteria (OQ-09-01) they replace this table; the stored levels then need re-review. Rejected: a mandatory free-text basis now (would look like legal evidence the system cannot validate).

### D7 — Board read access

`AI_MODEL_VIEWER` is **not** added in V1. Rationale: no demonstrated user need; the FRD's secondary actor (Ban Giám hiệu) decides outside the system and the decision number is captured in routing history; every additional role widens the authorization matrix and test surface. Re-open when a named Board user needs self-service read access; the change is additive (one role, `mdl.read`, no UI rework because writes are already gated by `mdl.manage`).

### D11 — retention policy (project policy; not a legal-compliance claim)

| Data category | Retention | Mechanism |
| --- | --- | --- |
| Audit events (all `mdl.*` actions) | Life of the system | INSERT-only; no application delete path |
| Agreements and withdrawals | Life of the system (evidence for every past test or route) | INSERT-only tables |
| Routing state and revisions | Life of the system (FR-MDL-021 trail) | Revisions INSERT-only; routing row updated only by PUT |
| Connection tests | At least 24 months; may be archived later by a reviewed DBA procedure | No DELETE grant; growth bounded by cooldown and caps |
| Providers and models | Never hard-deleted (FR-MDL-012); deactivated instead | No DELETE grant |
| Provider credentials | Only the current ciphertext; replaced on rotation, never archived | UPDATE in place; key ring separate from backups |
| Backups | Institution IT policy; contain ciphertext only | Key ring backed up separately (D14) |

Any purge or archive requires a separate, reviewed procedure and a statutory basis supplied by the school; the system offers none today. **No legal compliance is claimed.**

### D5 — fail-closed withdrawal (wording clarified)

Fail-closed use after withdrawal (M5) is **project policy** decided under delegation, not legal approval. It is the conservative reading of FR-MDL-030 (no use without an agreement in force). Legal confirmation remains advisable; the behaviour would only become less strict if Legal explicitly allowed continued use.

### Quota isolation and live-provider readiness

- **Quota (FR-MDL-020 AC3):** strengthened without QTA/CRT: a static import-closure test over everything reachable from MDL, and a PostgreSQL test that attaches a write-logging trigger to *every* table and proves a connection test writes only `mdl_connection_tests`, `audit_events` (and possibly `auth_sessions`), and a routing change only routing tables. Any future quota/credit table is covered automatically. End-to-end proof still needs QTA/CRT.
- **Live provider:** opt-in `live_provider` test (skipped unless `AQ_UAI_LIVE_PROVIDER_AUTHORIZED=I-ACCEPT-A-POSSIBLY-BILLED-CALL`) and the [verification runbook](MDL_LIVE_PROVIDER_VERIFICATION.md). **Not run**: no provider supplied and no billed call authorized.

### M6 UI decisions

| Topic | Decision | Rationale |
| --- | --- | --- |
| Placement | One section `#mdl` ("Cấu hình Nhà cung cấp & Mô hình AI") with tabs: routing (default), providers, models, agreements, history; detail views `#mdl/providers/<id>`, `#mdl/models/<id>` | Matches the FRD menu; reuses the shell, `listing`, `formDialog`; small router extension |
| Visibility | Section visible with `mdl.read`; every write control requires `mdl.manage`; the server remains the authority | FR-MDL-001 |
| Secrets | Password-type inputs, `autocomplete="new-password"`, never prefilled (the API never returns them), cleared after every submit and from submitted payloads | FR-MDL-010, RULE-MDL-04 |
| Cost acknowledgement | External test dialog shows the cost notice and requires a checkbox; the client sends `acknowledge_provider_charges: true` only then; the server enforces it independently | D4 |
| Error messages | MDL error codes and the allowlisted `details` (`used_in`, `reasons`) are mapped to fixed Vietnamese text; unknown detail values are dropped, never rendered | Clear reasons without free text |
| Routing dialog | Offers only `routing_eligible` models, keeps the current slot value as "giữ nguyên", sends `expected_revision` | FR-MDL-021 AC1, D9 |

## M7 decision record (2026-11-26)

**Authority:** the sole project owner delegated the M7 review, technical decisions, defect fixes and closeout to the coding agent. **No Tech Lead, Product Owner, legal or school sign-off is claimed.** D1–D14 are unchanged; no decision was reopened.

| Topic | Decision | Rationale | Alternatives rejected |
| --- | --- | --- | --- |
| FRD §6 "Should": configuration version history with diff | **Implemented** as `GET /api/v1/mdl/history` (needs `mdl.read`; own institution only; `mdl.*` configuration events, connection tests excluded; filters `target_type`, `target_id`) plus UI views with "field: before → after" lines (history tab, provider and model details) | Every MDL write already stores a typed before/after audit payload in the same transaction, so the history is complete back to M3 without a new table or migration; `public_audit_changes` returns only allowlisted fields | A new revisions table per entity (duplicate data, migration, backfill impossible for M3–M6 changes); reuse of the audit viewer (needs `audit.read`, which MDL administrators do not hold and should not get); documenting a limitation (cheap to build properly) |
| History limitation | Endpoint changes show the **origin** and a "path changed" flag, not the full path; a credential rotation shows only the new credential version | Decided in M3 for audit privacy (a path could embed identifiers); secrets are never history data | Auditing full URLs |
| Pickers limited to 100 entries (M6 observation) | **Fixed**: the admin UI pages through the API (`readAll`, 100 per request, up to the API's offset ceiling) for the provider picker and the routing dialog | The single request silently omitted entries beyond 100, and opening "Thêm mô hình" from a provider beyond the first 100 preselected a different provider | Raise the API page limit (shared Phase 2 contract); searchable picker (larger UI change, not needed at this registry size) |
| Stale ciphertext after switching a provider to `NONE` | **Kept, documented**: the old sealed secret stays in `mdl_provider_credentials` (unused, still encrypted) until a new secret overwrites it | The runtime has no DELETE grant by design (D11/M2); the row is unreadable without the key ring and is never sent (`NONE` sends no credential); switching back requires a new secret | Granting DELETE on credentials (weakens the no-delete invariant); nulling columns (would need a migration and nullable ciphertext) |
| `AI_MODEL_VIEWER` (D7) | Unchanged: deferred | No new need surfaced in M7 | — |

**Still external (no decision here can replace them):** live-provider run (provider, credentials and authorization of a possibly billed call), official risk criteria (OQ-09-01), statutory retention periods (D11), legal confirmation of the D5 fail-closed reading, and QTA/CRT for end-to-end quota proof (FR-MDL-020 AC3).

## D15 record: synthetic demo provider (2026-11-26)

**Authority and provenance:** decided **directly by the sole Project Owner** in the session of 2026-11-26 ("this project is only for simple demo and testing my capability, we don't really need the real providers"), who asked for a synthetic provider and a completed connection. Recorded by the coding agent; **not** a Tech Lead decision.

| Topic | Decision | Rationale | Alternatives rejected |
| --- | --- | --- | --- |
| Verification target for FR-MDL-020 AC1 | A synthetic, OpenAI-compatible HTTPS server in the repository (`infra/demo-provider/server.py`) replaces the pending live-vendor run for this project's scope | The FRD criterion is "a successful test makes the model selectable"; the product path (adapter, egress policy, TLS verification, credential, transactions, eligibility) is identical whatever answers on the other side. The owner does not need vendor compatibility | Keep waiting for a vendor (blocks a demo project indefinitely); a public free API (still external, may bill or change) |
| How it runs | Opt-in Compose override `infra/compose.demo-provider.yaml`, started with `bash scripts/dev-up.sh --demo-provider`; service `demo-provider` on the Compose network only (no published port); the API trusts its CA through `AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE` and may reach only `demo-provider:8443` while the override is used | Same security posture as a real internal provider: https with verification, port-scoped allowlist, secret sent only over TLS. The main `compose.yaml` and the default configuration are unchanged | Plain-HTTP fake without authentication (would not exercise the credential path); disabling TLS verification (never) |
| Behaviour | Checks the key from `AQ_DEMO_PROVIDER_API_KEY` (Bearer or `X-Api-Key`, constant-time compare); models from `AQ_DEMO_PROVIDER_MODELS` (default `demo-chat,demo-chat-mini`); fixed reply "OK"; 401 for a wrong key, 404 for an unknown model, so `AUTH_FAILED` and `MODEL_NOT_FOUND` can be demonstrated; logs method, path and status only | Demonstrates success and the common failure classes deterministically | Always-succeed stub (would hide failure handling) |
| Key material | A new CA and server key are generated at every start, kept inside the container; only the public CA certificate is shared (volume `demo_provider_ca`, read-only in `api`) | No certificate or private key in the repository | Committed test certificates |
| What it does **not** prove | Compatibility with any specific real vendor, real model quality, real billing | Stated so the demo evidence is not over-read | — |
| Effect on status | FR-MDL-020 AC1 and AC2 **verified in demo scope**; AC3 (quota unchanged) still structural until QTA/CRT exist | AC3 needs a quota balance to compare, which does not exist yet | — |
