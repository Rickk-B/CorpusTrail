"""Exact remote preview/consent over CP8; CP9 remains the proposal/audit store."""
from contextlib import closing
import json
import threading

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, now, identifier
from corpustrail.application import _workflow_files as files
from corpustrail.application.handoff import fields, text, token
from corpustrail.application.projects import ProjectCommandError
from corpustrail.classification import ClassificationService, Budgets
from corpustrail.classification import storage
from corpustrail.chatgpt.connection import ChatGPTConnection
from corpustrail.chatgpt.engine import ChatGPTEngine, DESTINATION
from corpustrail.chatgpt.transport import ConnectionFailure
from corpustrail.populations.contracts import command_id

SCHEMA = 'corpustrail-local-chatgpt/v1'
MESSAGES = {
    'no_cost_not_verified': 'Assessment is blocked: account-bound prevention of extra charges has not been verified. Sign-in and model availability alone are insufficient.',
    'authentication': 'Connect the intended ChatGPT registration before proceeding.',
    'plan_scope_missing': 'This registration has not granted ChatGPT-plan usage. Reconnect explicitly if eligible.',
    'optional_dependency_missing': 'Install the optional chatgpt extra in this Python environment. Manual review remains available.',
    'ineligible': 'This account or workspace is not eligible for the requested ChatGPT-plan operation.',
    'usage_limit': 'ChatGPT-plan usage limit reached. Completed work is preserved. No credit purchase, billing fallback or automatic retry occurred.',
    'unsupported_reference_evidence': 'This initial adapter accepts metadata/abstract reference examples only. Choose a reference version using those evidence types; full text is not transferred.',
    'resource_limit': 'The selected exact input exceeds the explicit request budget. Choose a smaller frozen population or reference context; nothing was silently truncated.',
}


