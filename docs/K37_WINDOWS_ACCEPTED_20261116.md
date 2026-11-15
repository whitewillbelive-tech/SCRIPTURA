# SCRIPTURA K-3–K-7 — Windows private research browser acceptance

Recorded: 2026-11-16 (Asia/Seoul)  
Branch: `codex/scriptura-k37-private-candidate-fix`  
Functional code baseline: `be6c4163ea7c71926b476f7e77a6c04230f7b969`

## Latest user acceptance (actual personal Windows machine)

The user tested the integrated private-local viewer with D-13 and D-14–D-16 research archives and reported **5 / 5 PASS**:

| Item | User result |
|---|---|
| Interpretation cards render for different selected passages | PASS |
| D-13 or D-14 interpretation statement appears as actual text | PASS |
| D-13 or D-14 reasoning appears as actual text | PASS |
| Unverified private research input notes are clearly distinguished | PASS |
| Passage change, candidate search and detail-view transition function | PASS |

The user previously reported K-2 Windows acceptance **7/7 PASS** (an earlier version, not a substitute for this result).

## Automated evidence and provenance

- GitHub Actions run: https://github.com/whitewillbelive-tech/SCRIPTURA/actions/runs/43745598748
- Five jobs succeeded on the same functional baseline, including Windows synthetic launcher/security and application regression tests.
- The D-13/D-14 two-archive private loader, D-16 comparison display, source/reasoning private-note tier and Windows archive stat/fstat fix are incorporated in this branch.

## Scope of this acceptance

**Accepted:** usability-critical private-local research functions tested by the user. The former blocker "actual D-13 and D-14–D-16 archives cannot be read and interpretations cannot be displayed" is resolved at the functional level.

**Not inferred:** that all 145 new records or all 81 comparison partitions were individually visually inspected on Windows; completeness/accuracy of every source; human scholarly review; official doctrinal adoption; licensing for redistribution, full-text indexing or model transmission; public or production readiness. The `local_input_candidate` state means input note with independent confirmation, quotation status and reuse rights *still unverified*. Such ongoing research evaluation does **not** invalidate the successful private browsing functionality.

## Completion policy

Call the **K-3–K-7 private-local browsing functional pilot: Windows user accepted (5/5)**.

Do not repeat a blanket "integration incomplete" on the basis of independent academic/permissions coverage. Report specific new functional defects only if observed or reproduced. Historical gate reports are retained as time-specific snapshots, not silently rewritten as though they were final findings.

No main merge, production deploy, research ZIP alteration or Library conversation-log upload is included in this record.
