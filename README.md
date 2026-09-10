# PANAM CI Lab

Public synthetic CI laboratory for PANAM.

This repository is intentionally isolated from PANAM production infrastructure and private source code. It contains only public-safe synthetic checks, generic linters, public dependency/standards checks and non-sensitive benchmark harnesses.

## Security boundary

- No production credentials or secrets.
- No access to private PANAM repositories or services.
- No real user, legal, email, Drive, Telegram or operational data.
- No production deployment authority.
- A green workflow here is test evidence only; it cannot authorize a PANAM production action.

The initial workflow runs a deterministic synthetic smoke check on GitHub-hosted `ubuntu-latest`.
