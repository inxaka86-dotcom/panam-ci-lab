# witr W1 — public synthetic runtime-provenance probe

Status: **PUBLIC-SAFE SYNTHETIC / NO PRIVATE DATA / NO PRODUCTION AUTHORITY**

## Purpose

Validate a narrowly reduced machine-readable `witr` ancestry path using only public upstream software and an invented local process on a standard GitHub-hosted runner.

This public test exists specifically to avoid spending private CI capacity on evidence that can be generated without private PANAM source, data, topology or credentials.

## Exact upstream pin

- upstream: `pranshuparmar/witr`
- release: `v0.3.3`
- release commit: `86831e80c59c54e19c74cdbd126ed7ff6bcad756`
- asset: `witr-linux-amd64`
- expected SHA-256: `08fc46e3f80a374476f71d0d6e6579477cd98c6df5cc59d98224adf948f5ebf5`

The probe downloads only that exact public release asset and rejects it unless the SHA-256 matches.

## Why reduced tree JSON only

The audited upstream release collects process environment information internally and full JSON serializes the complete result model. A full `witr --json` response is therefore not treated as privacy-safe merely because `--env` was omitted.

W1 intentionally exercises only:

```text
witr --pid <synthetic-pid> --tree --json
```

The test asserts that emitted JSON contains only the reduced ancestry key set:

- `Ancestry`
- `Children`
- `PID`
- `Command`

A synthetic environment marker is deliberately placed on the invented child process and the test fails if that marker appears in stdout/stderr.

## Public-only boundary

This PR contains and uses only:

- public upstream repository/release identifiers;
- a public release digest;
- a newly created synthetic sleeping process;
- generic privacy-field allowlist assertions;
- a standard GitHub-hosted Ubuntu runner.

It contains **no** private repository source or history, real process names, VM names, production topology, credentials, private documents, user data, runtime logs, receipts, cloud identifiers or secret values.

The workflow has `contents: read`, uses the repository publication gate, uses a SHA-pinned checkout action with `persist-credentials: false`, and does not use a self-hosted runner or secret context.

## What a PASS proves

A green W1 run supports only these statements for the exact pinned public binary on the tested GitHub-hosted Linux runner:

1. the fetched binary matched the expected SHA-256;
2. the binary reported the expected `0.3.3` version;
3. a synthetic PID could be resolved through reduced tree JSON;
4. the target PID appeared in the ancestry payload;
5. the reduced output stayed within the explicit JSON key allowlist;
6. the synthetic environment marker was not emitted.

## What a PASS does not prove

It does not establish:

- safety of full `witr --json`;
- safety of `--env`, `--verbose` or interactive/TUI modes;
- safety on a private or production host;
- least-privilege requirements for real runtime inspection;
- private integration correctness;
- Security/Observability PASS;
- authority to install, deploy, signal, kill, restart or renice a process;
- authority to send runtime evidence to an LLM or persist raw upstream output.

Any private promotion must separately consume only reviewed public evidence and revalidate the private integration boundary. Public CI remains supporting evidence only.
