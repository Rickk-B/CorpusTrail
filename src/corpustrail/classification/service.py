"""Explicit frozen planning and bounded, non-authoritative offline execution."""
from dataclasses import asdict
from contextlib import nullcontext
import json
import time

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, digest_bytes, identifier, now, timestamp
from corpustrail.application.project_use import operation_use, project_use
from corpustrail.populations.contracts import command_id, page, version_id
from corpustrail.references.contracts import bounded_text, exact_id
from .contracts import (Assessment, AssessmentFailure, AssessmentPlan, Budgets, CalibrationBinding,
                        ClassifierPolicy, EngineRequest, ExecutionUnit, ValidationProtocol, json_value)
from .registry import EngineRegistry
from . import inputs, storage


class ClassificationService:
    def __init__(self, project, *, registry=None, _db=None):
        self.project = project
        self.registry = registry if registry is not None else EngineRegistry()
        self._db = _db

    def _connection(self, *, write=False):
        return nullcontext(self._db) if self._db is not None else connection(self.project.database_path, write=write)

    def ready(self):
        with connection(self.project.database_path) as db: return storage.ready(db)

    def engines(self): return self.registry.describe()

    def _fields(self, *, request_id, name, actor, created_at, config_event_id,
                population_version_id, reference_version_id, engine_id, engine_version,
                input_mode='full_set', evidence_basis='best_available', context_ids=(), settings=None,
                policy=ClassifierPolicy(), budgets=Budgets(), validation=ValidationProtocol(), calibration_binding_id=None):
        command_id(request_id); timestamp(created_at)
        bounded_text(name, 'assessment plan name', 200); bounded_text(actor, 'planning actor', 200)
        version_id(population_version_id); exact_id(reference_version_id, 'reference-version')
        if not isinstance(policy, ClassifierPolicy) or not isinstance(budgets, Budgets) or not isinstance(validation, ValidationProtocol):
            raise ContractError('typed assessment policy, budgets and validation protocol required')
        if input_mode not in {'full_set', 'bounded_context'} or evidence_basis not in {'best_available', 'metadata', 'abstract', 'structured_text', 'frozen_context'}:
            raise ContractError('choose an explicit supported input/evidence mode')
        if (input_mode == 'bounded_context') != (evidence_basis == 'frozen_context'):
            raise ContractError('bounded input uses the exact frozen_context basis; full-set input chooses its own explicit evidence rule')
        if not isinstance(context_ids, tuple) or len(set(context_ids)) != len(context_ids):
            raise ContractError('unique immutable selected-context references required')
        for cid in context_ids: exact_id(cid, 'reference-context')
        if calibration_binding_id is not None: exact_id(calibration_binding_id, 'assessment-calibration')
        if settings is None: settings = {}
        if not isinstance(settings, dict): raise ContractError('explicit JSON engine settings required')
        fields = {'request_id': request_id, 'name': name, 'actor': actor, 'created_at': created_at,
            'config_event_id': config_event_id, 'population_version_id': population_version_id,
            'reference_version_id': reference_version_id, 'engine_id': engine_id, 'engine_version': engine_version,
            'input_mode': input_mode, 'evidence_basis': evidence_basis, 'context_ids': sorted(context_ids),
            'settings': settings, 'policy': policy.to_dict(), 'budgets': budgets.to_dict(),
            'validation': validation.to_dict(), 'calibration_binding_id': calibration_binding_id}
        return json.loads(json_value(fields, 1_000_000))

    @staticmethod
    def _calibration(db, bid):
        if bid is None: return None
        row = db.execute('SELECT * FROM ct_classifier_calibrations WHERE binding_id=?', (bid,)).fetchone()
        if row is None: raise ContractError('calibration binding is not in this project')
        value = json.loads(row['payload_json'])
        if identifier('assessment-calibration', value) != bid or value['contract']['source_run_id'] != row['source_run_id'] or row['artifact_sha256'] != value['contract']['artifact_sha256']:
            raise ContractError('calibration provenance integrity changed')
        storage.blob(db, row['artifact_sha256'])
        return {'binding_id': bid, **value}

    def _freeze(self, db, fields, info, *, sink=None):
        storage.require(db)
        calibration = self._calibration(db, fields['calibration_binding_id'])
        if fields['input_mode'] not in info['input_modes']:
            raise ContractError('engine does not support the selected input mode')
        if fields['policy']['score_type'] is not None and fields['policy']['score_type'] not in info['score_types']:
            raise ContractError('policy score type is not an engine capability')
        if calibration and (calibration['engine_sha256'] != content_hash(info) or calibration['settings_sha256'] != content_hash(fields['settings'])):
            raise ContractError('calibration provenance belongs to another engine/configuration identity')
        descriptor, validation = inputs.freeze(self.project, db, {**fields, 'calibration': calibration}, sink=sink)
        return descriptor, validation

    @staticmethod
    def _header(fields, info, descriptor, validation, prepared):
        body = canonical(validation).encode()
        return {**descriptor, 'request_id': fields['request_id'], 'name': fields['name'], 'actor': fields['actor'],
            'created_at': fields['created_at'], 'command_sha256': content_hash(fields),
            'request_sha256': content_hash(descriptor), 'engine': info, 'engine_sha256': content_hash(info),
            'settings': fields['settings'], 'settings_sha256': content_hash(fields['settings']),
            'engine_plan': prepared.to_dict(), 'validation_snapshot_sha256': digest_bytes(body),
            'authority': 'non_authoritative', 'transfer_sha256': content_hash({'input_request': descriptor,
                'engine': info, 'settings': fields['settings']}),
            'calibration_state': 'declared_unvalidated' if fields['calibration_binding_id'] else 'not_calibrated'}

    @staticmethod
    def public(header):
        return {k: v for k, v in header.items() if k not in {'input_chunk_hashes', 'engine_plan', 'validation_snapshot_sha256'}}

    def _prepared(self, fields):
        engine, info = self.registry.get(fields['engine_id'], fields['engine_version'])
        with connection(self.project.database_path) as db:
            descriptor, validation = self._freeze(db, fields, info)
        request = EngineRequest(content_hash(descriptor), canonical(descriptor), content_hash(info), canonical(fields['settings']))
        prepared = engine.prepare(request)
        if not isinstance(prepared, AssessmentPlan): raise ContractError('engine preparation must return a typed immutable plan')
        expected = (request.request_sha256, content_hash(info), content_hash(fields['settings']))
        if (prepared.request_sha256, prepared.engine_sha256, prepared.settings_sha256) != expected:
            raise ContractError('engine preparation does not bind the exact frozen request/configuration')
        header = self._header(fields, info, descriptor, validation, prepared)
        return header, prepared

    def prepare(self, **values):
        header, _ = self._prepared(self._fields(**values))
        return {**self.public(header), 'preview_sha256': content_hash(header)}

    def commit_plan(self, *, expected_preview_sha256, **values):
        fields = self._fields(**values)
        with project_use(self.project.root):
            with connection(self.project.database_path) as db:
                storage.require(db)
                prior = db.execute('SELECT plan_id,request_sha256 FROM ct_classifier_plans WHERE request_id=?', (fields['request_id'],)).fetchone()
                if prior:
                    if prior['request_sha256'] != content_hash(fields): raise ContractError('plan command cannot be reused with different inputs')
                    header = storage.plan(db, prior['plan_id'])
                    if content_hash(header) != expected_preview_sha256: raise ContractError('completed plan preview differs')
                    return {'plan_id': prior['plan_id'], **self.public(header), 'replayed': True}
            # Engine callbacks never execute while holding a scientific write transaction.
            proposed, prepared = self._prepared(fields)
            if content_hash(proposed) != expected_preview_sha256:
                raise ContractError('assessment preview changed; inspect and prepare again')
            info = proposed['engine']
            pid = identifier('assessment-plan', proposed)
            with connection(self.project.database_path, write=True) as db:
                prior = db.execute('SELECT plan_id,request_sha256 FROM ct_classifier_plans WHERE request_id=?', (fields['request_id'],)).fetchone()
                if prior:
                    header = storage.plan(db, prior['plan_id'])
                    if prior['plan_id'] != pid: raise ContractError('concurrent assessment plan command differs')
                    return {'plan_id': pid, **self.public(header), 'replayed': True}
                def sink(kind, position, record, body):
                    blob_sha = storage.put_blob(db, body) if body is not None else None
                    if kind == 'candidate':
                        db.execute('INSERT INTO ct_classifier_inputs VALUES (?,?,?,?,?,?)',
                            (pid, position, record['paper_id'], blob_sha, canonical(record), content_hash(record)))
                    else:
                        db.execute('INSERT INTO ct_classifier_references VALUES (?,?,?,?,?,?,?)',
                            (pid, position, record['paper_id'], record['decision'], blob_sha, canonical(record), content_hash(record)))
                frozen, validation = self._freeze(db, fields, info, sink=sink)
                header = self._header(fields, info, frozen, validation, prepared)
                if header != proposed: raise ContractError('assessment evidence/context changed before commit')
                storage.put_blob(db, canonical(validation).encode())
                storage.put_blob(db, canonical({'input_request': frozen, 'engine': info, 'settings': fields['settings']}).encode())
                db.execute('INSERT INTO ct_classifier_plans(plan_id,request_id,request_sha256,population_version_id,reference_version_id,config_event_id,payload_json) VALUES (?,?,?,?,?,?,?)',
                    (pid, fields['request_id'], content_hash(fields), fields['population_version_id'], fields['reference_version_id'], fields['config_event_id'], canonical(header)))
                return {'plan_id': pid, **self.public(header), 'replayed': False}

    def inspect_plan(self, pid):
        with connection(self.project.database_path) as db: return {'plan_id': pid, **self.public(storage.plan(db, pid))}

    def plan_inputs(self, pid, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            header = storage.plan(db, pid)
            return {'plan_id': pid, 'total': header['candidate_count'], 'items': storage.items(db, pid, offset=offset, limit=limit),
                    'next_offset': offset + limit if offset + limit < header['candidate_count'] else None}

    def exact_input(self, pid, paper_id):
        exact_id(paper_id, 'ct-paper')
        with connection(self.project.database_path) as db:
            storage.plan(db, pid)
            row = db.execute('SELECT position FROM ct_classifier_inputs WHERE plan_id=? AND paper_id=?', (pid, paper_id)).fetchone()
            if row is None: raise ContractError('paper is outside this frozen plan')
            record = storage.items(db, pid, offset=row[0], limit=1)[0]
            return {'plan_id': pid, **record, 'input': json.loads(storage.blob(db, record['input_blob_sha256']))}

    def exact_request(self, pid):
        with connection(self.project.database_path) as db:
            head = storage.plan(db, pid)
            return {'plan_id': pid, 'sha256': head['transfer_sha256'],
                    'request': json.loads(storage.blob(db, head['transfer_sha256']))}

    def start_run(self, pid, *, request_id, actor, created_at, parent_run_id=None, transfer_sha256=None):
        command_id(request_id); timestamp(created_at); bounded_text(actor, 'execution actor', 200)
        command = {'plan_id': pid, 'request_id': request_id, 'actor': actor, 'created_at': created_at,
                   'parent_run_id': parent_run_id, 'transfer_sha256': transfer_sha256}
        json_value(command)
        rid = identifier('assessment-run', command)
        with project_use(self.project.root), self._connection(write=True) as db:
            head = storage.plan(db, pid)
            prior = db.execute('SELECT run_id FROM ct_classifier_runs WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                if prior[0] != rid: raise ContractError('run request identity cannot be reused with different content')
                storage.run(db, rid)
                return {'run_id': rid, 'replayed': True}
            self._execution_guard(db, head)
            if parent_run_id is not None: storage.run(db, parent_run_id)
            if head['engine']['locality'] == 'remote_declared_mock' and transfer_sha256 != head['transfer_sha256']:
                raise ContractError('explicit consent for the exact candidate/reference/definition payload is required')
            if head['engine']['locality'] == 'local' and transfer_sha256 is not None:
                raise ContractError('local execution has no remote transfer authorization')
            db.execute('INSERT INTO ct_classifier_runs(run_id,plan_id,parent_run_id,request_id,payload_json) VALUES (?,?,?,?,?)',
                       (rid, pid, parent_run_id, request_id, canonical(command)))
            storage.append_event(db, rid, 'planned', created_at, actor=actor)
        return {'run_id': rid, 'replayed': False}

    def _execution_guard(self, db, head):
        if latest_config(db)[0] != head['config_event_id']:
            raise ContractError('configuration changed; old plan is preserved but new execution requires replanning')
        engine, info = self.registry.get(head['engine']['engine_id'], head['engine']['version'])
        if content_hash(info) != head['engine_sha256'] or inputs.implementation_hash() != head['implementation_sha256']:
            raise ContractError('engine or execution implementation changed; prepare a new plan')
        return engine

    def inspect_run(self, rid):
        with connection(self.project.database_path) as db:
            run = storage.run(db, rid); plan = storage.plan(db, run['plan_id']); event, revision = storage.event(db, rid)
            primary = {'include': 0, 'exclude': 0, 'uncertain': 0, 'failed': 0}
            for row in db.execute('SELECT kind,outcome,COUNT(*) AS n FROM ct_classifier_results WHERE run_id=? GROUP BY kind,outcome', (rid,)):
                primary['failed' if row['kind'] == 'failure' else row['outcome']] = row['n']
            processed = sum(primary.values()); remaining = plan['candidate_count'] - processed
            return {'run_id': rid, **run, 'status': event['status'], 'revision': revision, 'candidate_count': plan['candidate_count'],
                'primary_counts': {**primary, 'not_assessed': remaining}, 'processed': processed,
                'terminal': remaining == 0, 'authority': 'non_authoritative'}

    def results(self, rid, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            run = storage.run(db, rid); total = storage.plan(db, run['plan_id'])['candidate_count']
            positions = [r[0] for r in db.execute('SELECT position FROM ct_classifier_results WHERE run_id=? ORDER BY position LIMIT ? OFFSET ?', (rid, limit, offset))]
            count = db.execute('SELECT COUNT(*) FROM ct_classifier_results WHERE run_id=?', (rid,)).fetchone()[0]
            return {'run_id': rid, 'population_count': total, 'recorded_count': count,
                'items': [storage.result(db, rid, pos) for pos in positions], 'next_offset': offset + limit if offset + limit < count else None}

    def runs(self, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            if not storage.ready(db): return {'available': False, 'total': 0, 'items': [], 'next_offset': None}
            total = db.execute('SELECT COUNT(*) FROM ct_classifier_runs').fetchone()[0]
            ids = [r[0] for r in db.execute('SELECT run_id FROM ct_classifier_runs ORDER BY sequence LIMIT ? OFFSET ?', (limit, offset))]
        return {'available': True, 'total': total, 'items': [self.inspect_run(rid) for rid in ids],
                'next_offset': offset + limit if offset + limit < total else None}

    def _unit(self, pid, head, record):
        with connection(self.project.database_path) as db:
            body = storage.blob(db, record['input_blob_sha256']).decode('utf-8')
        payload = json.loads(body)
        def references():
            if head['input_mode'] == 'bounded_context':
                for value in payload['references']: yield canonical(value)
                return
            hashes = []; decisions = []
            with connection(self.project.database_path) as db:
                rows = db.execute('SELECT * FROM ct_classifier_references WHERE plan_id=? ORDER BY position', (pid,))
                for row in rows:
                    value = json.loads(row['payload_json'])
                    if (content_hash(value) != row['content_sha256'] or value['paper_id'] != row['paper_id']
                            or value['decision'] != row['decision'] or value.get('input_blob_sha256') != row['input_blob_sha256']):
                        raise ContractError('frozen reference-input integrity changed')
                    decisions.append(value)
                    if value['decision'] != 'eligible' or head['self_match'] == 'exclude' and value['paper_id'] == record['paper_id']:
                        continue
                    exact = storage.blob(db, value['input_blob_sha256']).decode('utf-8')
                    hashes.append(value['input_blob_sha256'])
                    yield exact
            if content_hash(decisions) != head['reference_input_manifest_sha256'] or content_hash(hashes) != payload['reference_input_manifest_sha256']:
                raise ContractError('full-set context manifest changed')
        return ExecutionUnit(pid, record['input_blob_sha256'], body, record['reference_count'], references)

    @staticmethod
    def _validated_output(value, record, head, allowed_hashes):
        if type(value) is AssessmentFailure:
            if value.paper_id != record['paper_id']: raise ContractError('failure identifies another candidate')
            return 'failure', value.to_dict()
        if type(value) is not Assessment: raise ContractError('typed assessment output required; unsupported fields cannot claim authority')
        data = value.to_dict()
        if data['paper_id'] != record['paper_id'] or not set(data['evidence_hashes']) <= allowed_hashes:
            raise ContractError('assessment cites a paper or evidence outside the frozen request')
        target = record['evidence_snapshot']['available']
        used = record['evidence_snapshot']['used']
        if data['outcome'] != 'uncertain' and not {target[k]['sha256'] for k in used} & set(data['evidence_hashes']):
            raise ContractError('a scientific direction requires support from the actual candidate input')
        score = data['score']; policy = head['policy']
        if score is not None:
            if score['score_type'] not in head['engine']['score_types'] or score['score_type'] != policy['score_type']:
                raise ContractError('score semantics differ from the frozen engine/policy')
            if score['score_type'] == 'calibrated_probability':
                raise ContractError('unvalidated calibration provenance cannot establish calibrated probability')
            binding = head['calibration']
            expected = binding['contract']['calibration_id'] if binding else None
            if score['calibration_id'] != expected:
                raise ContractError('score calibration identity differs from its frozen provenance')
            if policy['include_band'] is not None and data['outcome'] != 'uncertain':
                low, high = policy[data['outcome'] + '_band']
                if not low <= score['value'] <= high: raise ContractError('assessment contradicts its explicit score band')
        elif policy['score_type'] is not None and data['outcome'] != 'uncertain':
            raise ContractError('score-based policy requires a score for a directional assessment')
        return 'assessment', data

    @staticmethod
    def _preservable_response(value, maximum):
        try:
            raw = asdict(value) if type(value) in (Assessment, AssessmentFailure) else value
            return json_value(raw, maximum).encode(), 'retained_untrusted_json'
        except Exception:
            # Never persist raw exception messages, secrets, arbitrary repr(),
            # executable objects or an unbounded provider response.
            return b'{"rejected_output":"unsafe_nonjson_or_over_budget"}', 'unsafe_output_not_retained'

    def _write_result(self, db, run, rid, head, position, record, value, at, *, forced_reason=None):
        attempt = db.execute('SELECT * FROM ct_classifier_attempts WHERE run_id=? AND position=?', (rid, position)).fetchone()
        attempt_value = json.loads(attempt['payload_json'])
        if content_hash(attempt_value) != attempt['content_sha256']:
            raise ContractError('assessment attempt provenance changed')
        raw, retained = self._preservable_response(value, head['budgets']['max_output_bytes'])
        try:
            if forced_reason: raise ContractError('execution did not return a scientific response')
            allowed = set(record['inline_evidence_hashes'])
            if head['input_mode'] == 'full_set':
                decisions = []; selected = []
                for row in db.execute('SELECT payload_json,content_sha256 FROM ct_classifier_references WHERE plan_id=? ORDER BY position', (run['plan_id'],)):
                    reference = json.loads(row['payload_json'])
                    if content_hash(reference) != row['content_sha256']:
                        raise ContractError('reference evidence integrity changed')
                    decisions.append(reference)
                    if reference['decision'] == 'eligible' and not (head['self_match'] == 'exclude' and reference['paper_id'] == record['paper_id']):
                        selected.append(reference['input_blob_sha256']); allowed.add(reference['evidence_sha256'])
                exact = json.loads(storage.blob(db, record['input_blob_sha256']))
                if content_hash(decisions) != head['reference_input_manifest_sha256'] or content_hash(selected) != exact['reference_input_manifest_sha256']:
                    raise ContractError('reference evidence selection changed')
            kind, output = self._validated_output(value, record, head, allowed)
        except (ContractError, TypeError, ValueError, AttributeError):
            kind = 'failure'
            output = AssessmentFailure(record['paper_id'], forced_reason or 'invalid_output').to_dict()
        response_sha = storage.put_blob(db, raw)
        parent = None
        if run['parent_run_id']:
            row = db.execute('SELECT position FROM ct_classifier_results WHERE run_id=? AND paper_id=? AND kind=?',
                             (run['parent_run_id'], record['paper_id'], 'assessment')).fetchone()
            if row: parent = storage.result(db, run['parent_run_id'], row[0])['result_id']
        payload = {'schema': 'corpustrail-immutable-assessment/v1', 'kind': kind, 'run_id': rid,
            'plan_id': run['plan_id'], 'paper_id': record['paper_id'], 'position': position,
            'population_version_id': head['population_version_id'], 'reference_version_id': head['reference_version_id'],
            'context_id': record['context_id'], 'context_input_sha256': record['context_input_sha256'],
            'evidence_snapshot_sha256': record['evidence_snapshot_sha256'], 'input_sha256': record['input_blob_sha256'],
            'task_input_sha256': content_hash({'engine_request_sha256': head['transfer_sha256'], 'candidate_input_sha256': record['input_blob_sha256']}),
            'definition_sha256': head['definition_sha256'], 'config_event_id': head['config_event_id'],
            'policy_sha256': content_hash(head['policy']), 'engine_sha256': head['engine_sha256'],
            'engine': head['engine'], 'calibration_state': head['calibration_state'],
            'created_at': at, 'authority': 'non_authoritative', 'attempt_sha256': attempt['content_sha256'],
            'response_blob_sha256': response_sha, 'response_retention': retained, 'parent_assessment_id': parent,
            'assessment' if kind == 'assessment' else 'failure': output}
        result_id = identifier('assessment' if kind == 'assessment' else 'assessment-failure', payload)
        db.execute('INSERT INTO ct_classifier_results VALUES (?,?,?,?,?,?,?)',
            (result_id, rid, position, record['paper_id'], kind, output['outcome'] if kind == 'assessment' else None, canonical(payload)))

    def execute(self, rid, *, expected_revision, clock=now, cancelled=lambda: False, monotonic=time.monotonic):
        """One explicit bounded continuation. Reservations precede each callback.

        Completed results are never regenerated. Process death leaves an explicit
        ambiguous reservation requiring recover(), which records failure rather
        than automatically resending the invocation.
        """
        exact_id(rid, 'assessment-run')
        with operation_use(self.project.root, rid):
            status = self.inspect_run(rid)
            if status['terminal'] and status['status'] != 'planned': return {**status, 'replayed': True}
            self.verify_plan(status['plan_id'])
            with connection(self.project.database_path, write=True) as db:
                run = storage.run(db, rid); head = storage.plan(db, run['plan_id'])
                event, revision = storage.event(db, rid)
                if revision != expected_revision: raise ContractError('stale assessment lifecycle revision')
                if event['status'] == 'running': raise ContractError('interrupted execution must be inspected/recovered before continuation')
                pending = db.execute('SELECT 1 FROM ct_classifier_attempts a LEFT JOIN ct_classifier_results r USING(run_id,position) WHERE a.run_id=? AND r.result_id IS NULL LIMIT 1', (rid,)).fetchone()
                if pending: raise ContractError('unfinished invocation must be explicitly recovered; no automatic resend')
                engine = self._execution_guard(db, head)
                at = clock(); timestamp(at)
                running = storage.append_event(db, rid, 'running', at, expected=revision, actor=run['actor'])
            spent = 0; stopped = False; started = monotonic()
            try:
                while spent < head['budgets']['max_items_per_execution']:
                    if monotonic() - started >= head['budgets']['max_seconds_per_execution']: break
                    if cancelled(): stopped = True; break
                    take = min(head['budgets']['chunk_size'], head['budgets']['max_items_per_execution'] - spent)
                    with connection(self.project.database_path, write=True) as db:
                        if storage.event(db, rid)[1] != running: raise ContractError('assessment lifecycle changed during execution')
                        self._execution_guard(db, head)
                        positions = [r[0] for r in db.execute('SELECT i.position FROM ct_classifier_inputs i LEFT JOIN ct_classifier_attempts a ON a.run_id=? AND a.position=i.position WHERE i.plan_id=? AND a.position IS NULL ORDER BY i.position LIMIT ?', (rid, run['plan_id'], take))]
                        records = [storage.items(db, run['plan_id'], offset=pos, limit=1)[0] for pos in positions]
                        for pos, record in zip(positions, records):
                            attempt = {'run_id': rid, 'position': pos, 'paper_id': record['paper_id'],
                                'input_sha256': record['input_blob_sha256'], 'started_at': clock(), 'lifecycle_revision': running}
                            timestamp(attempt['started_at'])
                            db.execute('INSERT INTO ct_classifier_attempts VALUES (?,?,?,?)', (rid, pos, canonical(attempt), content_hash(attempt)))
                    if not positions: break
                    units = tuple(self._unit(run['plan_id'], head, record) for record in records)
                    reason = None
                    try:
                        outputs = engine.assess(AssessmentPlan(**head['engine_plan']), units)
                        if not isinstance(outputs, tuple) or len(outputs) != len(units):
                            outputs = tuple(outputs for _ in units); reason = 'invalid_output'
                    except Exception:
                        outputs = tuple(None for _ in units); reason = 'engine_error'
                    at = clock(); timestamp(at)
                    with connection(self.project.database_path, write=True) as db:
                        if storage.event(db, rid)[1] != running: raise ContractError('assessment lifecycle changed before result commit')
                        for pos, record, output in zip(positions, records, outputs):
                            self._write_result(db, run, rid, head, pos, record, output, at, forced_reason=reason)
                    spent += len(units)
                status = self.inspect_run(rid)
                state = ('interrupted' if stopped else 'completed' if status['terminal'] and not status['primary_counts']['failed']
                         else 'failed' if status['terminal'] and status['primary_counts']['failed'] == head['candidate_count'] else 'partial')
                with connection(self.project.database_path, write=True) as db:
                    storage.append_event(db, rid, state, clock(), expected=running, actor=run['actor'])
            except BaseException as original:
                try:
                    self._recover_reserved(rid, expected=running, actor=run['actor'], at=clock())
                except Exception:
                    original.add_note('Assessment interruption receipt could not be written; inspect the durable reservation before recovery.')
                raise
            return {**self.inspect_run(rid), 'replayed': False}

    def _recover_reserved(self, rid, *, expected, actor, at):
        timestamp(at)
        with connection(self.project.database_path, write=True) as db:
            run = storage.run(db, rid); head = storage.plan(db, run['plan_id'])
            event, revision = storage.event(db, rid)
            if revision != expected or event['status'] != 'running': raise ContractError('recovery requires the exact unfinished lifecycle revision')
            positions = [r[0] for r in db.execute('SELECT a.position FROM ct_classifier_attempts a LEFT JOIN ct_classifier_results r USING(run_id,position) WHERE a.run_id=? AND r.result_id IS NULL ORDER BY a.position', (rid,))]
            for pos in positions:
                record = storage.items(db, run['plan_id'], offset=pos, limit=1)[0]
                self._write_result(db, run, rid, head, pos, record, None, at, forced_reason='interrupted_no_response')
            storage.append_event(db, rid, 'interrupted', at, expected=expected, actor=actor)

    def recover(self, rid, *, expected_revision, actor, created_at):
        bounded_text(actor, 'recovery actor', 200)
        with operation_use(self.project.root, rid):
            self._recover_reserved(rid, expected=expected_revision, actor=actor, at=created_at)
        return self.inspect_run(rid)

    def register_calibration(self, contract, body, *, actor, created_at):
        if not isinstance(contract, CalibrationBinding): raise ContractError('typed calibration provenance required')
        raw = contract.to_dict(); bounded_text(actor, 'calibration registrar', 200); timestamp(created_at)
        if not isinstance(body, bytes) or len(body) > 1_000_000 or digest_bytes(body) != contract.artifact_sha256:
            raise ContractError('calibration artifact must be bounded exact bytes')
        try: json_value(json.loads(body), 1_000_000)
        except (ValueError, UnicodeError) as exc: raise ContractError('calibration artifacts must be non-secret JSON, never executable models') from exc
        with project_use(self.project.root), connection(self.project.database_path, write=True) as db:
            run = storage.run(db, contract.source_run_id); head = storage.plan(db, run['plan_id'])
            validation = json.loads(storage.blob(db, head['validation_snapshot_sha256']))
            if validation['protocol']['purpose'] != 'calibration' or content_hash(validation['protocol']) != contract.protocol_sha256:
                raise ContractError('calibration provenance must identify its frozen calibration-role protocol')
            if head['policy']['score_type'] != contract.score_type:
                raise ContractError('calibration score semantics differ from its source run')
            if db.execute('SELECT COUNT(*) FROM ct_classifier_results WHERE run_id=?', (contract.source_run_id,)).fetchone()[0] != head['candidate_count']:
                raise ContractError('calibration source run is incomplete')
            value = {'schema': 'corpustrail-calibration-binding/v1', 'contract': raw,
                'engine_sha256': head['engine_sha256'], 'settings_sha256': head['settings_sha256'],
                'label_snapshot_sha256': head['validation_snapshot_sha256'], 'actor': actor, 'created_at': created_at,
                'authority': 'non_authoritative', 'notice': 'Unvalidated calibration provenance; no calibrated probability claim.'}
            bid = identifier('assessment-calibration', value)
            if db.execute('SELECT 1 FROM ct_classifier_calibrations WHERE binding_id=?', (bid,)).fetchone(): self._calibration(db, bid)
            else:
                storage.put_blob(db, body)
                db.execute('INSERT INTO ct_classifier_calibrations VALUES (?,?,?,?)', (bid, contract.source_run_id, contract.artifact_sha256, canonical(value)))
            return {'binding_id': bid, **value}

    def validate(self, rid):
        from .validation import record_validation
        with project_use(self.project.root):
            return record_validation(self.project, rid)

    def audit_preview(self, run_ids, protocol):
        from .validation import audit_preview
        return audit_preview(self.project, run_ids, protocol)

    def verify_plan(self, pid):
        with connection(self.project.database_path) as db:
            head = storage.plan(db, pid); hashes = []
            for offset in range(0, head['candidate_count'], 100):
                for item in storage.items(db, pid, offset=offset, limit=100):
                    storage.blob(db, item['input_blob_sha256']); hashes.append(content_hash(item))
            if len(hashes) != head['candidate_count'] or content_hash(hashes) != head['input_manifest_sha256']:
                raise ContractError('assessment input manifest changed')
            references = []
            for row in db.execute('SELECT * FROM ct_classifier_references WHERE plan_id=? ORDER BY position', (pid,)):
                value = json.loads(row['payload_json'])
                if content_hash(value) != row['content_sha256'] or value['paper_id'] != row['paper_id'] or value.get('input_blob_sha256') != row['input_blob_sha256'] or value['decision'] != row['decision']:
                    raise ContractError('reference-input record changed')
                if row['input_blob_sha256']: storage.blob(db, row['input_blob_sha256'])
                references.append(value)
            if len(references) != head['reference_decision_count'] or content_hash(references) != head['reference_input_manifest_sha256']:
                raise ContractError('reference-input manifest changed')
            storage.blob(db, head['validation_snapshot_sha256'])
            storage.blob(db, head['transfer_sha256'])
            return {'plan_id': pid, 'verified': True, 'input_manifest_sha256': head['input_manifest_sha256'],
                    'candidate_count': head['candidate_count']}

    def reference_inputs(self, pid, paper_id, *, offset=0, limit=20):
        """Explicit bounded inspection of exactly the context offered to an engine."""
        page(offset, limit)
        exact = self.exact_input(pid, paper_id)
        head = self.inspect_plan(pid)
        if head['input_mode'] == 'bounded_context':
            selected = exact['input']['references']
            return {'total': len(selected), 'items': selected[offset:offset + limit],
                    'context_id': exact['context_id'], 'next_offset': offset + limit if offset + limit < len(selected) else None}
        with connection(self.project.database_path) as db:
            query = " FROM ct_classifier_references WHERE plan_id=? AND decision='eligible'"
            params = [pid]
            if head['self_match'] == 'exclude': query += ' AND paper_id<>?'; params.append(paper_id)
            rows = db.execute('SELECT *' + query + ' ORDER BY position LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
            values = []; response_bytes = 0
            for row in rows:
                metadata = json.loads(row['payload_json'])
                if content_hash(metadata) != row['content_sha256'] or metadata['input_blob_sha256'] != row['input_blob_sha256']:
                    raise ContractError('full-set inspection integrity changed')
                body = storage.blob(db, row['input_blob_sha256'])
                if values and response_bytes + len(body) > 1_000_000: break
                response_bytes += len(body); values.append(json.loads(body))
            total = exact['reference_count']
            return {'total': total, 'items': values, 'manifest_sha256': exact['input']['reference_input_manifest_sha256'],
                    'next_offset': offset + len(values) if offset + len(values) < total else None}

    def plans(self, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            if not storage.ready(db): return {'available': False, 'total': 0, 'items': [], 'next_offset': None}
            total = db.execute('SELECT COUNT(*) FROM ct_classifier_plans').fetchone()[0]
            ids = [r[0] for r in db.execute('SELECT plan_id FROM ct_classifier_plans ORDER BY sequence LIMIT ? OFFSET ?', (limit, offset))]
            return {'available': True, 'total': total, 'items': [{'plan_id': pid, **self.public(storage.plan(db, pid))} for pid in ids],
                    'next_offset': offset + limit if offset + limit < total else None}

    def validation_protocol(self, pid):
        """Operational provenance only; never part of a blinded review DTO."""
        with connection(self.project.database_path) as db:
            head = storage.plan(db, pid)
            return json.loads(storage.blob(db, head['validation_snapshot_sha256']))

    def verify_run(self, rid):
        run = self.inspect_run(rid); self.verify_plan(run['plan_id'])
        with connection(self.project.database_path) as db:
            previous = None; revision = 0
            for row in db.execute('SELECT * FROM ct_classifier_run_events WHERE run_id=? ORDER BY revision', (rid,)):
                value = json.loads(row['payload_json']); revision += 1
                if (content_hash(value) != row['content_sha256'] or value['previous_sha256'] != previous
                        or value['revision'] != revision or row['revision'] != revision or value['run_id'] != rid):
                    raise ContractError('assessment lifecycle chain changed')
                previous = row['content_sha256']
            for row in db.execute('SELECT position FROM ct_classifier_results WHERE run_id=? ORDER BY position', (rid,)):
                result = storage.result(db, rid, row[0])
                item = storage.items(db, run['plan_id'], offset=row[0], limit=1)[0]
                attempt = db.execute('SELECT payload_json,content_sha256 FROM ct_classifier_attempts WHERE run_id=? AND position=?', (rid, row[0])).fetchone()
                if (result['paper_id'] != item['paper_id'] or result['input_sha256'] != item['input_blob_sha256']
                        or content_hash(json.loads(attempt[0])) != attempt[1] or result['attempt_sha256'] != attempt[1]):
                    raise ContractError('assessment attempt/input lineage changed')
            return {'run_id': rid, 'verified': True, 'lifecycle_revision': previous, 'result_count': run['processed']}
