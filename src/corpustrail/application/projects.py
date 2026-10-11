"""Guided local project commands over the existing configuration contract.

No migrations, remote calls, membership writes or persistent application registry.
Browser paths are names under a launcher-approved root, never arbitrary filenames.
"""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid

from corpustrail.errors import ContractError
from corpustrail.models.contracts import safe_data
from corpustrail.project import Project, ProjectConfig
from corpustrail.project.config import EvidencePolicy, ProviderConfig, ReviewPolicy, SearchConcept
from corpustrail.project.service import BOOTSTRAP
from corpustrail.providers import metadata_provider
from corpustrail.evidence.service import EuropePmcResolver

SCHEMA = 'corpustrail-project-form/v1'
NAMES = {'openalex': 'OpenAlex', 'crossref': 'Crossref', 'europepmc': 'Europe PMC',
         'semantic_scholar': 'Semantic Scholar'}


class ProjectCommandError(ContractError):
    """Messages are deliberately safe to return; never include request/OS errors."""

    def __init__(self, message, *, code='invalid_configuration', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def _text(value, label, maximum=16000, *, optional=False):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ProjectCommandError('Check the ' + label + ' field.')
    value = value.strip()
    if not value and not optional:
        raise ProjectCommandError('Enter ' + label + '.')
    return value


def _safe_path(path):
    """Reject symlinks in every existing component, including registered parents."""
    path = Path(path).absolute()
    for current in (*reversed(path.parents), path):
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ProjectCommandError('Symbolic-link project locations are not supported.', code='unsafe_location')
    return path


def _folder(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value)
            or value.endswith('.') or value.casefold().split('.')[0] in
            {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}):
        raise ProjectCommandError('Use a folder name with letters, numbers, hyphens or underscores.', code='unsafe_location')
    return value


