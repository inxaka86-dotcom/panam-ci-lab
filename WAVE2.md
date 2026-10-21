# Wave 2: synthetic document-learning feedback loop

Wave 2 tests a generic, publication-safe feedback loop for learning reusable drafting conventions from approved document revisions.

## Contract under test

Synthetic source/draft -> synthetic approved reference -> deterministic textual revision pair -> manual change classification -> reviewed-pair qualification -> reusable-rule candidate -> conservative rule acceptance.

The experiment intentionally separates:

1. evidence that text changed;
2. human-reviewed classification of why it changed;
3. qualification that the reviewed pair still matches the same approved reference and review receipt;
4. whether a repeated editorial pattern is safe to reuse.

A textual diff never classifies itself, and an evidence pair is not reusable merely because its ID was supplied by a caller.

## Safety policy

A reusable rule may be accepted only when:

- it is manually verified;
- it belongs to an allowed style/structure category;
- it is supported by at least three distinct qualified synthetic revision pairs;
- every evidence pair is fully reviewed and still bound to the exact approved reference metadata;
- duplicate evidence-pair IDs are rejected;
- contradiction count is integer zero;
- rule identity and before/after patterns are non-empty;
- before and after patterns differ.

Factual, legal or other substantive corrections are explicitly blocked from promotion into reusable style rules.

The minimum evidence count of three is a conservative Wave 2 engineering policy, not a statistical claim.

## Public-only boundary

This repository remains a synthetic laboratory:

- no private source code or repository history;
- no real documents or extracted text from real documents;
- no user, legal, email, Drive, Telegram or operational data;
- no production identifiers, topology, credentials, receipts or logs;
- no private repository access;
- no deployment or promotion authority.

All examples in tests are invented and generic.

## Files

- `wave2/document_learning.py` — synthetic feedback-loop contract;
- `wave2/test_document_learning.py` — deterministic safety tests;
- `.github/workflows/wave2-document-learning.yml` — GitHub-hosted public CI.

## Interpretation

A green Wave 2 workflow means only that this public synthetic contract passed its tests. It does not authorize production use. Private integration must be separately reviewed and, if adopted, pinned to an explicit public commit revision.
