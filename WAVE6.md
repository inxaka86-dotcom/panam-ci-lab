# Wave 6 — Open News guarded live-public canary

Status: PUBLIC-SAFE / OWNER-AUTHORIZED-RESEARCH / LIVE-PUBLIC-ONLY / NO-PRODUCTION-AUTHORITY

## Purpose

Run the first bounded live-public acquisition canary for pinned `alphap365/open-news` after Wave 5 passed 15/15 synthetic offline cases.

The network security boundary is PANAM CI Lab code, not upstream Open News fetch/crawler code:

```text
frozen source plan
  -> URL/DNS admission
  -> address-pinned curl HTTPS transport
  -> bounded public bytes
  -> pinned Open News extraction / RSS parsing / dedupe
  -> metrics-only result
```

## Exact upstream

- repository: https://github.com/alphap365/open-news
- commit: `ebb0e9b4deb0bf8fa8983e6324276a51f091ab43`
- release context: `v1.0.3`

## Frozen live sources

The canary uses five public URLs on four exact hostnames:

1. a Rospatent public news article;
2. an Official Publication of Legal Acts document page;
3. the public Digital Government situational-centre home page;
4. ConsultantPlus "News for lawyers" RSS;
5. ConsultantPlus procurement-specialist RSS.

No search-engine discovery, arbitrary URL input, crawler, JavaScript renderer, cookies, authentication, credentials, or private data is used.

## Transport safety

For every hop:

- HTTPS only;
- port 443 only;
- exact hostname allowlist;
- IP-literal URLs forbidden;
- userinfo forbidden;
- all DNS answers must be globally routable;
- mixed public/private DNS answers fail closed;
- ambient proxy environment is removed;
- curl config is disabled;
- the actual connection is pinned with `curl --resolve` to a validated IP;
- normal TLS certificate/SNI validation remains bound to the original hostname;
- automatic redirects are disabled;
- each redirect is independently revalidated before the next connection;
- actual remote IP must equal the validated/pinned address.

Raw destination IPs are not emitted into the benchmark result; only IP family counts and truncated SHA-256 digests are retained.

## Limits

- max sources: 5;
- max fetched objects: 20;
- max redirects: 3 per object;
- connect timeout: 5 seconds;
- total object timeout: 10 seconds;
- max body: 2 MiB per hop;
- max aggregate downloaded bytes: 10 MiB.

## Output boundary

Durable output contains metrics and content hashes only. Full fetched HTML/RSS bodies remain in runner-temporary storage and are discarded with the job.

A successful workflow is research evidence only. It does not approve PANAM production egress, install Open News in production, satisfy the Security/Observability Gate, activate Autopilot, or create a scheduler/source-authority plane.
