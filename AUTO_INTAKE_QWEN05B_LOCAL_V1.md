# PANAM Auto Intake — Qwen2.5 0.5B Local Qualification V1

Status: `PUBLIC_RESEARCH / SYNTHETIC_ONLY / LOCAL_MODEL / NO_PRIVATE_DATA / NO_PRODUCTION_AUTHORITY`

## Purpose

Qualify one small local semantic-classification candidate against the public-safe PANAM Auto Intake synthetic suite.

This is evidence for a possible **Level-1 escalation lane** only. It does not replace deterministic Level-0 rules and does not authorize any file, matter, Memory, Task, External Operations or Control Plane mutation.

## Exact model

- model: `Qwen/Qwen2.5-0.5B-Instruct`
- exact revision: `ec7ddfa904d4d447eedd0b7f126df16957734abb`
- licence: Apache-2.0
- family size: approximately 0.5B parameters

The selected upstream model card describes multilingual support including Russian and improved structured-output/JSON instruction following. PANAM measures actual behavior rather than adopting those claims by assumption.

## Public-safe suite

`benchmarks/auto_intake/intake_bakeoff_suite.v2.json` contains 12 authored synthetic legal/administrative cases.

Each case contains:

- synthetic filename;
- bounded structured facts;
- a short authored `semantic_hint` representing the kind of semantic signal a Level-1 classifier could receive after extraction;
- gold classification used only for benchmark scoring.

No real PANAM document, client identifier, private repository data or raw production content is present. Identifiers and dates are intentionally synthetic, including `A00-00000-2099` and year 2099.

## Why this differs from Level 0

The corresponding private rule baseline intentionally ignores `semantic_hint` and scores `10/12` exact classifications. The two difficult cases are a generic scan that is semantically a court motion and a generic document that is semantically a contract amendment.

The local-model lane receives the semantic hint. This measures whether a small offline model can add value specifically where deterministic metadata/rules become ambiguous.

## Deterministic finite-choice method

The benchmark never allows free-form category generation. It presents exactly 13 fixed classification bundles, labelled `A` through `M`, and asks the model to return exactly one label.

Each label must tokenize to exactly one unique token under the pinned tokenizer. One forward pass per case obtains the next-token logits; only the 13 label-token logits are compared. The highest-scoring label selects the corresponding fixed classification bundle.

This **single-token multiple-choice** design avoids comparing the surface language probability of long JSON class names. A prior experimental run that scored full JSON continuations was retained in Actions history and rejected as a classification-quality measure because it showed a strong answer-surface prior (nearly every case preferred the same `Судебный акт` string). That failed method is evidence about benchmark design, not evidence that the model understood the cases.

Benefits of the accepted method:

- no sampling;
- no arbitrary new category;
- equal one-token answer surface for every class;
- deterministic finite output space;
- reproducible scores for a pinned model/runtime;
- substantially lower CPU cost than scoring full answer sequences.

Confidence is a softmax over only the 13 allowed label logits. It is benchmark confidence, never action authority.

## Isolation

Network is available only while installing research dependencies and downloading the exact model revision.

Actual inference runs:

- on a disposable GitHub-hosted public runner;
- under a separate Linux network namespace;
- after a fail-closed outbound socket check;
- with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`;
- using only the local exact-revision model directory and public synthetic suite.

No secrets or private repository access are permitted by the workflow.

## Dependency boundary

Top-level research versions are pinned:

- `torch==2.4.1` from the PyTorch CPU index;
- `transformers==4.45.2`;
- `huggingface_hub==0.25.2`;
- `safetensors==0.4.5`.

The model revision is exact and the workflow prints SHA-256 values for selected downloaded model/tokenizer files.

However, transitive Python wheels and model files are not pre-approved by a complete hash lockfile. Therefore:

`SUPPLY_CHAIN_LOCKED=false`.

A successful benchmark is functional/research evidence, not production dependency approval.

## Outputs

The workflow creates only two synthetic evidence files:

- `snapshot.json` — `panam.auto-intake-candidate-snapshot.v2`, lane `local_model`, containing one V1-compatible candidate per benchmark case;
- `report.json` — model/revision, method, label token IDs, suite/snapshot hashes, per-case scores, aggregate accuracy, latency and max RSS.

Only these two synthetic files are uploaded as a short-retention GitHub Actions artifact.

## Matter-link boundary

A synthetic case-number relationship is included in the candidate only if:

1. a case number exists in the bounded synthetic facts;
2. the selected category is `Судебные документы`;
3. benchmark confidence is at least `0.85`.

Even then it is only a `related_matter_candidate`; it does not mutate a registry or Task State.

## Authority boundary

Every result remains:

- `authority=public_research_evidence_only`;
- `source_of_truth=false`;
- `synthetic_only=true`;
- `real_data_used=false`;
- `private_repository_access=false`;
- `network_during_inference=false`;
- `automatic_winner_selected=false`;
- `production_switch_authorized=false`.

The public benchmark cannot move or rename files, write Memory, change Task/Job State, call External Operations, or grant Control Plane authority.

## Decision gate

After a runner-backed result, PANAM compares the exact synthetic snapshot with the existing deterministic rule baseline. A model win would justify, at most, designing a **bounded escalation policy for ambiguous/low-confidence cases**.

A model loss is equally useful: the candidate can be rejected without adding runtime complexity. Neither outcome authorizes processing real documents or activating a production classifier automatically.
