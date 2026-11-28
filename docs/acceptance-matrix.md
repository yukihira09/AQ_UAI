# Three-FRD acceptance tracker

**Current status: none of the 33 module requirements are accepted.** The source UI is a prototype; Phase 0–1 added only infrastructure and a diagnostic endpoint.

**MDL update (2026-11-26):** the nine MDL requirements are implemented and have automated evidence (see the Evidence column). Technical verification is not acceptance: they stay **not accepted** until a Tech Lead or Product Owner records sign-off here.

**QTA update (2026-11-27, Q6):** Phase 4 Stages Q0–Q6 (RBAC `0007_qta_access_catalog`, 8-table schema `0008_qta_schema`, PO decisions `PD-Q1..PD-Q6`, `ADR-0004`, Q2–Q4 API/CLI, Q5 `#qta` Admin UI, and Q6 `FR-MDL-020 AC3` populated-QTA isolation proof, `0006 → 0008` populated upgrade, backup/restore rehearsal & [qta-handoff.md](phase4/qta-handoff.md); see [QTA_Q6_REPORT.md](phase4/reports/QTA_Q6_REPORT.md)) are implemented and technically verified via the full `verify_phase2.sh` gate (API: 583 passed, 1 skipped; browser: 21 passed; awaiting Q6 review). Technical verification is not formal acceptance: all 12 `FR-QTA-*` requirements stay **not accepted** (`0/33` total) until Tech Lead / Product Owner sign-off. CRT is not started (Phase 5 awaits separate authorization).

| FRD | Requirement | Implementation | Evidence |
| --- | --- | --- | --- |
| AQ-FRD-UAI-MDL-001 | FR-MDL-001 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-010 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-011 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-012 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-020 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | AC1–AC2 verified with synthetic demo provider (D15); AC3 verified with populated QTA (Phase 4 Q6 `test_q6_mdl_qta_isolation.py`, CRT awaits Phase 5): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-021 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-030 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-031 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical); official criteria external: [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-MDL-001 | FR-MDL-040 | Implemented (Phase 3 M1–M7, 2026-11-26); **not accepted** | Verified (technical): [M7 status](phase3/MDL_REQUIREMENTS_TRACEABILITY.md#m7-acceptance-status-2026-11-26) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-001 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-010 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-011 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-020 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-021 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-022 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-030 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-031 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical); consumption `NOT_INTEGRATED`: [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-032 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical); host scheduler documented in [handoff](phase4/qta-handoff.md#5-scheduling-the-monthly-reset-documented-not-executed): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-040 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-041 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
| AQ-FRD-UAI-QTA-001 | FR-QTA-050 | Implemented (Phase 4 Q1–Q6, 2026-11-27); **not accepted** | Verified (technical): [QTA traceability](phase4/QTA_REQUIREMENTS_TRACEABILITY.md) |
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
