"""Evidence-aware in-memory research graph; no database writes or network.

Callers supply locally scoped opaque keys and already rights-filtered records.
Input evidence labels are never treated as independent verification. The
optional verifier must be application-owned code, never a callback from input.
"""
from collections import Counter, defaultdict
from itertools import chain

_KINDS = frozenset(('passage', 'source', 'edition', 'locator', 'person',
                    'community', 'institution', 'tradition', 'claim',
                    'evidence', 'authority_document', 'topic'))
_RULES = {
    'authored': ({'person', 'institution'}, {'source'}),
    'speaker': ({'person', 'institution', 'community'}, {'claim'}),
    'affiliation': ({'person'}, {'community', 'institution'}),
    'official_adoption': ({'community', 'institution'}, {'claim', 'authority_document'}),
    'external_critique_of': ({'claim'}, {'community', 'institution', 'claim'}),
    'about_passage': ({'claim'}, {'passage'}),
    'cites': ({'claim', 'evidence'}, {'source', 'edition', 'locator'}),
    'has_evidence': ({'claim'}, {'evidence'}),
    'supports': ({'claim', 'evidence'}, {'claim'}),
    'qualifies': ({'claim'}, {'claim'}),
    'contrasts': ({'claim'}, {'claim'}),
    'contradicts': ({'claim'}, {'claim'}),
    'rebuts': ({'claim'}, {'claim'}),
    'alignment': ({'passage'}, {'passage'}),
    'cross_reference': ({'passage', 'claim', 'source'}, {'passage', 'claim', 'source'}),
    'about_topic': ({'claim', 'source', 'passage'}, {'topic'}),
    'published_by': ({'source', 'authority_document'}, {'institution', 'community'}),
    'edition_of': ({'edition'}, {'source'}),
    'locator_in': ({'locator'}, {'edition'}),
}
_SENSITIVE_RELATIONS = frozenset(('speaker', 'affiliation', 'official_adoption',
                                  'external_critique_of', 'rebuts', 'alignment',
                                  'contradicts'))


def _key(value):
    return isinstance(value, str) and 0 < len(value) <= 200 and not any(ord(c) < 32 for c in value)


class ResearchGraph:
    """Read-only graph with explicit and independently assessed edges.

    Result projections contain only local keys and fixed status labels. They
    deliberately omit input free text, raw metadata, URLs, and rights details.
    A passage's exact corpus/scheme/reference tuple is an isolation boundary;
    lookup does not normalize or merge distinct numbering schemes.
    """
    def __init__(self, nodes, edges, *, verifier=None):
        if not isinstance(nodes, (list, tuple)) or not isinstance(edges, (list, tuple)):
            raise ValueError('graph_invalid_input')
        if len(nodes) > 500_000 or len(edges) > 1_000_000:
            raise ValueError('graph_input_too_large')
        grouped = defaultdict(list)
        for node in nodes:
            if isinstance(node, dict) and _key(node.get('key')):
                grouped[node['key']].append(node)
        self._nodes = {}
        counts = Counter()
        for key, rows in grouped.items():
            if len(rows) != 1:
                counts['duplicate_nodes'] += len(rows)
                continue
            n = rows[0]
            if not isinstance(n.get('kind'), str) or n.get('kind') not in _KINDS:
                counts['invalid_nodes'] += 1
                continue
            self._nodes[key] = n
        counts['invalid_nodes'] += sum(1 for n in nodes if not isinstance(n, dict) or not _key(n.get('key')))
        addresses = defaultdict(list)
        for key, node in self._nodes.items():
            if node['kind'] != 'passage':
                continue
            address = (node.get('corpus'), node.get('scheme'), node.get('reference'))
            if all(_key(value) for value in address):
                addresses[address].append(key)
            else:
                counts['invalid_addresses'] += 1
        self._addresses = dict(addresses)
        self._out, self._in = defaultdict(list), defaultdict(list)
        edge_keys = Counter(e.get('key') for e in edges if isinstance(e, dict) and _key(e.get('key')))
        for edge in edges:
            if not isinstance(edge, dict):
                counts['invalid_edges'] += 1
                continue
            key, kind, src, dst = (edge.get('key'), edge.get('kind'), edge.get('from'), edge.get('to'))
            if (not _key(key) or edge_keys[key] != 1 or not isinstance(kind, str)
                    or kind not in _RULES or not _key(src) or not _key(dst)):
                counts['invalid_edges'] += 1
                continue
            source, target = self._nodes.get(src), self._nodes.get(dst)
            if not source or not target or source['kind'] not in _RULES[kind][0] or target['kind'] not in _RULES[kind][1]:
                counts['invalid_edges'] += 1
                continue
            raw_refs = edge.get('evidence', [])
            if not isinstance(raw_refs, list) or any(not _key(ref) for ref in raw_refs):
                counts['invalid_edges'] += 1
                continue
            # A source location is required even to consider an evidence
            # chain; an evidence row alone does not establish its provenance.
            evidence = []
            for ref in raw_refs:
                item = self._nodes.get(ref)
                locator = self._nodes.get(item.get('locator')) if item and _key(item.get('locator')) else None
                edition = self._nodes.get(locator.get('edition')) if locator and _key(locator.get('edition')) else None
                source_record = self._nodes.get(edition.get('source')) if edition and _key(edition.get('source')) else None
                if (item and item['kind'] == 'evidence' and locator and locator['kind'] == 'locator'
                        and edition and edition['kind'] == 'edition' and source_record and source_record['kind'] == 'source'):
                    evidence.append(ref)
            complete = bool(evidence) and len(set(evidence)) == len(raw_refs)
            confirmed = False
            if complete and callable(verifier):
                try:
                    confirmed = verifier(key, tuple(evidence)) is True
                except Exception:
                    confirmed = False
            status = 'source_confirmed' if confirmed else ('pending' if kind in _SENSITIVE_RELATIONS or not complete else 'recorded_unverified')
            # Unconfirmed assertions cannot be mistaken for an established
            # rebuttal, alignment, official adoption, or personal affiliation.
            result = {'key': key, 'from': src, 'to': dst,
                      'kind': kind if status != 'pending' else 'relation_candidate',
                      'asserted_kind': kind, 'status': status,
                      'evidence_count': len(evidence)}
            self._out[src].append(result)
            self._in[dst].append(result)
            counts['edges_'+status] += 1
        self._summary = dict(counts)

    def passage(self, corpus, scheme, reference):
        if not all(_key(value) for value in (corpus, scheme, reference)):
            return ()
        return tuple(self._addresses.get((corpus, scheme, reference), ()))

    def neighbors(self, key, *, direction='out', include_pending=False):
        if not _key(key) or direction not in ('out', 'in'):
            return ()
        rows = (self._out if direction == 'out' else self._in).get(key, ())
        return tuple(dict(row) for row in rows if include_pending or row['status'] != 'pending')

    def alignments(self, key):
        # Alignment is inherently bidirectional but only verified explicit
        # edges are traversable; no automatic address-equivalence closure.
        rows = chain(self._out.get(key, ()), self._in.get(key, ()))
        return tuple(dict(row) for row in rows if row['asserted_kind'] == 'alignment' and row['status'] == 'source_confirmed')

    def summary(self):
        return dict(self._summary)
