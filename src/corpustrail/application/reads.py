"""Read-only researcher-facing operational DTOs, deliberately not review packets.

No writes, persistent cache, plugin loading or network access. Every request uses
one SQLite read snapshot. Cursor revisions reject changes rather than mixing pages.
"""

import base64
import json
import re

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.pipeline import events_in_connection, artifact_in_connection
from corpustrail._internal.values import ContractError, content_hash
from corpustrail.curation.service import membership_in_connection
from ._catalogue import catalogue_sql, filter_sql, SORTS

SCHEMA = 'corpustrail-operational-reads/v1'
MEMBERSHIP = {'included', 'excluded', 'insufficient_evidence', 'unresolved', 'not_reviewed'}
EVIDENCE = {'metadata', 'abstract', 'structured_text', 'pending', 'mismatch_or_invalid'}
REVIEW = {'human_reviewed', 'not_human_reviewed', 'draft_history'}


class StaleCursor(ContractError):
    """A live view changed; restart pagination, never silently mix snapshots."""


def _handle(paper_id):
    if not re.fullmatch(r'ct-paper:[0-9a-f]{64}', paper_id):
        raise ContractError('unsupported paper identifier')
    return paper_id.split(':', 1)[1]


def _paper_id(handle):
    if not isinstance(handle, str) or not re.fullmatch(r'[0-9a-f]{64}', handle):
        raise ContractError('invalid paper link')
    return 'ct-paper:' + handle


def _revision(db):
    config_id, raw = latest_config(db)
    sizes = [tuple(db.execute(sql).fetchone()) for sql in (
        'SELECT COUNT(*) FROM paper_entities',
        'SELECT COUNT(*) FROM paper_identifiers',
        'SELECT COUNT(*) FROM ct_paper_observations',
        'SELECT COALESCE(MAX(sequence),0) FROM ct_pipeline_events',
        'SELECT COALESCE(MAX(sequence),0) FROM ct_review_events',
        'SELECT COUNT(*) FROM ct_review_sessions',
        'SELECT COALESCE(MAX(sequence),0) FROM ct_review_session_events',
    )]
    return content_hash([raw['project_id'], config_id, sizes])


def _page(cursor, revision, options):
    if cursor is None:
        return 0
    try:
        if not isinstance(cursor, str) or len(cursor) > 2048:
            raise ValueError()
        obj = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
        if set(obj) != {'revision', 'options', 'offset'} or obj['options'] != options:
            raise ValueError()
        offset = obj['offset']
        if type(offset) is not int or not 0 <= offset <= 10**12:
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ContractError('invalid pagination cursor; restart the list') from exc
    if obj['revision'] != revision:
        raise StaleCursor('Project changed. Refresh the list to restart pagination.')
    return offset


def _cursor(offset, revision, options):
    return base64.urlsafe_b64encode(json.dumps(
        {'offset': offset, 'revision': revision, 'options': options},
        separators=(',', ':')).encode()).decode()


def _sources(db, pid):
    # Producer IDs only, no queries, endpoints, raw response or private source paths.
    rows = db.execute("SELECT DISTINCT json_extract(payload_json,'$.source.producer_id') "
                      'FROM ct_paper_observations WHERE paper_id=? ORDER BY 1', (pid,))
    return [row[0] for row in rows]


def _review(db, pid):
    counts = db.execute("SELECT COALESCE(SUM(producer_type='human'),0),"
                        "COALESCE(SUM(producer_type!='human'),0) FROM ct_review_events WHERE paper_id=?", (pid,)).fetchone()
    drafts = db.execute("SELECT COUNT(DISTINCT e.session_id) FROM ct_review_session_events e,"
        "json_each(COALESCE(json_extract(e.payload_json,'$.delta.drafts'),"
        "json_extract(e.payload_json,'$.state.drafts'),'{}')) j WHERE j.key=?", (pid,)).fetchone()[0]
    return {'human_observations': counts[0], 'other_observations': counts[1],
            'sessions_with_draft_history': drafts,
            'status': 'human_reviewed' if counts[0] else ('draft_history' if drafts else 'not_human_reviewed'),
            'notice': 'Draft history and non-authoritative observations do not establish corpus membership.'}


