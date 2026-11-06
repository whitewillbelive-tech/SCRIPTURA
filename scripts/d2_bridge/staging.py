"""Synthetic-only, metadata-only staging. Research data must never be loaded.

The public CLI must generate its own synthetic fixture and must not expose this
internal function as an arbitrary ZIP importer. No source payload is stored.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .validator import EXPECTED_SHA256, EXPECTED_SNAPSHOT, TABLES, validate_archive

# Frozen research data is read-only; a synthetic test pin cannot authorize it.
D3_RESEARCH_SHA256 = 'baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be'
D4_RESEARCH_SHA256 = '05ab5bdf3fc258f39b926257c771ef4a17138355aa072cb8bc97c56387999beb'
D5_RESEARCH_SHA256 = '4709ddbe914c276e68ebcc66cee1d76e1c096e0071992eb53b9e4c2f03e96d19'
D6_RESEARCH_SHA256 = '6d94de447eba8517c038f6f709c8b1040e0c6efbdd4676f9e19aea568d3e59da'
D7_RESEARCH_SHA256 = '8a8fb8d4efde68f639b99ab8edb9eab14c320b4bc9e64e0aab882af7ee0a4820'
RESEARCH_ARCHIVE_SHA256 = frozenset({EXPECTED_SHA256, D3_RESEARCH_SHA256, D4_RESEARCH_SHA256, D5_RESEARCH_SHA256, D6_RESEARCH_SHA256, D7_RESEARCH_SHA256})
TEST_ACK = 'synthetic-test-only'
ACTIONS = frozenset({'browse', 'collect_metadata', 'store_raw', 'store_excerpt', 'index_fulltext', 'embed', 'send_to_model', 'redistribute', 'public_link'})
DANGEROUS_ACTIONS = frozenset({'store_raw', 'store_excerpt', 'index_fulltext', 'embed', 'send_to_model', 'redistribute', 'public_link'})
ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$')
SNAPSHOT_PATTERN = re.compile(r'^TEST-SYNTHETIC-[A-Za-z0-9._-]{1,100}$')
DB_PATTERN = re.compile(r'^scriptura_staging_[a-zA-Z0-9_]+$')
CODE_PATTERN = re.compile(r'^[a-z][a-z0-9_]{0,100}$')
SHA_PATTERN = re.compile(r'^[a-f0-9]{64}$')


class StagingError(Exception):
    """Safe, non-sensitive error; never include DB URLs or record content."""


def action_allowed(decisions, action):
    """No content action is enabled in this synthetic-only staging bridge.

    A source decision of allowed, even if explicit, does not establish edition,
    purpose, territory, duration and independent authorization. Preserve the
    decision but default deny until a separately reviewed rights model exists.
    """
    return False


def _parse_url(value, *, staging=False):
    try:
        p = urlsplit(value)
        if p.scheme not in ('postgres', 'postgresql') or not p.hostname or p.query or p.fragment or not p.path.startswith('/') or '/' in p.path[1:]:
            raise ValueError()
        # libpq query parameters and URI fragments can override connection target.
        host = p.hostname.lower()
        if host == 'localhost':
            host_group = 'loopback'
        else:
            try:
                addr = ipaddress.ip_address(host)
                host_group = 'loopback' if addr.is_loopback else str(addr)
            except ValueError:
                host_group = host.rstrip('.')
        port = p.port or 5432
        database = unquote(p.path[1:])
        username = unquote(p.username or '')
        password = unquote(p.password or '')
        if not database or '\x00' in database or not username or '\x00' in username or '\x00' in password:
            raise ValueError()
        if staging and (host not in ('localhost','127.0.0.1','::1') or not DB_PATTERN.fullmatch(database)):
            raise ValueError()
        return {'host':host,'host_group':host_group,'port':port,'database':database,'username':username,'password':password}
    except (ValueError, TypeError):
        raise StagingError('invalid_database_configuration') from None


def _connection(env):
    if env.get('SCRIPTURA_STAGING_APPROVED') != TEST_ACK:
        raise StagingError('synthetic_staging_not_explicitly_approved')
    stage = _parse_url(env.get('SCRIPTURA_STAGING_DATABASE_URL'), staging=True)
    for key in ('DATABASE_URL', 'SCRIPTURA_PRODUCTION_DATABASE_URL', 'SCRIPTURA_REVIEW_DATABASE_URL'):
        value = env.get(key)
        if value:
            other = _parse_url(value)
            # Loopback aliases refer to the same machine, irrespective of user.
            if (stage['host_group'], stage['port'], stage['database']) == (other['host_group'], other['port'], other['database']):
                raise StagingError('staging_matches_existing_database')
            # DNS names may resolve to loopback. A same-port/db production URL
            # with an unknown hostname cannot be proven different, so refuse.
            if other['host_group'] not in ('loopback',) and other['port'] == stage['port'] and other['database'] == stage['database']:
                raise StagingError('staging_database_identity_ambiguous')
    return stage


def _safe_data(report, records, origin, file_hashes):
    if report.get('status') != 'pass':
        raise StagingError('archive_validation_failed')
    snapshot = report.get('snapshot')
    digest = report.get('archive_sha256')
    if not isinstance(snapshot, str) or not SNAPSHOT_PATTERN.fullmatch(snapshot) or snapshot == EXPECTED_SNAPSHOT:
        raise StagingError('synthetic_snapshot_required')
    if not isinstance(digest, str) or not SHA_PATTERN.fullmatch(digest) or digest in RESEARCH_ARCHIVE_SHA256:
        raise StagingError('synthetic_archive_required')
    origin = Path(origin).name
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,160}[.]zip', origin):
        raise StagingError('invalid_archive_name')
    if not isinstance(records, dict) or set(records) != set(TABLES):
        raise StagingError('invalid_records')
    result = []
    for table in TABLES:
        for item in records[table]:
            data = item.get('data')
            if not isinstance(data, dict): raise StagingError('invalid_synthetic_record')
            record_id = data.get('id')
            expected_file = f'd2/records_merged/{table}.jsonl'
            source_file = item.get('file')
            line = item.get('row_number')
            rowhash = item.get('sha256')
            filehash = file_hashes.get(source_file)
            disposition = item.get('disposition')
            reasons = item.get('reasons')
            if not isinstance(record_id,str) or not ID_PATTERN.fullmatch(record_id) or source_file != expected_file or not isinstance(line,int) or isinstance(line,bool) or line < 1 or not isinstance(rowhash,str) or not SHA_PATTERN.fullmatch(rowhash) or not isinstance(filehash,str) or not SHA_PATTERN.fullmatch(filehash):
                raise StagingError('invalid_record_provenance')
            if disposition not in ('eligible','quarantined','blocked') or not isinstance(reasons,list) or any(not isinstance(r,str) or not CODE_PATTERN.fullmatch(r) for r in reasons):
                raise StagingError('invalid_record_disposition')
            status = data.get('review_status', data.get('verification_status', data.get('decision') if table == 'reviews' else None))
            if status is not None and (not isinstance(status,str) or not CODE_PATTERN.fullmatch(status)):
                raise StagingError('invalid_record_status')
            action = decision = edition = None
            if table == 'rights':
                action, decision, edition = data.get('action'), data.get('decision'), data.get('edition_id')
                if action not in ACTIONS or decision not in ('allowed','conditional','unknown','prohibited') or not isinstance(edition,str) or not ID_PATTERN.fullmatch(edition):
                    raise StagingError('invalid_rights_decision')
            result.append({'record_type':table,'record_id':record_id,'origin_file':source_file,'row_number':line,'origin_file_sha256':filehash,'original_sha256':rowhash,'disposition':disposition,'reasons':reasons,'validation_status':status,'rights_action':action,'rights_decision':decision,'rights_edition_id':edition})
    result.sort(key=lambda x:(x['record_type'],x['record_id']))
    if len({(r['record_type'],r['record_id']) for r in result}) != len(result) or len({(r['origin_file'],r['row_number']) for r in result}) != len(result):
        raise StagingError('duplicate_record_provenance')
    metadata = json.dumps(result, ensure_ascii=True, separators=(',', ':'), sort_keys=True).encode()
    return {'snapshot_id':snapshot, 'archive_sha256':digest, 'origin_zip':origin, 'record_count':len(result), 'metadata_hash':hashlib.sha256(metadata).hexdigest(), 'records':result}


def _sql(payload):
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True, separators=(',', ':'), sort_keys=True).encode()).decode('ascii')
    # Input crosses the SQL boundary solely as base64 alphabet in a string literal.
    return r'''\set ON_ERROR_STOP on
BEGIN;
SET LOCAL statement_timeout = '120s';
DO $guard$
DECLARE role_rec record; owner_oid oid; db_owner oid;
BEGIN
  IF current_database() !~ '^scriptura_staging_[a-zA-Z0-9_]+$' THEN RAISE EXCEPTION 'invalid staging database'; END IF;
  SELECT * INTO role_rec FROM pg_roles WHERE rolname=current_user;
  SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='scriptura_d2_stage';
  SELECT datdba INTO db_owner FROM pg_database WHERE datname=current_database();
  IF owner_oid IS NULL OR role_rec.rolsuper OR role_rec.rolcreatedb OR role_rec.rolcreaterole OR role_rec.rolreplication OR role_rec.rolbypassrls
     OR pg_has_role(current_user::regrole::oid, owner_oid, 'MEMBER') OR pg_has_role(current_user::regrole::oid, db_owner, 'MEMBER')
     OR has_database_privilege(current_user,current_database(),'CREATE') OR has_schema_privilege(current_user,'scriptura_d2_stage','CREATE')
     OR NOT has_schema_privilege(current_user,'scriptura_d2_stage','USAGE')
     OR NOT has_table_privilege(current_user,'scriptura_d2_stage.snapshots','SELECT') OR NOT has_table_privilege(current_user,'scriptura_d2_stage.snapshots','INSERT')
     OR NOT has_table_privilege(current_user,'scriptura_d2_stage.records','SELECT') OR NOT has_table_privilege(current_user,'scriptura_d2_stage.records','INSERT')
     OR has_table_privilege(current_user,'scriptura_d2_stage.snapshots','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
     OR has_table_privilege(current_user,'scriptura_d2_stage.records','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') THEN
    RAISE EXCEPTION 'staging writer must be a restricted non-owner role';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname NOT IN ('pg_catalog','information_schema','scriptura_d2_stage') AND n.nspname NOT LIKE 'pg\_%') THEN
    RAISE EXCEPTION 'database contains non-staging user tables or views';
  END IF;
END $guard$;
DO $load$
DECLARE p jsonb := convert_from(decode(''' + "'" + encoded + "'" + r''','base64'),'UTF8')::jsonb;
        old scriptura_d2_stage.snapshots%ROWTYPE; actual_count integer; mismatch_count integer;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p->>'snapshot_id',0));
  SELECT * INTO old FROM scriptura_d2_stage.snapshots WHERE snapshot_id=p->>'snapshot_id';
  IF FOUND THEN
    IF old.archive_sha256 IS DISTINCT FROM p->>'archive_sha256' OR old.origin_zip IS DISTINCT FROM p->>'origin_zip'
       OR old.record_count IS DISTINCT FROM (p->>'record_count')::integer OR old.metadata_hash IS DISTINCT FROM p->>'metadata_hash' THEN
      RAISE EXCEPTION 'snapshot conflict; use a new snapshot';
    END IF;
    SELECT count(*) INTO actual_count FROM scriptura_d2_stage.records WHERE snapshot_id=p->>'snapshot_id';
    SELECT count(*) INTO mismatch_count FROM jsonb_to_recordset(p->'records') AS x(record_type text,record_id text,origin_file text,row_number integer,origin_file_sha256 text,original_sha256 text,disposition text,reasons jsonb,validation_status text,rights_action text,rights_decision text,rights_edition_id text)
    LEFT JOIN scriptura_d2_stage.records r ON r.snapshot_id=p->>'snapshot_id' AND r.record_type=x.record_type AND r.record_id=x.record_id
    WHERE r.record_id IS NULL OR r.origin_file IS DISTINCT FROM x.origin_file OR r.row_number IS DISTINCT FROM x.row_number
      OR r.origin_file_sha256 IS DISTINCT FROM x.origin_file_sha256 OR r.original_sha256 IS DISTINCT FROM x.original_sha256
      OR r.disposition IS DISTINCT FROM x.disposition OR to_jsonb(r.reasons) IS DISTINCT FROM x.reasons
      OR r.validation_status IS DISTINCT FROM x.validation_status OR r.rights_action IS DISTINCT FROM x.rights_action
      OR r.rights_decision IS DISTINCT FROM x.rights_decision OR r.rights_edition_id IS DISTINCT FROM x.rights_edition_id;
    IF actual_count <> (p->>'record_count')::integer OR mismatch_count <> 0 THEN RAISE EXCEPTION 'snapshot provenance conflict'; END IF;
  ELSE
    INSERT INTO scriptura_d2_stage.snapshots(snapshot_id,archive_sha256,origin_zip,record_count,metadata_hash)
      VALUES (p->>'snapshot_id',p->>'archive_sha256',p->>'origin_zip',(p->>'record_count')::integer,p->>'metadata_hash');
    INSERT INTO scriptura_d2_stage.records(snapshot_id,record_type,record_id,origin_file,row_number,origin_file_sha256,original_sha256,disposition,reasons,validation_status,rights_action,rights_decision,rights_edition_id)
    SELECT p->>'snapshot_id',x.record_type,x.record_id,x.origin_file,x.row_number,x.origin_file_sha256,x.original_sha256,x.disposition,
      ARRAY(SELECT jsonb_array_elements_text(x.reasons)),x.validation_status,x.rights_action,x.rights_decision,x.rights_edition_id
    FROM jsonb_to_recordset(p->'records') AS x(record_type text,record_id text,origin_file text,row_number integer,origin_file_sha256 text,original_sha256 text,disposition text,reasons jsonb,validation_status text,rights_action text,rights_decision text,rights_edition_id text);
  END IF;
END $load$;
COMMIT;
'''


def stage_synthetic(archive_path, *, expected_sha256, expected_counts, expected_snapshot, env=None, psql_bin=None):
    """Stage only trusted, generated synthetic input into a restricted temporary DB.

    Returns aggregate counts only. This internal API requires caller-generated
    test pins and is not a general-purpose ZIP loader or production importer.
    """
    env = dict(os.environ if env is None else env)
    config = _connection(env)  # Check guards before opening files or contacting DB.
    if not isinstance(expected_snapshot,str) or not SNAPSHOT_PATTERN.fullmatch(expected_snapshot) or expected_snapshot == EXPECTED_SNAPSHOT:
        raise StagingError('synthetic_snapshot_required')
    if not isinstance(expected_sha256,str) or not SHA_PATTERN.fullmatch(expected_sha256) or expected_sha256 in RESEARCH_ARCHIVE_SHA256:
        raise StagingError('synthetic_archive_required')
    try:
        path = Path(archive_path)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise StagingError('archive_too_large')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise StagingError('archive_sha256_mismatch')
        # The immutable private copy prevents races between hash/manifest reads.
        with tempfile.TemporaryDirectory(prefix='scriptura-synthetic-') as directory:
            copy = Path(directory) / 'synthetic.zip'
            copy.write_bytes(data)
            report, records = validate_archive(copy, expected_sha256=expected_sha256, expected_snapshot=expected_snapshot, expected_counts=expected_counts, allow_synthetic=True)
            if report.get('status') != 'pass': raise StagingError('archive_validation_failed')
            with zipfile.ZipFile(copy) as z:
                file_hashes = {f'd2/records_merged/{t}.jsonl':hashlib.sha256(z.read(f'd2/records_merged/{t}.jsonl')).hexdigest() for t in TABLES}
            payload = _safe_data(report, records, path.name, file_hashes)
    except StagingError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, KeyError):
        raise StagingError('synthetic_archive_unreadable') from None
    proc_env = {k:v for k,v in env.items() if not k.upper().startswith('PG')}
    proc_env.update({'PGHOST':('127.0.0.1' if config['host'] == 'localhost' else config['host']), 'PGPORT':str(config['port']), 'PGDATABASE':config['database'], 'PGUSER':config['username'], 'PGCONNECT_TIMEOUT':'5'})
    if config['password']: proc_env['PGPASSWORD'] = config['password']
    try:
        result = subprocess.run([psql_bin or 'psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1'], input=_sql(payload), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=proc_env, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise StagingError('staging_database_unavailable') from None
    # Never surface stderr or URLs; PostgreSQL diagnostics can contain data.
    if result.returncode != 0:
        raise StagingError('staging_transaction_rejected')
    return {'status':'staged_or_identical', 'snapshot':payload['snapshot_id'], 'archive_sha256':payload['archive_sha256'], 'record_count':payload['record_count'], 'canonical_promotion':False, 'payload_stored':False}