class ProjectController:
    """One local application with explicitly enrolled project locations.

    Request receipts are bounded, in-memory navigation state. Configuration CAS
    and exclusive directory reservation remain the durable/restart safeguards.
    """

    def __init__(self, *, projects_root=None, project=None):
        self.root = _safe_path(projects_root or Path.home() / 'CorpusTrailProjects')
        if self.root.exists() and not self.root.is_dir():
            raise ProjectCommandError('The configured projects root must be a directory.')
        self._lock = threading.RLock()
        self._registered = {}
        self._receipts = {}
        self.active_handle = None
        if project is not None:
            self.active_handle = self._register(project.root)
            self.project()  # Validate enrollment, without migration.

    def _register(self, path):
        path = _safe_path(path)
        for handle, enrolled in self._registered.items():
            if enrolled == path:
                return handle
        handle = uuid.uuid4().hex
        self._registered[handle] = path
        return handle

    def _open(self, path):
        path = _safe_path(path)
        bootstrap = _safe_path(path / BOOTSTRAP)
        if not bootstrap.is_file() or bootstrap.stat().st_size > 1024 * 1024:
            raise ProjectCommandError('This folder is not a complete standalone CorpusTrail project.', code='project_unavailable')
        try:
            config = ProjectConfig.from_dict(json.loads(bootstrap.read_text(encoding='utf-8')))
            _safe_path(path / config.database)
            return Project.open(path)
        except (ContractError, ValueError, OSError, TypeError) as exc:
            raise ProjectCommandError('Project could not be opened. Check permissions and compatibility; no automatic upgrade was attempted.',
                                      code='project_unavailable') from exc

    def project(self, handle=None):
        with self._lock:
            handle = handle or self.active_handle
            if handle not in self._registered:
                raise ProjectCommandError('Choose a project first.', code='project_required', status=409)
            return self._open(self._registered[handle])

    def entry(self, *, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectCommandError('Invalid project page.')
        with self._lock:
            _safe_path(self.root)
            candidates = set(self._registered.values())
            if self.root.is_dir():
                candidates.update(child for child in self.root.iterdir()
                                  if not child.is_symlink() and child.is_dir() and (child / BOOTSTRAP).is_file())
            ordered = sorted(candidates, key=lambda p: (p.name.casefold(), str(p)))
            items = []
            for path in ordered[offset:offset+limit]:
                try:
                    project = self._open(path)
                    items.append({'handle': self._register(path), 'name': project.config.name, 'location': str(path)})
                except ProjectCommandError:
                    items.append({'name': path.name, 'unavailable': True})
            return {'schema': SCHEMA, 'projects_root': str(self.root), 'items': items,
                    'next_offset': offset + limit if offset + limit < len(ordered) else None,
                    'active_handle': self.active_handle, 'persistent_application_state': False,
                    'capabilities': self.capabilities()}

    def capabilities(self):
        # Instantiate only installed adapters; request/transport is never invoked.
        providers = []
        for name, label in NAMES.items():
            adapter = metadata_provider(name)
            providers.append({'id': adapter.name, 'label': label,
                              'credential_env_supported': name in {'openalex', 'semantic_scholar'}})
        resolver = EuropePmcResolver()
        return {'providers': providers, 'resolvers': [{'id': resolver.name, 'label': 'Europe PMC',
                'description': 'Open structured article text for an already known PMCID. Automatic DOI/PMID-to-PMCID enrichment is not available.'}]}

    def open(self, handle):
        with self._lock:
            self.project(handle)
            self.active_handle = handle
            return {'schema': SCHEMA, 'project_handle': handle, 'dashboard_url': '/dashboard'}

    def settings(self, handle=None):
        from .reads import ProjectReads
        project = self.project(handle)
        history = project.configuration_history()
        current = history[-1]
        config = ProjectConfig.from_dict(current['config'])
        result = {'schema': SCHEMA, 'project_handle': handle or self.active_handle,
                  'revision': current['event_id'], 'version': config.config_version,
                  'location': str(project.root), 'fields': {
                      'name': config.name, 'description': config.description, 'scope': config.review.scope or '',
                      'providers': [{'id': p.provider_id, 'adapter': p.adapter, 'credential_env': p.credential_env} for p in config.providers],
                      'resolvers': list(config.evidence.resolvers),
                      'search': [dict(concept_id=s.concept_id, label=s.label, language=s.language, aliases=list(s.aliases)) for s in config.search],
                      'reviewer': current['created_by'], 'authorized_reviewers': list(config.review.authorized_reviewers)},
                  'definition': {'scope_present': config.review.scope is not None,
                      'configuration_revision': current['event_id'],
                      'sha256': hashlib.sha256(json.dumps({'description': config.description,
                          'scope': config.review.scope, 'policy': config.review.policy_id}, sort_keys=True).encode()).hexdigest()},
                  'history': [{'version': row['config']['config_version'], 'created_by': row['created_by'],
                               'created_at': row['created_at']} for row in history[-20:]],
                  'has_frozen_review_sessions': bool(ProjectReads(project).dashboard()['review']['sessions']),
                  'capabilities': self.capabilities(),
                  'session_warning': 'Every saved configuration change makes existing frozen review sessions stale. Their packets and saved work remain unchanged; prepare a new session explicitly.'}
        safe_data(result, secrets=self._secrets(config))
        return result

    @staticmethod
    def _secrets(config):
        envs = [p.credential_env for p in config.providers] + [m.credential_env for m in config.models]
        return tuple(os.environ.get(name, '') for name in envs if name)

    def _config(self, raw, *, prior=None):
        if not isinstance(raw, dict) or set(raw) != {'name', 'description', 'scope', 'providers', 'resolvers',
                                                    'search', 'reviewer', 'authorized_reviewers'}:
            raise ProjectCommandError('Unsupported project form fields.')
        try:
            if any(not isinstance(raw[key], list) for key in ('providers', 'resolvers', 'search', 'authorized_reviewers')):
                raise ProjectCommandError('Project collections must be lists.')
            safe_data(raw, secrets=self._secrets(prior) if prior else ())
            actor = _text(raw['reviewer'], 'reviewer pseudonym', 100)
            providers = []
            for item in raw['providers']:
                if not isinstance(item, dict) or set(item) != {'id', 'adapter', 'credential_env'}:
                    raise ProjectCommandError('Invalid provider configuration.')
                providers.append(ProviderConfig(item['id'], item['adapter'], item['credential_env']))
            available = self.capabilities()
            old_providers = prior.providers if prior else ()
            old_resolvers = prior.evidence.resolvers if prior else ()
            for provider in providers:
                if provider.adapter not in NAMES and provider not in old_providers:
                    raise ProjectCommandError('Only installed discovery adapters can be selected.')
            resolvers = tuple(raw['resolvers'])
            if any(name not in {r['id'] for r in available['resolvers']} and name not in old_resolvers for name in resolvers):
                raise ProjectCommandError('Only installed evidence resolvers can be selected.')
            search = []
            for item in raw['search']:
                if not isinstance(item, dict) or set(item) != {'concept_id', 'label', 'language', 'aliases'}:
                    raise ProjectCommandError('Invalid search concept.')
                search.append(SearchConcept(item['concept_id'], item['label'], item['language'], tuple(item['aliases'])))
            authorized = tuple(_text(r, 'authorized reviewer pseudonym', 100) for r in raw['authorized_reviewers'])
            scope = _text(raw['scope'], 'broad-corpus definition', optional=prior is not None and prior.review.scope is None)
            config = replace(prior or ProjectConfig('project-' + uuid.uuid4().hex, 'pending', 'pending'),
                name=_text(raw['name'], 'project name', 200), description=_text(raw['description'], 'topic description', 8000),
                config_version=prior.config_version+1 if prior else 1, search=tuple(search), providers=tuple(providers),
                review=replace(prior.review if prior else ReviewPolicy(), scope=scope or None, authorized_reviewers=authorized),
                evidence=replace(prior.evidence if prior else EvidencePolicy(), resolvers=resolvers))
            config.validate()
            safe_data(raw, secrets=self._secrets(config))
            return config, actor
        except ProjectCommandError:
            raise
        except (ContractError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ProjectCommandError('Invalid configuration. Check required fields, unique concepts, reviewer names and credential environment-variable names; never enter secret values.') from exc

    def _once(self, request_id, payload, action):
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}', request_id):
            raise ProjectCommandError('A valid request receipt is required.')
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        with self._lock:
            if request_id in self._receipts:
                previous, result = self._receipts[request_id]
                if signature != previous:
                    raise ProjectCommandError('This request was already used for different settings.', status=409)
                return result
            result = action()
            if len(self._receipts) >= 256:
                self._receipts.pop(next(iter(self._receipts)))
            self._receipts[request_id] = (signature, result)
            return result

    def create(self, *, request_id, folder, fields, confirm_authority=False):
        def action():
            config, actor = self._config(fields)
            safe_data(folder, secrets=self._secrets(config))
            if config.review.authorized_reviewers and confirm_authority is not True:
                raise ProjectCommandError('Explicitly confirm the initial corpus-decision authority configuration.')
            target = _safe_path(self.root / _folder(folder))
            if target.exists():
                raise ProjectCommandError('That project folder already exists. Choose another folder; nothing was overwritten.', code='location_exists', status=409)
            try:
                project = Project.create(target, config, created_by=actor)
            except Exception as exc:
                raise ProjectCommandError('Project creation did not complete. Any reserved folder/data has been preserved; inspect it before retrying with a new location.', code='creation_failed', status=409) from exc
            self.active_handle = self._register(project.root)
            return {'schema': SCHEMA, 'project_handle': self.active_handle, 'dashboard_url': '/dashboard', 'version': 1}
        return self._once(request_id, ['create', folder, fields, confirm_authority], action)

    def configure(self, *, request_id, project_handle, revision, fields, confirm_authority=False, confirm_session_change=False):
        def action():
            project = self.project(project_handle)
            history = project.configuration_history()
            if revision != history[-1]['event_id']:
                raise ProjectCommandError('Settings changed in another window. Reload settings before saving.', code='stale_revision', status=409)
            prior = ProjectConfig.from_dict(history[-1]['config'])
            config, actor = self._config(fields, prior=prior)
            if config.review.authorized_reviewers != prior.review.authorized_reviewers and confirm_authority is not True:
                raise ProjectCommandError('Explicitly confirm the reviewer authority changes.')
            comparable = replace(config, config_version=prior.config_version)
            if comparable == prior:
                return {'schema': SCHEMA, 'project_handle': project_handle, 'revision': revision,
                        'version': prior.config_version, 'changed': False}
            from .reads import ProjectReads
            if ProjectReads(project).dashboard()['review']['sessions'] and confirm_session_change is not True:
                raise ProjectCommandError('Confirm that existing frozen review sessions will become stale; their saved work remains preserved.', code='session_confirmation', status=409)
            try:
                event_id = project.configure(config, expected_event_id=revision, created_by=actor)
            except ContractError as exc:
                code = 'stale_revision' if 'stale' in str(exc) else 'scope_guard'
                message = ('Settings changed in another window. Reload before saving.' if code == 'stale_revision' else
                           'Scientific scope cannot change after authoritative review. Existing decisions and review packets have been preserved.')
                raise ProjectCommandError(message, code=code, status=409) from exc
            return {'schema': SCHEMA, 'project_handle': project_handle, 'revision': event_id,
                    'version': config.config_version, 'changed': True}
        return self._once(request_id, ['configure', project_handle, revision, fields, confirm_authority, confirm_session_change], action)
