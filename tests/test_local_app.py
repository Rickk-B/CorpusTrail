"""Read-only application contracts, synthetic data and offline loopback only."""

from dataclasses import asdict
import hashlib
import http.client
from importlib import resources
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from corpustrail.application import ProjectReads
from corpustrail.application.reads import StaleCursor
from corpustrail._internal.database import connection
from corpustrail._internal.pipeline import append, preserve
from corpustrail._internal.values import canonical, content_hash, identifier
from corpustrail.curation import ReviewEvent, EvidenceBasis
from corpustrail.discovery import CandidateObservation, DiscoveryPage
from corpustrail.identity import BibliographicRecord, SourceReference, Identifier
from corpustrail.local_app import make_server
from corpustrail.project import Project, ProjectConfig, ReviewPolicy, ProviderConfig, EvidencePolicy

AT = '2026-01-01T00:00:00+00:00'


def fingerprints(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class AppFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'topic'
        self.project = Project.create(self.root, ProjectConfig('app-fixture', 'Materials catalogue',
            'Invented materials fixtures', providers=(ProviderConfig('crossref', 'crossref'),),
            review=ReviewPolicy(scope='Broad materials research', authorized_reviewers=('curator',)),
            evidence=EvidencePolicy(resolvers=('europepmc',))), created_by='fixture', created_at=AT)
        self.ids = [self.enroll(i) for i in range(5)]
        self.reads = ProjectReads(self.project)

    def enroll(self, i, *, title=None, year=None, abstract=True):
        record = BibliographicRecord(title if title is not None else ('Duplicate title' if i < 2 else 'Paper '+str(i)),
            'Invented abstract '+str(i) if abstract else None, ('Fixture author',), year or 2020+i,
            'Fixture journal', (Identifier('doi', '10.1234/app.'+str(i)),) if i != 1 else ())
        body = canonical({'fixture': i}).encode()
        source = SourceReference('fixture://private-query/'+str(i), str(i),
            'sha256:'+hashlib.sha256(body).hexdigest(), len(body), 'fixture_source', AT, identity_status='verified')
        return self.project.identities.apply(self.project.identities.plan(record, source),
            approve_new_identity=True, approve_aliases=True)

    def handle(self, index):
        return self.ids[index].split(':', 1)[1]

    def label(self, index, state, *, authoritative=True, producer='human'):
        pid = self.ids[index]
        source = self.project.identities.observations(pid)[0]['source']
        event = ReviewEvent(pid, state, 'insufficient' if state == 'insufficient_evidence' else 'sufficient',
            'metadata', 'Invented rationale', 'curator' if producer == 'human' else 'fixture_engine', AT,
            (EvidenceBasis('metadata', source['source_sha256'], source['source_uri'], artifact_validity='verified'),),
            authority_state='human_authorized' if authoritative else 'non_authoritative', producer_type=producer,
            supersedes=self.project.reviews.membership(pid)['current_event_id'] if authoritative else None)
        self.project.reviews.apply(self.project.reviews.plan(event), recorded_at=AT)

    def document(self, index, *, kind='verified'):
        body = (b'%PDF-1.4\nsynthetic pending' if kind == 'pending' else
            b'not xml' if kind == 'invalid' else
            ('<article><front><article-meta><article-id pub-id-type="doi">'+
             ('10.1234/wrong' if kind == 'mismatch' else '10.1234/app.'+str(index))+
             '</article-id></article-meta></front><body><p>Invented trusted measurement.</p></body></article>').encode())
        return self.project.evidence.preserve_document(self.ids[index], body,
            representation='pdf' if kind == 'pending' else 'jats_xml',
            media_type='application/pdf' if kind == 'pending' else 'application/xml',
            source_uri='fixture://document/'+kind, legitimate_basis='synthetic_fixture',
            resolver='fixture', resolver_version='v1', created_at=AT)


class ReadModelTests(AppFixture):
    def test_dashboard_membership_review_evidence_and_services(self):
        self.label(0, 'included'); self.label(1, 'excluded'); self.label(2, 'insufficient_evidence')
        self.label(3, 'included', authoritative=False)
        self.label(4, 'excluded', authoritative=False, producer='model')
        self.document(0); self.document(1, kind='pending'); self.document(2, kind='mismatch')
        self.project.review_sessions.prepare('draft-session', reviewer_id='curator', paper_ids=self.ids)
        self.project.review_sessions.update('draft-session', expected_revision=None, action='draft',
            value={'sufficiency': 'sufficient', 'decision': 'included', 'review_extent': 'metadata', 'rationale': 'Synthetic'})
        data = self.reads.dashboard()
        self.assertEqual(data['papers'], 5)
        self.assertEqual(data['project']['broad_corpus_definition'], 'Broad materials research')
        self.assertEqual(data['membership'], {'included': 1, 'excluded': 1, 'insufficient_evidence': 1, 'unresolved': 0, 'not_reviewed': 2})
        self.assertEqual(data['review']['human_reviewed_papers'], 4)
        self.assertEqual(data['review']['published_corpus_decisions'], 3)
        self.assertEqual(data['review']['sessions'], 1)
        self.assertEqual(data['review']['papers_with_draft_history'], 1)
        self.assertEqual(data['evidence']['verified_structured_text_papers'], 1)
        self.assertEqual(data['evidence']['pending_document_papers'], 1)
        self.assertEqual(data['evidence']['mismatch_or_invalid_papers'], 1)
        self.assertEqual(data['providers'], ['crossref']); self.assertEqual(data['resolvers'], ['europepmc'])

    def test_five_recorded_reviews_without_published_membership(self):
        for index in range(5): self.label(index, 'included', authoritative=False)
        before = fingerprints(self.root)
        dashboard = self.reads.dashboard()
        self.assertEqual(dashboard['review']['human_reviewed_papers'], 5)
        self.assertEqual(dashboard['review']['published_corpus_decisions'], 0)
        self.assertEqual(dashboard['membership']['not_reviewed'], 5)
        for paper in self.reads.papers()['items']:
            self.assertEqual(paper['membership'], {'state': 'not_reviewed', 'authority_state': 'none'})
            self.assertEqual(paper['review']['human_observations'], 1)
        self.assertEqual(before, fingerprints(self.root))

    def test_scholarly_identifiers_normal_provider_identifiers_advanced_only(self):
        record = BibliographicRecord('Exact identifier fixture', identifiers=(
            Identifier('doi', '10.1234/app.0'), Identifier('pmid', '12345'),
            Identifier('pmcid', 'PMC12345'), Identifier('openalex', 'W12345')))
        source = SourceReference('fixture://identifiers', 'ids', 'sha256:'+'9'*64, 0, 'fixture', AT,
                                 identity_status='verified')
        self.project.identities.apply(self.project.identities.plan(record, source), approve_aliases=True)
        before = fingerprints(self.root)
        for paper in (self.reads.paper(self.handle(0))['paper'],
                      next(x for x in self.reads.papers()['items'] if x['handle'] == self.handle(0))):
            self.assertEqual({x['scheme'] for x in paper['identifiers']}, {'doi', 'pmid', 'pmcid'})
            self.assertNotIn('W12345', json.dumps(paper))
        advanced = self.reads.provenance(self.handle(0))
        self.assertIn('openalex', {x['scheme'] for x in advanced['summary']['identifiers']})
        self.assertIn('W12345', json.dumps(advanced))
        self.assertEqual(before, fingerprints(self.root))

    def test_page_joins_match_shared_scientific_services(self):
        self.label(0, 'included'); self.label(1, 'excluded'); self.document(0)
        for item in self.reads.papers()['items']:
            pid = 'ct-paper:' + item['handle']
            metadata = self.project.discovery.metadata(pid)
            self.assertEqual(item['bibliography'], {k: metadata['fields'][k] for k in ('title', 'authors', 'year', 'source')})
            self.assertEqual(item['membership']['state'], self.project.reviews.membership(pid)['state'])
            self.assertEqual(item['evidence']['best_available'], self.project.evidence.status(pid)['best_available'])
            self.assertEqual(item['sources'], ['fixture_source'])

    def test_duplicate_titles_and_missing_metadata(self):
        empty = BibliographicRecord()
        source = SourceReference('fixture://empty', 'empty', 'sha256:'+'1'*64, 0, 'fixture', AT)
        pid = self.project.identities.apply(self.project.identities.plan(empty, source), approve_new_identity=True)
        items = self.reads.papers()['items']
        duplicates = [x for x in items if x['bibliography']['title'] == 'Duplicate title']
        self.assertEqual(len(duplicates), 2); self.assertNotEqual(duplicates[0]['handle'], duplicates[1]['handle'])
        self.assertEqual(items[-1]['handle'], pid.split(':')[1])
        self.assertIsNone(items[-1]['bibliography']['title'])
        self.assertEqual(items[-1]['bibliography']['authors'], [])
        self.assertEqual(items[-1]['evidence']['best_available'], 'metadata')

    def test_canonical_sort_filter_uses_selected_value_not_provider_precedence(self):
        record = BibliographicRecord('Earlier canonical title', year=1900, identifiers=(Identifier('doi', '10.1234/app.0'),))
        source = SourceReference('fixture://earlier', 'record', 'sha256:'+'2'*64, 0, 'other_provider',
            '1900-01-01T00:00:00+00:00', identity_status='verified')
        self.project.identities.apply(self.project.identities.plan(record, source), approve_aliases=True)
        found = self.reads.papers(q='earlier')['items']
        self.assertEqual(len(found), 1); self.assertEqual(found[0]['bibliography']['title'], record.title)
        self.assertEqual(self.reads.papers(sort='year_oldest')['items'][0]['handle'], self.handle(0))
        self.assertEqual(self.reads.provenance(self.handle(0))['total'], 2)

    def test_literal_brackets_are_not_missing_title(self):
        self.enroll(9, title='[]')
        page = self.reads.papers(q='[]')
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['items'][0]['bibliography']['title'], '[]')

    def test_each_advanced_section_and_identifier_source_lineage(self):
        self.label(0, 'included'); self.document(0)
        for section in ('bibliography', 'reviews', 'representations', 'identifiers', 'provider'):
            result = self.reads.provenance(self.handle(0), section=section, limit=1)
            self.assertEqual(result['section'], section)
            self.assertLessEqual(len(result['items']), 1)
        identifier_row = self.reads.provenance(self.handle(0), section='identifiers')['items'][0]
        self.assertEqual(identifier_row['raw_value'], '10.1234/app.0')
        self.assertEqual(identifier_row['provider'], 'fixture_source')
        self.assertTrue(identifier_row['supporting_assertion'])

    def test_stable_pagination_no_duplicate_or_missing_papers(self):
        page = self.reads.papers(limit=2)
        first = page
        handles = []
        while True:
            handles += [x['handle'] for x in page['items']]
            if page['next_cursor'] is None: break
            page = self.reads.papers(limit=2, cursor=page['next_cursor'])
        self.assertEqual(len(handles), 5); self.assertEqual(len(set(handles)), 5)
        second = self.reads.papers(limit=2, cursor=first['next_cursor'])
        self.assertEqual(self.reads.papers(limit=2, cursor=second['previous_cursor']), first)

    def test_stale_and_foreign_or_changed_filter_cursor_rejected(self):
        cursor = self.reads.papers(limit=2)['next_cursor']
        with self.assertRaises(ValueError): self.reads.papers(limit=2, cursor=cursor, q='different')
        self.label(0, 'included')
        with self.assertRaises(StaleCursor): self.reads.papers(limit=2, cursor=cursor)
        with self.assertRaises(ValueError): self.reads.papers(cursor='not-a-cursor')

    def test_filters_sort_unicode_and_validation(self):
        self.label(0, 'included'); self.label(1, 'insufficient_evidence')
        self.document(0); self.document(1, kind='pending')
        self.enroll(8, title='Älpha 材料', abstract=False)
        self.assertEqual(self.reads.papers(q='älPHA')['total'], 1)
        self.assertEqual(self.reads.papers(q='材料')['total'], 1)
        self.assertEqual(self.reads.papers(q="' OR 1=1 --")['total'], 0)
        self.assertEqual(self.reads.papers(membership='included')['total'], 1)
        self.assertEqual(self.reads.papers(review='human_reviewed')['total'], 2)
        self.assertEqual(self.reads.papers(evidence='structured_text')['total'], 1)
        self.assertEqual(self.reads.papers(evidence='pending')['total'], 1)
        self.assertEqual(self.reads.papers(sort='year_newest')['items'][0]['bibliography']['year'], 2028)
        for kwargs in ({'sort': 'paper_id;DELETE'}, {'membership': 'model_included'}, {'limit': 101}, {'limit': True}, {'q': 'x'*301}):
            with self.assertRaises(ValueError): self.reads.papers(**kwargs)

    def test_evidence_pending_mismatch_invalid_and_verified_body_access(self):
        for i, kind in enumerate(('verified', 'pending', 'mismatch', 'invalid')): self.document(i, kind=kind)
        paper = self.reads.paper(self.handle(0))['paper']
        readable = next(x for x in paper['representations'] if x['readable'])
        doc = self.reads.document(self.handle(0), readable['handle'], limit=8)
        self.assertEqual(len(doc['text']), 8); self.assertIsNotNone(doc['next_offset'])
        for i in (1, 2, 3):
            rep = self.reads.paper(self.handle(i))['paper']['representations'][0]
            self.assertFalse(rep['readable'])
            with self.assertRaises(ValueError): self.reads.document(self.handle(i), rep['handle'])
        with self.assertRaises(KeyError): self.reads.document(self.handle(1), readable['handle'])

    def test_read_models_exclude_raw_payload_paths_queries_and_judgments(self):
        self.label(0, 'included', authoritative=False, producer='model')
        blob = json.dumps([self.reads.dashboard(), self.reads.papers(), self.reads.paper(self.handle(0))])
        for forbidden in ('raw_record', 'response_sha256', 'source_uri', 'private-query', 'rationale', 'producer_id', 'settings', 'ct-paper:'):
            self.assertNotIn(forbidden, blob)
        self.assertEqual(self.reads.paper(self.handle(0))['paper']['membership']['state'], 'not_reviewed')
        advanced = self.reads.provenance(self.handle(0), section='reviews')
        self.assertEqual(advanced['items'][0]['record']['producer_type'], 'model')

    def test_raw_provider_observation_only_in_explicit_advanced_view(self):
        class Provider:
            name = 'crossref'; version = 'fixture/v1'; network = False
            hosts = ('api.crossref.org',)
            def request(self, plan, cursor):
                from corpustrail.discovery import RequestSpec
                return RequestSpec('https://api.crossref.org/fixture')
            def normalize(self, body, plan, cursor):
                return DiscoveryPage((CandidateObservation('fixture-record', BibliographicRecord('Provider title',
                    identifiers=(Identifier('doi', '10.1234/app.0'),)), {'private_query': 'hidden', 'raw': True}),))
        class Transport:
            network = False
            def request(self, *args, **kwargs):
                from corpustrail.providers.network import HttpResponse
                return HttpResponse(200, {}, b'{}', args[0])
        provider = Provider()
        plan = self.project.discovery.plan(provider, run_id='fixture-provider', query='private search')
        self.project.discovery.execute(plan, provider, transport=Transport())
        self.project.discovery.canonicalize(plan.run_id, approve_new_identities=True, approve_aliases=True)
        self.assertNotIn('private search', json.dumps(self.reads.paper(self.handle(0))))
        provenance = self.reads.provenance(self.handle(0), section='provider', limit=1)
        self.assertEqual(provenance['items'][0]['record']['payload']['query'], 'private search')
        self.assertTrue(provenance['items'][0]['record']['payload']['raw_record']['raw'])

    def test_reads_no_mutation_or_network_and_deterministic(self):
        self.document(0); self.document(1, kind='pending'); self.label(0, 'included')
        before = fingerprints(self.root)
        with patch('urllib.request.urlopen', side_effect=AssertionError('no external request')):
            for _ in range(2):
                self.assertEqual(self.reads.dashboard(), self.reads.dashboard())
                self.assertEqual(self.reads.papers(), self.reads.papers())
                self.reads.paper(self.handle(0)); self.reads.provenance(self.handle(0))
        self.assertEqual(fingerprints(self.root), before)

    def test_method_blind_review_boundary_stays_separate(self):
        self.label(0, 'included', authoritative=False, producer='model')
        self.project.review_sessions.prepare('blind', reviewer_id='curator', paper_ids=[self.ids[0]])
        view = self.project.review_sessions.view('blind')
        for key in ('membership', 'sources', 'priority', 'provenance', 'other_observations'):
            self.assertNotIn(key, view)
        self.assertNotIn('fixture_engine', json.dumps(view))
        self.assertEqual(self.reads.paper(self.handle(0))['mode'], 'operational_read_only')

    def test_paths_and_untrusted_artifact_never_served(self):
        for handle in ('../secret', '/etc/passwd', self.ids[0], 'x'*64):
            with self.assertRaises(ValueError): self.reads.paper(handle)
        self.document(0)
        rep = next(x for x in self.reads.paper(self.handle(0))['paper']['representations'] if x['readable'])
        with connection(self.project.database_path) as db:
            path = self.root / db.execute('SELECT relative_path FROM ct_artifact_files WHERE sha256=?',
                (self.reads.document(self.handle(0), rep['handle'])['source_sha256'],)).fetchone()[0]
        path.unlink(); path.symlink_to(Path(self.temp.name)/'outside')
        (Path(self.temp.name)/'outside').write_text('PRIVATE OUTSIDE', encoding='utf-8')
        with self.assertRaises(ValueError): self.reads.document(self.handle(0), rep['handle'])

    def test_large_catalogue_bounded_page_and_server_side_query(self):
        # Direct valid synthetic fixture rows, not a production import API. Avoid
        # measuring the enrollment service's unrelated per-write snapshot costs.
        count = 20000
        with connection(self.project.database_path, write=True) as db:
            config_id = self.project.configuration_history()[-1]['event_id']
            for i in range(count):
                pid = identifier('ct-paper', ['large-fixture', i]); plan_id = identifier('enroll', i)
                source = SourceReference('fixture://large', str(i), 'sha256:'+'3'*64, 0, 'fixture', AT)
                record = BibliographicRecord('Synthetic catalogue '+str(i).zfill(5), year=2000)
                db.execute('INSERT OR IGNORE INTO raw_artifacts VALUES (?,?,?,?)', (source.source_sha256, 'application/json', 0, AT))
                db.execute("INSERT INTO paper_entities VALUES (?,?,?,'active',NULL)", (pid, AT, 'fixture'))
                db.execute('INSERT INTO ct_enrollment_operations VALUES (?,?,?,?)', (plan_id, pid, '{}', config_id))
                db.execute('INSERT INTO ct_paper_observations VALUES (?,?,?,?,?)',
                    (identifier('bibliography', i), pid, plan_id, source.source_sha256, canonical({'record': asdict(record), 'source': asdict(source)})))
        with patch.object(self.reads, '_row', wraps=self.reads._row) as row:
            page = self.reads.papers(q='Synthetic catalogue', limit=25)
            self.assertEqual(page['total'], count); self.assertEqual(row.call_count, 25)
            self.assertEqual(len(page['items']), 25)
            self.assertLess(len(json.dumps(page)), 60000)
            next_page = self.reads.papers(q='Synthetic catalogue', limit=25, cursor=page['next_cursor'])
            self.assertEqual(next_page['items'][0]['bibliography']['title'], 'Synthetic catalogue 00025')

    def test_packaged_assets_and_no_browser_html_or_secret_storage(self):
        assets = resources.files('corpustrail.local_app').joinpath('assets')
        script = assets.joinpath('app.js').read_text(encoding='utf-8')
        html = assets.joinpath('index.html').read_text(encoding='utf-8')
        for name in ('index.html', 'app.js', 'app.css'): self.assertTrue(assets.joinpath(name).is_file())
        for forbidden in ('innerHTML', 'localStorage', 'sessionStorage', 'eval(', 'http://', 'https://'):
            self.assertNotIn(forbidden, script)
        self.assertIn('textContent', script)
        self.assertNotIn('Record human decision', html)
        self.assertNotIn('Save & Next', html)
        self.assertIn('Read-only', html)

    def test_progressive_disclosure_accessibility_and_single_evidence_summary(self):
        html = resources.files('corpustrail.local_app').joinpath('assets/index.html').read_text(encoding='utf-8')
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__(); self.entries = []
            def handle_starttag(self, tag, attrs):
                self.entries.append((tag, dict(attrs)))
        parser = Tags(); parser.feed(html)
        by_id = {attrs['id']: (tag, attrs) for tag, attrs in parser.entries if 'id' in attrs}
        for key in ('advanced', 'lineage-details', 'raw-details', 'dashboard-details'):
            self.assertEqual(by_id[key][0], 'details')
            self.assertNotIn('open', by_id[key][1])
        self.assertLess(html.index('Technical identifiers'), html.index('Show detailed lineage'))
        self.assertLess(html.index('Show detailed lineage'), html.index('Show raw JSON'))
        self.assertIn('not a method-blind review view', html)
        self.assertNotIn('detail-evidence', by_id)
        self.assertEqual(sum(attrs.get('id') == 'paper-status' for _, attrs in parser.entries), 1)
        self.assertEqual(by_id['search'][1]['placeholder'], 'Search title, author or journal')
        self.assertIn('<label>Search papers', html)
        self.assertIn('Sort by', html); self.assertIn('Results per page', html)
        self.assertIn('summary', {tag for tag, _ in parser.entries})


