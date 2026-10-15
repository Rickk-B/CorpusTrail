"""Minimal invented JATS: text preservation, ordering, offsets and immutable history."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from corpustrail._internal.pipeline import artifact
from corpustrail._internal.values import digest_bytes
from corpustrail.evidence.native_parsers import NativeJatsParser, NativePublisherXmlParser
from corpustrail.project import Project
import test_jats_compatibility as compatibility


def article(body):
    return (compatibility.DOCTYPE+'<article><front><article-meta><article-id pub-id-type="pmc">PMC13558126</article-id>'
        '<article-id pub-id-type="pmid">42723954</article-id>'
        '<article-id pub-id-type="doi">10.3389/ebm.2026.11146</article-id>'
        '</article-meta></front><body>'+body+'</body></article>').encode()


def table(notes):
    return '<table-wrap><caption><p>Table caption.</p></caption><table><tr><td>7</td></tr></table><table-wrap-foot>'+notes+'</table-wrap-foot></table-wrap>'


class JatsTextPreservationTests(unittest.TestCase):
    def parse(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'invented.xml'
            path.write_bytes(article(body))
            output = NativeJatsParser().parse(path)
            publisher = NativePublisherXmlParser().parse(path)
            self.assertEqual(output.body, publisher.body)
            self.assertEqual(output.quality['sections'], publisher.quality['sections'])
            # Sections partition the normalized text, excluding only separators.
            pieces, end = [], 0
            for section in output.quality['sections']:
                start, stop = section['start_offset'], section['end_offset']
                self.assertEqual(output.body[end:start], '\n\n' if pieces else '')
                self.assertGreater(stop, start)
                pieces.append(output.body[start:stop]); end = stop
            self.assertEqual(end, len(output.body))
            self.assertEqual('\n\n'.join(pieces), output.body)
            self.assertEqual(output.quality['characters'], len(output.body))
            self.assertEqual(path.read_bytes(), article(body))
            return output

    def test_one_table_one_labelled_footnote(self):
        result = self.parse('<sec><title>Results</title>'+table('<fn><label>a</label><p>Unique table note.</p></fn>')+'</sec>')
        self.assertEqual(result.body, 'Results\n\nTable caption.\n\n7\n\na\n\nUnique table note.')
        self.assertEqual(result.quality['blocks'], 5)

    def test_multiple_notes_and_paragraphs_do_not_merge_or_duplicate(self):
        result = self.parse(table('<fn><label>a</label><p>First paragraph.</p><p>Second paragraph.</p></fn>'
            '<fn><label>b</label><p>Third paragraph.</p></fn>'))
        self.assertTrue(result.body.endswith('a\n\nFirst paragraph.\n\nSecond paragraph.\n\nb\n\nThird paragraph.'))
        for value in ('First paragraph.', 'Second paragraph.', 'Third paragraph.'):
            self.assertEqual(result.body.count(value), 1)

    def test_nested_inline_references_special_characters_and_missing_label(self):
        result = self.parse(table('<fn><label>*</label><p>α &amp; café <italic>nested <bold>text</bold></italic>; '
            '<xref ref-type="bibr" rid="r1">[3]</xref> and H<sub>2</sub>O, x<sup>2</sup>.</p></fn>'
            '<fn><p>Unlabelled ± 2 μm &lt; 5.</p></fn>'))
        self.assertIn('*\n\nα & café nested text; [3] and H2O, x2.', result.body)
        self.assertIn('Unlabelled ± 2 μm < 5.', result.body)

    def test_two_tables_keep_distinct_notes_in_document_order(self):
        result = self.parse('<sec><title>Results</title><p>Before.</p>'+table('<fn><p>First table note.</p></fn>')+
            '<p>Between.</p>'+table('<fn><p>Second table note.</p></fn>')+'<p>After.</p></sec>')
        positions = [result.body.index(s) for s in ('Before.', 'First table note.', 'Between.', 'Second table note.', 'After.')]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(result.body.count('First table note.'), 1)
        self.assertEqual(result.body.count('Second table note.'), 1)

    def test_nested_sections_and_parent_continuations_keep_source_order(self):
        result = self.parse('<p>Body before.</p><sec><title>Parent</title><p>Parent before.</p>'
            '<sec><title>Child</title>'+table('<fn><p>Child table note.</p></fn>')+'</sec>'
            '<p>Parent after.</p></sec><p>Body after.</p>')
        expected = ('Body before.', 'Parent before.', 'Child', 'Child table note.', 'Parent after.', 'Body after.')
        self.assertEqual([result.body.index(s) for s in expected], sorted(result.body.index(s) for s in expected))
        self.assertEqual([s['path'] for s in result.quality['sections']],
            [['Body'], ['Parent'], ['Parent', 'Child'], ['Parent'], ['Body']])

    def test_related_captions_figure_notes_boxed_text_and_section_notes(self):
        result = self.parse('<sec><title>Results</title><fig><caption><p>Figure caption <italic>text</italic>.</p></caption>'
            '<p>Figure explanation.</p><fn-group><fn><label>f</label><p>Figure note.</p></fn></fn-group></fig>'
            '<boxed-text><caption><p>Box caption.</p></caption><p>Box explanation.</p></boxed-text>'
            '<fn-group><title>Notes</title><fn><p>Section note.</p></fn></fn-group></sec>')
        for value in ('Figure caption text.', 'Figure explanation.', 'Figure note.', 'Box caption.', 'Box explanation.', 'Section note.'):
            self.assertEqual(result.body.count(value), 1)

    def test_direct_table_notes_and_inline_only_footnotes(self):
        result = self.parse(table('<p>Direct table note.</p><fn><label>c</label> Inline <italic>only</italic> note.</fn>'))
        self.assertIn('Direct table note.\n\nc Inline only note.', result.body)

    def test_existing_text_without_footnotes_remains_unchanged(self):
        result = self.parse('<sec><title>Methods</title><p>Text with <italic>formatting</italic>.</p>'
            '<fig><caption><p>Existing caption.</p></caption></fig><table-wrap><alternatives><table><tr><th>A</th><td>B</td></tr></table></alternatives></table-wrap></sec>')
        self.assertEqual(result.body, 'Methods\n\nText with formatting.\n\nExisting caption.\n\nA | B')

    def test_repeated_source_paragraphs_are_not_content_deduplicated(self):
        result = self.parse(table('<fn><p>Same text.</p></fn><fn><p>Same text.</p></fn>'))
        self.assertEqual(result.body.count('Same text.'), 2)

    def test_new_version_does_not_rewrite_historical_derived_evidence(self):
        helper = compatibility.JatsCompatibilityTests()
        with tempfile.TemporaryDirectory() as tmp:
            project, pid = helper.project(Path(tmp))
            raw = article(table('<fn><p>Preserved scientific note.</p></fn>'))
            with patch.object(NativeJatsParser, 'version', 'historical-fixture/v1'):
                helper.preserve(project, pid, raw)
            old = project.evidence.representations(pid)
            helper.preserve(project, pid, raw)
            records = project.evidence.representations(pid)
            self.assertEqual(records[:len(old)], old)
            derived = records[-1]['payload']
            self.assertEqual(derived['parser_version'], 'corpustrail-native-jats/v4')
            self.assertEqual(derived['xml_policy'], 'bounded-inert-jats/v2')
            self.assertIn('Preserved scientific note.', artifact(project, derived['artifact_sha256']).read_text(encoding='utf-8'))
            self.assertEqual(digest_bytes(artifact(project, records[-2]['payload']['artifact_sha256']).read_bytes()), digest_bytes(raw))
            reopened = Project.open(project.root)
            self.assertEqual(reopened.evidence.representations(pid), records)
            self.assertEqual(project.reviews.history(pid), [])
            self.assertEqual(project.reviews.membership(pid)['state'], 'not_reviewed')
