"""Closed, local-only entry point for legacy Work and generic JSONL receipts.

Legacy K37's already rights-filtered preview cannot be reconstructed as a
canonical raw research archive. It stays in its existing private preview lane.
The generic lane changes only the caller-supplied in-memory catalog.
"""
from copy import deepcopy
from c01_receipt import ResearchCatalog
from k3_bridge.receipt import ReceiptError

_SEAL = object()


class AdapterResult:
    __slots__ = ('__mode', '__aggregate', '__preview')

    def __init__(self, token, mode, aggregate, preview=None):
        if token is not _SEAL:
            raise ReceiptError('adapter_untrusted')
        self.__mode, self.__aggregate, self.__preview = mode, deepcopy(aggregate), preview

    def __repr__(self):
        return '<AdapterResult redacted>'

    def aggregate(self):
        return deepcopy(self.__aggregate)

    def local_preview(self):
        """Return the existing K37 private preview, never a canonical dataset.

        This object is sensitive and must not be logged, serialized publicly,
        sent to an AI provider, or treated as a rights approval.
        """
        if self.__mode != 'legacy_work_d13_d16':
            raise ReceiptError('preview_not_available')
        return self.__preview


def receive_increment(kind, *, catalog=None, blob=None, trusted_manifest_sha256=None,
                      expected_anchor=None, base_path=None, delta_path=None):
    """Receive one of two explicitly specified formats without trust fallback.

    The legacy lane is read-only and returns only its existing protected local
    preview. The JSONL v1 lane needs an explicitly authenticated catalog and
    manifest. Neither successful lane grants publication or model-use rights.
    """
    if kind == 'legacy_work_d13_d16':
        if (catalog is not None or blob is not None or trusted_manifest_sha256 is not None
                or expected_anchor is not None or base_path is None or delta_path is None):
            raise ReceiptError('adapter_invalid')
        from k37_bridge.real_receipt import load_d16_archive
        try:
            preview = load_d16_archive(base_path, delta_path)
            receipt = preview['d16_receipt']
            keys = ('d13_sources', 'd13_claims', 'd14_sources', 'd14_claims',
                    'd14_passages', 'comparison_sets', 'd13_quarantined', 'd14_quarantined')
            summary = {key: receipt[key] for key in keys}
            if any(type(value) is not int or value < 0 for value in summary.values()):
                raise ValueError
        except Exception:
            raise ReceiptError('legacy_receipt_invalid') from None
        return AdapterResult(_SEAL, kind, summary, preview)
    if kind == 'jsonl_v1':
        if type(catalog) is not ResearchCatalog or base_path is not None or delta_path is not None:
            raise ReceiptError('adapter_invalid')
        event = catalog.integrate(blob, trusted_manifest_sha256=trusted_manifest_sha256,
                                  expected_anchor=expected_anchor)
        return AdapterResult(_SEAL, kind, event)
    raise ReceiptError('adapter_format_unsupported')
