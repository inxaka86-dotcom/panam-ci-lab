# Work coding-agent pilot: dependency layers

Task reference: LAB-DAG-20261116-01 (synthetic experiment identity, not an authoritative PANAM job).

Implement a small deterministic utility from this natural-language specification. It is a pure algorithm, not a scheduler, task registry, security decision or production integration.

## Required behavior

`dependency_layers(graph)` accepts a plain Python dict mapping task IDs to plain lists of prerequisite IDs. IDs are ASCII strings matching `[a-z][a-z0-9_-]{0,31}`. At most 1000 nodes and 10000 total dependency entries are accepted. Empty input returns an empty list.

Return a list of lists: each list contains all nodes ready at that depth, sorted lexicographically. A dependency must occur in an earlier layer. Neither dictionary insertion order nor prerequisite order may change the result. Do not mutate the input. Repeated prerequisite entries are harmless and count toward the input limit. Use the Python standard library, preferably `graphlib.TopologicalSorter` after validation.

Reject malformed graph/container types, malformed IDs, unknown prerequisite IDs, self-dependencies, cycles and oversized input with `ValueError`. Do not partially return a graph containing a cycle. No file/network access or subprocess execution in the utility.

Examples: `{}` -> `[]`; `{'b': ['a'], 'a': [], 'c': []}` -> `[['a', 'c'], ['b']]`; `{'a': ['b'], 'b': ['a']}` -> `ValueError`.

## Experiment acceptance

Write behavioral unittest tests before implementation. Run them against a temporary inert stub and record real assertion failures, then implement and run unchanged tests to green. Preserve genuine failures and repairs; do not invent an error to claim self-correction. Retain text logs and a JSON receipt with commands, exit codes, durations and code hashes. A synthetic negative control is explicitly labeled; it is not a failed model attempt.

Add a bounded path-scoped GitHub Actions workflow using the repository's pinned checkout, `contents: read`, no persisted credentials, no secrets, no self-hosted runners and no deployment. Run publication gate and the standard-library tests. No external packages or model APIs.

Document exact reproduction commands, input limitations, author identity as Work coding agent, and scope. All content must be public synthetic. Do not add private source, data, topology, receipts or instructions to this repository. No merge or publish.
