# Work Coding Agent Pilot Implementation Plan

> For agentic workers: execute this single task through a bounded implementer, TDD and a fresh reviewer. No user approval pause is needed for these explicitly authorized isolated experimental changes.

**Goal:** Prove a real Work coding agent can deliver tested code from a text task and preserve reproducible evidence.
**Architecture:** Pure dependency-layer utility and unittest suite; public GitHub-hosted CI. This is an algorithmic fixture, not a runtime orchestrator.
**Tech Stack:** Python 3 standard library, unittest, graphlib, GitHub Actions.
**Spec:** `work_agent_pilot/SPEC.md`.

## Global Constraints

- Public synthetic only; no private PANAM source, data, secrets or production topology.
- Worker owns only its dedicated branch/worktree.
- No production, external model calls, install, merge, deployment or access changes.
- Plain dict/list input, ASCII IDs `[a-z][a-z0-9_-]{0,31}`, at most 1000 nodes and 10000 dependency entries.
- Workflow uses GitHub-hosted ubuntu-latest, contents: read and no persisted credentials.

## Review Focus

- Reject bool/None/string and wrong container shapes consistently with ValueError.
- Unknown references cannot silently become additional nodes.
- Cycles in disconnected components must reject the entire graph.
- Ordering is independent of input insertion order and repeated prerequisites.
- Resource limits include repeated prerequisite entries and boundary values.

## Task 1: Implement and verify dependency layers

Files: create `work_agent_pilot/__init__.py`, `work_agent_pilot/dependencies.py`, `work_agent_pilot/test_dependencies.py`, `work_agent_pilot/README.md`, `work_agent_pilot/evidence/*`, `.github/workflows/work-agent-pilot.yml`.

Interfaces: `dependency_layers(graph: object) -> list[list[str]]`; malformed data raises `ValueError`.

- [ ] Inspect existing public code; no equivalent dependency algorithm was found by controller in main or open public PR scope.
- [ ] Write behavioral tests covering the specification and review focus. Example assertions: empty -> []; a+b+c example -> [['a', 'c'], ['b']]; reversed insertion order unchanged; unknown IDs/cycles -> ValueError; limits and valid boundaries; original input unchanged.
- [ ] Run the same tests against a temporary inert implementation; capture nonzero exit and actual assertion failures. Label as synthetic RED control. Commit test/evidence before final implementation when practical.
- [ ] Implement minimal behavior using graphlib after validation; keep utility free of I/O and effects.
- [ ] Run focused tests, diagnose and fix actual failures. Log them honestly; never weaken requirements to turn tests green.
- [ ] Add path-scoped bounded CI and reproduction documentation. Use existing checkout pin `fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09` with persist-credentials: false.
- [ ] Run `python3 -B -m unittest discover -v`, `python3 checks/public_smoke.py`, and after staging `python3 checks/publication_gate.py`; preserve output and actual exit codes.
- [ ] Commit, self-review, write full report outside repository. Do not push; controller independently verifies, reviews and creates Draft PR.

## Ownership preflight

Main at inspection: 045931f887b4e066df15103cc2879e7f0e7fe729. Public PRs #51 (inert plan validator) and #52 (mini-SWE/local-Qwen addition pilot) are complementary existing baselines, frozen and unmodified. No listed open PR owns this dependency algorithm. This experiment measures a different execution path; it does not supersede #52 or claim a production worker.
