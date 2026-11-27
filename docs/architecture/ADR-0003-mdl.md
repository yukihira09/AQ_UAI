# ADR-0003 · MDL provider and model configuration

**Status:** Proposed overall. The **Secrets**, provider-authentication (D2) and routing-scope (D8) parts were **decided on 2026-11-25 under the sole project owner's delegated authority** (see Approval). The connection-test parts D1, D3 and D4 (M4) and the routing parts D5 (serving), D9 and D13 (M5, 2026-11-26) were decided under the same delegation. Not signed off by a Tech Lead or Product Owner. M1 (access), M2 (schema, encryption, grants), M3 (provider, model, agreement and risk APIs), M4 (egress policy, adapter, real connection test), M5 (routing, versions, guards), M6 (admin UI) and M7 (closeout: configuration history with diff, picker fix, backup/restore and upgrade rehearsals) are implemented and technically verified (2026-11-26). The ADR **stays Proposed**: promotion to Accepted needs Tech Lead or Product Owner approval, which is not recorded. Status per requirement: [traceability](../phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26).
**Date:** 2026-11-25 (M0).
**Scope:** MDL only ([FRD](../frd/AQ-FRD-UAI-MDL-001.md)). QTA and CRT are out of scope.
**Detail:** [architecture](../phase3/MDL_ARCHITECTURE_AND_DECISIONS.md) · [decisions](../phase3/MDL_OPEN_DECISIONS.md) · [plan](../phase3/MDL_IMPLEMENTATION_PLAN.md).

## Context

MDL lets an administrator register AI providers and models, run a real connection test, choose primary and fallback models with a version trail, record data-protection agreement (DPA) evidence, and classify risk. It must extend the Phase 2 identity, permission, audit and migration foundations ([ADR-0002](ADR-0002-phase2-shared-foundation.md)) rather than build parallel ones. The connection test makes the server call an administrator-supplied URL with a stored secret, which creates credential-storage and SSRF risks.

## Decision (proposed)

- **Module:** an `mdl` package inside the existing modular monolith, exposed under `/api/v1/mdl`, with additive Alembic migrations.
- **Permissions:** `mdl.read` and `mdl.manage`; one role, `AI_MODEL_ADMIN`, direct GLOBAL grant only. `FOUNDATION_ADMIN` and `AI_SPECIALIST` groups confer no MDL authority. `AI_MODEL_VIEWER` is deferred beyond V1 (D7, decided under delegation in M6).
- **Secrets (decided, delegated):** AES-256-GCM with associated data binding institution, provider, endpoint origin, credential version and key ID; key ring `AQ_UAI_MDL_CREDENTIAL_KEYS` / `AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID` held only by the `api` service, never by PostgreSQL, `provision` or `migrate`; rotation by key ring plus rewrap; secrets never returned, logged or audited.
- **Provider authentication (decided, delegated, D2):** `BEARER`, `HEADER_KEY` (named header) or `NONE`.
- **Connection test (decided, delegated, M4: D1, D3, D4):** one generic OpenAI-compatible adapter; text-only; real HTTP through an SSRF-resistant egress layer built on `httpcore` (HTTPS-only public host names for external, connect-time address validation and pinning with TLS verification on the host name, operator-only allowlist for internal hosts, no redirects, no proxies, bounded size and time, no automatic retries); two short transactions around the network call; no quota or credit code path. External tests require an explicit acknowledgement that the provider may charge, and are rate-limited per model.
- **Routing (decided, delegated, M5: D9, D13):** institution-wide primary/fallback (D8) with optimistic revision control and append-only revision rows carrying an optional decision document number. Configuration never changes automatically (persistence), but every configured slot is re-checked against the full eligibility rules on each read and is unusable at once when any rule fails (fail-closed use); the usable fallback then becomes the effective route.
- **DPA (decided, delegated, D5):** external providers need a recorded basis and document number before test or use. Withdrawal is allowed while routed; the slot stays configured but cannot be used until an agreement is in force again (fail closed). No legal approval is claimed.
- **History and retention (D11, project policy):** append-only, no application delete path; audit, agreements and routing history kept for the life of the system, connection tests at least 24 months. No legal-compliance claim.
- **Risk criteria (D6, internal guidance):** HIGH/MEDIUM/LOW criteria shown in the UI, explicitly not a legal classification; unclassified models are ineligible.
- **Admin UI (M6):** one `#mdl` section in the existing admin shell; write-only secret fields; mandatory cost acknowledgement for external tests.
- **Configuration history (M7, FRD §6 Should):** `GET /api/v1/mdl/history` (needs `mdl.read`) projects the institution's MDL configuration audit events with their typed before/after payloads; the UI renders field-by-field differences. No new table: the audit event written in the same transaction as each change is the single source.
- **Excluded configuration:** no prompt, temperature or template fields anywhere in MDL (FR-MDL-040).
- **Demo provider (D15, Project Owner decision):** FR-MDL-020 is verified against a synthetic OpenAI-compatible HTTPS server in the repository (`infra/demo-provider/server.py`), opt-in through `infra/compose.demo-provider.yaml`; no real vendor is required for this project and vendor compatibility is not claimed.

