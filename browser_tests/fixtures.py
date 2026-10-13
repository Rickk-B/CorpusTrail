"""Disposable scientific fixtures served by the real installed application."""
from contextlib import ExitStack
from importlib import resources
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import uuid
from urllib.parse import urlsplit
from unittest.mock import patch

from corpustrail.application.discovery import DiscoveryController
from corpustrail.application.evidence import EvidenceController
from corpustrail.application.projects import ProjectController
from corpustrail.application.trash import ProjectRemoval
from corpustrail.curation import ReviewEvent, EvidenceBasis
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.local_app import make_server
from corpustrail.project import Project, ProjectConfig, ProviderConfig, SearchConcept, ReviewPolicy, EvidencePolicy
from corpustrail.providers.network import HttpResponse

AT = '2026-01-01T00:00:00+00:00'
TITLE = 'Evidence reference: synthetic porous materials'
ABSTRACT = 'Invented scientific abstract. <script>Scientific text is data, not executable content.</script>'
SCOPE = 'Broad-topic collection of invented porous materials; not question-specific screening.'
# Reuse the authoritative verification fixture used by Checkpoint 4 unit tests.
XML = b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/evidence.1</article-id><article-id pub-id-type="pmc">PMC123</article-id><abstract><p>Invented acquired abstract.</p></abstract></article-meta></front><body><sec><title>Methods</title><p>Invented structured scientific fixture text.</p></sec></body></article>'


