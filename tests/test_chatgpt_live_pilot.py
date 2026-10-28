"""Owner pilot helper only; disposable fixtures, no live credentials or requests."""
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from corpustrail._internal.values import ContractError
from corpustrail.chatgpt.connection import ChatGPTConnection, DIRECT
from corpustrail.chatgpt.credentials import CredentialStore

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('chatgpt_live_pilot', ROOT/'tools/chatgpt_live_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class OwnerPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ct-owner-pilot-offline-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'project'
        self.network = patch('socket.socket.connect', side_effect=AssertionError('No network authorized'))
        self.network.start(); self.addCleanup(self.network.stop)

    def store(self):
        store = CredentialStore(Path(self.temp.name)/'synthetic-private')
        with store.transaction() as state:
            state['active'] = 'synthetic'; state['profiles']['synthetic'] = {
                'client_id': 'synthetic-client', 'subject': 'synthetic-subject', 'scope': DIRECT,
                'refresh_token': 'synthetic-refresh', 'access_token': 'synthetic-access'}
        return store

    def test_fresh_one_paper_no_authority_no_eligible_references_and_reopen(self):
        with patch.object(pilot, 'CredentialStore', side_effect=AssertionError('Preparation must not inspect credentials')):
            result = pilot.prepare(self.root)
        self.assertEqual(result['publications'], 1); self.assertFalse(result['network_used'])
        status = pilot.inspect(self.root)
        self.assertTrue(status['membership_unchanged']); self.assertEqual(status['human_observations'], 0)
        self.assertEqual(status['assessment_runs'], 0)
        from corpustrail.project import Project
        project = Project.open(self.root)
        version = project.references.versions()['items'][0]
        self.assertEqual(version['counts']['unattested'], 1)
        member = project.references.members(version['version_id'])['items'][0]
        self.assertFalse(member['human_attested'])

    def test_existing_project_refused_without_rewriting(self):
        pilot.prepare(self.root)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(FileExistsError): pilot.prepare(self.root)
        self.assertEqual(before, {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_unmarked_project_and_alias_refused(self):
        pilot.prepare(self.root)
        (self.root/pilot.MARKER).rename(self.root/'saved-marker.json')
        with self.assertRaises(FileNotFoundError): pilot.inspect(self.root)
        alias = Path(self.temp.name)/'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ContractError): pilot.prepare(alias/'new')

    def test_no_charge_requires_exact_owner_observation_and_eligible_same_device_profile(self):
        store = self.store(); before = store.path.read_bytes()
        for phrase in ('', 'Signed in successfully', 'Weekly cap is ten percent'):
            with self.assertRaises(ContractError): pilot.record_no_charge(phrase, store=store)
        self.assertEqual(store.path.read_bytes(), before)
        with store.transaction() as state: state['profiles']['synthetic']['scope'] = 'openid'
        with self.assertRaises(ContractError): pilot.record_no_charge(pilot.CONFIRMATION, store=store)
        empty = CredentialStore(Path(self.temp.name)/'empty-private')
        with self.assertRaises(ContractError): pilot.record_no_charge(pilot.CONFIRMATION, store=empty)
        self.assertFalse(empty.root.exists())

    def test_record_is_private_bound_expiring_and_never_inference_consent(self):
        store = self.store()
        result = pilot.record_no_charge(pilot.CONFIRMATION, store=store)
        profile = store.read()['profiles']['synthetic']
        self.assertTrue(ChatGPTConnection._cost_permitted(profile))
        self.assertFalse(result['inference_authorized']); self.assertFalse(result['network_used'])
        self.assertFalse(result['provider_settings_changed'])
        self.assertNotIn('synthetic-refresh', json.dumps(result))
        self.assertNotIn('synthetic-access', json.dumps(result))
        self.assertNotIn('synthetic-subject', json.dumps(result))
        self.assertLessEqual(profile['plan_only_permit']['expires_at'], time.time()+1800)
        profile['subject'] = 'another-subject'
        self.assertFalse(ChatGPTConnection._cost_permitted(profile))
        profile['subject'] = 'synthetic-subject'; profile['plan_only_permit']['expires_at'] = 0
        self.assertFalse(ChatGPTConnection._cost_permitted(profile))

    def test_malformed_private_profile_cannot_be_attested(self):
        store = self.store()
        with store.transaction() as state: state['profiles']['synthetic'] = ['not-a-profile']
        with self.assertRaises(ContractError): pilot.record_no_charge(pilot.CONFIRMATION, store=store)

    def test_cli_private_store_failure_is_nonzero_without_secret_or_path(self):
        out = io.StringIO(); err = io.StringIO()
        with patch('sys.argv', ['helper', 'record-no-charge']), patch('builtins.input', return_value=pilot.CONFIRMATION), \
                patch.object(pilot, 'CredentialStore', side_effect=PermissionError('synthetic-secret-or-private-path')), \
                redirect_stdout(out), redirect_stderr(err):
            code = pilot.main()
        self.assertEqual(code, 1)
        self.assertNotIn('synthetic-secret-or-private-path', out.getvalue()+err.getvalue())
        self.assertIn('no request was sent', err.getvalue())

    def test_offline_preview_has_exactly_one_target_no_reference_text_and_persists_proposal(self):
        from corpustrail.application.chatgpt import ChatGPTController
        from corpustrail.application.curation import CurationController
        from corpustrail.project import Project
        from test_chatgpt_assessment import synthetic_connection
        pilot.prepare(self.root); project = Project.open(self.root)
        marker = json.loads((self.root/pilot.MARKER).read_text())
        client = synthetic_connection(Path(self.temp.name))
        curation = CurationController(); app = ChatGPTController(curation, connection_client=client, synthetic=True)
        self.addCleanup(curation.close); self.addCleanup(app.close)
        preview = app.preview(project, {'request_id':uuid.uuid4().hex,'actor':'pilot_owner',
            'population_version_id':marker['population_version_id'],
            'reference_version_id':marker['reference_version_id'],'model':'fixture-model'})
        self.assertEqual(len(preview['manifest']['requests']),1)
        wire = preview['manifest']['requests'][0]['payload']
        supplied = json.loads(wire['input'][0]['content'])
        self.assertEqual(supplied['target']['title'], pilot.TITLE)
        self.assertEqual(supplied['target']['abstract'], pilot.ABSTRACT)
        self.assertEqual(supplied['reference_examples'], [])
        self.assertEqual(client.transport.sent, [])
        started = app.command(project,'confirm', {'request_id':uuid.uuid4().hex,'preview_id':preview['preview_id'],
            'preview_sha256':preview['preview_sha256'],'confirmed':True,'confirm_external':True})
        deadline=time.monotonic()+10
        while curation.run(project,started['run_id'])['local_worker_active'] and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertFalse(curation.run(project,started['run_id'])['local_worker_active'])
        result=pilot.inspect(self.root)
        self.assertTrue(result['membership_unchanged']); self.assertEqual(result['assessment_runs'],1)
        self.assertEqual(result['runs'][0]['status'],'completed')
        self.assertEqual(len(client.transport.sent),1)