## Consequences

- Positive: least-privilege authority, one audit and authorization path, additive schema, testable network behaviour, secret never at rest in plaintext.
- Costs: M1 modifies accepted shared code; connect-time pinning needs custom network code; the application must manage an encryption key and its backup; bootstrap of the first MDL administrator is a two-step flow.
- Risks: delegated assumptions (D1, D3, D4, D5, D9, D13) may be reopened by the PO/TL/Legal; genuine provider verification depends on a provider and credentials not yet supplied; withdrawal-while-routed semantics need PO/Legal confirmation.
- Evidence: acceptance of any FR-MDL requirement requires new reports; demo interactions and controlled-server tests are not formal acceptance.

## Alternatives considered

- Five fine-grained permissions (rejected: no FRD need, more surface; split remains additive).
- Fernet (simpler, no AAD binding).
- Pre-resolve-only SSRF check (rejected: DNS-rebinding window).
- Separate database role for secrets (rejected as disproportionate; the limit is documented).
- Vendor-specific adapters now (deferred: no approved provider list, D1).

## Approval

| Date | Who | Scope | Kind |
| --- | --- | --- | --- |
| 2026-11-25 | Sole project owner, by delegation to the coding agent | D14 (cipher, AAD, key custody, configuration names, rotation), D2, D8 and the M2 schema choices in the [M2 decision record](../phase3/MDL_OPEN_DECISIONS.md#m2-decision-record-2026-11-25) | Owner-delegated engineering decision. **Not** Tech Lead or Product Owner sign-off |
| 2026-11-25 | Sole project owner, by delegation to the coding agent | D5 recording (append-only withdrawals), D10 and the M3 API rules in the [M3 decision record](../phase3/MDL_OPEN_DECISIONS.md#m3-decision-record-2026-11-25) | Owner-delegated engineering decision. **Not** Tech Lead or Product Owner sign-off; the D5 serving question was decided in M5 (fail closed) |
| 2026-11-25 | Sole project owner, by delegation to the coding agent | D1, D3, D4 and the M4 egress, adapter and transaction rules in the [M4 decision record](../phase3/MDL_OPEN_DECISIONS.md#m4-decision-record-2026-11-25) | Owner-delegated engineering decision. **Not** Tech Lead or Product Owner sign-off; live-provider verification still pending |
| 2026-11-26 | Sole project owner, by delegation to the coding agent | D5 serving (fail closed), D9, D13 and the M3/M4 fixes in the [M5 decision record](../phase3/MDL_OPEN_DECISIONS.md#m5-decision-record-2026-11-26) | Owner-delegated engineering decision. **Not** Tech Lead, Product Owner or legal sign-off |
| 2026-11-26 | Sole project owner, by delegation to the coding agent | D6 and D11 (as internal project policy), D7 (viewer deferred), D12, the D5 wording, and the M6 UI rules in the [M6 decision record](../phase3/MDL_OPEN_DECISIONS.md#m6-decision-record-2026-11-26) | Owner-delegated decision. **Not** Tech Lead, Product Owner, legal or school sign-off |

| 2026-11-26 | Sole project owner, by delegation to the coding agent | M7: configuration history built on audit events, picker paging fix, M7 verification scope, in the [M7 decision record](../phase3/MDL_OPEN_DECISIONS.md#m7-decision-record-2026-11-26) | Owner-delegated decision. **Not** Tech Lead, Product Owner, legal or school sign-off |

| 2026-11-26 | Sole Project Owner, directly | D15: synthetic demo provider instead of a real vendor ([D15 record](../phase3/MDL_OPEN_DECISIONS.md#d15-record-synthetic-demo-provider-2026-11-26)) | Project Owner decision, recorded by the coding agent. **Not** Tech Lead sign-off |

Everything else in this ADR remains **Proposed**. Do not infer approval of other parts from this entry.
