"""Explicit CP9 audit/correction workflows over immutable CP7/CP8 records."""
from dataclasses import dataclass, asdict
import heapq
import json

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, identifier, timestamp
from corpustrail.application.project_use import project_use
from corpustrail.curation.guided import GuidedReviewService
from corpustrail.curation.sessions import _load
from corpustrail.curation.service import _history
from corpustrail.populations.contracts import command_id, page
from corpustrail.references.contracts import bounded_text, exact_id
from corpustrail.references import storage as reference_storage
from corpustrail.references.service import ReferenceService, definition
from .contracts import json_value
from . import storage
from .curation_views import PRIMARY, OVERLAYS, query, where, counts, is_assisted

ASSISTED_NOTICE = 'Explicitly assisted operational review. Suggestions are not human decisions. Newly frozen review evidence may differ from earlier engine input; neither is rewritten.'


def _source(member, audit_id, packet):
    return {'paper_id':member['paper_id'],'audit_id':audit_id,'audit_member_sha256':content_hash(member),
        'result_ids':member['result_ids'],'review_evidence_snapshot_sha256':packet['evidence_snapshot_sha256']}


def ready(db):
    return db.execute('SELECT 1 FROM schema_migrations WHERE version=41').fetchone() is not None


def require(db):
    if not ready(db): raise ContractError('curation writes require an explicit backed-up project upgrade')


def _cutoff(db, table, cutoff, offset):
    if table not in {'ct_curation_audits', 'ct_curation_sessions', 'ct_curation_outcomes', 'ct_curation_workflow_events'}:
        raise ContractError('unsupported curation list')
    if offset and cutoff is None: raise ContractError('continue this append-only list with its original cutoff')
    maximum = db.execute('SELECT COALESCE(MAX(rowid),0) FROM ' + table).fetchone()[0]
    if cutoff is None: return maximum
    if type(cutoff) is not int or not 0 <= cutoff <= maximum: raise ContractError('invalid curation list cutoff')
    return cutoff


@dataclass(frozen=True)
class AuditSelection:
    mode: str
    seed: int
    size: int
    groups: tuple[str, ...] = ('exclude', 'uncertain', 'include', 'disagreement')
    primary_filter: str = ''
    overlay_filter: str = ''

    def to_dict(self):
        if self.mode not in {'random', 'stratified'} or type(self.seed) is not int or not -(2**63) <= self.seed < 2**63:
            raise ContractError('choose random/stratified sampling and an explicit bounded integer seed')
        if type(self.size) is not int or not 1 <= self.size <= 100:
            raise ContractError('choose 1–100 samples per explicit audit unit, not a collection size limit')
        if not isinstance(self.groups, tuple) or not self.groups or len(set(self.groups)) != len(self.groups) or not set(self.groups) <= set(PRIMARY + OVERLAYS):
            raise ContractError('choose unique supported audit strata')
        where(self.primary_filter, self.overlay_filter)
        return asdict(self)


def _record(db, audit_id):
    require(db); exact_id(audit_id, 'curation-audit')
    row = db.execute('SELECT * FROM ct_curation_audits WHERE audit_id=?', (audit_id,)).fetchone()
    if row is None: raise ContractError('audit is not in this project')
    value = json.loads(row['payload_json'])
    if identifier('curation-audit', value) != audit_id or row['request_id'] != value['request_id'] or row['command_sha256'] != value['command_sha256']:
        raise ContractError('frozen audit integrity changed')
    return value


