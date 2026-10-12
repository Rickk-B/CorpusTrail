"""Exact-plan local discovery orchestration over the existing scientific executor.

No provider/identity rules live here. Durable files carry UI preparation/approval
and parent lifecycle; the existing database carries scientific request/results.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from importlib import resources
import os
import json
import re
import secrets
import threading
import time
import uuid

from corpustrail import __version__
from corpustrail._internal.values import content_hash, digest_bytes, now, ContractError
from corpustrail.discovery import SearchPlan
from corpustrail.models.contracts import safe_data
from corpustrail.providers import metadata_provider
from corpustrail.providers.metadata import request_preview, verify_preview_request
from corpustrail.providers.network import UrlLibTransport
from . import _workflow_files as files
from .project_use import acquire_project_use, ProjectUseError
from .projects import NAMES, ProjectCommandError, ProjectController

SCHEMA = 'corpustrail-discovery-workflow/v1'
BOUNDS = {'page_size': 20, 'max_pages': 1, 'max_attempts': 1,
          'retry_delay_seconds': 1, 'max_retry_wait_seconds': 30}
TERMINAL = {'completed', 'partial', 'failed', 'cancelled', 'interrupted'}


def _handle(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ProjectCommandError('Select a saved search plan.')
    return value


def _command(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', value):
        raise ProjectCommandError('Invalid discovery command identity.')
    return value


def _implementation_hash():
    return digest_bytes(resources.files('corpustrail.providers').joinpath('metadata.py').read_bytes())


def _completion(value):
    if value is None: return None
    # The exact runtime cursor remains in authoritative scientific provenance,
    # not routine status DTOs or duplicated parent receipts.
    return {**{key: item for key, item in value.items() if key!='next_cursor'},
            'continuation_available': bool(value.get('next_cursor'))}


class _FrozenProvider:
    def __init__(self, provider, preview):
        self.provider, self.preview = provider, preview
        self.name, self.version, self.network, self.hosts = provider.name, provider.version, provider.network, provider.hosts

    def request(self, plan, cursor):
        request = self.provider.request(plan, cursor)
        verify_preview_request(self.preview, request, cursor)
        return request

    def normalize(self, *args):
        return self.provider.normalize(*args)


class _SafeTransport:
    def __init__(self, transport, values):
        self.transport, self.values, self.network = transport, values, transport.network

    def request(self, *args, **kwargs):
        response = self.transport.request(*args, **kwargs)
        # Reject echoed credentials before the scientific service preserves bytes
        # or allowlisted rate headers. Never log rejected remote text.
        text = response.body.decode('utf-8', errors='replace')
        if any(value and (value in text or any(value in str(h) for h in response.headers.values())) for value in self.values):
            raise ContractError('sensitive provider response rejected')
        safe_data(text, secrets=self.values)
        try:
            decoded = json.loads(text)
        except (ValueError, TypeError):
            decoded = None
        def scan(value):
            if isinstance(value, str) and any(secret and secret in value for secret in self.values):
                raise ContractError('sensitive provider response rejected')
            if isinstance(value, dict):
                for key, item in value.items(): scan(key); scan(item)
            if isinstance(value, list):
                for item in value: scan(item)
        scan(decoded)
        safe_data(list(response.headers.values()), secrets=self.values)
        safe_data(response.final_url, secrets=self.values)
        return response


class DiscoveryController:
    def __init__(self, controller, *, provider_factory=metadata_provider, transport_factory=UrlLibTransport):
        self.controller, self.provider_factory, self.transport_factory = controller, provider_factory, transport_factory
        self._mutex = threading.RLock()
        self._previews, self._workers = {}, {}
        self._closed = False

    @contextmanager
    def _write(self, project):
        # Only immutable workflow publication is serialized. Scientific network
        # execution never holds this lock or a database transaction.
        lease = None
        for _ in range(40):
            try:
                lease = files.operation_lease(project, 'journal'); break
            except ProjectUseError:
                time.sleep(.05)
        if lease is None:
            raise ProjectCommandError('Discovery state is busy. Refresh before retrying.', status=409)
        try: yield
        finally: lease.close()

    def _plan(self, project, handle):
        handle = _handle(handle)
        value = files.read(files.location(project) / 'plans' / (handle+'.json'))
        if content_hash(value) != 'sha256:'+handle or value['schema'] != SCHEMA or value['project_id'] != project.config.project_id:
            raise ContractError('saved discovery plan identity differs')
        for child in value['providers']:
            plan = SearchPlan(**child['plan']); plan.validate()
            if plan.plan_id != child['plan_id']:
                raise ContractError('saved provider plan identity differs')
            from corpustrail._internal.pipeline import events
            reserved = events(project, scope_id=plan.run_id, kind='discovery_plan')
            if reserved and reserved[0]['payload'] != child['plan']:
                raise ProjectCommandError('A scientific run identity belongs to a different plan. Inspect it and prepare a new search; no results are attributed here.',
                                          code='run_binding_conflict', status=409)
        return value

    def _validate(self, project, value):
        if (project.configuration_history()[-1]['event_id'] != value['config_event_id']
                or value['adapter_code_sha256'] != _implementation_hash()):
            raise ProjectCommandError('Project configuration or adapter changed. Preview and approve a new search.', code='stale_search', status=409)
        availability = {p['id']: p for p in self.configuration(project)['providers']}
        for child in value['providers']:
            if not availability[child['provider']]['ready']:
                raise ProjectCommandError('Selected provider needs configuration. No search was started.', status=409)
            provider = self.provider_factory(child['provider'])
            plan = SearchPlan(**child['plan'])
            if provider.version != plan.adapter_version or request_preview(provider, plan) != child['request_preview']:
                raise ProjectCommandError('Provider request rules changed. Preview a new search.', status=409)

    def configuration(self, project):
        config = project.config
        providers = []
        for name, label in NAMES.items():
            matches = [p for p in config.providers if p.adapter == name and p.provider_id == name]
            matching = len(matches) == 1
            env = matches[0].credential_env if matching else None
            credential_ready = not env or bool(os.environ.get(env))
            providers.append({'id': name, 'label': label, 'configured': matching,
                'ready': matching and credential_ready, 'credential_env': env,
                'credential_present': bool(os.environ.get(env)) if env else None,
                'reason': ('Not enabled with the supported provider identity in Project Settings.' if not matching else
                           'Set the configured credential environment variable before launching CorpusTrail.' if not credential_ready else
                           'Uses your configured credential.' if env else 'Unauthenticated adapter mode; provider access/rate limits may apply.'),
                'connectivity_tested': False})
        return {'schema': SCHEMA, 'config_event_id': project.configuration_history()[-1]['event_id'],
                'providers': providers, 'concepts': [{'id': c.concept_id, 'label': c.label} for c in config.search],
                'bounds': BOUNDS, 'limitations': 'One exact query is sent to each selected adapter. No automatic alias expansion or separate date/language filters.'}

    def _receipt(self, project, request_id, payload):
        path = files.location(project) / 'commands' / (content_hash(request_id).split(':')[1]+'.json')
        if not path.exists(): return None
        value = files.read(path)
        if value['request_sha256'] != content_hash(payload):
            raise ProjectCommandError('This command was already used for different content.', status=409)
        return value['result']

    def _record_receipt(self, project, request_id, payload, result):
        files.publish(files.location(project) / 'commands' / (content_hash(request_id).split(':')[1]+'.json'),
                      {'request_sha256': content_hash(payload), 'result': result})

    def prepare(self, project, *, request_id, config_event_id, query, providers, bounds):
        _command(request_id)
        if (not isinstance(query, str) or not query.strip() or len(query) > 4000 or '\x00' in query
                or not isinstance(providers, list) or not 1 <= len(providers) <= 4 or any(not isinstance(p, str) for p in providers)
                or len(set(providers)) != len(providers)
                or any(p not in NAMES for p in providers) or not isinstance(bounds, dict) or set(bounds) != set(BOUNDS)):
            raise ProjectCommandError('Enter an exact search query, select supported providers and check bounded search settings.')
        payload = {'operation': 'prepare', 'config_event_id': config_event_id, 'query': query, 'providers': providers, 'bounds': bounds}
        safe_data(payload, secrets=ProjectController._secrets(project.config))
        with self._mutex, self._write(project):
            if project.configuration_history()[-1]['event_id'] != config_event_id:
                raise ProjectCommandError('Project settings changed. Reload Discovery before previewing.', status=409)
            prior = self._receipt(project, request_id, payload)
            if prior:
                value = self._plan(project, prior['handle'])
            else:
                created_at, children = now(), []
                for name in providers:
                    provider = self.provider_factory(name)
                    plan = project.discovery.plan(provider, run_id='local-discovery-'+uuid.uuid4().hex,
                                                  query=query, created_at=created_at, **bounds)
                    children.append({'provider': name, 'label': NAMES[name], 'plan_id': plan.plan_id,
                                     'plan': asdict(plan), 'request_preview': request_preview(provider, plan)})
                value = {'schema': SCHEMA, 'project_id': project.config.project_id, 'created_at': created_at,
                    'config_event_id': config_event_id, 'software_version': __version__,
                    'adapter_code_sha256': _implementation_hash(), 'providers': children,
                    'query': query, 'bounds': bounds, 'request_id': request_id,
                    'canonicalization': 'Explicitly approved exact-identifier/source enrollment; never corpus membership.'}
                self._validate(project, value)
                handle = content_hash(value).split(':')[1]
                files.publish(files.location(project) / 'plans' / (handle+'.json'), value)
                self._record_receipt(project, request_id, payload, {'handle': handle})
            handle = content_hash(value).split(':')[1]
            nonce = secrets.token_urlsafe(32)
            self._previews = {k: v for k, v in self._previews.items() if v[2] > time.monotonic()}
            if len(self._previews) >= 256:
                raise ProjectCommandError('Too many pending previews. Wait before creating another.')
            from .project_use import directory_identity
            self._previews[nonce] = (project.config.project_id, handle, time.monotonic()+900, directory_identity(project.root))
            return {**self.inspect(project, handle), 'preview_nonce': nonce}

    def approve(self, project, *, handle, request_id, preview_nonce, confirm_external, approve_identities):
        _handle(handle); _command(request_id)
        payload = {'operation': 'approve', 'handle': handle, 'nonce_hash': content_hash(preview_nonce),
                   'confirm_external': confirm_external, 'approve_identities': approve_identities}
        with self._mutex, self._write(project):
            prior = self._receipt(project, request_id, payload)
            if prior: return self.inspect(project, handle)
            value = self._plan(project, handle); self._validate(project, value)
            token = self._previews.get(preview_nonce)
            from .project_use import directory_identity
            if (confirm_external is not True or approve_identities is not True or token is None
                    or token[:2] != (project.config.project_id, handle) or token[2] < time.monotonic()
                    or token[3] != directory_identity(project.root)):
                raise ProjectCommandError('Review this preview and explicitly approve transfer and exact identity organization.', status=409)
            history = files.history(project, handle)
            if any(e['kind'] in {'approved', 'invalidated', 'queued'} for e in history):
                raise ProjectCommandError('This preview is already approved, edited or executed. Inspect its history.', status=409)
            files.append(project, handle, 'approved', {'plan_sha256': 'sha256:'+handle, 'request_id': request_id,
                'transfer': 'Displayed queries/settings to selected scholarly providers; no paper evidence or review labels.',
                'confirm_external': True, 'approve_identities': True, 'actor': 'local-user'}, now())
            self._previews.pop(preview_nonce, None)
            self._record_receipt(project, request_id, payload, {'handle': handle})
        return self.inspect(project, handle)

    def invalidate(self, project, *, handle):
        value = self._plan(project, handle)
        with self._mutex, self._write(project):
            history = files.history(project, handle)
            if any(e['kind'] == 'queued' for e in history):
                raise ProjectCommandError('A started search cannot be edited; prepare a new search.', status=409)
            if not any(e['kind'] == 'invalidated' for e in history):
                files.append(project, handle, 'invalidated', {'plan_sha256': content_hash(value)}, now())
        return self.inspect(project, handle)

    def _alive(self, project, handle):
        try:
            lease = files.operation_lease(project, 'worker-'+handle); lease.close(); return False
        except ProjectUseError as exc:
            from .project_use import ProjectBusy
            if isinstance(exc, ProjectBusy): return True
            raise ProjectCommandError('Search activity cannot be verified safely. Inspect the launcher before retrying.', status=409) from exc

    def start(self, project, *, handle, request_id):
        _handle(handle); _command(request_id)
        payload = {'operation': 'start', 'handle': handle}
        with self._mutex, self._write(project):
            prior = self._receipt(project, request_id, payload)
            if prior: return self.inspect(project, handle)
            value = self._plan(project, handle); self._validate(project, value)
            history = files.history(project, handle)
            if any(e['kind'] == 'queued' for e in history):
                raise ProjectCommandError('This plan already has an execution. Inspect it or explicitly prepare a new search.', status=409)
            if not any(e['kind'] == 'approved' and e['payload']['plan_sha256'] == 'sha256:'+handle for e in history) or any(e['kind']=='invalidated' for e in history):
                raise ProjectCommandError('Preview and approve this exact search before running.', status=409)
            if self._closed: raise ProjectCommandError('This launcher is stopping; no search was started.', status=409)
            leases = []
            try:
                leases = [acquire_project_use(project.root)]
                leases.append(files.operation_lease(project, 'project-worker'))
                leases.append(files.operation_lease(project, 'worker-'+handle))
                files.append(project, handle, 'queued', {'request_id': request_id}, now())
                self._record_receipt(project, request_id, payload, {'handle': handle})
                cancellation = threading.Event()
                thread = threading.Thread(target=self._execute, args=(project, handle, value, cancellation, leases), daemon=True)
                self._workers[(str(project.root), handle)] = (thread, cancellation)
                thread.start()
            except BaseException as exc:
                for lease in reversed(leases): lease.close()
                self._workers.pop((str(project.root), handle), None)
                if isinstance(exc, Exception):
                    raise ProjectCommandError('Search startup could not be completed. Inspect saved status before retrying; no automatic replay.',
                                              code='startup_failed', status=409) from exc
                raise
        return self.inspect(project, handle)

    def _event(self, project, handle, kind, payload):
        with self._write(project):
            self._plan(project, handle)
            files.append(project, handle, kind, payload, now())

    def _execute(self, project, handle, value, cancellation, leases):
        successful, interrupted = 0, False
        from .project_use import directory_identity
        def event(kind, payload):
            if directory_identity(project.root) != leases[0].identity:
                raise ContractError('project location changed during discovery')
            self._event(project, handle, kind, payload)
        try:
            event('running', {})
            for child in value['providers']:
                if cancellation.is_set():
                    event('terminal', {'status': 'cancelled', 'reason': 'Stopped between providers; no resume or automatic retry.'}); return
                name = child['provider']
                event('provider_started', {'provider': name})
                try:
                    self._validate(project, value)
                    provider = _FrozenProvider(self.provider_factory(name), child['request_preview'])
                    transport = _SafeTransport(self.transport_factory(), ProjectController._secrets(project.config))
                    result = project.discovery.execute(SearchPlan(**child['plan']), provider, transport=transport, confirm_external=True)
                    self._validate(project, value)
                    # This is the existing, explicitly approved exact enrollment.
                    links = project.discovery.canonicalize(child['plan']['run_id'], approve_new_identities=True, approve_aliases=True)
                    good = result['outcome'] in {'exhausted', 'truncated_page_limit', 'truncated_provider_limit'}
                    if good: successful += 1
                    event('provider_finished', {'provider': name, 'result': _completion(result),
                        'status': 'completed' if good else 'failed', 'identity_issues': sum('paper_id' not in x for x in links)})
                except Exception as exc:
                    progress = project.discovery.run_summary([child['plan']['run_id']])['runs'][child['plan']['run_id']]
                    uncertain = progress['physical_requests_started'] > 0 and progress['completion'] is None
                    interrupted = interrupted or uncertain
                    event('provider_finished', {'provider': name, 'status': 'interrupted' if uncertain else 'failed',
                        'diagnostic': type(exc).__name__, 'message': 'Provider execution or organization failed. Inspect preserved provenance; no automatic retry.'})
            preserved = project.discovery.run_summary([x['plan']['run_id'] for x in value['providers']])['observations_preserved']
            status = 'completed' if successful == len(value['providers']) else 'partial' if successful or preserved else 'interrupted' if interrupted else 'failed'
            event('terminal', {'status': status})
        except BaseException:
            # A failed journal write cannot become a success claim. A dead worker
            # is projected as interrupted without rewriting records on a GET.
            pass
        finally:
            for lease in reversed(leases): lease.close()
            with self._mutex: self._workers.pop((str(project.root), handle), None)

    def cancel(self, project, *, handle):
        self._plan(project, handle)
        with self._mutex, self._write(project):
            worker = self._workers.get((str(project.root), handle))
            if worker is None or any(e['kind']=='terminal' for e in files.history(project, handle)):
                raise ProjectCommandError('This launcher does not own a running search. Inspect its outcome.', status=409)
            if not worker[1].is_set():
                files.append(project, handle, 'cancel_requested', {'boundary': 'After the current bounded provider operation.'}, now())
                worker[1].set()
        return self.inspect(project, handle)

    def close(self):
        with self._mutex:
            self._closed = True
            for _, cancellation in self._workers.values(): cancellation.set()
        # Do not release worker leases or pretend to finish scientific requests.
        # Process exit releases kernel locks; unfinished parent jobs show interrupted.

    def inspect(self, project, handle):
        value = self._plan(project, handle)
        history = files.history(project, handle)
        terminal = [e for e in history if e['kind']=='terminal']
        queued = any(e['kind']=='queued' for e in history)
        alive = self._alive(project, handle) if queued and not terminal else False
        if queued and not terminal and not alive:
            # The worker may have published its terminal receipt and released
            # its lease after our first history read. Refresh immutable history
            # under that observed quiescence before claiming interruption.
            history = files.history(project, handle)
            terminal = [e for e in history if e['kind']=='terminal']
        status = (terminal[-1]['payload']['status'] if terminal else
                  ('running' if any(e['kind']=='running' for e in history) else 'queued') if queued and alive else 'interrupted' if queued else
                  'invalidated' if any(e['kind']=='invalidated' for e in history) else
                  'approved' if any(e['kind']=='approved' for e in history) else 'prepared')
        results = {e['payload']['provider']: e['payload'] for e in history if e['kind']=='provider_finished'}
        started = {e['payload']['provider'] for e in history if e['kind']=='provider_started'}
        summary = project.discovery.run_summary([x['plan']['run_id'] for x in value['providers']])
        children = []
        for child in value['providers']:
            run = summary['runs'][child['plan']['run_id']]
            run = {**run, 'completion': _completion(run['completion'])}
            children.append({'provider': child['provider'], 'label': child['label'],
                'status': results[child['provider']]['status'] if child['provider'] in results else
                          ('interrupted' if status=='interrupted' else 'running') if child['provider'] in started else 'not_started',
                **run, 'outcome': results.get(child['provider'])})
        available = status in {'prepared', 'approved'}
        try: self._validate(project, value)
        except ContractError: available = False
        running = [e for e in history if e['kind']=='running']
        started_at = running[0]['timestamp'] if running else None
        finished_at = terminal[-1]['timestamp'] if terminal else None
        elapsed = max(0, int((datetime.fromisoformat(finished_at or now())-datetime.fromisoformat(started_at)).total_seconds())) if started_at and status!='interrupted' else None
        result = {'schema': SCHEMA, 'handle': handle, 'plan': value, 'status': status, 'execution_available': available,
                'providers': children, 'summary': {**{k:v for k,v in summary.items() if k!='runs'},
                    'provider_errors': sum(p['status'] in {'failed','interrupted'} for p in children)},
                'providers_finished': len(results), 'providers_total': len(children), 'history': history,
                'cancel_requested': any(e['kind']=='cancel_requested' for e in history),
                'cancellation_available': (str(project.root), handle) in self._workers and status in {'queued','running'},
                'started_at': started_at, 'finished_at': finished_at, 'elapsed_seconds': elapsed,
                'notice': 'Discovery collects candidates, not corpus membership. Repeating requires a new plan and approval; interrupted searches never resume automatically.'}
        safe_data(result, secrets=ProjectController._secrets(project.config))
        return result

    def history(self, project, *, offset=0, limit=10):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
            raise ProjectCommandError('Invalid search-history page.')
        directory = files.location(project) / 'plans'
        handles = sorted((p.stem for p in directory.glob('*.json')),
                         key=lambda h: (self._plan(project, h)['created_at'], h), reverse=True) if directory.exists() else []
        items = []
        for handle in handles[offset:offset+limit]:
            view = self.inspect(project, handle)
            items.append({'handle': handle, 'query': view['plan']['query'], 'created_at': view['plan']['created_at'],
                          'status': view['status'], 'summary': view['summary']})
        return {'schema': SCHEMA, 'items': items, 'next_offset': offset+limit if offset+limit<len(handles) else None}

    def papers(self, project, handle, **page):
        value = self._plan(project, handle)
        result = project.discovery.run_papers([x['plan']['run_id'] for x in value['providers']], **page)
        return {'schema': SCHEMA, 'items': [{'title': x['fields']['title'] or 'Untitled publication',
                'url': '/papers/'+x['paper_id'].split(':')[1]} for x in result['items']], 'next_offset': result['next_offset']}

    def provenance(self, project, handle, *, provider, **page):
        value = self._plan(project, handle)
        matches = [x for x in value['providers'] if x['provider']==provider]
        if len(matches)!=1: raise ProjectCommandError('Choose a provider from this plan.')
        return {'schema': SCHEMA, **project.discovery.run_provenance(matches[0]['plan']['run_id'], **page)}

    def command(self, project, operation, body):
        fields = {'prepare': {'request_id', 'config_event_id', 'query', 'providers', 'bounds'},
                  'approve': {'handle', 'request_id', 'preview_nonce', 'confirm_external', 'approve_identities'},
                  'start': {'handle', 'request_id'}, 'invalidate': {'handle'}, 'cancel': {'handle'}}
        if operation not in fields or set(body) != fields[operation]:
            raise ProjectCommandError('Unsupported discovery fields or operation.')
        return getattr(self, operation)(project, **body)
