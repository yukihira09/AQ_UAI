# Stage prompt for the implementing agent — Phase 5 CRT (reusable)

**How the PO uses this:**
1. Copy everything inside the fence.
2. Replace `<STAGES>` with the stage(s) you authorize, e.g. `C1`, or `C1, C2`.
3. Replace `<COMMIT_MODE>` with either `commit after each stage` or `do not commit`.
4. Paste it into a **new** Antigravity session.

Use one stage per session where possible. For a batch, follow the recommended batches in [CRT_IMPLEMENTATION_PLAN.md](CRT_IMPLEMENTATION_PLAN.md) §6.

**Before pasting:**
- Commit everything reviewed so far: the tree must be clean.
- Check [AGENT_LOG.md](AGENT_LOG.md): the previous stage must not be `BLOCKED`.
- For C1 or later, every PD-C must already be confirmed (C0 exit).

~~~text
# AQ EduUAI — Phase 5 CRT, stage(s) <STAGES>. Authorized by the Project Owner.
# Commit mode: <COMMIT_MODE>.

You are the implementing agent. The Project Owner (PO) decides; the reviewer (Claude
Code) verifies later, possibly days from now. Everything you do must be reconstructible
from your evidence, report and log entry alone.

## 0. Read first (all of it, before any edit)
1. AGENTS.md and CLAUDE.md.
2. docs/agents/ANTIGRAVITY_OPERATING_RULES.md — binding. Follow R1–R10 exactly.
3. docs/phase5/CRT_IMPLEMENTATION_PLAN.md — the spec of each stage you are authorized
   for (scope, allowlist, tests, mutation proofs, exit), plus §2 decisions, §3
   architecture and §5 phase rules.
4. docs/phase5/CRT_OPEN_DECISIONS.md (from C0 on): the PD-C status. If a PD-C your
   stage depends on is not "PO", STOP (rules R8).
5. docs/phase5/AGENT_LOG.md: what happened before you, and any reviewer notes.
6. docs/frd/AQ-FRD-UAI-CRT-001.md (all), docs/phase4/qta-handoff.md §7–§8,
   docs/phase4/QTA_ARCHITECTURE_AND_DECISIONS.md (§2–§4), docs/PROJECT_CONTEXT.md.
7. The code the stage touches, and the closest existing pattern: qta/ for backend,
   qta.mjs for UI, tests/*/test_q*.py for tests. Reuse helpers; never copy them.

## 1. For EACH authorized stage, in order
a. Preflight evidence into docs/phase5/reports/<stage>/ (rules R4.1). Compare the
   baseline gate with the expected counts (plan §4, or the previous stage's final
   gate in AGENT_LOG.md). Mismatch → STOP.
b. Implement exactly the stage spec. Tests first where a business rule is involved.
c. Focused tests, then the full gate (rules R4.3). Mutation proofs (R4.5).
d. Postflight evidence (R4.2).
e. Report docs/phase5/reports/CRT_<STAGE>_REPORT.md with the EXACT sections of rules
   R5. Section 10 must answer every R7 checklist item, plus:
     X-1 What in the plan or this prompt was unclear, wrong or missing for this stage?
     X-2 What should the NEXT stage know (traps, decisions, numbers)?
     X-3 Any PROV decision you made that the PO should confirm?
f. Update the docs the stage lists (traceability, plan "<STAGE> completion" section,
   status lines). Formal acceptance stays unchanged.
g. Append the AGENT_LOG.md entry (rules R9). Review status: PENDING.
h. Commit only if the commit mode says so (rules R6.4); otherwise print the commands.
i. If anything failed or a STOP condition happened: write the report with BLOCKED,
   append the log entry with status BLOCKED, and stop the whole run (rules R6.2).

## 2. At the very end
Reply with a short summary of each stage: status, final gate counts, the report
path, open NEEDS-PO items, and what the PO should do next. Do not start any stage that
was not authorized above.
~~~
