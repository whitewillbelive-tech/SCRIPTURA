#!/usr/bin/env python3
"""Private loopback-only candidate preview; the research ZIP stays read-only."""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import hmac
import ipaddress
import json
import re
import sys
import threading
import time
import urllib.parse
import warnings
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from j2_bridge.candidate_readonly import load_candidate_archive

WEB_ROOT = Path(__file__).resolve().parent / 'j2_web'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
FILTERS = {'community': 'tradition', 'researcher': 'researcher', 'corpus': 'passage_corpus', 'scheme': 'passage_scheme', 'reference': 'passage_reference', 'source_kind': 'source_kind', 'attribution': 'attribution', 'verification_status': 'verification_status', 'authority_status': 'authority_status', 'rights_status': 'rights_status', 'access_path': 'access_path', 'record_kind': 'record_kind', 'stage': 'stage'}
SEARCH_FIELDS = ('tradition', 'community_reference', 'evaluated_subject', 'researcher', 'speaker', 'passage_corpus', 'passage_scheme', 'passage_reference', 'source_title', 'source_creator', 'source_kind', 'attribution', 'verification_status', 'authority_status', 'rights_status', 'access_path', 'record_kind')
MAX_QUERY_LENGTH = 200
PAGE_SIZE = 100
RIGHTS_ACTIONS = frozenset(('browse', 'collect_metadata', 'store_raw', 'store_excerpt', 'index_fulltext', 'embed', 'send_to_model', 'redistribute', 'public_link'))
RIGHTS_DECISIONS = frozenset(('unknown', 'conditional', 'allowed', 'prohibited', 'not_recorded', 'conflicting', 'unmapped'))
SAFE_RECORD_FIELDS = frozenset(('key', 'stage', 'record_kind', 'category', 'attribution', 'original_attribution', 'authority_status', 'input_authority_status', 'verification_status', 'quotation_status', 'argument_status', 'reported_independent_review_status', 'independent_review_status', 'audit_observation_key', 'rights_status', 'tradition', 'community_reference', 'community_role', 'evaluated_subject', 'researcher', 'speaker', 'speaker_type', 'passage_corpus', 'passage_scheme', 'passage_reference', 'source_title', 'source_creator', 'source_kind', 'source_doi', 'source_year', 'access_path', 'locator', 'unmapped', 'checked_at', 'as_of', 'valid_from', 'valid_until', 'display_status'))
SAFE_STAGES = frozenset(('base', 'd5', 'd6', 'd7', 'd8'))
SAFE_TABLES = frozenset(('sources', 'editions', 'locators', 'rights', 'passages', 'alignments', 'agents', 'affiliations', 'claims', 'evidence', 'relations', 'reviews', 'audit_conflicts', 'authority_documents', 'authority_registries', 'claim_scope_audits', 'cross_corpus_topics', 'interpretive_evidence', 'position_attestations', 'rights_delta', 'source_access_events', 'communities', 'assessments', 'relationships', 'authority', 'audit_reviews', 'correction_candidates', 'research_gaps', 'conflicts', 'institutional_assertions', 'rights_overrides', 'unresolved_gaps'))


