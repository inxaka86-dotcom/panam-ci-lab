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
