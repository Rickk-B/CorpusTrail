"""Synthetic OAuth/Responses fixtures only. Never contacts or signs in to OpenAI."""
from contextlib import closing
import base64
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit

from corpustrail._internal.values import ContractError
from corpustrail.chatgpt.connection import ChatGPTConnection, IdentityVerifier, DIRECT, installed
from corpustrail.chatgpt.credentials import CredentialStore
from corpustrail.chatgpt.transport import AUTH, API, TOKEN, JWKS, DISCOVERY, Transport, ConnectionFailure


class Stream(io.BytesIO):
    status = 200


def event(kind, **fields):
    return ('data: ' + json.dumps({'type': kind, **fields}) + '\n\n').encode()


class FixtureTransport:
    def __init__(self):
        self.calls = []; self.tokens = None; self.keys = None; self.failure = None
        self.catalog = {'models': [{'slug': 'fixture-model', 'display_name': 'Offline synthetic model', 'visibility': 'list'},
                                   {'slug': 'hidden-fixture', 'display_name': 'Hidden', 'visibility': 'hide'}]}
    def json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.failure: raise self.failure
        if url == JWKS: return self.keys
        if url == TOKEN: return self.tokens
        if url == API + '/models': return self.catalog
        if url == DISCOVERY: return {'revocation_endpoint': AUTH + '/oauth/revoke'}
        raise AssertionError('Unexpected fixture endpoint')
    def _request(self, url, **kwargs):
        self.calls.append((url, kwargs)); return Stream()


class StoreAndTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = CredentialStore(self.root / 'private')
        self.transport = FixtureTransport()
        self.app = ChatGPTConnection(store=self.store, transport=self.transport)
        self.addCleanup(self.app.close)

    def test_open_has_no_writes_or_network_or_credential_discovery(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-key-must-never-be-read'}):
            self.assertFalse(self.app.status()['connected'])
        self.assertFalse(self.store.root.exists()); self.assertEqual(self.transport.calls, [])

    def test_stable_host_atomic_storage_permissions_and_disconnect(self):
        host = self.store.host_id(); self.assertTrue(host.startswith('urn:uuid:'))
        self.assertEqual(CredentialStore(self.store.root).host_id(), host)
        with self.store.transaction() as value:
            value['active'] = 'synthetic-profile'
            value['profiles']['synthetic-profile'] = {'client_id': 'oaiapp_fixture', 'subject': 'synthetic-subject',
                'scope': DIRECT, 'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
                'id_token': 'synthetic-id', 'expires_at': time.time() + 3600}
        self.assertTrue(self.app.status()['connected'])
        self.assertNotIn('synthetic-access', json.dumps(self.app.status()))
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.store.root.stat().st_mode), 0o700)
        elif os.name == 'nt':
            self.assertNotIn(b'synthetic-refresh', self.store.path.read_bytes())
        result = self.app.disconnect()
        self.assertTrue(result['revocation_confirmed']); self.assertTrue(result['local_tokens_removed'])
        after = self.store.read(); self.assertEqual(after['host_id'], host)
        self.assertEqual(after['profiles']['synthetic-profile']['client_id'], 'oaiapp_fixture')
        self.assertNotIn('synthetic-refresh', json.dumps(after))
        self.assertFalse(self.app.status()['connected'])

    @unittest.skipUnless(os.name == 'posix', 'POSIX credential permission checks')
    def test_unsafe_permissions_links_and_interrupted_atomic_write_fail_closed(self):
        self.store.host_id(); old = self.store.path.read_bytes()
        with patch('corpustrail.chatgpt.credentials.os.replace', side_effect=OSError('synthetic interruption')):
            with self.assertRaises(OSError):
                with self.store.transaction() as value: value['active'] = 'not-committed'
        self.assertEqual(self.store.path.read_bytes(), old)
        self.assertEqual([p.name for p in self.store.root.iterdir()], ['credentials.json'])
        self.store.path.chmod(0o644)
        with self.assertRaises(ContractError): self.store.read()
        self.store.path.chmod(0o600)
        link = self.root / 'link'; link.symlink_to(self.store.root, target_is_directory=True)
        with self.assertRaises(ContractError): CredentialStore(link).read()

    def seed(self):
        with self.store.transaction() as value:
            value['host_id'] = 'urn:uuid:00000000-0000-4000-8000-000000000001'; value['active'] = 'fixture'
            value['profiles']['fixture'] = {'client_id': 'oaiapp_fixture', 'subject': 'fixture-subject',
                'scope': DIRECT, 'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
                'id_token': 'synthetic-id', 'expires_at': time.time() + 3600}

    def test_live_gate_blocks_even_with_identity_scope_models_and_api_key(self):
        self.seed(); self.assertEqual(self.app.catalog()[0]['slug'], 'fixture-model')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'never-use-me'}):
            with self.assertRaisesRegex(ConnectionFailure, 'no_cost_not_verified'):
                self.app.access('fixture', inference=True)
        self.assertFalse(self.app.status()['no_extra_charge_verified'])
        self.assertEqual(len(self.transport.calls), 1)

    def test_refresh_is_serialized_rotation_persists_and_terminal_error_clears_tokens(self):
        self.seed()
        with self.store.transaction() as state: state['profiles']['fixture']['expires_at'] = 0
        self.transport.tokens = {'access_token': 'synthetic-access-new', 'refresh_token': 'synthetic-refresh-new',
                                 'token_type': 'Bearer', 'expires_in': 3600}
        self.assertEqual(self.app.access('fixture'), 'synthetic-access-new')
        self.assertEqual(self.store.read()['profiles']['fixture']['refresh_token'], 'synthetic-refresh-new')
        body = parse_qs(self.transport.calls[0][1]['body'].decode())
        self.assertNotIn('scope', body); self.assertEqual(body['client_id'], ['oaiapp_fixture'])
        with self.store.transaction() as state: state['profiles']['fixture']['expires_at'] = 0
        self.transport.failure = ConnectionFailure('reauthenticate')
        with self.assertRaises(ConnectionFailure): self.app.access('fixture')
        self.assertFalse(self.app.status()['connected']); self.assertNotIn('access_token', self.store.read()['profiles']['fixture'])

    def test_temporary_refresh_failure_preserves_reauth_mapping_and_tokens(self):
        self.seed()
        with self.store.transaction() as state: state['profiles']['fixture']['expires_at'] = 0
        before = self.store.path.read_bytes(); self.transport.failure = ConnectionFailure('transport')
        with self.assertRaises(ConnectionFailure): self.app.access('fixture')
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_refresh_scope_loss_commits_rotating_token_without_claiming_eligibility(self):
        self.seed()
        with self.store.transaction() as state: state['profiles']['fixture']['expires_at'] = 0
        self.transport.tokens = {'access_token': 'new-access', 'refresh_token': 'new-refresh',
                                 'token_type': 'Bearer', 'expires_in': 3600, 'scope': 'openid'}
        with self.assertRaisesRegex(ConnectionFailure, 'plan_scope_missing'): self.app.access('fixture')
        self.assertEqual(self.store.read()['profiles']['fixture']['refresh_token'], 'new-refresh')
        self.assertFalse(self.app.status()['eligible_scope'])

    def test_models_malformed_and_duplicate_catalog_are_rejected(self):
        self.seed()
        for response in ({'data': []}, {'models': [{'slug': 'bad\nmodel', 'display_name': 'Bad', 'visibility': 'list'}]},
                         {'models': self.transport.catalog['models'][:1] * 2}):
            self.transport.catalog = response
            with self.assertRaises(ConnectionFailure): self.app.catalog()

    def test_http_transport_tls_fixed_urls_no_redirect_or_ambient_api_key(self):
        calls = []
        def open_request(req, timeout):
            calls.append(req); return Stream(b'{"models": []}')
        transport = Transport(open_request=open_request)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'not-used'}): transport.json(API + '/models')
        self.assertIsNone(calls[0].get_header('Authorization'))
        for url in ('http://api.openai.com/v1/models', 'https://attacker.invalid/models', API + '/models?access_token=bad'):
            with self.assertRaises(ConnectionFailure): transport.json(url)
        self.assertEqual(len(calls), 1)
        for code in (301, 401, 403, 429, 500, 503):
            def fail(req, timeout, code=code): raise HTTPError(req.full_url, code, 'synthetic', {}, Stream(b'{"detail":"private synthetic body"}'))
            with self.assertRaises(ConnectionFailure) as error: Transport(open_request=fail).json(API + '/models')
            self.assertNotIn('private', str(error.exception)); self.assertEqual(error.exception.status, code)
        def fail(req, timeout): raise URLError('synthetic private path and proxy information')
        with self.assertRaisesRegex(ConnectionFailure, '^transport$'): Transport(open_request=fail).json(API + '/models')

    def test_stream_requires_completed_event_and_preserves_error_categories(self):
        payload = {'model': 'synthetic', 'store': False, 'stream': True, 'input': []}
        complete = {'id': 'synthetic-response', 'status': 'completed', 'model': 'synthetic', 'output': []}
        def run(raw, cancelled=lambda: False):
            return Transport(open_request=lambda *args, **kwargs: Stream(raw)).response(payload, bearer='synthetic-access', cancelled=cancelled)
        response, receipt = run(event('response.created') + event('response.completed', response=complete))
        self.assertEqual(response, complete); self.assertEqual(receipt['terminal_event'], 'response.completed')
        with self.assertRaisesRegex(ConnectionFailure, '^interrupted$') as incomplete: run(event('response.output_text.delta', delta='partial'))
        self.assertEqual(incomplete.exception.diagnostics['partial_output_text'], 'partial')
        with self.assertRaisesRegex(ConnectionFailure, '^incomplete$'): run(event('response.incomplete', response={}))
        for code, category in [('subscription_sharing_usage_limit_exceeded', 'usage_limit'),
                               ('subscription_sharing_usage_unavailable', 'usage_unavailable'),
                               ('subscription_sharing_user_not_eligible', 'ineligible')]:
            with self.assertRaisesRegex(ConnectionFailure, '^' + category + '$'):
                run(event('response.failed', response={'error': {'code': code}}))
        with self.assertRaisesRegex(ConnectionFailure, '^cancelled$'): run(b'', cancelled=lambda: True)
        with self.assertRaisesRegex(ConnectionFailure, '^resource_limit$'): run(b'x' * 270000)


