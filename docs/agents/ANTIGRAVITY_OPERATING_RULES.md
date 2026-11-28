# Operating rules for implementing agents (Antigravity: Gemini Neon / Carbon, Opus, …)

**Status:** binding from Phase 5 onward. `AGENTS.md` points here. If a stage prompt conflicts with this file, **stop and ask**; do not pick one silently.
**Why this file exists:** the reviewer (Claude Code) may be unavailable for several days while an agent implements one or more stages. Every change must stay reconstructible afterwards: what changed, why, how it was verified, and what is still open. These rules make that possible.
**Roles:**
- The **Project Owner (PO)** is the user. The PO decides, authorizes stages and commits.
- The **reviewer** is Claude Code. It verifies each stage independently and writes §11 of every stage report.
- The **implementer** is the agent. It implements, verifies and reports, and never approves its own work.

---

## R1. Authorization and scope

1. Implement **only** the stage(s) the PO names in the message, e.g. "Implement CRT stage C2". A plan, a stage prompt or a TODO is **not** authorization.
2. One stage = one closed unit of work. In multi-stage runs (R6), finish and close stage *n* completely (gate green, report, log entry) before starting stage *n+1*.
3. Stay inside the stage's **file allowlist** (in the stage spec of the phase plan). If a file outside it must change: **stop**, write the reason in the report under "Blocked", and ask. Never "fix it while you're there".
4. No refactors, renames, formatting sweeps or dependency additions unless the stage spec lists them.
5. Never implement a later stage's feature early, even when "trivial".

## R2. Hard prohibitions (any breach = stop and report; never work around them)

- Never read, print, copy or commit `.env`, keys, passwords or tokens. Synthetic test data only.
- Never edit `apps/web/` (frozen prototype) or `docs/prototype/` hashes.
- Never run Docker and never touch the developer's `aq-uai-dev` stack, its containers, volumes or images. Disposable PostgreSQL through the test harness only. (Docker rehearsals are the reviewer's job.)
- Never push, deploy, change Git remotes or rewrite history. Commit only when R6.4 allows it.
- Never call a real AI provider or anything that could be billed. Use the local fake providers.
- Never edit a migration that is already merged (`0001`–`0008`, then each new one once its stage is reviewed). New schema = new migration.
- Never weaken, skip, delete or `xfail` a test to get green. Edits to existing tests must be listed in the stage spec, or authorized by the PO, and each one is reported as before/after/why.
- Never invent prices, token/credit conversions, consumption figures, legal criteria or institutional policy. Unknown → `NEEDS-PO` / `NEEDS-INSTITUTION`.
- Never claim a test ran that did not run. Never mark an FR "accepted"; only the PO/Tech Lead do that.
- Never use the words "credit", "token", "Nạp credit" or "Nạp tiền" in user-facing UI. Amounts are **"đơn vị hạn mức"**.

## R3. Decisions and provenance

- Every non-trivial choice gets a provenance tag:
  - `SPEC`: the FRD says so.
  - `PO`: decided by the PO, with the date and where it is recorded.
  - `REC`: reviewer recommendation.
  - `PROV`: implementer's provisional choice.
  - `NEEDS-PO` or `NEEDS-INSTITUTION`: open.
- You may make `PROV` choices only inside the stage scope, and each one must be listed in report §8. You may **never** mark something `PO` yourself.
- If an `NEEDS-PO` item blocks the stage: stop and ask. Do not guess.

## R4. Evidence (per stage, in `docs/phaseN/reports/<stage>/`)

1. **Preflight, before any edit:** `git-status-before.txt`, `hashes-before.txt` and `baseline-gate.log`. Run the hash command from the repository root, and include root files:
   ```
   { find apps tests scripts infra docs .github -type f -not -path '*/__pycache__/*' \
       -not -path '*/.ruff_cache/*' -not -path '*/node_modules/*' -print0; \
     printf '%s\0' AGENTS.md CLAUDE.md README.md; } | sort -z | xargs -0 sha256sum
   ```
   If the baseline is not the expected count stated in the stage spec: **stop** and report it before coding.
2. **Postflight:**
   - `git-status-after.txt`;
   - `hashes-after.txt`, written to a temp path first and then moved in;
   - `changed-files.txt`, the diff of the two manifests, where every entry is explained in the report;
   - `focused-tests.log`, `final-gate.log` and `mutation-proof.log`;
   - `screenshots/` for UI stages.
3. **Full gate command** (record the API and browser counts separately):
   `AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin AQ_PHASE2_PYTHON=<venv python> AQ_NGINX=<nginx or wrapper> bash scripts/verify_phase2.sh`
4. **Flake policy:** a known startup-timing flake in an old browser test may be re-run **once**; record both runs. Any other failure is a failure.
5. **Mutation proofs** (each stage spec lists them):
   - break the rule temporarily;
   - run the named test and show it fail;
   - restore the file byte-identically;
   - record the sha256 before and after.
   A test that cannot fail proves nothing.
6. No secrets, dumps or personal data in any evidence file.

## R5. The stage report (`docs/phaseN/reports/<PREFIX>_<STAGE>_REPORT.md`): exact sections

Use these numbers and titles. If something was not done, write **`NOT DONE: <reason>`** in its place. Never omit a section.