class ChatGPTController:
    def __init__(self, curation, *, connection_client=None, clock=now, synthetic=False):
        self.curation = curation; self.connection = connection_client if connection_client is not None else ChatGPTConnection()
        self.clock = clock; self.synthetic = synthetic; self._engines = {}; self._lock = threading.RLock(); self.return_url = None

    @staticmethod
    def root(project): return files.location(project, family='handoff') / 'chatgpt' / 'v1'

    def _engine(self, model, profile):
        state = self.connection.status()
        if not state['installed']: raise ConnectionFailure('optional_dependency_missing')
        if not state['connected'] or state['profile_id'] != profile: raise ConnectionFailure('authentication')
        if not state['eligible_scope']: raise ConnectionFailure('plan_scope_missing')
        if not any(m['slug'] == model for m in state['models']):
            raise ContractError('Refresh the account-specific model list explicitly, then choose an available model.')
        key = (profile, model)
        if key not in self._engines:
            engine = ChatGPTEngine(self.connection, profile, model)
            self.curation.registry.register(engine); self._engines[key] = engine
        return self._engines[key]

    def _private_boundary(self, project):
        private = self.connection.store.root.resolve()
        research = project.root.resolve()
        if private.is_relative_to(research) or research.is_relative_to(private):
            raise ProjectCommandError('Keep private ChatGPT credentials separate from research project directories.',
                code='chatgpt_storage_boundary', status=409)

    def configuration(self, project):
        self._private_boundary(project)
        with connection(project.database_path) as db:
            revision, config = latest_config(db)
        return {'schema': SCHEMA, 'connection': self.connection.status(), 'synthetic_fixture': self.synthetic,
            'config_event_id': revision, 'storage_ready': project.classification.ready(),
            'default_model_selected': False, 'destination': DESTINATION,
            'limits': {'papers_per_authorization': 10, 'wire_bytes_per_paper': 32000,
                       'response_bytes_per_paper': 20000, 'requests_per_paper': 1},
            'notice': 'Optional cloud processing. Proposals are not human judgments or corpus membership. Missing abstracts never imply exclusion. No model request occurs on open.'}

    def preview(self, project, body):
        self._private_boundary(project)
        fields(body, {'request_id', 'actor', 'population_version_id', 'reference_version_id', 'model'})
        command_id(body['request_id']); text(body['actor'], 'acting person', 200)
        path = self.root(project) / 'previews' / (body['request_id'] + '.json')
        with closing(files.operation_lease(project, 'chatgpt-preview:' + body['request_id'])):
            if path.exists():
                old = files.read(path)
                if old['command'] != body: raise ContractError('Preview identity belongs to different inputs.')
                return self.inspect(project, body['request_id'])
            if not project.classification.ready():
                raise ProjectCommandError('Enable assessment storage through the existing explicit backed-up upgrade in Curation first.',code='chatgpt_upgrade_required',status=409)
            count = project.populations.inspect(body['population_version_id'])['member_count']
            if not 1 <= count <= 10:
                raise ProjectCommandError('Choose a frozen candidate set of one to ten papers for this bounded authorization.',code='chatgpt_request_budget',status=409)
            status = self.connection.status(); engine = self._engine(body['model'], status['profile_id'])
            revision = self.configuration(project)['config_event_id']
            service = self.curation.classifier(project)
            values = {'request_id': body['request_id'], 'name': 'ChatGPT title/abstract assessment', 'actor': body['actor'],
                'created_at': self.clock(), 'config_event_id': revision,
                'population_version_id': body['population_version_id'], 'reference_version_id': body['reference_version_id'],
                'engine_id': engine.engine_id, 'engine_version': 'v1', 'evidence_basis': 'title_abstract',
                'settings': {'profile_id': status['profile_id'], 'model': body['model'], 'transport': 'chatgpt-plan-responses/v1'},
                'budgets': Budgets(chunk_size=1, max_input_bytes=64000, max_output_bytes=65536,
                    max_items_per_execution=10, max_reference_bytes=32000, max_seconds_per_execution=300)}
            proposed = service.prepare(**values)
            plan = service.commit_plan(**values, expected_preview_sha256=proposed['preview_sha256'])
            manifest = self._manifest(project, plan['plan_id'], engine)
            record = {'schema': SCHEMA, 'command': body, 'plan_id': plan['plan_id'], 'created_at': self.clock(),
                'manifest': manifest, 'transmission_sha256': content_hash(manifest), 'plan_transfer_sha256': plan['transfer_sha256'],
                'actor': body['actor'], 'synthetic_fixture': self.synthetic}
            files.publish(path, record)
        return self.inspect(project, body['request_id'])

    def _manifest(self, project, plan_id, engine):
        service = self.curation.classifier(project); service.verify_plan(plan_id)
        with connection(project.database_path) as db:
            head = storage.plan(db, plan_id)
            if head['candidate_count'] > 10: raise ContractError('Choose a frozen population of one to ten papers for this bounded assessment.')
            records = storage.items(db, plan_id, offset=0, limit=10)
        requests = []
        for record in records:
            unit = service._unit(plan_id, head, record)
            wire = engine.wire(unit)
            requests.append({'paper_id': record['paper_id'], 'input_sha256': record['input_blob_sha256'],
                'evidence_snapshot_sha256': record['evidence_snapshot_sha256'], 'payload': wire,
                'wire_sha256': content_hash({'destination': DESTINATION, 'payload': wire})})
        return {'schema': 'corpustrail-assessment-transmission/v1', 'destination': DESTINATION,
            'profile_id': engine.profile_id, 'model': engine.model, 'engine_sha256': head['engine_sha256'],
            'plan_id': plan_id, 'population_version_id': head['population_version_id'],
            'reference_version_id': head['reference_version_id'], 'definition_sha256': head['definition_sha256'],
            'requests': requests, 'tools': 'none', 'retries': 'none', 'provider_store': False,
            'retention_notice': 'Local scientific history retains exact inputs/outputs. Cloud processing is subject to OpenAI terms; store:false does not guarantee zero retention.'}

    def inspect(self, project, key):
        self._private_boundary(project)
        token(key); record = files.read(self.root(project) / 'previews' / (key + '.json'))
        return {**record, 'preview_id': key, 'preview_sha256': content_hash(record),
                'connection': self.connection.status(), 'authority': 'non_authoritative',
                'notice': 'Preview froze local scientific inputs, not an assessment or membership judgment. Nothing has been sent to a model.'}

    def confirm(self, project, body):
        fields(body, {'request_id', 'preview_id', 'preview_sha256', 'confirmed', 'confirm_external'})
        command_id(body['request_id']); token(body['preview_id'])
        if body['confirmed'] is not True or body['confirm_external'] is not True:
            raise ContractError('Explicitly authorize the exact displayed cloud transfer.')
        with self._lock, closing(files.operation_lease(project, 'chatgpt-confirm:' + body['request_id'])):
            view = self.inspect(project, body['preview_id'])
            if view['preview_sha256'] != body['preview_sha256']: raise ContractError('The exact preview changed; consent is invalid.')
            state = self.connection.status()
            engine = self._engine(view['manifest']['model'], view['manifest']['profile_id'])
            if not state['no_extra_charge_verified']: raise ConnectionFailure('no_cost_not_verified')
            if self._manifest(project, view['plan_id'], engine) != view['manifest']:
                raise ContractError('The transmitted payload changed; prepare and authorize a new preview.')
            path = self.root(project) / 'authorizations' / (body['request_id'] + '.json')
            replayed = path.exists()
            if replayed:
                receipt = files.read(path)
                if receipt['command'] != body: raise ContractError('Authorization identity belongs to another preview.')
            else:
                receipt = {'schema': 'corpustrail-assessment-transfer-authorization/v1', 'command': body,
                    'plan_id': view['plan_id'], 'actor': view['actor'], 'created_at': self.clock(),
                    'transmission_sha256': view['transmission_sha256'], 'manifest': view['manifest'],
                    'transfer_sha256': view['plan_transfer_sha256']}
                files.publish(path, receipt)
            service = self.curation.classifier(project)
            started = service.start_run(receipt['plan_id'], request_id=body['request_id'], actor=receipt['actor'],
                created_at=receipt['created_at'], transfer_sha256=receipt['transfer_sha256'],
                transmission_sha256=receipt['transmission_sha256'])
            rid = started['run_id']
            if not started['replayed']:
                key = (str(project.root), rid)
                def cancelled():
                    worker = self.curation._workers.get(key)
                    return bool(worker and worker[1].is_set())
                engine.authorize(receipt['plan_id'], receipt['manifest'], cancelled=cancelled)
                self.curation.execute(project, rid, service.inspect_run(rid)['revision'], remote_authorized=True)
            return {'schema': SCHEMA, 'run_id': rid, 'replayed': started['replayed'],
                'notice': 'Explicitly authorized execution. Inspect saved proposals in Curation and audits; corpus membership is unchanged.'}

    def command(self, project, action, body):
        self._private_boundary(project)
        try:
            if action == 'preview': return self.preview(project, body)
            if action == 'confirm': return self.confirm(project, body)
            if action in {'connect', 'cancel-connect', 'disconnect', 'models', 'acknowledge-plan'}:
                fields(body, {'confirmed'})
                if body['confirmed'] is not True: raise ContractError('Confirm this connection operation explicitly.')
                if action == 'acknowledge-plan':
                    with self.connection.store.transaction() as state:
                        profile = state['profiles'].get(state['active'])
                        if not profile or not profile.get('refresh_token'): raise ConnectionFailure('authentication')
                        profile['plan_notice_acknowledged'] = True
                    return {'schema': SCHEMA, 'acknowledged': True}
                if action == 'disconnect':
                    for _, event in self.curation._workers.values(): event.set()
                    return {'schema': SCHEMA, **self.connection.disconnect()}
                if any(t.is_alive() for t, _ in self.curation._workers.values()):
                    raise ContractError('Stop the active assessment before changing the connection.')
                if action == 'connect': return {'schema': SCHEMA, **self.connection.begin(return_url=self.return_url)}
                if action == 'cancel-connect': self.connection.cancel_sign_in(); return {'schema': SCHEMA, 'cancelled': True}
                return {'schema': SCHEMA, 'models': self.connection.catalog()}
            raise ContractError('Unsupported ChatGPT operation.')
        except ConnectionFailure as exc:
            raise ProjectCommandError(MESSAGES.get(exc.kind, 'ChatGPT operation stopped (' + exc.kind + '). No automatic retry or billing fallback occurred.'),
                code='chatgpt_' + exc.kind, status=409) from None

    def close(self): self.connection.close()
