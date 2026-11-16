"""Atomic in-memory manager for K3 receipts; no implicit persistence or network.

The expected baseline digest and manifest digest must be authenticated out of
band. Archive hashes establish integrity, not rights or factual correctness.
"""
from copy import deepcopy
import hashlib
import json
import re
import threading
from k3_bridge.receipt import receive, TABLES, ReceiptError

_VERSION = re.compile(r'D[1-9][0-9]{0,5}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def canonical_snapshot(version, tables):
    """Return exact snapshot bytes for a separately authenticated trust anchor.

    The bytes are sensitive; keep them local and do not log them or their hash.
    """
    if not isinstance(version, str) or not _VERSION.fullmatch(version) or not isinstance(tables, dict):
        raise ReceiptError('baseline_invalid')
    clean = {}
    seen = set()
    for table, rows in tables.items():
        if table not in TABLES or not isinstance(rows, list):
            raise ReceiptError('baseline_invalid')
        clean[table] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'].strip() or row['id'] in seen:
                raise ReceiptError('baseline_invalid')
            seen.add(row['id'])
            clean[table].append(deepcopy(row))
    try:
        return json.dumps({'version': version, 'tables': clean}, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError):
        raise ReceiptError('baseline_invalid') from None


def snapshot_digest(version, tables):
    return hashlib.sha256(canonical_snapshot(version, tables)).hexdigest()


class ResearchCatalog:
    """One local process manager with immutable generations and atomic commits.

    This is not a multi-process coordinator or an archive provenance verifier.
    The caller authenticates the initial canonical snapshot out of band.
    """
    def __init__(self, *, version, tables, trusted_snapshot_sha256):
        if not isinstance(trusted_snapshot_sha256, str) or not _SHA.fullmatch(trusted_snapshot_sha256):
            raise ReceiptError('baseline_invalid')
        owned = deepcopy(tables)
        digest = snapshot_digest(version, owned)
        if digest != trusted_snapshot_sha256:
            raise ReceiptError('baseline_untrusted')
        self.__lock = threading.Lock()
        self.__version, self.__tables, self.__digest = version, owned, digest
        self.__history = []

    def __repr__(self):
        return '<ResearchCatalog redacted>'

    def current_anchor(self):
        """Sensitive local digest, never suitable for logs or remote transport."""
        with self.__lock:
            return self.__digest

    def snapshot(self):
        """Return a local isolated copy; content can contain private data."""
        with self.__lock:
            return {'version': self.__version, 'tables': deepcopy(self.__tables)}

    def history(self):
        with self.__lock:
            return deepcopy(self.__history)

    def integrate(self, blob, *, trusted_manifest_sha256, expected_anchor):
        """Verify before locking and publish only if the baseline is unchanged.

        Rejected rows and their dependencies remain out of the new generation.
        Hash, archive, schema or concurrency failures leave the old state intact.
        """
        with self.__lock:
            if expected_anchor != self.__digest:
                raise ReceiptError('baseline_changed')
            version, tables = self.__version, deepcopy(self.__tables)
        ids = {row['id']: table for table, rows in tables.items() for row in rows}
        receipt = receive(blob, trusted_manifest_sha256=trusted_manifest_sha256,
                          trusted_baseline_sha256=expected_anchor,
                          baseline_ids=ids, trusted_baseline_version=version)
        counts = receipt.aggregate()
        if counts['accepted_rows'] == 0:
            raise ReceiptError('increment_fully_quarantined')
        for table in TABLES:
            accepted = receipt.accepted_records(table)
            if accepted:
                tables.setdefault(table, []).extend(accepted)
        new_version = receipt.version()
        new_digest = snapshot_digest(new_version, tables)
        event = {'version': new_version, 'counts': counts}
        with self.__lock:
            if expected_anchor != self.__digest:
                raise ReceiptError('baseline_changed')
            self.__tables, self.__version, self.__digest = tables, new_version, new_digest
            self.__history.append(deepcopy(event))
        return deepcopy(event)
