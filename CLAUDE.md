@AGENTS.md
# CLAUDE.md — AQ EduUAI

Read these before changing anything; link to them rather than duplicating their contents here:

- Binding rules: [AGENTS.md](AGENTS.md) (overrides defaults; scope, source rules, development loop).
- Project onboarding and evidence levels: [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md).
- Canonical FRDs: `docs/frd/` (root-level `AQ-FRD-UAI-*.md` files are untracked duplicates; ignore them).
- Phase 3 MDL (implemented & technically verified, M1–M7):
  - FRD: [docs/frd/AQ-FRD-UAI-MDL-001.md](docs/frd/AQ-FRD-UAI-MDL-001.md) · Plan: [docs/phase3/MDL_IMPLEMENTATION_PLAN.md](docs/phase3/MDL_IMPLEMENTATION_PLAN.md) · Handoff: [docs/phase3/mdl-handoff.md](docs/phase3/mdl-handoff.md) · ADR: [docs/architecture/ADR-0003-mdl.md](docs/architecture/ADR-0003-mdl.md)
- **Current work: QTA (Phase 4, Module 2 — Q0, Q1, and Q1-R completed; Q2 next upon authorization).**
  - FRD: [docs/frd/AQ-FRD-UAI-QTA-001.md](docs/frd/AQ-FRD-UAI-QTA-001.md) · ADR: [docs/architecture/ADR-0004-qta.md](docs/architecture/ADR-0004-qta.md)
  - Implementation plan: [docs/phase4/QTA_IMPLEMENTATION_PLAN.md](docs/phase4/QTA_IMPLEMENTATION_PLAN.md)
  - Open decisions & PO decisions (`PD-Q1..PD-Q6`): [docs/phase4/QTA_OPEN_DECISIONS.md](docs/phase4/QTA_OPEN_DECISIONS.md)
  - Architecture: [docs/phase4/QTA_ARCHITECTURE_AND_DECISIONS.md](docs/phase4/QTA_ARCHITECTURE_AND_DECISIONS.md)
  - Traceability: [docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md](docs/phase4/QTA_REQUIREMENTS_TRACEABILITY.md)
  - Q1 review brief: [docs/phase4/QTA_Q1_REVIEW.md](docs/phase4/QTA_Q1_REVIEW.md)

## Working rules

- **Plan first.** State the phase, FRD IDs, milestone, and exact files or areas in scope before implementation. Implement only the authorized milestone (M0 = documentation only; M1+ require explicit authorization).
- **Protect secrets.** Never read, print, expose, or commit `.env`. Never put secrets in logs, responses, tests, or documentation.
- **Protect project operations.** Do not commit, push, deploy, or change Git remotes unless explicitly asked. Do not edit `apps/web/` or alter its protected original files and hashes.
- **Reuse existing foundations.** Reuse shared authentication, authorization, audit, error-handling, and migration infrastructure. Never create parallel implementations without a documented and justified reason.
- **Preserve decision provenance.** Distinguish specified (FRD), recommended, provisional, and resolved-under-delegated-Project-Owner-authority decisions. When a task explicitly delegates decision-making authority, resolve decisions within that mandate and document the rationale, trade-offs, and provenance. Never claim approval from a separate PO or Tech Lead unless explicitly recorded.
- **Preserve evidence integrity.** Keep automated tests, Docker verification, hosted CI, developer-reported results, and formal acceptance separate. Never infer acceptance or sign-off; verify the current acceptance records.
- Do not invent legal criteria, usage prices, provider credentials, or token/credit conversion rules.

## Execution and efficiency

- Start with task-relevant files and targeted searches. Expand inspection whenever shared foundations, security, migrations, architectural dependencies, or regression risks require it.
- Follow `AGENTS.md` for the mandatory development loop, source precedence, and project-specific engineering rules.
- Do not duplicate existing documentation or refactor unrelated code.
- Prefer existing dependencies and abstractions. Introduce new ones only when technically justified.
- Do not use subagents for straightforward, self-contained tasks.
- Run focused tests first, then expand verification when changes affect shared foundations, security boundaries, migrations, or broader behavior.
- Never claim unexecuted tests or unverified behavior as successful.

## Completion report

Briefly report:

1. Changes made and modified files.
2. Tests and checks executed, with their results.
3. Blocked, unverified, or incomplete items.
4. Remaining decisions, risks, or required authorization.