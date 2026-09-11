# Wave 4: synthetic storage / lineage boundary

Wave 4 validates a public-only storage/lineage adapter layered on Wave 3 exact-match intake.

## Contract

Synthetic draft text is registered with stable metadata and a content digest. The registry stores no raw text. Later, explicitly supplied storage snapshots are checked against the exact registered storage identity and handed to Wave 3.

## Automatic authority

Allowed invocation labels:

- `owner_explicit`
- `approved_workflow`
- `manual_operator`

Unknown/background labels fail closed.

The synthetic adapter does not enumerate storage, poll folders, watch inboxes, call external services or authorize production actions.

## Identity policy

- draft ID, artifact ID, storage object ID, source/correlation keys, text digest and storage revision form immutable lineage identity;
- exact re-registration is idempotent;
- display names are informational only;
- the same source may legitimately produce multiple drafts;
- one storage object cannot silently represent two distinct draft IDs.

## Handoff

For a Wave 3 exact draft match, the adapter verifies:

1. exact draft storage object ID;
2. exact draft text digest;
3. exact final/reference storage object ID.

Only then does it hand ephemeral texts to Wave 3. Wave 3 remains responsible for reference qualification, final-text integrity, revision-pair generation and the unclassified review queue.

## Public-only boundary

Everything is invented and publication-safe. There are no private repository references, real documents, real storage IDs, credentials, private topology or production permissions.

A green workflow is test evidence only and grants no production authority.
