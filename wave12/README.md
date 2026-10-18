# Wave 12 — Evidence-grounded offline evaluator for Harness²

Status: **PUBLIC_SYNTHETIC / OFFLINE_EVALUATOR_ONLY / NO_MODEL_RUN / DRAFT_PR**.

## Objective

Provide a fail-closed, reproducible **offline** evaluation contract for comparing
baseline agent output and candidate output on the **same** synthetic legal
and procurement tasks. It is a preparatory gate toward, *not* proof of,
a real model-backed Harness² A/B.

Unlike Wave 11's scripted patch, the evaluator is **not tied to a specific
editor or model**. It scores already-produced predictions, records both
improvements and regressions and checks source-grounded citations.

## Dataset and labels

16 wholly fictional scenarios (`synthetic_cases.json`): 8 legal / 8 tender.
Every case has an ID, question, quoted fictional source clauses and a human-
authored answer key. Classes: `REQUIRED`, `NOT_REQUIRED`, `UNKNOWN`,
`CONFLICT`. An UNKNOWN answer needs empty citations; a CONFLICT needs both
contradictory evidence IDs. This dataset contains **no real Russian laws,
procurement notices, PANAM customer files, or legal opinions**.

Included phenomena: explicit negative requirements, scope exclusions,
threshold boundaries, edition-specific answers, contradictory equal-ranked
texts and missing evidence.

## Use

Export a task-only input pack:

```bash
python3 wave12/evaluator.py export \
  --cases wave12/synthetic_cases.json \
  --out /tmp/panam-wave12-tasks.json
```

The exported JSON contains `tasks` but not the `gold` answer fields.
Have **two independently executed and otherwise comparable** agents produce
separate prediction files. Each prediction must match exactly this schema:

```json
{
  "schema_version": 1,
  "predictions": [
    {
      "case_id": "L01",
      "decision": "REQUIRED",
      "citations": ["L01-A"]
    }
  ]
}
```

A real submission must include **every** case exactly once.

Score baseline and candidate:

```bash
python3 wave12/evaluator.py compare \
  --cases wave12/synthetic_cases.json \
  --baseline /tmp/baseline.json \
  --candidate /tmp/candidate.json \
  --out /tmp/comparison.json
```

Metrics: exact decision accuracy, exact supporting citations, combined
fully-correct cases, unsupported citations (including references to the
**wrong case**), unknown/abstention correctness, per-domain counts, per-case
improvements and **regressions**, dataset SHA-256 and comparison SHA-256.

A negative result is preserved as a valid measurement. There is no
automatic promotion/merge and no PASS just because candidate beats baseline.

## Unit test / CI

```bash
python3 -m unittest discover -s wave12 -p 'test_*.py' -v
```

The tests exercise expected-good and deliberately defective synthetic
prediction sets, duplicate/missing answers, invalid fields, citations to
invented or other-case sources, report serialization and input-overwrite
rejection. Test predictions are **hand/program generated control fixtures,
not produced by an LLM**.

CI workflow: `.github/workflows/wave12-harness2-offline-evaluator.yml`,
runs in approved public CI with no network-model calls, secret context, or
self-hosted runner.

## Honesty and security boundaries

- **Public answer keys are not truly secret from an internet-enabled model.**
  The `export` command hides gold from its generated task pack, but a model
  allowed to browse GitHub could locate the public `synthetic_cases.json`.
  Therefore this suite only verifies scorer mechanics and can serve as an
  educational/development set. Do not claim it is blind held-out model evidence.
- For a genuine blind model-backed evaluation, create a **separate restricted
  test set**, stored in an authorized private environment and withheld from the
  solver; apply egress restrictions. Do **not** move that set into public CI.
- This evaluator **never launches** Harness², agents, providers, Codex,
  OpenCode, external tools, deployment or production code. It only reads
  explicit local files and writes a local report.
- No PANAM production access, private source, real documents, credentials,
  client data, tokens, external API spend or Control Plane operations.
- Workflow evidence cannot authorize a PANAM production integration or
  promotion. Keep new work on the dedicated branch and the PR draft.

## Real-model admission gates (NOT satisfied here)

1. Independently approved private or properly isolated test data, with source
   provenance and human-checked answer keys.
2. Network egress denial to answer keys and sensitive services; isolate
   untrusted executor, apply process/filesystem constraints.
3. A concrete reviewed model/provider and fixed executor/harness configuration
   with task order, seed, tokens/time/cost caps and stop conditions.
4. Fixed output contract for base/refined, same tasks, independent judging,
   privacy and leakage preflight, and exact immutable source/config lineage.
5. Owner approval under applicable PANAM Risk/Privacy/Approval boundaries
   *before* protected effects, any costs or deployment.
6. Current run evidence independently inspected after completion; store
   only sanitized summaries in approved evidence locations.

A green Wave 12 CI result is **SCORER_TESTS_PASS**, not
`MODEL_BACKED_AB_PASS` or `LEGAL_QUALITY_VERIFIED`.
