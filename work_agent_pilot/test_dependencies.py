"""Behavioral requirements; the same tests run against RED and GREEN subjects."""

import copy
import itertools
import unittest
from collections import UserDict

from work_agent_pilot.dependencies import dependency_layers


class DictSubclass(dict):
    pass


class ListSubclass(list):
    pass


class DependencyLayersTests(unittest.TestCase):
    def test_empty_graph(self):
        self.assertEqual(dependency_layers({}), [])

    def test_specification_example(self):
        self.assertEqual(
            dependency_layers({'b': ['a'], 'a': [], 'c': []}),
            [['a', 'c'], ['b']],
        )

    def test_independent_nodes_are_lexicographically_sorted(self):
        graph = {name: [] for name in ['z', 'a_1', 'a-1', 'a0', 'a']}
        self.assertEqual(dependency_layers(graph), [['a', 'a-1', 'a0', 'a_1', 'z']])

    def test_layers_wait_for_all_prerequisites(self):
        graph = {'a': [], 'b': ['a'], 'c': ['a'], 'd': ['a', 'b'],
                 'e': ['b', 'c'], 'f': ['d', 'e'], 'g': []}
        self.assertEqual(dependency_layers(graph),
                         [['a', 'g'], ['b', 'c'], ['d', 'e'], ['f']])

    def test_dictionary_insertion_order_does_not_change_layers(self):
        items = [('a', []), ('b', []), ('c', ['b', 'a']),
                 ('d', ['a']), ('e', ['c', 'd'])]
        for ordered in itertools.permutations(items):
            with self.subTest(order=[key for key, _ in ordered]):
                self.assertEqual(dependency_layers(dict(ordered)),
                                 [['a', 'b'], ['c', 'd'], ['e']])

    def test_prerequisite_order_does_not_change_layers(self):
        for ordered in itertools.permutations(['a', 'b', 'c']):
            with self.subTest(order=ordered):
                graph = {'a': [], 'b': [], 'c': [], 'd': list(ordered)}
                self.assertEqual(dependency_layers(graph), [['a', 'b', 'c'], ['d']])

    def test_duplicate_prerequisites_are_harmless(self):
        self.assertEqual(dependency_layers({'a': [], 'b': ['a', 'a', 'a']}),
                         [['a'], ['b']])

    def test_valid_id_boundaries(self):
        ids = ['a', 'z', 'a' + '0' * 31, 'a_b-c9']
        self.assertEqual(dependency_layers({key: [] for key in ids}), [sorted(ids)])

    def test_invalid_node_ids(self):
        bad_ids = ['', 'A', '1a', '_a', '-a', 'a.b', 'a b', 'a\n',
                   'a\t', 'a/b', 'é', 'а', 'a' * 33, None, True, 7, ('a',)]
        for bad_id in bad_ids:
            with self.subTest(node=bad_id):
                with self.assertRaises(ValueError):
                    dependency_layers({bad_id: []})

    def test_invalid_prerequisite_ids(self):
        bad_ids = ['', 'A', '1a', 'a\n', 'é', 'a' * 33,
                   None, True, 7, [], {}, ('a',)]
        for bad_id in bad_ids:
            with self.subTest(prerequisite=bad_id):
                with self.assertRaises(ValueError):
                    dependency_layers({'a': [bad_id]})

    def test_requires_plain_dictionary(self):
        for graph in [None, True, False, 0, '', 'a', [], (), set(),
                      UserDict({'a': []}), DictSubclass({'a': []})]:
            with self.subTest(graph=graph):
                with self.assertRaises(ValueError):
                    dependency_layers(graph)

    def test_requires_plain_prerequisite_lists(self):
        for value in [None, True, False, 0, '', 'a', (), set(), {}, ListSubclass()]:
            with self.subTest(prerequisites=value):
                with self.assertRaises(ValueError):
                    dependency_layers({'a': value})

    def test_unknown_prerequisite_is_rejected(self):
        with self.assertRaises(ValueError):
            dependency_layers({'a': ['missing']})

    def test_unknown_prerequisite_in_disconnected_component_is_rejected(self):
        with self.assertRaises(ValueError):
            dependency_layers({'a': [], 'b': ['unknown']})

    def test_self_dependency_is_rejected(self):
        with self.assertRaises(ValueError):
            dependency_layers({'a': ['a']})

    def test_two_node_cycle_is_rejected(self):
        with self.assertRaises(ValueError):
            dependency_layers({'a': ['b'], 'b': ['a']})

    def test_longer_cycle_is_rejected(self):
        with self.assertRaises(ValueError):
            dependency_layers({'a': ['c'], 'b': ['a'], 'c': ['b']})

    def test_disconnected_cycle_rejects_entire_graph(self):
        with self.assertRaises(ValueError):
            dependency_layers({'ready': [], 'a': ['b'], 'b': ['a']})

    def test_thousand_node_chain_is_accepted(self):
        names = [f't{i:04d}' for i in range(1000)]
        graph = {name: ([names[i - 1]] if i else [])
                 for i, name in enumerate(names)}
        self.assertEqual(dependency_layers(graph), [[name] for name in names])

    def test_more_than_thousand_nodes_is_rejected(self):
        with self.assertRaises(ValueError):
            dependency_layers({f't{i}': [] for i in range(1001)})

    def test_ten_thousand_dependency_entries_are_accepted(self):
        self.assertEqual(dependency_layers({'a': [], 'b': ['a'] * 10000}),
                         [['a'], ['b']])

    def test_repeats_count_toward_dependency_limit(self):
        with self.assertRaises(ValueError):
            dependency_layers({'a': [], 'b': ['a'] * 10001})

    def test_dependency_limit_is_total_across_lists(self):
        with self.assertRaises(ValueError):
            dependency_layers({'a': [], 'b': ['a'] * 5000, 'c': ['a'] * 5001})

    def test_success_does_not_mutate_input(self):
        shared = ['a', 'a']
        graph = {'a': [], 'b': shared, 'c': shared}
        before = copy.deepcopy(graph)
        self.assertEqual(dependency_layers(graph), [['a'], ['b', 'c']])
        self.assertEqual(graph, before)
        self.assertIs(graph['b'], shared)
        self.assertIs(graph['c'], shared)

    def test_rejection_does_not_mutate_input(self):
        graph = {'ready': [], 'a': ['b', 'b'], 'b': ['a']}
        before = copy.deepcopy(graph)
        with self.assertRaises(ValueError):
            dependency_layers(graph)
        self.assertEqual(graph, before)

    def test_calls_are_independent(self):
        first = dependency_layers({'a': [], 'b': ['a']})
        self.assertEqual(first, [['a'], ['b']])
        first[0].append('changed')
        self.assertEqual(dependency_layers({'a': [], 'b': ['a']}), [['a'], ['b']])


if __name__ == '__main__':
    unittest.main()
