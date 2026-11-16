"""Synthetic graph contracts; no private archive or model calls."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from c01_graph import ResearchGraph


def fixture():
    nodes = [
        {'key': 'source', 'kind': 'source'},
        {'key': 'edition', 'kind': 'edition', 'source': 'source'},
        {'key': 'locator', 'kind': 'locator', 'edition': 'edition'},
        {'key': 'evidence', 'kind': 'evidence', 'locator': 'locator'},
        {'key': 'author', 'kind': 'person'}, {'key': 'speaker', 'kind': 'person'},
        {'key': 'community', 'kind': 'community'},
        {'key': 'claim-a', 'kind': 'claim'}, {'key': 'claim-b', 'kind': 'claim'},
        {'key': 'bible-a', 'kind': 'passage', 'corpus': 'Bible', 'scheme': 'A', 'reference': '1:1'},
        {'key': 'bible-b', 'kind': 'passage', 'corpus': 'Bible', 'scheme': 'B', 'reference': '1:1'},
        {'key': 'other', 'kind': 'passage', 'corpus': 'Other', 'scheme': 'A', 'reference': '1:1'},
    ]
    return nodes


def relation(key, kind, start, end, evidence=('evidence',), **extra):
    return dict(key=key, kind=kind, **{'from': start, 'to': end}, evidence=list(evidence), **extra)


class GraphTests(unittest.TestCase):
    def test_address_lookup_is_exact_not_an_implicit_alignment(self):
        graph = ResearchGraph(fixture(), [])
        self.assertEqual(graph.passage('Bible', 'A', '1:1'), ('bible-a',))
        self.assertEqual(graph.passage('Bible', 'B', '1:1'), ('bible-b',))
        self.assertEqual(graph.passage('Other', 'A', '1:1'), ('other',))
        self.assertEqual(graph.passage('Bible', 'unknown', '1:1'), ())
        self.assertEqual(graph.alignments('bible-a'), ())

    def test_only_evidenced_independently_confirmed_alignment_is_traversable(self):
        edge = relation('align', 'alignment', 'bible-a', 'bible-b', status='source_confirmed')
        untrusted = ResearchGraph(fixture(), [edge])
        self.assertEqual(untrusted.alignments('bible-a'), ())
        self.assertEqual(untrusted.neighbors('bible-a', include_pending=True)[0]['kind'], 'relation_candidate')
        verified = ResearchGraph(fixture(), [edge], verifier=lambda key, evidence: key == 'align')
        self.assertEqual(len(verified.alignments('bible-a')), 1)
        self.assertEqual(len(verified.alignments('bible-b')), 1)
        self.assertEqual(verified.alignments('other'), ())

    def test_author_is_not_claim_speaker_and_officiality_is_not_inferred(self):
        graph = ResearchGraph(fixture(), [relation('authorship', 'authored', 'author', 'source')], verifier=lambda *_: True)
        self.assertEqual(graph.neighbors('author')[0]['kind'], 'authored')
        self.assertEqual(graph.neighbors('claim-a', direction='in'), ())
        self.assertEqual(graph.neighbors('community'), ())

    def test_unconfirmed_rebuttal_officiality_and_affiliation_are_candidates(self):
        edges = [relation('r', 'rebuts', 'claim-a', 'claim-b'),
                 relation('o', 'official_adoption', 'community', 'claim-a'),
                 relation('a', 'affiliation', 'author', 'community'),
                 relation('s', 'speaker', 'speaker', 'claim-a')]
        graph = ResearchGraph(fixture(), edges)
        self.assertEqual(graph.neighbors('claim-a'), ())
        for node in ('claim-a', 'community', 'author', 'speaker'):
            pending = graph.neighbors(node, include_pending=True)
            self.assertEqual(pending[0]['status'], 'pending')
            self.assertEqual(pending[0]['kind'], 'relation_candidate')

    def test_explicit_confirmed_rebuttal_remains_distinct_from_comparison(self):
        edges = [relation('contrast', 'contrasts', 'claim-a', 'claim-b'),
                 relation('rebuttal', 'rebuts', 'claim-a', 'claim-b')]
        graph = ResearchGraph(fixture(), edges, verifier=lambda key, _: key == 'rebuttal')
        values = graph.neighbors('claim-a')
        self.assertEqual([(x['kind'], x['status']) for x in values],
                         [('contrasts', 'recorded_unverified'), ('rebuts', 'source_confirmed')])

    def test_missing_locator_source_or_evidence_never_promotes(self):
        base = fixture()
        for missing in ('evidence', 'locator', 'edition', 'source'):
            graph = ResearchGraph([n for n in base if n['key'] != missing],
                                  [relation('r', 'rebuts', 'claim-a', 'claim-b')], verifier=lambda *_: True)
            self.assertEqual(graph.neighbors('claim-a'), ())
            self.assertEqual(graph.neighbors('claim-a', include_pending=True)[0]['status'], 'pending')

    def test_verifier_exception_is_closed_and_error_values_do_not_escape(self):
        def reject(*_):
            raise RuntimeError('SYNTHETIC SECRET')
        graph = ResearchGraph(fixture(), [relation('r', 'rebuts', 'claim-a', 'claim-b')], verifier=reject)
        result = graph.neighbors('claim-a', include_pending=True)
        self.assertEqual(result[0]['status'], 'pending')
        self.assertNotIn('SYNTHETIC SECRET', repr(result))

    def test_duplicate_nodes_and_edges_are_quarantined(self):
        nodes = fixture() + [{'key': 'claim-b', 'kind': 'claim'}]
        edges = [relation('same', 'contrasts', 'claim-a', 'claim-b'),
                 relation('same', 'contrasts', 'claim-a', 'claim-b')]
        graph = ResearchGraph(nodes, edges, verifier=lambda *_: True)
        self.assertEqual(graph.neighbors('claim-a', include_pending=True), ())
        self.assertEqual(graph.summary()['duplicate_nodes'], 2)
        self.assertEqual(graph.summary()['invalid_edges'], 2)

    def test_incorrect_relation_types_never_become_valid(self):
        graph = ResearchGraph(fixture(), [relation('bad', 'authored', 'claim-a', 'community')], verifier=lambda *_: True)
        self.assertEqual(graph.neighbors('claim-a', include_pending=True), ())
        self.assertEqual(graph.summary()['invalid_edges'], 1)

    def test_no_raw_metadata_in_graph_projection(self):
        nodes = fixture()
        nodes[0]['private_text'] = 'SYNTHETIC PRIVATE VALUE'
        graph = ResearchGraph(nodes, [relation('r', 'contrasts', 'claim-a', 'claim-b')])
        self.assertNotIn('SYNTHETIC PRIVATE VALUE', repr(graph.neighbors('claim-a')))

    def test_malformed_unhashable_input_is_quarantined(self):
        nodes = fixture() + [{'key': 'bad', 'kind': []}]
        edges = [relation('bad-edge', [], 'claim-a', 'claim-b')]
        graph = ResearchGraph(nodes, edges)
        self.assertEqual(graph.summary()['invalid_nodes'], 1)
        self.assertEqual(graph.summary()['invalid_edges'], 1)


if __name__ == '__main__':
    unittest.main()
