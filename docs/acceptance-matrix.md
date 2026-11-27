# Three-FRD acceptance tracker

**Current status: none of the 33 module requirements are accepted.** The source UI is a prototype; Phase 0–1 added only infrastructure and a diagnostic endpoint.

**MDL update (2026-11-26):** the nine MDL requirements are implemented and have automated evidence (see the Evidence column). Technical verification is not acceptance: they stay **not accepted** until a Tech Lead or Product Owner records sign-off here.

**QTA update (2026-11-27, Q2):** Phase 4 Stages Q0–Q1-R (RBAC `0007_qta_access_catalog`, 8-table schema `0008_qta_schema`, PO decisions `PD-Q1..PD-Q6`, `ADR-0004`) and Stage Q2 (group registry, sync, AI-specialist group lifecycle reusing `directory.service`, and group × model quota configuration APIs under `/api/v1/qta`; see [QTA_Q2_REPORT.md](phase4/reports/QTA_Q2_REPORT.md)) are implemented and verified via the full `verify_phase2.sh` gate (API: 525 passed, 1 skipped; browser: 16 passed; awaiting review). No `FR-QTA-*` requirement is formally accepted yet (entitlements, budgets, kill-switch, reset, and `#qta` Admin UI arrive in Stages Q3–Q5). CRT is not started.

| FRD | Requirement | Implementation | Evidence |
| --- | --- | --- | --- |
| AQ-FRD-UAI-MDL-001 | FR-MDL-001 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-010 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-011 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-012 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-020 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | AC1–AC2 verified with the synthetic demo provider (Project Owner decision D15); AC3 needs QTA/CRT: [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-021 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-030 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-031 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical); official criteria external: [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-040 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-001 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-010 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-011 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-020 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-021 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-022 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-030 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-031 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-032 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-040 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-041 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-QTA-001 | FR-QTA-050 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-001 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-002 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-010 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-011 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-012 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-013 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-020 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-021 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-022 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-030 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-031 | Not started (backend) | Planned acceptance test |
| AQ-FRD-UAI-CRT-001 | FR-CRT-040 | Not started (backend) | Planned acceptance test |

Update this table only when a real backend operation, authorized API, and expected result have been verified. Do not mark an item completed because a screen or simulated localStorage behavior exists.

Business ambiguities (token/credit relationship, budget rules, DPA approval and unit-level delegation) must be decided with the PO before asserting accounting acceptance.
