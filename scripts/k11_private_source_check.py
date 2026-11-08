"""Bounded private source-check preparation; default mode makes no network request.

Real source addresses, names, text and exceptions remain in process memory.
The optional network mode is for a separately authorised source check only.
The resulting aggregate is NOT a display grant or legal determination.
"""
from __future__ import annotations

import collections
from contextlib import redirect_stderr, redirect_stdout
import html
from html.parser import HTMLParser
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from i3_bridge import d6
from j3_bridge.private_io import read_checked_d8_layers
from k1_bridge.candidate_archive import load_k1_archive

MAX_SOURCES = 5
MAX_BYTES = 262144
_FIELDS = {
    'title': ('citation_title', 'dc.title', 'dcterms.title'),
    'creator': ('citation_author', 'dc.creator', 'dcterms.creator'),
    'publisher': ('citation_publisher', 'dc.publisher', 'dcterms.publisher'),
    'publication_year': ('citation_publication_date', 'citation_date', 'dc.date', 'dcterms.issued'),
}
_COUNTS = ('eligible', 'attempted', 'http_success', 'http_error', 'connection_failed',
           'other_failed', 'non_html', 'exact_title', 'exact_creator', 'exact_publisher',
           'exact_publication_year', 'license_reference_present', 'license_metadata_present')


def _hostname(url):
    try:
        value = urllib.parse.urlsplit(url)
        if (value.scheme != 'https' or not value.hostname or value.username or value.password
                or value.port not in (None, 443)):
            return None
        return value.hostname
    except (TypeError, ValueError):
        return None


def select(rows, allowed):
    """Return at most five rows; caller must not print the returned values."""
    if not isinstance(rows, list) or not isinstance(allowed, set):
        raise ValueError('invalid_input')
    return [row for row in rows if isinstance(row, dict) and _hostname(row.get('url')) in allowed][:MAX_SOURCES]


class _PrivateRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, original_host):
        self._original_host = original_host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _hostname(newurl) != self._original_host:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = collections.defaultdict(list)
        self.license_reference = False
        self.license_metadata = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = (attrs.get('name') or attrs.get('property') or '').lower()
            value = attrs.get('content')
            if key and value:
                self.values[key].append(value)
            if key in ('dc.rights', 'dc.rights.license', 'rights', 'license', 'copyright') and value:
                self.license_metadata = True
        if tag == 'link' and 'license' in (attrs.get('rel') or '').lower().split():
            self.license_reference = True


def _normal(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', html.unescape(str(value))).strip()).casefold()


def inspect(rows, allowed, *, approved_network=False, opener_factory=None):
    """Return fixed-key counts only. Never print rows or exception details."""
    selected = select(rows, allowed)
    counts = {key: 0 for key in _COUNTS}
    counts['eligible'] = len(selected)
    if not approved_network:
        return counts
    for row in selected:
        counts['attempted'] += 1
        try:
            factory = opener_factory or (lambda host: urllib.request.build_opener(_PrivateRedirect(host)))
            opener = factory(_hostname(row['url']))
            req = urllib.request.Request(row['url'], headers={
                'User-Agent': 'SCRIPTURA-Private-Research-Verification/1.0',
                'Accept': 'text/html', 'Accept-Encoding': 'identity'})
            with opener.open(req, timeout=8) as response:
                counts['http_success'] += 1
                if 'html' not in response.headers.get('Content-Type', '').lower():
                    counts['non_html'] += 1
                    continue
                page = response.read(MAX_BYTES).decode('utf-8', 'replace')
            parsed = _Metadata()
            parsed.feed(page)
            counts['license_reference_present'] += int(parsed.license_reference)
            counts['license_metadata_present'] += int(parsed.license_metadata)
            for field, keys in _FIELDS.items():
                if not row.get(field):
                    continue
                expected = _normal(row[field])
                actual = [_normal(value) for key in keys for value in parsed.values.get(key, [])]
                if field == 'publication_year':
                    match = any(re.fullmatch(r'\d{4}', expected) and
                                re.match(r'^' + re.escape(expected) + r'(?:[-/]|$)', value)
                                for value in actual)
                else:
                    match = expected in actual
                counts['exact_' + field] += int(match)
        except urllib.error.HTTPError:
            counts['http_error'] += 1
        except urllib.error.URLError:
            counts['connection_failed'] += 1
        except Exception:
            counts['other_failed'] += 1
    return counts


def _load_sources(blob):
    # Full K-1 receipt validation checks the pinned archive and its baseline.
    if load_k1_archive(blob).get('dataset') != 'D10':
        raise ValueError('archive_invalid')
    with zipfile.ZipFile(io.BytesIO(blob)) as d10:
        matches = [n for n in d10.namelist() if n.endswith('/SCRIPTURA_D9_RESEARCH.zip')]
        if len(matches) != 1:
            raise ValueError('archive_invalid')
        with zipfile.ZipFile(io.BytesIO(d10.read(matches[0]))) as d9:
            with zipfile.ZipFile(io.BytesIO(d9.read('baseline/SCRIPTURA_D8_RESEARCH.zip'))) as d8:
                snapshot = read_checked_d8_layers(d8)
            if snapshot.error_count:
                raise ValueError('archive_invalid')
            layers = snapshot.layers
            errors = collections.Counter()
            layers['d9'] = {'sources': d6._records(d9, 'd9/records/sources.jsonl', errors)}
            if errors:
                raise ValueError('archive_invalid')
            return [item['value'] for tables in layers.values() for item in tables.get('sources', [])]


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # An explicit switch is required for the action rejected by auto-review.
    # It does not itself replace the required user approval.
    approved_network = '--send-approved' in args
    args = [arg for arg in args if arg != '--send-approved']
    if len(args) != 1:
        print('invalid_arguments')
        return 2
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            path = args[0]
            if path.startswith(('\\\\', '//', '\\/', '/\\')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]+:', path):
                raise ValueError('archive_invalid')
            with open(path, 'rb') as source:
                blob = source.read(64 * 1024 * 1024 + 1)
            if len(blob) > 64 * 1024 * 1024:
                raise ValueError('archive_invalid')
            with open('/etc/codex/network-policy.json', encoding='utf-8') as config:
                policy = json.load(config)
            if policy.get('http_network_policy', {}).get('type') != 'restricted':
                raise ValueError('policy_unavailable')
            hosts = {item['host'] for item in policy['http_network_policy']['egress_rules']
                     if isinstance(item, dict) and isinstance(item.get('host'), str)}
            rows = _load_sources(blob)
            counts = inspect(rows, hosts, approved_network=approved_network)
        print(json.dumps(counts, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception:
        print('verification_unavailable')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
