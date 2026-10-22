"""Operational assisted controller; never reused by method-blind API routes."""
from pathlib import Path
import json
import threading

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, content_hash, now, identifier
from corpustrail.application.project_use import acquire_project_use, no_links
from corpustrail.classification import ClassificationService, EngineRegistry, Budgets, ClassifierPolicy, ValidationProtocol
from corpustrail.classification.curation import CurationService, AuditSelection, ready
from corpustrail.classification.curation_views import CurationReads, PRIMARY, OVERLAYS
from corpustrail.classification import storage
from corpustrail.curation.sessions import _load
from corpustrail.models.contracts import safe_data
from corpustrail.populations.contracts import command_id, page
from corpustrail.project import Project
from corpustrail.references.service import definition
from .projects import ProjectCommandError, ProjectController
from .reads import ProjectReads
from .review import ReviewController, _session, _handle

SCHEMA = 'corpustrail-local-curation/v1'


class CurationController:
    def __init__(self, *, registry=None, synthetic=False, clock=now):
        self.registry = registry if registry is not None else EngineRegistry()
        self.synthetic = synthetic; self.clock = clock
        self._lock = threading.RLock(); self._workers = {}; self._errors = {}; self._closed = False

    def classifier(self, project): return ClassificationService(project, registry=self.registry)

    def configuration(self, project):
        with connection(project.database_path) as db:
            revision, config = latest_config(db); available = ready(db)
        installed = self.registry.describe()
        methods = [{'id': 'manual', 'label': 'Manual only — method-blind human review', 'available': True,
            'notice': 'No model or classifier required. Human observations and corpus publication remain separate.'}]
        for engine in installed:
            methods.append({'id': engine['engine_id'], 'version': engine['version'], 'available': True,
                'label': ('Synthetic offline example — ' if self.synthetic else 'Installed offline adapter — ') + engine['engine_id'],
                'synthetic_example': self.synthetic, 'input_modes': engine['input_modes'],
                'notice': 'Software fixture only; no scientific performance or real-model interoperability is established.' if self.synthetic else 'Installed capability is not proof of scientific validation.'})
        methods.extend({'id': key, 'label': label, 'available': False, 'notice': 'Unavailable; separate implementation and validation approval required.'}
            for key, label in [('local_embedding', 'Local embedding classifier'), ('external_llm', 'External LLM'),
                               ('typed_model', 'Typed decision adapter'), ('hybrid', 'Hybrid orchestration')])
        return {'schema': SCHEMA, 'available': available, 'assessment_storage_available': project.classification.ready(),
            'project_id': config['project_id'], 'config_event_id': revision, 'definition': definition(config),
            'suggested_time': self.clock(), 'methods': methods, 'authorized_reviewers': list(config['review']['authorized_reviewers']),
            'primary_states': list(PRIMARY), 'overlays': list(OVERLAYS), 'default_engine_selected': False,
            'notice': 'Operational assisted workspace. Engine observations, evidence sufficiency, human review and authoritative membership are different states. No network/model call occurs on open.'}

    def runs(self, project, *, offset=0, limit=20, cutoff=None):
        page(offset, limit)
        with connection(project.database_path) as db:
            if not storage.ready(db): return {'schema': SCHEMA, 'total': 0, 'items': [], 'next_offset': None}
            maximum = db.execute('SELECT COALESCE(MAX(sequence),0) FROM ct_classifier_runs').fetchone()[0]
            if offset and cutoff is None: raise ContractError('continue run choices with their original cutoff')
            if cutoff is None: cutoff = maximum
            if type(cutoff) is not int or not 0 <= cutoff <= maximum: raise ContractError('invalid run-list cutoff')
            total = db.execute('SELECT COUNT(*) FROM ct_classifier_runs WHERE sequence<=?', (cutoff,)).fetchone()[0]
            ids = [r[0] for r in db.execute('SELECT run_id FROM ct_classifier_runs WHERE sequence<=? ORDER BY sequence DESC LIMIT ? OFFSET ?', (cutoff,limit,offset))]
        data = {'total':total,'cutoff':cutoff,'items':[self.classifier(project).inspect_run(rid) for rid in ids],
            'next_offset':offset+limit if offset+limit<total else None}
        for value in data['items']:
            head = self.classifier(project).inspect_plan(value['plan_id'])
            value.update(name=head['name'], created_at=value['created_at'], engine=head['engine'],
                reference_version_id=head['reference_version_id'], population_version_id=head['population_version_id'])
        return {'schema': SCHEMA, **data}

    def run(self, project, run_id):
        with self._lock:
            # Keep lifecycle inspection and local-worker ownership coherent.
            # Otherwise the final event can land after the read but before
            # worker removal, reporting stale 'running' with no worker to poll.
            value = self.classifier(project).inspect_run(run_id)
            head = self.classifier(project).inspect_plan(value['plan_id'])
            worker = self._workers.get((str(project.root), run_id))
            active = bool(worker and worker[0].is_alive())
            error = self._errors.get((str(project.root), run_id))
        available = any(e['engine_id'] == head['engine']['engine_id'] and e['version'] == head['engine']['version'] for e in self.registry.describe())
        with connection(project.database_path) as db:
            internal = storage.plan(db, value['plan_id'])
            prepared = internal['engine_plan']['preparation']
            synthetic = bool(prepared.get('fixture_only') or prepared.get('synthetic_only'))
        return {'schema': SCHEMA, **value, 'plan': head, 'engine_available': available,
            'synthetic_example': synthetic, 'local_worker_active': active, 'diagnostic': error,
            'validation_protocol': self.classifier(project).validation_protocol(value['plan_id'])['protocol'],
            'notice': 'Synthetic software architecture example, not a scientific relevance prediction.' if synthetic else 'Non-authoritative engine observations; inspect actual score meanings and calibration state. No stopping rule is provided.'}

    def results(self, project, run_id, **options):
        value = CurationReads(project).results(run_id, **options)
        reads = ProjectReads(project)
        with connection(project.database_path) as db:
            for item in value['items']:
                item['publication'] = reads._row(db, item['paper_id'])
                for key in ('observation', 'comparison'):
                    if key in item:
                        data = item[key]
                        item[key] = {k: v for k, v in data.items() if k in {'outcome', 'evidence_sufficiency', 'score', 'reason', 'retryable'}}
        return {'schema': SCHEMA, **value}

    def validations(self, project, run_id, *, offset=0, limit=20, cutoff=None):
        page(offset,limit)
        with connection(project.database_path) as db:
            storage.run(db,run_id)
            maximum=db.execute('SELECT COALESCE(MAX(rowid),0) FROM ct_classifier_validations WHERE run_id=?',(run_id,)).fetchone()[0]
            if offset and cutoff is None:raise ContractError('continue validation history with its original cutoff')
            if cutoff is None:cutoff=maximum
            if type(cutoff) is not int or not 0<=cutoff<=maximum:raise ContractError('invalid validation history cutoff')
            total=db.execute('SELECT COUNT(*) FROM ct_classifier_validations WHERE run_id=? AND rowid<=?',(run_id,cutoff)).fetchone()[0]
            items=[]
            for row in db.execute('SELECT validation_id,payload_json FROM ct_classifier_validations WHERE run_id=? AND rowid<=? ORDER BY rowid DESC LIMIT ? OFFSET ?',(run_id,cutoff,limit,offset)):
                value=json.loads(row[1])
                if identifier('assessment-validation',value)!=row[0] or value['run_id']!=run_id:raise ContractError('validation history integrity changed')
                items.append({'validation_id':row[0],**{k:v for k,v in value.items() if k!='result_ids'},
                    'result_count':len(value['result_ids']),'result_ids_sha256':content_hash(value['result_ids'])})
            return {'schema':SCHEMA,'total':total,'cutoff':cutoff,'items':items,'next_offset':offset+limit if offset+limit<total else None}

    def paper(self, project, run_id, paper_id, *, section='target', offset=0, limit=16000, index=0):
        service = self.classifier(project); run = service.inspect_run(run_id); pid = run['plan_id']
        source = CurationReads(project).source(run_id, paper_id)
        if section == 'provenance':
            return {'schema': SCHEMA, **source, 'plan': service.inspect_plan(pid)}
        if section == 'references':
            page(offset, limit)
            data = service.reference_inputs(pid, paper_id, offset=offset, limit=limit)
            return {'schema': SCHEMA, **data, 'items': [{k: v for k, v in item.items() if k != 'text'} for item in data['items']]}
        if section not in {'target', 'reference_text'} or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 32000:
            raise ContractError('choose a bounded exact text segment')
        if section == 'target':
            exact = service.exact_input(pid, paper_id); item = exact['input']['target']
            title = exact['evidence_snapshot']['available']['metadata']['bibliography']['title']
        else:
            if type(index) is not int or index < 0: raise ContractError('choose a reference passage')
            data = service.reference_inputs(pid, paper_id, offset=index, limit=1)
            if not data['items']: raise ContractError('reference passage is outside this exact input')
            item = data['items'][0]; title = None
        body = item['text']
        if offset > len(body): raise ContractError('text segment is outside the frozen representation')
        return {'schema': SCHEMA, 'text': body[offset:offset + limit], 'offset': offset, 'frozen_title':title,
            'total_characters': len(body), 'next_offset': offset + limit if offset + limit < len(body) else None,
            'representation': item['representation'], 'paper_id': item['paper_id'],
            'notice': 'Exact frozen engine input, not current evidence or an attestation that a person read it. Structured text reuses the verified stored representation; no XML is rendered here.'}

    def assisted(self, project, handle, *, section=None, **paging):
        review = ReviewController(); sid = _session(project, handle)
        if section == 'summary': return review.summary_page(project, handle, assisted=True, **paging)
        if section == 'document': return review.document(project, handle, assisted=True, **paging)
        if paging: raise ContractError('assisted session view has no pagination fields')
        base = review.view(project, handle, assisted=True)
        sources = CurationService(project).assisted_sources(sid, base['paper_id'])
        return {**base, 'schema': SCHEMA, 'assisted_sources': sources}

    def _execute(self, project, run_id, expected_revision, cancel, lease):
        try:
            self.classifier(project).execute(run_id, expected_revision=expected_revision, cancelled=cancel.is_set, clock=self.clock)
        except Exception:
            with self._lock:
                self._errors[(str(project.root), run_id)] = 'Bounded execution stopped. Inspect durable results/reservations before explicit continuation or recovery; no automatic retry occurred.'
        finally:
            lease.close()
            with self._lock: self._workers.pop((str(project.root), run_id), None)

    def execute(self, project, run_id, expected_revision):
        key = (str(project.root), run_id)
        with self._lock:
            if self._closed: raise ContractError('this launcher is stopping')
            if key in self._workers: return self.run(project, run_id)
            state = self.classifier(project).inspect_run(run_id)
            if state['revision'] != expected_revision: raise ContractError('run state changed; inspect it before execution')
            if state['terminal']: return self.run(project, run_id)
            if any(t.is_alive() for t, _ in self._workers.values()):
                raise ContractError('another bounded assessment is active; inspect it before starting another')
            lease = acquire_project_use(project.root); event = threading.Event()
            try:
                thread = threading.Thread(target=self._execute, args=(project, run_id, expected_revision, event, lease), daemon=True)
                self._workers[key] = (thread, event); self._errors.pop(key, None); thread.start()
            except BaseException:
                self._workers.pop(key, None); lease.close(); raise
        return self.run(project, run_id)

    def command(self, project, action, body):
        try:
            safe_data(body, secrets=ProjectController._secrets(project.config))
            service = CurationService(project); classifier = self.classifier(project)
            if action == 'upgrade':
                if set(body) != {'request_id', 'confirm_backup', 'project_id', 'config_event_id'} or body['confirm_backup'] is not True:
                    raise ContractError('explicitly confirm backup before enabling curation storage')
                command_id(body['request_id']); config = self.configuration(project)
                if body['project_id'] != config['project_id'] or body['config_event_id'] != config['config_event_id']: raise ContractError('project/configuration changed')
                if config['available']: return {'schema': SCHEMA, 'available': True, 'already_enabled': True}
                no_links(project.root)
                backup = project.config.data_directory + '/curation-upgrades/' + body['request_id'] + '.sqlite3'
                no_links(project.root / Path(backup), missing=True)
                Project.upgrade(project.root, backup=backup, expected_config_event=body['config_event_id'])
                return {'schema': SCHEMA, 'available': True, 'backup_created': True}
            if action in {'plan_preview', 'plan_commit'}:
                fields = {'request_id', 'name', 'actor', 'created_at', 'config_event_id', 'population_version_id', 'reference_version_id', 'engine_id', 'engine_version', 'input_mode', 'context_ids', 'parent_run_id'}
                if action == 'plan_commit': fields.add('expected_preview_sha256')
                if set(body) != fields: raise ContractError('unsupported plan fields; select existing versions and an available offline implementation')
                body = dict(body); parent = body.pop('parent_run_id')
                inherited = {}
                if parent is not None:
                    source = classifier.inspect_run(parent); old = classifier.inspect_plan(source['plan_id'])
                    policy = {**old['policy']}
                    for key in ('include_band','exclude_band'):
                        if policy[key] is not None: policy[key] = tuple(policy[key])
                    inherited = {'settings': old['settings'], 'policy': ClassifierPolicy(**policy),
                        'budgets': Budgets(**old['budgets']),
                        'validation': ValidationProtocol(**classifier.validation_protocol(source['plan_id'])['protocol']),
                        'calibration_binding_id': old['calibration']['binding_id'] if old['calibration'] else None}
                body = {**body, 'context_ids': tuple(body['context_ids']),
                    'evidence_basis': 'frozen_context' if body['input_mode'] == 'bounded_context' else 'best_available',
                    'budgets': Budgets(max_seconds_per_execution=10), **inherited}
                if parent is not None and body['input_mode'] == 'full_set' and old['input_mode'] == 'full_set':
                    body['evidence_basis'] = old['evidence_basis']
                result = (classifier.prepare if action == 'plan_preview' else classifier.commit_plan)(**body)
            elif action == 'start':
                if set(body) != {'request_id', 'plan_id', 'parent_run_id', 'actor', 'created_at'}: raise ContractError('unsupported run request')
                if body['parent_run_id'] is None:
                    result = classifier.start_run(body['plan_id'], **{k: body[k] for k in ('request_id', 'actor', 'created_at')})
                else: result = service.request_reassessment(registry=self.registry, **body)
            elif action == 'execute':
                if set(body) != {'run_id', 'expected_revision'}: raise ContractError('inspect the exact run revision')
                result = self.execute(project, **body)
            elif action == 'recover':
                if set(body) != {'run_id', 'expected_revision', 'actor', 'created_at'}: raise ContractError('explicit recovery provenance required')
                result = classifier.recover(body.pop('run_id'), **body)
            elif action == 'cancel':
                if set(body) != {'run_id'}: raise ContractError('choose the bounded operation to stop')
                with self._lock:
                    worker = self._workers.get((str(project.root), body['run_id']))
                    if worker: worker[1].set()
                result = self.run(project, body['run_id'])
            elif action == 'validate':
                if set(body) != {'run_id'}: raise ContractError('choose an exact frozen run for explicit validation')
                value = classifier.validate(body['run_id'])
                result = {k:v for k,v in value.items() if k!='result_ids'}
                result.update(result_count=len(value['result_ids']),result_ids_sha256=content_hash(value['result_ids']))
            elif action in {'audit_preview', 'audit_commit'}:
                fields = {'request_id', 'name', 'actor', 'created_at', 'config_event_id', 'run_id', 'compare_run_id', 'selection'}
                if action == 'audit_commit': fields.add('expected_preview_sha256')
                if set(body) != fields or not isinstance(body['selection'], dict): raise ContractError('unsupported audit selection fields')
                body = {**body, 'selection': AuditSelection(**{**body['selection'], 'groups': tuple(body['selection']['groups'])})}
                result = (service.preview_audit if action == 'audit_preview' else service.commit_audit)(**body)
            elif action == 'assisted_create':
                if set(body) != {'request_id', 'audit_id', 'reviewer_id', 'config_event_id', 'confirm_assisted'}: raise ContractError('explicit assisted-review selection required')
                result = service.create_assisted(**body); result['handle'] = _handle(result['session_id'])
            elif action == 'review_command':
                if set(body) != {'handle', 'command_id', 'expected_revision', 'action', 'value'}: raise ContractError('unsupported assisted command')
                body = dict(body); sid = _session(project, body.pop('handle'))
                result = service.review_command(sid, **body); result['handle'] = _handle(sid)
            elif action in {'correction_preview', 'correction_commit'}:
                fields = {'request_id', 'run_id', 'audit_id', 'paper_id', 'reference_version_id', 'actor', 'created_at', 'config_event_id', 'label', 'evidence_used', 'rationale', 'attest', 'replace_existing'}
                if action == 'correction_commit': fields.add('expected_preview_sha256')
                if set(body) != fields: raise ContractError('unsupported explicit human correction fields')
                result = (service.preview_correction if action == 'correction_preview' else service.commit_correction)(**body)
            else: raise ContractError('unsupported curation action')
            safe_data(result, secrets=ProjectController._secrets(project.config))
            return {'schema': SCHEMA, **result}
        except (ContractError, TypeError, ValueError) as exc:
            message = str(exc) if isinstance(exc, ContractError) else 'Unsupported curation form fields/types; no automatic retry occurred.'
            raise ProjectCommandError(message, code='curation_conflict', status=409) from exc

    def close(self):
        with self._lock:
            self._closed = True
            for _, event in self._workers.values(): event.set()
        # Workers keep their project leases. Process death leaves CP8 durable
        # reservations; startup never resumes or silently resends them.
