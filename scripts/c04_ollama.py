"""Bounded discovery of models on the local Ollama loopback server only.

No user-controlled URL, redirect handling, proxy use, prompt, or model call.
The result is for local display; it contains no research records.
"""
import http.client
import json
import re
import socket
import time

_HOST = '127.0.0.1'
_PORT = 11434
_MAX_BYTES = 65536
_MAX_MODELS = 1000
_SECONDS = 3.0
_NAME = re.compile(r'[A-Za-z0-9_.:-]{1,70}\Z')


def _empty(status):
    return {'status': status, 'models': [], 'unsupported_count': 0}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def _read_bounded(connection, response, deadline):
    """Enforce a total deadline, including a slowly streamed response."""
    data = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('deadline')
        # HTTP/1.0 responses can detach conn.sock; response's buffered file
        # retains the same local socket until the response is consumed.
        sock = connection.sock
        if sock is None:
            try:
                sock = response.fp.raw._sock
            except AttributeError:
                raise OSError('socket_unavailable') from None
        sock.settimeout(remaining)
        part = response.read1(min(4096, _MAX_BYTES + 1 - len(data)))
        if not part:
            return bytes(data)
        data.extend(part)
        if len(data) > _MAX_BYTES:
            raise ValueError('response_too_large')


def list_local_models():
    """Return installed compatible names, or an explicitly non-ready state.

    A name must also be accepted by the existing local generation API. Names
    of models with other valid Ollama naming schemes are counted, not used.
    A successful connection is not evidence of inference or scholarly quality.
    """
    connection = None
    deadline = time.monotonic() + _SECONDS
    try:
        connection = http.client.HTTPConnection(_HOST, _PORT, timeout=_SECONDS)
        connection.request('GET', '/api/tags', headers={'Accept': 'application/json'})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('deadline')
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        response = connection.getresponse()
        # http.client never follows a redirect; refuse it explicitly.
        if response.status != 200:
            return _empty('unavailable')
        if response.length is not None and response.length > _MAX_BYTES:
            return _empty('invalid_response')
        try:
            raw = _read_bounded(connection, response, deadline)
            payload = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
        except (UnicodeError, ValueError, RecursionError):
            return _empty('invalid_response')
        items = payload.get('models') if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) > _MAX_MODELS:
            return _empty('invalid_response')
        names = []
        unsupported = 0
        for row in items:
            value = row.get('name') if isinstance(row, dict) else None
            if not isinstance(value, str) or not _NAME.fullmatch(value):
                unsupported += 1
            elif value not in names:
                names.append(value)
        return {'status': 'ready', 'models': names, 'unsupported_count': unsupported}
    except (OSError, socket.timeout, TimeoutError, http.client.HTTPException):
        return _empty('unavailable')
    finally:
        if connection is not None:
            connection.close()
