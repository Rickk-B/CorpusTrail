"""Offline model infrastructure fixtures, not scientific extraction validation."""
from copy import deepcopy
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch

from corpustrail._internal.database import connection, create_database, migrations
from corpustrail._internal.pipeline import artifact
from corpustrail._internal.values import ContractError, canonical, digest_bytes
from corpustrail.cli import main
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.models import AdapterInfo, AdapterRegistry, FixtureAdapter, ModelConfig, ModelResponse, ModelService, TaskSpec
from corpustrail.project import Project, ProjectConfig, ProviderConfig

AT = '2026-01-01T00:00:00+00:00'
PREDICATE = 'ct.organism_population'
SECRET = 'private-fixture-value-never-persisted'


class RemoteFixture(FixtureAdapter):
    info = AdapterInfo('remote-fixture', 'external-fixture', 'v1', True)


class ModelsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.config = ProjectConfig('materials', 'Materials', 'Invented software fixture', models=(
            ModelConfig('local', 'fixture', 'fixture-model'),
            ModelConfig('remote', 'remote-fixture', 'configured-model'),))
        self.project = Project.create(self.root, self.config, created_by='fixture', created_at=AT)
        source = SourceReference('fixture://source', 'record', digest_bytes(b'invented evidence'), 17,
                                 'fixture', AT, identity_status='verified')
        record = BibliographicRecord('Invented human and rabbit investigation',
                                     'The study included human and rabbit samples.',
                                     identifiers=(Identifier('doi', '10.1234/fixture-model'),))
        self.pid = self.project.identities.apply(self.project.identities.plan(record, source),
                                               approve_new_identity=True, approve_aliases=True)
        self.local = FixtureAdapter(); self.remote = RemoteFixture()
        self.registry = AdapterRegistry((self.local, self.remote))
        self.service = ModelService(self.project, registry=self.registry)
        self.spec = TaskSpec('organisms', 'v1', 'Extract only explicit organisms; otherwise abstain.', (PREDICATE,))

    def plan(self, workflow='local', run_id='run', **kwargs):
        return self.service.plan(workflow, self.spec, run_id=run_id, paper_id=self.pid, created_at=AT, **kwargs)

    def response(self, plan, value='human', **kwargs):
        evidence = next(e for e in plan['evidence'] if e['representation'] == 'abstract')
        return ModelResponse({'claims': [{'predicate': PREDICATE, 'raw_value': value,
            'value_datatype': 'string', 'evidence_id': evidence['evidence_id'], 'quote': evidence['text']}]},
            'observed-primary', ('observed-primary', 'observed-auxiliary'), True,
            usage={'input_tokens': 12, 'output_tokens': 7, 'per_model': [{'model': 'observed-primary', 'input_tokens': 12}]}, **kwargs)

    def protected(self):
        with connection(self.project.database_path) as db:
            return {table: [tuple(r) for r in db.execute('SELECT * FROM '+table+' ORDER BY 1')] for table in
                ('paper_entities', 'paper_identifiers', 'ct_review_events', 'ct_priority_artifacts',
                 'ct_priority_runs', 'screening_events', 'screening_approvals', 'asreview_exports', 'ct_pipeline_events')}

    def configure(self, **changes):
        config = replace(self.project.config, config_version=self.project.config.config_version+1, **changes)
        self.project.configure(config, expected_event_id=self.project.configuration_history()[-1]['event_id'],
                               created_by='fixture', created_at=AT)

    def test_no_models_remains_fully_functional_and_status_is_read_only(self):
        self.configure(models=())
        before = self.project.database_path.read_bytes()
        status = self.project.models.status()
        self.assertEqual(status['model_providers'], [])
        self.assertEqual(status['external_evidence_transfer'], 'disabled_without_exact_plan_authorization')
        self.assertEqual(self.project.database_path.read_bytes(), before)
        self.assertEqual(self.project.reviews.membership(self.pid)['state'], 'not_reviewed')
        with self.assertRaises(ContractError): self.plan()

    def test_adapter_registration_and_capabilities(self):
        self.assertEqual(self.registry.available(), ['fixture', 'remote-fixture'])
        with self.assertRaises(ContractError): self.registry.register(FixtureAdapter())
        with self.assertRaises(ContractError): self.registry.resolve('not-installed')
        wrong = FixtureAdapter(); wrong.info = AdapterInfo('fixture', 'fixture', 'v1', False, ('other',))
        service = ModelService(self.project, registry=AdapterRegistry((wrong,)))
        with self.assertRaises(ContractError): service.plan('local', self.spec, run_id='bad', paper_id=self.pid)

    def test_installed_plugin_is_lazy_and_exactly_selected(self):
        class Plugin:
            name = 'fixture'
            calls = 0
            def load(inner): inner.calls += 1; return FixtureAdapter
        plugin = Plugin()
        with patch('corpustrail.models.registry.entry_points', return_value=[plugin]):
            registry = AdapterRegistry(installed_plugins=True)
        service = ModelService(self.project, registry=registry)
        self.assertIn('fixture', service.status()['available_adapters'])
        self.assertEqual(plugin.calls, 0)
        service.plan('local', self.spec, run_id='plugin', paper_id=self.pid)
        self.assertEqual(plugin.calls, 1)

    def test_local_execution_needs_no_external_consent_and_preserves_authority(self):
        plan = self.plan(); self.local.response = self.response(plan)
        before = self.protected()
        result = self.service.execute(plan, clock=lambda: AT)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(self.protected(), before)
        assertion = self.project.knowledge_store.assertions()[0]['payload']
        self.assertEqual(assertion['producer_type'], 'model')
        self.assertEqual(assertion['initial_authority'], 'non_authoritative')
        self.assertEqual(assertion['initial_validation'], 'unvalidated')
        self.assertTrue(self.project.knowledge_store.evidence(result['assertion_ids'][0])['resolved']['reference_available'])
        self.assertEqual(self.project.knowledge_store.authoritative('knowledge.organization'), [])
        self.assertEqual(self.project.knowledge_store.verify()['production_effect'], 'none')

    def test_remote_consent_required_and_bound_to_exact_plan(self):
        plan = self.plan('remote'); self.remote.response = self.response(plan)
        before = self.project.database_path.read_bytes()
        with self.assertRaises(ContractError): self.service.execute(plan)
        self.assertEqual(self.remote.calls, 0)
        self.assertEqual(self.project.database_path.read_bytes(), before)
        with self.assertRaises(ContractError): self.service.authorize(plan, actor_id='reviewer')
        consent = self.service.authorize(plan, actor_id='reviewer', confirm_external=True, created_at=AT)
        other = self.plan('remote', run_id='different')
        with self.assertRaises(ContractError): self.service.execute(other, consent_event_id=consent)
        self.assertEqual(self.service.execute(plan, consent_event_id=consent, clock=lambda: AT)['status'], 'succeeded')
        self.assertEqual(self.remote.calls, 1)

    def test_prompt_and_evidence_changes_invalidate_plan_and_consent(self):
        plan = self.plan('remote')
        altered = deepcopy(plan); altered['request']['specification']['instructions'] += ' changed'
        with self.assertRaises(ContractError): self.service.authorize(altered, actor_id='reviewer', confirm_external=True)
        self.configure(models=(ModelConfig('local', 'fixture', 'new-model'),))
        with self.assertRaises(ContractError): self.service.execute(plan)
        self.assertEqual(self.remote.calls, 0)

    def test_same_specification_runs_across_models_without_semantic_rewrite(self):
        local = self.plan(); remote = self.plan('remote', run_id='remote')
        self.assertEqual(local['request']['specification'], remote['request']['specification'])
        self.assertEqual(local['request']['specification_sha256'], self.spec.sha256)
        self.assertEqual(local['evidence'], remote['evidence'])

    def test_config_rejects_secret_fields_and_credentials_in_normal_values(self):
        for settings in ({'api_key': SECRET}, {'nested': {'password': SECRET}}, {'headers': {'Authorization': SECRET}}):
            with self.assertRaises(ContractError):
                ModelConfig('local', 'fixture', 'fixture-model', settings=settings).validate()
        with patch.dict(os.environ, {'FIXTURE_MODEL_KEY': SECRET}):
            with self.assertRaises(ContractError):
                ModelConfig('local', 'fixture', 'fixture-model', credential_env='FIXTURE_MODEL_KEY',
                            settings={'custom': SECRET}).validate()
        with self.assertRaises(ContractError): ModelConfig('x', 'fixture', 'm', endpoint_id='https://private.example.test/').validate()
        with self.assertRaises(ContractError): ModelConfig('x', 'fixture', 'm', credential_env='not an env name').validate()

    def test_user_credentials_not_persisted_and_status_never_displays_secret(self):
        self.configure(models=(ModelConfig('remote', 'remote-fixture', 'configured-model', credential_env='FIXTURE_MODEL_KEY'),))
        self.remote.info = replace(self.remote.info, credentials_required=True)
        with patch.dict(os.environ, {'FIXTURE_MODEL_KEY': SECRET}):
            plan = self.plan('remote')
            self.remote.response = self.response(plan)
            consent = self.service.authorize(plan, actor_id='reviewer', confirm_external=True, created_at=AT)
            self.assertEqual(self.service.execute(plan, consent_event_id=consent, clock=lambda: AT)['status'], 'succeeded')
            self.assertNotIn(SECRET, json.dumps(self.service.status()))
        for p in self.root.rglob('*'):
            if p.is_file(): self.assertNotIn(SECRET.encode(), p.read_bytes())

    def test_secret_echo_and_exception_details_never_persisted(self):
        self.configure(models=(ModelConfig('local', 'fixture', 'fixture-model', credential_env='FIXTURE_MODEL_KEY'),))
        with patch.dict(os.environ, {'FIXTURE_MODEL_KEY': SECRET}):
            plan = self.plan(); self.local.response = ModelResponse({'claims': [], 'echo': SECRET})
            result = self.service.execute(plan, clock=lambda: AT)
            self.assertEqual(result['failure'], 'unsafe_or_invalid_response')
            plan2 = self.plan(run_id='exception')
            with patch.object(self.local, 'invoke', side_effect=RuntimeError(SECRET)):
                self.assertEqual(self.service.execute(plan2, clock=lambda: AT)['failure'], 'adapter_error')
        for p in self.root.rglob('*'):
            if p.is_file(): self.assertNotIn(SECRET.encode(), p.read_bytes())

    def test_missing_credential_failure_is_recorded_without_invocation(self):
        self.local.info = replace(self.local.info, credentials_required=True)
        plan = self.plan()
        result = self.service.execute(plan, clock=lambda: AT)
        self.assertEqual(result['failure'], 'missing_credentials'); self.assertEqual(self.local.calls, 0)
        self.assertEqual(self.service.execute(plan), result)

    def test_response_provenance_records_configured_actual_auxiliary_and_usage(self):
        plan = self.plan(); self.local.response = self.response(plan)
        result = self.service.execute(plan, clock=lambda: AT)
        self.assertEqual(result['observed_models'], ['observed-primary', 'observed-auxiliary'])
        self.assertTrue(result['model_usage_ambiguity'])
        response = next(e['payload'] for e in self.service.inspect('run') if e['kind'] == 'model_response')
        self.assertEqual(response['response']['usage']['input_tokens'], 12)
        assertion = self.project.knowledge_store.assertions()[0]['payload']
        self.assertEqual(assertion['source']['configured_model'], 'fixture-model')
        self.assertEqual(assertion['source']['request_sha256'], plan['request_sha256'])

    def test_exact_replay_no_provider_call_or_duplicate_assertions(self):
        plan = self.plan(); self.local.response = self.response(plan)
        first = self.service.execute(plan, clock=lambda: AT)
        before = self.project.database_path.read_bytes()
        self.assertEqual(self.service.execute(plan), first)
        self.assertEqual(self.service.resume('run'), first)
        self.assertEqual(self.local.calls, 1)
        self.assertEqual(self.project.database_path.read_bytes(), before)
        self.assertEqual(len(self.project.knowledge_store.assertions()), 1)

    def test_independent_runs_and_conflicts_coexist(self):
        for run_id, value in [('one', 'human'), ('two', 'human'), ('three', 'rabbit')]:
            plan = self.plan(run_id=run_id); self.local.response = self.response(plan, value=value)
            self.service.execute(plan, clock=lambda: AT)
        self.assertEqual(len(self.project.knowledge_store.assertions()), 3)
        self.assertEqual(len(self.project.knowledge.conflicts(self.pid)), 1)

    def test_unknown_remains_unknown(self):
        plan = self.plan()
        self.local.response = ModelResponse({'claims': [{'predicate': PREDICATE, 'raw_value': None,
            'value_datatype': 'unknown', 'evidence_id': None, 'quote': None}]})
        self.assertEqual(self.service.execute(plan, clock=lambda: AT)['status'], 'succeeded')
        self.assertIsNone(self.project.knowledge_store.assertions()[0]['payload']['raw_value'])

    def test_malformed_output_cannot_add_authority_tools_or_wrong_evidence(self):
        plan = self.plan()
        good = self.response(plan).output['claims'][0]
        bads = [dict(good, authority='human_authorized'), dict(good, quote='not present'),
                dict(good, predicate='not.registered'), dict(good, evidence_id='wrong'),
                dict(good, value_datatype='boolean'), dict(good, raw_value=None),
                dict(good, tools=['shell'])]
        before = self.protected()
        for i, claim in enumerate(bads):
            p = self.plan(run_id='bad'+str(i)); self.local.response = ModelResponse({'claims': [claim]})
            self.assertEqual(self.service.execute(p, clock=lambda: AT)['status'], 'failed')
        self.assertEqual(self.project.knowledge_store.assertions(), [])
        self.assertEqual(self.protected(), before)

    def test_model_strings_are_not_executable(self):
        plan = self.plan()
        self.local.response = ModelResponse({'claims': [], 'tool_calls': [{'file': '/not-a-real-file', 'code': 'raise RuntimeError()'}]})
        self.assertEqual(self.service.execute(plan, clock=lambda: AT)['status'], 'failed')
        self.assertEqual(self.project.knowledge_store.assertions(), [])

    def test_pending_pdf_is_not_model_input(self):
        rep = self.project.evidence.preserve_document(self.pid, b'%PDF invented fixture', representation='pdf',
            media_type='application/pdf', source_uri='https://example.test/document', legitimate_basis='synthetic',
            resolver='fixture', resolver_version='v1', created_at=AT)
        with self.assertRaises(ContractError): self.plan(mode='full_text', representation_id=rep)
        self.assertEqual(self.local.calls, 0)
        self.assertEqual(self.project.evidence.status(self.pid)['pending_identity'], 1)

    def test_metadata_does_not_silently_transmit_abstract_or_human_labels(self):
        plan = self.plan(mode='metadata')
        self.assertTrue(all(e['representation'] == 'metadata' for e in plan['request']['evidence']))
        request = json.dumps(plan['request'])
        self.assertNotIn('The study included', request)
        self.assertNotIn('reviewer', request)
        self.assertNotIn('membership', request)
        self.assertNotIn('source_uri', request)

    def test_missing_abstract_requires_explicit_metadata_choice(self):
        source = SourceReference('fixture://empty', 'empty', digest_bytes(b'empty'), 5, 'fixture', AT)
        pid = self.project.identities.apply(self.project.identities.plan(BibliographicRecord('Metadata only'), source),
                                           approve_new_identity=True, approve_aliases=True)
        with self.assertRaises(ContractError): self.service.plan('local', self.spec, run_id='missing', paper_id=pid)
        plan = self.service.plan('local', self.spec, run_id='missing', paper_id=pid, mode='metadata')
        self.assertEqual(plan['mode'], 'metadata')

    def test_plan_write_no_clobber_and_path_traversal(self):
        plan = self.plan()
        self.service.write_plan(plan, 'plans/one.json')
        self.assertEqual(self.service.read_plan('plans/one.json'), plan)
        with self.assertRaises(FileExistsError): self.service.write_plan(plan, 'plans/one.json')
        with self.assertRaises(ContractError): self.service.write_plan(plan, '../outside.json')

    def test_provider_failure_and_interrupted_run_never_implicitly_retry(self):
        plan = self.plan(); self.local.response = ModelResponse({}, failure='rate_limited')
        first = self.service.execute(plan, clock=lambda: AT)
        self.assertEqual(first['failure'], 'rate_limited')
        self.assertEqual(self.service.execute(plan), first); self.assertEqual(self.local.calls, 1)
        other = self.plan(run_id='interrupted')
        self.service._record('model_request_started', other, {'plan': other, 'consent_event_id': None})
        with self.assertRaises(ContractError): self.service.execute(other)
        with self.assertRaises(ContractError): self.service.resume('interrupted')
        self.assertEqual(self.local.calls, 1)

    def test_local_resume_after_assertions_commit_does_not_duplicate(self):
        plan = self.plan(); self.local.response = self.response(plan)
        original = self.service._record
        def crash(kind, *args, **kwargs):
            if kind == 'model_complete': raise OSError('simulated crash')
            return original(kind, *args, **kwargs)
        with patch.object(self.service, '_record', side_effect=crash):
            with self.assertRaises(OSError): self.service.execute(plan, clock=lambda: AT)
        self.assertEqual(len(self.project.knowledge_store.assertions()), 1)
        self.assertEqual(self.service.resume('run')['status'], 'succeeded')
        self.assertEqual(self.local.calls, 1)
        self.assertEqual(len(self.project.knowledge_store.assertions()), 1)

    def test_cli_status_and_help_are_local_read_only(self):
        before = self.project.database_path.read_bytes()
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(main(['models', 'status', str(self.root)]), 0)
        self.assertIn('external_evidence_transfer', output.getvalue())
        self.assertEqual(self.project.database_path.read_bytes(), before)
        with patch('sys.stdout', new_callable=io.StringIO), self.assertRaises(SystemExit) as result:
            main(['models', '--help'])
        self.assertEqual(result.exception.code, 0)

    def test_model_events_are_immutable_and_run_ids_are_reserved(self):
        plan = self.plan(); self.service.execute(plan, clock=lambda: AT)
        for sql in ('DELETE FROM ct_model_events', 'UPDATE ct_model_events SET scope_id=scope_id',
                    'INSERT OR REPLACE INTO ct_model_events SELECT * FROM ct_model_events'):
            with self.assertRaises(sqlite3.IntegrityError), connection(self.project.database_path, write=True) as db:
                db.execute(sql)
        other = self.plan(mode='metadata')
        with self.assertRaises(ContractError): self.service.execute(other)
        self.assertEqual(self.local.calls, 1)

    def test_verified_document_and_selected_passage_depth_are_explicit(self):
        xml = b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/fixture-model</article-id></article-meta></front><body><sec><title>Methods</title><p>Human and rabbit samples were measured.</p></sec></body></article>'
        self.project.evidence.preserve_document(self.pid, xml, representation='jats_xml',
            media_type='application/xml', source_uri='https://example.test/article', legitimate_basis='synthetic',
            resolver='fixture', resolver_version='v1', created_at=AT)
        rep = next(r for r in self.project.evidence.representations(self.pid) if r['payload']['representation'] == 'structured_text')
        body = artifact(self.project, rep['payload']['artifact_sha256']).read_text(encoding='utf-8')
        start = body.index('Human and rabbit')
        plan = self.plan(mode='selected_passages', representation_id=rep['event_id'], passages=((start, start+16),))
        sent = [e for e in plan['request']['evidence'] if e['representation'] == 'structured_text']
        self.assertEqual([e['text'] for e in sent], ['Human and rabbit'])
        self.local.response = ModelResponse({'claims': [{'predicate': PREDICATE, 'raw_value': 'human',
            'value_datatype': 'string', 'evidence_id': sent[0]['evidence_id'], 'quote': 'Human'}]})
        self.assertEqual(self.service.execute(plan, clock=lambda: AT)['status'], 'succeeded')
        assertion = self.project.knowledge_store.assertions()[0]['payload']
        self.assertEqual(assertion['evidence_location']['character_start'], start)
        self.assertTrue(self.project.knowledge_store.evidence(self.project.knowledge_store.assertions()[0]['id'])['resolved']['trusted'])
        full = self.plan(run_id='full', mode='full_text', representation_id=rep['event_id'])
        self.assertIn(body, [e['text'] for e in full['request']['evidence']])

    def test_project_from_published_schema_upgrades_additively_without_reinterpreting_data(self):
        old = Path(self.temp.name) / 'old-project'
        config = ProjectConfig('old', 'Old project', 'Synthetic existing project')
        original = migrations()
        with patch('corpustrail._internal.database.migrations', return_value=original[:35]):
            old.mkdir()
            raw = config.to_dict(); raw.pop('models')  # Actual published config shape.
            create_database(old/config.database, raw, AT, 'fixture')
            (old/'corpustrail.project.json').write_bytes((canonical(raw)+'\n').encode('utf-8'))
            prior = Project.open(old)
            source = SourceReference('fixture://old', 'record', digest_bytes(b'old'), 3, 'fixture', AT)
            pid = prior.identities.apply(prior.identities.plan(BibliographicRecord('Old unchanged record'), source),
                                        approve_new_identity=True, approve_aliases=True)
            knowledge = prior.knowledge.observations(pid)
            bootstrap = (old/'corpustrail.project.json').read_bytes()
        with self.assertRaises(ContractError): Project.open(old)
        upgraded = Project.upgrade(old, backup='data/backups/pre36.sqlite3', created_at=AT)
        self.assertEqual(upgraded.knowledge.observations(pid), knowledge)
        self.assertEqual((old/'corpustrail.project.json').read_bytes(), bootstrap)
        self.assertEqual(upgraded.models.status()['model_providers'], [])
        with connection(upgraded.database_path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_model_events').fetchone()[0], 0)

    def test_plugin_load_failure_is_redacted(self):
        class Plugin:
            name = 'fixture'
            def load(inner): raise ImportError(SECRET)
        with patch('corpustrail.models.registry.entry_points', return_value=[Plugin()]):
            registry = AdapterRegistry(installed_plugins=True)
        with self.assertRaises(ContractError) as error: registry.resolve('fixture')
        self.assertNotIn(SECRET, str(error.exception))

    def test_model_configuration_cannot_persist_a_discovery_credential(self):
        before = self.project.database_path.read_bytes()
        config = replace(self.project.config, config_version=2,
            providers=(ProviderConfig('openalex', 'openalex', 'DISCOVERY_FIXTURE_KEY'),),
            models=(ModelConfig('local', 'fixture', 'fixture-model', settings={'custom': SECRET}),))
        with patch.dict(os.environ, {'DISCOVERY_FIXTURE_KEY': SECRET}):
            with self.assertRaises(ContractError):
                self.project.configure(config, expected_event_id=self.project.configuration_history()[-1]['event_id'],
                                       created_by='fixture')
        self.assertEqual(self.project.database_path.read_bytes(), before)

    def test_evidence_and_task_secret_guards_run_before_transmission_or_logging(self):
        self.configure(providers=(ProviderConfig('openalex', 'openalex', 'DISCOVERY_FIXTURE_KEY'),))
        spec = TaskSpec('bad', 'v1', 'Text including '+SECRET, (PREDICATE,))
        before = self.project.database_path.read_bytes()
        with patch.dict(os.environ, {'DISCOVERY_FIXTURE_KEY': SECRET}):
            with self.assertRaises(ContractError):
                self.service.plan('remote', spec, run_id='bad', paper_id=self.pid)
        self.assertEqual(self.remote.calls, 0)
        self.assertEqual(self.project.database_path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
