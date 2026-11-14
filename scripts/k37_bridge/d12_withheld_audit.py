"""Explain D-12 summary withholding without serializing research data.

This diagnostic does not grant access, change the K-2 gate, or determine that
withheld material is protected text. Callers must keep per-card coordinates
private and report only ``summary()`` aggregates.
"""
from collections import Counter
import re

from k2_bridge.receipt import summary_for_record

_KEY = re.compile(r'd12:claims:[1-9][0-9]{0,7}\Z')
_METHOD_MARKERS = ('자체 요약', '인용 없이')
_NEGATIVE_MARKERS = ('아님', '금지', '불가', '아니', '미확인')
_REASONS = frozenset(('card_unmapped', 'self_or_nonquote_not_attested',
                      'original_storage_not_explicitly_false', 'other_safety_gate'))


class D12WithheldAudit:
    """Opaque in-memory diagnosis. Coordinates are not diagnostic output."""
    __slots__ = ('__records', '__summary')

    def __init__(self, records, summary):
        self.__records = records
        self.__summary = summary

    def __repr__(self):
        return '<D12WithheldAudit redacted>'

    def for_record(self, key):
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            return ()
        return self.__records.get(key, ())

    def summary(self):
        return dict(self.__summary)


def audit_d12_withheld(layers, dataset):
    """Classify each claim against the actual sealed summary index.

    The marker and storage checks mirror the first K-2 summary guard. Other
    guards remain classified as ``other_safety_gate``; this helper never
    predicts that those guards passed when an earlier guard did not. The two
    attestation reasons may overlap. No data value, raw identifier, path or
    exception is included in the result.
    """
    try:
        if not isinstance(dataset, dict) or dataset.get('dataset') != 'D12':
            raise ValueError('invalid')
        cards = dataset.get('records')
        tables = layers.get('d12')
        if not isinstance(cards, list) or not isinstance(tables, dict):
            raise ValueError('invalid')
        claims = tables.get('claims')
        if not isinstance(claims, list):
            raise ValueError('invalid')
        keys = {r.get('key') for r in cards if isinstance(r, dict)
                and r.get('stage') == 'd12' and r.get('record_kind') == 'claim'
                and isinstance(r.get('key'), str) and _KEY.fullmatch(r['key'])}
        reasons_by_key, counts = {}, Counter()
        seen = set()
        for entry in claims:
            if not isinstance(entry, dict) or not isinstance(entry.get('value'), dict):
                raise ValueError('invalid')
            line = entry.get('line')
            if type(line) is not int or not 0 < line < 100000000:
                raise ValueError('invalid')
            key = 'd12:claims:' + str(line)
            if key in seen:
                raise ValueError('invalid')
            seen.add(key)
            counts['claims_total'] += 1
            row = entry['value']
            if key not in keys:
                reasons = ('card_unmapped',)
            elif summary_for_record(dataset.get('_k2_summary_index'), 'D12', key) is not None:
                counts['displayed'] += 1
                reasons_by_key[key] = ()
                continue
            else:
                reasons = []
                method = row.get('verification_method')
                if (not isinstance(method, str)
                        or not all(marker in method for marker in _METHOD_MARKERS)
                        or any(marker in method for marker in _NEGATIVE_MARKERS)):
                    reasons.append('self_or_nonquote_not_attested')
                if row.get('original_text_stored') is not False:
                    reasons.append('original_storage_not_explicitly_false')
                if not reasons:
                    reasons.append('other_safety_gate')
                reasons = tuple(reasons)
            reasons_by_key[key] = reasons
            counts['withheld'] += 1
            for reason in reasons:
                counts[reason] += 1
            if 'self_or_nonquote_not_attested' in reasons and (
                    not isinstance(row.get('verification_method'), str)
                    or not row['verification_method'].strip()):
                counts['verification_method_missing_or_empty'] += 1
            if ('original_storage_not_explicitly_false' in reasons
                    and 'original_text_stored' not in row):
                counts['original_storage_field_absent'] += 1
        if not keys.issubset(seen):
            raise ValueError('invalid')
        result = {k: counts[k] for k in ('claims_total', 'displayed', 'withheld',
                  'card_unmapped', 'self_or_nonquote_not_attested',
                  'original_storage_not_explicitly_false', 'other_safety_gate',
                  'verification_method_missing_or_empty', 'original_storage_field_absent')}
        return D12WithheldAudit(reasons_by_key, result)
    except Exception:
        raise ValueError('d12_withheld_audit_unavailable') from None
