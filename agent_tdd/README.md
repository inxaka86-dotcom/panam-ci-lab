# Public synthetic agent TDD pilot

Purpose: demonstrate a **fail-first -> fix -> verify** workflow with deterministic
evidence, without running an AI agent or accessing any private environment.

## Scope

- All samples are invented; paths refer to a **virtual** synthetic/ root.
- No model calls, remote tool execution, live repository edits, secrets, or
  private PANAM data are used by this pilot.
- plan_guard.py validates an inert plan manifest only. It does not establish
  real filesystem containment, symlink policy, process isolation, production
  approval, or a replacement for any existing security gate.
- unsafe_baseline.py is deliberately wrong and is an expected-fail control;
  it must never be used for authorization.
- Green public CI demonstrates only the documented synthetic contract.

## TDD sequence

1. **Specification:** tests/test_plan_guard.py defines a tiny change-plan contract
   with positive cases and negative cases including path escape and bad actions.
2. **RED:** run the same tests against unsafe_baseline.py; the suite must fail
   with actual test assertion failures, not with import or setup errors.
3. **GREEN:** run the unchanged tests against plan_guard.py; all must pass.
4. **Review:** inspect CI receipts, changed files and permissions before reuse.

### Local verification

Run from the repository root:

\`\`\`sh
python3 checks/publication_gate.py
python3 -m agent_tdd.verify
\`\`\`

Expected receipt fields:

\`\`\`text
TDD_NEGATIVE_CONTROL=PASS expected_failures=<nonzero>
TDD_GREEN=PASS tests=9
DATA_CLASS=PUBLIC_SYNTHETIC
LIVE_AGENT_EXECUTION=NO
PRODUCTION_ACCESS=NO
\`\`\`

This is a **Superpowers-inspired engineering-method experiment**, not an
installation or actual execution of Superpowers, OpenHands, Aider or any other
coding-agent runtime. A distinct future test could run one upstream agent
inside a disposable sandbox with pinned versions, constrained resources,
and a separate approval boundary.
