# MDL requirements traceability

**Status (M7, 2026-11-26):** every Must requirement is implemented and has automated evidence; the per-requirement classification is in [M7 acceptance status](#m7-acceptance-status-2026-11-26). **Technical verification is not formal acceptance**: no Tech Lead or Product Owner sign-off is recorded. FR-MDL-020 is verified against the synthetic demo provider chosen by the Project Owner (D15); only its AC3 (quota balance) waits for QTA/CRT. History of this document: planning document (M0), with M1 progress (FR-MDL-001 access foundation), M2 progress (storage, encryption and grants behind FR-MDL-010/012/021/030/031 and RULE-MDL-04), [M3 evidence](#m3-evidence-2026-11-25-automated-awaiting-independent-review), [M4 evidence](#m4-evidence-2026-11-25-automated-controlled-server-awaiting-independent-review) [M5 evidence](#m5-evidence-2026-11-26-automated-and-docker-smoke-awaiting-independent-review) and [M6 evidence](#m6-evidence-2026-11-26-automated-api-and-browser-awaiting-independent-review) noted. **No requirement below is accepted**; M1 and M2 await independent review, and no FR-MDL acceptance criterion is satisfied by storage alone (routes arrive in M3); `docs/acceptance-matrix.md` correctly shows "Not started (backend)" for all nine. This file maps every Must requirement and each acceptance criterion (AC) of [AQ-FRD-UAI-MDL-001](../frd/AQ-FRD-UAI-MDL-001.md) to the planned implementation and verification. Milestones (M1–M7) are defined in the [implementation plan](MDL_IMPLEMENTATION_PLAN.md); designs in the [architecture](MDL_ARCHITECTURE_AND_DECISIONS.md); open items in the [decision register](MDL_OPEN_DECISIONS.md) (D1–D14).

## Basis legend

| Tag | Meaning |
| --- | --- |
| **SPEC** | Directly specified by the FRD |
| **REC** | Technical recommendation (reviewable, not stated in the FRD) |
| **PROV** | Provisional assumption pending confirmation |
| **APPR** | Needs Product Owner (PO) or Tech Lead (TL) approval before dependent work |

Evidence column: what must exist before the AC may be called verified. "Automated" evidence from a controlled local test server verifies wire behaviour only; it is **not** genuine provider verification.

## Coverage summary

| Requirement | Priority | ACs | Milestones | Blocking unknowns |
| --- | --- | --- | --- | --- |
| FR-MDL-001 Access | Must | 2 | **M1, M3 API, M6 UI done (review pending)** | D7 decided (viewer deferred beyond V1) |
| FR-MDL-010 Provider | Must | 2 | **M2, M3, M4, M6 UI done (review pending)** | D1, D2 decided (delegated) |
| FR-MDL-011 Model | Must | 2 | **M3 API, M6 UI done (review pending)** | D3 decided (delegated) |
| FR-MDL-012 Deactivate | Must | 2 | **M3, M5, M6 UI message done (review pending)** | D10 decided (delegated) |
| FR-MDL-020 Connection test | Must | 3 | **M4, M5, M6 UI done (review pending)** | **Live run pending** (no provider supplied, no billed call authorized; runbook ready); AC3 end-to-end needs QTA/CRT (write-set evidence added in M6) |
| FR-MDL-021 Primary/fallback | Must | 3 | **M2, M5, M6 UI done (review pending)** | D8, D9, D13 decided (delegated) |
| FR-MDL-030 DPA gate | Must | 2 | **M3, M4, M5, M6 UI done (review pending)** | D5 decided as project policy (fail closed); legal confirmation advisable |
| FR-MDL-031 Risk | Must | 2 | **M3 API, M6 UI with D6 guidance done (review pending)** | Official criteria (OQ-09-01) external; internal guidance in place |
| FR-MDL-040 Excluded config | Must | 1 | **M3 API layers, M6 DOM check done (review pending)** | none |
| **Total** | 9 Must | **19 ACs** + 4 RULEs | | Implementation complete (M7); 8 Must requirements technically verified; FR-MDL-020 verified in demo scope (synthetic provider, D15) except AC3 (needs QTA/CRT); **formal acceptance needs TL/PO sign-off** |
| §6 Should: configuration history with diff | Should | — | **M7 done** | none |
| §6 Could: ordered multi-fallback | Could | — | Not built (later) | — |

## FR-MDL-001 — Access control

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 001-AC1 | Unauthenticated or unauthorized users cannot change providers/models | SPEC | All writes via the shared protected-write path (session + exact Origin + CSRF + transaction-time re-authorization). Permission `mdl.manage`, direct GLOBAL grant only (M1, M3) | API matrix: every write route × {anonymous, authenticated without grant, `FOUNDATION_ADMIN`, `AI_SPECIALIST` group member, `AI_MODEL_ADMIN`}; expect 401/403 except the last | Automated pytest report |
| 001-AC2 | Authorized account opens screen and sees list, even empty | SPEC | `mdl.read`; list endpoints return 200 with empty page; UI empty states (M3, M6) | API test on empty database; browser test of empty states | pytest + Playwright capture |
| 001 note | Hide or reject write controls without permission | SPEC / REC | Server is the authority; UI hides controls when `mdl.manage` absent | Browser test with a read-only account is **only possible if** a read-only role exists; deferred with `AI_MODEL_VIEWER` (D7). Server-side 403 test covers the rule meanwhile | — |
| 001 scope | Who holds MDL authority | REC / APPR | **M1 implemented (automated, awaiting review):** `AI_MODEL_ADMIN` direct GLOBAL only. `FOUNDATION_ADMIN` and `AI_SPECIALIST` groups confer nothing (structural: central-permission table + DB check) | Policy unit tests + PostgreSQL constraint tests (`test_m1_contracts.py`, `test_m1_mdl_access.py`, `test_wp1_schema.py`) | pytest (disposable PostgreSQL 18) |

Bootstrap consequence (REC): an existing `FOUNDATION_ADMIN` assigns the first `AI_MODEL_ADMIN` through the existing role-assignment UI. The handoff must document this two-step flow.

## FR-MDL-010 — Provider configuration

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 010-AC1 | Can add External and Internal providers | SPEC | `POST /api/v1/mdl/providers`; fields name, type (`EXTERNAL`/`INTERNAL`), connection info; plus `api_style`, `endpoint`, `auth_scheme` (REC/PROV) (M2, M3) | Integration test creates both types; audit row present | pytest |
| 010-AC2 | Reopened form shows empty secret; saving without re-entry keeps old connection (checked by later connection test) | SPEC | PATCH treats absent/null/empty secret as "keep". Responses expose only `has_credential`, `credential_updated_at`, `credential_status` (M3, M6) | Edit name only, then run the test against a controlled server that asserts the `Authorization` header equals the original secret (M4); UI test that the field is blank | pytest (M3 part now, full check at M4) + Playwright |
| 010 secret storage | Stored securely, never shown | SPEC | **M2 implemented (automated, awaiting review):** AES-256-GCM with length-prefixed AAD (tenant, provider, endpoint origin, credential version, key ID); key ring only in the `api` environment; `provision`/`migrate` refuse it; ciphertext-only table, no DELETE (D14 decided, delegated) | `tests/unit/test_m2_credentials.py` (round trip, tamper ×4, wrong key, every AAD field, key relabel, rotation and retirement, invalid key rings, unsafe secret values, redaction of repr/logs/exceptions, startup without keys, setup refusal); `tests/integration/test_m2_mdl_schema.py` (runtime-login round trip, no plaintext or key in any MDL or audit row, ciphertext swap / endpoint redirect / version rollback fail closed, rewrap through runtime grants). Response/audit canary scans remain M3 | pytest (disposable PostgreSQL 18). Crypto review by a TL **not** recorded |
| 010 REC | Immutable `provider_type`; endpoint-origin change requires re-entering the secret | REC | Service rule + AAD origin binding | Tests: type change rejected; origin change without secret rejected (422) | pytest |

## FR-MDL-011 — Model registration

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 011-AC1 | Added model under existing provider appears in list | SPEC | `POST /api/v1/mdl/models`; fields provider, `technical_id` (unique per provider, immutable), `display_name`, capabilities ⊆ {TEXT, IMAGE, VOICE}, `max_output_tokens` (nullable) (M3) | Integration test; duplicate → 409 | pytest |
| 011-AC2 | No system-prompt field on this feature | SPEC | Pydantic `extra="forbid"`, no such columns, no JSONB options column | Schema/column-name test; OpenAPI scan; DOM test (see FR-MDL-040) | pytest + Playwright |

## FR-MDL-012 — Deactivation of a model with an assigned role

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 012-AC1 | Deactivating the primary model is refused with a message | SPEC | `POST …/deactivate` takes the routing lock then consults a where-used registry. M3 ships the registry seam; M5 registers routing. 409 `MDL_MODEL_IN_USE` with an allowlisted `details.used_in` (M1 adds `details`) | Integration test plus race test (deactivate vs routing change) | pytest, repeated runs |
| 012-AC2 | After switching primary, the old model can be deactivated | SPEC | Same endpoint | Integration test of the switch-then-deactivate flow | pytest |
| 012 no hard delete | History-bearing model never hard-deleted | SPEC | No `DELETE` route and no `DELETE` grant on any MDL table (REC for grant) | Privilege-matrix test (M2) | pytest |
| 012 other mandatory config | "another explicitly identified mandatory configuration" | SPEC (no instance exists today) | Registry seam only; QTA/CRT register themselves later; no stub | Unit test of registry | pytest |
| 012 provider deactivation | Not in FRD | PROV / APPR (D10) | Block while any of its models is routed; otherwise allow | Integration test once approved | pytest |

## FR-MDL-020 — Real connection test

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 020-AC1 | Successful test makes the model selectable as primary/fallback | SPEC | `POST …/connection-tests` runs one real HTTP call through the provider adapter and egress policy; PASSED requires 2xx **and** expected body shape; result persisted (M4) | Controlled-server test of wire format and state change. **Genuine provider verification** needs one recorded `live_provider` run with PO-supplied credentials | pytest; live run **pending** until PO/TL supply a provider |
| 020-AC2 | Failed test: not selectable | SPEC | Eligibility requires latest current test PASSED | Integration test per failure class (`AUTH_FAILED`, `TIMEOUT`, …) | pytest |
| 020-AC3 | Tester's quota balance unchanged | SPEC | Quota-free by construction: the MDL code path imports no quota/credit table | **Verified end-to-end with populated QTA (Phase 4 Q6, 2026-11-27):** `test_q6_mdl_qta_isolation.py` proves PASSED/FAILED connection tests and routing leave a `4,000`-entitlement tester's lookup, school budget, QTA events, and all 8 `qta_*` tables byte-identical with zero `qta_*` writes (plus positive control & reverse direction; consumption remains `NOT_INTEGRATED`, so "balance" means live `base_entitlement`); CRT proof awaits Phase 5 | Structural (`test_m6_quota_isolation.py`) + populated-QTA end-to-end (`test_q6_mdl_qta_isolation.py`); CRT deferred to Phase 5 |
| 020 fixed request | No institutional data in the request | SPEC | Fixed one-message body, small `max_tokens` | Test captures the request body and asserts equality with the constant | pytest |
| 020 safety | SSRF-resistant, bounded, no redirects, no retries | REC | [Egress policy](MDL_ARCHITECTURE_AND_DECISIONS.md#6-ssrf-resistant-egress) | Table-driven address cases, redirect, oversize, slow, DNS-rebinding tests | pytest (no database for pure-library cases) |
| 020 scope | Text-only test | PROV (D3) | Image/voice models are registerable but test-unsupported, hence not routable initially | Test asserts no image/voice test claim | pytest |
| 020 cost | External test may incur provider charges although AQ allowance is untouched | REC / APPR (D4) | UI notice and minimal request; per-model cooldown | Browser test asserts notice text | Playwright |

## FR-MDL-021 — Primary and fallback with version trail

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 021-AC1 | Model without a successful test is not offered as primary | SPEC | `routing_eligible` filter and PUT-time re-check under locks (M5) | Eligibility matrix test | pytest |
| 021-AC2 | Fallback equal to primary is refused | SPEC | Service check plus database `CHECK (primary <> fallback)` | Unit test and PostgreSQL constraint test | pytest |
| 021-AC3 | After two primary changes, both versions remain viewable | SPEC | Append-only `routing_revisions` row in the same transaction as each change; `GET /routing/revisions` | Integration + browser test | pytest + Playwright |
| 021 "validly in use" | "or already being used validly" is ambiguous | PROV / APPR (D9) | A slot value unchanged by the PUT is not re-validated. **Existing-route behaviour after a failed retest is retained** and surfaced as a warning; new selections need a current PASSED test | Test matrix incl. failed retest of a routed model | pytest; needs PO confirmation |
| 021 `decision_reference` | Actor phụ "records the document number" | PROV / APPR (D13) | Optional nullable field, **provisional until approved**; must be decided before M5 because history is append-only | Test only after approval | — |
| 021 concurrency | Lost updates | REC | `expected_revision` plus row lock; 409 `MDL_ROUTING_CONFLICT` | Two-thread race tests | pytest, repeated |

## FR-MDL-030 — DPA gate for external providers

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 030-AC1 | Missing agreement document number blocks test and use | SPEC | Gate in the connection-test service (M4) and routing eligibility (M5); 409 `MDL_DPA_REQUIRED`. Internal providers are exempt | Integration tests: test and routing both refuse | pytest |
| 030-AC2 | Agreement plus number allows the test | SPEC | Append-only agreement rows: basis ∈ {`NO_TRAINING_COMMITMENT`, `SCHOOL_WRITTEN_AUTHORIZATION`} plus non-empty `document_number` (M3) | Integration test | pytest |
| 030 no upload | FRD requires only a recorded number | SPEC | No file upload built | — | — |
| 030 withdrawal | Not in FRD; needed to correct a wrong record | REC / **awaiting approval** (D5) | Withdrawal is **permitted even if a model is routed**. It invalidates future eligibility (new tests and new routing selections are refused; earlier tests stay stored but are not "current") and the UI warns which routing is affected. Whether a routed external model must keep operating is a PO/Legal question | Test: withdraw with routed model succeeds, warning lists the routing, new selection refused | pytest; needs approval |
| 030 legal | System records a number only | SPEC / REC | UI states no legal review is performed; no legal approval is claimed | Browser text check | Playwright |

## FR-MDL-031 — Risk classification

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 031-AC1 | Each model in use shows its recorded risk | SPEC | `risk_level` ∈ {`HIGH`,`MEDIUM`,`LOW`} or NULL shown as "Chưa phân loại"; required before routing, not before testing; every change audited (M3, M6) | API and browser tests | pytest + Playwright |
| 031-AC2 | Demo sample data not locked in as the only required configuration | SPEC | No seed data; select starts empty; no vendor defaults | Migration test: all MDL tables empty after upgrade (**M2: done**, clean and populated `0003` paths; prototype labels such as `Cao` refused as risk codes) | pytest |
| 031 criteria | Classification criteria | SPEC (OQ-09-01 external) | **No criteria invented**; the system records a user-chosen level only. Optional `risk_basis_reference` text is PROV | — | PO to supply criteria later |

## FR-MDL-040 — No assistant-prompt configuration

| AC | FRD text (summary) | Basis | Planned implementation | Verification | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| 040-AC1 | No system prompt, creativity or template field/tab on the acceptance screen | SPEC | Four layers: Pydantic `extra="forbid"`; no columns; no JSONB; UI. The prototype's **Temperature** control (`apps/web/module1/module1.js`, `apps/web/shared/dialogs.js`, `apps/web/shared/actions.js`) is illustrative and must not be reproduced | OpenAPI schema scan for `prompt|temperature|template|creativity`; DB column-name test; DOM test | pytest + Playwright |

## Cross-cutting RULEs

| Rule | Basis | Planned control | Verification |
| --- | --- | --- | --- |
| RULE-MDL-01 only successfully tested models route | SPEC | See 020/021 | See 021 |
| RULE-MDL-02 external requires agreement before test/use | SPEC | See 030 | See 030 |
| RULE-MDL-03 no system prompt | SPEC | See 040 | See 040 |
| RULE-MDL-04 secrets never displayed and never in logs | SPEC | `SecretStr`, redaction, audit payload allowlist (no endpoint userinfo, no provider body) | Canary-secret scan of HTTP bodies, audit rows and `caplog` |
| §4 attribute: audit "who/what/when" without secrets (§1.2) | SPEC | Same-transaction typed audit events | Audit pairing and rollback-on-audit-failure tests |
| Append-only history | REC | No delete path in the application; revisions and agreements INSERT-only; **no promise of indefinite retention** (D11). **M2:** enforced by grants (no DELETE/TRUNCATE on any MDL table; no UPDATE on agreements or revisions; immutable columns not updatable) | Privilege-matrix test `test_runtime_privilege_matrix` (M2, automated) |

## M3 evidence (2026-11-25, automated, awaiting independent review)

API-level evidence only. **No AC is accepted**: UI parts (M6), connection-test parts (M4) and routing parts (M5) are still open. Tests: `tests/integration/test_m3_mdl_api.py` (PostgreSQL, real routes, runtime login) and `tests/unit/test_m3_contracts.py`.

| AC / rule | M3 status | Test | Still needed |
| --- | --- | --- | --- |
| 001-AC1 | Every MDL route: anonymous 401; `FOUNDATION_ADMIN` and an `AI_SPECIALIST` group member 403; write without CSRF refused; `AI_MODEL_ADMIN` allowed | `test_authorization_matrix_and_empty_lists` | UI hiding (M6) |
| 001-AC2 | Empty provider and model lists return 200 | same | UI empty states (M6) |
| 010-AC1 | External and internal providers created | `test_provider_credentials_follow_the_secret_rules` | UI (M6) |
| 010-AC2 | Blank secret on edit leaves ciphertext, nonce, key and version byte-identical; responses never contain the secret | same | "checked by a later connection test" (M4); blank field in UI (M6) |
| 010 secret rules | Origin change or scheme change needs a new secret; rotation bumps `credential_version`; HEADER_KEY rules; unsafe endpoints and headers refused; key ring missing → 503 with no change | same, `test_missing_key_ring_is_reported_and_blocks_only_secret_writes` | — |
| 011-AC1 / AC2 | Model created and listed; duplicate technical ID 409; `system_prompt`/`temperature`/`template` refused | `test_models_registry_risk_and_where_used_guards`, unit OpenAPI scan | UI (M6) |
| 012-AC1 / AC2 | Deactivating a routed model or its provider → 409 `MDL_MODEL_IN_USE` with `details.used_in`; after switching, deactivation succeeds; no DELETE route | same (routing rows seeded; routing writes are M5) | Race tests with real routing PUT (M5) |
| 030 recording | Basis + number, external only, append-only withdrawal, in force = latest non-withdrawn; withdrawal while routed reports `affected_routing` | `test_agreements_are_append_only_and_external_only` | Gate on test (M4) and routing (M5) |
| 031-AC1 | Risk recorded, filterable (`UNCLASSIFIED`), no default, audited as `mdl.model_risk_changed`; a routed model cannot be unclassified | `test_models_registry_risk_and_where_used_guards` | UI display (M6) |
| 040-AC1 | No such field in any input, output or OpenAPI document | `test_openapi_has_no_assistant_prompt_configuration`, `test_inputs_reject_unknown_fields` | DOM test (M6) |
| RULE-MDL-04 | Canary secrets absent from every response body, every audit row and captured logs | `mdl` fixture teardown scan; `test_provider_credentials_…` caplog check | — |
| Tenancy | Another institution's providers and models are invisible (404 on every route) | `test_other_institutions_are_invisible` | — |
| Atomicity | Audit failure rolls back provider and credential; concurrent duplicate creates → one 201, one 409 `MDL_DUPLICATE` | `test_audit_failure_rolls_back_provider_and_credential`, `test_concurrent_duplicate_creates_yield_one_provider` | — |
| 020-AC3 groundwork | MDL code imports no quota or credit module | `test_mdl_code_has_no_quota_or_credit_path` | Functional proof after QTA/CRT |

## M4 evidence (2026-11-25, automated, controlled server, awaiting independent review)

Evidence category: **automated tests against a controlled local server** on disposable private PostgreSQL 18. This proves wire format, network policy, transaction shape and the quota-free code path. It is **not genuine provider verification**: no live provider was called (none supplied, none authorized). **No AC is accepted.** Tests: `tests/unit/test_m4_egress.py` (148, no database) and `tests/integration/test_m4_connection_tests.py` (12, PostgreSQL, real routes, runtime login).

| AC / rule | M4 status | Test | Still needed |
| --- | --- | --- | --- |
| 020-AC1 | A successful test is stored as PASSED with a version snapshot and shows as the model's current state (`connection_test.result = PASSED`) | `test_lifecycle_blank_secret_rotation_and_failure` | Selection as primary/fallback (M5); **one recorded live-provider run (pending: PO/TL must supply a provider and credentials)** |
| 020-AC2 | A failed latest test leaves the model `FAILED`; every failure class is stored as a fixed code with no provider text; a configuration change makes earlier results `OUTDATED` | same, `test_failure_classes_are_recorded_without_provider_text`, `test_egress_policy_failures_are_recorded` | "Not selectable" enforced by routing (M5) |
| 020-AC3 | No quota/credit import anywhere in `mdl/` including `adapters/` (static, now recursive) | `test_mdl_code_has_no_quota_or_credit_path` | Functional proof after QTA/CRT exist |
| 020 fixed request | Captured body equals `probe_body(technical_id)`: one fixed message, `max_tokens` 16, no temperature or institutional data | `test_lifecycle_…`, `test_adapter_builds_one_fixed_request_without_generation_settings` | — |
| 020 safety (SSRF) | External: https/443/public DNS name only; IP literals, numeric/octal/hex/short forms, Unicode and full-width hosts, `localhost`, single labels refused; 40 private/special address cases refused, mixed answers refused; internal: operator allowlist, blocklist wins, loopback only by CIDR, invalid list fails closed | `test_external_destinations_must_be_public`, `test_external_endpoint_static_rules`, `test_internal_destinations_*`, `test_invalid_allowlists_fail_closed` | — |
| 020 safety (rebinding, pinning) | Resolved once; public-then-loopback answers never reach a second lookup; connection only to validated literals; peer re-checked; TLS SNI and certificate checked against the host name (wrong name and untrusted CA fail) | `test_dns_rebinding_is_closed_by_resolving_once_and_pinning`, `test_peer_address_is_checked_after_connecting`, `test_external_tls_uses_host_name_for_sni_and_verification`, `test_certificate_for_another_name_fails`, `test_untrusted_certificate_fails_with_the_default_trust_store` | — |
| 020 safety (bounds) | Redirect to metadata not followed; one request per test (no retries); 64 KiB cap (declared and chunked); slow reply and slow drip bounded by the total deadline; DNS deadline; proxy variables ignored; compressed replies refused | `test_redirects_are_reported_and_never_followed`, `test_no_retries_on_server_errors`, `test_oversize_responses_are_cut_off`, `test_slow_*`, `test_resolver_deadline`, `test_proxy_environment_is_ignored`, `test_encoded_bodies_are_not_decoded` | — |
| 020 transaction shape | `RUNNING` row committed before the call; no runtime session idle in a transaction during the call; provider edits proceed during the call; one test per model (409); config change during the call ⇒ `STALE_CONFIGURATION`; abandoned rows ⇒ `EXPIRED`; authority lost during the call ⇒ `ABORTED`, 403, no audit | `test_network_call_holds_no_transaction_and_stale_results_are_discarded`, `test_orphans_expire_and_lost_authority_aborts` | — |
| 020 scope (D3) | Image/voice-only model → 409 `MDL_TEST_UNSUPPORTED`, state `UNSUPPORTED` | `test_gates_refuse_before_any_network_activity` | — |
| 020 cost (D4) | External test refused without `acknowledge_provider_charges: true` (strict boolean); cooldown per model and configuration; process cap → 429 | `test_gates_…`, `test_cooldown_and_process_cap` | UI notice text (M6) |
| 010-AC2 | "Checked by a later connection test": after a blank-secret edit the provider receives exactly the original `Authorization` value; after rotation it receives the new one | `test_lifecycle_blank_secret_rotation_and_failure` | Blank field in the UI (M6) |
| 030-AC1 / AC2 | External model without an agreement in force → 409 `MDL_DPA_REQUIRED` before any DNS lookup; with an agreement the test runs; after withdrawal it is refused again | `test_gates_refuse_before_any_network_activity` | Routing gate (M5) |
| RULE-MDL-04 | Canary secrets absent from every response, every audit row (fixture scan), DEBUG logs and stored test rows; provider error text absent from audit and logs; `httpcore` DEBUG traces suppressed by the app; tampered ciphertext or missing key ring → 503 and nothing sent | `mdl` fixture teardown, `test_secret_never_reaches_logs`, `test_app_silences_httpcore_debug_traces`, `test_stored_rows_hold_codes_only`, `test_gates_…` | — |
| 001-AC1 (new routes) | Anonymous 401, `FOUNDATION_ADMIN` 403, no CSRF refused, nothing sent to the provider | `test_routes_require_mdl_rights_and_make_no_call_without_them` | — |

## M5 evidence (2026-11-26, automated and Docker smoke, awaiting independent review)

Evidence categories: (1) **automated** tests on disposable private PostgreSQL 18 with the loopback HTTPS fake provider: `tests/integration/test_m5_routing.py` (15) and `tests/unit/test_m5_contracts.py` (6); (2) a **Docker Compose smoke test** (disposable project, synthetic configuration, fake provider container on the Compose network, removed afterwards). Neither is genuine provider verification or acceptance. **No AC is accepted**: the UI parts (M6) and a live-provider run remain.

| AC / rule | M5 status | Test | Still needed |
| --- | --- | --- | --- |
| 021-AC1 | Models without a current PASSED test (and with any other issue) are excluded from `?routing_eligible=true` and refused by `PUT /routing` with `details.reasons` | `test_eligibility_matrix_and_selection_list` | Select list in the UI (M6) |
| 021-AC2 | Fallback equal to primary → 422 `MDL_FALLBACK_EQUALS_PRIMARY` (service) plus the database `CHECK`; fallback without primary → 422 | `test_changes_create_immutable_revisions_and_no_ops_do_not`, `test_routing_requires_mdl_rights_and_starts_empty` | — |
| 021-AC3 | Four changes → four readable revisions (who, when, before/after IDs and name snapshots, optional decision reference); no-op writes nothing; stale `expected_revision` → 409; runtime cannot UPDATE or DELETE history; audit failure rolls back routing and revision | same, `test_audit_failure_rolls_back_routing` | History tab (M6) |
| 021 "validly in use" (D9) | Unchanged slot persists; failed or outdated retest makes the slot unusable at once and the usable fallback effective; a passing retest restores it; nothing is rewritten | `test_route_persists_but_unusable_slots_fail_closed` | — |
| 021 concurrency | PUT vs PUT (including the first configuration), PUT vs deactivation, PUT vs credential rotation: repeated rounds, invariants hold | `test_concurrent_writers_serialize`, `test_selection_and_deactivation_never_leave_an_inactive_route`, `test_rotation_during_selection_is_never_lost` | — |
| 012-AC1 / AC2 | Deactivating a routed model (primary or fallback) or its provider → 409 `MDL_MODEL_IN_USE` with `used_in`; after switching, the old model can be deactivated | `test_deactivation_guards_follow_routing` | UI message (M6) |
| 030-AC1 (use) | External model without an agreement is not selectable (`dpa_missing`); withdrawal while routed keeps configuration and history but stops use (fail closed); a new agreement restores use | `test_agreement_withdrawal_fails_closed_and_keeps_history` | — |
| 020-AC1 / AC2 (selection) | PASSED ⇒ selectable; FAILED/OUTDATED ⇒ not selectable and not usable | `test_eligibility_matrix_and_selection_list`, `test_route_persists_…` | Live-provider run (pending) |
| 031 (use) | Unclassified model is not selectable (`risk_unclassified`); a routed model still cannot be unclassified (M3) | `test_eligibility_matrix_and_selection_list` | — |
| 001-AC1 (new routes) | Anonymous 401, `FOUNDATION_ADMIN` 403, no CSRF refused | `test_routing_requires_mdl_rights_and_starts_empty`; smoke test | — |
| RULE-MDL-04 / transport | Secrets never over plain HTTP (registration, connect time, eligibility); canary scan of responses and audit (fixture) | `test_registration_refuses_credentials_without_tls_and_unusable_hosts`, `test_credentials_are_never_sent_without_tls` | — |
| M4 risk fixes | Port-scoped allowlist; institution-wide test cap; acknowledgement audited; DNS thread cap; internal CA file; V2 style; key rewrap with tests staying current | `test_internal_destinations_*`, `test_institution_wide_test_cap_holds_across_workers`, `test_charge_acknowledgement_is_audited`, `test_abandoned_lookup_threads_are_bounded`, `test_internal_https_trusts_the_operator_ca_file`, `test_v2_style_sends_max_completion_tokens`, `test_rewrap_moves_credentials_to_the_active_key_without_outdating_tests` | — |
| Migration | Populated `0005` database → provision → migrate → `0006`: data kept, new column NULL, runtime grant correct, rerun no-op; revision IDs ≤ 32 characters | `test_populated_m4_database_upgrades_to_0006`, `test_every_revision_id_fits_alembic_version_column` | — |
| Docker smoke | Stack up, credential isolation (live), real test to a fake provider over the Compose network PASSED, routing revision 1, egress refused `db`, `api`, metadata and an unlisted port, rewrap CLI ran, schema `0006` | `~/.cache/aqm5/compose-smoke.sh` (outside the repository) | Repeat on the target host (M7) |

## M6 evidence (2026-11-26, automated API and browser, awaiting independent review)

Evidence categories: automated PostgreSQL tests; **Chromium through nginx** against the real API (`tests/browser/test_mdl.py`, 2 tests); a Docker Compose smoke run. The internal provider is the loopback HTTPS fake; the external provider's test request is intercepted in the browser so nothing leaves the machine. **No AC is accepted**; acceptance is M7 work and needs TL/PO sign-off.

| AC / rule | M6 status | Test | Still needed |
| --- | --- | --- | --- |
| 001-AC1 | `FOUNDATION_ADMIN` sees no MDL menu and gets "không có quyền" on `#mdl`; write controls render only with `mdl.manage`; server checks unchanged | `test_internal_provider_model_test_routing_and_guards` (setup) | Read-only UI view needs a viewer role (deferred, D7) |
| 001-AC2 | MDL administrator opens the screen; empty states shown ("Chưa cấu hình", "Không tìm thấy bản ghi phù hợp.") | same | — |
| 010-AC1 | Internal provider created through the UI (external in the second test) | both tests | — |
| 010-AC2 | Reopened edit form has an empty password-type secret field (`autocomplete="new-password"`); saving without it keeps the connection: the next real test sends the original secret | `test_internal_…` | — |
| 011-AC1 / AC2 | Model added under a provider appears in the list; no prompt/temperature/template control in any MDL view (DOM scan) | `test_internal_…`, `assert_no_excluded_fields` in both tests | — |
| 012-AC1 | Deactivating the routed model is refused with "Đang dùng làm mô hình chính" | `test_internal_…` | — |
| 020-AC1 / AC2 | Test from the UI against the fake → "Thử kết nối thành công."; model becomes eligible after risk; failed/outdated tests block use and selection | `test_internal_…` | **Live run (pending)** |
| 020 cost (D4) | External test dialog shows the cost notice ("có thể tính phí", "không trừ hạn mức"); unticked → no request sent; ticked → body `{"acknowledge_provider_charges": true}` | `test_external_cost_acknowledgement_…` | — |
| 020-AC3 | Write-set trigger on every table: a connection test writes only `mdl_connection_tests`, `audit_events` (and possibly `auth_sessions`); routing writes only routing tables; reads write nothing else; import closure of MDL reaches no quota/credit module | `test_m6_quota_isolation.py`, `test_mdl_import_closure_reaches_no_quota_or_credit_code` | End-to-end balance check once QTA/CRT exist |
| 021-AC1 / AC2 / AC3 | Routing dialog lists only eligible models (image-only model absent); fallback = primary refused in the dialog; decision number shown in history | `test_internal_…` | — |
| 021 D9 | After secret rotation the routing tab shows "Không có mô hình nào được phép dùng" with reason "Kết quả thử đã cũ" while the configuration stays | `test_internal_…` | — |
| 030-AC1 / AC2 / D5 | Agreement recorded with the "không thẩm định giá trị pháp lý" notice; withdrawal dialog warns that the routed model will not be used; afterwards the route stays configured but unusable ("Chưa có thỏa thuận dữ liệu còn hiệu lực") | `test_external_…` | Legal confirmation of the D5 reading |
| 031-AC1 / AC2 | Risk shown per model and in the list; classification dialog shows the D6 guidance labelled "không phải phân loại pháp lý"; no default | `test_internal_…` | Official criteria (OQ-09-01) |
| RULE-MDL-04 | Secret never in page HTML or any input value after save, reopen or rotation; secret inputs cleared after submit | `assert_secret_never_shown` (both tests) | — |
| Usability | 390 px width: no page-level horizontal overflow (found and fixed a top-bar defect) | `test_internal_…` | Manual review of the captures in M7 |

## Items verifiable only outside the repository

- Live provider connection with a real vendor: **no longer required** (Project Owner decision D15, synthetic provider used); optional procedure in the [runbook](MDL_LIVE_PROVIDER_VERIFICATION.md).
- Quota unchanged end to end (020-AC3): needs QTA/CRT.
- Docker Compose runtime, hosted CI, formal Tech Lead / PO acceptance: separate evidence categories; none recorded.

## M7 acceptance status (2026-11-26)

**Meaning of the classes.** *Verified*: every AC has passing automated evidence on the real routes and database (and Chromium where the AC is about the screen) in the M7 full gate. *Partially verified*: some ACs verified, others only structurally or against a controlled server. *Externally dependent*: completion needs an input outside the repository. *Unverified*: no evidence. **None of these is formal acceptance**; no Tech Lead, Product Owner, legal or school sign-off is recorded. Evidence: [M7 verification](MDL_IMPLEMENTATION_PLAN.md#m7-verification); a manual checklist is in the [handoff](mdl-handoff.md#5-manual-acceptance-checklist).

| Requirement | Status | AC evidence (tests) | Notes / external inputs |
| --- | --- | --- | --- |
| FR-MDL-001 Access | **Verified** | AC1: `test_authorization_matrix_and_empty_lists`, `test_routes_require_mdl_rights_…`, `test_routing_requires_mdl_rights_…`, `test_history_requires_mdl_read`; AC2: same + browser `test_internal_provider_model_test_routing_and_guards` (menu hidden and "không có quyền" for the foundation admin; empty states for the MDL admin) | Read-only screen variant needs a viewer role, deferred (D7); server rejects every write without `mdl.manage` |
| FR-MDL-010 Provider | **Verified** | AC1: both types via API and UI; AC2: blank secret on reopen (browser), unchanged ciphertext (M3), next real test sends the original secret (M4 API, browser); restore keeps the ciphertext usable (M7 `test_restore_keeps_ciphertext_usable_and_key_loss_fails_closed`) | — |
| FR-MDL-011 Model | **Verified** | AC1: API + browser; AC2: OpenAPI scan, `extra="forbid"`, no columns, DOM scan | — |
| FR-MDL-012 Deactivation guard | **Verified** | AC1/AC2: `test_deactivation_guards_follow_routing`, race test `test_selection_and_deactivation_never_leave_an_inactive_route`, browser refusal message; Compose smoke (409) | Routing is the only "mandatory configuration" today; QTA/CRT must register their own where-used checks (`mdl/usage.py`) |
| FR-MDL-020 Connection test | **AC1, AC2 verified (demo scope, D15); AC3 verified with populated QTA (Q6, 2026-11-27); CRT awaits Phase 5** | AC1: PASSED ⇒ selectable, against the repository's synthetic provider `infra/demo-provider/server.py` (`test_demo_provider.py`; Compose run with real TLS, Bearer and header keys, routing), plus the loopback test fake (API, browser); AC2: every failure class ⇒ not selectable, including `AUTH_FAILED` and `MODEL_NOT_FOUND` from the synthetic provider; AC3: structural (import closure), write-set test (`test_m6_quota_isolation.py`), and end-to-end populated-QTA proof (`test_q6_mdl_qta_isolation.py` — tester with `4,000` base entitlement, byte-identical lookup/budget/events/all 8 `qta_*` tables before & after PASSED/FAILED tests + routing, positive control & reverse check) | By the Project Owner's D15 no real vendor is required; vendor compatibility is **not** claimed. Consumption is `NOT_INTEGRATED` (balance = `base_entitlement`); CRT ledger isolation proof awaits Phase 5 |
| FR-MDL-021 Primary/fallback | **Verified** | AC1: eligibility matrix and selection list (API, browser); AC2: service + `CHECK` + browser; AC3: four changes → four revisions (API), history tab (browser), revision survives backup/restore (M7) | D9 persistence vs. fail-closed use decided under delegation |
| FR-MDL-030 DPA gate | **Verified** (technical) | AC1: test refused before any DNS lookup, selection refused (`dpa_missing`), use fails closed after withdrawal; AC2: test runs once an agreement is recorded (API; browser with intercepted call) | System records a number only; no legal review claimed; legal confirmation of the D5 reading advisable |
| FR-MDL-031 Risk | **Verified** (recording); criteria externally dependent | AC1: risk shown per model, unclassified ⇒ not eligible; AC2: no seed data, no default, empty tables after upgrade | Official criteria (OQ-09-01) external; current D6 criteria are internal guidance |
| FR-MDL-040 Excluded configuration | **Verified** | OpenAPI and schema scans, column test, DOM scans in both MDL browser tests | — |
| RULE-MDL-04 Secrets | **Verified** | Canary scans of every response and audit row (API fixtures), logs (`caplog`), page HTML and inputs (browser), history payloads (M7), backup file (M7: neither secret nor key in an uncompressed dump) | Python cannot wipe plaintext from memory (documented residual) |
| §6 Should: history with diff | **Verified** (M7) | `test_history_shows_each_change_with_before_and_after` (order, before/after values, filters, tenant isolation, tests excluded), `test_history_requires_mdl_read`, browser history assertions | Endpoint shown as origin + "path changed" flag by design |
| §6 Could: multi-fallback | Not implemented | — | Later phase |
| Picker limit (M6 observation) | **Fixed and verified** (M7) | Browser: 101 providers, the 101st preselected correctly | — |
