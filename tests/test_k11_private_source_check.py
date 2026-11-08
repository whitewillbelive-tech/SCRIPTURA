"""Synthetic-only tests: no test opens a research archive or external site."""
import io
import json
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import k11_private_source_check as checker

SENTINEL = 'synthetic-sensitive-sentinel-921'


class _Response:
    headers = {'Content-Type': 'text/html'}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size):
        assert size == checker.MAX_BYTES
        return (b'<meta name="citation_title" content="Synthetic title">'
                b'<meta name="citation_author" content="Synthetic author">'
                b'<meta name="citation_publisher" content="Synthetic publisher">'
                b'<meta name="citation_date" content="2020-01-03">'
                b'<link rel="license" href="/synthetic">')


class _Opener:
    def __init__(self): self.calls = 0
    def open(self, *args, **kwargs):
        self.calls += 1
        return _Response()


class PrivateSourceCheckTests(unittest.TestCase):
    def row(self):
        return {'url': 'https://example.invalid/synthetic', 'title': 'Synthetic title',
                'creator': 'Synthetic author', 'publisher': 'Synthetic publisher',
                'publication_year': '2020'}

    def test_offline_mode_makes_no_request(self):
        with patch('urllib.request.build_opener', side_effect=AssertionError(SENTINEL)):
            result = checker.inspect([self.row()], {'example.invalid'})
        self.assertEqual(result['eligible'], 1)
        self.assertEqual(result['attempted'], 0)
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_network_is_bounded_and_only_fixed_aggregate_is_returned(self):
        opener = _Opener()
        result = checker.inspect([self.row()] * 7, {'example.invalid'},
                                 approved_network=True, opener_factory=lambda _host: opener)
        self.assertEqual(opener.calls, 5)
        for name in ('eligible', 'attempted', 'http_success', 'exact_title', 'exact_creator',
                     'exact_publisher', 'exact_publication_year', 'license_reference_present'):
            self.assertEqual(result[name], 5)
        self.assertNotIn('Synthetic', json.dumps(result))
        self.assertNotIn('example.invalid', json.dumps(result))
        self.assertNotIn('license_scope_verified', result)

    def test_denies_other_hosts_insecure_schemes_and_credentials(self):
        rows = [self.row(), {'url': 'https://other.invalid/path'},
                {'url': 'http://example.invalid/path'},
                {'url': 'https://user:password@example.invalid/path'},
                {'url': 'https://example.invalid:444/path'}]
        self.assertEqual(len(checker.select(rows, {'example.invalid'})), 1)

    def test_redirect_to_another_host_is_rejected(self):
        handler = checker._PrivateRedirect('example.invalid')
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'https://other.invalid/x'))
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'http://example.invalid/x'))

    def test_exceptions_are_aggregated_without_error_details(self):
        class Fails:
            def open(self, *args, **kwargs): raise urllib.error.URLError(SENTINEL)
        result = checker.inspect([self.row()], {'example.invalid'}, approved_network=True,
                                 opener_factory=lambda _host: Fails())
        self.assertEqual(result['connection_failed'], 1)
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_cli_error_does_not_echo_sensitive_argument_or_exception(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), patch('builtins.open', side_effect=OSError(SENTINEL)):
            result = checker.main([SENTINEL])
        self.assertEqual(result, 1)
        self.assertEqual(stdout.getvalue(), 'verification_unavailable\n')
        self.assertNotIn(SENTINEL, stdout.getvalue() + stderr.getvalue())


if __name__ == '__main__': unittest.main()
