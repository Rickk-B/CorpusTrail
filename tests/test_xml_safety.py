"""Encoding-independent XML policy regression; only invented document bytes."""
import codecs
import gzip
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from corpustrail.errors import ContractError
from corpustrail.evidence.native_parsers import (
    NativeJatsParser, NativePublisherXmlParser, render_grobid_tei,
)
from corpustrail.evidence.parsing import ParsingError
from corpustrail.evidence.service import _document_ids


ENCODINGS = (
    ('utf-8', b''), ('utf-8', codecs.BOM_UTF8),
    ('utf-16-le', b''), ('utf-16-le', codecs.BOM_UTF16_LE),
    ('utf-16-be', b''), ('utf-16-be', codecs.BOM_UTF16_BE),
    ('iso-8859-1', b''), ('ascii', b''),
)


def document(encoding, bom, *, malicious=False, tei=False):
    declared = 'UTF-16' if encoding.startswith('utf-16') else encoding.upper()
    root = 'TEI' if tei else 'article'
    dtd = f'<!DOCTYPE {root} [<!ENTITY marker "synthetic expansion">]>' if malicious else ''
    body = '&marker;' if malicious else 'Safe synthetic café measurement &amp; methods.'
    content = (f'<TEI><text><body><div><head>Methods</head><p>{body}</p></div></body></text></TEI>'
               if tei else '<article><front><article-meta><article-id pub-id-type="doi">'
               f'10.1234/fixture.xml</article-id></article-meta></front><body><p>{body}</p></body></article>')
    return bom + (f'<?xml version="1.0" encoding="{declared}"?>{dtd}{content}').encode(encoding, errors='xmlcharrefreplace')


