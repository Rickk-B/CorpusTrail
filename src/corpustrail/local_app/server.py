"""Thin loopback HTTP transport. Guided writes require explicit protected POSTs.

The original make_server(project) remains a read-only compatibility surface.
The existing human-review server remains separate and unchanged.
"""

from http.server import BaseHTTPRequestHandler
from corpustrail._internal.loopback_http import LoopbackHTTPServer as ThreadingHTTPServer
from contextlib import ExitStack
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
from corpustrail.application.project_use import leased_server_factory

ASSETS = {'app.js': 'text/javascript; charset=utf-8', 'app.css': 'text/css; charset=utf-8',
          'projects.js': 'text/javascript; charset=utf-8'}


def _query(value, allowed):
    query = parse_qs(value, keep_blank_values=True, strict_parsing=True, max_num_fields=12)
    if set(query) - allowed or any(len(values) != 1 for values in query.values()):
        raise ContractError('unsupported or repeated query parameter')
    return {key: values[0] for key, values in query.items()}


def _number(value):
    if not re.fullmatch(r'[0-9]{1,12}', value):
        raise ContractError('invalid numeric query parameter')
    return int(value)


@leased_server_factory
def make_server(project=None, *, port=8766, controller=None):
    """Reads never write; only controller-enabled project POSTs can configure."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ContractError('port must be between 0 and 65535')
    reads = ProjectReads(project) if project is not None else None
    if reads is None and controller is None:
        raise ContractError('a project or guided project controller is required')
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
            leases = ExitStack()
            try:
                if len(self.path) > 4096:
                    raise ContractError('request target is too long')
                route = urlsplit(self.path)
                if route.scheme or route.netloc or route.fragment:
                    raise ContractError('invalid local request target')
                path = route.path
                if path in {'/', '/home', '/dashboard', '/papers', '/projects', '/projects/new', '/settings'} or re.fullmatch(r'/papers/[0-9a-f]{64}', path):
                    if route.query:
                        raise ContractError('page route does not accept query parameters')
                    active = controller.active_handle is not None if controller is not None else project is not None
                    home = path == '/home' or path == '/' and not active
                    setup = controller is not None and path in {'/projects', '/projects/new', '/settings'}
                    page = 'home.html' if home else 'projects.html' if setup else 'index.html'
                    html = assets.joinpath(page).read_text(encoding='utf-8')
                    html = html.replace('SESSION_TOKEN', token).replace('PROJECT_NAV_HIDDEN', '' if active else 'hidden')
                    return self.send(200, html, 'text/html; charset=utf-8')
                if path.startswith('/assets/'):
                    name = path[len('/assets/'):]
                    if name not in ASSETS or route.query:
                        return self.error(404, 'not_found', 'Resource not found.')
                    return self.send(200, assets.joinpath(name).read_bytes(), ASSETS[name])
                if not path.startswith('/api/v1/'):
                    return self.error(404, 'not_found', 'Page not found.')
                if self.headers.get_all('X-CorpusTrail-Session') != [token]:
                    return self.error(403, 'session_required', 'Open the local application before reading its API.')
                if path.startswith('/api/v1/projects/trash/') or path == '/api/v1/projects/close':
                    return self.error(404, 'not_found', 'This operation requires explicit protected submission.')
                if controller is not None and path == '/api/v1/projects':
                    query = _query(route.query, {'offset', 'limit'})
                    result = controller.entry(**{key: _number(value) for key, value in query.items()})
                    return self.send(200, json.dumps(result, ensure_ascii=False, allow_nan=False))
                if controller is not None and path == '/api/v1/project-settings':
                    query = _query(route.query, {'handle'})
                    result = controller.settings(query.get('handle'))
                    return self.send(200, json.dumps(result, ensure_ascii=False, allow_nan=False))
                current_reads = ProjectReads(leases.enter_context(controller.use())) if controller is not None else reads
                if path == '/api/v1/dashboard':
                    _query(route.query, set())
                    result = current_reads.dashboard()
                elif path == '/api/v1/papers':
                    query = _query(route.query, {'limit', 'cursor', 'q', 'sort', 'membership', 'evidence', 'review'})
                    if 'limit' in query:
                        query['limit'] = _number(query['limit'])
                    result = current_reads.papers(**query)
                else:
                    match = re.fullmatch(r'/api/v1/papers/([0-9a-f]{64})(?:/(provenance|evidence)(?:/([0-9a-f]{64}))?)?', path)
                    if match is None:
                        return self.error(404, 'not_found', 'API resource not found.')
                    handle, section, representation = match.groups()
                    if section == 'provenance' and representation is None:
                        query = _query(route.query, {'section', 'limit', 'cursor'})
                        if 'limit' in query:
                            query['limit'] = _number(query['limit'])
                        result = current_reads.provenance(handle, **query)
                    elif section == 'evidence' and representation:
                        query = _query(route.query, {'offset', 'limit'})
                        result = current_reads.document(handle, representation, **{key: _number(value) for key, value in query.items()})
                    elif section is None:
                        _query(route.query, set())
                        result = current_reads.paper(handle)
                    else:
                        return self.error(404, 'not_found', 'API resource not found.')
                return self.send(200, json.dumps(result, ensure_ascii=False, allow_nan=False))
            except StaleCursor as exc:
                self.error(409, 'stale_view', str(exc))
            except KeyError:
                self.error(404, 'not_found', 'Paper or representation not found.')
            except (ContractError, ValueError, TypeError) as exc:
                from corpustrail.application.projects import ProjectCommandError
                if isinstance(exc, ProjectCommandError):
                    return self.error(exc.status, exc.code, str(exc))
                self.error(400, 'invalid_request', 'Invalid request or unavailable trusted evidence. Refresh or check the selected filters.')
            except OSError:
                self.error(400, 'artifact_unavailable', 'Local evidence is missing or inaccessible; no evidence was modified.')
            except sqlite3.DatabaseError:
                self.error(500, 'read_unavailable', 'Project data could not be read. No project state was modified.')
            finally:
                leases.close()

        def readonly(self):
            if not self.allowed():
                return self.error(403, 'origin_required', 'A same-origin loopback request is required.')
            self.close_connection = True
            self.send_response(405)
            self.send_header('Allow', 'GET')
            self.send_header('Content-Length', '0')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

        def do_POST(self):
            routes = {'/api/v1/projects/create', '/api/v1/projects/open', '/api/v1/project-settings/save',
                      '/api/v1/projects/close', '/api/v1/projects/trash/prepare',
                      '/api/v1/projects/trash/cancel', '/api/v1/projects/trash/execute'}
            if controller is None or self.path not in routes:
                return self.readonly()
            self.close_connection = True
            expected_origin = 'http://127.0.0.1:' + str(self.server.server_port)
            if (not self.allowed() or self.headers.get_all('Origin') != [expected_origin]
                    or self.headers.get_all('X-CorpusTrail-Session') != [token]
                    or self.headers.get_all('X-CorpusTrail-CSRF') != [token]):
                return self.error(403, 'csrf_required', 'Open the local application and submit from its project form.')
            from corpustrail.application.projects import ProjectCommandError, SCHEMA
            try:
                lengths = self.headers.get_all('Content-Length')
                if (self.headers.get_all('Content-Type') != ['application/json']
                        or self.headers.get('Transfer-Encoding') is not None or not lengths or len(lengths) != 1
                        or not re.fullmatch(r'[0-9]{1,6}', lengths[0]) or not 1 <= int(lengths[0]) <= 65536):
                    return self.error(413, 'bounded_json_required', 'Submit a JSON project form smaller than 64 KiB.')
                payload = self.rfile.read(int(lengths[0]))
                if len(payload) != int(lengths[0]):
                    raise ValueError('incomplete body')
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError('duplicate field')
                        result[key] = value
                    return result
                body = json.loads(payload, object_pairs_hook=unique,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
                from corpustrail.application.trash import SCHEMA as TRASH_SCHEMA
                expected_schema = TRASH_SCHEMA if '/trash/' in self.path else SCHEMA
                if not isinstance(body, dict) or body.pop('schema', None) != expected_schema:
                    raise ValueError('invalid form version')
                if '/trash/' in self.path:
                    operation = self.path.rsplit('/', 1)[1]
                    fields = {'prepare': {'handle'}, 'cancel': {'confirmation'}, 'execute': {'confirmation', 'folder'}}[operation]
                    if set(body) != fields:
                        raise ValueError('unsupported removal fields')
                    result = controller.remove_command(operation, **body)
                elif self.path.endswith('/close'):
                    if body:
                        raise ValueError('unsupported close fields')
                    controller.close()
                    result = {'schema': SCHEMA, 'status': 'closed'}
                elif self.path.endswith('/open'):
                    if set(body) != {'handle'}:
                        raise ValueError('unsupported open fields')
                    result = controller.open(body['handle'])
                else:
                    fields = ({'request_id', 'folder', 'fields', 'confirm_authority'} if self.path.endswith('/create') else
                              {'request_id', 'project_handle', 'revision', 'fields', 'confirm_authority', 'confirm_session_change'})
                    if set(body) != fields:
                        raise ValueError('unsupported command fields')
                    for key in ('confirm_authority', 'confirm_session_change'):
                        if key in body and type(body[key]) is not bool:
                            raise ValueError('confirmation must be boolean')
                    result = (controller.create if self.path.endswith('/create') else controller.configure)(**body)
                self.send(200, json.dumps(result, ensure_ascii=False, allow_nan=False))
            except ProjectCommandError as exc:
                self.error(exc.status, exc.code, str(exc))
            except (ContractError, ValueError, TypeError, KeyError, RecursionError):
                self.error(400, 'invalid_project_form', 'Check the project form and refresh if its version is unsupported. No secret values are accepted.')
            except (OSError, sqlite3.DatabaseError):
                self.error(409, 'project_unavailable', 'Project operation failed. Check local permissions and inspect saved state before retrying; no automatic upgrade or cleanup was performed.')

        do_PUT = readonly
        do_PATCH = readonly
        do_DELETE = readonly
        do_OPTIONS = readonly
        do_HEAD = readonly
        do_TRACE = readonly
        do_CONNECT = readonly

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(project=None, *, port=8766, open_browser=False, projects_root=None):
    from corpustrail.application.projects import ProjectController
    controller = ProjectController(projects_root=projects_root, project=project)
    try:
        server = make_server(port=port, controller=controller)
    except BaseException:
        controller.close()
        raise
    url = 'http://127.0.0.1:' + str(server.server_port)
    print('CorpusTrail local application: ' + url, flush=True)
    try:
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
