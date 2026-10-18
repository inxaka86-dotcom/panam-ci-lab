# Wave 11 — PANAM Harness² synthetic legal/tender A/B

**Scope:** public CI proof of scripted harness adaptation, not a test of LLM legal reasoning.

## Hypothesis

For two tiny synthetic domains, does Harness²'s real recursion scheduler execute the original script, probe a deterministic reviewable improvement to the editable harness script, select a revised final and produce a better exact-match result?

The deterministic editor repairs one known issue: classification of an explicit negation. The baseline treats both "обязан" and "не обязан" (or "требуется" and "не требуется") as requirements.

The examples are newly authored fiction; they are **not** actual Russian legal interpretations or authentic procurement documentation.

## Experiment contract

- Source: https://github.com/google-research/harness2
- Upstream commit: 1cfe254e8d25b15f37048c3730134686abe60335
- Entrypoint: python wave11/panam_harness2_ab.py --output OUTPUT_DIR
- Two domains: legal, tender.
- Two tasks per domain, three fictional clauses per task: **12 examples** total.
- Fixed k=1; run both parallel/agg and sequential/seq.
- Baseline vs selected final are evaluated on the **same** examples with identical strict scoring.
- Each line is exactly classified REQUIRED, NOT_REQUIRED, or UNKNOWN.
- Reject duplicate, missing, invented, malformed IDs/labels (fail closed).
- Require zero scheduler failures, no score regression, strict improvement in both domains and both modes. Emit machine-readable metrics and SHA-256.
- Budget: one ephemeral GitHub-hosted runner, 15 minutes max, no model calls.
- Upstream packages installed without extras or cloud/provider authentication.

**Oracle separation:** gold labels live in the evaluator in memory. The editor receives source statements and execution observations, but not the gold mapping through the Harness² task workspace. This is not a security boundary against malicious Python; the editor is trusted, hand-written code running in the same Python process.

## Interpretation

This is a deliberately easy controlled test. A higher score demonstrates that the Harness² scheduler can transport a predetermined repair from proposals to selected executions in this synthetic adapter. It **does not** measure AI-generated improvement quality, legal validity, procurement compliance, generalization to unseen documents, or model cost-effectiveness.

There is no automatic adoption into any PANAM agent. A real model-backed A/B would need separately approved isolated network egress, pinned provider/model, a blind held-out dataset, a judge not visible to the solver, token/cost caps, manual source review, and PANAM Risk/Privacy/Approval gates.

## Security boundaries

1. Public synthetic text only. No private PANAM code, documents, history, client data, infrastructure identifiers, secrets, or provider credentials.
2. GitHub-hosted ephemeral ubuntu-latest, never PANAM self-hosted runners.
3. contents: read, checkout without persistent credentials, pinned upstream commit and Actions SHAs. No production Control Plane or deploy.
4. **Not network sandboxed**. The upstream source runs with runner egress; CI success does not prove runtime containment.
5. Separate feature branch and draft PR; no merge or release authority.
6. Do not treat a passing synthetic benchmark as production readiness.

## Evidence

Workflow: .github/workflows/wave11-harness2-synthetic-ab.yml

Only accept measured claims after inspecting the actual GitHub Actions job log with the emitted PANAM_HARNESS2_AB, report digest and exact branch commit.
