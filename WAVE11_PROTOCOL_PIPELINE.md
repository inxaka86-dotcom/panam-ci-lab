# Wave 11 — Synthetic Approved Protocol Pipeline

Wave 11 validates the orchestration contract that joins the previously tested generation, IPC, runtime adapter, storage coordinator and lineage layers.

## Core invariant

A generated draft receives a durable **metadata-only generation checkpoint before storage is attempted**. The checkpoint stores IDs and cryptographic hashes, not transcript or draft text.

If a later retry regenerates a different draft for the same immutable pipeline identity, the pipeline fails closed as `GENERATION_CONFLICT_REQUIRES_REVIEW` and does not call storage.

This prevents a crash/retry from silently substituting a second model output for the draft that was originally prepared for the operation.

## Trigger boundary

Only these invocation modes are accepted in the synthetic contract:

- `owner_explicit`
- `approved_workflow`

A `background_watcher` or any unknown trigger fails before generation or storage. This mirrors the private PANAM rule that Wave 11 does not enable Autopilot or automatic Inbox analysis.

## End-to-end synthetic path

`Wave 11 Python pipeline -> Wave 9 RuntimeClient -> Node subprocess -> Wave 10 entrypoint -> Wave 8 generation/writer adapters -> Wave 6 commit -> Wave 5 hook -> Wave 4 lineage`

The Node fixture uses an in-memory/file-backed synthetic artifact store containing identity metadata only. No raw generated text is persisted in the external synthetic store.

## Recovery scenarios covered

- normal end-to-end commit and lineage registration;
- storage failure after generation checkpoint;
- retry with identical generated draft continues safely;
- retry with changed generated draft stops before storage;
- already committed replay makes no runtime call;
- changed immutable pipeline identity is rejected before runtime;
- background-watcher invocation is rejected before subprocess execution.

## Public safety boundary

The public lab contains no PANAM credentials, real Drive IDs, real documents, private folder names, model endpoints, user data, deployment authority or production sending.

Public CI evidence validates only the generic orchestration/recovery contract.