def fingerprint(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class ConfirmationOnlyTrash:
    """Exercises actual confirmation/lease services, never native disposal."""
    def capability(self):
        return {'available': True, 'reason': ''}

    def move(self, path):
        raise AssertionError('Browser confirmation tests must not execute disposal')


class FixtureTransport:
    network = False

    def __init__(self):
        self.calls = []
        self.errors = []
        self.gate = None
        self.entered = threading.Event()
        self.mismatch = False
        self.fail_crossref = False

    def request(self, url, **kwargs):
        self.calls.append(url)
        self.entered.set()
        if self.gate and not self.gate.wait(15):
            raise AssertionError('Controlled provider gate timed out')
        parsed = urlsplit(url)
        if url == 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML':
            body = XML.replace(b'PMC123', b'PMC999').replace(b'evidence.1', b'wrong.9') if self.mismatch else XML
            return HttpResponse(200, {}, body, url)
        if parsed.hostname == 'api.openalex.org' and parsed.path == '/works':
            value = {'results': [
                {'id': 'https://openalex.org/W1', 'doi': '10.1234/evidence.1', 'title': TITLE},
                {'id': 'https://openalex.org/W2', 'doi': '10.1234/discovery.2', 'title': 'Discovered glass scaffold'}],
                'meta': {'count': 2, 'next_cursor': None}}
        elif parsed.hostname == 'api.crossref.org' and parsed.path == '/works':
            if self.fail_crossref:
                return HttpResponse(503, {}, b'Controlled provider failure', url)
            value = {'message': {'items': [
                {'DOI': '10.1234/evidence.1', 'title': [TITLE]},
                {'DOI': '10.1234/discovery.3', 'title': ['Discovered glass scaffold']}], 'total-results': 2}}
        elif parsed.hostname == 'www.ebi.ac.uk' and parsed.path.endswith('/search'):
            value = {'hitCount': 2, 'resultList': {'result': [
                {'id': '123', 'source': 'MED', 'doi': '10.1234/evidence.1', 'pmcid': 'PMC123', 'title': TITLE},
                {'id': '124', 'source': 'MED', 'doi': '10.1234/discovery.4', 'title': 'Discovered polymer study'}]}}
        elif parsed.hostname == 'api.semanticscholar.org' and parsed.path.endswith('/paper/search'):
            value = {'total': 2, 'data': [
                {'paperId': '1'*40, 'externalIds': {'DOI': '10.1234/evidence.1'}, 'title': TITLE},
                {'paperId': '2'*40, 'externalIds': {'DOI': '10.1234/discovery.5'}, 'title': 'Discovered metal study'}]}
        else:
            self.errors.append('Unrecognized provider request')
            raise AssertionError('No fixture for requested endpoint')
        return HttpResponse(200, {}, json.dumps(value).encode('utf-8'), url)


class ApplicationFixture:
    def __init__(self):
        self.stack = ExitStack()
        try:
            self._setup()
        except BaseException:
            self.stack.close()
            raise

    def _setup(self):
        source=Path(__file__).resolve().parents[1]/'src'/'corpustrail'
        installed=resources.files('corpustrail')
        import corpustrail
        if Path(corpustrail.__file__).resolve().is_relative_to(source):
            raise AssertionError('Browser acceptance requires an installed wheel, not editable source')
        for path in source.rglob('*'):
            if path.is_file() and path.suffix in {'.py','.html','.css','.js'}:
                if installed.joinpath(*path.relative_to(source).parts).read_bytes()!=path.read_bytes():
                    raise AssertionError('Installed package differs from checkout. Rebuild and force-reinstall its wheel.')
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='ct-browser-disposable-'))
        self.base = Path(self.temp).resolve()
        self.root = self.base / 'projects'
        self.errors = []
        self.stack.enter_context(patch('corpustrail.application.project_use.lock_directory', return_value=self.base/'locks'))
        # Backend network guard, independent of browser routing. No hidden real
        # transport can reach a provider even if a fixture injection regresses.
        def forbidden(*args, **kwargs):
            self.errors.append('Unexpected real backend transport')
            raise AssertionError('Real external network forbidden in browser acceptance')
        self.stack.enter_context(patch('corpustrail.providers.network.UrlLibTransport.request', side_effect=forbidden))
        original = socket.socket.connect
        def connect(sock, address):
            if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
                self.errors.append('Unexpected nonloopback backend socket')
                raise AssertionError('Nonloopback network forbidden')
            return original(sock, address)
        self.stack.enter_context(patch.object(socket.socket, 'connect', connect))
        self.project = Project.create(self.root/'materials', ProjectConfig('browser-'+uuid.uuid4().hex, 'Synthetic materials',
            'Invented publications for browser acceptance.',
            providers=tuple(ProviderConfig(x, x) for x in ('openalex', 'crossref', 'europepmc', 'semantic_scholar')),
            search=(SearchConcept('porous', 'porous materials'),),
            review=ReviewPolicy(scope=SCOPE), evidence=EvidencePolicy(('europepmc',), max_attempts=1)),
            created_by='fixture', created_at=AT)
        self.papers = []
        for i, title in enumerate((TITLE, 'Publication without a PMCID',
                'Long scientific title — Μικροδομή ' + 'porous materials and characterization ' * 8,
                'Pending document publication', 'Metadata-only publication'), 1):
            raw = ('synthetic-'+str(i)).encode()
            record = BibliographicRecord(title, ABSTRACT if i == 1 else None,
                authors=('Fixture Researcher',), year=2025, source='Synthetic Journal',
                identifiers=(Identifier('doi', '10.1234/evidence.'+str(i)),) +
                ((Identifier('pmcid', 'PMC123'),) if i == 1 else ()))
            source = SourceReference('fixture://bibliography/'+str(i), str(i),
                'sha256:'+hashlib.sha256(raw).hexdigest(), len(raw), 'fixture_discovery', AT, identity_status='verified')
            self.papers.append(self.project.identities.apply(self.project.identities.plan(record, source),
                approve_new_identity=True, approve_aliases=True))
        self.project.evidence.preserve_document(self.papers[3],
            b'<article><body><p>Unidentified synthetic document.</p></body></article>',
            representation='jats_xml',media_type='application/xml',source_uri='fixture://pending-document',
            legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='v1')
        source=self.project.identities.observations(self.papers[1])[0]['source']
        observation=ReviewEvent(self.papers[1],'included','sufficient','metadata','Synthetic earlier human observation',
            'fixture_reviewer',AT,(EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
            authority_state='non_authoritative')
        self.project.reviews.apply(self.project.reviews.plan(observation),recorded_at=AT)
        self.controller = ProjectController(projects_root=self.root)
        self.stack.callback(self.controller.close)
        self.controller._removal_service = ProjectRemoval(self.controller, ConfirmationOnlyTrash())
        self.transport = FixtureTransport()
        self.discovery = DiscoveryController(self.controller, transport_factory=lambda: self.transport)
        self.evidence = EvidenceController(self.controller, transport_factory=lambda: self.transport)
        self.server = make_server(port=0, controller=self.controller, discovery=self.discovery, evidence=self.evidence)
        self.stack.callback(self.server.server_close)
        self.disconnects = 0
        def handler_error(*_):
            error=sys.exc_info()[1]
            if isinstance(error,(BrokenPipeError,ConnectionResetError)):
                self.disconnects+=1  # Browser navigation/teardown, not a provider failure.
            else:
                self.errors.append('Local server exception: '+type(error).__name__)
        self.server.handle_error=handler_error
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = 'http://127.0.0.1:'+str(self.server.server_port)

    def close(self):
        try:
            if self.transport.gate:
                self.transport.gate.set()
            for worker in self.discovery._workers.values():
                worker[0].join(20)
            for worker in self.evidence._workers.values():
                worker.join(20)
            self.server.shutdown()
            self.thread.join(10)
            self.server.server_close()
            self.controller.close()
        finally:
            self.stack.close()
