# PANAM Public CI Lab — Wave 2

Wave 2 adds three fully synthetic, generic benchmark families:

- deterministic event attribution scoring;
- retrieval metrics (`MRR`, `Recall@k`);
- lightweight proofreading diagnostics and normalization.

All code and test cases in this wave were written specifically for the public lab. They do not contain production PANAM source, internal topology, real documents, user data, logs, receipts, incidents, cloud identifiers, or access material.

## Boundary

These tests are evidence for generic algorithmic behavior only. They do not provide production trust, do not access the private PANAM repository, and do not authorize deployment or external actions.

## Purpose

The public lab is used for public-safe synthetic workloads that can run on standard GitHub-hosted runners. Private integration, production verification, privileged control, database, deployment and real-data tests remain outside this repository.
