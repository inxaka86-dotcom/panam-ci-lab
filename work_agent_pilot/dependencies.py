"""Deterministic dependency layers for bounded public synthetic task graphs."""

from graphlib import CycleError, TopologicalSorter
import re


_ID = re.compile(r'[a-z][a-z0-9_-]{0,31}')


def dependency_layers(graph: object) -> list[list[str]]:
    """Return sorted ready-node batches, or raise ValueError for invalid input.

    Only plain dicts containing plain prerequisite lists are accepted. At most
    1000 nodes and 10000 entries (including repetitions) may be supplied.
    Validation precedes sorting so unknown prerequisites cannot create nodes.
    The input is never modified, and cycles reject the entire graph.
    """
    if type(graph) is not dict:
        raise ValueError('graph must be a plain dict')
    if len(graph) > 1000:
        raise ValueError('graph exceeds 1000 nodes')
    for node in graph:
        if not isinstance(node, str) or _ID.fullmatch(node) is None:
            raise ValueError('invalid task ID')

    entries = 0
    for node, prerequisites in graph.items():
        if type(prerequisites) is not list:
            raise ValueError('prerequisites must be a plain list')
        entries += len(prerequisites)
        if entries > 10000:
            raise ValueError('graph exceeds 10000 dependency entries')
        for prerequisite in prerequisites:
            if not isinstance(prerequisite, str) or _ID.fullmatch(prerequisite) is None:
                raise ValueError('invalid prerequisite ID')
            if prerequisite not in graph:
                raise ValueError('unknown prerequisite ID')
            if prerequisite == node:
                raise ValueError('self-dependency is forbidden')

    sorter = TopologicalSorter(graph)
    try:
        sorter.prepare()
    except CycleError as error:
        raise ValueError('graph contains a cycle') from error
    layers = []
    while sorter.is_active():
        ready = sorted(sorter.get_ready())
        layers.append(ready)
        sorter.done(*ready)
    return layers
