# PANAM: mini-SWE-agent restricted public runtime pilot

This experiment runs **the real pinned upstream mini-SWE-agent 2.4.6 loop and DockerEnvironment** on a disposable GitHub-hosted runner. The input data and test files are purely synthetic.

## Stage A — integration and containment check

- Upstream: [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent/commit/04d809ceab9df28f9adaed044884180159172930), pinned to exact commit `04d809ceab9df28f9adaed044884180159172930`.
- Uses upstream `DeterministicModel` — **NOT an LLM**. This confirms agent control-flow, tool execution, RED/GREEN tests and submission handling only.
- Uses upstream DockerEnvironment, with `--network=none`, `--ipc=none`, read-only root filesystem, `--cap-drop=ALL`, `no-new-privileges`, UID/GID 65532, PID/memory/CPU caps, disposable tmpfs, no host binds.
- No user tokens, model API keys, private PANAM files, self-hosted PANAM runners or production operations.
- The public base Docker image is acquired by tag and its digest is logged; **not yet digest-pinned**. Do not call the experiment a fully reproducible supply-chain attestation.
- Docker daemon remains a privileged trusted host component; this test is not proof against daemon/kernel escape.

## Acceptance evidence

Verify the GitHub Actions **job log**, not just green check:

```text
PUBLICATION_GATE=PASS
UPSTREAM_PIN=MATCH
SANDBOX_BOUNDARY=PASS
NETWORK_DENIED=PASS
AGENT_MODEL=UPSTREAM_DETERMINISTIC_NO_LLM
TDD_RED=PASS expected_test_failure=YES
TDD_GREEN=PASS tests=3
MINI_SWE_RUNTIME=PASS steps=5
```

## Stage B — actual language-model coding

**Not established by Stage A.** A separate local-model or authorized API-model experiment must prove that generated edits, not prewritten commands, satisfy tests. No claim of autonomous code generation or speedup is valid until that evidence exists.

**Disposition:** DRAFT / RESEARCH_ONLY. Keep PR unmerged, never deploy. A public green result confers no PANAM production authority.
