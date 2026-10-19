# Leanrea paired Codex A/B — evidence intake contract (research only)

Status: PUBLIC-SAFE / SYNTHETIC CONTRACT / PUBLIC GOLD SCORER / NO AGENT EXECUTOR / NO LLM / NO BILLING / NOT BLIND.

## Question

Does a pinned, constrained Leanrea instruction improve an otherwise identical coding agent's evidence-based analysis of authorized synthetic artifacts? Distinguish **answer correctness** from **wall time**, **input/output token usage**, **actual provider cost**, and **safety violations**. A win in one dimension never implies a win in the others.

## Proposed equal-condition pairs (not yet conducted)

Four case IDs reserve these analysis types: LR-E01 (Electron hidden bundler / IPC), LR-N01 (ELF/native import inventory), LR-G01 (Go static build information), LR-D01 (multi-hop static call/string reasoning). The four targets are now created by `build_synthetic_targets.py` from invented local Electron JavaScript, C and Go programs, using only local compilers and standard libraries. `test_synthetic_targets.py` checks actual static metadata, hidden source folders, ELF symbols/disassembly and binary Go build info; the test does not execute compiled targets. The targets and tests are NOT a blinded agent evaluation or accepted independent reference set.

Run both arms on the **same exact task bytes and fixture bytes**:
- `base`: selected agent/model/provider and native preinstalled local CLI tools, without Leanrea instructions.
- `leanrea`: identical setup with only the independently pinned `wave13/SKILL.md` guidance introduced through an approved agent skill-loading path.

The candidate skill changes guidance, NOT tool grants, model, task text, permitted commands, environment, network, temperature, reasoning tier or max tokens. Freeze profiles, fixture SHA-256, exact code SHA, route SHA-256, environment SHA-256, per-run trace hashes and provider usage receipts. Cross-over case order should be fixed and published before any billable run. Include setup/skill loading tokens in measured totals. No retries or silent fallback.

Do **not** borrow the budget or permission from an unrelated Harness² A/B: this is a distinct research experiment. A full model-backed run requires separately approved spend, exact provider/model/wire entitlement, external USD-denominated enforcement, a disposable unprivileged executor with provable egress restrictions, independently blinded ground truth and held-out questions, and access through a reviewed existing PANAM execution/approval lane. Public GitHub Actions cannot call a model or hold credentials for this pilot.

## Identical agent-only workspaces (now implemented; still no model invocation)

`export_equal_workspaces.py` creates a pair of byte-identical analysis workspaces for the `base` and `leanrea` arms. It exports only the seven selected task/fixture files, leaves publicly visible scorer/test/source material outside both workspaces, clears binary executable bits, emits a separate SHA-256 manifest, and refuses unsafe/existing output locations. `test_equal_workspaces.py` checks exact equality and negative path/permission cases.

The Leanrea skill is intentionally not included in either workspace; it would be selectively mounted/injected through a separately approved agent profile **only after** provider, isolated executor, cost and blind-label approvals. Workspace equality is not proof of an isolated runtime, model route, egress filtering or blindness. See `WORKSPACES.md`.

## Minimal offline receipt shape

`ab_trace_contract.py` admits a packet containing:
- a versioned schema and honest `data_class` (synthetic or claimed observed);
- pinned lab HEAD SHA-1 and separate skill/task/route/environment SHA-256 identities;
- two distinct arm profile hashes;
- exactly the four identical task IDs, each with base/leanrea runs, common task SHA-256, identical route and environment hashes, unique run IDs, trace and receipt SHA-256 references, measured latency and token figures.

The program rejects extra/missing fields, duplicated cases/runs, changed route/environment, mismatched profiles, malformed digests, negative and Boolean token counts, unsupported accuracy claims and unsupported USD costs. It projects **unverified input** counts and differences for inspection. It has no network, provider client, runtime launcher, answer scorer, privileged action or persistent state. It cannot verify the hashes against an external ledger, inspect provider receipts or validate actual model responses. Its output always says `SHAPE_ONLY_NEVER_EXECUTION_AUTHORITY` and `real_model_benefit_proven=false` — including when `data_class=observed`.

