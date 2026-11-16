"""Generate only synthetic nodes and edges; print aggregate timings."""
import argparse
import time
from c01_graph import ResearchGraph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--records', type=int, required=True, choices=(10000, 100000, 200000))
    count = parser.parse_args().records
    nodes = [{'key': 'claim', 'kind': 'claim'},
             {'key': 'source', 'kind': 'source'},
             {'key': 'edition', 'kind': 'edition', 'source': 'source'},
             {'key': 'locator', 'kind': 'locator', 'edition': 'edition'},
             {'key': 'evidence', 'kind': 'evidence', 'locator': 'locator'}]
    nodes.extend({'key': f'passage-{i}', 'kind': 'passage', 'corpus': 'synthetic',
                  'scheme': 'synthetic', 'reference': str(i)} for i in range(count))
    edges = [{'key': f'edge-{i}', 'from': 'claim', 'to': f'passage-{i}',
              'kind': 'about_passage', 'evidence': ['evidence']} for i in range(count)]
    start = time.monotonic()
    graph = ResearchGraph(nodes, edges)
    build = time.monotonic() - start
    start = time.monotonic()
    checks = sum(graph.passage('synthetic', 'synthetic', str(i)) == (f'passage-{i}',)
                 for i in (0, count // 2, count - 1))
    outgoing = len(graph.neighbors('claim'))
    query = time.monotonic() - start
    if checks != 3 or outgoing != count:
        raise SystemExit('synthetic_graph_benchmark_failed')
    print(f'synthetic_nodes={count} synthetic_edges={count} build_seconds={build:.3f} '
          f'query_seconds={query:.3f} lookup_checks=3/3')


if __name__ == '__main__':
    main()
