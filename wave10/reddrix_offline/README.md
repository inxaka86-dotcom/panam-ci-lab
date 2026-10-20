# PANAM Wave 10 — Reddrix-shaped offline signal contract

**Status:** public synthetic CI lab only. No Reddit collection, Reddrix install/import, network I/O, production access, customer data, credentials, or deployment.

`offline_signal.py` demonstrates a proposed `panam.signal.v1` event: a validated HTTPS hostname and conservative path, bounded JSONL fixtures, deterministic topic labels, deduplication, pseudonymous keys, timestamps, a proposed retention deadline and basic email/telephone redaction. It explicitly rejects any non-synthetic source policy.

Run from this directory:

```sh
python3 -m unittest discover -s tests -v
```

Expected fixture: 4 consumed, 3 accepted, 1 duplicate; topics consumer, contracts, procurement (one each).

**Limitations:** All records are invented and use the reserved example hostname `forum.example.org`. Basic regex redaction does **not** guarantee anonymization or 152-FZ/GDPR compliance. `delete_after` is metadata; no deletion scheduler exists. Topic labeling is keyword-based and not a validated machine-learning model. This proposed event format is *not* an approved PANAM SYSTEM production API contract.

The original research target is https://github.com/Coding-Doctor-Omar/reddrix. This PR does not run it, contact Reddit or imply authorization for commercial scraping.

**Merge/deploy gate:** a passing CI run only supports this synthetic lab code; it does not authorize production deployment, real data access, IAM updates or collection from third-party platforms.

## PANAM sources compatibility — repository-only study

`source_projection.py` compares the **synthetic** `panam.signal.v1` event to
the column shape declared in
[panam-infrastructure/database/migrations/0001_core.sql](https://github.com/inxaka86-dotcom/panam-infrastructure/blob/main/database/migrations/0001_core.sql)
for `panam.sources`. The result is an inert `panam.sources.synthetic_projection.v1`
object with `write_authorized=false`, `runtime_compatibility_verified=false`
and `requires_separate_permission=true`.

| Proposed projection field | Repository panam.sources field | Guard |
| --- | --- | --- |
| `record_key` | `external_id` | Synthetic-only prefixed hash, no human ID |
| `source_url` | `source_url` | Exact reserved host and path |
| `published_at` | `occurred_at` | UTC-aware timestamp |
| `delete_after` | `retention_until` | **Advisory**; no deletion or TTL task |
| `topics`, `type` | `metadata` | Small synthetic labels, no post body |
| source identity | `source_type=web`, `authority=unknown` | No invented credibility |
| possible residual personal data | `contains_personal_data=true` | Conservative, not anonymization |

In this projection `title=null` and the original `body` is excluded. It deliberately
does not set a `project_id`, create SQL, choose a DB identity/role, perform writes, expose
a service, or assume the migration is currently deployed. The projection does not
claim production API compatibility or real-data authorization.

The real PANAM Tender Hub already describes a separate
`connectors -> normalization -> SQLite storage/deduplication -> scoring` pipeline
([tender_hub/README.md](https://github.com/inxaka86-dotcom/panam-infrastructure/blob/main/tender_hub/README.md)).
This research module must not bypass Tender Hub's source verification,
Risk/Privacy/Approval classification, or authorized action path.

The new `test_source_projection.py` suite runs through the same offline
`unittest discover` command. A passing CI job proves only the synthetic shape
and negative checks, not legality, privacy compliance, runtime readiness or
production persistence.

## Synthetic ingress and retention simulation (no live connector)

`synthetic_ingress.py` offers a **pure in-process boundary**, not an HTTP/API
server. `SyntheticInbox.accept(...)` and `expire(...)` operate only on
invented fixture events and ephemeral Python memory. The hard-coded exact
fixture context requires `synthetic-ci-harness`, `synthetic_offline_only`,
`projection_contract_test`, `in_process`, `network_allowed=false` and the
reserved synthetic source. It is a test *assertion*, **not authentication,
not an IAM permission, and not a real source licence**.

- Rejects foreign/missing context properties, real-source modes, invalid events,
  noncanonical URLs, future/expired records, oversized batches and capacity
  overflow. No partial in-memory acceptance when any event is invalid.
- Reuses `source_projection.py` and retains only bounded metadata fields.
  Full post/comment text and author identifiers never enter the inbox.
- Replayed event keys are deduplicated within a running inbox.
- `expire(..., now=...)` explicitly removes rows from this Python dictionary
  at or after `retention_until`; it is not scheduled and does **not** erase
  databases, durable storage, exports, audit logs or backups.
- Results explicitly state `production_write_authorized=false`,
  `runtime_authorization_verified=false` and
  `persistent_retention_enforced=false`.

Use the same offline test command; it now includes `test_synthetic_ingress.py`.

### Admission criteria before any real integration

1. Independently verify a written entitlement for the actual source, exact
   purpose, commercial use where applicable, collection mechanism and
   permitted fields. No assumption that a public page is a licensed feed.
2. Map into an **existing** PANAM source-ingestion/approval path in a private
   reviewed change. The public test context must not be reused as a token.
3. Define production identity and least-privilege authN/authZ, rate limits,
   input validation, replay semantics, isolated runtime and audit receipts.
4. Perform a privacy/security assessment of purpose limitation, personally
   identifying content, minimization and cross-border retention requirements.
5. Implement measured scheduled persistent expiry and deletion evidence for
   every storage/backup/export layer where legally and technically applicable.
6. Run private isolated integration checks, a source-specific authorized
   canary, current-state risk gates and separate owner approval before any
   production write/deploy. Green public CI is **not** authority.

No production schema migration, listener, API credential, network connection,
scheduler, secrets, deployment or external source collection is included.
