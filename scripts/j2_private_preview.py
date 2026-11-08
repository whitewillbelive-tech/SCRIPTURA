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

from k1_bridge.candidate_archive import load_k1_archive as load_versioned_archive
from k11_bridge.metadata import FIELDS as VERIFIED_METADATA_FIELDS, PrivateMetadataCandidates, metadata_for_record
from k12_bridge.snapshot import load_authenticated_snapshot
from j2_bridge import candidate_readonly as candidate

WEB_ROOT = Path(__file__).resolve().parent / 'j2_web'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
FILTERS = {'community': 'tradition', 'researcher': 'researcher', 'corpus': 'passage_corpus', 'scheme': 'passage_scheme', 'reference': 'passage_reference', 'source_kind': 'source_kind', 'attribution': 'attribution', 'verification_status': 'verification_status', 'authority_status': 'authority_status', 'rights_status': 'rights_status', 'access_path': 'access_path', 'record_kind': 'record_kind', 'stage': 'stage'}
SEARCH_FIELDS = ('tradition', 'community_reference', 'evaluated_subject', 'researcher', 'speaker', 'passage_corpus', 'passage_scheme', 'passage_reference', 'source_title', 'source_creator', 'source_kind', 'attribution', 'verification_status', 'authority_status', 'rights_status', 'access_path', 'record_kind')
MAX_QUERY_LENGTH = 200
PAGE_SIZE = 100
RIGHTS_ACTIONS = frozenset(('browse', 'collect_metadata', 'store_raw', 'store_excerpt', 'index_fulltext', 'embed', 'send_to_model', 'redistribute', 'public_link'))
RIGHTS_DECISIONS = frozenset(('unknown', 'conditional', 'allowed', 'prohibited', 'not_recorded', 'conflicting', 'unmapped'))
SAFE_RECORD_FIELDS = frozenset(('key', 'stage', 'record_kind', 'category', 'attribution', 'original_attribution', 'authority_status', 'input_authority_status', 'verification_status', 'quotation_status', 'argument_status', 'reported_independent_review_status', 'independent_review_status', 'audit_observation_key', 'rights_status', 'tradition', 'community_reference', 'community_role', 'evaluated_subject', 'researcher', 'speaker', 'speaker_type', 'passage_corpus', 'passage_scheme', 'passage_reference', 'source_title', 'source_creator', 'source_kind', 'source_doi', 'source_year', 'access_path', 'locator', 'unmapped', 'checked_at', 'as_of', 'valid_from', 'valid_until', 'display_status'))
SAFE_STAGES = frozenset(('base', 'd5', 'd6', 'd7', 'd8', 'd9', 'd10'))
RESEARCH_DATASETS = frozenset(('D8', 'D9', 'D10'))
ALLOWED_DATASETS = RESEARCH_DATASETS | {'synthetic'}


def _stage_pattern(dataset, *, research=True):
    """Exact version boundary; unknown research versions never become synthetic."""
    if not research:
        return r'(?:base|d[5-9]|d10|synthetic)'
    return {'D8': r'(?:base|d[5-8])', 'D9': r'(?:base|d[5-9])',
            'D10': r'(?:base|d[5-9]|d10)'}.get(dataset, r'(?!)')


def _stage_allowed(stage, dataset):
    return isinstance(stage, str) and re.fullmatch(_stage_pattern(dataset), stage) is not None