def _safe_unmapped(value):
    """Only table names, mapping enum, and counts; never source text or IDs."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for stage, tables in value.items():
        if stage not in SAFE_STAGES or not isinstance(tables, dict):
            continue
        accepted = {}
        for table, details in tables.items():
            if table not in SAFE_TABLES or not isinstance(details, dict):
                continue
            count, mapping = details.get('input_count'), details.get('mapping')
            if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 100000 and mapping in ('partial', 'unmapped'):
                accepted[table] = {'input_count': count, 'mapping': mapping}
        result[stage] = accepted
    return result


def _rights_map(value):
    if not isinstance(value, dict):
        return {a: 'not_recorded' for a in sorted(RIGHTS_ACTIONS)}
    return {a: value.get(a) if isinstance(value.get(a), str) and value.get(a) in RIGHTS_DECISIONS else 'unmapped' for a in sorted(RIGHTS_ACTIONS)}


def _rights_overrides(value):
    if not isinstance(value, list):
        return []
    return [
        {'action': item['action'],
         'previous_decision': item.get('previous_decision') if item.get('previous_decision') in RIGHTS_DECISIONS else 'unmapped',
         'new_decision': item.get('new_decision') if item.get('new_decision') in RIGHTS_DECISIONS else 'unmapped',
         'evidence': item.get('evidence') if item.get('evidence') in ('recorded', 'missing') else 'missing'}
        for item in value if isinstance(item, dict) and item.get('action') in RIGHTS_ACTIONS
    ]


def _safe_record(row, *, research=False):
    """Defense-in-depth projection: never forward arbitrary source fields."""
    result = {key: value for key, value in row.items() if key in SAFE_RECORD_FIELDS and (value is None or isinstance(value, (str, int, float)))}
    result['unmapped'] = [value for value in row.get('unmapped', []) if isinstance(value, str)] if isinstance(row.get('unmapped'), list) else []
    if research:
        # Format checks alone do not establish field-specific display rights
        # or privacy suitability. Keep such fields out of response and search.
        for key in ('source_title', 'source_creator', 'researcher', 'speaker', 'tradition', 'community_reference', 'evaluated_subject'):
            result[key] = None
    # Direct quotation and free-form claim text are not authorized in this gate.
    result['summary'] = None
    result['rights'] = _rights_map(row.get('rights'))
    result['effective_permissions'] = {a: False for a in sorted(RIGHTS_ACTIONS)}
    result['rights_overrides'] = _rights_overrides(row.get('rights_overrides'))
    editions = row.get('edition_rights', [])
    result['edition_rights'] = [
        {'key': item.get('key') if isinstance(item.get('key'), str) and re.fullmatch(r'(?:base|d[5-8]|synthetic):editions:[1-9][0-9]*', item['key']) else None,
         'rights': _rights_map(item.get('rights')),
         'rights_overrides': _rights_overrides(item.get('rights_overrides')),
         'effective_permissions': {a: False for a in sorted(RIGHTS_ACTIONS)}}
        for item in editions if isinstance(item, dict)
    ] if isinstance(editions, list) else []
    policy = row.get('field_policy', {})
    if isinstance(policy, dict):
        result['field_policy'] = {key: value for key, value in policy.items() if key in ('source_metadata', 'summary', 'locator') and value in ('metadata_candidate', 'candidate_visible_local', 'redacted_rights_unresolved', 'structured_identifier_only', 'unmapped')}
    passages = row.get('passages', [])
    if isinstance(passages, list):
        result['passages'] = [{key: p.get(key) for key in ('corpus', 'scheme', 'reference') if isinstance(p.get(key), str) or p.get(key) is None} for p in passages if isinstance(p, dict)]
    for key, fields in (('evidence', ('kind', 'status')), ('relationships', ('kind', 'status', 'direction', 'target_key', 'assessment')), ('attestation_observations', ('scope', 'verification_status', 'as_of')), ('access_events', ('method', 'result', 'checked_at'))):
        items = row.get(key, [])
        result[key] = [{field: item.get(field) for field in fields if item.get(field) is None or isinstance(item.get(field), str)} for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return result


def _text(value):
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return ' '.join(_text(item) for item in value)
    return ''


def local_archive_path(value):
    """Reject obvious network paths before any file open; mount type is unknown."""
    if not isinstance(value, str) or not value or '\x00' in value or value.startswith(('\\\\', '//')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', value):
        raise ValueError('로컬 파일 경로가 필요합니다.')
    return Path(value)


def filter_records(dataset, params):
    """Search the pre-redacted projection only; unknown temporal scope stays pending."""
    allowed = set(FILTERS) | {'q', 'as_of', 'offset', 'key', 'evidence_kind', 'evidence_status', 'relation_kind', 'relation_status', 'relation_direction', 'rights_action', 'rights_decision'}
    if set(params) - allowed or any(len(v) != 1 for v in params.values()):
        raise ValueError('invalid query')
    q = {k: v[0].strip() for k, v in params.items()}
    if any(len(value) > MAX_QUERY_LENGTH for value in q.values()):
        raise ValueError('invalid query')
    if q.get('rights_action') and q['rights_action'] not in RIGHTS_ACTIONS or q.get('rights_decision') and q['rights_decision'] not in RIGHTS_DECISIONS:
        raise ValueError('invalid query')
    try:
        offset = int(q.get('offset', '0'))
        if not 0 <= offset <= 100000:
            raise ValueError('invalid offset')
        requested_date = q.get('as_of', '')
        if requested_date and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}', requested_date) or dt.date.fromisoformat(requested_date).isoformat() != requested_date):
            raise ValueError('invalid date')
    except (TypeError, ValueError, OverflowError):
        raise ValueError('invalid query') from None
    search = q.get('q', '').casefold()
    found = []
    for original in dataset['records']:
        row = _safe_record(original, research=dataset.get('dataset') == 'D8')
        if q.get('key') and row.get('key') != q['key']:
            continue
        if search and not (any(search in _text(row.get(key)) for key in SEARCH_FIELDS) or any(search in _text(p.get(field)) for p in row.get('passages', []) for field in ('corpus', 'scheme', 'reference'))):
            continue
        community = q.get('community', '').casefold()
        if community and not any(community in _text(row.get(key)) for key in ('tradition', 'community_reference', 'evaluated_subject')):
            continue
        researcher = q.get('researcher', '').casefold()
        if researcher and not any(researcher in _text(row.get(key)) for key in ('researcher', 'speaker', 'source_creator')):
            continue
        # Enumerations use exact matches: e.g. "verified" must never also
        # select a record labeled "unverified".
        if any(term and term.casefold() != _text(row.get(FILTERS[key])) for key, term in q.items() if key in FILTERS and key not in ('community', 'researcher', 'corpus', 'scheme', 'reference')):
            continue
        passage_terms = {key: q.get(key, '').casefold() for key in ('corpus', 'scheme', 'reference')}
        if any(passage_terms.values()):
            passages = row.get('passages')
            if not isinstance(passages, list) or not passages:
                passages = [{'corpus': row.get('passage_corpus'), 'scheme': row.get('passage_scheme'), 'reference': row.get('passage_reference')}]
            # Every address predicate must refer to the same passage entry.
            if not any(isinstance(p, dict) and all(not term or term in _text(p.get(key)) for key, term in passage_terms.items()) for p in passages):
                continue
        action, decision = q.get('rights_action', ''), q.get('rights_decision', '')
        if action or decision:
            rights_groups = row['edition_rights'] if row['record_kind'] == 'source' and row['edition_rights'] else [row]
            observations = [(a, value) for group in rights_groups for a, value in group['rights'].items()] + [(item['action'], item['new_decision']) for group in rights_groups for item in group['rights_overrides']]
            if not any((not action or name == action) and (not decision or value == decision) for name, value in observations):
                continue
        for collection, predicates in (('evidence', {'kind': q.get('evidence_kind', ''), 'status': q.get('evidence_status', '')}), ('relationships', {'kind': q.get('relation_kind', ''), 'status': q.get('relation_status', ''), 'direction': q.get('relation_direction', '')})):
            if any(predicates.values()) and not any(all(not term or term.casefold() == _text(item.get(key)) for key, term in predicates.items()) for item in row[collection]):
                break
        else:
            predicates = None
        if predicates is not None:
            continue
        projected = dict(row)
        if requested_date:
            start, end = row.get('valid_from'), row.get('valid_until')
            try:
                # Never infer a historical/current official status from a year alone.
                if not isinstance(start, str) or not isinstance(end, str):
                    raise ValueError('unknown')
                if dt.date.fromisoformat(start).isoformat() != start or dt.date.fromisoformat(end).isoformat() != end or start > end:
                    raise ValueError('unknown')
                if not start <= requested_date <= end:
                    continue
                projected['date_filter_status'] = 'documented_interval_only'
            except (TypeError, ValueError):
                projected['date_filter_status'] = 'pending'
        found.append(projected)
    return {'dataset': dataset['dataset'], 'counts': dataset['counts'], 'warnings': dataset['warnings'], 'facets': dataset.get('facets', {}), 'unmapped_summary': _safe_unmapped(dataset.get('unmapped_summary')), 'total': len(found), 'offset': offset, 'page_size': PAGE_SIZE, 'records': found[offset:offset + PAGE_SIZE]}


class PrivatePreviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, data, secret, port=0):
        if not isinstance(secret, str) or len(secret) < 20 or not secret.strip() or len(secret.encode('utf-8')) > 256 or any(ord(c) < 32 or ord(c) > 126 for c in secret):
            raise ValueError('세션 비밀은 출력 가능한 ASCII 문자 20자 이상이어야 합니다.')
        if not isinstance(data, dict) or not isinstance(data.get('records'), list) or data.get('dataset') not in ('D8', 'synthetic'):
            raise ValueError('후보 자료를 불러올 수 없습니다.')
        self.dataset = data
        self._secret = secret.encode('utf-8')
        self._attempt_lock = threading.Lock()
        self._failed_attempts = 0
        self._retry_after = 0.0
        super().__init__(('127.0.0.1', port), Handler)
        self.expected_host = '127.0.0.1:' + str(self.server_address[1])
        self.expected_origin = 'http://' + self.expected_host

    def handle_error(self, request, client_address):
        # Neither request paths nor selected data may reach server logs.
        return


class Handler(BaseHTTPRequestHandler):
    server_version = 'SCRIPTURA-Local'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args):
        return

    def _respond(self, status, body, content_type='text/plain; charset=utf-8'):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def _valid_peer(self):
        try:
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                return False
        except ValueError:
            return False
        if self.headers.get_all('Host', []) != [self.server.expected_host]:
            return False
        origin = self.headers.get_all('Origin', [])
        if len(origin) > 1 or (origin and origin[0] != self.server.expected_origin):
            return False
        fetch_site = self.headers.get('Sec-Fetch-Site', '')
        if fetch_site and fetch_site not in ('same-origin', 'none'):
            return False
        return True

    def _authenticated(self):
        header = self.headers.get_all('Authorization', [])
        try:
            supplied = header[0][7:].encode('ascii') if len(header) == 1 and header[0].startswith('Bearer ') else b''
        except UnicodeEncodeError:
            supplied = b''
        with self.server._attempt_lock:
            now = time.monotonic()
            if now < self.server._retry_after:
                return False
            if hmac.compare_digest(supplied, self.server._secret):
                self.server._failed_attempts = 0
                return True
            self.server._failed_attempts += 1
            if self.server._failed_attempts >= 5:
                self.server._failed_attempts = 0
                self.server._retry_after = now + 10
            return False

    def do_GET(self):
        if not self._valid_peer():
            return self._respond(403, '접근이 거부되었습니다.')
        try:
            url = urllib.parse.urlsplit(self.path)
            # Exact raw path match; no filesystem traversal or remote URL accepted.
            if url.scheme or url.netloc or not url.path.startswith('/'):
                return self._respond(400, '잘못된 요청입니다.')
            if url.path in ASSETS and not url.query:
                name, mime = ASSETS[url.path]
                return self._respond(200, (WEB_ROOT / name).read_bytes(), mime)
            if url.path == '/api/candidates':
                if not self._authenticated():
                    return self._respond(401, '세션 인증이 필요합니다.')
                if len(url.query) > 4096:
                    return self._respond(400, '잘못된 요청입니다.')
                params = urllib.parse.parse_qs(url.query, keep_blank_values=True, max_num_fields=32, encoding='utf-8', errors='strict')
                value = filter_records(self.server.dataset, params)
                return self._respond(200, json.dumps(value, ensure_ascii=False, separators=(',', ':')), 'application/json; charset=utf-8')
            return self._respond(404, '요청을 찾을 수 없습니다.')
        except (ValueError, UnicodeError):
            return self._respond(400, '잘못된 요청입니다.')
        except (OSError, KeyError, TypeError):
            return self._respond(500, '요청을 처리할 수 없습니다.')

    def do_POST(self):
        return self._respond(405, '허용되지 않는 요청입니다.')

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_POST


def main(argv=None):
    parser = argparse.ArgumentParser(description='로컬 연구 후보 탐색기 (루프백 전용)')
    parser.add_argument('--archive', required=True, help='고정 D-8 ZIP 파일')
    args = parser.parse_args(argv)
    try:
        archive = local_archive_path(args.archive)
        dataset = load_candidate_archive(archive)
    except Exception:
        print('고정 D-8 자료를 확인할 수 없습니다. 경로와 무결성을 확인하세요.', file=sys.stderr)
        return 1
    try:
        if not sys.stdin.isatty():
            raise ValueError('terminal required')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            secret = getpass.getpass('세션 비밀 (ASCII 20자 이상, 입력 숨김): ')
        server = PrivatePreviewServer(dataset, secret)
        secret = None
    except (ValueError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print('\n세션을 시작할 수 없습니다. 20자 이상 ASCII 세션 비밀이 필요합니다.', file=sys.stderr)
        return 1
    url = 'http://' + server.expected_host + '/'
    try:
        # The loopback address has no archive path, record, or secret.
        print('비공개 로컬 탐색기 주소: ' + url)
        print('종료하려면 Ctrl+C를 누르세요.')
        try:
            if not webbrowser.open(url, new=1):
                print('브라우저를 자동으로 열지 못했습니다. 위 주소를 로컬 브라우저에서 여세요.')
        except Exception:
            print('브라우저를 자동으로 열지 못했습니다. 위 주소를 로컬 브라우저에서 여세요.')
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