class ProjectReads:
    """Operational-only read boundary. Never use these DTOs for blinded review."""

    def __init__(self, project):
        self.project = project

    def _row(self, db, pid, *, detail=False):
        metadata = self.project.discovery._metadata(db, pid)
        membership = membership_in_connection(db, pid)
        reps = events_in_connection(db, kind='representation', paper_id=pid)
        evidence = self.project.evidence._status(metadata, reps)
        fields = metadata['fields']
        result = {'handle': _handle(pid),
            'bibliography': {key: fields[key] for key in ('title', 'authors', 'year', 'source')},
            # Provider keys remain preserved on the explicit advanced surface.
            'identifiers': [x for x in metadata['identifiers'] if x['scheme'] in {'doi', 'pmid', 'pmcid'}],
            'membership': {key: membership[key] for key in ('state', 'authority_state')},
            'review': _review(db, pid),
            'evidence': {key: evidence[key] for key in (
                'best_available', 'abstract_available', 'verified_structured_text',
                'pending_identity', 'mismatch_or_invalid')},
            'sources': _sources(db, pid)}
        if detail:
            result['abstract'] = fields['abstract']
            result['representations'] = [{
                'handle': x['event_id'].split(':', 1)[1],
                'kind': x['payload']['representation'],
                'validity': x['payload']['artifact_validity'],
                'trusted': x['payload']['trusted'],
                'document_body': x['payload'].get('evidence_depth') == 'document_body',
                'readable': (x['payload']['trusted'] and x['payload']['artifact_validity'] == 'verified'
                    and x['payload']['representation'] == 'structured_text'
                    and x['payload'].get('evidence_depth') == 'document_body')}
                for x in reps]
            result['notices'] = [
                'Missing evidence never implies exclusion.',
                'Pending, mismatched and invalid documents are not trusted evidence.',
                'This browser is read-only. Review and corpus decisions are not changed.']
        return result

    def dashboard(self):
        with connection(self.project.database_path) as db:
            _, config = latest_config(db)
            sql = catalogue_sql()
            membership = dict(db.execute(sql + 'SELECT membership,COUNT(*) FROM catalogue GROUP BY membership'))
            states = {state: membership.get(state, 0) for state in sorted(MEMBERSHIP)}
            counts = db.execute(sql + "SELECT COUNT(*),COALESCE(SUM(abstract_available),0),"
                "COALESCE(SUM(evidence='structured_text'),0),COALESCE(SUM(pending>0),0),"
                "COALESCE(SUM(invalid>0),0),COALESCE(SUM(human_count>0),0),"
                'COALESCE(SUM(draft_sessions>0),0) FROM catalogue').fetchone()
            sessions = db.execute('SELECT COUNT(*) FROM ct_review_sessions').fetchone()[0]
            updates = db.execute('SELECT COUNT(*) FROM ct_review_session_events').fetchone()[0]
            issues = db.execute("SELECT COUNT(DISTINCT scope_id) FROM ct_pipeline_events WHERE kind='identity_issue'").fetchone()[0]
            return {'schema': SCHEMA, 'mode': 'operational_read_only', 'revision': _revision(db),
                'project': {'name': config['name'], 'description': config['description'],
                    'broad_corpus_definition': config['review'].get('scope') or config['description'],
                    'definition_origin': 'review_scope' if config['review'].get('scope') else 'project_description'},
                'papers': counts[0], 'membership': states,
                'review': {'human_reviewed_papers': counts[5], 'papers_with_draft_history': counts[6],
                    'published_corpus_decisions': counts[0] - states['not_reviewed'],
                    'sessions': sessions, 'session_updates': updates,
                    'notice': 'Draft history is not a recorded decision. Session completion is not inferred.'},
                'evidence': {'abstract_available_papers': counts[1], 'verified_structured_text_papers': counts[2],
                    'pending_document_papers': counts[3], 'mismatch_or_invalid_papers': counts[4]},
                'identity_issues': {'recorded_observations_with_issues': issues,
                    'notice': 'Historical recorded warnings, not a claim that each is currently unresolved.'},
                'providers': [x['provider_id'] for x in config['providers']],
                'resolvers': config['evidence']['resolvers'],
                'notice': 'Read-only operational browser; not a method-blind review or ASReview eligibility screen.'}

    def papers(self, *, limit=25, cursor=None, q='', sort='title', membership='', evidence='', review=''):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ContractError('page size must be between 1 and 100')
        if not isinstance(q, str) or len(q) > 300 or '\x00' in q:
            raise ContractError('search text must be at most 300 characters')
        if sort not in SORTS or membership not in MEMBERSHIP | {''} or evidence not in EVIDENCE | {''} or review not in REVIEW | {''}:
            raise ContractError('unsupported catalogue filter or sort')
        options = {'limit': limit, 'q': q, 'sort': sort, 'membership': membership, 'evidence': evidence, 'review': review}
        where, values = filter_sql(options)
        with connection(self.project.database_path) as db:
            db.create_function('ct_fold', 1, lambda value: value.casefold(), deterministic=True)
            revision = _revision(db)
            offset = _page(cursor, revision, options)
            sql = catalogue_sql()
            total = db.execute(sql + 'SELECT COUNT(*) FROM catalogue' + where, values).fetchone()[0]
            if offset > total:
                raise ContractError('cursor is beyond this catalogue')
            ids = [row[0] for row in db.execute(sql + 'SELECT paper_id FROM catalogue' + where +
                ' ORDER BY ' + SORTS[sort] + ' LIMIT ? OFFSET ?', (*values, limit, offset))]
            return {'schema': SCHEMA, 'mode': 'operational_read_only', 'revision': revision,
                'items': [self._row(db, pid) for pid in ids], 'total': total,
                'offset': offset, 'limit': limit, 'filters': options,
                'previous_cursor': _cursor(max(0, offset-limit), revision, options) if offset else None,
                'next_cursor': _cursor(offset+limit, revision, options) if offset+limit < total else None}

    def paper(self, handle):
        with connection(self.project.database_path) as db:
            return {'schema': SCHEMA, 'mode': 'operational_read_only', 'revision': _revision(db),
                    'paper': self._row(db, _paper_id(handle), detail=True)}

    def provenance(self, handle, *, section='bibliography', limit=25, cursor=None):
        """Explicit paginated advanced access; raw records are never normal DTOs."""
        pid = _paper_id(handle)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ContractError('page size must be between 1 and 100')
        if section not in {'bibliography', 'provider', 'reviews', 'representations', 'identifiers'}:
            raise ContractError('unsupported provenance section')
        with connection(self.project.database_path) as db:
            if db.execute('SELECT 1 FROM paper_entities WHERE paper_id=?', (pid,)).fetchone() is None:
                raise KeyError(pid)
            revision = _revision(db)
            options = {'paper_id': pid, 'section': section, 'limit': limit}
            offset = _page(cursor, revision, options)
            if section == 'provider':
                query = "SELECT o.event_id,o.payload_json FROM ct_pipeline_events l " \
                    "JOIN ct_pipeline_events o ON o.event_id=l.scope_id " \
                    "WHERE l.kind='canonical_link' AND l.paper_id=? AND o.kind='candidate_observation' ORDER BY o.sequence"
            elif section == 'representations':
                query = "SELECT event_id,payload_json FROM ct_pipeline_events WHERE kind='representation' AND paper_id=? ORDER BY sequence"
            elif section == 'bibliography':
                query = 'SELECT observation_id,payload_json FROM ct_paper_observations WHERE paper_id=? ORDER BY observation_id'
            elif section == 'reviews':
                query = 'SELECT event_id,payload_json FROM ct_review_events WHERE paper_id=? ORDER BY sequence'
            else:
                query = 'SELECT i.identifier_id,i.scheme,i.normalized_value,i.status,i.verification_method,' \
                    'i.supporting_assertion,i.created_at,i.verified_at,a.raw_value,a.provider,a.provider_record_id,' \
                    'a.raw_artifact_sha256,a.asserted_at FROM paper_identifiers i LEFT JOIN identifier_assertions a ' \
                    'ON a.assertion_id=i.supporting_assertion WHERE i.paper_id=? ORDER BY i.scheme,i.normalized_value'
            total = db.execute('SELECT COUNT(*) FROM (' + query + ')', (pid,)).fetchone()[0]
            if offset > total:
                raise ContractError('cursor is beyond this provenance section')
            rows = [dict(row) for row in db.execute(query + ' LIMIT ? OFFSET ?', (pid, limit, offset))]
            items = [{**{key: value for key, value in row.items() if key != 'payload_json'},
                      **({'record': json.loads(row['payload_json'])} if 'payload_json' in row else {})} for row in rows]
            result = {'schema': SCHEMA, 'mode': 'advanced_operational_provenance', 'paper_id': pid,
                'section': section, 'revision': revision, 'items': items, 'total': total, 'offset': offset,
                'previous_cursor': _cursor(max(0, offset-limit), revision, options) if offset else None,
                'next_cursor': _cursor(offset+limit, revision, options) if offset+limit < total else None}
            if section == 'bibliography':
                metadata = self.project.discovery._metadata(db, pid)
                result['canonical_selection'] = {'rule': metadata['selection_rule'], 'fields': metadata['field_provenance']}
            metadata = self.project.discovery._metadata(db, pid)
            result['summary'] = {'identifiers': metadata['identifiers'], 'sources': _sources(db, pid),
                'canonical_selection_rule': metadata['selection_rule']}
            return result

    def document(self, handle, representation_handle, *, offset=0, limit=16000):
        """Bounded text view of an enrolled verified body; never a path endpoint."""
        pid = _paper_id(handle)
        if not re.fullmatch(r'[0-9a-f]{64}', representation_handle):
            raise ContractError('invalid representation link')
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 32000:
            raise ContractError('invalid text page')
        with connection(self.project.database_path) as db:
            rows = events_in_connection(db, paper_id=pid, kind='representation')
            selected = next((x for x in rows if x['event_id'] == 'pipeline:' + representation_handle), None)
            if selected is None:
                raise KeyError(representation_handle)
            value = selected['payload']
            if not (value['trusted'] and value['artifact_validity'] == 'verified'
                    and value['representation'] == 'structured_text' and value.get('evidence_depth') == 'document_body'):
                raise ContractError('This representation is not trusted document-body evidence.')
            body = artifact_in_connection(self.project, db, selected['source_sha256']).read_text(encoding='utf-8')
            if offset > len(body):
                raise ContractError('text offset is beyond the document')
            return {'schema': SCHEMA, 'text': body[offset:offset+limit], 'offset': offset,
                'total_characters': len(body), 'next_offset': offset+limit if offset+limit < len(body) else None,
                'representation_handle': representation_handle, 'source_sha256': selected['source_sha256'],
                'notice': 'Viewing evidence does not record a review or attest that the full paper was read.'}
