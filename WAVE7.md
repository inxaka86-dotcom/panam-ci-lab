# Wave 7 — SONAR guarded live-public canary

Status: PUBLIC-SAFE / OWNER-AUTHORIZED-RESEARCH / LIVE-PUBLIC-ONLY / NO-PRODUCTION-AUTHORITY

## Purpose

Produce one real RunetMonitor SONAR CSV on an isolated GitHub-hosted runner and use it as interoperability evidence for PANAM's offline SONAR evidence adapter.

This canary does **not** represent PANAM production networking, the owner's ISP, or NetWatch runtime state. It proves only that the real upstream SONAR measurement format can be collected in a bounded public environment.

## Exact upstream

- repository: https://github.com/RunetMonitor/SONAR
- commit: `aa1df9171a823fa5c40e1eaf88c4d66da033983e`

## Public targets

The frozen canary list contains only generic public test targets:

- `example.com`;
- `expired.badssl.com`;
- `neverssl.com`;
- `nonexistent-sonar-canary.invalid`.

No PANAM production hostname, endpoint, IP, account, token, private repository, user data or operational log is used.

## Network boundary

- GitHub-hosted `ubuntu-latest` only;
- no self-hosted runner;
- no secrets;
- no production/private-repository access;
- SONAR upload token is forced empty;
- SONAR upload function is fail-closed if unexpectedly invoked;
- location/provider lookup is disabled before `main()`;
- version-network lookup is disabled;
- the DNS-probe resolver set is reduced to Cloudflare `1.1.1.1` and Google `8.8.8.8`;
- one DNS-probe attempt per resolver;
- four targets maximum;
- two workers;
- bounded DNS/HTTP timeouts.

## Output

The job sanitizes the SONAR CSV before artifact upload:

- `check_location` blank;
- `check_provider` blank;
- `sonar_id` blank.

The public canary targets and their public DNS answers may remain in the artifact because they are deliberately public test material. No private PANAM material is present.

Artifact: `wave7-sonar-live-public`.

## Authority boundary

A successful canary is interoperability/research evidence only. It does not:

- diagnose PANAM production networking;
- reclassify a NetWatch UNKNOWN;
- approve egress policy;
- satisfy Security/Observability Gate V2;
- authorize a production probe;
- activate Autopilot.