class XmlSafetyTests(unittest.TestCase):
    def test_all_native_entry_points_reject_encoded_dtd_entities(self):
        for encoding, bom in ENCODINGS:
            with self.subTest(encoding=encoding, bom=bool(bom)), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'article.xml'
                path.write_bytes(document(encoding, bom, malicious=True))
                for parser in (NativeJatsParser(), NativePublisherXmlParser()):
                    with self.assertRaises(ParsingError):
                        parser.parse(path)
                with self.assertRaises(ContractError):
                    _document_ids(path.read_bytes())
                with self.assertRaises(ParsingError):
                    render_grobid_tei(document(encoding, bom, malicious=True, tei=True))

    def test_legitimate_utf16_is_preserved(self):
        for encoding, bom in ENCODINGS:
            with self.subTest(encoding=encoding, bom=bool(bom)), tempfile.TemporaryDirectory() as temp:
                raw = document(encoding, bom)
                path = Path(temp) / 'article.xml'
                path.write_bytes(raw)
                for parser in (NativeJatsParser(), NativePublisherXmlParser()):
                    self.assertIn('café measurement & methods', parser.parse(path).body)
                self.assertEqual(_document_ids(raw)[0], ('doi', '10.1234/fixture.xml'))
                self.assertIn('café measurement & methods', render_grobid_tei(document(encoding, bom, tei=True)).body)

    def test_compressed_and_unsupported_utf32_are_not_unwrapped(self):
        raw = document('utf-8', b'', malicious=True)
        for body in (gzip.compress(raw), b'PK\x03\x04' + raw,
                     raw.decode().replace('UTF-8', 'UTF-32').encode('utf-32')):
            with self.subTest(prefix=body[:4]), self.assertRaises(ContractError):
                _document_ids(body)

    def test_external_parameter_and_wrapped_declarations_fail(self):
        declarations = (
            '<!DOCTYPE article SYSTEM "https://example.test/private.dtd">',
            '<!DOCTYPE article [<!ENTITY % external SYSTEM "file:///not-a-real-file">%external;]>',
            '<!DOCTYPE article>',
        )
        for encoding, bom in ENCODINGS:
            for declaration in declarations:
                raw = document(encoding, bom).decode('utf-16' if bom and encoding.startswith('utf-16') else encoding).lstrip('\ufeff')
                at = raw.index('?>') + 2
                payload = bom + (raw[:at] + declaration + raw[at:]).encode(encoding, errors='xmlcharrefreplace')
                with self.subTest(encoding=encoding, declaration=declaration), self.assertRaises(ContractError):
                    _document_ids(payload)

    def test_bounded_xml_and_inert_xinclude(self):
        from corpustrail._internal import xml_safety
        for limits, raw in (
            ({'MAX_BYTES': 5}, b'<article/>'),
            ({'MAX_DEPTH': 2}, b'<article><a><b/></a></article>'),
            ({'MAX_NODES': 2}, b'<article><a/><b/></article>'),
            ({'MAX_TEXT': 2}, b'<article>abcd</article>'),
        ):
            with self.subTest(limits=limits), patch.multiple(xml_safety, **limits), self.assertRaises(xml_safety.XmlPolicyError):
                xml_safety.parse_xml(raw)
        # The parser never invokes XInclude or fetches its URI.
        root = xml_safety.parse_xml(b'<article xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="https://example.test/no-network"/></article>')
        self.assertEqual(root.tag, 'article')

    def test_bomless_utf16_without_declaration(self):
        from corpustrail._internal.xml_safety import parse_xml, XmlPolicyError
        for encoding in ('utf-16-le', 'utf-16-be'):
            self.assertEqual(parse_xml('<article><p>Safe</p></article>'.encode(encoding)).tag, 'article')
            with self.assertRaises(XmlPolicyError):
                parse_xml('<!DOCTYPE article [<!ENTITY e "marker">]><article>&e;</article>'.encode(encoding))

    def test_utf32_endian_bom_variants_fail_closed(self):
        from corpustrail._internal.xml_safety import parse_xml, XmlPolicyError
        for encoding, bom in (('utf-32-le', b''), ('utf-32-le', codecs.BOM_UTF32_LE),
                              ('utf-32-be', b''), ('utf-32-be', codecs.BOM_UTF32_BE)):
            for content in ('<article/>', '<!DOCTYPE article><article/>'):
                with self.subTest(encoding=encoding, bom=bool(bom)), self.assertRaises(XmlPolicyError):
                    parse_xml(bom + content.encode(encoding))

    def test_recovered_abstract_and_identity_share_policy(self):
        from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
        from corpustrail.project import Project, ProjectConfig
        from corpustrail._internal.values import digest_bytes
        with tempfile.TemporaryDirectory() as temp:
            project = Project.create(Path(temp)/'topic', ProjectConfig('fixture', 'Materials', 'Invented fixture'), created_by='fixture')
            source = SourceReference('fixture://record', 'record-1', digest_bytes(b'invented record'),
                                     len(b'invented record'), 'fixture', '2026-01-01T00:00:00+00:00', identity_status='verified')
            plan = project.identities.plan(BibliographicRecord(title='Invented article', identifiers=(Identifier('doi','10.1234/fixture.xml'),)), source)
            pid = project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)
            for encoding, bom in ENCODINGS:
                raw = document(encoding, bom).decode('utf-16' if bom and encoding.startswith('utf-16') else encoding).lstrip('\ufeff')
                raw = raw.replace('</article-meta>', '<abstract><p>Invented abstract.</p></abstract></article-meta>')
                body = bom + raw.encode(encoding)
                project.evidence.preserve_document(pid, body, representation='jats_xml', media_type='application/xml',
                    source_uri='fixture://xml', legitimate_basis='synthetic_fixture', resolver='fixture', resolver_version='1')
            project.evidence.preserve_document(pid, document('utf-16-le', b'', malicious=True), representation='jats_xml',
                media_type='application/xml', source_uri='fixture://bad', legitimate_basis='synthetic_fixture', resolver='fixture', resolver_version='1')
            reps = project.evidence.representations(pid)
            self.assertTrue(any(r['payload']['representation']=='abstract' and r['payload']['trusted'] for r in reps))
            self.assertEqual(reps[-1]['payload']['artifact_validity'], 'invalid')
            self.assertFalse(reps[-1]['payload']['trusted'])
            self.assertEqual(project.reviews.corpus()[0]['state'], 'not_reviewed')


if __name__ == '__main__':
    unittest.main()
