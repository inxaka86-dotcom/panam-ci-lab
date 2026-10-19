# Leanrea offline pilot — Wave 13

Status: RESEARCH_ONLY / PUBLIC_SYNTHETIC_ONLY / NO_MODEL_CALLS / NO_PRODUCTION_AUTHORITY.

## Hypothesis

A compact reverse-engineering skill might guide an agent to existing local CLI tools without a 207-tool REA MCP server. This phase tests only selected command correctness and safety patterns. It is NOT an agent A/B experiment and yields no measured model speed, accuracy, token or cost claims.

## Provenance

- Source: https://github.com/aicodeking/leanrea
- Observed upstream leanrea/SKILL.md Git blob: 2723c75d49361bf14dea70d37fc24479a0f55f3b
- License: https://github.com/aicodeking/leanrea/blob/main/LICENSE
- Relevant upstream issues: https://github.com/aicodeking/leanrea/issues/1 and https://github.com/aicodeking/leanrea/issues/3
- Ghidra/Electron fixes: https://github.com/aicodeking/leanrea/pull/5

The candidate here is a bounded research adaptation, not a verbatim installation or a canonical PANAM skill.

## Scope and boundaries

Synthetic fixtures and host-native metadata only. No secrets, private repository source, user data, untrusted executable execution, model/provider calls, self-hosted runners, Control Plane actions or deployments. The skill and measured test do not install dependencies, make HTTP requests or call a model. The disposable public CI runner may fetch signed Ubuntu distribution packages to provision missing static inspection tools *before* the test; the CI run is not a network-isolation proof and the runner itself has network access. The script does not enforce OS network isolation and should be run only in a disposable credential-free environment.

The path-scoped `.github/workflows/wave13-leanrea-offline.yml` workflow is public-only Route A, runs on standard GitHub-hosted runners, checks the publication gate, provisions missing public OS packages for the test host, runs positive and missing-tool negative checks, and records the exact checkout/CLI versions. No external model or production workflow is added.

## Test

Run from the wave13 directory:

    python3 smoke_test.py

The script checks hidden Electron folders, command regex alternation, HAR jq expressions, temporary directory safety, static ELF inventory, static Go build metadata, and candidate security assertions. All five required local tools (rg, jq, file, readelf, go) are checked in unittest setUpClass; a missing tool raises an error under both direct and unittest discovery execution. A missing Linux ELF fixture is likewise a failure, not a skipped capability. The synthetic Go build sets GOPROXY=off, GOSUMDB=off and GOTOOLCHAIN=local; no provider or external API is contacted.

## Exact-branch local audit (2026-10-19)

- Inspected draft PR #38, three changed files, exact fetched smoke_test.py and SKILL.md Git blob identities.
- Initial script bug reproduced: five missing-tool skips still gave PASS.
- Corrected fail-closed completion check, added required-tool preflight for all unittest entrypoints, and disabled Go module/toolchain network fetches on the existing draft branch.
- Verified updated smoke_test.py Git blob SHA-1 `dfe8f8da17258209f2d08e0852006978e0f67c01` matches the locally executed file.
- Positive local run: seven executed, zero skipped, zero failed; `PANAM_LEANREA_OFFLINE_SMOKE=PASS`.
- Adversarial local run (PATH=/nonexistent): preflight reports all five missing tools; zero tests executed; exit 1; `PANAM_LEANREA_OFFLINE_SMOKE=FAIL`.
- This is a single-machine local command smoke; it does NOT prove agent performance, compatibility of a real target, egress isolation, generic subprocess security or CI success. Do not count a skipped test as capability evidence.

## Public CI note

The first isolated workflow run failed *before executing smoke tests* because stock GitHub-hosted Ubuntu did not provide `rg`; publication gate passed. This setup failure is not a Leanrea benchmark result. Explicit signed Ubuntu package provisioning is isolated to CI setup; it is **not** a change to the candidate skill's ban on installing software. Read the exact-head run log before claiming a successful rerun.

## Leanrea model A/B research contract (no model calls)

