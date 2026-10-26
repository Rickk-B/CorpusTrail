"""Public-client PKCE sign-in, verified identity and serialized token rotation.

No account probing on page open. Only explicit connect/catalog/disconnect actions
contact fixed OpenAI endpoints. Inference additionally needs a separate permit.
"""
import base64
from importlib.util import find_spec
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import hmac
from html import escape
import secrets
import re
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from corpustrail._internal.values import ContractError, content_hash
from .credentials import CredentialStore
from .transport import AUTH, API, TOKEN, JWKS, DISCOVERY, Transport, ConnectionFailure

SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
DIRECT = 'chatgpt.tokens.use.direct'


def installed():
    return find_spec('jwt') is not None and find_spec('cryptography') is not None


class IdentityVerifier:
    def __init__(self, transport):
        self.transport = transport; self._keys = None; self._saved = 0

    def verify(self, token, client_id, *, nonce=None, expected_subject=None):
        if not installed(): raise ConnectionFailure('optional_dependency_missing')
        import jwt
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
                raise ConnectionFailure('invalid_identity')
            candidates = []
            for refresh in (False, True):
                if refresh or self._keys is None or time.monotonic() - self._saved > 600:
                    self._keys = self.transport.json(JWKS); self._saved = time.monotonic()
                candidates = [key for key in self._keys.get('keys', []) if key.get('kid') == header['kid'] and
                              key.get('kty') == 'RSA' and key.get('use', 'sig') == 'sig' and key.get('alg', 'RS256') == 'RS256']
                if candidates: break
            if len(candidates) != 1: raise ConnectionFailure('invalid_identity')
            key = jwt.PyJWK.from_dict(candidates[0], algorithm='RS256').key
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=AUTH, audience=client_id,
                leeway=5, options={'require': ['sub', 'exp', 'iat', 'iss', 'aud']})
            if isinstance(claims.get('aud'), list) and len(claims['aud']) > 1 and claims.get('azp') != client_id:
                raise ConnectionFailure('invalid_identity')
            if not isinstance(claims['sub'], str) or not claims['sub'] or len(claims['sub']) > 512:
                raise ConnectionFailure('invalid_identity')
            if nonce is not None and (not isinstance(claims.get('nonce'), str) or not hmac.compare_digest(claims['nonce'], nonce)):
                raise ConnectionFailure('invalid_identity')
            if expected_subject is not None and claims['sub'] != expected_subject:
                raise ConnectionFailure('account_mismatch')
            return claims
        except ConnectionFailure: raise
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            raise ConnectionFailure('invalid_identity') from None


def _single(query, name, *, optional=False):
    values = query.get(name)
    if optional and values is None: return None
    if not values or len(values) != 1 or not values[0] or len(values[0]) > 16384:
        raise ConnectionFailure('invalid_callback')
    return values[0]


def _tokens(value, *, old=None):
    old = old or {}
    if value.get('token_type', '').lower() != 'bearer': raise ConnectionFailure('invalid_tokens')
    access = value.get('access_token'); refresh = value.get('refresh_token', old.get('refresh_token'))
    expiry = value.get('expires_in')
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh or type(expiry) not in (int, float) or not 0 < expiry <= 86400:
        raise ConnectionFailure('invalid_tokens')
    if any(len(t) > 32768 or any(ord(c) < 33 or ord(c) > 126 for c in t) for t in (access, refresh)):
        raise ConnectionFailure('invalid_tokens')
    scope = value.get('scope', old.get('scope'))
    if not isinstance(scope, str) or len(scope) > 4000: raise ConnectionFailure('invalid_tokens')
    return {'access_token': access, 'refresh_token': refresh, 'token_type': 'Bearer',
            'expires_at': time.time() + expiry, 'scope': scope,
            'id_token': value.get('id_token', old.get('id_token'))}


