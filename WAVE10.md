# Wave 10 — OD-3B isolated browser/files canary

Status: LIVE_PUBLIC_CANARY / PUBLIC_SAFE / NO PANAM PRIVATE SOURCE

This wave runs one real public-safe browser/files episode for PANAM OD-3B.

## Boundary

- public GitHub-hosted runner only;
- no access to private PANAM repositories;
- no production topology or credentials;
- no model/provider credentials;
- no real user data;
- no Control Plane;
- no merge/deploy authority;
- one ephemeral OpenShell sandbox;
- browser/files canary only;
- concurrency = 1.

The public canary contains no private PANAM commit identifiers. Private acceptance binds the final public run/evidence to exact PANAM main separately.

## Pinned runtime inputs

- NVIDIA OpenShell: `v0.1.2`;
- Microsoft Playwright: `v1.63.0`;
- Playwright image:
  `mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27`.

The image digest was resolved in Wave 10 PR #33 run #1 before the live canary was enabled.

## Shell boundary

OpenShell's internal exec transport may depend on ordinary system shell infrastructure, so Wave 10 does not mutate or remove those transport internals.

The **task-facing computer capability surface** still has no shell capability:

- the canary is a fixed Node program;
- the task accepts no command string;
- no `run_command` / `shell.run` operation exists;
- the workflow statically rejects `child_process`, `exec(`, `spawn(` and shell/run-command primitives in the exact live canary source;
- the canary reports the SHA-256 of its own source.

This preserves the OD-3 requirement at the capability boundary without breaking the sandbox's own transport machinery.

## Network boundary

OpenShell permits the fixed Node executable and its descendants to reach only:

`https://example.com:443`

with REST read-only enforcement.

The live program requires:

1. Chromium navigation to `https://example.com/` succeeds;
2. Chromium navigation to unlisted `https://www.iana.org/` fails.

The effective OpenShell policy and sandbox logs are retained as public-safe run artifacts.

## Real filesystem effects

The program creates:

- one screenshot under `/tmp/od3b-workspace/out/`;
- one text summary under the same ephemeral workspace.

It reads the summary back and records a SHA-256, then stop removes the entire workspace.

The independent post-stop probe fails if the workspace remains.

## Real stop/kill evidence

The live program closes Chromium before stop completes.

Afterward a separate fixed Node probe inspects `/proc` and fails if any Chromium/Chrome-headless process survived.

The application state also rejects an action attempted after stop.

## Credential boundary

The sandbox has no providers attached. The live program fails if common GitHub/model/cloud credential variables are present.

No credentials are required for the target page.

## Evidence

The workflow retains for seven days:

- live canary JSON;
- post-stop probe JSON;
- full effective OpenShell policy;
- OpenShell sandbox log.

A green public run proves only this exact isolated public canary. It grants no PANAM merge, deploy, production or provider authority.
