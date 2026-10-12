"""Explicit, bounded local evidence operations over the existing trust services.

No enrichment, identity or document verification algorithm lives here.
"""
from contextlib import contextmanager
from dataclasses import asdict
from importlib import resources
import threading
import time

from corpustrail._internal.values import ContractError, content_hash, digest_bytes, now, canonical
from corpustrail.evidence import EuropePmcResolver, ResolutionRequest
from corpustrail.identity import Identifier
from corpustrail.models.contracts import safe_data
from corpustrail.providers.network import UrlLibTransport
from . import _workflow_files as files
from .discovery import _SafeTransport, _command, _handle
from .project_use import acquire_project_use, directory_identity, ProjectUseError, ProjectBusy
from .projects import ProjectCommandError, ProjectController
from .reads import _paper_id

SCHEMA = 'corpustrail-evidence-workflow/v1'


def _adapter_hash():
    return digest_bytes(resources.files('corpustrail.evidence').joinpath('service.py').read_bytes())


class EvidenceController:
    def __init__(self, controller, *, transport_factory=UrlLibTransport, resolver_factory=EuropePmcResolver):
        self.controller, self.transport_factory, self.resolver_factory = controller, transport_factory, resolver_factory
        self._mutex, self._workers, self._closed = threading.RLock(), {}, False

    @contextmanager
    def _write(self, project):
        lease = None
        for _ in range(40):
            try: lease = files.operation_lease(project, 'evidence-journal'); break
            except ProjectUseError: time.sleep(.05)
        if lease is None: raise ProjectCommandError('Evidence operation state is busy. Refresh before retrying.', status=409)
        try: yield
        finally: lease.close()

    def _events(self, project, handle):
        return files.history(project, handle, family='evidence')

    def _event(self, project, handle, kind, payload):
        with self._write(project):
            self._plan(project, handle)
            return files.append(project, handle, kind, payload, now(), family='evidence')

    def _plan(self, project, handle):
        value = files.read(files.location(project, family='evidence')/'plans'/(_handle(handle)+'.json'))
        if value['schema'] != SCHEMA or value['handle'] != handle or value['project_id'] != project.config.project_id:
            raise ContractError('evidence operation identity differs')
        request = ResolutionRequest(**{**value['request'], 'resolvers': tuple(value['request']['resolvers']),
                                      'identifiers': tuple(tuple(x) for x in value['request']['identifiers'])})
        if (request.request_id != value['resolution_id'] or request.paper_id != _paper_id(value['paper'])
                or request.project_id != value['project_id']):
            raise ContractError('saved resolution request differs')
        queued = [e for e in self._events(project,handle) if e['kind']=='queued']
        if queued and queued[0]['payload'].get('plan_sha256') != content_hash(value):
            raise ContractError('frozen evidence manifest differs from its reservation')
        return value, request

    def availability(self, project, paper):
        pid = _paper_id(paper)
        request = project.evidence.plan(pid)
        body = asdict(request); body.pop('created_at')
        owners = [(s,v,project.identities.exact_owner(Identifier(s,v))) for s,v in request.identifiers]
        pmc = [v for s,v in request.identifiers if s == 'pmcid']
        configured = request.resolvers
        reason = ('No evidence resolver is configured.' if not configured else
                  'Configured resolver combination is not supported; no substitution is performed.' if configured != ('europepmc',) else
                  'A known PMCID is required. Automatic DOI/PMID-to-PMCID enrichment is not implemented.' if not pmc else
                  'Multiple PMCIDs require explicit identity resolution; no identifier is selected automatically.' if len(pmc)!=1 else
                  'The PMCID does not have verified ownership for this publication.' if project.identities.exact_owner(Identifier('pmcid',pmc[0]))!=pid else '')
        spec = self.resolver_factory().request(request) if not reason else None
        result = {'schema': SCHEMA, 'paper': paper, 'configured_resolvers': list(configured),
                  'resolver': 'Europe PMC', 'eligible': not reason, 'reason': reason,
                  'pmcid': pmc[0] if len(pmc)==1 else None,
                  'eligibility_hash': content_hash({'request': body, 'owners': owners, 'adapter': _adapter_hash()}),
                  'config_event_id': request.config_event_id, 'request_url': spec.url if spec else None,
                  'max_attempts': request.max_attempts, 'max_retry_wait_seconds': request.max_retry_wait_seconds,
                  'notice': 'Only the known PMCID is sent to Europe PMC to request available structured XML. '
                            'Source terms apply. Retrieval never changes membership or records a review.',
                  'enrichment': 'Unavailable: no standalone exact-identifier lookup adapter is installed.'}
        safe_data(result, secrets=ProjectController._secrets(project.config))
        return result

    def _validate(self, project, value, request):
        project.evidence._validate(request)
        available = self.availability(project, value['paper'])
        if not available['eligible'] or available['eligibility_hash'] != value['eligibility_hash']:
            raise ProjectCommandError('Identifiers, resolver or project settings changed. Refresh before requesting evidence.', status=409)
        return available

    def start(self, project, *, paper, request_id, eligibility_hash, confirm_external):
        pid = _paper_id(paper); _command(request_id)
        if confirm_external is not True: raise ProjectCommandError('Explicitly authorize the displayed evidence request.', status=409)
        command = {'paper': paper, 'request_id': request_id, 'eligibility_hash': eligibility_hash, 'confirm_external': True}
        safe_data(command, secrets=ProjectController._secrets(project.config))
        handle = content_hash({'project_id': project.config.project_id, 'request_id': request_id}).split(':')[1]
        expected_identity = directory_identity(project.root)
        with self._mutex, self._write(project):
            path = files.location(project, family='evidence')/'plans'/(handle+'.json')
            if path.exists():
                value, request = self._plan(project, handle)
                if value['command_hash'] != content_hash(command):
                    raise ProjectCommandError('This request identity was used for different evidence content.', status=409)
                if any(x['kind']=='queued' for x in self._events(project, handle)): return self.inspect(project, handle)
                self._validate(project, value, request)
            else:
                availability = self.availability(project, paper)
                if not availability['eligible'] or availability['eligibility_hash'] != eligibility_hash:
                    raise ProjectCommandError(availability['reason'] or 'Evidence settings changed. Refresh before requesting retrieval.', status=409)
                request = project.evidence.plan(pid)
                value = {'schema': SCHEMA, 'handle': handle, 'project_id': project.config.project_id,
                    'paper': paper, 'created_at': request.created_at, 'request': asdict(request),
                    'resolution_id': request.request_id, 'eligibility_hash': eligibility_hash,
                    'command_hash': content_hash(command), 'confirm_external': True,
                    'adapter_code_sha256': _adapter_hash(), 'resolver_version': self.resolver_factory().version}
                files.publish(path, value)
            if self._closed: raise ProjectCommandError('This launcher is stopping. No new retrieval was started.', status=409)
            leases = []
            try:
                leases.append(acquire_project_use(project.root))
                if leases[0].identity != expected_identity:
                    raise ContractError('project location changed before retrieval')
                self._validate(project,value,request)
                # Shared with discovery: no competing local scientific worker.
                leases.append(files.operation_lease(project, 'project-worker'))
                leases.append(files.operation_lease(project, 'evidence-worker-'+handle))
                files.append(project, handle, 'queued', {'confirm_external': True, 'plan_sha256':content_hash(value)}, now(), family='evidence')
                thread = threading.Thread(target=self._execute, args=(project, handle, value, request, leases), daemon=True)
                self._workers[(str(project.root),handle)] = thread; thread.start()
            except BaseException as exc:
                for lease in reversed(leases): lease.close()
                self._workers.pop((str(project.root),handle),None)
                if isinstance(exc, Exception):
                    raise ProjectCommandError('Retrieval could not start. Inspect saved evidence history before retrying.', status=409) from exc
                raise
        return self.inspect(project, handle)

    def _execute(self, project, handle, value, request, leases):
        def event(kind, payload):
            if directory_identity(project.root) != leases[0].identity: raise ContractError('project location changed')
            self._event(project,handle,kind,payload)
        try:
            event('running', {})
            self._validate(project,value,request)
            manager = self
            class Transport:
                def __init__(self):
                    self.wrapped = _SafeTransport(manager.transport_factory(), ProjectController._secrets(project.config))
                    self.network = self.wrapped.network
                def request(self,*args,**kwargs):
                    manager._validate(project,value,request)
                    response = self.wrapped.request(*args,**kwargs)
                    if len(response.body)>20_000_000: raise ContractError('bounded evidence response exceeded')
                    manager._validate(project,value,request)
                    return response
            project.evidence.acquire(request, resolvers={'europepmc': self.resolver_factory()},
                                     transport=Transport(), confirm_external=True)
            self._validate(project,value,request)
            event('terminal', {'status':'completed'})
        except Exception as exc:
            try: event('terminal', {'status':'interrupted', 'diagnostic':type(exc).__name__})
            except Exception: pass  # No false success if receipt publication fails.
        finally:
            for lease in reversed(leases): lease.close()
            with self._mutex: self._workers.pop((str(project.root),handle),None)

    def _alive(self, project, handle):
        try:
            lease = files.operation_lease(project,'evidence-worker-'+handle);lease.close();return False
        except ProjectBusy: return True
        except ProjectUseError as exc:
            raise ProjectCommandError('Retrieval activity cannot be verified safely.',status=409) from exc

    def inspect(self, project, handle):
        value, request = self._plan(project,handle)
        history = self._events(project,handle)
        terminal = [e for e in history if e['kind']=='terminal']
        queued = any(e['kind']=='queued' for e in history)
        alive = self._alive(project,handle) if queued and not terminal else False
        if queued and not terminal and not alive:
            history = self._events(project,handle);terminal = [e for e in history if e['kind']=='terminal']
        status = terminal[-1]['payload']['status'] if terminal else (
            ('running' if any(e['kind']=='running' for e in history) else 'queued') if alive else 'interrupted') if queued else 'not_started'
        result = {'schema': SCHEMA, 'handle':handle, 'paper':value['paper'], 'resolution_id':request.request_id,
                  'status':status, 'request':asdict(request), 'created_at':value['created_at'],
                  'activity':self.activity(project, request.paper_id, resolution_id=request.request_id),
                  'notice':'Operation completion is not document verification. Inspect evidence outcomes. No crash-resume or automatic retry.'}
        outcome = next((x['outcome'] for x in result['activity']['items'] if x['kind']=='acquisition_result'
                        and ('http_status' in x or x.get('outcome')=='not_applicable')),None)
        result['network_outcome'] = outcome
        if status=='completed' and outcome!='success': result['status']='unsuccessful'
        safe_data(result, secrets=ProjectController._secrets(project.config))
        return result

    def activity(self, project, pid, *, advanced=False, **page):
        result = project.evidence.acquisition_page(pid,**page)
        if not advanced:
            result = {**result,'items':[{'handle':row['event_id'].split(':')[1], 'kind':row['kind'],
                'source_sha256':row['source_sha256'],**{k:v for k,v in row['payload'].items() if k in {
                    'resolver','version','timestamp','created_at','attempt','outcome','http_status','error','will_retry',
                    'retry_blocked','run_complete','representation','artifact_validity','trusted','evidence_depth',
                    'source_uri','resolver_version','resolution_id','derived_from','parser','parser_version','version_kind'}}}
                for row in result['items']]}
        safe_data(canonical(result),secrets=ProjectController._secrets(project.config))
        return result

    def view(self, project, paper, *, offset=0, limit=20, advanced=False):
        pid = _paper_id(paper)
        metadata = project.discovery.metadata(pid)
        selected = metadata['field_provenance']['abstract']
        source = None
        if selected:
            reps = project.evidence.representations(pid)
            rep = next((r for r in reps if r['event_id']==selected),None)
            if rep: source = {'origin':'Retrieved document abstract','provider':rep['payload']['resolver'],
                              'source_sha256':rep['source_sha256'],'source_uri':rep['payload']['source_uri'],
                              'verification':rep['payload']['artifact_validity']}
            else:
                observation = next((x for x in project.identities.observations(pid) if x['observation_id']==selected),None)
                if observation: source = {'origin':'Bibliographic/discovery metadata abstract',
                    'provider':observation['source']['producer_id'],'source_sha256':observation['source']['source_sha256'],
                    'source_uri':observation['source']['source_uri'],'verification':'Not a verified full-text document'}
        result = {'schema':SCHEMA,'availability':self.availability(project,paper),
                  'evidence':project.evidence.status(pid),'abstract_source':source,
                  'activity':self.activity(project,pid,advanced=advanced,offset=offset,limit=limit)}
        safe_data(canonical(result),secrets=ProjectController._secrets(project.config))
        return result

    def history(self, project, paper, *, offset=0, limit=10):
        pid = _paper_id(paper)
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=50: raise ContractError('invalid evidence history page')
        directory = files.location(project,family='evidence')/'plans'
        records = []
        if directory.exists():
            for path in directory.glob('*.json'):
                value,_ = self._plan(project,path.stem)
                if value['paper']==paper: records.append(value)
        records.sort(key=lambda x:(x['created_at'],x['handle']),reverse=True)
        return {'schema':SCHEMA,'items':[{'handle':v['handle'],'created_at':v['created_at'],
                 'status':self.inspect(project,v['handle'])['status']} for v in records[offset:offset+limit]],
                 'next_offset':offset+limit if offset+limit<len(records) else None,
                 'scientific':self.activity(project,pid,offset=offset,limit=limit)}

    def close(self):
        with self._mutex: self._closed=True
        # The worker keeps its own lease; process exit is crash-safe, not resume.