@unittest.skipUnless(installed(), 'Optional chatgpt extra not installed; manual/core remains independent')
class SignedIdentityTests(unittest.TestCase):
    def setUp(self):
        StoreAndTransportTests.setUp(self)
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        self.jwt = jwt; self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.transport.keys = {'keys': [{**jwk, 'kid': 'synthetic-key', 'use': 'sig', 'alg': 'RS256'}]}

    def signed(self, **changes):
        claims = {'iss': AUTH, 'aud': 'oaiapp_fixture', 'sub': 'fixture-subject', 'iat': int(time.time()),
                  'exp': int(time.time()) + 3600, 'nonce': 'synthetic-nonce', **changes}
        return self.jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'synthetic-key'})

    def test_signature_claims_nonce_account_and_algorithm_validation(self):
        verifier = IdentityVerifier(self.transport)
        good = self.signed()
        self.assertEqual(verifier.verify(good, 'oaiapp_fixture', nonce='synthetic-nonce')['sub'], 'fixture-subject')
        for token in (self.signed(iss='https://attacker.invalid'), self.signed(aud='wrong-registration'),
                      self.signed(exp=int(time.time())-60), self.signed(nonce='wrong-nonce'),
                      self.jwt.encode({'sub': 'forged'}, 'synthetic-hmac-key-for-offline-negative-test-only', algorithm='HS256', headers={'kid': 'synthetic-key'})):
            with self.assertRaisesRegex(ConnectionFailure, 'invalid_identity'):
                verifier.verify(token, 'oaiapp_fixture', nonce='synthetic-nonce')
        with self.assertRaisesRegex(ConnectionFailure, 'account_mismatch'):
            verifier.verify(good, 'oaiapp_fixture', expected_subject='other-subject')
        self.assertEqual(len(self.transport.calls), 1)

    def test_invalid_signature_unknown_key_and_multi_audience_reject_without_redirected_jwks(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        verifier = IdentityVerifier(self.transport)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {'iss': AUTH, 'aud': 'oaiapp_fixture', 'sub': 'fixture-subject',
                  'iat': int(time.time()), 'exp': int(time.time())+3600}
        forged = self.jwt.encode(claims, other, algorithm='RS256', headers={'kid':'synthetic-key', 'jku':'https://attacker.invalid/keys'})
        with self.assertRaisesRegex(ConnectionFailure, 'invalid_identity'): verifier.verify(forged, 'oaiapp_fixture')
        unknown = self.jwt.encode(claims, self.key, algorithm='RS256', headers={'kid':'unknown-key'})
        with self.assertRaisesRegex(ConnectionFailure, 'invalid_identity'): verifier.verify(unknown, 'oaiapp_fixture')
        with self.assertRaisesRegex(ConnectionFailure, 'invalid_identity'):
            verifier.verify(self.signed(aud=['oaiapp_fixture','other-app']), 'oaiapp_fixture')
        self.assertTrue(all(url == JWKS for url, _ in self.transport.calls))

    def test_actual_loopback_callback_pkce_registration_and_restart(self):
        start = self.app.begin(return_url='http://127.0.0.1:8766/chatgpt'); auth = urlsplit(start['authorization_url']); fields = parse_qs(auth.query)
        self.assertEqual(auth.netloc, 'auth.openai.com'); self.assertEqual(fields['client_id'], ['dynamic_agent_client'])
        self.assertEqual(fields['agent_name_hint'], ['CorpusTrail'])
        verifier = self.app._pending['verifier']
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        self.assertEqual(fields['code_challenge'], [challenge])
        self.transport.tokens = {'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
            'token_type': 'Bearer', 'expires_in': 3600, 'scope': 'openid ' + DIRECT,
            'id_token': self.signed(nonce=fields['nonce'][0])}
        callback = urlsplit(fields['redirect_uri'][0])
        with closing(http.client.HTTPConnection('127.0.0.1', callback.port, timeout=10)) as client:
            client.request('GET', callback.path+'?'+urlencode({'state': fields['state'][0], 'code': 'synthetic-code', 'client_id': 'oaiapp_fixture'}))
            reply = client.getresponse(); self.assertEqual(reply.status, 200); body=reply.read(); self.assertNotIn(b'synthetic-access', body); self.assertIn(b'Back to CorpusTrail',body)
        self.assertTrue(self.app.status()['connected']); self.assertTrue(self.app.status()['eligible_scope'])
        exchange = parse_qs(next(kw['body'].decode() for url, kw in self.transport.calls if url == TOKEN))
        self.assertEqual(exchange['client_id'], ['oaiapp_fixture']); self.assertEqual(exchange['redirect_uri'], fields['redirect_uri'])
        self.assertNotIn('client_secret', exchange)
        restarted = ChatGPTConnection(store=CredentialStore(self.store.root), transport=self.transport)
        self.addCleanup(restarted.close)
        self.assertTrue(restarted.status()['connected']); self.assertFalse(restarted.status()['no_extra_charge_verified'])
        self.app.cancel_sign_in()
        returning = parse_qs(urlsplit(restarted.begin()['authorization_url']).query)
        self.assertEqual(returning['client_id'], ['oaiapp_fixture']); self.assertNotIn('agent_name_hint', returning)
        self.assertEqual(returning['ext_agent_host_id'], fields['ext_agent_host_id'])

    def test_invalid_state_decline_missing_registration_and_replay_have_no_token_exchange(self):
        for case in ('wrong_state', 'declined', 'missing_registration'):
            self.app.begin(); pending = self.app._pending
            fields = {'state': pending['state'] if case != 'wrong_state' else 'incorrect', 'code': 'synthetic-code'}
            if case == 'declined': fields['error'] = 'access_denied'
            self.assertFalse(self.app.finish(urlencode(fields), pending))
            self.assertEqual(self.transport.calls, [])
            self.app.cancel_sign_in()
        self.assertFalse(self.app.finish(urlencode(fields), pending))
        self.assertEqual(self.transport.calls, [])

    def test_code_exchange_failure_retains_issued_registration_without_connected_identity(self):
        self.app.begin(); pending = self.app._pending
        self.transport.failure = ConnectionFailure('reauthenticate')
        self.assertFalse(self.app.finish(urlencode({'state':pending['state'],'code':'synthetic-code','client_id':'oaiapp_fixture'}), pending))
        saved = self.store.read()
        self.assertEqual(saved['profiles'][saved['active']]['client_id'], 'oaiapp_fixture')
        self.assertFalse(self.app.status()['connected'])
        self.app.cancel_sign_in(); self.transport.failure = None
        fields = parse_qs(urlsplit(self.app.begin()['authorization_url']).query)
        self.assertEqual(fields['client_id'], ['oaiapp_fixture'])
