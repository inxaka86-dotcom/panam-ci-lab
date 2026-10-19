# Leanrea cost envelope and executor admission (RESEARCH ONLY)

Status: PUBLIC-SAFE / OFFLINE / NO MODEL OR PROVIDER CLIENT / NOT AN AUTHORITY.

## Current pricing distinction

AiDostup publicly documents charges as (input tokens + output tokens) times a model multiplier, in VENDOR TOKENS. The GET /balance endpoint returns that unit, not USD. An API catalog multiplier is not a USD exchange rate. Public reference: https://aidostup.site/docs.html

The US$0.10 / eight-request cap belongs to the separate proposed Harness² pilot and cannot be transferred to Leanrea as budget authorization. The same number is used below solely as a SYNTHETIC arithmetic example, not as a billable credit limit.

## What is implemented

The Python module synthetic_usd_envelope.py uses only Python standard-library math, JSON, and strict input validation. There are NO imports for subprocess, sockets, network requests, agent SDKs, authentication, host administration or persistent accounting. It accepts only public_synthetic envelopes and fabricated_example USD tariffs. The fixed eight slots represent exactly two arms for each of LR-E01, LR-N01, LR-G01, LR-D01, with shared route, environment, task SHA-256 identity and identical maximum token reservations per matched pair. It rejects retries, unaccounted extra billable calls, unsupported models, non-USD units and forged approval claims.

Integer prices use micro-USD per million tokens. Every individual simulated request is rounded UP to the next micro-USD; the total cannot be reduced by aggregate rounding. The fixed toy ceiling is 100000 micro-USD (US$0.10). Requests that exceed it are reported as over the demo ceiling, not silently accepted. Impossible or ill-formed limits are rejected.

Even when synthetic arithmetic is under the toy limit, ALL safety/authority fields remain false: execution_allowed, usd_hard_cap_enforced, tariff_verified_against_provider, actual_provider_usd_billing_verified, hidden_provider_subcalls_verified, network_egress_isolation_verified, blind_independent_gold_verified, specific_owner_spend_approval.

Reproduce with Python and no external dependencies:

    python3 -m unittest discover -s wave13 -p 'test_synthetic_usd_envelope.py' -v

This does not turn an estimated amount into a hard real-world spend cap. Provider tokens and dollars are different units. Hidden/streamed/retried subrequests, max context tokens and unbounded provider billing cannot be controlled by the module.

## In-memory reservation prototype — NOT a request broker

`synthetic_reservation_book.py` is a thread-safe **simulation of request-slot admission** over the **fabricated** eight-slot arithmetic envelope. It validates exact four paired slots, uses a process-local mutex to serialize concurrent reservations, blocks duplicate slots and nonce replays, denies reservation beyond the toy ceiling, permanently retains each reserved maximum on a claimed/unknown outcome, and stops new reservations on an over-limit fabricated charge. `test_synthetic_reservation_book.py` includes parallel multi-thread races, deliberate replays, malformed IDs, missing rates/approvals, uncertain outcomes, and over-claim stop behavior. No charges are actually made.

A reservation record saying `synthetic_reservation_recorded=true` is NOT forwarding authorization: it explicitly says `real_upstream_request_allowed=false`. The module has **no socket, HTTP client, provider API, run launcher, model key, persistent journal, billing proof or crash recovery**; a new Python process starts a fresh fictional book. Even a green concurrent test does NOT prove cross-process or distributed atomicity, OS-level network confinement, bounded Codex subcalls, a vendor-recognized USD hard cap or model response compatibility. A real reservation service would require durable atomic state and strict fail-closed crash recovery; none is staged here.

## Local SQLite transaction simulation — still not a broker

`synthetic_sqlite_ledger.py` adds a **separate, public-synthetic SQLite local-file prototype** on top of the fabricated eight-slot cost envelope. It does not replace or extend any protected PANAM Control Plane ledger.

On a disposable, existing directory owned by the test user and mode `0700`, a new SQLite file (mode `0600`) is created with `O_EXCL`/no-follow. It records a canonical synthetic envelope SHA-256, fixed schema version and stopped bit. Each reservation uses SQLite `BEGIN IMMEDIATE`, `synchronous=FULL`, a fixed case/arm primary key and a unique nonce; it refuses a changed envelope, unsafe file ownership/mode/hard links, symlinked DB path, duplicate slot/nonce and missing or corrupt DB metadata. Each slot consumes its entire fabricated worst-case reserve permanently. A fabricated over-claim commits the stop state **before** returning failure. There is NO callback to transmit a request, use a model or hold credentials.

`test_synthetic_sqlite_ledger.py` uses **27 local tests**, including 16 competing Python processes, interrupted transactions and a fresh reopen after process exit. A transaction interrupted before commit must not appear as a completed reservation, while one committed before a test-process exit remains visible. Even if these tests pass, they do not prove survival of host power failures, filesystem failure, malicious modification, independent server trust, multi-host atomicity or real billing.

**Threat limitations:** SQLite is the durability primitive for this *toy local filesystem*, not a money-service authorization source. The repository does not provide a kernel sandbox, trusted USD conversion, dollar-denominated prepaid API quota, authenticated provider receipts or a separate credential-holding request broker. The file path guard is a best-effort local demo, not a defense against a hostile user with write access to the parent directory or filesystem races. No API wiring is authorized.

## Explicit future executor boundary (NOT implemented, NOT deployed)

1. Bind exact case bytes, fixture, route, allowed tools, model and environment hashes. Only the candidate arm receives a pinned Leanrea skill via a reviewed profile injection external to the identical task workspaces; the baseline has no such skill.
2. Build on an existing approved PANAM execution lane, with an ephemeral unprivileged worker, read-only fixture mounts, separate writable scratch, bounded CPU/memory/pids/time, no host SSH keys, no production mounts, no Docker socket, no root and disposal after a single experiment.
3. Enforce no direct network egress by an OS network namespace or equivalent independent kernel-level boundary. Test negative egress on the ACTUAL target worker; passing tests in public GitHub Actions or setting an environment variable are not evidence of target-host isolation.
4. The API credential must belong to a separate reviewed, least-privilege request broker outside the agent namespace. The only admissible route is the exact pinned provider/model/wire API. No fallback provider, unbounded retries, streaming side channels, speculative child calls or alternate network path.
5. Before forwarding EACH upstream request, a broker must atomically reserve its provable worst-case USD amount against an authorized Leanrea-specific limit; it must count hidden Codex tool/model turns, request retries and streaming charges, and fail closed on unknown pricing, concurrency or missing vendor guarantees. After-the-fact GET /balance and /keys/logs can support reconciliation, not a prospective enforced USD ceiling.
6. Independent sealed held-out answers and a separated grader are still required for credible real A/B correctness; public scorers in Wave13 cannot be treated as truly blind.
7. Any actual model call, spend cap selection, CONTROL action, deployment, merge or protected side effect needs its own fresh approval and existing PANAM governance. Harness² PR #2944 is a separate research hypothesis, not inherited authority.

## Status of external admission dependencies

- AiDostup catalog and provider metadata: earlier guarded GET checks existed. The on-disk Codex route subsequently returned static PASS in Control Plane issue #2965, but no actual Responses generation was demonstrated.
- Verified USD price/exchange and enforceable hard cap: NOT PROVEN.
- Real host kernel network isolation plus request broker: NOT BUILT OR VERIFIED.
- True privately held, independent answer key: NOT ESTABLISHED.
- Leanrea billable-model approval: NOT GIVEN.

This is a reproducible offline calculation and design handoff only. A green CI result is NEVER execution authority, real-dollar expense evidence, isolation proof, or a performance claim.
