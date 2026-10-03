"""Explicit bounded model calls and non-authoritative Knowledge Layer writes.

No automatic extraction, model SDK, vendor selection, retries or tool execution.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import os

from corpustrail import __version__
from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.pipeline import artifact, preserve
from corpustrail._internal.values import ContractError, canonical, confined, content_hash, identifier, now, text, timestamp
from corpustrail.knowledge.evidence import resolve_reference
from .contracts import CAPABILITY, MODES, ModelResponse, TaskSpec, safe_data
from .registry import AdapterRegistry

MAX_BYTES = 2 * 1024 * 1024
PRIVACY_NOTICE = ('Evidence leaves this machine for the declared provider/model. '
                  'Third-party privacy and retention terms apply; CorpusTrail makes no promises about them.')


class ModelService:
    def __init__(self, project, *, registry=None):
        self.project = project
        self.registry = registry if registry is not None else AdapterRegistry()

    def _config(self, workflow_id):
        matches = [c for c in self.project.config.models if c.workflow_id == workflow_id]
        if len(matches) != 1:
            raise ContractError('model workflow is not configured')
        matches[0].validate()
        return matches[0]

    def _secrets(self):
        config = self.project.config
        return tuple(os.environ.get(c.credential_env, '') for c in (*config.providers, *config.models)
                     if c.credential_env)

    def status(self):
        """Read-only; inspect registration without loading third-party plugin code."""
        rows = []
        for c in self.project.config.models:
            adapter = self.registry._adapters.get(c.adapter)
            info = asdict(adapter.info) if adapter else None
            rows.append({'workflow_id': c.workflow_id, 'adapter': c.adapter, 'model': c.model,
                'status': 'available' if adapter else ('installed_not_loaded' if c.adapter in self.registry.available()
                                                     else 'adapter_unavailable'),
                'provider': info,
                'credential_status': ('present' if os.environ.get(c.credential_env) else 'missing')
                    if c.credential_env else ('required_but_not_configured' if adapter and adapter.info.credentials_required
                                            else 'not_configured'),
                'data_leaves_machine': adapter.info.data_leaves_machine if adapter else None})
        result = {'model_providers': rows, 'available_adapters': self.registry.available(),
                  'local_model': 'not_configured' if not rows else 'see_configured_workflows',
                  'external_model': 'not_configured' if not rows else 'see_configured_workflows',
                  'external_evidence_transfer': 'disabled_without_exact_plan_authorization'}
        safe_data(result, secrets=self._secrets())
        return result

    def _evidence(self, paper_id, mode, representation_id, passages):
        metadata = self.project.discovery.metadata(paper_id)
        observations = {x['observation_id']: x for x in self.project.identities.observations(paper_id)}
        reps = {x['event_id']: x for x in self.project.evidence.representations(paper_id)}
        inputs = []

        def add(body, representation, ref, location=None):
            payload = {'paper_id': paper_id, 'evidence_representation': representation,
                       'evidence_reference': ref, 'source': {}}
            with connection(self.project.database_path) as con:
                resolved = resolve_reference(self.project, con, payload)
            sha = resolved.get('artifact_sha256')
            item = {'text': body, 'representation': representation,
                    'content_sha256': content_hash(body), 'source_sha256': sha,
                    'reference': ref, 'location': location, 'trusted': resolved.get('trusted', False)}
            item['evidence_id'] = identifier('model-evidence', item)
            inputs.append(item)

        for field in ('title', 'authors', 'year', 'source'):
            value = metadata['fields'][field]
            source_id = metadata['field_provenance'][field]
            if value not in (None, [], '') and source_id in observations:
                add(value if isinstance(value, str) else canonical(value), 'metadata',
                    {'kind': 'bibliographic_observation', 'observation_id': source_id, 'field': field},
                    {'metadata_field': field})
        if mode == 'abstract':
            value = metadata['fields']['abstract']
            source_id = metadata['field_provenance']['abstract']
            if not value:
                raise ContractError('abstract unavailable; explicitly choose metadata mode instead')
            ref = ({'kind': 'bibliographic_observation', 'observation_id': source_id, 'field': 'abstract'}
                   if source_id in observations else {'kind': 'representation', 'event_id': source_id})
            add(value, 'abstract', ref)
        elif mode in ('full_text', 'selected_passages'):
            rep = reps.get(representation_id)
            if not rep or not rep['payload']['trusted'] or rep['payload']['artifact_validity'] != 'verified' or (
                    rep['payload']['representation'] != 'structured_text' or rep['payload'].get('evidence_depth') != 'document_body'):
                raise ContractError('explicit verified structured document-body representation required')
            body = artifact(self.project, rep['payload']['artifact_sha256']).read_text(encoding='utf-8')
            ref = {'kind': 'representation', 'event_id': representation_id}
            if mode == 'full_text':
                if passages:
                    raise ContractError('full-text mode does not accept passage selectors')
                add(body, 'structured_text', ref)
            else:
                if not passages:
                    raise ContractError('explicit selected passage offsets required')
                for pair in passages:
                    if (not isinstance(pair, (tuple, list)) or len(pair) != 2 or
                            any(type(n) is not int for n in pair) or not 0 <= pair[0] < pair[1] <= len(body)):
                        raise ContractError('invalid passage offsets')
                    add(body[pair[0]:pair[1]], 'structured_text', ref,
                        {'character_start': pair[0], 'character_end': pair[1]})
        elif mode != 'metadata':
            raise ContractError('unknown evidence mode')
        if mode in ('metadata', 'abstract') and (representation_id is not None or passages):
            raise ContractError('document selectors do not belong to metadata/abstract mode')
        if not inputs:
            raise ContractError('no supplied evidence available')
        return inputs

    def plan(self, workflow_id, spec, *, run_id, paper_id, mode='abstract',
             representation_id=None, passages=(), created_at=None):
        """Read-only frozen task, configuration, registry and exact evidence snapshot."""
        text(run_id, 'run ID')
        if not isinstance(spec, TaskSpec) or mode not in MODES or mode not in spec.evidence_modes:
            raise ContractError('task does not support selected evidence mode')
        c = self._config(workflow_id)
        adapter = self.registry.resolve(c.adapter)
        if CAPABILITY not in adapter.info.capabilities:
            raise ContractError('adapter does not support structured assertions')
        vocabulary = self.project.knowledge_store.registry.describe()
        if any(p not in vocabulary['concepts'] for p in spec.predicates):
            raise ContractError('task predicate is not explicitly registered')
        at = created_at or now(); timestamp(at)
        evidence = self._evidence(paper_id, mode, representation_id, passages)
        request = {'run_id': run_id, 'model': c.model, 'endpoint_id': c.endpoint_id,
                   'request_id': identifier('model-request', {'project_id': self.project.config.project_id,
                       'run_id': run_id, 'specification_sha256': spec.sha256,
                       'evidence_ids': [e['evidence_id'] for e in evidence]}),
                   'settings': deepcopy(c.settings), 'specification': spec.to_dict(),
                   'specification_sha256': spec.sha256,
                   'predicate_definitions': {p: json.loads(vocabulary['concepts'][p]) for p in spec.predicates},
                   'output_contract': {'schema': CAPABILITY, 'claims': 'array',
                       'claim_fields': ['predicate', 'raw_value', 'value_datatype', 'evidence_id', 'quote'],
                       'positive_claims': 'exact supporting quote and supplied evidence_id required',
                       'unknown_claims': 'raw_value=null, value_datatype=unknown, evidence_id=null, quote=null'},
                   'evidence': [{k: item[k] for k in ('evidence_id', 'text', 'representation', 'content_sha256')}
                                for item in evidence]}
        body = {'schema': 'corpustrail-model-plan/v0', 'run_id': run_id,
                'project_id': self.project.config.project_id, 'paper_id': paper_id,
                'workflow_id': workflow_id, 'config_event_id': self.project.configuration_history()[-1]['event_id'],
                'configuration': asdict(c), 'adapter': asdict(adapter.info), 'mode': mode,
                'representation_id': representation_id, 'passages': list(passages),
                'registry_sha256': content_hash(vocabulary), 'created_at': at,
                'software_version': __version__, 'evidence': evidence,
                'request': request, 'request_sha256': content_hash(request),
                'notice': PRIVACY_NOTICE if adapter.info.data_leaves_machine else 'Declared local execution; no external transfer.',
                'production_effect': 'none'}
        safe_data(body, secrets=self._secrets())
        if len(canonical(request).encode('utf-8')) > MAX_BYTES:
            raise ContractError('bounded model input exceeded; select smaller evidence explicitly')
        return json.loads(canonical({**body, 'plan_sha256': content_hash(body)}))

    def _validate(self, plan):
        try:
            recreated = self.plan(plan['workflow_id'], TaskSpec.from_dict(plan['request']['specification']),
                run_id=plan['run_id'], paper_id=plan['paper_id'], mode=plan['mode'],
                representation_id=plan['representation_id'], passages=plan['passages'], created_at=plan['created_at'])
            if recreated != plan:
                raise ContractError('stale or altered model plan')
        except (KeyError, TypeError) as exc:
            raise ContractError('invalid model plan') from exc

    def write_plan(self, plan, relative_path):
        self._validate(plan)
        path = confined(self.project.root, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as handle:
            handle.write(canonical(plan) + '\n')
        return {'plan_sha256': plan['plan_sha256'], 'path': relative_path,
                'provider': plan['adapter']['provider_id'], 'model': plan['configuration']['model'],
                'data_leaves_machine': plan['adapter']['data_leaves_machine'], 'notice': plan['notice']}

    def read_plan(self, relative_path):
        plan = json.loads(confined(self.project.root, relative_path).read_text(encoding='utf-8'))
        self._validate(plan)
        return plan

    def _record(self, kind, plan, payload, *, con=None):
        safe_data(payload, secrets=self._secrets())
        envelope = {'kind': kind, 'scope_id': plan['run_id'], 'payload': payload,
                    'paper_id': plan['paper_id'], 'source_sha256': None,
                    'config_event_id': plan['config_event_id']}
        body = canonical(envelope); event_id = identifier('model-event', envelope)
        def insert(db):
            old = db.execute('SELECT payload_json FROM ct_model_events WHERE event_id=?', (event_id,)).fetchone()
            if old:
                if old[0] != body:
                    raise ContractError('model provenance identity collision')
            else:
                db.execute('INSERT INTO ct_model_events (event_id,kind,scope_id,paper_id,source_sha256,config_event_id,payload_json,content_sha256) VALUES (?,?,?,?,?,?,?,?)',
                           (event_id, kind, plan['run_id'], plan['paper_id'], None,
                            plan['config_event_id'], body, content_hash(envelope)))
        if con is None:
            with connection(self.project.database_path, write=True) as db:
                insert(db)
        else:
            insert(con)
        return event_id

    def authorize(self, plan, *, actor_id, confirm_external=False, created_at=None):
        """Explicit caller approval, not identity authentication; exact-plan scope only."""
        self._validate(plan)
        text(actor_id, 'authorization actor')
        if confirm_external is not True or not plan['adapter']['data_leaves_machine']:
            raise ContractError('explicit external approval applies only to a remote plan')
        at = created_at or now(); timestamp(at)
        return self._record('model_transfer_consent', plan, {'actor_id': actor_id, 'created_at': at,
            'plan_sha256': plan['plan_sha256'], 'provider': plan['adapter']['provider_id'],
            'model': plan['configuration']['model'], 'mode': plan['mode'], 'notice': PRIVACY_NOTICE,
            'evidence_sha256': [e['content_sha256'] for e in plan['evidence']]})

    def inspect(self, run_id):
        result = []
        with connection(self.project.database_path) as db:
            for row in db.execute('SELECT * FROM ct_model_events WHERE scope_id=? ORDER BY sequence', (run_id,)):
                envelope = json.loads(row['payload_json'])
                if (identifier('model-event', envelope) != row['event_id'] or content_hash(envelope) != row['content_sha256']
                        or any(envelope[k] != row[k] for k in ('kind','scope_id','paper_id','source_sha256','config_event_id'))):
                    raise ContractError('model provenance is corrupt')
                result.append({'event_id': row['event_id'], **envelope})
        return result

    def execute(self, plan, *, consent_event_id=None, clock=now):
        """One explicit invocation. Exact completed replay never calls the model again."""
        self._validate(plan)
        adapter = self.registry.resolve(plan['configuration']['adapter'])
        prior = [r for r in self.inspect(plan['run_id']) if r['kind'] == 'model_request_started']
        if prior:
            if prior[0]['payload']['plan'] != plan:
                raise ContractError('model run ID belongs to a different plan')
            completed = [r for r in self.inspect(plan['run_id']) if r['kind'] == 'model_complete']
            if completed:
                return completed[0]['payload']
            raise ContractError('interrupted model run; inspect/resume without repeating the model call')
        if adapter.info.data_leaves_machine:
            consent = [r for r in self.inspect(plan['run_id']) if r['kind'] == 'model_transfer_consent'
                       and r['event_id'] == consent_event_id and r['payload']['plan_sha256'] == plan['plan_sha256']]
            if len(consent) != 1:
                raise ContractError('remote evidence transfer disabled: inspect plan and explicitly authorize it')
        c = self._config(plan['workflow_id'])
        credential = os.environ.get(c.credential_env) if c.credential_env else None
        missing = (c.credential_env is not None or adapter.info.credentials_required) and not credential
        # Serialize reservations for this run ID, including competing different plans.
        started_at = clock(); timestamp(started_at)
        with connection(self.project.database_path, write=True) as db:
            if latest_config(db)[0] != plan['config_event_id']:
                raise ContractError('configuration changed before invocation')
            if db.execute("SELECT 1 FROM ct_model_events WHERE scope_id=? AND kind='model_request_started'", (plan['run_id'],)).fetchone():
                raise ContractError('model run already reserved')
            self._record('model_request_started', plan, {'plan': plan, 'consent_event_id': consent_event_id,
                                                        'started_at': started_at}, con=db)
        if missing:
            return self._failure(plan, 'missing_credentials', clock())
        try:
            response = adapter.invoke(deepcopy(plan['request']), credential=credential)
        except Exception:
            # Arbitrary adapter exception strings/tracebacks may contain credentials.
            return self._failure(plan, 'adapter_error', clock())
        try:
            if asdict(adapter.info) != {**plan['adapter'], 'capabilities': tuple(plan['adapter']['capabilities'])}:
                raise ContractError('adapter changed during invocation')
            if not isinstance(response, ModelResponse):
                raise ContractError('adapter returned an invalid response envelope')
            raw = response.to_dict()
            safe_data(raw, secrets=self._secrets())
            if len(canonical(raw).encode('utf-8')) > MAX_BYTES:
                raise ContractError('bounded model output exceeded')
        except Exception:
            return self._failure(plan, 'unsafe_or_invalid_response', clock())
        at = clock(); timestamp(at)
        sha = preserve(self.project, canonical(raw).encode('utf-8'), 'application/json', at)
        self._record('model_response', plan, {'response': raw, 'output_sha256': sha, 'received_at': at})
        return self.resume(plan['run_id'])

    def _failure(self, plan, code, at):
        timestamp(at)
        result = {'run_id': plan['run_id'], 'plan_sha256': plan['plan_sha256'],
                  'status': 'failed', 'failure': code, 'completed_at': at,
                  'assertion_ids': [], 'production_effect': 'none'}
        self._record('model_complete', plan, result)
        return result

    def _drafts(self, plan, response):
        raw = response['response']
        output = raw['output']
        if set(output) != {'claims'} or not isinstance(output['claims'], list) or len(output['claims']) > plan['request']['specification']['max_claims']:
            raise ContractError('invalid structured assertion output')
        supplied = {e['evidence_id']: e for e in plan['evidence']}
        definitions = plan['request']['predicate_definitions']
        drafts = []
        for claim in output['claims']:
            if not isinstance(claim, dict) or set(claim) != {'predicate', 'raw_value', 'value_datatype', 'evidence_id', 'quote'}:
                raise ContractError('unknown/missing claim fields')
            predicate = claim['predicate']
            if not isinstance(predicate, str) or predicate not in definitions:
                raise ContractError('predicate not allowed by frozen task')
            evidence = supplied.get(claim['evidence_id']) if isinstance(claim['evidence_id'], str) else None
            quote = claim['quote']
            if claim['raw_value'] is None:
                if claim['value_datatype'] != 'unknown' or quote is not None or claim['evidence_id'] is not None:
                    raise ContractError('unknown claim must stay unknown without invented evidence')
            elif not evidence or not isinstance(quote, str) or not quote.strip() or quote not in evidence['text']:
                raise ContractError('positive assertion requires exact supporting supplied evidence')
            location = deepcopy(evidence['location']) if evidence else None
            if evidence:
                start = evidence['text'].index(quote)
                location = {**(location or {}), 'quote_start_in_input': start, 'quote_end_in_input': start + len(quote), 'quote': quote}
            source = {'reference': plan['run_id'], 'response_sha256': response['output_sha256'],
                      'request_sha256': plan['request_sha256'], 'specification_sha256': plan['request']['specification_sha256'],
                      'adapter': plan['adapter'], 'configured_model': plan['configuration']['model'],
                      'reported_model': raw['reported_model'], 'observed_models': raw['observed_models'],
                      'reported_model_version': raw['reported_model_version'],
                      'model_usage_ambiguity': raw['model_usage_ambiguity']}
            if evidence and evidence['source_sha256']:
                source['artifact_sha256'] = evidence['source_sha256']
            drafts.append({'subject_type': 'paper', 'subject_id': plan['paper_id'], 'paper_id': plan['paper_id'],
                'predicate': predicate, 'vocabulary_version': definitions[predicate]['version'],
                'raw_value': claim['raw_value'], 'value_datatype': claim['value_datatype'],
                'producer_type': 'model', 'producer_id': plan['adapter']['provider_id'] + ':' + plan['configuration']['model'],
                'producer_version': plan['adapter']['version'], 'created_at': response['received_at'],
                'evidence_representation': evidence['representation'] if evidence else 'none',
                'evidence_reference': evidence['reference'] if evidence else {'kind': 'unavailable', 'reason': 'model abstained'},
                'evidence_location': location, 'source': source, 'lineage_ref': plan['run_id']})
        return drafts

    def resume(self, run_id):
        """Explicit local-only recovery of a preserved response; never re-invoke an adapter."""
        records = self.inspect(run_id)
        starts = [r for r in records if r['kind'] == 'model_request_started']
        if len(starts) != 1:
            raise ContractError('unknown or inconsistent model run')
        plan = starts[0]['payload']['plan']
        completed = [r for r in records if r['kind'] == 'model_complete']
        if completed:
            return completed[0]['payload']
        responses = [r for r in records if r['kind'] == 'model_response']
        if len(responses) != 1:
            raise ContractError('response unavailable; no automatic model replay')
        response = responses[0]['payload']
        if content_hash(response['response']) != response['output_sha256'] or (
                artifact(self.project, response['output_sha256']).read_text(encoding='utf-8') != canonical(response['response'])):
            raise ContractError('preserved response integrity differs; no recovery writes')
        if response['response']['failure']:
            return self._failure(plan, response['response']['failure'], response['received_at'])
        try:
            if self.project.configuration_history()[-1]['event_id'] != plan['config_event_id']:
                raise ContractError('configuration changed during execution')
            if content_hash(self.project.knowledge_store.registry.describe()) != plan['registry_sha256']:
                raise ContractError('vocabulary changed during execution')
            store = self.project.knowledge_store
            batch = store.plan_batch(self._drafts(plan, response))
            self._record('model_assertion_plan', plan, {'knowledge_plan': batch})
            store.apply(batch)  # Existing transactional, immutable non-authoritative machinery.
        except (ValueError, TypeError, KeyError):
            return self._failure(plan, 'invalid_assertions_or_changed_snapshot', response['received_at'])
        result = {'run_id': run_id, 'plan_sha256': plan['plan_sha256'], 'status': 'succeeded',
                  'assertion_ids': [a['id'] for a in batch['assertions']], 'output_sha256': response['output_sha256'],
                  'reported_model': response['response']['reported_model'],
                  'observed_models': response['response']['observed_models'],
                  'model_usage_ambiguity': response['response']['model_usage_ambiguity'],
                  'completed_at': response['received_at'], 'production_effect': 'none'}
        self._record('model_complete', plan, result)
        return result
