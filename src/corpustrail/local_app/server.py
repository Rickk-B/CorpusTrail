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
          'projects.js': 'text/javascript; charset=utf-8', 'discovery.js': 'text/javascript; charset=utf-8',
          'evidence.js': 'text/javascript; charset=utf-8', 'review.js':'text/javascript; charset=utf-8',
          'populations.js': 'text/javascript; charset=utf-8','references.js':'text/javascript; charset=utf-8'}


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
def make_server(project=None, *, port=8766, controller=None, discovery=None, evidence=None):
    """Reads never write; only controller-enabled project POSTs can configure."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ContractError('port must be between 0 and 65535')
    reads = ProjectReads(project) if project is not None else None
    if reads is None and controller is None:
        raise ContractError('a project or guided project controller is required')
    token = secrets.token_urlsafe(32)
    assets = resources.files('corpustrail.local_app').joinpath('assets')
    if controller is not None and discovery is None:
        from corpustrail.application.discovery import DiscoveryController
        discovery = DiscoveryController(controller)
    if controller is not None and evidence is None:
        from corpustrail.application.evidence import EvidenceController
        evidence = EvidenceController(controller)
    from corpustrail.application.review import ReviewController
    review = ReviewController() if controller is not None else None
    from corpustrail.application.populations import PopulationController
    populations = PopulationController() if controller is not None else None
    from corpustrail.application.references import ReferenceController
    references = ReferenceController() if controller is not None else None

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
                if path in {'/', '/home', '/dashboard', '/papers', '/projects', '/projects/new', '/settings', '/discovery','/review','/populations','/references'} or re.fullmatch(r'/papers/[0-9a-f]{64}', path):
                    if route.query:
                        raise ContractError('page route does not accept query parameters')
                    active = controller.active_handle is not None if controller is not None else project is not None
                    home = path == '/home' or path == '/' and not active
                    setup = controller is not None and path in {'/projects', '/projects/new', '/settings'}
                    if path == '/discovery' and (not active or discovery is None):
                        return self.error(409, 'project_required', 'Open a project before using Discovery.')
                    if path == '/review' and (not active or review is None):
                        return self.error(409,'project_required','Open a project before using Guided Review.')
                    if path == '/populations' and (not active or populations is None):
                        return self.error(409,'project_required','Open a project before using candidate populations.')
                    if path == '/references' and (not active or references is None):
                        return self.error(409,'project_required','Open a project before using reference collections.')
                    page = 'home.html' if home else 'projects.html' if setup else 'references.html' if path=='/references' else 'populations.html' if path=='/populations' else 'review.html' if path=='/review' else 'discovery.html' if path == '/discovery' else 'index.html'
                    html = assets.joinpath(page).read_text(encoding='utf-8')
                    html = html.replace('SESSION_TOKEN', token).replace('PROJECT_NAV_HIDDEN', '' if active else 'hidden')
                    html = html.replace('DISCOVERY_NAV_HIDDEN', '' if active and discovery is not None else 'hidden')
                    html = html.replace('REVIEW_NAV_HIDDEN', '' if active and review is not None else 'hidden')
                    html = html.replace('POPULATIONS_NAV_HIDDEN', '' if active and populations is not None else 'hidden')
                    html = html.replace('REFERENCES_NAV_HIDDEN', '' if active and references is not None else 'hidden')
                    html = html.replace('EVIDENCE_WORKFLOW_HIDDEN', '' if active and evidence is not None else 'hidden')
                    html = html.replace('PROJECT_BROWSER_STATUS', 'Local project workspace' if evidence is not None else 'Read-only project browser')
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
                if references is not None and path.startswith('/api/v1/references/'):
                    from corpustrail.application.references import handle
                    with controller.use() as current:
                        query=_query(route.query,{'offset','limit','cutoff','label'})
                        paging={k:_number(v) for k,v in query.items() if k!='label'}
                        if path=='/api/v1/references/configuration':
                            if query:raise ContractError('reference configuration has no query fields')
                            result=references.configuration(current)
                        elif path=='/api/v1/references/versions':
                            if 'label' in query:raise ContractError('unsupported reference list filter')
                            result=current.references.versions(**paging)
                        elif path=='/api/v1/references/contexts':
                            if 'label' in query:raise ContractError('unsupported context list filter')
                            result=references.contexts(current,**paging)
                        elif re.fullmatch(r'/api/v1/references/versions/[0-9a-f]{64}/assignments/[0-9a-f]{64}',path):
                            if query:raise ContractError('single reference provenance has no query fields')
                            parts=path.split('/')
                            result=current.references.assignment(handle(parts[5],'reference-version'),handle(parts[7],'reference-assignment'))
                        else:
                            match=re.fullmatch(r'/api/v1/references/(papers|versions|contexts)/([0-9a-f]{64})(?:/(members|provenance|verify))?',path)
                            if not match:return self.error(404,'not_found','Reference resource not found.')
                            kind,item,section=match.groups()
                            if 'cutoff' in query:raise ContractError('version detail does not accept a live-list cutoff')
                            if kind=='papers' and section is None:
                                if query:raise ContractError('paper reference context has no query fields')
                                result=references.paper(current,item)
                            elif kind=='versions':
                                vid=handle(item,'reference-version')
                                if section=='members':result=current.references.members(vid,**paging,label=query.get('label'))
                                elif section=='provenance' and 'label' not in query:result=current.references.provenance(vid,**paging)
                                elif section is None and not query:result=current.references.inspect(vid)
                                else:return self.error(404,'not_found','Reference version resource not found.')
                            elif kind=='contexts' and section in {None,'verify'} and 'label' not in query:
                                result=references.context(current,handle(item,'reference-context'),**paging,verify=section=='verify')
                            else:return self.error(404,'not_found','Reference resource not found.')
                        return self.send(200,json.dumps(result,ensure_ascii=False,allow_nan=False))
                if populations is not None and path.startswith('/api/v1/populations/'):
                    from corpustrail.application.populations import version_handle
                    with controller.use() as current:
                        if path == '/api/v1/populations/configuration':
                            query = _query(route.query, {'offset','limit','cutoff'})
                            result = populations.configuration(current, **{k:_number(v) for k,v in query.items()})
                        elif path == '/api/v1/populations/versions':
                            query = _query(route.query, {'offset','limit','cutoff'})
                            result = current.populations.versions(**{k:_number(v) for k,v in query.items()})
                        else:
                            match = re.fullmatch(r'/api/v1/populations/versions/([0-9a-f]{64})(?:/(members|lineage|issues))?', path)
                            if not match: return self.error(404,'not_found','Population version not found.')
                            handle, section = match.groups()
                            query = _query(route.query, {'offset','limit'} if section else set())
                            vid = version_handle(handle)
                            result = getattr(current.populations, section)(vid, **{k:_number(v) for k,v in query.items()}) if section else current.populations.inspect(vid)
                        return self.send(200,json.dumps(result,ensure_ascii=False,allow_nan=False))
                if review is not None and path.startswith('/api/v1/review/'):
                    with controller.use() as current:
                        query=_query(route.query,{'offset','limit'})
                        page={k:_number(v) for k,v in query.items()}
                        if path=='/api/v1/review/configuration': result=review.configuration(current,**page)
                        else:
                            match=re.fullmatch(r'/api/v1/review/sessions/([0-9a-f]{64})(?:/(summary|document))?',path)
                            if not match: return self.error(404,'not_found','Review session not found.')
                            handle,section=match.groups()
                            if section=='summary': result=review.summary_page(current,handle,**page)
                            elif section=='document': result=review.document(current,handle,**page)
                            else:
                                if page: raise ContractError('session view does not accept paging parameters')
                                result=review.view(current,handle)
                        return self.send(200,json.dumps(result,ensure_ascii=False,allow_nan=False))
                if evidence is not None and path.startswith('/api/v1/evidence/'):
                    with controller.use() as current:
                        match = re.fullmatch(r'/api/v1/evidence/(papers|operations)/([0-9a-f]{64})(?:/(history|provenance))?',path)
                        if not match: return self.error(404,'not_found','Evidence resource not found.')
                        kind,handle,section = match.groups()
                        query = _query(route.query, {'offset','limit'} if section or kind=='papers' else set())
                        page = {k:_number(v) for k,v in query.items()}
                        if kind=='operations':
                            if section: return self.error(404,'not_found','Evidence operation resource not found.')
                            result = evidence.inspect(current,handle)
                        elif section=='history': result = evidence.history(current,handle,**page)
                        else: result = evidence.view(current,handle,advanced=section=='provenance',**page)
                        return self.send(200,json.dumps(result,ensure_ascii=False,allow_nan=False))
                if discovery is not None and path.startswith('/api/v1/discovery/'):
                    with controller.use() as current:
                        if path == '/api/v1/discovery/configuration':
                            _query(route.query, set()); result = discovery.configuration(current)
                        elif path == '/api/v1/discovery/history':
                            query = _query(route.query, {'offset', 'limit'})
                            result = discovery.history(current, **{k: _number(v) for k,v in query.items()})
                        else:
                            match = re.fullmatch(r'/api/v1/discovery/plans/([0-9a-f]{64})(?:/(papers|provenance))?', path)
                            if not match: return self.error(404, 'not_found', 'Discovery resource not found.')
                            handle, section = match.groups()
                            if section is None:
                                _query(route.query, set()); result = discovery.inspect(current, handle)
                            else:
                                query = _query(route.query, {'offset', 'limit', 'provider'} if section=='provenance' else {'offset', 'limit'})
                                for key in ('offset', 'limit'):
                                    if key in query: query[key] = _number(query[key])
                                result = getattr(discovery, section)(current, handle, **query)
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
                self.error(400, 'invalid_request', 'Saved search request is invalid or unavailable. Refresh Discovery and inspect its history.' if self.path.startswith('/api/v1/discovery/') else
                    'Invalid request or unavailable trusted evidence. Refresh or check the selected filters.')
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
            routes.update('/api/v1/discovery/'+name for name in ('prepare', 'approve', 'start', 'invalidate', 'cancel'))
            routes.add('/api/v1/evidence/start')
            routes.update('/api/v1/review/'+name for name in ('create','command'))
            routes.update('/api/v1/populations/'+name for name in ('preview','create','upgrade','verify'))
            routes.update('/api/v1/references/'+name for name in ('preview','commit','upgrade','verify','context_preview','context_commit'))
            if controller is None or self.path not in routes:
                return self.readonly()
            self.close_connection = True
            expected_origin = 'http://127.0.0.1:' + str(self.server.server_port)
            if (not self.allowed() or self.headers.get_all('Origin') != [expected_origin]
                    or self.headers.get_all('X-CorpusTrail-Session') != [token]
                    or self.headers.get_all('X-CorpusTrail-CSRF') != [token]):
                return self.error(403, 'csrf_required', 'Open the local application and submit from its project form.')
            from corpustrail.application.projects import ProjectCommandError, SCHEMA
            is_discovery = self.path.startswith('/api/v1/discovery/')
            is_evidence = self.path=='/api/v1/evidence/start'
            is_review = self.path.startswith('/api/v1/review/')
            is_population = self.path.startswith('/api/v1/populations/')
            is_reference = self.path.startswith('/api/v1/references/')
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
                from corpustrail.application.discovery import SCHEMA as DISCOVERY_SCHEMA
                from corpustrail.application.evidence import SCHEMA as EVIDENCE_SCHEMA
                from corpustrail.curation.guided import SCHEMA as REVIEW_SCHEMA
                from corpustrail.application.populations import SCHEMA as POPULATION_SCHEMA
                from corpustrail.application.references import SCHEMA as REFERENCE_SCHEMA
                expected_schema = REFERENCE_SCHEMA if is_reference else POPULATION_SCHEMA if is_population else REVIEW_SCHEMA if is_review else EVIDENCE_SCHEMA if is_evidence else DISCOVERY_SCHEMA if is_discovery else TRASH_SCHEMA if '/trash/' in self.path else SCHEMA
                if not isinstance(body, dict) or body.pop('schema', None) != expected_schema:
                    raise ValueError('invalid form version')
                if is_reference:
                    with controller.use() as current: result=references.command(current,self.path.rsplit('/',1)[1],body)
                elif is_population:
                    with controller.use() as current: result=populations.command(current,self.path.rsplit('/',1)[1],body)
                elif is_review:
                    with controller.use() as current: result=review.command(current,self.path.rsplit('/',1)[1],body)
                elif is_evidence:
                    if set(body)!={'paper','request_id','eligibility_hash','confirm_external'}: raise ValueError('unsupported evidence fields')
                    with controller.use() as current: result = evidence.start(current,**body)
                elif is_discovery:
                    with controller.use() as current:
                        result = discovery.command(current, self.path.rsplit('/', 1)[1], body)
                elif '/trash/' in self.path:
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
                self.error(400, 'invalid_search' if is_discovery else 'invalid_project_form',
                    'Check the query, bounded settings and current plan. No secret values or arbitrary endpoints are accepted.' if is_discovery else
                    'Check the project form and refresh if its version is unsupported. No secret values are accepted.')
            except (OSError, sqlite3.DatabaseError):
                self.error(409, 'project_unavailable', 'Project operation failed. Check local permissions and inspect saved state before retrying; no automatic upgrade or cleanup was performed.')

        do_PUT = readonly
        do_PATCH = readonly
        do_DELETE = readonly
        do_OPTIONS = readonly
        do_HEAD = readonly
        do_TRACE = readonly
        do_CONNECT = readonly

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    if discovery is not None:
        original_close = server.server_close
        def close():
            discovery.close()
            if evidence is not None: evidence.close()
            original_close()
        server.server_close = close
    return server


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
