# LoadBear — isolated public research pilot

Status: RESEARCH_ONLY / REVIEW_REQUIRED / NO VPS OR PRODUCTION DEPLOYMENT.

## Exact identity

- Public upstream: https://github.com/weaztoven/loadbear
- Pinned commit: 39a40f1ee550d944b3131ff228e458c9396e62fe (2026-11-13).
- PANAM CI lab starting point: main@045931f887b4e066df15103cc2879e7f0e7fe729.
- Only public open-source sources and three synthetic loopback HTTP backends.
- Only disposable GitHub-hosted runners, no credentials, private code or PANAM servers.

## What the workflow does

Fetches the pinned public upstream; checks the exact commit; runs upstream Go tests; applies a narrowly scoped patch to the temporary checkout; runs go vet, race tests and builds the research executable; checks loopback round-robin distribution, health failover, SIGHUP behavior, metrics and trusted/untrusted forwarded-proto handling.

## Ephemeral patch rationale

1. SIGHUP must not accidentally terminate LoadBear. It logs that hot reload is unavailable. Config changes still require a controlled restart.
2. An upstream HTTPS indicator may only be accepted from an explicitly trusted immediate peer, and only for the values http/https. Untrusted clients cannot spoof the scheme.
3. Source-shape assertions cause patching to fail closed if the pinned source layout changes. The patch is not applied to PANAM or submitted to upstream.

## Acceptance evidence

Required output: PUBLICATION_GATE=PASS, UPSTREAM_PIN=MATCH, LOADBEAR_EPHEMERAL_PATCH=APPLIED, LOADBEAR_SMOKE=PASS, plus successful original upstream tests, patched vet and race tests. CI status without those logs is insufficient.

## Non-goals and limitations

No production deployment, VPS changes, merge, security approval, network firewall changes, administrative authority, real PANAM workloads, or connection to EIS. The existing dedicated EIS HTTP CONNECT/Squid route is not replaceable by this experiment. No performance, WebSocket, TLS termination or high-load resilience claims are made. An isolated VPS test would require an independently verified execution path, current host checks, rollback and approval.

## Manual reproduction

On disposable Linux with Go 1.23 and Python 3: fetch the exact pinned upstream commit, run go test ./..., run python3 loadbear-pilot/harden.py PATH_TO_CHECKOUT, then inside that checkout run go vet ./..., go test -race ./..., go build -o /tmp/loadbear-research ./cmd/loadbear, and finally python3 loadbear-pilot/smoke.py /tmp/loadbear-research.
