"""Explicit append-only scientific observations; never a production authority writer.

Read methods use mode=ro. Project.upgrade is the separate explicit migration action.
Plan -> apply -> verify is mandatory; no implicit timestamp, identity or backfill.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import json
import re
import sqlite3

from .registry import Registry
from corpustrail._internal.values import canonical, content_hash as digest
from corpustrail._internal.database import connection, latest_config

PRODUCERS = {'human', 'model', 'deterministic', 'parser/document', 'imported/external'}
RELATIONS = {'validates', 'disputes', 'supersedes', 'retracts', 'duplicates', 'derived_from', 'rejects', 'grants_authority', 'revokes_authority'}
HUMAN_EVENTS = {'validates', 'grants_authority', 'revokes_authority'}
REPRESENTATIONS = {'none', 'metadata', 'abstract', 'structured_text', 'pdf_text', 'ocr_text', 'image_only', 'citation_context', 'imported_metadata', 'source_record', 'pdf', 'jats_xml', 'publisher_xml', 'bioc_json', 'external_document'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    require(nonempty(value), 'explicit source/run timestamp required')
    require(datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None, 'timestamp requires timezone')


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'invalid SHA-256')


def assertion_payload(draft, registry):
    p = deepcopy(draft)
    required = {'subject_type', 'subject_id', 'paper_id', 'predicate', 'vocabulary_version', 'raw_value', 'value_datatype',
                'producer_type', 'producer_id', 'created_at', 'evidence_representation', 'source', 'lineage_ref'}
    optional = {'normalized_value', 'normalization', 'producer_version', 'evidence_location', 'evidence_reference',
                'document_artifact_id', 'text_artifact_id', 'passage_id', 'confidence', 'context'}
    require(required <= p.keys() and not (p.keys() - required - optional), 'unknown/missing assertion fields')
    for key in optional:
        p.setdefault(key, None)
    for key in ('subject_type', 'subject_id', 'predicate', 'vocabulary_version', 'producer_id', 'lineage_ref'):
        require(nonempty(p[key]), 'non-empty ' + key + ' required')
    require(p['paper_id'] is None or nonempty(p['paper_id']), 'invalid paper_id')
    if p['subject_type'] in ('paper', 'report'):
        require(p['paper_id'] == p['subject_id'], 'paper/report must use an existing canonical paper_id')
    require(p['producer_type'] in PRODUCERS, 'unknown producer type')
    require(p['evidence_representation'] in REPRESENTATIONS, 'unknown evidence representation')
    timestamp(p['created_at'])
    definitions = registry.describe()['concepts']
    versions = registry.describe().get('versions', {})
    require(not versions or versions.get(p['predicate']) == p['vocabulary_version'], 'concept version mismatch')
    require(p['predicate'] in definitions, 'predicate is not in the explicit registry')
    require('.' in p['predicate'], 'predicate must be namespaced')
    require(isinstance(p['source'], dict), 'source must explicitly describe provenance (possibly unknown)')
    if p['source'].get('artifact_sha256') is not None:
        sha(p['source']['artifact_sha256'])
    source_field = p['source'].get('field')
    require(source_field is None, 'source fields require an explicit scoped adapter; generic writes cannot reinterpret legacy fields')
    mappings = registry.describe()['legacy_field_mappings']
    if source_field in mappings:
        require(p['predicate'] == mappings[source_field], 'legacy field semantic reinterpretation forbidden')
    types = {'unknown': lambda v: v is None, 'string': lambda v: isinstance(v, str),
             'boolean': lambda v: type(v) is bool, 'integer': lambda v: type(v) is int,
             'number': lambda v: type(v) in (int, float), 'object': lambda v: isinstance(v, dict),
             'array': lambda v: isinstance(v, list)}
    require(p['value_datatype'] in types and types[p['value_datatype']](p['raw_value']), 'raw value/datatype mismatch')
    definition = json.loads(definitions[p['predicate']])
    require(definition.get('concept_id') == p['predicate'] and definition.get('version') == p['vocabulary_version'], 'stored definition/version binding mismatch')
    require(not definition.get('value_types') or p['value_datatype'] in definition['value_types'], 'value datatype incompatible with concept')
    if p['normalized_value'] is not None:
        require(isinstance(p['normalization'], dict) and all(nonempty(p['normalization'].get(k)) for k in ('method', 'version', 'source_ref')), 'normalization requires explicit provenance')
        require(p['raw_value'] is not None, 'unknown raw value cannot acquire normalized truth')
    if p['confidence'] is not None:
        c = p['confidence']
        require(isinstance(c, dict) and c.get('kind') in ('descriptive', 'probability'), 'invalid confidence')
        if c['kind'] == 'probability':
            require(type(c.get('value')) in (int, float) and 0 <= c['value'] <= 1, 'invalid probability')
        else:
            require(nonempty(c.get('label')), 'descriptive confidence requires label')
    p.update(schema_version='corpustrail-knowledge-assertion/v0b', definition=definitions[p['predicate']],
             initial_validation='unvalidated', initial_authority='non_authoritative')
    canonical(p)  # Reject NaN/non-JSON data rather than changing it.
    return p


def event_payload(draft):
    p = deepcopy(draft)
    required = {'target_assertion_id', 'relation', 'actor_type', 'actor_id', 'created_at', 'rationale', 'source', 'lineage_ref'}
    optional = {'source_assertion_id', 'target_event_id', 'purpose', 'policy_id', 'actor_version'}
    require(required <= p.keys() and not (p.keys() - required - optional), 'unknown/missing event fields')
    for key in optional:
        p.setdefault(key, None)
    for key in ('target_assertion_id', 'actor_id', 'rationale', 'lineage_ref'):
        require(nonempty(p[key]), 'non-empty event ' + key + ' required')
    require(p['relation'] in RELATIONS and p['actor_type'] in PRODUCERS, 'invalid event relation/actor')
    timestamp(p['created_at'])
    require(isinstance(p['source'], dict), 'event source required')
    if p['source'].get('artifact_sha256') is not None:
        sha(p['source']['artifact_sha256'])
    if p['relation'] in HUMAN_EVENTS:
        require(p['actor_type'] == 'human', 'only explicit human events validate/grant/revoke')
        require(nonempty(p['purpose']) and p['purpose'].startswith('knowledge.') and len(p['purpose']) > 10, 'authority purpose must be knowledge-scoped')
        require(nonempty(p['policy_id']) and nonempty(p['source'].get('reference')) and p['source'].get('artifact_sha256'), 'human validation requires policy and hash-bound decision source')
    if p['relation'] in ('supersedes', 'duplicates', 'derived_from'):
        require(nonempty(p['source_assertion_id']), 'relationship requires a source assertion')
    require(p['source_assertion_id'] != p['target_assertion_id'], 'self relationship forbidden')
    require((p['relation'] == 'revokes_authority') == (p['target_event_id'] is not None), 'revocation must name a specific grant')
    p['schema_version'] = 'corpustrail-knowledge-event/v0b'
    canonical(p)
    return p


def identified(payload, kind):
    h = digest(payload)
    return {'id': 'knowledge-' + kind + ':' + h[7:], 'content_sha256': h, 'payload': payload}


class KnowledgeStore:
    def __init__(self, project, *, registry=None):
        self.project = project
        self.registry = registry or Registry.for_project(project)
        self.path = project.database_path

    @contextmanager
    def connection(self, *, write=False):
        with connection(self.path, write=write) as con:
            require(con.execute('SELECT 1 FROM schema_migrations WHERE version=35').fetchone(),
                    'explicit standalone migration 35 required')
            yield con

    def plan_batch(self, assertions=(), events=()):
        a = [identified(assertion_payload(d, self.registry), 'assertion') for d in assertions]
        e = [identified(event_payload(d), 'event') for d in events]
        with self.connection() as con:
            base = self._event_revision(con)
            config_id = latest_config(con)[0]
        body = {'schema_version': 'corpustrail-knowledge-plan/v0b', 'registry_sha256': digest(self.registry.describe()),
                'base_event_revision': base, 'config_event_id': config_id, 'assertions': a, 'events': e, 'production_effect': 'none'}
        return {**body, 'plan_sha256': digest(body)}

    @staticmethod
    def _event_revision(con):
        return digest([r[0] for r in con.execute('SELECT event_id FROM knowledge_events ORDER BY event_id')])

    @staticmethod
    def _insert(con, table, key, row):
        existing = con.execute(f'SELECT * FROM {table} WHERE {key}=?', (row[key],)).fetchone()
        if existing:
            require(dict(existing) == row, 'identity collision or corrupted stored content')
            return False
        con.execute(f'INSERT INTO {table} (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))
        return True

    def apply(self, plan, *, human_authorization=None):
        """Explicit mutation. Optional authorization binds exact plan/purposes/reviewer.

        Authorization is a caller-supplied human approval record, not authentication.
        Never create it autonomously on a model's behalf.
        """
        body = {k: v for k, v in plan.items() if k != 'plan_sha256'}
        require(digest(body) == plan.get('plan_sha256'), 'plan hash mismatch')
        require(body.get('schema_version') == 'corpustrail-knowledge-plan/v0b' and body.get('production_effect') == 'none', 'invalid write plan')
        require(body['registry_sha256'] == digest(self.registry.describe()), 'registry changed')
        require(body['registry_sha256'] == digest(Registry.for_project(self.project).describe()), 'live project registry changed')
        for item in body['assertions']:
            p = item['payload']
            raw = {k: v for k, v in p.items() if k not in ('schema_version', 'definition', 'initial_validation', 'initial_authority')}
            require(item == identified(assertion_payload(raw, self.registry), 'assertion'), 'assertion identity/contract mismatch')
        for item in body['events']:
            p = item['payload']
            require(item == identified(event_payload({k: v for k, v in p.items() if k != 'schema_version'}), 'event'), 'event identity/contract mismatch')
            if p['relation'] in HUMAN_EVENTS:
                auth = human_authorization or {}
                require(auth.get('plan_sha256') == plan['plan_sha256'] and auth.get('reviewer_id') == p['actor_id']
                        and p['purpose'] in auth.get('purposes', []) and auth.get('policy_id') == p['policy_id']
                        and auth.get('decision_source') == p['source'], 'explicit plan-bound human authorization required')
        added = {'assertions': 0, 'events': 0}
        with self.connection(write=True) as con:
            require(latest_config(con)[0] == body['config_event_id'], 'configuration changed since planning')
            require(body['registry_sha256'] == digest(Registry.from_connection(con).describe()), 'registry changed before transaction')
            for item in body['events']:
                p = item['payload']
                if p['relation'] in HUMAN_EVENTS:
                    require(p['actor_id'] in latest_config(con)[1]['review']['authorized_reviewers'],
                            'human knowledge validation requires an explicitly configured reviewer')
            if self._event_revision(con) != body['base_event_revision']:
                require(all(con.execute(f'SELECT 1 FROM {table} WHERE {key}=? AND payload_json=?', (i['id'], canonical(i['payload']))).fetchone()
                            for table, key, items in [('knowledge_assertions', 'assertion_id', body['assertions']), ('knowledge_events', 'event_id', body['events'])] for i in items), 'stale lineage plan; re-plan')
            for item in body['assertions']:
                p = item['payload']
                self._check_evidence(con, p)
                concept = {'predicate': p['predicate'], 'vocabulary_version': p['vocabulary_version'],
                           'definition': p['definition'], 'definition_sha256': digest(p['definition'])}
                old = con.execute('SELECT * FROM knowledge_concepts WHERE predicate=? AND vocabulary_version=?', (p['predicate'], p['vocabulary_version'])).fetchone()
                if old:
                    require(dict(old) == concept, 'concept version already has a different definition')
                else:
                    con.execute('INSERT INTO knowledge_concepts VALUES (?,?,?,?)', list(concept.values()))
                added['assertions'] += self._insert(con, 'knowledge_assertions', 'assertion_id', assertion_row(item))
            for item in body['events']:
                self._check_event(con, item['payload'])
                added['events'] += self._insert(con, 'knowledge_events', 'event_id', event_row(item))
            verify_connection(con, self)  # Failure rolls back the whole batch.
        return {**added, 'plan_sha256': plan['plan_sha256'], 'production_effect': 'none'}

    def append_assertion(self, draft, *, apply=False):
        return self.append_batch([draft], apply=apply)

    def append_batch(self, drafts, *, apply=False):
        plan = self.plan_batch(drafts)
        return self.apply(plan) if apply else plan

    def _check_evidence(self, con, p):
        from .evidence import resolve_reference
        resolve_reference(self.project, con, p)

    @staticmethod
    def _check_event(con, p):
        require(con.execute('SELECT 1 FROM knowledge_assertions WHERE assertion_id=?', (p['target_assertion_id'],)).fetchone(), 'unknown assertion target')
        if p['source_assertion_id']:
            source = con.execute('SELECT * FROM knowledge_assertions WHERE assertion_id=?', (p['source_assertion_id'],)).fetchone()
            require(source is not None, 'unknown source assertion')
            if p['relation'] in ('supersedes','duplicates'):
                target = con.execute('SELECT * FROM knowledge_assertions WHERE assertion_id=?', (p['target_assertion_id'],)).fetchone()
                require(all(source[k]==target[k] for k in ('subject_type','subject_id','predicate')), 'replacement/duplicate must concern same subject and predicate')
        if p['relation'] == 'revokes_authority':
            grant = con.execute('SELECT * FROM knowledge_events WHERE event_id=?', (p['target_event_id'],)).fetchone()
            require(grant is not None and grant['relation'] == 'grants_authority' and
                    all(grant[k] == p[k] for k in ('target_assertion_id', 'purpose', 'policy_id')), 'revocation must target a matching grant')

    def assertions(self, *, subject_type=None, subject_id=None, predicate=None):
        with self.connection() as con:
            rows = [json.loads(r[0]) for r in con.execute('SELECT payload_json FROM knowledge_assertions ORDER BY assertion_id')]
        return [identified(p, 'assertion') for p in rows if all(v is None or p[k] == v for k, v in
                [('subject_type', subject_type), ('subject_id', subject_id), ('predicate', predicate)])]

    def query(self, predicate, value):
        return [r for r in self.assertions(predicate=predicate) if canonical(r['payload']['raw_value']) == canonical(value)]

    def history(self, assertion_id):
        with self.connection() as con:
            return [identified(json.loads(r[0]), 'event') for r in con.execute(
                'SELECT payload_json FROM knowledge_events WHERE target_assertion_id=? OR source_assertion_id=? ORDER BY event_id', (assertion_id, assertion_id))]

    def validation_history(self, assertion_id):
        return [r for r in self.history(assertion_id) if r['payload']['target_assertion_id']==assertion_id
                and r['payload']['relation'] in ('validates','rejects','disputes','grants_authority','revokes_authority','retracts')]

    def evidence(self, assertion_id):
        with self.connection() as con:
            row = con.execute('SELECT payload_json FROM knowledge_assertions WHERE assertion_id=?', (assertion_id,)).fetchone()
            require(row is not None, 'unknown assertion')
            p = json.loads(row[0])
        from .evidence import resolve_reference
        with self.connection() as con:
            resolved = resolve_reference(self.project, con, p)
        return {'resolved': resolved, **{k:p[k] for k in ('source','evidence_representation','evidence_location','evidence_reference',
                                 'document_artifact_id','text_artifact_id','passage_id','lineage_ref')}}

    def conflicts(self, *, subject_type=None, subject_id=None):
        groups = {}
        for row in self.assertions(subject_type=subject_type, subject_id=subject_id):
            p = row['payload']
            key = (p['subject_type'],p['subject_id'],p['predicate'],p['vocabulary_version'],canonical(p['context']))
            groups.setdefault(key,[]).append(row)
        return [{'subject_type':key[0], 'subject_id':key[1], 'predicate':key[2], 'vocabulary_version':key[3],
                 'assertions': rows, 'kind':'candidate_value_difference', 'resolution':'not_inferred'}
                for key,rows in sorted(groups.items()) if len({canonical(r['payload']['raw_value']) for r in rows if r['payload']['raw_value'] is not None})>1]

    def authoritative(self, purpose):
        require(nonempty(purpose) and purpose.startswith('knowledge.'), 'knowledge purpose required')
        with self.connection() as con:
            grouped = {}
            for r in con.execute('SELECT a.assertion_id, a.payload_json, g.event_id FROM knowledge_events g JOIN knowledge_assertions a ON a.assertion_id=g.target_assertion_id '
                    "WHERE g.relation='grants_authority' AND g.purpose=? AND NOT EXISTS (SELECT 1 FROM knowledge_events r WHERE r.relation='revokes_authority' AND r.target_event_id=g.event_id) ORDER BY a.assertion_id,g.event_id", (purpose,)):
                grouped.setdefault(r['assertion_id'], {'assertion':identified(json.loads(r['payload_json']),'assertion'), 'grant_ids':[], 'purpose':purpose})['grant_ids'].append(r['event_id'])
            return list(grouped.values())

    def verify(self):
        with self.connection() as con:
            return verify_connection(con, self)


def assertion_row(item):
    p = item['payload']
    keys = ('subject_type','subject_id','paper_id','predicate','vocabulary_version','value_datatype','producer_type','producer_id','producer_version','created_at','evidence_representation','document_artifact_id','text_artifact_id','passage_id','initial_validation','initial_authority')
    return {'assertion_id': item['id'], 'content_sha256': item['content_sha256'], **{k:p[k] for k in keys},
            'raw_value_json': canonical(p['raw_value']), 'normalized_value_json': canonical(p['normalized_value']), 'payload_json': canonical(p)}


def event_row(item):
    p = item['payload']
    return {'event_id': item['id'], 'content_sha256': item['content_sha256'], **{k:p[k] for k in
            ('target_assertion_id','source_assertion_id','target_event_id','relation','actor_type','actor_id','purpose','policy_id','created_at')}, 'payload_json': canonical(p)}


def verify_connection(con, store):
    """Reconstruct IDs, indexed columns, concepts and links from immutable payloads."""
    counts = {}
    for table, kind, row_fn in [('knowledge_assertions','assertion',assertion_row), ('knowledge_events','event',event_row)]:
        rows = con.execute('SELECT * FROM ' + table).fetchall()
        counts[table] = len(rows)
        for row in rows:
            p = json.loads(row['payload_json'])
            require(dict(row) == row_fn(identified(p,kind)), 'knowledge content/index hash mismatch')
            if kind == 'assertion':
                raw = {k:v for k,v in p.items() if k not in ('schema_version','definition','initial_validation','initial_authority')}
                # Stored definitions are versioned historical evidence; do not reinterpret with future core definitions.
                class StoredDefinition:
                    def describe(self):
                        return {'concepts': {p['predicate']:p['definition']}, 'legacy_field_mappings':{}}
                require(assertion_payload(raw,StoredDefinition())==p, 'invalid assertion contract')
                concept = con.execute('SELECT * FROM knowledge_concepts WHERE predicate=? AND vocabulary_version=?', (p['predicate'],p['vocabulary_version'])).fetchone()
                require(concept is not None and concept['definition']==p['definition'] and concept['definition_sha256']==digest(p['definition']), 'concept binding mismatch')
                store._check_evidence(con,p)
            else:
                require(event_payload({k:v for k,v in p.items() if k!='schema_version'})==p, 'invalid event payload')
                KnowledgeStore._check_event(con,p)
    return {'ok': True, **counts, 'production_effect':'none'}
