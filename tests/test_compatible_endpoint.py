"""Offline loopback HTTP fixtures only; no commercial service or real model."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch

from corpustrail._internal.database import connection
from corpustrail._internal.values import ContractError, digest_bytes
from corpustrail.cli import main
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.models import ModelConfig, TaskSpec
from corpustrail.models.integrations.compatible_endpoint import CompatibleEndpointAdapter, TEST_MESSAGE
from corpustrail.project import Project, ProjectConfig

AT = '2026-01-01T00:00:00+00:00'
PREDICATE = 'ct.organism_population'
SECRET = 'private-compatible-fixture-key'


class CompatibleEndpointTests(unittest.TestCase):
    def setUp(self):
        self.requests = []; self.status_code = 200; self.delay = 0
        self.reply = 'OK'; self.extra = {}; self.response_bytes = None; self.headers = {}
        case = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                # Only the fixture inspects transient HTTP headers; not product provenance.
                case.requests.append((self.path, dict(self.headers), payload))
                if case.delay:
                    time.sleep(case.delay)
                content = case.reply(payload) if callable(case.reply) else case.reply
                body = case.response_bytes if case.response_bytes is not None else json.dumps({
                    'id': 'fixture-response', 'model': 'server-reported-model', 'usage': {'prompt_tokens': 4, 'completion_tokens': 2},
                    'choices': [{'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
                    **case.extra}).encode('utf-8')
                self.send_response(case.status_code)
                for k, v in case.headers.items():
                    self.send_header(k, v)
                self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}/v1'
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.project = Project.create(self.root, ProjectConfig('materials', 'Materials', 'Invented fixture'),
                                      created_by='fixture', created_at=AT)
        self.spec = TaskSpec('organisms', 'v1', 'Extract explicit organisms only.', (PREDICATE,))

    def configure(self, *, execution='local', credential_env=None, timeout=5, settings=None, workflow='extract', base=None):
        config = ModelConfig(workflow, 'compatible-endpoint', 'user-chosen-model', 'fixture-endpoint', credential_env,
            settings or {}, {'base_url': base or self.base, 'execution': execution, 'timeout_seconds': timeout})
        CompatibleEndpointAdapter(config)  # Config validation never connects.
        current = self.project.config
        self.project.configure(replace(current, config_version=current.config_version+1,
            models=tuple(c for c in current.models if c.workflow_id != workflow)+(config,)),
            expected_event_id=self.project.configuration_history()[-1]['event_id'], created_by='fixture', created_at=AT)
        return config

    def paper(self):
        source = SourceReference('fixture://source', 'record', digest_bytes(b'invented evidence'), 17, 'fixture', AT,
                                 identity_status='verified')
        return self.project.identities.apply(self.project.identities.plan(
            BibliographicRecord('Invented investigation', 'The study included rabbit samples.',
                identifiers=(Identifier('doi', '10.1234/compatible'),)), source),
            approve_new_identity=True, approve_aliases=True)

    def plan(self, *, workflow='extract', run_id='science'):
        return self.project.models.plan(workflow, self.spec, run_id=run_id, paper_id=self.paper(), created_at=AT)

    def claims_reply(self, payload):
        evidence = json.loads(payload['messages'][1]['content'])['evidence']
        item = next(e for e in evidence if e['representation'] == 'abstract')
        return json.dumps({'claims': [{'predicate': PREDICATE, 'raw_value': 'rabbit', 'value_datatype': 'string',
                                      'evidence_id': item['evidence_id'], 'quote': item['text']}]})

    def protected(self):
        with connection(self.project.database_path) as db:
            return {t: [tuple(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in (
                'paper_entities', 'paper_identifiers', 'ct_review_events', 'ct_priority_runs', 'ct_pipeline_events',
                'screening_events', 'screening_approvals', 'asreview_exports')}

    def assert_no_secret(self):
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(SECRET.encode(), path.read_bytes())
        self.assertNotIn(SECRET, json.dumps(self.project.models.status()))

    def test_no_model_required_and_factory_available_without_default(self):
        before = self.project.database_path.read_bytes()
        self.assertEqual(self.project.models.status()['model_providers'], [])
        self.assertIn('compatible-endpoint', self.project.models.status()['available_adapters'])
        self.assertEqual(self.requests, [])
        self.assertEqual(before, self.project.database_path.read_bytes())

    def test_configure_and_status_are_local_only_and_config_is_versioned(self):
        self.configure()
        before = self.project.database_path.read_bytes()
        self.project = Project.open(self.root)
        row = self.project.models.status()['model_providers'][0]
        self.assertEqual(row['execution'], 'local'); self.assertFalse(row['data_leaves_machine'])
        self.assertEqual(row['credential_status'], 'not_configured')
        self.assertEqual(row['external_evidence_transfer'], 'disabled_without_exact_plan_authorization')
        self.assertEqual(before, self.project.database_path.read_bytes()); self.assertEqual(self.requests, [])
        self.assertEqual(len(self.project.configuration_history()), 2)

    def test_explicit_local_literal_loopback_and_tls_policy(self):
        for url, mode in [('http://localhost:8000/v1', 'local'), ('https://models.example.test/v1', 'local'),
                          ('http://192.168.0.2/v1', 'local'), ('http://models.example.test/v1', 'remote'),
                          ('https://user:password@models.example.test/v1', 'remote'),
                          ('https://models.example.test/v1?api_key=opaque', 'remote'),
                          ('https://models.example.test/v1#private', 'remote'),
                          ('http://127.0.0.1:8000/../v1', 'local'),
                          ('http://127.0.0.1:8000/%2e%2e/v1', 'local')]:
            with self.subTest(mode=mode, category='unsafe_url'), self.assertRaises(ContractError):
                self.configure(execution=mode, base=url)
        self.configure(base='http://[::1]:8000/v1')  # Validation only; no IPv6 socket required.
        self.configure(execution='remote', base='https://models.example.test/v1')
        self.assertEqual(self.requests, [])

    def test_settings_and_credentials_rejected_before_config_persistence(self):
        before = self.project.database_path.read_bytes()
        for settings in ({'api_key': SECRET}, {'headers': {}}, {'tools': []}, {'model': 'override'},
                         {'stream': True}, {'temperature': 8}, {'max_tokens': 0}):
            with self.assertRaises(ContractError):
                self.configure(settings=settings)
        with patch.dict(os.environ, {'FIXTURE_KEY': SECRET}), self.assertRaises(ContractError):
            self.configure(credential_env='FIXTURE_KEY', base='https://models.example.test/'+SECRET)
        self.assertEqual(before, self.project.database_path.read_bytes()); self.assertEqual(self.requests, [])

    def test_connection_test_sends_only_synthetic_payload_and_no_assertions(self):
        self.configure(settings={'temperature': 0.2})
        before = self.protected()
        result = self.project.models.test_connection('extract', run_id='connection', clock=lambda: AT)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['response']['reported_model'], 'server-reported-model')
        self.assertEqual(result['response']['usage']['prompt_tokens'], 4)
        self.assertTrue(result['response']['model_usage_ambiguity'])
        self.assertEqual(self.requests[0][0], '/v1/chat/completions')
        self.assertEqual(self.requests[0][2], {'model': 'user-chosen-model', 'stream': False,
                          'messages': [{'role': 'user', 'content': TEST_MESSAGE}]})
        self.assertEqual(result['assertion_ids'], []); self.assertFalse(result['external_evidence_transfer_authorized'])
        self.assertEqual(self.project.knowledge_store.assertions(), []); self.assertEqual(self.protected(), before)
        before = self.project.database_path.read_bytes()
        self.assertEqual(self.project.models.test_connection('extract', run_id='connection', clock=lambda: AT), result)
        self.assertEqual(len(self.requests), 1); self.assertEqual(self.project.database_path.read_bytes(), before)

    def test_remote_test_needs_separate_synthetic_approval_not_scientific_consent(self):
        self.configure(execution='remote')
        with self.assertRaises(ContractError): self.project.models.test_connection('extract', run_id='connection')
        self.assertEqual(self.requests, [])
        self.project.models.test_connection('extract', run_id='connection', confirm_external=True, clock=lambda: AT)
        plan = self.plan()
        self.reply = self.claims_reply
        with self.assertRaises(ContractError): self.project.models.execute(plan)
        self.assertEqual(len(self.requests), 1)
        consent = self.project.models.authorize(plan, actor_id='fixture-reviewer', confirm_external=True, created_at=AT)
        self.assertEqual(self.project.models.execute(plan, consent_event_id=consent, clock=lambda: AT)['status'], 'succeeded')

    def test_local_scientific_output_is_evidence_linked_non_authoritative_and_idempotent(self):
        self.configure(settings={'temperature': 0, 'max_tokens': 100})
        plan = self.plan(); before = self.protected(); self.reply = self.claims_reply
        result = self.project.models.execute(plan, clock=lambda: AT)
        self.assertEqual(result['status'], 'succeeded'); self.assertEqual(self.protected(), before)
        self.assertEqual(self.requests[0][2]['temperature'], 0)
        self.assertNotIn('endpoint_id', self.requests[0][2]); self.assertNotIn('paper_id', json.dumps(self.requests[0][2]))
        assertion = self.project.knowledge_store.assertions()[0]['payload']
        self.assertEqual(assertion['producer_type'], 'model'); self.assertEqual(assertion['initial_authority'], 'non_authoritative')
        self.assertEqual(assertion['source']['configured_model'], 'user-chosen-model')
        response = next(e['payload']['response'] for e in self.project.models.inspect('science') if e['kind'] == 'model_response')
        self.assertIn('wire_request_sha256', response['diagnostics']); self.assertIn('wire_response_sha256', response['diagnostics'])
        self.assertEqual(self.project.models.execute(plan), result); self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(self.project.knowledge_store.assertions()), 1)

    def test_auth_header_only_uses_user_env_key_and_not_provenance(self):
        self.configure(credential_env='FIXTURE_KEY')
        with patch.dict(os.environ, {'FIXTURE_KEY': SECRET}):
            result = self.project.models.test_connection('extract', run_id='auth', clock=lambda: AT)
            self.assertEqual(result['status'], 'succeeded'); self.assert_no_secret()
            self.assertEqual(self.requests[0][1]['Authorization'], 'Bearer '+SECRET)
            plan = self.plan(); self.reply = self.claims_reply
            self.assertEqual(self.project.models.execute(plan, clock=lambda: AT)['status'], 'succeeded'); self.assert_no_secret()

    def test_missing_key_has_clear_status_and_failure_without_request(self):
        self.configure(credential_env='FIXTURE_MISSING_KEY')
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.project.models.status()['model_providers'][0]['credential_status'], 'missing')
            result = self.project.models.test_connection('extract', run_id='missing', clock=lambda: AT)
            self.assertEqual(result['failure'], 'missing_credentials')
            self.assertEqual(self.project.models.execute(self.plan(), clock=lambda: AT)['failure'], 'missing_credentials')
        self.assertEqual(self.requests, [])

    def test_timeout_recorded_no_automatic_retry(self):
        self.configure(timeout=0.03); self.delay = 0.15
        result = self.project.models.test_connection('extract', run_id='timeout', clock=lambda: AT)
        self.assertEqual(result['response']['diagnostics']['failure_kind'], 'timeout')
        self.assertEqual(len(self.requests), 1)

    def test_malformed_response_and_invalid_structured_output_preserved_as_failure(self):
        self.configure(); self.response_bytes = b'not JSON'
        result = self.project.models.test_connection('extract', run_id='bad-envelope', clock=lambda: AT)
        self.assertEqual(result['status'], 'failed')
        self.response_bytes = None; self.reply = '{"claims": [{"authority": "human"}]}'
        result = self.project.models.execute(self.plan(), clock=lambda: AT)
        self.assertEqual(result['failure'], 'invalid_assertions_or_changed_snapshot')
        self.assertEqual(self.project.knowledge_store.assertions(), [])

    def test_http_error_body_and_key_echo_are_never_logged(self):
        self.configure(credential_env='FIXTURE_KEY'); self.status_code = 429; self.response_bytes = SECRET.encode()
        with patch.dict(os.environ, {'FIXTURE_KEY': SECRET}):
            result = self.project.models.test_connection('extract', run_id='http', clock=lambda: AT)
            self.assertEqual(result['failure'], 'rate_limited'); self.assertEqual(result['response']['diagnostics']['http_status'], 429)
            self.status_code = 200; self.response_bytes = None; self.reply = SECRET
            result = self.project.models.test_connection('extract', run_id='echo', clock=lambda: AT)
            self.assertEqual(result['status'], 'failed'); self.assert_no_secret()

    def test_redirects_never_followed_or_credentials_forwarded(self):
        self.configure(credential_env='FIXTURE_KEY'); self.status_code = 307
        self.headers = {'Location': self.base+'/elsewhere'}
        with patch.dict(os.environ, {'FIXTURE_KEY': SECRET}):
            result = self.project.models.test_connection('extract', run_id='redirect', clock=lambda: AT)
        self.assertEqual(result['response']['diagnostics']['failure_kind'], 'redirect_rejected')
        self.assertEqual(len(self.requests), 1)

    def test_provider_401_and_500_failures_have_safe_diagnostics(self):
        self.configure()
        for status in (401, 500):
            self.status_code = status; self.response_bytes = b'Untrusted provider error body'
            result = self.project.models.test_connection('extract', run_id='error-'+str(status), clock=lambda: AT)
            self.assertEqual(result['failure'], 'provider_error')
            self.assertEqual(result['response']['diagnostics']['http_status'], status)
            self.assertNotIn('Untrusted provider error body', json.dumps(result))

    def test_tool_calls_truncated_and_multiple_choices_rejected(self):
        self.configure()
        for i, choices in enumerate([
            [{'message': {'role': 'assistant', 'content': 'OK', 'tool_calls': [{'type': 'function'}]}, 'finish_reason': 'tool_calls'}],
            [{'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'length'}],
            [{'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'stop'}]*2,
        ]):
            self.extra = {'choices': choices}
            result = self.project.models.test_connection('extract', run_id='disallowed-'+str(i), clock=lambda: AT)
            self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.project.knowledge_store.assertions(), [])

    def test_exposed_auxiliary_model_identifiers_preserved_without_inventing_roles(self):
        self.configure(); self.extra = {'observed_models': ['server-reported-model', 'server-auxiliary-model']}
        result = self.project.models.test_connection('extract', run_id='aux', clock=lambda: AT)
        self.assertEqual(result['response']['observed_models'], ['server-reported-model', 'server-auxiliary-model'])
        self.assertTrue(result['response']['model_usage_ambiguity'])

    def test_unavailable_connection_and_bad_auth_header_are_redacted(self):
        self.configure(base='http://127.0.0.1:1/v1', credential_env='FIXTURE_KEY', timeout=0.1)
        with patch.dict(os.environ, {'FIXTURE_KEY': SECRET}):
            result = self.project.models.test_connection('extract', run_id='unavailable', clock=lambda: AT)
            self.assertEqual(result['response']['diagnostics']['failure_kind'], 'connection_error')
            self.assert_no_secret()
        with patch.dict(os.environ, {'FIXTURE_KEY': SECRET+'\r\nInjected: unsafe'}):
            result = self.project.models.test_connection('extract', run_id='invalid-auth', clock=lambda: AT)
            self.assertEqual(result['response']['diagnostics']['failure_kind'], 'invalid_credential')
        self.assertEqual(self.requests, [])

    def test_no_ambient_proxy_even_for_local_endpoint(self):
        self.configure()
        with patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:1', 'HTTP_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            result = self.project.models.test_connection('extract', run_id='no-proxy', clock=lambda: AT)
        self.assertEqual(result['status'], 'succeeded')

    def test_multiple_workflow_localities_do_not_share_adapter_binding(self):
        self.configure(workflow='local'); self.configure(execution='remote', workflow='remote')
        plans = [self.plan(workflow=w, run_id=w) for w in ('local', 'remote')]
        self.assertFalse(plans[0]['adapter']['data_leaves_machine']); self.assertTrue(plans[1]['adapter']['data_leaves_machine'])
        self.assertEqual(plans[0]['request']['specification'], plans[1]['request']['specification'])
        with self.assertRaises(ContractError): self.project.models.execute(plans[1])
        self.assertEqual(self.requests, [])

    def test_connection_history_immutable_and_stale_reuse_rejected(self):
        self.configure(); self.project.models.test_connection('extract', run_id='history', clock=lambda: AT)
        history = self.project.models.connection_history('history')
        self.assertEqual([e['kind'] for e in history], ['started', 'complete'])
        before = self.project.database_path.read_bytes()
        with self.assertRaises(sqlite3.IntegrityError), connection(self.project.database_path, write=True) as db:
            db.execute('UPDATE ct_model_connection_events SET kind=?', ('complete',))
        self.assertEqual(before, self.project.database_path.read_bytes())
        self.configure(settings={'temperature': 0})
        with self.assertRaises(ContractError): self.project.models.test_connection('extract', run_id='history')
        self.assertEqual(len(self.requests), 1)

    def test_cli_config_status_test_and_history_no_secret(self):
        args = ['models', 'configure', str(self.root), '--workflow', 'extract', '--model', 'user-chosen-model',
            '--endpoint-id', 'fixture-endpoint', '--base-url', self.base, '--execution', 'local',
            '--credential-env', 'FIXTURE_KEY', '--settings', '{"temperature":0}', '--created-by', 'fixture']
        with patch.dict(os.environ, {'FIXTURE_KEY': SECRET}), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            self.assertEqual(main(args), 0)
            self.assertEqual(main(['models', 'status', str(self.root)]), 0)
            self.assertEqual(main(['models', 'test-connection', str(self.root), '--workflow', 'extract',
                                   '--run-id', 'cli-test', '--execute']), 0)
            self.assertEqual(main(['models', 'connection-history', str(self.root), '--run-id', 'cli-test']), 0)
            self.assertNotIn(SECRET, stdout.getvalue()); self.assert_no_secret()
        self.assertEqual(len(self.requests), 1)