SAFE_TABLES = frozenset(('sources', 'editions', 'locators', 'rights', 'passages', 'alignments', 'agents', 'affiliations', 'claims', 'evidence', 'relations', 'reviews', 'audit_conflicts', 'authority_documents', 'authority_registries', 'claim_scope_audits', 'cross_corpus_topics', 'interpretive_evidence', 'position_attestations', 'rights_delta', 'source_access_events', 'communities', 'assessments', 'relationships', 'authority', 'audit_reviews', 'correction_candidates', 'research_gaps', 'conflicts', 'institutional_assertions', 'rights_overrides', 'unresolved_gaps', 'authority_scope', 'review_queue', 'rights_actions', 'sample_manifest'))
SAFE_FIELD_NAMES = frozenset(('id', 'source_id', 'source_locator_id', 'locator_id', 'edition_id', 'source_title', 'source_creator', 'title', 'creator', 'speaker', 'community_id', 'community_id_role', 'claim_id', 'claim_ids', 'baseline_claim_id', 'baseline_record_id', 'baseline_target_id', 'target_community_id', 'authority_registry_id', 'authority_document_id', 'document_id', 'position_attestation_id', 'passage_ids', 'subject_id', 'object_id', 'source_locator_ids', 'evidence_locator_id', 'additional_evidence_locator_ids', 'baseline_edition_id', 'baseline_right_id', 'source_right_id', 'statement_ko', 'summary', 'note', 'notes', 'scope_note', 'rights_basis', 'action_specific_basis', 'jurisdiction', 'territory', 'limitations', 'url', 'doi', 'source_url', 'source_full_text', 'full_text', 'raw_text', 'full_text_url', 'original_content_stored', 'raw_text_stored', 'reference', 'reference_scheme', 'alignment_status', 'reviewer', 'checked_at', 'reviewed_at', 'verification_status', 'source_verification', 'previous_verification_status', 'status', 'decision', 'source_chain', 'source_metadata', 'rights_scope', 'formal_adoption_evidence', 'independent_human_review', 'unreviewed_source_text', 'position_scope', 'claim_statement', 'unrecognized_field', 'unmapped'))
SAFE_STATUS_CODES = frozenset(('unknown', 'unmapped', 'pending', 'none', 'not_done', 'not_recorded', 'not_assessed', 'unverified', 'verified', 'checked', 'source_checked', 'source_verified', 'scholarly_reviewed', 'direct_checked', 'translation_checked', 'secondary_report', 'search_only', 'unchecked', 'adoption_documented', 'issuer_documented', 'historical_only', 'individual_only', 'disputed', 'documented_argument', 'externally_challenged', 'cross_checked', 'contested', 'human_review_documented', 'published_critique_documented', 'independent_review_not_done', 'pending_authority', 'pending_academic', 'pending_language_review', 'redacted_rights_unresolved', 'candidate', 'candidate_source', 'metadata_candidate', 'not_performed', 'not_reviewed', 'source_checked_secondary_transmission', 'collaborator_checked_not_self_checked', 'direct_full_text_section_checked', 'ongoing', 'not_applicable', 'multiple_editions', 'conditional', 'allowed', 'prohibited', 'conflicting', 'recorded', 'missing', 'active', 'historical', 'proposed', 'draft', 'not_verified', 'translation_only', 'ai_translation_pending'))
SAFE_ATTRIBUTIONS = frozenset(('unknown', 'unmapped', 'unconfirmed_authority', 'community_self_explanation', 'individual_opinion', 'academic_interpretation', 'external_critique', 'official_doctrine', 'scriptural_narrative', 'textual_narrative'))
SAFE_SOURCE_KINDS = frozenset(('unknown', 'unmapped', 'book', 'journal_article', 'article', 'academic_article', 'research_article', 'thesis', 'dissertation', 'monograph', 'commentary', 'academic_book', 'reference_work', 'webpage', 'website', 'official_website', 'official_statement', 'institutional_publication', 'institutional_document', 'institutional_report', 'institutional_statement', 'institutional_explanation', 'religious_text', 'confession', 'catechism', 'doctrinal_document', 'primary_source', 'secondary_source', 'scholarly_publication', 'press_report', 'news_report', 'report', 'interview', 'video', 'lecture', 'archive', 'encyclopedia', 'synthetic'))
SAFE_METHOD_CODES = frozenset(('unknown', 'unmapped', 'direct', 'direct_checked', 'translation', 'translation_checked', 'secondary', 'secondary_report', 'search', 'search_only', 'web_page', 'website', 'web_text', 'web_extract', 'web_extracted_text', 'direct_web', 'pdf', 'pdf_page', 'abstract', 'abstract_only', 'external_summary', 'blocked', 'not_accessed', 'collaborator', 'collaborator_checked_not_self_checked', 'ai_translation_pending', 'unverified', 'pending'))
SAFE_EVIDENCE_KINDS = frozenset(('unknown', 'unmapped', 'support', 'contradiction', 'context', 'primary', 'secondary', 'source', 'citation', 'bibliographic', 'textual', 'linguistic', 'historical', 'academic', 'scripture', 'translation', 'direct', 'quotation', 'source_support', 'claim_support', 'interpretive_evidence', 'source_evidence', 'contextual', 'evidence', 'counterargument', 'refutation', 'comparison', 'synthetic_evidence'))
SAFE_RELATION_KINDS = frozenset(('unknown', 'unmapped', 'support', 'contradict', 'contradicts', 'contrast', 'qualifies', 'rebuts', 'directly_rebuts', 'related_topic', 'later_institutional_report_relevant_to', 'criticizes_community_position', 'contrasting_interpretation_on_shared_text', 'same_passage_other_research', 'interpretive_contrast_candidate', 'response_to_specific_assessment_candidate', 'similar_topic_and_conclusion_to', 'external_institutional_assessment_of', 'community_context_from', 'documented_in_reported_community_interview', 'reports_process_about', 'critiques_personal_lectures_of', 'shares_topic_with_later_material', 'possible_related_criticism', 'same_passage_research_not_direct_rebuttal', 'possible_same_topic_criticism', 'academic_secondary_interpretation_of', 'shares_1950_edition_critique_topic', 'critiques_group_argument_related_to', 'related_criticism_on_same_passage', 'academic_analysis_of', 'evaluates_book_treatment'))
SAFE_RELATION_KINDS = SAFE_RELATION_KINDS | frozenset(('same_community_similar_interpretation', 'published_review_criticizes_book_treatment', 'bibliographic_record_describes'))
SAFE_SCOPES = frozenset(('unknown', 'unmapped', 'individual', 'individual_opinion', 'community', 'institutional', 'official', 'historical', 'external', 'academic', 'specific_group', 'local', 'regional', 'global', 'plural', 'pending', 'self_explanation', 'individual_only', 'not_applicable'))
SAFE_STATUS_CODES = SAFE_STATUS_CODES | frozenset(('verified_exact', 'partially_verified', 'metadata_checked', 'direct_published_source_rechecked', 'translation_checked_human_review_pending', 'rendered_content_checked_adoption_unknown', 'source_label_checked_legal_event_ambiguous', 'direct_rendered_browser_checked', 'review_scan_checked_book_unseen'))
def _safe_visibility(value, *, dataset=None):
    """Only fixed aggregate counts; input reports never authorize display."""
    if dataset == 'D8' or not isinstance(value, dict):
        return {}
    permitted = ('metadata_candidate', 'candidate_visible_local', 'unknown', 'unmapped', 'total')
    result = {key: count for key in permitted
            if isinstance((count := value.get(key)), int) and not isinstance(count, bool)
            and 0 <= count <= 100000}
    # Current D9's pinned input has 9 metadata candidates and no approved
    # candidate-visible fields. Input counters never authorize display.
    if dataset == 'D9' and result and (result.get('metadata_candidate') != 9 or result.get('candidate_visible_local') != 0):
        return {'status': 'pending_inconsistent'}
    if dataset == 'D10' and result:
        # The source ledger calls one row candidate_visible_local, but the
        # contract says this is conditional, not an operational approval.
        # Do not let a supplied counter authorize a real field.
        conditional = result.get('candidate_visible_local')
        if conditional != 1:
            return {'status': 'pending_inconsistent'}
        result['conditional_candidate'] = conditional
        result['candidate_visible_local'] = 0
    return result


