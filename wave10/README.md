# Wave 10 — Harness² local recursion smoke

Status: **experimental / public synthetic CI only**.

## Question

Can the pinned upstream Harness² code execute its deterministic **parallel** and
**sequential** Propose–Probe–Compose demo, complete the two built-in synthetic
ledger tasks, and save machine-readable reports without any model/provider
credentials?

This is a **mechanics / integration smoke**, not a measurement of improved
legal reasoning or tender accuracy.

## Immutable upstream

- Source: https://github.com/google-research/harness2
- Commit: `1cfe254e8d25b15f37048c3730134686abe60335`
- Demo entrypoint: `harness2-demo` from upstream `harness2/cli/demo.py`
- Python: 3.12
- Budget: `k=1`; modes tested separately: `parallel` and `sequential`
- Fixtures: upstream's **fictional** ledger-1 and ledger-2; no PANAM data.

The source is fetched at the exact commit, checked out detached, its HEAD is
verified, and the git remote is removed. No floating `main` runtime is used.

## Execution and evidence

CI: `.github/workflows/wave10-harness2-local-demo.yml`.

The job:
1. uses a GitHub-hosted ephemeral `ubuntu-latest` runner;
2. checks the PANAM public-only publication boundary;
3. installs only the pinned public source (no optional integrations);
4. runs both demo modes with distinct temporary output roots;
5. requires `failed == 0`, `done == 2`, positive execution and editor counts;
6. prints a bounded machine-readable summary and report SHA-256 hashes.

Each demo writes `demo.json`. The actual raw reports stay on the temporary
runner and are not used as PANAM production evidence.

## Security / authority

- Public synthetic data only; no confidential documents, production source,
  credentials, model API tokens, attached service accounts, or private repos.
- No PANAM self-hosted runner, Control Plane call, production action, or deploy.
- GitHub `contents: read`; checkout credentials are not persisted.
- **The upstream demo does not impose a network egress sandbox.** Although
  the runner is ephemeral and contains no PANAM credentials, this is *not*
  proof of network-level containment. Do not copy this workflow onto a
  privileged runner or replace synthetic input with real data.
- A green CI result proves only the observed pinned **demo mechanics**, not
  reasoning quality, legal accuracy, or suitability for PANAM production.
- No automatic promotion, merge, autonomous optimization, or agent execution
  against PANAM systems is authorized.

## Next experiment (not activated here)

Separately evaluate candidate vs baseline harnesses on a small, human-reviewed
set of synthetic legal and procurement tasks, with invariant scoring rules,
source attribution and hallucination checks. Keep comparison inputs and model
budget fixed; record exact task/config/run identity and failure evidence.
Changing PANAM live agent prompts or tool privileges requires its normal
approval and verification process.

## Known limitations

The CI run requires GitHub/network access to fetch pinned public source and
build dependencies, and has unrestricted network access during demo execution.
It uses no LLM; therefore any generated comparison against baseline here would
be misleading. Results of this PR remain **unverified** until the new
workflow's run logs and summary have been inspected.
