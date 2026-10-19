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

Synthetic fixtures and host-native metadata only. No secrets, private repository source, user data, untrusted executable execution, automatic dependency installs, model/provider calls, network traffic, self-hosted runners, Control Plane actions or deployments. The script does not itself enforce network isolation and should be run only in a disposable credential-free environment.

No workflow is added to automatically run this experiment.

## Test

Run from the wave13 directory:

    python3 smoke_test.py

The script checks hidden Electron folders, command regex alternation, HAR jq expressions, temporary directory safety, static ELF inventory, static Go build metadata, and candidate security assertions. Optional tools (rg/jq/file/readelf/go) are explicitly skipped if absent; missing tools never prove the corresponding capability works.

## Next measurement gate

To test agent benefit, run baseline-vs-candidate under an identical, separately approved model/provider/compute budget; freeze task data, environment, source/config hashes, scoring rubric and case order. Use real tool traces and provider receipts, held-out tasks and independently inspected output. No private materials or live production access. No promotion, merge or deployment is implied by a passing smoke check.