1. **Summary.** Five lines. Status is always "implemented, awaiting review".
2. **Files.** Every created or modified file: path, new or modified, why, FR or finding. It must match `changed-files.txt`.
3. **Design in plain words.** Request flow, database writes, locks, errors. For a beginner; define new terms.
4. **API / UI contract.** Routes, permissions, status and error codes, audit actions, example bodies (synthetic). For UI stages: what each role sees.
5. **FR / AC coverage table.** Every FRD acceptance line in scope → the test and assertion that proves it, or "not covered: why".
6. **Tests.** Every new test → FR/AC/rule. Every edited existing test → before/after/why.
7. **Results.**
   - Baseline vs final (API passed/skipped, browser passed).
   - Static checks and `alembic check`.
   - Mutation table with hashes.
   - Log paths.
8. **Decisions and deviations.** The REC decisions as applied, every PROV choice with its reason, and every deviation from the spec.
9. **Not verified / risks / blocked.** Always list: hosted CI, Docker Compose, the real developer stack, browsers other than Chromium, and anything else that was skipped.
10. **Implementer self-review (critic pass).** Run it after the gate, against R7. Also answer every question the stage prompt asks, by its ID. Say what was unclear or wrong in the prompt or plan.
11. **Reviewer response.** Leave empty: `<!-- Reserved for reviewer -->`.

## R6. Multi-stage runs (when the PO authorizes several stages in one message)

1. Each stage runs its **own full cycle**: preflight → code → focused tests → full gate → evidence → report → log entry. The baseline of stage *n+1* is the final gate of stage *n*. It may be reused as the preflight gate only when no file changed in between; say so explicitly.
2. **Stop on red.** If a stage's gate is not green, or a STOP condition (R8) occurs, do not start the next stage. Write the report with "Blocked" and stop the whole run.
3. Never interleave stages. A file changed in stage *n+1* must not be "fixed back" into stage *n*'s evidence.
4. **Commits.** Commit only when the PO's message explicitly says "commit after each stage":
   - one local commit per stage, after its report is complete;
   - message `<PREFIX> <STAGE>: <short summary>`, e.g. `CRT C2: ledger schema 0010 + runtime grants`;
   - never push, never amend, never squash.

   Without that instruction, do not commit. Instead, print the exact `git add`/`git commit` commands at the end of the report for the PO.
5. At the end of a multi-stage run, add a short "Run summary" to the agent log: the stages done, the stage that stopped and why, and what is next.

## R7. Self-review checklist (answer each in report §10, yes/no plus evidence)

1. Tenant isolation: does every query filter `institution_id`, with composite keys on joins?
2. Authorization: does every write go through `authorization.writes.protected` with transaction-time re-check, Origin/CSRF and the correct permission and scope? Do UNIT-scoped actors stay inside their unit?
3. Is the audit event written in the **same** transaction, with a typed payload and no free-text secrets?
4. Is the ledger or history really append-only (no UPDATE/DELETE grant, no route, no UI button)?
5. Concurrency: is the lock order documented and consistent with `QTA_ARCHITECTURE_AND_DECISIONS.md` §4.3? Is there a concurrency test for every invariant that a race could break?
6. Is the user-facing wording Vietnamese, with "đơn vị hạn mức" and no forbidden words? Is the UI XSS-safe (no `innerHTML` with data)?
7. Are there no N+1 queries on list endpoints (a counted-query test where relevant)?
8. Were MDL/QTA files touched? If yes, were they declared in the stage spec, and does the full QTA/MDL suite pass?
9. Docs: are traceability, plan completion, status lines and agent log updated? Does formal acceptance still read unchanged?

## R8. STOP conditions (stop, write the report with "Blocked", ask the PO)

- The baseline gate does not match the expected counts.
- A file outside the allowlist must change, or a merged migration seems wrong.
- An FRD requirement conflicts with a recorded decision (PD-*, R*, ADR).
- A `NEEDS-PO` decision blocks progress.
- A test can only pass by weakening it.
- A security doubt: secrets, tenant leak, authorization bypass.
- The same failure persists after two honest fix attempts. Report what was tried; do not thrash.

## R9. The agent log (`docs/phaseN/AGENT_LOG.md`, append-only)

After every stage, **append** one entry. Never edit earlier entries; corrections go in a new entry.

```
## <YYYY-MM-DD> · <STAGE> · <model name> · status: IMPLEMENTED-AWAITING-REVIEW | BLOCKED
- Authorized by: <quote the PO's instruction>
- Base commit: <hash>   Commit made: <hash or "none (PO commits)">
- Gate: baseline API x/y skipped, browser z → final API x/y, browser z
- Files: <count> changed — see reports/<stage>/changed-files.txt
- Decisions: PROV-… (one line each); NEEDS-PO raised: …
- Deviations / blocked: … (or "none")
- Report: reports/<PREFIX>_<STAGE>_REPORT.md
- Review status: PENDING
```

The reviewer later changes nothing in old entries. It appends "REVIEWED <stage>: verdict, fixes" as a new entry.

## R10. Cross-module safety

- **MDL** must never import QTA or CRT code (`test_mdl_import_closure_reaches_no_qta_code` must stay green; extend it to CRT). **QTA** may only be changed where the stage spec says so, and the full QTA suite must stay green.
- Shared foundations (`authorization/`, `auth/`, `db/audit.py`, `db/provision.py`, `directory/`) are touched **only** where the stage spec lists it, with the reason in the report.
- New advisory-lock namespaces must be documented in the phase architecture doc with their place in the global lock order.
