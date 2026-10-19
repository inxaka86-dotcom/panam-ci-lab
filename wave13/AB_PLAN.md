# Leanrea paired Codex A/B — evidence intake contract (research only)

Status: PUBLIC-SAFE / SYNTHETIC CONTRACT / NO EXECUTOR / NO LLM / NO BILLING / NO INDEPENDENT SCORE.

## Question

Does a pinned, constrained Leanrea instruction improve an otherwise identical coding agent's evidence-based analysis of authorized synthetic artifacts? Distinguish **answer correctness** from **wall time**, **input/output token usage**, **actual provider cost**, and **safety violations**. A win in one dimension never implies a win in the others.

## Proposed equal-condition pairs (not yet conducted)

Four case IDs reserve these analysis types: LR-E01 (Electron hidden bundler / IPC), LR-N01 (ELF/native import inventory), LR-G01 (Go static build information), LR-D01 (multi-hop static call/string reasoning). All targets must be newly fabricated public-safe fixtures; no third-party desktop app, customer data, production binaries, company secrets or private source. Target content and answer keys **have not yet been built or accepted**. The IDs are placeholders, not benchmark evidence.

Run both arms on the **same exact task bytes and fixture bytes**:
- `base`: selected agent/model/provider and native preinstalled local CLI tools, without Leanrea instructions.
- `leanrea`: identical setup with only the independently pinned `wave13/SKILL.md` guidance introduced through an approved agent skill-loading path.

The candidate skill changes guidance, NOT tool grants, model, task text, permitted commands, environment, network, temperature, reasoning tier or max tokens. Freeze profiles, fixture SHA-256, exact code SHA, route SHA-256, environment SHA-256, per-run trace hashes and provider usage receipts. Cross-over case order should be fixed and published before any billable run. Include setup/skill loading tokens in measured totals. No retries or silent fallback.

Do **not** borrow the budget or permission from an unrelated Harness² A/B: this is a distinct research experiment. A full model-backed run requires separately approved spend, exact provider/model/wire entitlement, external USD-denominated enforcement, a disposable unprivileged executor with provable egress restrictions, independently blinded ground truth and held-out questions, and access through a reviewed existing PANAM execution/approval lane. Public GitHub Actions cannot call a model or hold credentials for this pilot.

## Minimal offline receipt shape

`ab_trace_contract.py` admits a packet containing:
- a versioned schema and honest `data_class` (synthetic or claimed observed);
- pinned lab HEAD SHA-1 and separate skill/task/route/environment SHA-256 identities;
- two distinct arm profile hashes;
- exactly the four identical task IDs, each with base/leanrea runs, common task SHA-256, identical route and environment hashes, unique run IDs, trace and receipt SHA-256 references, measured latency and token figures.

The program rejects extra/missing fields, duplicated cases/runs, changed route/environment, mismatched profiles, malformed digests, negative and Boolean token counts, unsupported accuracy claims and unsupported USD costs. It projects **unverified input** counts and differences for inspection. It has no network, provider client, runtime launcher, answer scorer, privileged action or persistent state. It cannot verify the hashes against an external ledger, inspect provider receipts or validate actual model responses. Its output always says `SHAPE_ONLY_NEVER_EXECUTION_AUTHORITY` and `real_model_benefit_proven=false` — including when `data_class=observed`.

Do not label synthetic fixture arithmetic as a measured agent improvement. Task scoring and blind accepted answers belong to a separately reviewed evaluator and must not be provided to the running model. A published public task pack cannot be treated as truly held out against internet-connected models.

## Offline tests (no model/provider calls)

Run:
```sh
python3 -m unittest discover -s wave13 -p 'test_ab_trace_contract.py' -v
```

All test records and hashes are deliberately fabricated and safe for publication. The tests check positive schema parsing and adversarial rejection, not an actual Codex A/B. The existing Wave 13 workflow runs them on a temporary public GitHub-hosted runner with no secrets or model endpoints.

## Next explicit admission gate

Real performance claims must come from a separate approved runner and verified end-to-end receipts: each case's accepted answer and cited source offset, safe action trace, tool-count, provider usage/expense, runtime duration, and success/failure. Ingest only redacted/hashes in public CI. Perform independent correctness/security review before calculating model advantage. No merge, deploy or production permission arises from this document or a green workflow.