def _members(db, audit_id, *, offset=0, limit=20):
    head = _record(db, audit_id); page(offset, limit)
    values = []
    for row in db.execute('SELECT * FROM ct_curation_audit_members WHERE audit_id=? AND position>=? AND position<? ORDER BY position', (audit_id, offset, offset + limit)):
        value = json.loads(row['payload_json'])
        if content_hash(value) != row['content_sha256'] or value['paper_id'] != row['paper_id']:
            raise ContractError('frozen audit member changed')
        values.append(value)
    for chunk in range(offset // 100, (min(offset + limit, head['selected_count']) + 99) // 100):
        hashes = [r[0] for r in db.execute('SELECT content_sha256 FROM ct_curation_audit_members WHERE audit_id=? AND position>=? AND position<? ORDER BY position', (audit_id, chunk * 100, (chunk + 1) * 100))]
        if content_hash(hashes) != head['member_chunk_hashes'][chunk]: raise ContractError('audit selection manifest changed')
    return values


class CurationService:
    def __init__(self, project): self.project = project

    def _audit(self, db, *, request_id, name, actor, created_at, config_event_id, run_id, compare_run_id=None, selection):
        require(db); command_id(request_id); timestamp(created_at)
        bounded_text(name, 'audit name', 200); bounded_text(actor, 'explicit audit actor', 200)
        if not isinstance(selection, AuditSelection): raise ContractError('typed audit selection required')
        spec = selection.to_dict()
        command = json.loads(json_value({'request_id': request_id, 'name': name, 'actor': actor,
            'created_at': created_at, 'config_event_id': config_event_id, 'run_id': run_id,
            'compare_run_id': compare_run_id, 'selection': spec}))
        if latest_config(db)[0] != config_event_id: raise ContractError('configuration changed; preview the audit again')
        sql, params, head, sources, revision = query(db, run_id, compare_run_id)
        clause, filters = where(selection.primary_filter, selection.overlay_filter)
        base = 'SELECT * FROM candidates' + clause
        selected = {}; strata = []
        for group in (('random',) if selection.mode == 'random' else selection.groups):
            extra = '' if group == 'random' else (' AND ' if clause else ' WHERE ') + ('primary_state=?' if group in PRIMARY else group + '=1')
            args = (*params, *filters, *([group] if group in PRIMARY else []))
            total = db.execute(sql + 'SELECT COUNT(*) FROM candidates' + clause + extra, args).fetchone()[0]
            pool = db.execute(sql + base + extra, args)
            ranked = heapq.nsmallest(selection.size, ((content_hash({'seed': selection.seed, 'stratum': group, 'paper_id': row['paper_id']}), row['paper_id'], dict(row)) for row in pool))
            strata.append({'group': group, 'eligible_count': total, 'selected_count': len(ranked),
                'sampling_fraction': len(ranked) / total if total else None})
            for rank, (score, pid, row) in enumerate(ranked, 1):
                item = selected.setdefault(pid, {'paper_id': pid, 'position_in_run': row['position'],
                    'primary_state': row['primary_state'], 'overlays': [key for key in OVERLAYS if row[key]],
                    'result_ids': [v for v in (row['result_id'], row['comparison_result_id']) if v], 'selection': []})
                item['selection'].append({'stratum': group, 'rank': rank, 'decision_sha256': score})
        members = [selected[pid] for pid in sorted(selected)]
        for member in members:
            for result_id in member['result_ids']:
                row = db.execute('SELECT run_id,position FROM ct_classifier_results WHERE result_id=?', (result_id,)).fetchone()
                exact = storage.result(db, row['run_id'], row['position'])
                if exact['paper_id'] != member['paper_id']: raise ContractError('audit source identifies another paper')
        hashes = [content_hash(value) for value in members]
        header = {'schema': 'corpustrail-frozen-curation-audit/v1', **command, 'command_sha256': content_hash(command),
            'definition_sha256': head['definition_sha256'], 'population_version_id': head['population_version_id'],
            'source_revision': revision, 'sources': sources, 'population_counts': counts(db, sql, params),
            'sampling_algorithm': 'sha256-canonical-order/v1', 'strata': strata, 'selected_count': len(members),
            'selection_overlap_count': sum(s['selected_count'] for s in strata) - len(members),
            'member_manifest_sha256': content_hash(hashes),
            'member_chunk_hashes': [content_hash(hashes[n:n + 100]) for n in range(0, len(hashes), 100)],
            'authority': 'non_authoritative',
            'qualification': 'Frozen random-within-filter or policy-stratified selection. Strata may overlap. Audit outcomes do not establish unbiased corpus-wide performance or a stopping rule. Unsampled candidates remain accessible.'}
        return header, members, command

    @staticmethod
    def public(value): return {k: v for k, v in value.items() if k != 'member_chunk_hashes'}

    def preview_audit(self, **fields):
        with connection(self.project.database_path) as db:
            header, members, _ = self._audit(db, **fields)
            return {**self.public(header), 'preview_sha256': content_hash(header), 'items': members[:20],
                'next_offset': 20 if len(members) > 20 else None}

    def commit_audit(self, *, expected_preview_sha256, **fields):
        with project_use(self.project.root), connection(self.project.database_path, write=True) as db:
            require(db); command_id(fields['request_id'])
            prior = db.execute('SELECT audit_id FROM ct_curation_audits WHERE request_id=?', (fields['request_id'],)).fetchone()
            if prior:
                old = _record(db, prior[0])
                command = {**fields, 'selection': fields['selection'].to_dict()}
                if old['command_sha256'] != content_hash(command) or content_hash(old) != expected_preview_sha256:
                    raise ContractError('audit command was already used with different content')
                return {'audit_id': prior[0], **self.public(old), 'replayed': True}
            header, members, _ = self._audit(db, **fields)
            if content_hash(header) != expected_preview_sha256: raise ContractError('audit sources changed; inspect and preview again')
            aid = identifier('curation-audit', header)
            db.execute('INSERT INTO ct_curation_audits(audit_id,request_id,command_sha256,payload_json) VALUES (?,?,?,?)',
                       (aid, fields['request_id'], header['command_sha256'], canonical(header)))
            for position, member in enumerate(members):
                db.execute('INSERT INTO ct_curation_audit_members VALUES (?,?,?,?,?)', (aid, position, member['paper_id'], canonical(member), content_hash(member)))
            return {'audit_id': aid, **self.public(header), 'replayed': False}

    def audits(self, *, offset=0, limit=20, cutoff=None):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            if not ready(db): return {'available': False, 'total': 0, 'items': [], 'next_offset': None}
            cutoff = _cutoff(db, 'ct_curation_audits', cutoff, offset)
            total = db.execute('SELECT COUNT(*) FROM ct_curation_audits WHERE rowid<=?', (cutoff,)).fetchone()[0]
            rows = db.execute('SELECT audit_id FROM ct_curation_audits WHERE rowid<=? ORDER BY sequence DESC LIMIT ? OFFSET ?', (cutoff, limit, offset))
            return {'available': True, 'cutoff': cutoff, 'total': total, 'items': [{'audit_id': r[0], **self.public(_record(db, r[0]))} for r in rows],
                'next_offset': offset + limit if offset + limit < total else None}

    def audit(self, audit_id, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            value = _record(db, audit_id)
            return {'audit_id': audit_id, **self.public(value), 'items': _members(db, audit_id, offset=offset, limit=limit),
                'next_offset': offset + limit if offset + limit < value['selected_count'] else None}

    def verify_audit(self, audit_id):
        with connection(self.project.database_path) as db:
            head = _record(db, audit_id); hashes = []
            for offset in range(0, head['selected_count'], 100):
                hashes.extend(content_hash(row) for row in _members(db, audit_id, offset=offset, limit=100))
            if content_hash(hashes) != head['member_manifest_sha256']: raise ContractError('audit manifest changed')
            return {'audit_id': audit_id, 'verified': True, 'selected_count': len(hashes), 'manifest_sha256': content_hash(hashes)}

    def create_assisted(self, *, request_id, audit_id, reviewer_id, config_event_id, confirm_assisted):
        command_id(request_id); bounded_text(reviewer_id, 'explicit reviewing identity', 200)
        if confirm_assisted is not True: raise ContractError('explicitly choose operational assisted review; this is not method-blind validation')
        command = dict(request_id=request_id, audit_id=audit_id, reviewer_id=reviewer_id,
                       config_event_id=config_event_id, confirm_assisted=True)
        with project_use(self.project.root):
            with connection(self.project.database_path) as db:
                require(db)
                prior = db.execute('SELECT session_id,command_sha256 FROM ct_curation_sessions WHERE request_id=?', (request_id,)).fetchone()
                if prior:
                    if prior[1] != content_hash(command): raise ContractError('assisted session command differs')
                    self._binding(db,prior[0])
                    return {'session_id': prior[0], 'replayed': True}
                head = _record(db, audit_id)
                if not head['selected_count']: raise ContractError('this frozen audit selected no candidates')
                if latest_config(db)[0] != config_event_id or content_hash(definition(latest_config(db)[1])) != head['definition_sha256']:
                    raise ContractError('configuration/scope changed; explicitly inspect a new review snapshot')
                selected = []
                for offset in range(0, head['selected_count'], 100): selected.extend(_members(db, audit_id, offset=offset, limit=100))
            ids = [r['paper_id'] for r in selected]
            # Existing population service freezes exact identity/source observations.
            # It commits first: an interrupted creation may leave a clearly named
            # candidate version, never partial human observations or membership.
            fields = {'request_id': content_hash({'audit_review': request_id}).split(':')[1][:32],
                'name': 'Frozen audit review candidates', 'actor': reviewer_id,
                'sources': [{'kind': 'selection', 'paper_ids': ids[n:n + 500]} for n in range(0, len(ids), 500)]}
            preview = self.project.populations.preview(**fields)
            population = self.project.populations.create(**fields, expected_preview_sha256=preview['preview_sha256'], created_at=head['created_at'])
            with connection(self.project.database_path, write=True) as db:
                require(db)
                prior = db.execute('SELECT session_id,command_sha256 FROM ct_curation_sessions WHERE request_id=?', (request_id,)).fetchone()
                if prior:
                    if prior[1] != content_hash(command): raise ContractError('concurrent assisted session command differs')
                    return {'session_id': prior[0], 'replayed': True}
                result = GuidedReviewService(self.project, _db=db).create(command_id=request_id,
                    reviewer_id=reviewer_id, selection=population['version_id'], population_sha256=content_hash(ids),
                    config_event_id=config_event_id, mode='operational')
                sid = result['session_id']; packet, _, _, _ = _load(db, sid)
                if packet['mode'] != 'operational': raise ContractError('assisted context cannot be attached to blinded review')
                binding = {'schema': 'corpustrail-assisted-session/v1', **command, 'session_id': sid,
                    'command_sha256': content_hash(command), 'audit_manifest_sha256': head['member_manifest_sha256'],
                    'population_version_id': population['version_id'], 'review_evidence_snapshot_sha256': packet['evidence_snapshot_sha256'],
                    'notice': ASSISTED_NOTICE}
                db.execute('INSERT INTO ct_curation_sessions VALUES (?,?,?,?,?)', (sid, request_id, content_hash(command), audit_id, canonical(binding)))
                for member in selected:
                    source = _source(member,audit_id,packet)
                    db.execute('INSERT INTO ct_curation_session_sources VALUES (?,?,?,?)', (sid, member['paper_id'], canonical(source), content_hash(source)))
                return {**result, 'replayed': False}

    def _binding(self,db,session_id):
        require(db)
        row=db.execute('SELECT * FROM ct_curation_sessions WHERE session_id=?',(session_id,)).fetchone()
        if row is None:raise ContractError('session is not an operational assisted review')
        value=json.loads(row['payload_json'])
        command={k:value[k] for k in ('request_id','audit_id','reviewer_id','config_event_id','confirm_assisted')}
        packet,_,_,config=_load(db,session_id);head=_record(db,row['audit_id'])
        link=self.project.populations.review_link(db,session_id)
        if (content_hash(command)!=row['command_sha256'] or row['request_id']!=command['request_id']
                or row['audit_id']!=command['audit_id'] or command['confirm_assisted'] is not True
                or command['reviewer_id']!=packet['reviewer_id'] or config!=command['config_event_id']
                or packet['mode']!='operational' or not link):raise ContractError('assisted command/session binding changed')
        expected={'schema':'corpustrail-assisted-session/v1',**command,'session_id':session_id,
            'command_sha256':content_hash(command),'audit_manifest_sha256':head['member_manifest_sha256'],
            'population_version_id':link['version_id'],'review_evidence_snapshot_sha256':packet['evidence_snapshot_sha256'],
            'notice':ASSISTED_NOTICE}
        if expected!=value:raise ContractError('assisted audit/population/evidence binding changed')
        return value,packet

    def _bound_source(self,db,session_id,paper_id):
        binding,packet=self._binding(db,session_id)
        row=db.execute('SELECT position FROM ct_curation_audit_members WHERE audit_id=? AND paper_id=?',(binding['audit_id'],paper_id)).fetchone()
        if row is None:raise ContractError('paper is outside this assisted audit')
        member=_members(db,binding['audit_id'],offset=row[0],limit=1)[0]
        expected=_source(member,binding['audit_id'],packet)
        source=db.execute('SELECT payload_json,content_sha256 FROM ct_curation_session_sources WHERE session_id=? AND paper_id=?',(session_id,paper_id)).fetchone()
        if source is None or json.loads(source[0])!=expected or source[1]!=content_hash(expected):
            raise ContractError('assisted source differs from its immutable audit member')
        return expected,packet

    def assisted_sources(self, session_id, paper_id):
        with connection(self.project.database_path) as db:
            value,_=self._bound_source(db,session_id,paper_id)
            results = []
            for result_id in value['result_ids']:
                source = db.execute('SELECT run_id,position FROM ct_classifier_results WHERE result_id=?', (result_id,)).fetchone()
                exact = storage.result(db, source[0], source[1])
                if exact['paper_id'] != paper_id: raise ContractError('assisted result identifies another paper')
                results.append(exact)
            return {**value, 'results': results, 'presentation': 'operational_assisted',
                'notice': 'Engine observations/failures are not human judgments or corpus membership. Do not treat an assisted audit as fresh blinded validation.'}

    def _link_outcome(self, db, session_id, paper_id, event_id, kind):
        value,packet=self._bound_source(db,session_id,paper_id);source_sha=content_hash(value)
        event = next((e for e in _history(db, paper_id) if e['event_id'] == event_id), None)
        expected_authority = 'human_authorized' if kind == 'authorization' else 'non_authoritative'
        if not event or event['producer_type'] != 'human' or event['producer_id'] != packet['reviewer_id'] or event['authority_state'] != expected_authority:
            raise ContractError('assisted workflow cannot fabricate human judgment or authority')
        payload = {'schema': 'corpustrail-audit-human-outcome/v1', 'session_id': session_id,
            'paper_id': paper_id, 'audit_id': value['audit_id'], 'source_sha256': source_sha,
            'review_event_id': event_id, 'review_event_sha256': content_hash(event), 'kind': kind,
            'actor': event['producer_id'], 'created_at': event['created_at'], 'authority_state': expected_authority}
        lid = identifier('curation-outcome', payload)
        old = db.execute('SELECT payload_json FROM ct_curation_outcomes WHERE link_id=?', (lid,)).fetchone()
        if old:
            if json.loads(old[0]) != payload: raise ContractError('audit outcome integrity changed')
        else: db.execute('INSERT INTO ct_curation_outcomes VALUES (?,?,?,?,?,?,?)', (lid, value['audit_id'], session_id, paper_id, event_id, kind, canonical(payload)))
        for result_id in value['result_ids']:
            row = db.execute('SELECT run_id,position FROM ct_classifier_results WHERE result_id=?', (result_id,)).fetchone()
            result = storage.result(db, row[0], row[1])
            if result['paper_id'] != paper_id: raise ContractError('human outcome source differs')
            if result['kind'] != 'assessment': continue  # Failure is not a proposal.
            link = {'schema': 'corpustrail-assessment-human-link/v1', 'assessment_id': result_id,
                'review_event_id': event_id, 'review_event_sha256': content_hash(event), 'audit_outcome_id': lid,
                'kind': kind, 'engine_input_sha256': result['input_sha256'],
                'review_evidence_snapshot_sha256': value['review_evidence_snapshot_sha256'],
                'original_producer_unchanged': True, 'authority_state': expected_authority}
            link_id = identifier('assessment-human-link', link)
            prior = db.execute('SELECT payload_json FROM ct_classifier_authority_links WHERE link_id=?', (link_id,)).fetchone()
            if prior:
                if json.loads(prior[0]) != link: raise ContractError('assessment/human link integrity changed')
            else: db.execute('INSERT INTO ct_classifier_authority_links VALUES (?,?,?,?)', (link_id, result_id, event_id, canonical(link)))

    def review_command(self, session_id, **command):
        with project_use(self.project.root), connection(self.project.database_path, write=True) as db:
            self._binding(db,session_id)
            require(db)
            if not is_assisted(db, session_id): raise ContractError('choose an explicitly assisted session')
            result = GuidedReviewService(self.project, _db=db).command(session_id, **command)
            operation = result['result']
            if operation.get('observation_event_id'):
                self._link_outcome(db, session_id, operation['paper_id'], operation['observation_event_id'], 'observation')
            for link in operation.get('links', []):
                self._link_outcome(db, session_id, link['paper_id'], link['authority_event_id'], 'authorization')
            return result

    def outcomes(self, audit_id, *, offset=0, limit=20, cutoff=None):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            _record(db, audit_id)
            cutoff = _cutoff(db, 'ct_curation_outcomes', cutoff, offset)
            total = db.execute('SELECT COUNT(*) FROM ct_curation_outcomes WHERE audit_id=? AND rowid<=?', (audit_id,cutoff)).fetchone()[0]
            items = []
            for row in db.execute('SELECT * FROM ct_curation_outcomes WHERE audit_id=? AND rowid<=? ORDER BY rowid LIMIT ? OFFSET ?', (audit_id, cutoff, limit, offset)):
                value = json.loads(row['payload_json'])
                if identifier('curation-outcome', value) != row['link_id']: raise ContractError('audit outcome hash changed')
                items.append({'link_id': row['link_id'], **value})
            return {'audit_id': audit_id, 'cutoff': cutoff, 'total': total, 'items': items,
                'next_offset': offset + limit if offset + limit < total else None,
                'notice': 'Saved human observations and explicit authorizations are separate append-only events. Repeated or corrected observations are history, not a disjoint count of audited papers.'}

    def assisted_sessions(self, audit_id, *, offset=0, limit=20, cutoff=None):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            _record(db, audit_id)
            cutoff = _cutoff(db, 'ct_curation_sessions', cutoff, offset)
            total = db.execute('SELECT COUNT(*) FROM ct_curation_sessions WHERE audit_id=? AND rowid<=?', (audit_id,cutoff)).fetchone()[0]
            values = []
            for row in db.execute('SELECT * FROM ct_curation_sessions WHERE audit_id=? AND rowid<=? ORDER BY rowid LIMIT ? OFFSET ?', (audit_id, cutoff, limit, offset)):
                payload = json.loads(row['payload_json'])
                if payload['session_id'] != row['session_id'] or payload['audit_id'] != audit_id or payload['command_sha256'] != row['command_sha256']:
                    raise ContractError('assisted session binding changed')
                _,packet=self._binding(db,row['session_id']);_,state,_,_=_load(db,row['session_id'])
                values.append({'session_id': row['session_id'], 'reviewer_id': packet['reviewer_id'],
                    'created_at': packet['created_at'], 'lifecycle': state['lifecycle'], 'published': bool(state['publication'])})
            return {'audit_id': audit_id, 'cutoff': cutoff, 'total': total, 'items': values, 'next_offset': offset + limit if offset + limit < total else None}

    def _correction(self, db, *, request_id, run_id, audit_id, paper_id, reference_version_id, actor,
                    created_at, config_event_id, label, evidence_used, rationale, attest, replace_existing):
        require(db); command_id(request_id)
        source = storage.run(db, run_id); plan = storage.plan(db, source['plan_id'])
        if attest is not True or replace_existing is not True:
            raise ContractError('explicitly attest your human label and successor replacement of active labels for this paper')
        audit_source = None
        if audit_id is not None:
            audit = _record(db, audit_id)
            if run_id not in {audit['run_id'],audit['compare_run_id']}:
                raise ContractError('correction run is not a source of the selected frozen audit')
            if not db.execute('SELECT 1 FROM ct_curation_audit_members WHERE audit_id=? AND paper_id=?', (audit_id, paper_id)).fetchone():
                raise ContractError('paper is outside this frozen audit')
            audit_source = {'member_manifest_sha256':audit['member_manifest_sha256'], 'source_revision':audit['source_revision']}
        row = db.execute('SELECT position FROM ct_classifier_inputs WHERE plan_id=? AND paper_id=?', (source['plan_id'], paper_id)).fetchone()
        if row is None: raise ContractError('reference correction source is outside this run population')
        exact = storage.result(db, run_id, row[0])
        _, assignments = reference_storage.stored(db, reference_version_id)
        supersedes = sorted(aid for aid, value in assignments.items() if value['paper_id'] == paper_id)
        lineage = {'run_id': run_id, 'plan_id': source['plan_id'], 'paper_id': paper_id, 'audit_id': audit_id,
            'result_id': exact['result_id'] if exact else None, 'old_reference_version_id': plan['reference_version_id'],
            'selected_parent_reference_version_id': reference_version_id,'frozen_audit_source':audit_source}
        change = {'action': 'assign', 'paper_id': paper_id, 'label': label,
            'producer': {'type': 'human', 'id': actor, 'version': 'manual/v1'}, 'human_attested': True,
            'rationale': rationale, 'evidence_used': evidence_used, 'supersedes': supersedes,
            'source_assignment_ids': supersedes, 'source_event_id': None, 'source_artifact_sha256': None,
            'source_record': 'curation-source:' + content_hash(lineage).split(':')[1]}
        fields = dict(request_id=request_id, name='Explicit curation reference correction', actor=actor,
            parent=reference_version_id, changes=[change], created_at=created_at, config_event_id=config_event_id)
        return fields, lineage

    def preview_correction(self, **fields):
        with connection(self.project.database_path) as db:
            reference_fields, lineage = self._correction(db, **fields)
            value = ReferenceService(self.project, _db=db).preview(**reference_fields)
            return {'reference': value, 'source': lineage, 'preview_sha256': content_hash({'reference': value, 'source': lineage})}

    def commit_correction(self, *, expected_preview_sha256, **fields):
        with project_use(self.project.root), connection(self.project.database_path, write=True) as db:
            require(db); command_id(fields['request_id'])
            prior = db.execute('SELECT event_id,payload_json FROM ct_curation_workflow_events WHERE request_id=?', (fields['request_id'],)).fetchone()
            if prior:
                value = json.loads(prior[1])
                if value['command_sha256'] != content_hash(fields) or value['preview_sha256'] != expected_preview_sha256:
                    raise ContractError('correction command differs from its completed input')
                if identifier('curation-workflow', value) != prior[0]: raise ContractError('correction lineage changed')
                return {'event_id': prior[0], **value, 'replayed': True}
            reference_fields, lineage = self._correction(db, **fields)
            reference = ReferenceService(self.project, _db=db).preview(**reference_fields)
            if content_hash({'reference': reference, 'source': lineage}) != expected_preview_sha256:
                raise ContractError('reference correction preview changed')
            saved = ReferenceService(self.project, _db=db).commit(**reference_fields, expected_preview_sha256=reference['preview_sha256'])
            value = {'schema': 'corpustrail-curation-reference-correction/v1', 'kind': 'reference_correction',
                'request_id': fields['request_id'], 'command_sha256': content_hash(fields),
                'preview_sha256': expected_preview_sha256, 'source': lineage, 'reference_version_id': saved['version_id'],
                'actor': fields['actor'], 'created_at': fields['created_at'],
                'notice': 'Explicit human-attested successor reference version. No human review, membership, retraining or reassessment was performed.'}
            eid = identifier('curation-workflow', value)
            db.execute('INSERT INTO ct_curation_workflow_events(event_id,request_id,kind,payload_json) VALUES (?,?,?,?)', (eid, fields['request_id'], 'reference_correction', canonical(value)))
            return {'event_id': eid, **value, 'replayed': False}

    def request_reassessment(self, *, registry, request_id, plan_id, parent_run_id, actor, created_at):
        from .service import ClassificationService
        command_id(request_id); timestamp(created_at); bounded_text(actor, 'explicit reassessment actor', 200)
        command = dict(request_id=request_id, plan_id=plan_id, parent_run_id=parent_run_id, actor=actor, created_at=created_at)
        with project_use(self.project.root), connection(self.project.database_path, write=True) as db:
            require(db)
            prior = db.execute('SELECT event_id,payload_json FROM ct_curation_workflow_events WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                value = json.loads(prior[1])
                if value['command_sha256'] != content_hash(command) or identifier('curation-workflow', value) != prior[0]:
                    raise ContractError('reassessment command or lineage differs')
                return {'event_id': prior[0], **value, 'replayed': True}
            parent = storage.run(db, parent_run_id); old = storage.plan(db, parent['plan_id']); new = storage.plan(db, plan_id)
            if old['definition_sha256'] != new['definition_sha256']:
                raise ContractError('reassessment lineage cannot silently reinterpret a different corpus definition')
            result = ClassificationService(self.project, registry=registry, _db=db).start_run(plan_id,
                request_id=request_id, actor=actor, created_at=created_at, parent_run_id=parent_run_id)
            value = {'schema': 'corpustrail-explicit-reassessment/v1', 'kind': 'reassessment',
                **command, 'command_sha256': content_hash(command), 'run_id': result['run_id'],
                'old_reference_version_id': old['reference_version_id'], 'new_reference_version_id': new['reference_version_id'],
                'old_population_version_id': old['population_version_id'], 'new_population_version_id': new['population_version_id'],
                'notice': 'New run explicitly planned, not executed. Earlier inputs/assessments remain immutable. Reusing corrected validation labels does not establish fresh independent performance.'}
            eid = identifier('curation-workflow', value)
            db.execute('INSERT INTO ct_curation_workflow_events(event_id,request_id,kind,payload_json) VALUES (?,?,?,?)', (eid, request_id, 'reassessment', canonical(value)))
            return {'event_id': eid, **value, 'replayed': False}

    def workflow(self, *, offset=0, limit=20, cutoff=None):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            if not ready(db): return {'total': 0, 'items': [], 'next_offset': None}
            cutoff = _cutoff(db, 'ct_curation_workflow_events', cutoff, offset)
            total = db.execute('SELECT COUNT(*) FROM ct_curation_workflow_events WHERE rowid<=?', (cutoff,)).fetchone()[0]
            items = []
            for row in db.execute('SELECT event_id,payload_json FROM ct_curation_workflow_events WHERE rowid<=? ORDER BY sequence DESC LIMIT ? OFFSET ?', (cutoff, limit, offset)):
                value = json.loads(row[1])
                if identifier('curation-workflow', value) != row[0]: raise ContractError('curation workflow integrity changed')
                items.append({'event_id': row[0], **value})
            return {'cutoff': cutoff, 'total': total, 'items': items, 'next_offset': offset + limit if offset + limit < total else None}
