# Wave 5 — Open News offline benchmark

Status: PUBLIC-SAFE / SYNTHETIC-ONLY / ISOLATED-GITHUB-HOSTED / NO-PRODUCTION-AUTHORITY

## Purpose

Measure a pinned public `alphap365/open-news` snapshot on synthetic Russian-language news fixtures without PANAM private source, production services, credentials, user data, or real legal documents.

Exact upstream source under test:

- repository: https://github.com/alphap365/open-news
- commit: `ebb0e9b4deb0bf8fa8983e6324276a51f091ab43`
- stable release at qualification time: `v1.0.3`

## Public-only boundary

This wave contains only synthetic Russian HTML/RSS fixtures, a generic benchmark harness, the public upstream identity, and a GitHub-hosted workflow with read-only repository permission.

It contains no private PANAM repository source/history, production topology, secrets, tokens, credentials, real documents, logs, receipts, or private service access.

## Benchmark surface

Measured: Russian article extraction, Cyrillic preservation, local RSS parsing, Unicode query filtering, Russian language filtering, URL normalization and deduplication, date sorting, wall time and peak RSS.

Not measured: live news search, general crawling, Playwright/JavaScript rendering, external network acquisition, built-in summarization, or production integration.

## Network boundary

The workflow needs Internet access before the benchmark to clone the exact public upstream commit and install its public dependencies.

During the measured benchmark, the harness replaces Python socket connection methods with fail-closed guards. Any attempted network connection becomes a benchmark failure and is counted.

This is application-level evidence for the selected Python code path, not a claim of kernel-level network namespace isolation.

## Evidence

The workflow prints the exact upstream commit, Python version, hashes of upstream `pyproject.toml` and `uv.lock`, installed dependency freeze and SHA-256, machine-readable benchmark JSON, per-case pass/fail, wall time and peak RSS.

A green public CI run is benchmark evidence only. It does not authorize merge into a private repository, deployment, production execution, Autopilot activation, or private-data processing.
