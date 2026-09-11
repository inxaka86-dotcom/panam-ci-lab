# Wave 3: synthetic exact-match intake

Wave 3 publicly tests the generic intake contract that sits between an approved final and the Wave 2 revision-pair core.

## Contract under test

Synthetic draft registration -> approved synthetic final -> exact draft resolution -> approved-reference/integrity gates -> deterministic revision pair -> unclassified review queue.

## Exact matching only

Automatic matching may use only explicit identifiers:

- `draft_id_hint`;
- `correlation_id`;
- `source_id` within the same document type.

The synthetic intake deliberately does not auto-pair by filename similarity, semantic similarity, topic similarity, timestamps or a "best guess".

Ambiguity or conflicting exact keys produce `REVIEW_REQUIRED`; no exact match produces `UNPAIRED`.

## Gates

A matched draft still does not create a revision pair until:

- the synthetic final is an `APPROVED_REFERENCE`;
- the exact synthetic store identifier matches;
- draft and final text are supplied;
- the draft text matches its registered SHA-256;
- the final text matches the approved-reference content SHA-256 enforced by Wave 2.

A successful case ends `READY_FOR_CHANGE_REVIEW`. Every change remains `UNCLASSIFIED_REQUIRES_REVIEW`.

## Metrics

The synthetic helper counts intake states and prepared pairs and rejects duplicate accounting of the same `intake_id`.

## Public-only boundary

This lab contains invented generic text and metadata only. It has no private PANAM repository access, no real documents, no Google Drive/Telegram/email data, no production identifiers, no credentials, no private receipts and no deployment authority.

The public model intentionally uses generic approved-reference semantics. Private PANAM keeps its own exact-file GOLD and QA-receipt contract; the public field names do not redefine that private model.

## Validation target

The Wave 3 workflow compiles the Wave 2 document-learning core plus the Wave 3 intake module, runs the publication boundary, and runs the synthetic Wave 3 tests on a GitHub-hosted Ubuntu runner.

A green public run is test evidence only. It does not authorize private integration, merge or production deployment.
