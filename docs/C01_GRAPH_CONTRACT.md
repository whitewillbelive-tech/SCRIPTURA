# C-01 research graph contract

`scripts/c01_graph.py` builds a read-only in-memory graph from accepted,
rights-filtered records. It neither reads research ZIPs nor writes to a
database. Keys are **opaque local coordinates supplied by the application**;
callers must not use raw private record identifiers or unrestricted text as
keys. Graph projections omit free text, source URLs, and field payloads.

`ResearchGraph(nodes, edges, verifier=...)` accepts node dictionaries with
`key` and `kind`; passage nodes additionally have `corpus`, `scheme`, and
`reference`. Edges specify `key`, `from`, `to`, `kind`, and an `evidence`
list of local evidence keys. Evidence must point through an existing locator,
edition, and source before it can support a claim of source confirmation.
The optional verifier is trusted server code: archive data and user requests
must never supply it. A callback must validate that the evidence actually
supports that specific relation; mere existence of a source chain is not
independent verification.

Claims about speakers, affiliations, official adoption, external critiques,
contradictions, direct rebuttals, and alignments remain `pending` unless both
the source chain and the independent verifier support them. Pending edges are
returned only on explicit request and have `kind=relation_candidate` with a
separate `asserted_kind`; they are not affirmed facts. A different
interpretation does not create a rebuttal. Author and speaker edges are
separate and no role, affiliation, faith, or formal doctrine is inferred.
Source confirmation does not assert academic review or theological truth.

`passage(corpus, scheme, reference)` requires exact equality across all three
components; it never merges different corpora or numbering schemes.
`alignments(key)` returns only explicit, verified, evidenced alignment edges;
it does not infer transitive equivalence. `neighbors` supports incoming and
outgoing traversal, excluding pending links by default. Duplicate keys,
unknown kinds, invalid relation endpoints, and malformed records are
quarantined and counted without echoing them.

The existing private explorer exposes an authenticated read-only graph route
using its safe comparison projection. This adapter currently represents only
claim-to-passage links as pending candidates; it does not infer source,
speaker, official adoption, or rebuttal edges. The general graph engine has
not been tested as a persistent graph database. Run synthetic tests with
`python3 -m unittest discover -s tests -p test_c01_graph.py -v`; the synthetic
scale check is `python3 scripts/benchmark_c01_graph.py --records 200000`.