class ChatGPTConnection:
    def __init__(self, *, store=None, transport=None, verifier=None):
        self.store = store if store is not None else CredentialStore()
        self.transport = transport if transport is not None else Transport()
        self.verifier = verifier if verifier is not None else IdentityVerifier(self.transport)
        self._lock = threading.RLock(); self._pending = None; self._callback = None
        self._state = 'disconnected'; self._models = {}; self._cancel = threading.Event()

    def status(self):
        value = self.store.read(); profile = value['profiles'].get(value['active'])
        pending = self._pending
        if pending and time.monotonic() > pending['deadline']: self.cancel_sign_in()
        scope = profile.get('scope', '').split() if profile else []
        return {'installed': installed(), 'connected': bool(profile and profile.get('refresh_token')),
            'profile_id': value['active'], 'label': profile.get('label') if profile else None,
            'eligible_scope': DIRECT in scope, 'state': self._state,
            'plan_notice_required': bool(profile and profile.get('refresh_token') and DIRECT in scope and not profile.get('plan_notice_acknowledged')),
            'sign_in_pending': self._pending is not None, 'models': self._models.get(value['active'], []),
            'no_extra_charge_verified': self._cost_permitted(profile),
            'notice': 'Local projects stay on this computer. Explicitly authorized title/abstract requests are processed by OpenAI. No API-key billing or credit purchase is supported.'}

    @staticmethod
    def _cost_permitted(profile):
        # There is no documented provider endpoint/request flag that establishes
        # credit fallback is disabled. HTTP forms cannot grant this permit.
        permit = profile.get('plan_only_permit') if profile else None
        return bool(isinstance(permit, dict) and permit.get('client_id') == profile.get('client_id') and
                    permit.get('subject') == profile.get('subject') and
                    permit.get('credits_disabled_verified') is True and
                    isinstance(permit.get('owner_evidence_sha256'), str) and
                    re.fullmatch('[0-9a-f]{64}', permit['owner_evidence_sha256']) is not None and
                    type(permit.get('expires_at')) in (int, float) and permit['expires_at'] > time.time())

    def begin(self, *, return_url=None):
        if return_url is not None:
            value = urlsplit(return_url)
            if value.scheme != 'http' or value.hostname != '127.0.0.1' or not value.port or value.path != '/chatgpt' or value.query or value.fragment or value.username or value.password:
                raise ConnectionFailure('invalid_return_location')
        if not installed(): raise ConnectionFailure('optional_dependency_missing')
        if self._callback is not None and self._pending is None: self._close_callback()
        with self._lock:
            if self._pending: raise ConnectionFailure('sign_in_already_pending')
            self._cancel.clear()
            host = self.store.host_id(); saved = self.store.read()
            old = saved['profiles'].get(saved['active'])
            attempt = {'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32),
                       'verifier': secrets.token_urlsafe(48), 'deadline': time.monotonic() + 180,
                       'client_id': old['client_id'] if old else None,
                       'subject': old['subject'] if old else None}
            connection = self
            class Callback(BaseHTTPRequestHandler):
                timeout = 10
                def log_message(self, *_): pass
                def do_GET(self):
                    route = urlsplit(self.path)
                    valid_host = self.headers.get_all('Host') == ['127.0.0.1:' + str(self.server.server_port)]
                    if not valid_host or route.path != '/auth/callback' or len(self.path) > 24000:
                        self.send_error(400); return
                    ok = connection.finish(route.query, attempt)
                    message = ('ChatGPT connection completed.' if ok else 'ChatGPT connection did not complete.')
                    link = ('<p><a href="' + escape(return_url, quote=True) + '">Back to CorpusTrail</a></p>') if return_url else '<p>Return to your CorpusTrail window.</p>'
                    raw = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CorpusTrail connection</title><body><h1>' + message + '</h1>' + link + '</body></html>').encode()
                    self.send_response(200 if ok else 400)
                    for k, v in {'Content-Type': 'text/html; charset=utf-8', 'Content-Length': str(len(raw)),
                                 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"}.items(): self.send_header(k, v)
                    self.end_headers(); self.wfile.write(raw)
                def do_POST(self): self.send_error(405)
            server = HTTPServer(('127.0.0.1', 0), Callback)
            attempt['redirect_uri'] = 'http://127.0.0.1:' + str(server.server_port) + '/auth/callback'
            self._pending = attempt; self._callback = server; self._state = 'signing_in'
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True).start()
            fields = {'client_id': attempt['client_id'] or 'dynamic_agent_client',
                      'ext_agent_host_id': host, 'response_type': 'code', 'redirect_uri': attempt['redirect_uri'],
                      'scope': SCOPES, 'resource': API, 'state': attempt['state'], 'nonce': attempt['nonce'],
                      'code_challenge_method': 'S256', 'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(attempt['verifier'].encode()).digest()).decode().rstrip('=')}
            if attempt['client_id'] is None: fields['agent_name_hint'] = 'CorpusTrail'
            # No ID/email hints in a browser-facing URL; returning registration is
            # identified by its issued client ID. No auth URL is persisted/logged.
            return {'authorization_url': AUTH + '/api/accounts/authorize?' + urlencode(fields)}

    def finish(self, query, attempt):
        try:
            values = parse_qs(query, keep_blank_values=True, max_num_fields=12)
            with self._lock:
                if self._pending is not attempt or attempt.get('consumed') or time.monotonic() > attempt['deadline']:
                    raise ConnectionFailure('invalid_callback')
                if not hmac.compare_digest(_single(values, 'state'), attempt['state']):
                    raise ConnectionFailure('invalid_callback')
                attempt['consumed'] = True
                if 'error' in values: raise ConnectionFailure('consent_declined')
                client_id = _single(values, 'client_id', optional=True) or attempt['client_id']
                if not isinstance(client_id, str) or not client_id.startswith('oaiapp_') or len(client_id) > 512:
                    raise ConnectionFailure('missing_registration')
                if attempt['client_id'] and attempt['client_id'] != client_id:
                    raise ConnectionFailure('registration_mismatch')
                code = _single(values, 'code')
                # Retain an issued registration before exchange, even if its code
                # expires. It is never accepted as a verified connected identity.
                attempt['client_id'] = client_id
                with self.store.transaction() as saved:
                    if saved['active'] is None:
                        registration = 'pending:' + content_hash(client_id)
                        saved['profiles'][registration] = {'client_id': client_id, 'subject': None,
                            'label': 'ChatGPT registration pending verified identity'}
                        saved['active'] = registration
            body = urlencode({'grant_type': 'authorization_code', 'client_id': client_id, 'code': code,
                'code_verifier': attempt['verifier'], 'redirect_uri': attempt['redirect_uri'], 'resource': API}).encode()
            result = self.transport.json(TOKEN, body=body, form=True)
            credentials = _tokens(result)
            identity = self.verifier.verify(credentials['id_token'], client_id, nonce=attempt['nonce'], expected_subject=attempt['subject'])
            pid = content_hash({'issuer': AUTH, 'subject': identity['sub'], 'client_id': client_id})
            with self._lock:
                if self._pending is not attempt or self._cancel.is_set(): raise ConnectionFailure('cancelled')
                with self.store.transaction() as state:
                    prior = state['profiles'].get(pid, {})
                    state['profiles'][pid] = {**prior, **credentials, 'client_id': client_id, 'subject': identity['sub'],
                        'issuer': AUTH, 'label': prior.get('label', 'ChatGPT registration ' + str(len(state['profiles']) + 1)),
                        'plan_only_permit': None}
                    pending_id = state['active']
                    if pending_id and pending_id.startswith('pending:'): state['profiles'].pop(pending_id, None)
                    state['active'] = pid
                self._pending = None
                self._state = 'connected' if DIRECT in credentials['scope'].split() else 'plan_scope_missing'
            return True
        except (ConnectionFailure, ContractError, OSError, ValueError, TypeError, KeyError) as exc:
            with self._lock:
                if self._pending is attempt:
                    self._pending = None
                    self._state = exc.kind if isinstance(exc, ConnectionFailure) else 'local_connection_failure'
            return False

    def cancel_sign_in(self):
        with self._lock:
            self._pending = None; self._state = 'sign_in_cancelled'; self._cancel.set()
        self._close_callback()

    def _close_callback(self):
        server = self._callback; self._callback = None
        if server is not None:
            server.shutdown(); server.server_close()

    def access(self, profile_id, *, inference=False):
        if self._cancel.is_set(): raise ConnectionFailure('cancelled')
        with self.store.transaction() as state:
            if state['active'] != profile_id: raise ConnectionFailure('account_changed')
            profile = state['profiles'].get(profile_id)
            if not profile or not profile.get('refresh_token'): raise ConnectionFailure('authentication')
            if DIRECT not in profile.get('scope', '').split(): raise ConnectionFailure('plan_scope_missing')
            if inference and not self._cost_permitted(profile): raise ConnectionFailure('no_cost_not_verified')
            if profile['expires_at'] <= time.time() + 60:
                try:
                    result = self.transport.json(TOKEN, body=urlencode({'grant_type': 'refresh_token',
                        'client_id': profile['client_id'], 'refresh_token': profile['refresh_token'], 'resource': API}).encode(), form=True)
                    new = _tokens(result, old=profile)
                    if result.get('id_token'):
                        self.verifier.verify(new['id_token'], profile['client_id'], expected_subject=profile['subject'])
                    profile.update(new)
                    if DIRECT not in profile['scope'].split():
                        self.store._write(state)  # Rotated tokens must survive a scope-rejection path.
                        raise ConnectionFailure('plan_scope_missing')
                except ConnectionFailure as exc:
                    if exc.kind in {'reauthenticate', 'invalid_identity', 'account_mismatch'}:
                        # Commit local invalidation even when returning a failure.
                        for key in ('access_token', 'refresh_token', 'id_token', 'plan_only_permit'): profile.pop(key, None)
                        self.store._write(state)
                    raise
            return profile['access_token']

    def catalog(self):
        pid = self.store.read()['active']
        token = self.access(pid)
        value = self.transport.json(API + '/models', bearer=token)
        models = value.get('models')
        if not isinstance(models, list) or len(models) > 1000: raise ConnectionFailure('malformed_catalog')
        results = []
        for row in models:
            if not isinstance(row, dict): raise ConnectionFailure('malformed_catalog')
            if row.get('visibility') != 'list': continue
            if (not isinstance(row.get('slug'), str) or not 0 < len(row['slug']) <= 200 or
                    any(ord(c) < 33 or ord(c) > 126 for c in row['slug']) or
                    not isinstance(row.get('display_name'), str) or len(row['display_name']) > 200):
                raise ConnectionFailure('malformed_catalog')
            results.append({'slug': row['slug'], 'display_name': row['display_name']})
        if len({m['slug'] for m in results}) != len(results): raise ConnectionFailure('malformed_catalog')
        self._models = {pid: results}
        return results

    def disconnect(self):
        self._cancel.set(); self.cancel_sign_in()
        revoked = False
        with self.store.transaction() as state:
            profile = state['profiles'].get(state['active'])
            if profile and profile.get('refresh_token'):
                try:
                    config = self.transport.json(DISCOVERY)
                    endpoint = config.get('revocation_endpoint')
                    # Discovery may not redirect or introduce an arbitrary URL.
                    if endpoint not in {AUTH + '/api/accounts/oauth/revoke', AUTH + '/oauth/revoke'}:
                        raise ConnectionFailure('revocation_unconfirmed')
                    with self.transport._request(endpoint, body=urlencode({'token': profile['refresh_token'],
                        'token_type_hint': 'refresh_token', 'client_id': profile['client_id']}).encode(), form=True): pass
                    revoked = True
                except (ConnectionFailure, OSError): pass
                for key in ('access_token', 'refresh_token', 'id_token', 'plan_only_permit', 'expires_at', 'scope'):
                    profile.pop(key, None)
            self._models.clear(); self._state = 'disconnected'
        return {'local_tokens_removed': True, 'revocation_confirmed': revoked,
                'notice': 'Disconnected locally. If revocation could not be confirmed, also disconnect CorpusTrail in ChatGPT Settings → Security and login → Sign in with ChatGPT.'}

    def close(self):
        self._cancel.set(); self._pending = None; self._close_callback()