def _safe_counts(value, *, dataset):
    """No arbitrary keys, free text or D9 counts in a D8 session."""
    if not isinstance(value, dict):
        return {}
    result = {}
    count = value.get('display_records')
    if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 100000:
        result['display_records'] = count
    for stage in ('d8', 'd9', 'd10'):
        if not _stage_allowed(stage, dataset):
            continue
        tables = value.get(stage)
        if isinstance(tables, dict):
            result[stage] = {key: n for key, n in tables.items() if key in SAFE_TABLES
                             and isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 100000}
    by_stage = value.get('by_stage')
    if isinstance(by_stage, dict):
        safe = {}
        for stage, tables in by_stage.items():
            if not _stage_allowed(stage, dataset) or not isinstance(tables, dict):
                continue
            safe[stage] = {key: n for key, n in tables.items() if key in SAFE_TABLES
                           and isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 100000}
        result['by_stage'] = safe
    return result


def _safe_unmapped(value, *, dataset=None):
    """Only table names, mapping enum, and counts; never source text or IDs."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for stage, tables in value.items():
        if (stage not in SAFE_STAGES if dataset in (None, 'synthetic') else not _stage_allowed(stage, dataset)) or not isinstance(tables, dict):
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


def _safe_d10_receipt(value, *, dataset):
    """D10 quarantine is reported only as bounded fixed-name counts."""
    if dataset != 'D10' or not isinstance(value, dict):
        return {}
    result = {}
    for key in ('source_count', 'quarantined_source_count', 'conditional_candidate_count', 'effective_visible_fields'):
        count = value.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 100000:
            result[key] = count
    if result.get('effective_visible_fields') != 0:
        return {'status': 'pending_inconsistent'}
    fixed_duplicates = {prefix + field for prefix in ('cross_', 'within_') for field in ('id', 'title', 'doi', 'url')}
    fixed_links = {table + '_' + field + '_' + suffix
                   for table, field in (('editions', 'source_id'), ('locators', 'edition_id'), ('locators', 'source_id'), ('rights', 'edition_id'))
                   for suffix in ('present', 'resolved')}
    for section, names in (('duplicate_counts', fixed_duplicates), ('linkage_counts', fixed_links)):
        items = value.get(section)
        if isinstance(items, dict):
            result[section] = {key: count for key, count in items.items() if key in names
                               and isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 100000}
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


def _safe_day(value, *, allow_year=False):
    if not isinstance(value, str):
        return None
    if allow_year and re.fullmatch(r'[0-9]{4}', value) and value != '0000':
        return value
    try:
        return value if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) and dt.date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def _safe_eligibility(value, *, research):
    """Report recorded field status; it is never a content-display grant."""
    if not isinstance(value, dict):
        return {}
    result = {}
    groups = ('bibliography', 'own_summary', 'short_quote', 'full_text', 'private_link')
    statuses = ('metadata_candidate', 'unknown', 'unmapped', 'redacted_rights_unresolved')
    if not research:
        statuses += ('candidate_visible_local',)
    for entity in ('source', 'claim', 'edition', 'locator'):
        entries = value.get(entity)
        if isinstance(entries, dict):
            result[entity] = {group: (entries[group] if entries[group] in statuses else 'unmapped')
                              for group in groups if isinstance(entries.get(group), str)}
    return result


def _safe_d9_observations(row, *, dataset):
    """Only fixed observations, with no text, ID, URL, or automatic grant."""
    if dataset not in ('D9', 'D10', 'synthetic'):
        return [], []
    observed, rights = [], []
    for item in row.get('d9_observations', []) if isinstance(row.get('d9_observations'), list) else []:
        if not isinstance(item, dict) or item.get('kind') not in ('audit_review', 'review_queue', 'evidence', 'relationship'):
            continue
        target = item.get('target_key')
        observed.append({'kind': item['kind'],
                         'status': item.get('status') if item.get('status') in SAFE_STATUS_CODES else 'unmapped',
                         'method': item.get('method') if item.get('method') in SAFE_METHOD_CODES else 'unmapped',
                         'direction': item.get('direction') if item.get('direction') in ('incoming', 'outgoing') else 'unknown',
                         'relation_type': item.get('relation_type') if item.get('kind') == 'relationship' and item.get('relation_type') in SAFE_RELATION_KINDS else 'unmapped',
                         'target_key': target if isinstance(target, str) and re.fullmatch(_stage_pattern(dataset, research=dataset != 'synthetic') + r':(?:claims|sources):[1-9][0-9]*', target) else None})
    for item in row.get('d9_rights_observations', []) if isinstance(row.get('d9_rights_observations'), list) else []:
        if not isinstance(item, dict) or item.get('action') not in RIGHTS_ACTIONS:
            continue
        edition = item.get('edition_key')
        rights.append({'edition_key': edition if isinstance(edition, str) and re.fullmatch(_stage_pattern(dataset, research=dataset != 'synthetic') + r':editions:[1-9][0-9]*', edition) else None,
                       'action': item['action'], 'decision': item.get('decision') if item.get('decision') in RIGHTS_DECISIONS else 'unmapped'})
    return observed, rights


def _safe_record(row, *, research=False, dataset=None):
    """Defense-in-depth projection: never forward arbitrary source fields."""
    result = {key: value for key, value in row.items() if key in SAFE_RECORD_FIELDS and (value is None or isinstance(value, (str, int, float)))}
    unmapped = row.get('unmapped', [])
    result['unmapped'] = [value for value in unmapped if isinstance(value, str)] if isinstance(unmapped, list) else []
    if research:
        # Schema names are a fixed public vocabulary; a crafted ASCII field
        # must not become a channel for hidden identifiers or source text.
        safe_names = [name for name in result['unmapped'] if name in SAFE_FIELD_NAMES]
        if any(name not in SAFE_FIELD_NAMES for name in result['unmapped']):
            safe_names.append('unrecognized_field')
        result['unmapped'] = sorted(set(safe_names))
    if research:
        # Format checks alone do not establish field-specific display rights
        # or privacy suitability. Keep such fields out of response and search.
        for key in ('source_title', 'source_creator', 'researcher', 'speaker', 'tradition', 'community_reference', 'evaluated_subject'):
            result[key] = None
        table = {'claim': 'claims', 'source': 'sources'}.get(row.get('record_kind'))
        key = row.get('key')
        stages = _stage_pattern(dataset)
        stage = str(row.get('stage') or '').lower()
        if not _stage_allowed(stage, dataset):
            result['stage'] = 'unmapped'
        if table is None:
            result['record_kind'] = 'unmapped'
        if table is None or not isinstance(key, str) or not re.fullmatch(rf'{stages}:{table}:[1-9][0-9]*', key) or key.split(':', 1)[0] != stage:
            result['key'] = None
        # No field review from an input record or an HTTP request can authorize
        # actual display. Future reviewed permissions require a separate gate.
        result['display_status'] = 'redacted_rights_unresolved' if stage in ('d9', 'd10') else 'metadata_candidate'
        result['authority_status'] = 'pending_authority'
        if result.get('attribution') == 'official_doctrine':
            result['attribution'] = 'unconfirmed_authority'
        if result.get('independent_review_status') not in ('pending', 'independent_review_not_done'):
            result['independent_review_status'] = 'pending'
    # Only immutable input coordinates can link records. A raw source ID,
    # wrong table, URL or arbitrary string is never returned as a target.
    for field, table in (('source_key', 'sources'), ('edition_key', 'editions'), ('locator_key', 'locators')):
        value = row.get(field)
        stages = _stage_pattern(dataset, research=research)
        pattern = rf'{stages}:{table}:[1-9][0-9]*'
        result[field] = value if isinstance(value, str) and re.fullmatch(pattern, value) else None
    # Direct quotation and free-form claim text are not authorized in this gate.
    result['summary'] = None
    result['rights'] = _rights_map(row.get('rights'))
    result['effective_permissions'] = {a: False for a in sorted(RIGHTS_ACTIONS)}
    result['rights_overrides'] = _rights_overrides(row.get('rights_overrides'))
    editions = row.get('edition_rights', [])
    result['edition_rights'] = [
        {'key': item.get('key') if isinstance(item.get('key'), str) and re.fullmatch(_stage_pattern(dataset, research=research) + r':editions:[1-9][0-9]*', item['key']) else None,
         'rights': _rights_map(item.get('rights')),
         'rights_overrides': _rights_overrides(item.get('rights_overrides')),
         'effective_permissions': {a: False for a in sorted(RIGHTS_ACTIONS)}}
        for item in editions if isinstance(item, dict)
    ] if isinstance(editions, list) else []
    policy = row.get('field_policy', {})
    if isinstance(policy, dict):
        result['field_policy'] = {key: value for key, value in policy.items() if key in ('source_metadata', 'summary', 'locator') and value in ('metadata_candidate', 'candidate_visible_local', 'redacted_rights_unresolved', 'structured_identifier_only', 'unmapped')}
        if research:
            result['field_policy'] = {key: ('redacted_rights_unresolved' if value == 'candidate_visible_local' else value) for key, value in result['field_policy'].items()}
    passages = row.get('passages', [])
    if isinstance(passages, list):
        result['passages'] = [{key: p.get(key) for key in ('corpus', 'scheme', 'reference') if isinstance(p.get(key), str) or p.get(key) is None} for p in passages if isinstance(p, dict)]
    for key, fields in (('evidence', ('kind', 'status')), ('relationships', ('kind', 'status', 'direction', 'target_key', 'assessment')), ('attestation_observations', ('scope', 'verification_status', 'as_of')), ('access_events', ('method', 'result', 'checked_at'))):
        items = row.get(key, [])
        result[key] = [{field: item.get(field) for field in fields if item.get(field) is None or isinstance(item.get(field), str)} for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    if research:
        for field in ('verification_status', 'quotation_status', 'argument_status', 'reported_independent_review_status', 'input_authority_status', 'rights_status'):
            if field in result and result[field] not in SAFE_STATUS_CODES:
                result[field] = 'unmapped'
        for field in ('attribution', 'original_attribution'):
            if field in result and result[field] not in SAFE_ATTRIBUTIONS:
                result[field] = 'unmapped'
        if result.get('source_kind') not in SAFE_SOURCE_KINDS:
            result['source_kind'] = 'unmapped'
        if result.get('access_path') not in SAFE_METHOD_CODES:
            result['access_path'] = 'unmapped'
        result['category'] = None
        result['speaker_type'] = 'unknown'
        if result.get('community_role') not in ('self', 'target', 'unspecified'):
            result['community_role'] = 'unspecified'
        for field in ('checked_at', 'as_of', 'valid_from', 'valid_until'):
            result[field] = _safe_day(result.get(field))
        # A formatted DOI or date can identify an unapproved bibliography.
        # The D9 contract requires a separate field-level display decision.
        result['source_year'] = None
        result['source_doi'] = None
        result['locator'] = None
        audit_key = result.get('audit_observation_key')
        if not isinstance(audit_key, str) or not re.fullmatch(r'd5:claim_scope_audits:[1-9][0-9]*', audit_key):
            result['audit_observation_key'] = None
        safe_passages = []
        reverse_schemes = {value: key for key, value in candidate._SCHEMES.items()}
        for passage in result.get('passages', []):
            corpus = passage.get('corpus')
            scheme = passage.get('scheme')
            if corpus not in candidate._CORPORA.values() or scheme not in reverse_schemes:
                continue
            reference = candidate._reference(passage.get('reference'), corpus, reverse_schemes[scheme])
            safe_passages.append({'corpus': corpus, 'scheme': scheme, 'reference': reference})
        result['passages'] = safe_passages
        first = safe_passages[0] if safe_passages else {}
        result['passage_corpus'] = first.get('corpus')
        result['passage_scheme'] = first.get('scheme')
        result['passage_reference'] = first.get('reference')
        for item in result['evidence']:
            if item.get('kind') not in SAFE_EVIDENCE_KINDS: item['kind'] = 'unmapped'
            if item.get('status') not in SAFE_STATUS_CODES: item['status'] = 'unmapped'
        for item in result['relationships']:
            if item.get('kind') not in SAFE_RELATION_KINDS: item['kind'] = 'unmapped'
            if item.get('status') not in SAFE_STATUS_CODES: item['status'] = 'unmapped'
            if item.get('assessment') not in ('pending_evidence_review', 'pending', 'unmapped'): item['assessment'] = 'unmapped'
            if item.get('direction') not in ('incoming', 'outgoing'): item['direction'] = 'unknown'
            key = item.get('target_key')
            stages = _stage_pattern(dataset)
            if not isinstance(key, str) or not re.fullmatch(stages + r':(?:claims|sources):[1-9][0-9]*', key):
                item['target_key'] = None
        for item in result['attestation_observations']:
            if item.get('scope') not in SAFE_SCOPES: item['scope'] = 'unmapped'
            if item.get('verification_status') not in SAFE_STATUS_CODES: item['verification_status'] = 'unmapped'
            item['as_of'] = _safe_day(item.get('as_of'))
        for item in result['access_events']:
            if item.get('method') not in SAFE_METHOD_CODES: item['method'] = 'unmapped'
            if item.get('result') not in SAFE_STATUS_CODES: item['result'] = 'unmapped'
            item['checked_at'] = _safe_day(item.get('checked_at'))
    result['field_eligibility'] = _safe_eligibility(row.get('field_eligibility'), research=research) if dataset != 'D8' else {}
    result['d9_observations'], result['d9_rights_observations'] = _safe_d9_observations(row, dataset=dataset)
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


def attach_local_public_snapshot(dataset, snapshot_id, path, *, today=None):
    """Attach an independently reviewed fixed snapshot from a local file only.

    No snapshot is currently registered, so real inputs fail closed. The file
    is never sent to an external service and its path/content never enters API
    output or diagnostics. The approved static provider policy must cover the
    exact snapshot digest, source provenance, metadata use and privacy.
    """
    try:
        candidates = dataset.get('_private_metadata_candidates') if isinstance(dataset, dict) else None
        if type(candidates) is not PrivateMetadataCandidates or not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError('public_snapshot_untrusted')
        location = local_archive_path(path)
        with location.open('rb') as handle:
            content = handle.read(32 * 1024 * 1024 + 1)
        snapshot = load_authenticated_snapshot(snapshot_id, content, today=today or dt.date.today().isoformat())
        return candidates.attach_public_snapshot(dataset, snapshot)
    except Exception:
        raise ValueError('public_snapshot_untrusted') from None


def filter_records(dataset, params):
    """Search the pre-redacted projection only; unknown temporal scope stays pending."""
    if not isinstance(dataset, dict) or dataset.get('dataset') not in ALLOWED_DATASETS or not isinstance(dataset.get('records'), list):
        raise ValueError('invalid dataset')
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
    mode = dataset.get('dataset')
    # This object can only be supplied by trusted in-process verification code;
    # JSON records and recorded status flags are never treated as grants.
    metadata_index = dataset.get('_verified_metadata_index')
    metadata_coverage = {field: 0 for field in sorted(VERIFIED_METADATA_FIELDS)}
    for original in dataset['records']:
        # D8 mode must not include newer D9 records, even if the dataset is
        # accidentally assembled from mixed snapshots.
        if mode in RESEARCH_DATASETS and not _stage_allowed(str(original.get('stage') or '').lower(), mode):
            continue
        row = _safe_record(original, research=mode in RESEARCH_DATASETS, dataset=mode)
        row['verified_metadata'] = metadata_for_record(metadata_index, mode, row.get('key'))
        # A claim's verification/review label is not evidence that any source
        # bibliography has been independently verified.
        bibliographic_fields = {'source_title', 'source_creator', 'source_publisher', 'source_year'}
        row['source_verification_status'] = 'verified_fields_only' if bibliographic_fields.intersection(row['verified_metadata']) else 'unconfirmed'
        for field in row['verified_metadata']:
            if field in metadata_coverage:
                metadata_coverage[field] += 1
        if q.get('key') and row.get('key') != q['key']:
            continue
        if search and not (any(search in _text(row.get(key)) for key in SEARCH_FIELDS) or any(search in _text(value) for value in row['verified_metadata'].values()) or any(search in _text(p.get(field)) for p in row.get('passages', []) for field in ('corpus', 'scheme', 'reference'))):
            continue
        community = q.get('community', '').casefold()
        if community and not (any(community in _text(row.get(key)) for key in ('tradition', 'community_reference', 'evaluated_subject')) or community in _text(row['verified_metadata'].get('community_name'))):
            continue
        researcher = q.get('researcher', '').casefold()
        if researcher and not (any(researcher in _text(row.get(key)) for key in ('researcher', 'speaker', 'source_creator')) or researcher in _text(row['verified_metadata'].get('source_creator'))):
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
            edition_keys = {group.get('key') for group in rights_groups} if row['record_kind'] == 'source' else {row.get('edition_key')}
            observations += [(item['action'], item['decision']) for item in row['d9_rights_observations'] if item['edition_key'] is not None and item['edition_key'] in edition_keys]
            if not any((not action or name == action) and (not decision or value == decision) for name, value in observations):
                continue
        for collection, predicates in (('evidence', {'kind': q.get('evidence_kind', ''), 'status': q.get('evidence_status', '')}), ('relationships', {'kind': q.get('relation_kind', ''), 'status': q.get('relation_status', ''), 'direction': q.get('relation_direction', '')})):
            items = list(row[collection])
            for event in row['d9_observations']:
                if collection == 'evidence' and event['kind'] == 'evidence':
                    items.append({'kind': 'evidence', 'status': event['status']})
                elif collection == 'relationships' and event['kind'] == 'relationship':
                    items.append({'kind': event['relation_type'], 'status': event['status'], 'direction': event['direction']})
            if any(predicates.values()) and not any(all(not term or term.casefold() == _text(item.get(key)) for key, term in predicates.items()) for item in items):
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
    research = mode in RESEARCH_DATASETS
    counts = _safe_counts(dataset.get('counts'), dataset=mode) if research else dataset['counts']
    if mode in RESEARCH_DATASETS and 'display_records' in counts:
        counts['display_records'] = sum(1 for row in dataset['records'] if _stage_allowed(str(row.get('stage') or '').lower(), mode))
    return {'dataset': dataset['dataset'],
            'metadata_projection': 'k1.1-verified',
            'metadata_coverage': metadata_coverage,
            'counts': counts,
            'warnings': ['비공개 연구 후보이며 표시·권리·공식성은 별도 확인이 필요합니다.'] if research else dataset['warnings'],
            'facets': {} if research else dataset.get('facets', {}),
            'visibility_summary': _safe_visibility(dataset.get('visibility_summary'), dataset=mode),
            'd10_receipt': _safe_d10_receipt(dataset.get('d10_receipt'), dataset=mode),
            'unmapped_summary': _safe_unmapped(dataset.get('unmapped_summary'), dataset=mode),
            'total': len(found), 'offset': offset, 'page_size': PAGE_SIZE, 'records': found[offset:offset + PAGE_SIZE]}


class PrivatePreviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, data, secret, port=0):
        if not isinstance(secret, str) or len(secret) < 20 or not secret.strip() or len(secret.encode('utf-8')) > 256 or any(ord(c) < 32 or ord(c) > 126 for c in secret):
            raise ValueError('세션 비밀은 출력 가능한 ASCII 문자 20자 이상이어야 합니다.')
        if not isinstance(data, dict) or not isinstance(data.get('records'), list) or data.get('dataset') not in ALLOWED_DATASETS:
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
    parser.add_argument('--archive', required=True, help='고정 D-8, D-9 또는 D-10 ZIP 파일')
    parser.add_argument('--public-snapshot', help='검토된 고정 공개 서지 스냅샷의 로컬 파일')
    parser.add_argument('--public-snapshot-id', help='코드에 등록된 스냅샷 정책 이름')
    args = parser.parse_args(argv)
    try:
        archive = local_archive_path(args.archive)
        dataset = load_versioned_archive(archive)
        if bool(args.public_snapshot) != bool(args.public_snapshot_id):
            raise ValueError('public_snapshot_untrusted')
        if args.public_snapshot:
            dataset = attach_local_public_snapshot(dataset, args.public_snapshot_id, args.public_snapshot)
    except Exception:
        print('고정 D-8/D-9/D-10 자료를 확인할 수 없습니다. 경로와 무결성을 확인하세요.', file=sys.stderr)
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