A separate source-neutral, fail-closed paired-trace schema is staged in
`ab_trace_contract.py` with adversarial tests `test_ab_trace_contract.py`.
The four case identifiers represent future synthetic Electron, native ELF, Go
and deep static-analysis targets. The targets and blinded answer key are NOT
yet accepted. See `AB_PLAN.md` for equal-arm controls and execution gates.

The trace projector only validates supplied shapes and computes **unverified**
totals. Its output never treats synthetic/claimed observations as verified
agent performance, model accuracy, evidence authenticity, USD billing or
permission to execute. It makes zero provider/model calls; the existing
path-scoped public CI runs the unit tests.

## Four offline reverse-engineering fixtures and public scorer

`build_synthetic_targets.py` creates four invented public-safe artifacts into a **new** temporary target directory: Electron IPC files in hidden bundler directories, two compiled ELF shared libraries and a locally built Go executable. Only local C/Go compilers and Go standard-library packages are used; target binaries are never executed. `test_synthetic_targets.py` exercises static extraction and fails on unexpected overwrite or a dangling destination symlink.

`score_synthetic.py` tests exactly nine concrete answer fields over four cases, including a Go toolchain read from actual binary build metadata. `test_score_synthetic.py` exercises positive and deliberately incorrect synthetic submissions. Its publicly visible labels do **not** amount to independent blinded ground truth, validated tool traces, verified citations, or a real A/B result. No model ever receives a prompt or makes an API request in this CI phase.

The branch CI automatically checks all tests on a disposable GitHub-hosted runner. Public package bootstrap may use Ubuntu repository network access; no claim of kernel-enforced egress isolation is made.

## Equal, scorer-free A/B task exports

`export_equal_workspaces.py` and `test_equal_workspaces.py` now construct two byte-identical synthetic task folders (`base` and `leanrea`), each restricted to seven approved task/fixture files. No grader, gold labels, test scripts, skill file, git metadata, model credentials or private PANAM data is copied. All file execute bits are removed, a SHA-256 inventory is written outside both workspaces, and accidental output overwrite/symlink destinations are rejected.

This is an **offline data-preparation stage**, not an agent/model launcher, a true blind benchmark or a sandbox. Publicly available grader code could still be found by an internet-connected model. A private independently sealed answer key, approved model/provider route, USD budget guard and network/exec isolation remain separate blockers. See `WORKSPACES.md`.

## Grounded synthetic answer citations

`verify_public_evidence.py` reopens allowed synthetic artifacts and tests whether nine response values can be located at their cited source line, nm exported symbol, function-scoped objdump immediate, binary string or Go build metadata. `test_public_evidence.py` includes positive and adversarial citations. This detects fabricated source anchors, **not** semantic accuracy or trustworthy agent traces, and the labels remain public/nonblind. See `EVIDENCE.md`.

## Synthetic bill-envelope and future isolation boundary

`synthetic_usd_envelope.py` provides no-call, nonauthoritative arithmetic across eight paired response slots with explicit limits and adversarial failure controls. `test_synthetic_usd_envelope.py` verifies budget cap arithmetic, integer rounding, unsupported real tariff claims, retries, cross-arm mismatches and forbidden cost authorization. It never accesses the vendor, key, network or host. The toy $0.10 ceiling is **not** owner permission for this Leanrea pilot; no actual USD hard enforcement exists. `BUDGET_AND_EXECUTOR.md` describes the separately required OS-level network isolation and request broker.

## Reservation-book simulation (no request broker)

`synthetic_reservation_book.py` is a no-network, in-memory state machine for one-time holds against fabricated per-request maximum charges. `test_synthetic_reservation_book.py` stresses parallel reservations, replay attempts, stop-on-overclaim, unknown outcomes and permanent conservative holds. This is a concurrency-unit test only, **not** a real billable request limiter: it has no durable journal, kernel sandbox, API credentials or forward operation. Even when the toy bookkeeping succeeds, all execution and verified USD-cap flags are false. See `BUDGET_AND_EXECUTOR.md`.

## Next measurement gate

To test agent benefit, run baseline-vs-candidate under an identical, separately approved model/provider/compute budget; freeze task data, environment, source/config hashes, scoring rubric and case order. Use real tool traces and provider receipts, held-out tasks and independently inspected output. No private materials or live production access. No promotion, merge or deployment is implied by a passing smoke check.
