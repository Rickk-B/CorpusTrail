"""Read-only original-response diagnostics; no provider access or article export."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.project import Project, ProjectConfig, EvidencePolicy
from corpustrail.providers.network import HttpResponse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('evidence_diagnostic', ROOT/'tools/evidence_diagnostic.py')
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
AT = '2026-01-01T00:00:00+00:00'
XML = b'<article><front><article-meta><article-id pub-id-type="pmc">123</article-id><article-id pub-id-type="doi">10.1234/diagnostic</article-id></article-meta></front><body><p>PRIVATE_DOCUMENT_SENTINEL.</p></body></article>'


def fingerprint(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class EvidenceDiagnosticTests(unittest.TestCase):
    def test_valid_content_and_public_identifier_inventory_no_text_export(self):
        r = diagnostic.analyze_bytes(XML, public_identifiers=(('pmcid', 'PMC123'),))
        self.assertTrue(r['content_validation']['passed'])
        self.assertTrue(r['structure']['well_formed_without_external_loading'])
        self.assertGreater(r['structure']['body_text_characters'], 0)
        self.assertEqual(r['structure']['expected_identifiers_present'], [('pmcid', 'PMC123')])
        self.assertNotIn('PRIVATE_DOCUMENT_SENTINEL', json.dumps(r))
        self.assertNotIn('10.1234/diagnostic', json.dumps(r))

    def test_external_doctype_inventory_never_loads_and_strict_policy_still_rejects(self):
        raw = b'<!DOCTYPE article SYSTEM "https://external.example.test/article.dtd">' + XML
        with patch('urllib.request.urlopen', side_effect=AssertionError('no network')) as request:
            r = diagnostic.analyze_bytes(raw, public_identifiers=(('pmcid', 'PMC123'),))
        request.assert_not_called()
        self.assertTrue(r['structure']['doctype_present'])
        self.assertTrue(r['structure']['doctype_external_subset'])
        self.assertTrue(r['structure']['well_formed_without_external_loading'])
        self.assertEqual(r['content_validation'], {'passed': False, 'stage': 'xml_policy', 'reason': 'dtd_or_entity_refused'})

    def test_declared_entities_and_resource_limits_abort_safe_inventory(self):
        raw = b'<!DOCTYPE article [<!ENTITY hidden "PRIVATE_ENTITY_SENTINEL">]><article>&hidden;</article>'
        r = diagnostic.analyze_bytes(raw)
        self.assertTrue(r['structure']['entity_declaration_present'])
        self.assertIsNone(r['structure']['well_formed_without_external_loading'])
        self.assertNotIn('PRIVATE_ENTITY_SENTINEL', json.dumps(r))
        with patch.object(diagnostic, 'MAX_BYTES', 10):
            self.assertEqual(diagnostic.inventory(XML, set())['inventory_error'], 'byte_limit')

    def test_encoded_doctype_not_confused_with_comment_and_front_matter_not_body(self):
        r = diagnostic.analyze_bytes(('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE article>'+XML.decode()).encode('utf-16'))
        self.assertTrue(r['structure']['doctype_present'])
        self.assertFalse(r['content_validation']['passed'])
        r = diagnostic.analyze_bytes(b'<article><!-- <!DOCTYPE article> --><front><article-meta/></front></article>')
        self.assertFalse(r['structure']['doctype_present'])
        self.assertEqual(r['structure']['body_text_characters'], 0)

    def test_malformed_and_wrong_root_remain_invalid(self):
        self.assertEqual(diagnostic.analyze_bytes(b'<article>')['content_validation']['reason'], 'malformed_or_unsupported_xml')
        self.assertEqual(diagnostic.analyze_bytes(b'<html/>')['content_validation']['reason'], 'not_an_article')
        wrapped = diagnostic.analyze_bytes(b'<article-set>'+XML+b'</article-set>')
        self.assertEqual(wrapped['structure']['root_kind'], 'article-set')
        self.assertGreater(wrapped['structure']['article_body_text_characters_any_depth'], 0)
        self.assertEqual(wrapped['content_validation']['reason'], 'not_an_article')
        compressed = diagnostic.analyze_bytes(b'\x1f\x8bPRIVATE_BINARY_SENTINEL')
        self.assertEqual(compressed['byte_signature_hint'], 'gzip')
        self.assertFalse(compressed['content_validation']['passed'])
        self.assertNotIn('PRIVATE_BINARY_SENTINEL', json.dumps(compressed))

    def test_original_hash_verified_response_inspection_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix='ct-diagnostic-disposable-') as temp:
            # macOS temporary paths use the /var alias. Canonicalize our own
            # disposable fixture; keep the production symlink refusal intact.
            base = Path(temp).resolve()
            with patch('corpustrail.application.project_use.lock_directory', return_value=base/'locks'):
                project = Project.create(base/'project', ProjectConfig('diagnostic', 'Disposable diagnostics', 'Synthetic topic',
                    evidence=EvidencePolicy(('europepmc',))), created_by='fixture', created_at=AT)
                record = BibliographicRecord('Synthetic diagnostic paper', identifiers=(Identifier('pmcid', 'PMC123'), Identifier('doi', '10.1234/diagnostic')))
                source = SourceReference('fixture://diagnostic', 'source', 'sha256:'+hashlib.sha256(b'fixture').hexdigest(),
                    len(b'fixture'), 'fixture', AT, identity_status='verified')
                paper = project.identities.apply(project.identities.plan(record, source), approve_new_identity=True, approve_aliases=True)
                raw = b'<!DOCTYPE article>' + XML
                class Transport:
                    network = False
                    def request(self, url, **kwargs): return HttpResponse(200, {'Content-Type': 'application/xml'}, raw, url)
                project.evidence.acquire(project.evidence.plan(paper, created_at=AT), transport=Transport(), confirm_external=True, clock=lambda: AT)
                before = fingerprint(project.root)
                connect = sqlite3.connect
                def readonly(*args, **kwargs):
                    self.assertIn('?mode=ro', args[0]); return connect(*args, **kwargs)
                with patch('sqlite3.connect', side_effect=readonly), patch('urllib.request.urlopen', side_effect=AssertionError('no network')):
                    result = diagnostic.inspect_project(project.root, 'PMC123')
                self.assertEqual(before, fingerprint(project.root))
                self.assertEqual(result['attempts'][0]['http_status'], 200)
                self.assertEqual(result['attempts'][0]['response_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(result['attempts'][0]['content_validation']['reason'], 'dtd_or_entity_refused')
                self.assertFalse(result['attempts'][0]['stored_trusted'])
                self.assertNotIn(str(base), json.dumps(result))
                self.assertNotIn('PRIVATE_DOCUMENT_SENTINEL', json.dumps(result))
                self.assertEqual(project.reviews.history(paper), [])
                self.assertEqual(project.reviews.membership(paper)['state'], 'not_reviewed')
                with self.assertRaises(Exception): diagnostic.inspect_project(project.root, 'PMC999')
                artifact = project.root/project.config.data_directory/'artifacts'/hashlib.sha256(raw).hexdigest()
                artifact.write_bytes(b'corrupt fixture')
                with self.assertRaises(Exception): diagnostic.inspect_project(project.root, 'PMC123')

    def test_cli_errors_do_not_expose_paths_credentials_or_stack_traces(self):
        import contextlib
        import io
        output = io.StringIO()
        with (patch.object(diagnostic, 'inspect_project', side_effect=OSError('PRIVATE_PATH PRIVATE_CREDENTIAL')),
                contextlib.redirect_stdout(output)):
            status = diagnostic.main(['--project', '/explicit-project', '--pmcid', 'PMC123'])
        self.assertEqual(status, 1)
        self.assertNotIn('PRIVATE_PATH', output.getvalue())
        self.assertNotIn('PRIVATE_CREDENTIAL', output.getvalue())
