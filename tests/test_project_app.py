"""Guided configuration, preserved scientific state and offline loopback only."""

from copy import deepcopy
import hashlib
import http.client
from importlib import resources
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from corpustrail.application.projects import ProjectController, ProjectCommandError, SCHEMA
from corpustrail.application import ProjectReads
from corpustrail._internal.database import connection
from corpustrail.cli import main
from corpustrail.errors import ContractError
from corpustrail.curation import EvidenceBasis, ReviewEvent
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.local_app import make_server
from corpustrail.project import Project, ProjectConfig
from corpustrail.project.config import ReviewPolicy, ProviderConfig, SearchConcept, EvidencePolicy

AT = '2026-01-01T00:00:00+00:00'


def fingerprint(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def form():
    return {'name': 'Materials research', 'description': 'Invented scientific topic',
            'scope': 'Broad materials literature, not question-specific screening',
            'providers': [{'id': 'crossref', 'adapter': 'crossref', 'credential_env': None},
                          {'id': 'openalex', 'adapter': 'openalex', 'credential_env': 'CORPUSTRAIL_FIXTURE_KEY'}],
            'resolvers': ['europepmc'], 'search': [{'concept_id': 'materials', 'label': 'synthetic materials',
                                                  'language': 'en', 'aliases': ['invented materials']}],
            'reviewer': 'researcher', 'authorized_reviewers': []}


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'projects'
        self.controller = ProjectController(projects_root=self.root)
        self.addCleanup(self.controller.close)

    def create(self, *, fields=None, folder='materials', request_id='create-request-fixture', confirm_authority=False):
        return self.controller.create(request_id=request_id, folder=folder, fields=fields or form(), confirm_authority=confirm_authority)

    def existing(self, *, legacy=False):
        config = ProjectConfig('existing-fixture', 'Existing materials', 'Invented scope',
            providers=(ProviderConfig('crossref', 'crossref'),),
            search=(SearchConcept('foreign-concept', 'Matériaux', 'fr', ('matériau',)),),
            review=ReviewPolicy(scope=None if legacy else 'Existing broad definition', authorized_reviewers=('curator',)),
            evidence=EvidencePolicy(resolvers=('europepmc',), max_attempts=2))
        self.project = Project.create(self.root / 'existing', config, created_by='fixture', created_at=AT)
        self.ids = []
        for i in range(5):
            record = BibliographicRecord('Duplicate title' if i < 2 else 'Invented paper '+str(i),
                None if i == 4 else 'Synthetic abstract', ('Fixture author',), 2020, 'Invented journal',
                (Identifier('doi', '10.1234/project-app.'+str(i)),))
            source = SourceReference('fixture://metadata', str(i), 'sha256:'+str(i)*64, 0, 'fixture', AT)
            pid = self.project.identities.apply(self.project.identities.plan(record, source), approve_new_identity=True, approve_aliases=True)
            self.ids.append(pid)
            event = ReviewEvent(pid, 'included', 'sufficient', 'metadata', 'Synthetic review', 'curator', AT,
                (EvidenceBasis('metadata', source.source_sha256, source.source_uri, artifact_validity='verified'),),
                authority_state='non_authoritative')
            self.project.reviews.apply(self.project.reviews.plan(event), recorded_at=AT)
        self.project.review_sessions.prepare('frozen-session', reviewer_id='curator', paper_ids=self.ids)
        self.project.evidence.preserve_document(self.ids[0], b'%PDF-1.4\nsynthetic pending', representation='pdf',
            media_type='application/pdf', source_uri='fixture://document', legitimate_basis='synthetic_fixture', resolver='fixture', resolver_version='v1')
        return self.controller.entry()['items'][0]['handle']

    def save(self, fields, *, request_id='save-request-fixture', revision=None, confirm_authority=False, confirm_session_change=False):
        current = self.controller.settings()
        return self.controller.configure(request_id=request_id, project_handle=current['project_handle'],
            revision=revision or current['revision'], fields=fields, confirm_authority=confirm_authority,
            confirm_session_change=confirm_session_change)


class GuidedProjectTests(ProjectFixture):
    def test_entry_and_navigation_create_no_directories_or_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('no external call')):
            data = self.controller.entry()
            self.assertEqual(data['items'], [])
            self.assertEqual(len(data['capabilities']['providers']), 4)
            self.assertEqual(data['capabilities']['resolvers'][0]['id'], 'europepmc')
        self.assertFalse(self.root.exists())

    def test_create_explicit_scope_generated_identity_initial_revision_and_reopen(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('no external call')):
            result = self.create()
        project = self.controller.project()
        self.assertRegex(project.config.project_id, r'^project-[0-9a-f]{32}$')
        self.assertEqual(project.config.review.scope, form()['scope'])
        self.assertEqual(project.config.review.authorized_reviewers, ())
        self.assertEqual(project.config.search[0].aliases, ('invented materials',))
        self.assertEqual(project.config.evidence.resolvers, ('europepmc',))
        self.assertEqual(project.config.providers[1].credential_env, 'CORPUSTRAIL_FIXTURE_KEY')
        self.assertEqual(project.configuration_history()[0]['created_by'], 'researcher')
        self.assertEqual(project.config.config_version, 1)
        self.assertEqual(Project.open(project.root).config, project.config)
        self.assertEqual(result['project_handle'], self.controller.active_handle)

    def test_bootstrap_authority_requires_selected_identity_and_explicit_confirmation(self):
        fields = form(); fields['authorized_reviewers'] = ['researcher']
        with self.assertRaises(ProjectCommandError): self.create(fields=fields)
        self.assertFalse(self.root.exists())
        self.create(fields=fields, confirm_authority=True)
        self.assertEqual(self.controller.project().config.review.authorized_reviewers, ('researcher',))
        self.assertEqual(ProjectReads(self.controller.project()).dashboard()['review']['published_corpus_decisions'], 0)

    def test_invalid_inputs_never_reserve_directory(self):
        for key, bad in [('name', ''), ('description', ''), ('scope', ''), ('reviewer', ''),
                         ('authorized_reviewers', 'researcher'), ('search', [{'label': 'bad'}]),
                         ('resolvers', ['unimplemented']), ('providers', [{'id': 'unimplemented', 'adapter': 'unimplemented', 'credential_env': None}])]:
            fields = form(); fields[key] = bad
            with self.subTest(key=key), self.assertRaises(ProjectCommandError): self.create(fields=fields)
            self.assertFalse(self.root.exists())

    def test_unsupported_secret_field_and_env_values_rejected_redacted(self):
        for secret in ('sk-fixture-secret-value-123456789', 'a-user-only-opaque-secret'):
            fields = form(); fields['description'] = secret
            with patch.dict('os.environ', {'CORPUSTRAIL_FIXTURE_KEY': secret}), self.assertRaises(ProjectCommandError) as error:
                self.create(fields=fields)
            self.assertNotIn(secret, str(error.exception))
            self.assertFalse(self.root.exists())
        fields = form(); fields['api_key'] = 'not-an-allowed-field'
        with self.assertRaises(ProjectCommandError): self.create(fields=fields)

    def test_duplicate_location_no_overwrite_and_request_replay(self):
        first = self.create(); before = fingerprint(self.root)
        self.assertEqual(first, self.create())
        self.assertEqual(before, fingerprint(self.root))
        with self.assertRaises(ProjectCommandError): self.create(request_id='another-create-request')
        fields = form(); fields['name'] = 'Other name'
        with self.assertRaises(ProjectCommandError): self.create(fields=fields)
        self.assertEqual(before, fingerprint(self.root))

    def test_simultaneous_create_is_exclusive_and_retry_safe(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.create(), range(2)))
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(len(self.controller.project().configuration_history()), 1)

    def test_partial_failure_preserves_reserved_files_not_openable_or_overwritten(self):
        def failure(path, *_):
            path.parent.mkdir(parents=True)
            path.write_bytes(b'synthetic partial database')
            raise OSError('private detail not for browser')
        with patch('corpustrail.project.service.create_database', side_effect=failure), self.assertRaises(ProjectCommandError) as error:
            self.create()
        self.assertNotIn('private detail', str(error.exception))
        self.assertFalse((self.root / 'materials/corpustrail.project.json').exists())
        before = fingerprint(self.root)
        with self.assertRaises(ProjectCommandError): self.create()
        self.assertEqual(before, fingerprint(self.root))
        self.assertEqual(self.controller.entry()['items'], [])

    def test_permission_failure_is_redacted_and_no_retry_overwrite(self):
        with patch.object(Project, 'create', side_effect=PermissionError('sensitive OS path')), self.assertRaises(ProjectCommandError) as error:
            self.create()
        self.assertNotIn('sensitive OS path', str(error.exception))
        self.assertFalse(self.root.exists())

    def test_path_traversal_reserved_windows_names_and_symlinks(self):
        for folder in ('../outside', '/outside', '..', 'a/b', 'a\\b', 'CON', 'aux.txt', 'trailing.'):
            with self.subTest(folder=folder), self.assertRaises(ProjectCommandError): self.create(folder=folder)
        self.root.mkdir()
        target = Path(self.temp.name) / 'outside'; target.mkdir()
        (self.root / 'link').symlink_to(target, target_is_directory=True)
        with self.assertRaises(ProjectCommandError): self.create(folder='link')
        with self.assertRaises(ProjectCommandError): ProjectController(projects_root=self.root / 'link')
        self.assertEqual(list(target.iterdir()), [])

    def test_replaced_registered_root_symlink_rejected(self):
        other = Path(self.temp.name) / 'other'; other.mkdir()
        self.root.symlink_to(other, target_is_directory=True)
        with self.assertRaises(ProjectCommandError): self.create()
        self.assertEqual(list(other.iterdir()), [])

    def test_existing_five_paper_open_and_every_read_preserves_fingerprints(self):
        handle = self.existing(); before = fingerprint(self.root)
        with patch('urllib.request.urlopen', side_effect=AssertionError('no external call')), patch.object(Project, 'upgrade', side_effect=AssertionError('no migration')):
            self.controller.open(handle)
            self.controller.settings(); self.controller.entry()
            reads = ProjectReads(self.controller.project())
            dashboard = reads.dashboard(); page = reads.papers(limit=2)
            reads.paper(page['items'][0]['handle']); reads.provenance(page['items'][0]['handle'])
        self.assertEqual(dashboard['papers'], 5)
        self.assertEqual(dashboard['review']['human_reviewed_papers'], 5)
        self.assertEqual(dashboard['review']['published_corpus_decisions'], 0)
        self.assertEqual(before, fingerprint(self.root))

    def test_explicit_launcher_project_outside_root_no_duplicate_database(self):
        external = Project.create(Path(self.temp.name)/'external', ProjectConfig('external','External topic','Invented'), created_by='fixture')
        controller = ProjectController(projects_root=self.root, project=external)
        self.addCleanup(controller.close)
        before = fingerprint(external.root)
        self.assertEqual(controller.project().root, external.root)
        controller.entry(); controller.settings()
        self.assertFalse(self.root.exists())
        self.assertEqual(before, fingerprint(external.root))

    def test_unregistered_handle_cannot_open_arbitrary_filesystem(self):
        for handle in ('/etc/passwd', '../project', 'unregistered'):
            with self.assertRaises(ProjectCommandError): self.controller.open(handle)

    def test_existing_database_symlink_rejected(self):
        handle = self.existing()
        database = self.project.database_path
        moved = Path(self.temp.name)/'moved.sqlite3'; database.rename(moved); database.symlink_to(moved)
        with self.assertRaises(ProjectCommandError): self.controller.open(handle)

    def test_configuration_save_revision_history_and_retry(self):
        self.create(); settings = self.controller.settings(); before = fingerprint(self.controller.project().root)
        fields = settings['fields']; fields['name'] = 'Permitted new name'
        result = self.save(fields, revision=settings['revision'])
        replay = self.save(fields, revision=settings['revision'])
        self.assertEqual(result, replay)
        self.assertEqual(result['version'], 2)
        self.assertEqual(self.controller.project().config.name, fields['name'])
        self.assertEqual(len(self.controller.project().configuration_history()), 2)
        self.assertEqual(before['corpustrail.project.json'], fingerprint(self.controller.project().root)['corpustrail.project.json'])
        fresh = ProjectController(projects_root=self.root)
        self.addCleanup(fresh.close)
        fresh.open(fresh.entry()['items'][0]['handle'])
        self.assertEqual(fresh.settings()['version'], 2)

    def test_stale_or_invalid_save_changes_nothing(self):
        self.create(); current = self.controller.settings(); old = deepcopy(current['fields'])
        fields = deepcopy(old); fields['name'] = 'Changed'
        self.save(fields)
        before = fingerprint(self.root)
        with self.assertRaises(ProjectCommandError) as error: self.save(old, revision=current['revision'], request_id='stale-save-request')
        self.assertEqual(error.exception.code, 'stale_revision')
        bad = deepcopy(fields); bad['resolvers'] = ['unknown-resolver']
        with self.assertRaises(ProjectCommandError): self.save(bad, request_id='invalid-save-request')
        self.assertEqual(before, fingerprint(self.root))

    def test_noop_configuration_save_no_duplicate_events(self):
        self.create(); current = self.controller.settings(); before = fingerprint(self.root)
        result = self.save(current['fields'])
        self.assertFalse(result['changed'])
        self.assertEqual(before, fingerprint(self.root))

    def test_authority_change_requires_explicit_confirmation(self):
        self.create(); fields = self.controller.settings()['fields']; fields['authorized_reviewers'] = ['researcher']
        before = fingerprint(self.root)
        with self.assertRaises(ProjectCommandError): self.save(fields)
        self.assertEqual(before, fingerprint(self.root))
        self.save(fields, confirm_authority=True)
        self.assertEqual(self.controller.project().config.review.authorized_reviewers, ('researcher',))

    def test_sessions_scope_provenance_and_scientific_tables_preserved(self):
        self.controller.open(self.existing())
        self.assertTrue(self.controller.settings()['has_frozen_review_sessions'])
        fields = self.controller.settings()['fields']; fields['name'] = 'Permitted display change'
        prior_view = self.project.review_sessions.view('frozen-session')
        def scientific():
            with connection(self.project.database_path) as db:
                names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('ct_project_config_events','sqlite_sequence')")]
                return {name: [tuple(row) for row in db.execute('SELECT * FROM "'+name+'"')] for name in names}
        before = scientific()
        with self.assertRaises(ProjectCommandError): self.save(fields)
        self.save(fields, confirm_session_change=True)
        self.assertEqual(before, scientific())
        self.assertEqual(prior_view, self.project.review_sessions.view('frozen-session'))
        with self.assertRaises(ContractError):
            self.project.review_sessions.update('frozen-session', expected_revision=None, action='navigate', value='next')
        self.assertEqual(self.project.config.search[0].language, 'fr')
        self.assertEqual(self.project.config.evidence.max_attempts, 2)

    def test_post_authority_scope_changes_still_rejected_even_with_confirmations(self):
        self.controller.open(self.existing())
        pid = self.ids[0]; source = self.project.identities.observations(pid)[0]['source']
        event = ReviewEvent(pid, 'included', 'sufficient', 'metadata', 'Explicit synthetic authorization', 'curator', AT,
            (EvidenceBasis('metadata', source['source_sha256'], source['source_uri'], artifact_validity='verified'),), authority_state='human_authorized')
        self.project.reviews.apply(self.project.reviews.plan(event), recorded_at=AT)
        fields = self.controller.settings()['fields']; fields['scope'] = 'New scope'
        before = fingerprint(self.root)
        with self.assertRaises(ProjectCommandError) as error:
            self.save(fields, confirm_session_change=True, confirm_authority=True)
        self.assertEqual(error.exception.code, 'scope_guard')
        self.assertEqual(before, fingerprint(self.root))

    def test_legacy_absent_scope_not_derived_or_invented(self):
        self.controller.open(self.existing(legacy=True))
        settings = self.controller.settings()
        self.assertFalse(settings['definition']['scope_present']); self.assertEqual(settings['fields']['scope'], '')
        fields = settings['fields']; fields['name'] = 'New display name'
        self.save(fields, confirm_session_change=True)
        self.assertIsNone(self.project.config.review.scope)

    def test_entry_pagination_bounded(self):
        for i in range(4): self.create(folder='topic-'+str(i), request_id='create-topic-request-'+str(i))
        page = self.controller.entry(limit=2)
        self.assertEqual(len(page['items']), 2)
        next_page = self.controller.entry(limit=2, offset=page['next_offset'])
        self.assertEqual(len({p['handle'] for p in page['items']+next_page['items']}), 4)
        self.assertIsNone(next_page['next_offset'])

    def test_packaged_wizard_safe_rendering_no_storage_or_network_assets(self):
        assets = resources.files('corpustrail.local_app').joinpath('assets')
        script = assets.joinpath('projects.js').read_text(encoding='utf-8')
        html = assets.joinpath('projects.html').read_text(encoding='utf-8')
        for forbidden in ('innerHTML', 'localStorage', 'sessionStorage', 'eval(', 'https://', 'http://'):
            self.assertNotIn(forbidden, script)
        self.assertNotRegex(html, r'(?:src|href)="https?://')
        self.assertEqual(len(re.findall('data-step="[0-9]"', html)), 6)
        self.assertIn('X-CorpusTrail-CSRF', script); self.assertIn('textContent', script)
        self.assertNotIn('type="password"', html)

    def test_cli_can_launch_entry_without_project_or_migration(self):
        with patch('corpustrail.local_app.serve') as serve:
            self.assertEqual(main(['app', '--projects-root', str(self.root)]), 0)
        self.assertIsNone(serve.call_args.args[0]); self.assertEqual(serve.call_args.kwargs['projects_root'], self.root)
        self.assertFalse(self.root.exists())

    def test_cli_rejects_symlink_before_project_path_is_resolved(self):
        self.existing()
        before = fingerprint(self.root)
        link = Path(self.temp.name)/'project-link'
        link.symlink_to(self.project.root, target_is_directory=True)
        with patch('corpustrail.local_app.serve') as serve, patch('sys.stderr'):
            self.assertEqual(main(['app', str(link)]), 2)
        serve.assert_not_called()
        self.assertEqual(before, fingerprint(self.root))


class GuidedHttpTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.server = make_server(port=0, controller=self.controller)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        _, html, _ = self.request('GET', '/')
        self.token = re.search('name="corpustrail-session" content="([^"]+)"', html).group(1)

    def request(self, method, path, *, body=None, headers=None, authenticated=False):
        base = {'Origin': self.origin}
        if authenticated: base.update({'X-CorpusTrail-Session': self.token, 'X-CorpusTrail-CSRF': self.token})
        if body is not None: base['Content-Type'] = 'application/json'
        base.update(headers or {})
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            client.request(method, path, body=body, headers=base)
            result = client.getresponse()
            return result.status, result.read().decode(), dict(result.getheaders())
        finally: client.close()

    def payload(self):
        return json.dumps({'schema': SCHEMA, 'request_id': 'http-create-request', 'folder': 'materials', 'fields': form(), 'confirm_authority': False})

    def test_get_wizard_entry_assets_no_filesystem_mutation(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('no network')):
            for route in ('/', '/home', '/projects', '/projects/new', '/assets/projects.js', '/api/v1/projects'):
                self.assertEqual(self.request('GET', route, authenticated=True)[0], 200)
        self.assertFalse(self.root.exists())

    def test_home_workflow_capabilities_and_actions_are_packaged_and_explanatory(self):
        status, html, headers = self.request('GET', '/home')
        self.assertEqual(status, 200)
        self.assertIn('Welcome to CorpusTrail', html)
        self.assertIn('From literature discovery to a curated research corpus.', html)
        self.assertIn('<ol class="workflow"', html)
        self.assertEqual(html.count('class="step-number"'), 7)
        self.assertIn('href="/projects/new">Create New Project', html)
        self.assertIn('href="/projects#open-existing">Open Existing Project', html)
        self.assertIn('Exact-query search available', html)
        self.assertIn('Evidence inspection and eligible Europe PMC retrieval here', html)
        self.assertIn('CSV export and exact ASReview result mapping available', html)
        self.assertIn('Guided human review and explicit corpus publication here', html)
        self.assertIn('fixed candidate sets, human review, reference examples, curation audits', html)
        self.assertIn('RIS bibliography import/export, including available abstracts, is implemented.', html)
        self.assertIn('Other import formats', html)
        self.assertIn('remain separately scoped future work', html)
        self.assertIn('Free, open source and local.', html)
        self.assertIn('Manual review works without a model.', html)
        self.assertIn('ASReview — optional', html)
        self.assertIn('exact identifiers', html)
        self.assertIn('Missing evidence does not mean', html)
        self.assertNotIn('<script', html)  # Static Home makes no API/provider requests.
        self.assertNotRegex(html, r'(?:src|href)="https?://')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])

    def test_home_launch_and_active_project_navigation_direct_launch_compatibility(self):
        _, html, _ = self.request('GET', '/')
        self.assertIn('Welcome to CorpusTrail', html)
        for path in ('/dashboard', '/papers', '/settings'):
            self.assertNotRegex(html, r'<a\b[^>]*href="' + re.escape(path) + '"')
        self.create()
        _, html, _ = self.request('GET', '/')
        self.assertIn('Local project workspace', html)
        self.assertNotIn('Welcome to CorpusTrail', html)
        _, home, _ = self.request('GET', '/home')
        self.assertIn('Welcome to CorpusTrail', home)
        for path in ('/dashboard', '/papers', '/settings'):
            self.assertRegex(home, r'<a\b[^>]*href="' + re.escape(path) + '"')
        for path in ('/projects', '/projects/new', '/settings', '/dashboard', '/papers'):
            _, page, _ = self.request('GET', path)
            self.assertIn('href="/home">Home', page)
            self.assertNotIn('Papers / Corpus', page)

    def test_home_navigation_settings_and_existing_corpus_preserve_five_paper_files(self):
        self.controller.open(self.existing())
        before = fingerprint(self.root)
        with patch('urllib.request.urlopen', side_effect=AssertionError('no external network')), patch.object(Project, 'upgrade', side_effect=AssertionError('no upgrade')):
            for path in ('/home', '/projects', '/settings', '/dashboard', '/papers', '/api/v1/dashboard', '/api/v1/papers', '/api/v1/project-settings'):
                self.assertEqual(self.request('GET', path, authenticated=True)[0], 200)
        self.assertEqual(before, fingerprint(self.root))
        self.assertEqual(len(self.project.reviews.history(self.ids[0])), 1)
        self.assertEqual(ProjectReads(self.project).dashboard()['review']['published_corpus_decisions'], 0)

    def test_home_keeps_host_origin_mutation_and_path_protections(self):
        for headers in ({'Host': 'other.test'}, {'Origin': 'https://other.test'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request('GET', '/home', headers=headers)[0], 403)
        self.assertEqual(self.request('POST', '/home', body='{}', authenticated=True)[0], 405)
        self.assertEqual(self.request('GET', '/home?path=/etc/passwd')[0], 400)
        self.assertEqual(self.request('GET', '/assets/../home.html')[0], 404)
        self.assertFalse(self.root.exists())

    def test_settings_and_wizard_keep_accessible_panels_and_compact_summary(self):
        assets = resources.files('corpustrail.local_app').joinpath('assets')
        html = assets.joinpath('projects.html').read_text(encoding='utf-8')
        css = assets.joinpath('app.css').read_text(encoding='utf-8')
        js = assets.joinpath('projects.js').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'<fieldset data-step="\d" aria-labelledby="section-\d"', html)), 6)
        self.assertNotIn('<legend', html)
        self.assertIn('Discard Changes', html)
        self.assertIn('Configuration information and history', html)
        self.assertIn("make('dl')", js)
        self.assertIn("make('dt', label)", js)
        self.assertIn("make('dd', value)", js)
        self.assertIn('textarea:focus-visible', css)
        self.assertIn('button:focus-visible', css)
        self.assertIn('@media (max-width: 560px)', css)
        self.assertIn('grid-template-columns: minmax(0, 1fr)', css)
        self.assertIn('.section-heading:focus', css)
        self.assertNotIn("legend').focus()", js)

    def test_csrf_origin_host_and_payload_guards(self):
        for headers, auth in [({}, False), ({'X-CorpusTrail-CSRF': 'wrong'}, True),
                              ({'Origin': 'https://other.test'}, True), ({'Origin': ''}, True),
                              ({'Host': 'other.test'}, True), ({'Sec-Fetch-Site': 'cross-site'}, True)]:
            self.assertEqual(self.request('POST', '/api/v1/projects/create', body=self.payload(), headers=headers, authenticated=auth)[0], 403)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.request('POST', '/api/v1/projects/create', body='x'*65537, authenticated=True)[0], 413)
        self.assertEqual(self.request('POST', '/api/v1/projects/create', body=self.payload(), headers={'Content-Type': 'text/plain'}, authenticated=True)[0], 413)
        self.assertFalse(self.root.exists())

    def test_unknown_commands_and_duplicate_json_fields_rejected(self):
        self.assertEqual(self.request('POST', '/api/v1/papers', body='{}', authenticated=True)[0], 405)
        self.assertEqual(self.request('POST', '/api/v1/projects/create', body='{"schema":"'+SCHEMA+'","schema":"'+SCHEMA+'"}', authenticated=True)[0], 400)
        self.assertEqual(self.request('POST', '/api/v1/projects/open', body=json.dumps({'schema':SCHEMA,'path':'/etc/passwd'}), authenticated=True)[0], 400)
        self.assertFalse(self.root.exists())

    def test_complete_http_create_settings_save_reopen_and_no_secret_exposure(self):
        secret = 'opaque-secret-not-for-browser'
        with patch.dict('os.environ', {'CORPUSTRAIL_FIXTURE_KEY': secret}), patch('urllib.request.urlopen', side_effect=AssertionError('no network')):
            status, body, headers = self.request('POST', '/api/v1/projects/create', body=self.payload(), authenticated=True)
            self.assertEqual(status, 200, body); self.assertNotIn('Access-Control-Allow-Origin', headers)
            self.assertNotIn(secret, body)
            _, body, _ = self.request('GET', '/api/v1/project-settings', authenticated=True)
            settings = json.loads(body); fields = settings['fields']; fields['name'] = 'Edited display name'
            payload = json.dumps({'schema':SCHEMA, 'request_id':'http-settings-request', 'project_handle':settings['project_handle'],
                'revision':settings['revision'], 'fields':fields, 'confirm_authority':False, 'confirm_session_change':False})
            status, body, _ = self.request('POST', '/api/v1/project-settings/save', body=payload, authenticated=True)
            self.assertEqual(status, 200, body); self.assertEqual(json.loads(body)['version'], 2)
            self.assertNotIn(secret, json.dumps(fingerprint(self.root)))
            self.assertNotIn(secret, self.controller.project().database_path.read_bytes().decode('latin1'))
            before = fingerprint(self.root)
            for path in ('/settings','/dashboard','/api/v1/dashboard','/api/v1/papers','/api/v1/project-settings','/api/v1/projects'):
                status, body, _ = self.request('GET', path, authenticated=True)
                self.assertEqual(status, 200, body); self.assertNotIn(secret, body)
            self.assertEqual(before, fingerprint(self.root))

    def test_errors_redacted_not_reflecting_untrusted_text(self):
        payload = json.loads(self.payload()); payload['fields']['scope'] = 'Bearer PRIVATE_UNTRUSTED_VALUE'
        status, body, _ = self.request('POST', '/api/v1/projects/create', body=json.dumps(payload), authenticated=True)
        self.assertEqual(status, 400); self.assertNotIn('PRIVATE_UNTRUSTED_VALUE', body)

    def test_invalid_handles_path_queries_and_symlinks_cannot_bypass_controller(self):
        for path in ('/api/v1/projects?path=/etc/passwd', '/api/v1/project-settings?handle=/etc/passwd'):
            self.assertIn(self.request('GET', path, authenticated=True)[0], (400, 409))
        self.assertEqual(self.request('GET', '/assets/../projects.py', authenticated=True)[0], 404)

    @unittest.skipUnless(shutil.which('node'), 'Optional frontend test requires developer Node, not a product dependency')
    def test_synthetic_form_navigation_lost_response_retry_and_settings_using_real_local_api(self):
        # Tiny DOM contract harness: actual packaged JS + actual loopback API.
        # This verifies actions/data, not native browser layout or macOS visuals.
        assets = resources.files('corpustrail.local_app').joinpath('assets')
        html = assets.joinpath('projects.html').read_text(encoding='utf-8')
        script = assets.joinpath('projects.js').read_text(encoding='utf-8')
        other = Project.create(self.root/'other', ProjectConfig('other-ui-fixture', 'Other project', 'Synthetic topic'),
                               created_by='fixture')
        other_before = fingerprint(other.root)
        confirmation_backend = Mock()
        confirmation_backend.capability.return_value = {'available': True, 'reason': ''}
        self.controller.removal().backend = confirmation_backend
        harness = r"""
const assert=require('node:assert/strict'), vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const ids=[...input.html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
const nativeFetch=fetch;
const requests=[]; let loseResponse=true;
async function client(pathname) {
  const nodes=[];
  class Element {
    constructor(tag,id='') { this.tag=tag;this.id=id;this.value='';this.textContent='';this.checked=false;
      this.hidden=false;this.disabled=false;this.required=false;this.children=[];this.dataset={};this.handlers={};nodes.push(this); }
    append(...children) { for(const c of children){c.parent=this;this.children.push(c);} }
    prepend(...children) {for(const c of children)c.parent=this;this.children.unshift(...children);}
    replaceChildren(...children) {for(const c of this.children)c.parent=null;this.children=[];this.append(...children);}
    addEventListener(name,fn) {(this.handlers[name] ||= []).push(fn);}
    setAttribute(name,value) {this[name]=value;}
    reportValidity() {return !this.required || !!this.value.trim();}
    focus() {}
    async emit(name) { const event={preventDefault(){},stopPropagation(){this.stopped=true;}};
      for(const fn of this.handlers[name]||[]) await fn(event);
      if(!event.stopped && this.parent) await this.parent.emit(name); }
  }
  const elements={}; for(const id of ids)elements[id]=new Element('element',id);
  const form=elements['project-form']; for(const e of Object.values(elements))if(e!==form)e.parent=form;
  for(const id of ['name','description','reviewer','folder'])elements[id].required=true;
  const steps=Array.from({length:6},(_,i)=>{const e=new Element('fieldset');e.dataset.step=String(i);return e;});
  const groups=[['name','description','folder'],['scope'],[],[],['reviewer'],['confirm-authority','confirm-sessions']];
  const document={
    getElementById(id){return elements[id]||nodes.find(e=>e.id===id&&connected(e));}, createElement(tag){return new Element(tag);},
    querySelector(s){if(s==='meta[name="corpustrail-session"]')return {content:input.token};
      throw Error(s);},
    querySelectorAll(s){if(s==='[data-step]')return steps;
      const kind=s.match(/data-kind="(\w+)"/);if(kind)return nodes.filter(e=>e.dataset.kind===kind[1]&&connected(e));
      const group=s.match(/data-step="(\d)"/);if(group)return groups[Number(group[1])].map(id=>elements[id]);
      throw Error(s);}
  };
  function connected(e){while(e){if(e===form)return true;e=e.parent;}return false;}
  const location={pathname, assign(target){location.target=target;}};
  const context={document,location,crypto:require('node:crypto').webcrypto,console,
    fetch:async(path,options)=>{requests.push({path,options});
      const response=await nativeFetch(input.origin+path,{...options,headers:{...options.headers,Origin:input.origin}});
      if(path.endsWith('/create')&&loseResponse){loseResponse=false;await response.text();throw Error('Simulated response loss');}
      return response;}};
  vm.createContext(context);vm.runInContext(input.script,context);
  async function ready(){for(let i=0;i<200;i++){
    if(pathname==='/projects' ? !!elements['root-location'].textContent : !elements.setup.hidden&&elements.progress.textContent) return;
    await new Promise(r=>setTimeout(r,10));}throw Error('page not ready');}
  // Hidden defaults from packaged HTML; initialize makes setup visible.
  elements.setup.hidden=true;
  await ready();
  const set=async(id,value)=>{elements[id].value=value;await elements[id].emit('input');};
  return {elements,nodes,location,set,steps,context,next:async()=>elements.next.onclick(),submit:async()=>form.emit('submit')};
}
(async()=>{
  const c=await client('/projects/new');
  await c.set('name','Five-paper researcher test'); await c.set('description','Invented topic');
  await c.next();await c.set('scope','Broad invented corpus, not review eligibility');await c.next();
  c.nodes.find(e=>e.dataset.kind==='provider'&&e.value==='crossref').checked=true;
  await c.set('concepts','Synthetic topic');await c.next();
  c.nodes.find(e=>e.dataset.kind==='resolver'&&e.value==='europepmc').checked=true;
  await c.next();await c.set('reviewer','researcher');await c.next();
  assert.equal(c.elements.progress.textContent,'Step 6 of 6');
  assert.equal(c.elements.summary.children[0].tag,'dl');
  assert.equal(c.elements.summary.children[0].children.length,18);
  assert.equal(requests.filter(r=>r.options.method==='POST').length,0);
  assert.equal(c.elements['authority-confirmation'].hidden,true);
  await c.submit(); assert.match(c.elements.message.textContent,/response loss/);
  await c.submit(); assert.equal(c.location.target,'/dashboard#created');
  const creates=requests.filter(r=>r.path.endsWith('/create'));
  assert.equal(creates.length,2);assert.equal(creates[0].options.body,creates[1].options.body);
  const creation=JSON.parse(creates[0].options.body);
  assert.deepEqual(creation.fields.authorized_reviewers,[]);assert.equal(creation.confirm_authority,false);
  const s=await client('/settings');
  assert.equal(s.elements.name.value,'Five-paper researcher test');
  assert(s.steps.every(group=>!group.hidden));
  assert(s.elements.back.hidden&&s.elements.next.hidden&&!s.elements.save.hidden);
  assert.equal(s.elements['project-form'].children[0],s.elements['save-actions']);
  assert.equal(s.elements['return-link'].href,'/dashboard');
  const initial=JSON.parse(vm.runInContext('JSON.stringify(fields())',s.context));
  await s.set('description','Discard this unsaved edit');
  assert.match(s.elements['saved-status'].textContent,/Unsaved changes/);
  s.elements.discard.onclick();assert.equal(s.elements.description.value,'Invented topic');
  assert.match(s.elements['saved-status'].textContent,/No unsaved changes/);
  await s.submit(); assert.equal(requests.filter(r=>r.path.endsWith('/save')).length,0);
  await s.set('reviewer','different-pseudonym');await s.submit();
  assert.match(s.elements.message.textContent,/pseudonym-only/);
  assert.equal(requests.filter(r=>r.path.endsWith('/save')).length,0);s.elements.discard.onclick();
  await s.set('description','Updated invented research topic');
  assert.equal(s.elements['scope-confirmation'].hidden,true);
  assert.equal(s.elements['session-confirmation'].hidden,true);
  await s.submit();
  assert.match(s.elements.message.textContent,/version 2/);
  const saves=requests.filter(r=>r.path.endsWith('/save'));assert.equal(saves.length,1);
  const body=JSON.parse(saves[0].options.body);assert.equal(body.fields.providers[0].adapter,'crossref');
  assert.deepEqual(body.fields,{...initial,description:'Updated invented research topic'});
  assert.deepEqual(body.fields.authorized_reviewers,[]);
  const reopened=await client('/projects');
  const cards=reopened.elements['project-list'].children;
  const active=cards.find(e=>e.className.includes('active-project'));
  const actions=card=>card.children.find(e=>e.className==='project-actions').children;
  assert.equal(cards.length,2);assert(active);
  assert.equal(active.children[0].children[1].textContent,'Active project');
  const close=actions(active).find(e=>e.textContent==='Close Project');assert(close&&!close.disabled);
  assert(actions(active).find(e=>e.textContent==='Move to Trash…').disabled);
  assert.match(active.children.at(-1).textContent,/Other processes/);
  assert(!cards.filter(e=>e!==active).some(e=>actions(e).some(b=>b.textContent==='Close Project')));
  const removalBefore=requests.filter(r=>r.path.includes('/trash/')).length;
  await close.onclick();assert.equal(reopened.location.target,'/projects');
  const closed=await client('/projects');
  assert.equal(closed.elements['project-list'].children.length,2);
  assert(!closed.elements['project-list'].children.some(e=>e.className.includes('active-project')));
  assert(!closed.elements['project-list'].children.some(e=>actions(e).some(b=>b.textContent==='Close Project')));
  assert.equal(requests.filter(r=>r.path.includes('/trash/')).length,removalBefore);
  assert.equal(requests.filter(r=>r.path.endsWith('/close')).length,1);
  const selected=closed.elements['project-list'].children[0];
  await actions(selected).find(e=>e.textContent==='Move to Trash…').onclick();
  assert.equal(closed.elements['trash-confirmation'].hidden,false);
  assert.equal(closed.elements['trash-name'].textContent,'Five-paper researcher test');
  assert.equal(closed.elements['trash-location'].textContent,selected.children[1].textContent);
  assert.equal(closed.elements['trash-execute'].disabled,true);
  await closed.set('trash-folder','incorrect-name');assert.equal(closed.elements['trash-execute'].disabled,true);
  await closed.set('trash-folder',closed.elements['trash-folder-name'].textContent);
  assert.equal(closed.elements['trash-execute'].disabled,false);
  await closed.elements['trash-cancel'].onclick();
  assert.equal(closed.elements['trash-confirmation'].hidden,true);
  assert.equal(closed.elements['project-list'].children.length,2);
  assert.equal(requests.filter(r=>r.path.endsWith('/trash/execute')).length,0);
  const open=actions(closed.elements['project-list'].children[0]).find(e=>e.textContent==='Open Project');
  await open.onclick();assert.equal(closed.location.target,'/dashboard');
  const persisted=await client('/settings');
  assert.equal(persisted.elements.description.value,'Updated invented research topic');
  assert(s.steps.every(group=>!group.hidden));
  await s.set('scope','Different broad topic');await s.submit();
  assert.match(s.elements.message.textContent,/Confirm the broad-corpus definition/);
  assert.equal(requests.filter(r=>r.path.endsWith('/save')).length,1);s.elements.discard.onclick();
  await s.set('authorized-reviewers','curator');await s.submit();
  assert.match(s.elements.message.textContent,/Confirm the displayed authority/);
  assert.equal(requests.filter(r=>r.path.endsWith('/save')).length,1);s.elements.discard.onclick();
  vm.runInContext('settingsData.has_frozen_review_sessions = true',s.context);
  await s.set('description','A further edit');await s.submit();
  assert.match(s.elements.message.textContent,/Confirm the review-session safeguard/);
  assert.equal(requests.filter(r=>r.path.endsWith('/save')).length,1);s.elements.discard.onclick();
  // A second tab stays revision-pinned; no silent overwrite after another save.
  vm.runInContext('settingsData.has_frozen_review_sessions = false',s.context);
  const stale=await client('/settings');
  await s.set('name','Updated researcher test');await s.submit();
  await stale.set('description','A stale edit');await stale.submit();
  assert.match(stale.elements.message.textContent,/changed in another window/);
  // Existing adapter aliases, resolver order and uneditable/custom entries are
  // read-model data, not a reason to reconstruct unrelated configuration.
  vm.runInContext(`settingsData.fields.providers = [
    {id:'custom-provider',adapter:'custom',credential_env:null},
    {id:'alex-primary',adapter:'openalex',credential_env:'FIXTURE_PRIMARY'},
    {id:'alex-secondary',adapter:'openalex',credential_env:'FIXTURE_SECONDARY'},
    {id:'crossref',adapter:'crossref',credential_env:null}];
    settingsData.fields.resolvers = ['custom-resolver','europepmc']; populateSettings();`,stale.context);
  const restored=JSON.parse(vm.runInContext('JSON.stringify(fields())',stale.context));
  const prior=JSON.parse(vm.runInContext('JSON.stringify(settingsData.fields)',stale.context));
  assert.deepEqual(restored,prior);
  for(const r of requests) assert.ok(r.path.startsWith('/api/v1/'));
  console.log('Synthetic wizard, direct settings, discard/no-op, confirmations, stale-write and retry tests passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps({'html': html, 'script': script,
            'origin': self.origin, 'token': self.token}), text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('passed', result.stdout)
        project = self.controller.project()
        self.assertEqual(project.config.name, 'Updated researcher test')
        self.assertEqual(project.config.description, 'Updated invented research topic')
        self.assertEqual(len(project.configuration_history()), 3)
        self.assertEqual(project.config.review.authorized_reviewers, ())
        self.assertEqual(other_before, fingerprint(other.root))
        confirmation_backend.move.assert_not_called()


if __name__ == '__main__':
    unittest.main()
