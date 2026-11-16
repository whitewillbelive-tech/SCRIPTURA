"""C-03 W11 replay harness: uses question text, NOT the grading oracle.

Needs user-owned W10R canonical ZIP and prior W11 QA ZIP. Actual Ollama
inference is opt-in. All output is local and does not grade correctness.
"""
import argparse
import json
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile
from c03_canonical_local import CanonicalIndex, CanonicalError, analyze_local

BOOK_MAP = (
    ('이사야 7:14','Isaiah 7:14'),
    ('요한복음 1:1','John 1:1'),
    ('마태복음 16:18','Matthew 16:18'),
    ('로마서 3:28','Romans 3:28'),
    ('야고보서 2:24','James 2:24'),
    ('창세기 1:1','Genesis 1:1'),
)
ALLOWED_CATEGORIES = {'same_passage','original_language','argument_counterargument',
                      'method_uncertainty','false_officialness','insufficient_evidence',
                      'injection','canon_alignment','rights','attribution'}

def search_from_question(question, index):
    # Exact book/address cue only, not guessing different canon or translation.
    if not isinstance(question,str) or len(question)>1000:
        return [], None
    ref = next((en for ko,en in BOOK_MAP if ko in question),None)
    if ref is None:
        # No default passage: missing context must remain NOT_RUN rather than
        # artificially presenting a different scripture's evidence.
        return [],None
    found=[row for row in index.find(ref,limit=30) if row['reference']==ref]
    return found,ref

def replay(canonical, audit, *, model=None, output=None, **kwargs):
    """Legacy entry point; C-04 verifies QA integrity before any replay."""
    from c04_benchmark import replay as safe_replay
    return safe_replay(canonical, audit, model=model, output=output, **kwargs)


def main(argv=None):
    from c04_benchmark import main as safe_main
    return safe_main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