Do not label synthetic fixture arithmetic as a measured agent improvement. A separate **public synthetic scorer** (`score_synthetic.py`) checks nine bounded answer values against code-defined public labels and the actual synthetic Go binary's build metadata. It does not inspect submitted citations or traces, verify independent ground truth or authenticate actual model responses. The candidate must never be given the scorer source or keys in its workspace, but publication makes them discoverable on the internet; therefore **this is not a blinded evaluation**. The scorer is only for testing answer-checking behavior. Real held-out scoring and blind accepted answers require a separate restricted, independently reviewed evaluator.

## Offline tests (no model/provider calls)

Run:
```sh
python3 -m unittest discover -s wave13 -p 'test_ab_trace_contract.py' -v
```

All test records and hashes are deliberately fabricated and safe for publication. The tests check positive schema parsing and adversarial rejection, not an actual Codex A/B. The existing Wave 13 workflow runs them on a temporary public GitHub-hosted runner with no secrets or model endpoints.

## Synthetic artifact and scorer checks already implemented

The public GitHub-hosted CI generates an isolated temporary fixture pack and runs:

```sh
python3 -m unittest discover -s wave13 -p 'test_synthetic_targets.py' -v
python3 -m unittest discover -s wave13 -p 'test_score_synthetic.py' -v
```

Generator output remains in a private temporary working directory, not in Git history. The model-facing `tasks.json` has no expected answers. The scorer's checks deliberately include a hand-written correct response, wrong-channel and wrong-Go-toolchain responses, schema errors, duplicates and forbidden injected assertions. Passing these controls does not imply model accuracy, independent citation verification or security approval.

## Source-anchor checks (public, not semantic proof)

`verify_public_evidence.py` and `test_public_evidence.py` add a separate **public synthetic citation verifier**. It checks nine submitted field references against precise Electron source lines and allowlisted read-only static CLI outputs for ELF, Go and strings; malformed paths/positions/cross-case citations fail closed. Its `anchor_present` flags do **not** prove behavior, derivation, tool traces, blindness, real model accuracy or cost. See `EVIDENCE.md`.

## Offline spending-envelope calculation — deliberately NOT a hard cap

`synthetic_usd_envelope.py` now checks an eight-slot/four-pair synthetic budget plan: equal route/environment and task fingerprints, equal per-pair worst-case token reservations, zero retries/hidden extra billable calls, fixed example USD rates, and per-request integer rounding upward. It uses only fabricated-example tariffs and a toy $0.10 comparison ceiling. It cannot transform AiDostup **vendor tokens** to actual USD and never returns executable authority, real price verification, isolation or approved billing. The distinct Harness² spending cap is not transferable to Leanrea. See `BUDGET_AND_EXECUTOR.md`.

## In-memory simulated admission — no real API broker

`synthetic_reservation_book.py` implements lock-protected one-time holds for the eight fabricated A/B slots, duplicate/replay refusal, stop on an excessive *synthetic* claim, and no automatic refunds. Its snapshot unconditionally denies `real_upstream_request_allowed`, `real_usd_hard_cap_enforced`, crash-recovery, provider-billing and isolation claims. `test_synthetic_reservation_book.py` checks concurrency and negative admission paths; it does not create an executable Codex provider adapter. See `BUDGET_AND_EXECUTOR.md`.

## Next explicit admission gate

Real performance claims must come from a separate approved runner and verified end-to-end receipts: each case's accepted answer and cited source offset, safe action trace, tool-count, provider usage/expense, runtime duration, and success/failure. Ingest only redacted/hashes in public CI. Perform independent correctness/security review before calculating model advantage. No merge, deploy or production permission arises from this document or a green workflow.
