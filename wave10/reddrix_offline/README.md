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
