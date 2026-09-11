# Wave 6: public synthetic protocol artifact commit coordinator

Wave 6 validates a public-safe state machine for:

`generated text -> one storage-writer attempt -> stored-receipt checkpoint -> Wave 5 -> Wave 4 -> Wave 3`

## Contract

- exact generated-text digest is checked before the writer is called;
- `operation_id` binds the whole lifecycle and cannot be rebound;
- the writer receipt must echo exact request identity;
- successful storage is checkpointed before lineage completion;
- if lineage fails after storage, retry resumes from the stored receipt without calling the writer again;
- receipt conflicts fail closed and require review;
- raw text is never persisted in the commit registry;
- operation metadata is protected by a deterministic digest;
- full-chain validation must reach Wave 3 `READY_FOR_CHANGE_REVIEW` while edits remain `UNCLASSIFIED_REQUIRES_REVIEW`.

Everything in this wave uses invented text, identifiers and the invented `synthetic_store` provider. There is no private repository access, external service call, credential, real Drive ID, real document, production deployment or sending authority.

A passing public workflow is engineering evidence only.
