# Wave 5: public synthetic post-save generation hook

This wave validates a generic, public-safe lifecycle contract:

`synthetic document generation -> successful synthetic-store save receipt -> post-save hook -> Wave 4 lineage -> Wave 3 approved-reference intake`

## Contract

The hook:

- accepts only a bounded `meeting_record` document type;
- accepts only the invented `synthetic_store` provider;
- creates lineage only for `save_status = STORED`;
- verifies the exact supplied text against `text_sha256`;
- requires `source_id` and/or `correlation_id`;
- invokes Wave 4 using `approved_workflow`;
- records metadata only, never raw text;
- is idempotent for exact event replay;
- rejects event-ID rebinding and ledger tampering;
- does not watch folders, poll, call external services, send messages, or deploy.

A full-chain test continues from the Wave 5-registered draft through the real
public Wave 4 storage adapter and real public Wave 3 intake, and requires the
result to reach `READY_FOR_CHANGE_REVIEW` with edits still
`UNCLASSIFIED_REQUIRES_REVIEW`.

## Public-only boundary

All identifiers and text in this wave are invented. Do not add private PANAM
source, Drive IDs, real documents, people, organizations, credentials, logs,
receipts, production topology, private repository access, or production
permissions.

A green public run is engineering evidence only. It grants no production
authority.
