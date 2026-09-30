# Wave 9 — OpenShell policy-enforcement canary

This wave is a public-safe, synthetic interoperability test for NVIDIA OpenShell.

## Boundary

- Public GitHub-hosted runner only.
- No private repository access.
- No PANAM production access.
- No secrets or credential providers.
- No real user or operational data.
- No deployment authority.

## Upstream pin

OpenShell is pinned to `v0.1.2`.

The workflow installs from the exact `v0.1.2` tag and verifies the reported CLI version before the canary.

OpenShell 0.1.x uses a deliberately minimal default workload image. Wave 9 therefore builds a tiny local test image from the exact NVIDIA Ubuntu image digest observed in the first run and adds only `ca-certificates`, `curl`, and `python3`. The image runs as non-root UID/GID 1500, uses `/tmp` as its working directory, and is never pushed to a registry.

## Strict policy profile

The final canary mirrors the private PANAM PoC policy's enforcement-relevant fields:

- `filesystem_policy.include_workdir: false`;
- read-only system paths and read-write only `/tmp` plus `/dev/null`;
- `landlock.compatibility: hard_requirement`;
- explicit `process.run_as_user: "1500"` and `run_as_group: "1500"`;
- only `/usr/bin/curl` may reach `api.github.com:443`;
- REST enforcement is `enforce` with `read-only` access.

## Canary assertions

The canary requires:

1. GitHub API GET succeeds.
2. POST, PUT, PATCH and DELETE are denied.
3. `curl` to an unrelated host is denied.
4. another network-capable binary cannot reuse the curl allowance.
5. a write under `/etc` is denied by the filesystem boundary.
6. common provider/token environment variables are absent.
7. the effective policy is captured.
8. the sandbox is deleted after the run.

A green run is evidence for this exact public canary only. It does not authorize or prove PANAM production integration.
