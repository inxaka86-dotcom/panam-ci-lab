# Work coding-agent dependency-layer pilot

Author: Work coding agent. Task: LAB-DAG-20261116-01. This public synthetic
algorithm fixture implements [SPEC.md](SPEC.md). It is not a runtime scheduler,
production integration, security decision or authoritative PANAM job.

```python
from work_agent_pilot.dependencies import dependency_layers

assert dependency_layers({'b': ['a'], 'a': [], 'c': []}) == [['a', 'c'], ['b']]
```

`dependency_layers(graph: object) -> list[list[str]]` accepts a plain Python
dict whose values are plain lists of prerequisite IDs. IDs are ASCII strings
matching `[a-z][a-z0-9_-]{0,31}`. There may be at most 1000 nodes and 10000 total
prerequisite entries. Repetitions are harmless but count toward this limit.
Unknown references, invalid IDs or containers, self-dependencies, cycles and
oversized inputs raise `ValueError`. Empty input returns `[]`.

Every layer contains all nodes ready after completion of the previous layers,
sorted lexicographically. Input dictionary insertion and prerequisite order do
not affect the result. Inputs are not modified. Full validation and cycle
checking precede layer construction; a disconnected cycle rejects the whole
graph. The utility uses the Python standard library's `graphlib` and performs
no file/network access or subprocess execution.

Reproduce from the repository root with Python 3.9 or later:

```bash
python3 -B -m unittest -v work_agent_pilot.test_dependencies
python3 -B -m unittest discover -v
python3 -B checks/public_smoke.py
python3 -B checks/publication_gate.py
```

The publication gate scans tracked paths, so stage new files before using it to
check newly added content. Do not commit unrelated files. Local hash-bound
execution records, the explicitly labeled synthetic RED control and recorder
commands are documented in [evidence/README.md](evidence/README.md). The RED
control intentionally exits nonzero and is excluded from the GREEN CI run.
There are no external packages, model APIs or credentials required.

The path-scoped GitHub Actions job uses the repository's pinned checkout,
read-only contents permission, nonpersisted checkout credentials, a five-minute
job bound and a GitHub-hosted runner. It runs the publication gate, full root
standard-library test discovery and public smoke check. Local evidence does not
claim that a hosted workflow ran. This work does not merge, publish or deploy.
