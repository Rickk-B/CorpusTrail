"""Fixed official endpoints, bounded verified TLS, no redirects/proxies/retries.

OAuth tokens are never URL parameters. Error bodies, headers and exception text
are not exposed; inference text is handled separately as untrusted scientific data.
"""
from http.client import HTTPException
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from corpustrail._internal.values import canonical, digest_bytes

AUTH = 'https://auth.openai.com'
API = 'https://api.openai.com/v1'
TOKEN = AUTH + '/api/accounts/oauth/token'
JWKS = AUTH + '/.well-known/jwks.json'
DISCOVERY = AUTH + '/.well-known/openid-configuration'
ENDPOINTS = {TOKEN, JWKS, DISCOVERY, API + '/models', API + '/responses', AUTH + '/api/accounts/oauth/revoke', AUTH + '/oauth/revoke'}
CODES = {'subscription_sharing_user_not_eligible': 'ineligible',
         'subscription_sharing_usage_limit_exceeded': 'usage_limit',
         'subscription_sharing_usage_unavailable': 'usage_unavailable',
         'subscription_sharing_user_unavailable': 'usage_unavailable',
         'subscription_sharing_unsupported_capability': 'unsupported',
         'subscription_sharing_route_not_supported': 'unsupported',
         'subscription_sharing_invalid_user': 'authentication',
         'chatpass_v2_scope_not_authorized': 'authentication',
         'chatpass_v2_invalid_authorization_context': 'authentication',
         'invalid_grant': 'reauthenticate', 'invalid_refresh_token': 'reauthenticate',
         'token_expired': 'reauthenticate', 'refresh_token_expired': 'reauthenticate',
         'refresh_token_invalidated': 'reauthenticate', 'refresh_token_reused': 'reauthenticate',
         'invalid_client': 'registration'}


class ConnectionFailure(Exception):
    def __init__(self, kind, *, status=None, diagnostics=None):
        super().__init__(kind)
        self.kind = kind; self.status = status; self.diagnostics = diagnostics or {}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def object_json(raw):
    def unique(pairs):
        value = {}
        for k, v in pairs:
            if k in value: raise ValueError('duplicate JSON field')
            value[k] = v
        return value
    result = json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if not isinstance(result, dict): raise ValueError('JSON object required')
    return result


def error_kind(body, status):
    try:
        value = object_json(body)
        error = value.get('error', {})
        code = error.get('code') or error.get('type') if isinstance(error, dict) else None
    except (ValueError, UnicodeError, RecursionError): code = None
    return CODES.get(code, 'authentication' if status == 401 else 'usage_limit' if status == 429 else
                     'policy' if status == 403 else 'provider_unavailable' if status and status >= 500 else 'provider_error')


class Transport:
    def __init__(self, *, timeout=20, open_request=None):
        self.timeout = timeout
        self._open = open_request or build_opener(ProxyHandler({}), NoRedirect()).open

    def _request(self, url, *, body=None, bearer=None, form=False):
        if url not in ENDPOINTS: raise ConnectionFailure('unsupported_endpoint')
        if bearer is not None and (not isinstance(bearer, str) or not bearer or len(bearer) > 32768 or
                                   any(ord(c) < 33 or ord(c) > 126 for c in bearer)):
            raise ConnectionFailure('authentication')
        headers = {'Accept': 'application/json'}
        if body is not None: headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        if bearer: headers['Authorization'] = 'Bearer ' + bearer
        try:
            return self._open(Request(url, data=body, headers=headers, method='POST' if body is not None else 'GET'), timeout=self.timeout)
        except HTTPError as exc:
            try: raw = exc.read(65537)
            finally: exc.close()
            raise ConnectionFailure('redirect_refused' if 300 <= exc.code < 400 else error_kind(raw[:65536], exc.code), status=exc.code) from None
        except (TimeoutError, socket.timeout): raise ConnectionFailure('timeout') from None
        except (OSError, URLError, HTTPException, ValueError): raise ConnectionFailure('transport') from None

    def json(self, url, *, body=None, bearer=None, form=False):
        try:
            with self._request(url, body=body, bearer=bearer, form=form) as response:
                raw = response.read(262145)
                if len(raw) > 262144: raise ConnectionFailure('resource_limit')
                return object_json(raw)
        except (ValueError, UnicodeError, RecursionError): raise ConnectionFailure('malformed_response') from None
        except (OSError, HTTPException): raise ConnectionFailure('transport') from None

    def response(self, payload, *, bearer, cancelled=lambda: False):
        body = canonical(payload).encode()
        if len(body) > 32000: raise ConnectionFailure('resource_limit')
        if cancelled(): raise ConnectionFailure('cancelled')
        wire = bytearray(); event = bytearray(); pending = bytearray(); partial = []; complete = None; deadline = time.monotonic() + 60
        try:
            with self._request(API + '/responses', body=body, bearer=bearer) as stream:
                while True:
                    if cancelled(): raise ConnectionFailure('cancelled')
                    if time.monotonic() > deadline: raise ConnectionFailure('timeout')
                    if b'\n' not in pending:
                        chunk = stream.read1(4096)
                        if not chunk: break
                        wire.extend(chunk); pending.extend(chunk)
                        if len(wire) > 262144: raise ConnectionFailure('resource_limit')
                    if b'\n' not in pending:
                        if len(pending) > 65536: raise ConnectionFailure('resource_limit')
                        continue
                    line, _, rest = pending.partition(b'\n'); pending = bytearray(rest)
                    if len(line) > 65536: raise ConnectionFailure('resource_limit')
                    if line.strip():
                        if line.startswith(b'data:'): event.extend(line[5:].lstrip().rstrip(b'\r\n') + b'\n')
                        continue
                    if not event: continue
                    if event.strip() == b'[DONE]': event.clear(); break
                    value = object_json(bytes(event)); event.clear()
                    kind = value.get('type')
                    if kind == 'response.output_text.delta' and isinstance(value.get('delta'), str): partial.append(value['delta'])
                    if kind == 'response.completed':
                        complete = value.get('response')
                        break
                    if kind in {'error', 'response.failed', 'response.incomplete'}:
                        response = value.get('response', value)
                        code = response.get('error') or value.get('error') or {}
                        err = {'error': code} if isinstance(code, dict) else {}
                        raise ConnectionFailure(error_kind(canonical(err), None) if kind != 'response.incomplete' else 'incomplete')
            if complete is None: raise ConnectionFailure('interrupted')
            if not isinstance(complete, dict) or complete.get('status') != 'completed':
                raise ConnectionFailure('incomplete')
            return complete, {'wire_request_sha256': digest_bytes(body), 'stream_sha256': digest_bytes(bytes(wire)),
                              'stream_bytes': len(wire), 'terminal_event': 'response.completed'}
        except ConnectionFailure as exc:
            text = ''.join(partial).encode('utf-8')
            exc.diagnostics = {'wire_request_sha256': digest_bytes(body), 'stream_sha256': digest_bytes(bytes(wire)),
                               'stream_bytes': len(wire), 'terminal_event': None,
                               'partial_output_text': text[:12000].decode('utf-8', errors='replace'),
                               'partial_output_sha256': digest_bytes(text), 'partial_output_bytes': len(text),
                               'partial_output_retention': 'complete' if len(text) <= 12000 else 'bounded_prefix'}
            raise
        except (ValueError, UnicodeError, RecursionError): raise ConnectionFailure('malformed_response') from None
        except (OSError, HTTPException): raise ConnectionFailure('transport') from None
