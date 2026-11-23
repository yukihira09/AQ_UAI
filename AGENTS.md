# AQ EduUAI coding-agent working contract

Read `README.md`, `docs/setup/PHASE_0_1.md`, `docs/architecture/BLUEPRINT_v1.md`, and the exact relevant FRD in `docs/frd/` before modifying code.

## Milestone and scope

- Phase 0 and Phase 1 established the demo and API/DB baseline. Phase 2 WP1–WP5 are accepted for continued source development. WP6 adds browser administration and WP7 supplies verification and handoff.
- Live rollout and Phase 3+ MDL/QTA/CRT server business logic require separate authorization.
- Do not claim FRD acceptance from frontend demo interactions or stub/mock-only backend behavior.
- Never implement later-phase features without explicit scoped instructions.

## Source rules

- The supplied original frontend is preserved under `apps/web/`, with SHA256 manifests in `docs/prototype/`. Do not refactor or modify the original 14 assets incidentally when changing backend code.
- Keep the HTML classic `<script>` order intact until a separately tested JS migration is authorized.
- Do not import `aq_uai-demo-v1` synthetic localStorage values into a production database.
- Use one versioned backend API (`/api/v1`) and SQLAlchemy/Alembic migrations. Do not create another independent schema under `infra/`.
- Keep secrets out of source, logs, HTTP responses and Git. `.env.example` is illustrative; `.env` must remain ignored.
- PostgreSQL and other host-published ports are localhost-only. Keep this development stack private. Production deployment requires a separate review.
- Follow the FRDs: MDL connection test must be real and quota-free; QTA group entitlement is additive; CRT ledger is append-only; **token/credit conversion is not defined**.
- Do not invent PO approval, legal documents, usage prices or model credentials.

## Required development loop

1. Explain which phase, FRD IDs and exact files are in scope.
2. Make the smallest reviewable change that preserves currently working UI/API behavior.
3. Add or update relevant tests (unit/integration/FRD acceptance), preferably before implementing a business rule.
4. Run `python scripts/verify_frontend_assets.py`, `node --check` for changed JS, and API tests appropriate to the change. `verify_original_archive.py` is a **Phase-0 historical parity check only** and will naturally fail after legitimate frontend edits; do not rewrite original hashes to hide such modifications.
5. Document verified behavior and separately list tests blocked by the local environment.
6. Do not create Git commits, push, change the Git remote, alter external accounts, or deploy without the user's explicit instruction.
7. Keep documentation beginner-friendly: **what / why / how / how to verify**; define new terminology.

## User-facing documentation

The developer is primarily an AI researcher new to general backend engineering. Prefer concise explanations of request flows, database writes, errors, and tests instead of unsupported jargon. Avoid a big-bang frontend rewrite or unnecessary microservice/infrastructure complexity.