class HttpReadTests(AppFixture):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.project, port=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        code, body, _ = self.request('GET', '/')
        self.assertEqual(code, 200)
        self.token = re.search('name="corpustrail-session" content="([^"]+)"', body).group(1)

    def request(self, method, path, *, headers=None, body=None, authenticated=False):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            headers = dict(headers or {})
            if authenticated: headers['X-CorpusTrail-Session'] = self.token
            client.request(method, path, body=body, headers=headers)
            response = client.getresponse()
            return response.status, response.read().decode(), dict(response.getheaders())
        finally: client.close()

    def test_get_workflow_and_byte_identical_project(self):
        self.document(0); self.document(1, kind='pending'); self.label(0, 'included')
        before = fingerprints(self.root)
        for path in ('/dashboard', '/papers', '/papers/'+self.handle(0), '/assets/app.js', '/assets/app.css'):
            self.assertEqual(self.request('GET', path)[0], 200)
        for path in ('/api/v1/dashboard', '/api/v1/papers?limit=2', '/api/v1/papers/'+self.handle(0),
                     '/api/v1/papers/'+self.handle(0)+'/provenance'):
            code, body, _ = self.request('GET', path, authenticated=True)
            self.assertEqual(code, 200, body)
        self.assertEqual(before, fingerprints(self.root))

    def test_loopback_host_origin_and_api_session_gate(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        self.assertEqual(self.request('GET', '/', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.request('GET', '/api/v1/dashboard')[0], 403)
        self.assertEqual(self.request('GET', '/api/v1/dashboard', authenticated=True)[0], 200)

    def test_mutations_rejected_even_with_token_and_csrf(self):
        before = fingerprints(self.root)
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD', 'TRACE', 'CONNECT'):
            status, _, headers = self.request(method, '/api/v1/papers', authenticated=True,
                headers={'X-CorpusTrail-CSRF': self.token}, body='{}')
            self.assertEqual(status, 405); self.assertEqual(headers['Allow'], 'GET')
        self.assertEqual(before, fingerprints(self.root))

    def test_no_filesystem_routes_or_unversioned_rich_review(self):
        for path in ('/assets/../server.py', '/assets/%2e%2e/server.py', '/api/state', '/api/v1/review', '/document?path=/etc/passwd'):
            self.assertEqual(self.request('GET', path, authenticated=True)[0], 404)
        self.assertEqual(self.request('GET', '/api/v1/papers?path=/etc/passwd', authenticated=True)[0], 400)
        self.assertEqual(self.request('GET', '/api/v1/papers?limit=1&limit=2', authenticated=True)[0], 400)

    def test_csp_and_no_scientific_text_in_html_shell(self):
        self.enroll(9, title='<script>window.bad=true</script>')
        code, html, headers = self.request('GET', '/')
        self.assertEqual(code, 200); self.assertNotIn('window.bad', html)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        _, body, _ = self.request('GET', '/api/v1/papers?q=window.bad', authenticated=True)
        self.assertIn('<script>', body)  # Preserved data, rendered only by textContent.

    def test_pending_document_api_denied_and_stale_cursor_http_409(self):
        self.document(0, kind='pending')
        rep = self.reads.paper(self.handle(0))['paper']['representations'][0]
        self.assertEqual(self.request('GET', '/api/v1/papers/'+self.handle(0)+'/evidence/'+rep['handle'], authenticated=True)[0], 400)
        page = self.reads.papers(limit=2)
        self.label(0, 'included')
        from urllib.parse import urlencode
        path = '/api/v1/papers?' + urlencode({'limit': 2, 'cursor': page['next_cursor']})
        self.assertEqual(self.request('GET', path, authenticated=True)[0], 409)

    def test_cli_launch_delegates_without_status_scan_or_review_mutation(self):
        from corpustrail.cli import main
        with patch('corpustrail.local_app.serve') as serve, patch.object(Project, 'status', side_effect=AssertionError('no full status scan')):
            self.assertEqual(main(['app', str(self.root), '--port', '0']), 0)
        self.assertEqual(serve.call_args.kwargs, {'port': 0, 'open_browser': False})


@unittest.skipUnless(shutil.which('node'), 'optional Node DOM test unavailable')
class BrowserRenderingTests(AppFixture):
    def test_five_paper_frontend_navigation_and_escaping(self):
        for index in range(5): self.label(index, 'included', authoritative=False)
        self.document(0); self.document(1, kind='pending')
        self.document(2, kind='mismatch'); self.document(3, kind='invalid')
        data = {'dashboard': self.reads.dashboard(), 'papers': self.reads.papers(),
                'detail': self.reads.paper(self.handle(0)), 'provenance': self.reads.provenance(self.handle(0))}
        self.label(0, 'included'); self.label(1, 'excluded'); self.label(2, 'insufficient_evidence')
        data['published'] = [self.reads.paper(self.handle(i))['paper'] for i in range(3)]
        script = resources.files('corpustrail.local_app').joinpath('assets/app.js').read_text(encoding='utf-8')
        harness = r'''
const vm=require('node:vm'), assert=require('node:assert/strict');
const data=DATA, elements={}, requests=[];
function element(tag='div') {return {tag,value:'',content:'fixture-token',textContent:'',hidden:true,disabled:false,children:[],
  addEventListener(k,f){this['on'+k]=f;}, append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
  prepend(...items){this.children.unshift(...items);},setAttribute(k,v){this[k]=v;},focus(){this.focused=true;},select(){this.selected=true;},
  set innerHTML(v){throw Error('unsafe HTML');}};}
function visibleText(item){return [item.textContent,...item.children.map(visibleText)].join(' ');}
const document={getElementById(id){return elements[id]||(elements[id]=element());},querySelector(){return element();},createElement:element};
for(const [id,value] of Object.entries({'page-size':'25',sort:'title','provenance-section':'bibliography'})) document.getElementById(id).value=value;
let copied;
const context={document,location:{pathname:'/dashboard'},navigator:{clipboard:{writeText:async(value)=>{copied=value;}}},URLSearchParams,console,fetch:async(path,options)=>{
  requests.push(path); assert.equal(options.headers['X-CorpusTrail-Session'],'fixture-token');
  return {ok:true,json:async()=>structuredClone(path.includes('provenance')?data.provenance:path.endsWith('dashboard')?data.dashboard:path.includes('?')?data.papers:data.detail)};}};
vm.createContext(context);vm.runInContext(SCRIPT,context);
(async()=>{await new Promise(r=>setImmediate(r));assert.equal(elements['project-name'].textContent,'Materials catalogue');
const summary=visibleText(elements.summaries);
assert(summary.includes('Papers with recorded human review: 5'));
assert(summary.includes('Papers with published corpus decisions: 0'));
assert(summary.includes('Awaiting corpus decision: 5'));
assert(!summary.includes('Session updates'));assert(!summary.includes('draft history'));
assert(visibleText(elements['dashboard-details']).includes('Draft history is not a recorded decision'));
assert(elements.resolvers.textContent.includes('Europe PMC'));
await vm.runInContext('catalogue()',context);assert.equal(elements['paper-list'].children.length,5);
const link=elements['paper-list'].children[0].children[0].children[0];assert(link.href.startsWith('/papers/'));assert(!link.textContent.includes('ct-paper:'));
assert(!requests.some(x=>x.includes('provenance')));
const card=visibleText(elements['paper-list'].children[0]);
assert(card.includes('Human review recorded'));assert(card.includes('Awaiting corpus decision'));
assert(!card.includes('Draft history'));assert(!card.includes('ct-paper:'));
await vm.runInContext('detail('+JSON.stringify(data.detail.paper.handle)+')',context);
assert(visibleText(elements['paper-status']).includes('Verified full/structured text'));assert.equal(elements['document-controls'].children.length,1);
assert.equal(elements['advanced'].open,undefined);assert(!elements['detail-evidence']);
await vm.runInContext('provenance()',context);
assert(elements['technical-identifiers'].children[0].children[1].value.startsWith('ct-paper:'));
await elements['technical-identifiers'].children[0].children[2].onclick();assert.equal(copied,data.provenance.paper_id);
context.navigator.clipboard.writeText=async()=>{throw Error('clipboard unavailable');};
await elements['technical-identifiers'].children[0].children[2].onclick();
assert(elements['technical-identifiers'].children[0].children[1].selected);
assert(elements['copy-status'].textContent.includes('manual copying'));
assert(elements['selection-summary'].textContent.includes('Canonical metadata selection'));
assert(elements['provenance-text'].textContent.includes(data.provenance.items[0].observation_id));
assert.equal(elements['raw-details']?.open,undefined);
for(const [index,label] of ['In corpus','Out of corpus','Insufficient evidence'].entries()) {
  data.detail.paper=data.published[index];await vm.runInContext('detail('+JSON.stringify(data.detail.paper.handle)+')',context);
  assert(visibleText(elements['paper-status']).includes(label));
  if(index>0)assert.equal(elements['document-controls'].children.length,0);
}
data.dashboard.project.definition_origin='project_description';data.dashboard.project.broad_corpus_definition=data.dashboard.project.description;
await vm.runInContext('dashboard()',context);assert.equal(elements['definition-group'].hidden,true);
assert.equal(elements.definition.textContent,'');assert(elements['definition-note'].textContent.includes('No separate corpus definition'));
data.dashboard.project.definition_origin='review_scope';
await vm.runInContext('dashboard()',context);assert.equal(elements['definition-group'].hidden,true);
assert(!elements['definition-note'].textContent.includes('No separate corpus definition'));
data.detail.paper=data.papers.items[4];data.detail.paper.abstract=null;data.detail.paper.representations=[];
data.detail.paper.bibliography.source=null;data.detail.paper.evidence.abstract_available=false;
await vm.runInContext('detail('+JSON.stringify(data.detail.paper.handle)+')',context);
assert(elements.abstract.textContent.includes('No abstract is currently available in CorpusTrail'));
assert(visibleText(elements.representations).includes('No full-text document'));
assert(!elements.bibliography.textContent.includes('Source unavailable'));
assert(visibleText(elements['paper-status']).includes('Awaiting corpus decision'));
assert.equal(vm.runInContext('reviewLabel({human_observations:0,sessions_with_draft_history:1})',context),'No human review recorded');
assert.equal(vm.runInContext('identifierLine([{scheme:"openalex",value:"W12345"},{scheme:"pmcid",value:"PMC12345"}])',context),'PMCID: PMC12345');
data.papers.items[0].bibliography.title='<script>attack()</script>';await vm.runInContext('catalogue()',context);
assert.equal(elements['paper-list'].children[0].children[0].children[0].textContent,'<script>attack()</script>');
assert(requests.every(x=>x.startsWith('/api/v1/')));console.log('five-paper DOM walkthrough passed');})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('DATA', json.dumps(data)).replace('SCRIPT', json.dumps(script))
        result = subprocess.run([shutil.which('node')], input=harness, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
