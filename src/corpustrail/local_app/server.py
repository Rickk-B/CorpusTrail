"""Thin loopback HTTP transport for one explicitly opened project's read API.

No mutation routes. Session capability protects APIs from unrelated local origins;
the existing human-review server remains separate and unchanged.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
import re
import secrets
import sqlite3
from urllib.parse import parse_qs, urlsplit
import webbrowser

from corpustrail.application import ProjectReads
from corpustrail.application.reads import StaleCursor
from corpustrail.errors import ContractError

ASSETS = {'app.js': 'text/javascript; charset=utf-8', 'app.css': 'text/css; charset=utf-8'}


def _query(value, allowed):
    query = parse_qs(value, keep_blank_values=True, strict_parsing=True, max_num_fields=12)
    if set(query) - allowed or any(len(values) != 1 for values in query.values()):
        raise ContractError('unsupported or repeated query parameter')
    return {key: values[0] for key, values in query.items()}


def _number(value):
    if not re.fullmatch(r'[0-9]{1,12}', value):
        raise ContractError('invalid numeric query parameter')
    return int(value)


def make_server(project, *, port=8766):
    """No project/session creation, migrations, writes, plugins or network calls."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ContractError('port must be between 0 and 65535')
    reads = ProjectReads(project)
    token = secrets.token_urlsafe(32)
    assets = resources.files('corpustrail.local_app').joinpath('assets')

    class Handler(BaseHTTPRequestHandler):
        timeout = 20

        def log_message(self, *_):
            pass

        def allowed(self):
            expected = '127.0.0.1:' + str(self.server.server_port)
            origin = self.headers.get('Origin')
            return (self.headers.get_all('Host') == [expected]
                and (origin is None or self.headers.get_all('Origin') == ['http://' + expected])
                and self.headers.get('Sec-Fetch-Site', 'same-origin') in {'none', 'same-origin'})

        def send(self, status, body, content_type='application/json; charset=utf-8'):
            data = body if isinstance(body, bytes) else body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'none'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def error(self, status, code, message):
            self.send(status, json.dumps({'error': {'code': code, 'message': message}}))

        def do_GET(self):
            if not self.allowed():
                return self.error(403, 'origin_required', 'A same-origin loopback request is required.')
            try:
                if len(self.path) > 4096:
                    raise ContractError('request target is too long')
                route = urlsplit(self.path)
                if route.scheme or route.netloc or route.fragment:
                    raise ContractError('invalid local request target')
                path = route.path
                if path in {'/', '/dashboard', '/papers'} or re.fullmatch(r'/papers/[0-9a-f]{64}', path):
                    if route.query:
                        raise ContractError('page route does not accept query parameters')
                    html = assets.joinpath('index.html').read_text(encoding='utf-8')
                    return self.send(200, html.replace('SESSION_TOKEN', token), 'text/html; charset=utf-8')
                if path.startswith('/assets/'):
                    name = path[len('/assets/'):]
                    if name not in ASSETS or route.query:
                        return self.error(404, 'not_found', 'Resource not found.')
                    return self.send(200, assets.joinpath(name).read_bytes(), ASSETS[name])
                if not path.startswith('/api/v1/'):
                    return self.error(404, 'not_found', 'Page not found.')
                if self.headers.get_all('X-CorpusTrail-Session') != [token]:
                    return self.error(403, 'session_required', 'Open the local application before reading its API.')
                if path == '/api/v1/dashboard':
                    _query(route.query, set())
                    result = reads.dashboard()
                elif path == '/api/v1/papers':
                    query = _query(route.query, {'limit', 'cursor', 'q', 'sort', 'membership', 'evidence', 'review'})
                    if 'limit' in query:
                        query['limit'] = _number(query['limit'])
                    result = reads.papers(**query)
                else:
                    match = re.fullmatch(r'/api/v1/papers/([0-9a-f]{64})(?:/(provenance|evidence)(?:/([0-9a-f]{64}))?)?', path)
                    if match is None:
                        return self.error(404, 'not_found', 'API resource not found.')
                    handle, section, representation = match.groups()
                    if section == 'provenance' and representation is None:
                        query = _query(route.query, {'section', 'limit', 'cursor'})
                        if 'limit' in query:
                            query['limit'] = _number(query['limit'])
                        result = reads.provenance(handle, **query)
                    elif section == 'evidence' and representation:
                        query = _query(route.query, {'offset', 'limit'})
                        result = reads.document(handle, representation, **{key: _number(value) for key, value in query.items()})
                    elif section is None:
                        _query(route.query, set())
                        result = reads.paper(handle)
                    else:
                        return self.error(404, 'not_found', 'API resource not found.')
                return self.send(200, json.dumps(result, ensure_ascii=False, allow_nan=False))
            except StaleCursor as exc:
                self.error(409, 'stale_view', str(exc))
            except KeyError:
                self.error(404, 'not_found', 'Paper or representation not found.')
            except (ContractError, ValueError, TypeError):
                self.error(400, 'invalid_request', 'Invalid request or unavailable trusted evidence. Refresh or check the selected filters.')
            except OSError:
                self.error(400, 'artifact_unavailable', 'Local evidence is missing or inaccessible; no evidence was modified.')
            except sqlite3.DatabaseError:
                self.error(500, 'read_unavailable', 'Project data could not be read. No project state was modified.')

        def readonly(self):
            if not self.allowed():
                return self.error(403, 'origin_required', 'A same-origin loopback request is required.')
            self.close_connection = True
            self.send_response(405)
            self.send_header('Allow', 'GET')
            self.send_header('Content-Length', '0')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

        do_POST = readonly
        do_PUT = readonly
        do_PATCH = readonly
        do_DELETE = readonly
        do_OPTIONS = readonly
        do_HEAD = readonly
        do_TRACE = readonly
        do_CONNECT = readonly

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(project, *, port=8766, open_browser=False):
    server = make_server(project, port=port)
    url = 'http://127.0.0.1:' + str(server.server_port)
    print('CorpusTrail read-only application: ' + url, flush=True)
    try:
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
