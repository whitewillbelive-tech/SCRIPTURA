"""Synthetic checks: these tests never contact Ollama or a network."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import c04_ollama as local


class FakeSocket:
    def __init__(self): self.timeouts = []
    def settimeout(self, value): self.timeouts.append(value)


class FakeResponse:
    def __init__(self, data=b'', status=200, length=None):
        self.data, self.status, self.length = data, status, length
        self.calls = 0
    def read1(self, n):
        self.calls += 1
        result, self.data = self.data[:n], self.data[n:]
        return result


class FakeConnection:
    instances = []
    response = None
    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = FakeSocket()
        self.closed = False
        FakeConnection.instances.append(self)
    def request(self, method, path, headers): self.requested = (method, path, headers)
    def getresponse(self): return FakeConnection.response
    def close(self): self.closed = True


class OllamaDiscoveryTests(unittest.TestCase):
    def setUp(self): FakeConnection.instances.clear()

    def discover(self, response):
        FakeConnection.response = response
        with patch.object(local.http.client, 'HTTPConnection', FakeConnection):
            return local.list_local_models()

    def test_names_are_bounded_and_connection_is_literal_loopback(self):
        data = {'models': [{'name': 'synthetic:1'}, {'name': 'synthetic:1'},
                           {'name': 'owner/model:1'}, {'name': 'bad\nname'}]}
        value = self.discover(FakeResponse(json.dumps(data).encode()))
        self.assertEqual(value, {'status': 'ready', 'models': ['synthetic:1'], 'unsupported_count': 2})
        conn = FakeConnection.instances[-1]
        self.assertEqual((conn.host, conn.port), ('127.0.0.1', 11434))
        self.assertEqual(conn.requested[0:2], ('GET', '/api/tags'))
        self.assertTrue(conn.closed)
        self.assertTrue(conn.sock.timeouts)

    def test_redirect_is_never_followed(self):
        response = FakeResponse(b'', status=302)
        value = self.discover(response)
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(len(FakeConnection.instances), 1)
        self.assertEqual(response.calls, 0)

    def test_oversize_and_malformed_are_not_listed(self):
        value = self.discover(FakeResponse(b' ', length=local._MAX_BYTES + 1))
        self.assertEqual(value['status'], 'invalid_response')
        value = self.discover(FakeResponse(b' ' * (local._MAX_BYTES + 1)))
        self.assertEqual(value['status'], 'invalid_response')
        value = self.discover(FakeResponse(b'{"models": [], "models": []}'))
        self.assertEqual(value['status'], 'invalid_response')

    def test_deadline_stops_slow_drip(self):
        class Drip(FakeResponse):
            def read1(self, n): return b'x'
        with patch.object(local.http.client, 'HTTPConnection', FakeConnection), \
             patch.object(local.time, 'monotonic', side_effect=[0, 0, 1, 2, 4]):
            FakeConnection.response = Drip()
            self.assertEqual(local.list_local_models()['status'], 'unavailable')

    def test_network_failure_returns_fixed_status(self):
        with patch.object(local.http.client, 'HTTPConnection', side_effect=OSError('sensitive error')):
            self.assertEqual(local.list_local_models(), {'status': 'unavailable', 'models': [], 'unsupported_count': 0})


if __name__ == '__main__':
    unittest.main()
