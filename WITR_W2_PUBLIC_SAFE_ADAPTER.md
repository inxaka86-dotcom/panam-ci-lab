# witr W2 Public Safe Adapter

Status: `PUBLIC_SYNTHETIC / STACKED_ON_W1 / NO_PRIVATE_DATA / NO_PRODUCTION_AUTHORITY`

Purpose: validate a generic privacy-reduced execution boundary for `pranshuparmar/witr` before any PANAM-private integration.

## Stacked dependency

This branch is intentionally stacked on public W1 branch `research/witr-w1-public-synthetic-v1` / PR #14. It does not require merging W1 first and it does not authorize either PR to merge.

## Public-only boundary

This repository must receive no PANAM private source, documents, topology, process inventory, credentials, production receipts, private logs, private repository fetch or self-hosted runner access.

The exact upstream candidate remains:

- release: `v0.3.3`;
- release source commit: `86831e80c59c54e19c74cdbd126ed7ff6bcad756`;
- Linux amd64 asset SHA-256: `08fc46e3f80a374476f71d0d6e6579477cd98c6df5cc59d98224adf948f5ebf5`.

## Adapter contract

`witr_w2/safe_adapter.py` enforces:

1. explicit typed target: `pid`, `port`, absolute `file`, bounded `container`, or bounded exact `name`;
2. absolute `witr` binary path;
3. caller-supplied exact lowercase SHA-256 and verification before execution;
4. argv-only launch with `shell=False`;
5. fixed reduced mode only: `--tree --json`;
6. no `--env`, no interactive/TUI mode, no signal/kill/renice path;
7. minimal child environment: controlled `PATH`, locale only;
8. `cwd=/`, closed inherited file descriptors and a new process session;
9. hard timeout and stdout/stderr byte limits;
10. process-group kill on timeout or output overflow;
11. raw stderr is discarded and never surfaced in adapter errors/evidence;
12. JSON allowlist limited to upstream `Ancestry`, `Children`, `PID`, `Command`;
13. any unknown field fails closed, so `Env`, `Cmdline`, working directory, sockets and similar richer fields cannot pass through silently;
14. command arguments are omitted; secret-like command strings are fully redacted;
15. raw target value is not emitted in the safe evidence envelope: only target type plus deterministic target-reference SHA-256;
16. PANAM-owned output schema `panam.runtime_provenance.safe.v1`;
17. binary digest is checked again after the lookup.

The adapter deliberately does not persist raw upstream JSON. Parsing and reduction occur in memory and only the PANAM-owned reduced object is returned.

## Public adversarial suite

The W2 workflow tests at least:

- structured PID argv and absence of `--env` / `--interactive`;
- rejection of shell-like exact-name input;
- shell metacharacters in file paths remaining argv data, not shell syntax;
- rejection of relative binary and relative file target;
- invalid PID/port rejection;
- fail-closed handling of an injected `Env` field;
- command-argument omission;
- secret-like command redaction;
- proof that a parent environment marker is not inherited;
- proof that secret stderr text is not included in adapter exceptions;
- stdout overflow termination;
- timeout termination;
- digest mismatch blocking execution before the candidate binary runs;
- an exact-pinned real `witr v0.3.3` synthetic PID canary.

## Evidence meaning

A green W2 public run proves only the generic public-safe adapter contract on synthetic/public inputs and the exact pinned public upstream artifact.

It does **not** prove or authorize:

- compatibility with PANAM private runtime topology;
- access to real PANAM PIDs, files, ports, containers or names;
- installation on `panam-ci`, `panam-pr` or `panam-vm`;
- persistence of raw upstream output;
- Security/Observability Gate PASS;
- Autopilot/Multi-Agent activation;
- any process mutation or Control Plane authority.

## Next boundary

After runner-backed public W2 PASS, a separate private W2b PR may add only the minimum PANAM integration layer needed to bind private revision/evidence identity and approved target policy to this public-safe contract. Private W2b must not copy private data into this repository and must not deploy to production.
