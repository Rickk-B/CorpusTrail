"""Distribution/privacy contracts only; invented inputs, no remote actions."""
import hashlib
import json
from pathlib import Path
import runpy
import os
from unittest.mock import patch
import tempfile
import tomllib
import unittest

import corpustrail

ROOT = Path(__file__).resolve().parents[1]


class ReleaseFinalizationTests(unittest.TestCase):
    def test_mit_and_omitted_authorship_metadata(self):
        meta = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
        self.assertEqual(meta['license'], 'MIT')
        self.assertEqual(meta['version'], corpustrail.__version__)
        self.assertEqual(meta['license-files'], ['LICENSE', 'NOTICE.md'])
        self.assertNotIn('authors', meta)
        self.assertNotIn('maintainers', meta)
        self.assertNotIn('urls', meta)
        self.assertFalse((ROOT/'CITATION.cff').exists())
        text = (ROOT/'LICENSE').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('MIT License\n\nCopyright (c) 2026 CorpusTrail contributors\n'))
        self.assertIn('without restriction', text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', text)
        self.assertIn('0.1.0a1', (ROOT/'CHANGELOG.md').read_text(encoding='utf-8'))

    def test_final_population_excludes_archived_decisions_and_preserves_receipts(self):
        m = runpy.run_path(str(ROOT/'tools/release_manifest.py'))
        result = m['build'](ROOT)
        paths = {x['path'] for x in result['files']}
        self.assertNotIn('docs/decisions/RELEASE_DECISIONS.md', paths)
        self.assertNotIn('docs/developer/ALPHA_HARDENING_REPORT.md', paths)
        self.assertTrue({'LICENSE', 'SECURITY.md', 'CONTRIBUTING.md', 'CHANGELOG.md'} <= paths)
        self.assertTrue(m['RECEIPTS'] <= paths)
        self.assertEqual(result['license'], 'MIT')
        self.assertEqual(result['pending'], ['explicit remote creation/publication authorization'])

    def fake_tree(self, root, body=b'Safe synthetic text', name='README.md'):
        (root/name).write_bytes(body)
        (root/'release_candidate_manifest_v0.1.0a1.anonymized.json').write_text(json.dumps({'files':[
            {'path':name, 'bytes':len(body), 'sha256':'sha256:'+hashlib.sha256(body).hexdigest()}]}), encoding='utf-8')

    def test_final_scan_catches_changes_and_extra_files(self):
        scan = runpy.run_path(str(ROOT/'tools/audit_release.py'))['audit']
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fake_tree(root)
            self.assertTrue(scan(root)['ok'])
            (root/'README.md').write_text('changed', encoding='utf-8')
            (root/'private.sqlite3').write_bytes(b'SQLite format 3')
            report = scan(root)
            self.assertFalse(report['ok'])
            self.assertIn('content_hash_changed', {x['category'] for x in report['findings']})
            self.assertIn('outside_frozen_population', {x['category'] for x in report['findings']})

    def test_final_scan_does_not_print_sensitive_values(self):
        scan = runpy.run_path(str(ROOT/'tools/audit_release.py'))['audit']
        value = 'ghp_' + 'A'*36
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fake_tree(root, value.encode())
            report = scan(root)
            self.assertFalse(report['ok'])
            self.assertNotIn(value, json.dumps(report))
            self.assertIn('credential_signature', {x['category'] for x in report['findings']})

    def test_private_identity_variants_and_orcid_are_redacted(self):
        scan = runpy.run_path(str(ROOT/'tools/audit_release.py'))['audit']
        invented = 'Example Privateperson'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fake_tree(root, (invented.upper()+' '+'-'.join(['0000','0000','0000','000X'])).encode())
            report = scan(root, private_terms=[invented])
            self.assertFalse(report['ok'])
            self.assertNotIn(invented, json.dumps(report))
            self.assertEqual({'known_personal_identity','orcid_identifier'}, {x['category'] for x in report['findings']})

    def test_personal_initials_are_not_binary_file_modes(self):
        inspect = runpy.run_path(str(ROOT/'tools/audit_release.py'))['inspect_text']
        findings, context = inspect("with path.open('wb') as f: pass", 'example.py', private_terms=['WB'])
        self.assertFalse(findings)
        self.assertEqual(context[0]['category'], 'python_binary_file_mode_not_personal_initials')
        findings, _ = inspect('Copyright WB', 'LICENSE', private_terms=['WB'])
        self.assertTrue(findings)

    def test_neutral_git_identifier_is_not_a_contact_address(self):
        inspect = runpy.run_path(str(ROOT/'tools/audit_release.py'))['inspect_text']
        self.assertFalse(inspect('CorpusTrail <noreply@corpustrail.invalid>', 'guide.md')[0])
        self.assertTrue(inspect('Somebody <'+'person'+'@'+'institution.invalid>', 'guide.md')[0])

    def test_personal_contact_fields_are_not_allowed(self):
        inspect = runpy.run_path(str(ROOT/'tools/audit_release.py'))['inspect_text']
        self.assertTrue(inspect('affiliation = "Invented University"', 'example.toml')[0])

    def test_effective_git_identity_guard_rejects_environment_override(self):
        guard = runpy.run_path(str(ROOT/'tools/verify_git_identity.py'))
        manifest = runpy.run_path(str(ROOT/'tools/release_manifest.py'))['build'](ROOT)
        self.assertEqual(manifest['neutral_git_identity'], {'name':guard['NEUTRAL_NAME'],
            'email':guard['NEUTRAL_EMAIL'], 'account_linked':False})
        # git var works without writing/initializing a repository. Command-local
        # config is explicit; no local/global config or commit is created here.
        options = ['-c','user.name='+guard['NEUTRAL_NAME'],'-c','user.email='+guard['NEUTRAL_EMAIL']]
        env = {k:v for k,v in os.environ.items() if not k.startswith(('GIT_AUTHOR_','GIT_COMMITTER_'))}
        with patch.dict(os.environ,env,clear=True):
            self.assertTrue(guard['verify'](ROOT,git_options=options)['ok'])
            with patch.dict(os.environ,{'GIT_AUTHOR_NAME':'Invented private identity'}):
                result = guard['verify'](ROOT,git_options=options)
                self.assertFalse(result['ok'])
                self.assertNotIn('Invented private identity',json.dumps(result))


if __name__ == '__main__':
    unittest.main()
