"""CI/build contracts only; temporary repositories and invented artifacts."""

from pathlib import Path
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(ROOT / 'tools/development_artifact.py'))


@unittest.skipUnless(shutil.which('git'), 'CI/build provenance fixtures require developer Git tooling')
class DevelopmentArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()
        (self.root / 'pyproject.toml').write_text('[project]\nversion="0.1.0a3.dev0"\n', encoding='utf-8')
        (self.root / '.gitignore').write_text('dist/\n', encoding='utf-8')
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)
        self.commit()
        self.implementation = TOOL['git'](self.root, 'rev-parse', 'HEAD')
        (self.root / 'distribution.txt').write_text('Synthetic CI-only follow-up', encoding='utf-8')
        self.commit()
        self.sha = TOOL['git'](self.root, 'rev-parse', 'HEAD')
        (self.root / 'dist').mkdir()
        self.wheel = self.root / 'dist/corpus_trail-0.1.0a3.dev0-py3-none-any.whl'
        self.write_wheel()
        self.validation = Path(self.temp.name) / 'validation'
        self.validation.mkdir()
        (self.validation / 'development-tests.txt').write_text('\nRan 330 tests in 1.0s\n\nOK (skipped=46)\n', encoding='utf-8')
        (self.validation / 'development-tutorial.json').write_text('{"network_used":false}', encoding='utf-8')
        (self.validation / 'development-version.txt').write_text('0.1.0a3.dev0\n', encoding='utf-8')
        self.context = {'repository': 'fixture/CorpusTrail', 'ref': 'refs/heads/development/fixture',
                        'run_id': '12', 'run_attempt': '1'}
        self.output = Path(self.temp.name) / 'bundle'

    def commit(self):
        environment = dict(os.environ, GIT_AUTHOR_NAME='CorpusTrail', GIT_AUTHOR_EMAIL='noreply@corpustrail.invalid',
                           GIT_COMMITTER_NAME='CorpusTrail', GIT_COMMITTER_EMAIL='noreply@corpustrail.invalid')
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True, env=environment)
        subprocess.run(['git', '-C', str(self.root), 'commit', '--quiet', '-m', 'Synthetic artifact test'], check=True, env=environment)

    def write_wheel(self, *, version='0.1.0a3.dev0', extra='', omit_assets=False):
        with zipfile.ZipFile(self.wheel, 'w') as archive:
            archive.writestr('corpus_trail-0.1.0a3.dev0.dist-info/METADATA',
                'Name: corpus-trail\nVersion: '+version+'\nLicense-Expression: MIT\n'+extra)
            if not omit_assets:
                for name in TOOL['FRONTEND']:
                    archive.writestr(name, 'invented asset')

    def bundle(self):
        return TOOL['bundle'](self.root, self.sha, self.validation, self.output,
                              implementation=self.implementation, context=self.context)

    def test_clean_exact_commit_and_development_version(self):
        record = TOOL['check_source'](self.root, self.sha)
        self.assertEqual(record['commit_sha'], self.sha)
        self.assertEqual(record['version'], '0.1.0a3.dev0')

    def test_wrong_commit_or_dirty_source_rejected(self):
        with self.assertRaises(ValueError): TOOL['check_source'](self.root, '0' * 40)
        (self.root / 'unexpected').write_text('fixture', encoding='utf-8')
        with self.assertRaises(ValueError): TOOL['check_source'](self.root, self.sha)

    def test_public_release_version_rejected(self):
        (self.root / 'pyproject.toml').write_text('[project]\nversion="0.1.0a2"\n', encoding='utf-8')
        self.commit()
        with self.assertRaises(ValueError): TOOL['check_source'](self.root, TOOL['git'](self.root, 'rev-parse', 'HEAD'))

    def test_wheel_version_privacy_dependency_and_resource_checks(self):
        for options in ({'version': '0.1.0a2'}, {'extra': 'Author: Fixture person\n'},
                        {'extra': 'Requires-Dist: mandatory-fixture\n'}, {'omit_assets': True}):
            self.write_wheel(**options)
            with self.assertRaises(ValueError): TOOL['inspect_wheel'](self.wheel, '0.1.0a3.dev0')

    def test_bundle_records_commit_version_hash_and_only_explicit_context(self):
        with patch.dict(os.environ, {'FAKE_SECRET': 'not-for-provenance', 'GITHUB_ACTOR': 'not-for-provenance'}):
            name = self.bundle()
        record = json.loads((self.output / 'build-provenance.json').read_text(encoding='utf-8'))
        self.assertIn(self.sha, name)
        self.assertEqual(record['source']['commit_sha'], self.sha)
        self.assertEqual(record['checkpoint']['implementation_commit_sha'], self.implementation)
        self.assertNotEqual(record['source']['commit_sha'], record['checkpoint']['implementation_commit_sha'])
        self.assertTrue(record['checkpoint']['application_source_unchanged'])
        self.assertEqual(record['status'], 'unreleased_development_checkpoint')
        self.assertEqual(record['wheel']['sha256'], hashlib.sha256(self.wheel.read_bytes()).hexdigest())
        self.assertNotIn('not-for-provenance', json.dumps(record))
        self.assertEqual((self.output / self.wheel.name).read_bytes(), self.wheel.read_bytes())
        for line in (self.output / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
            digest, filename = line.split('  ')
            self.assertEqual(digest, hashlib.sha256((self.output / filename).read_bytes()).hexdigest())

    def test_failed_tests_or_network_tutorial_prevent_bundle(self):
        (self.validation / 'development-tests.txt').write_text('\nRan 330 tests in 1s\nFAILED\n', encoding='utf-8')
        with self.assertRaises(ValueError): self.bundle()
        self.assertFalse(self.output.exists())
        (self.validation / 'development-tests.txt').write_text('\nRan 330 tests in 1s\nOK\n', encoding='utf-8')
        (self.validation / 'development-tutorial.json').write_text('{"network_used":true}', encoding='utf-8')
        with self.assertRaises(ValueError): self.bundle()

    def test_existing_bundle_and_multiple_wheels_never_overwritten(self):
        self.bundle()
        before = (self.output / 'build-provenance.json').read_bytes()
        with self.assertRaises(FileExistsError): self.bundle()
        self.assertEqual((self.output / 'build-provenance.json').read_bytes(), before)
        (self.root / 'dist/extra.whl').write_bytes(b'fixture')
        with self.assertRaises(ValueError): self.bundle()

    def test_non_development_ref_or_arbitrary_repository_url_rejected(self):
        self.context['ref'] = 'refs/tags/v0.1.0a2'
        with self.assertRaises(ValueError): self.bundle()
        self.context['ref'] = 'refs/heads/development/fixture'
        self.context['repository'] = 'https://fixture.example.test/CorpusTrail'
        with self.assertRaises(ValueError): self.bundle()

    def test_workflow_is_validation_gated_and_read_only_to_github(self):
        source = (ROOT / '.github/workflows/standalone.yml').read_text(encoding='utf-8')
        artifact = source.split('  development-artifact:', 1)[1]
        self.assertIn('needs: acceptance', artifact)
        self.assertIn("ref: '${{ github.sha }}'", artifact)
        self.assertIn('persist-credentials: false', artifact)
        self.assertIn("CHECKPOINT_IMPLEMENTATION_SHA: '6e116118f05e53ec3694c60e9171cb873a437bf8'", artifact)
        self.assertIn('fetch-depth: 0', artifact)
        self.assertIn('retention-days: 90', artifact)
        self.assertIn('overwrite: false', artifact)
        self.assertIn('contents: read', source)
        for dangerous in ('secrets.', 'twine', 'gh release', 'git push', 'contents: write', 'id-token: write'):
            self.assertNotIn(dangerous, artifact)

    def test_implementation_must_be_ancestor_and_application_source_unchanged(self):
        with self.assertRaises(ValueError):
            TOOL['check_implementation'](self.root, self.sha, self.implementation)
        folder = self.root / 'src/corpustrail'
        folder.mkdir(parents=True)
        (folder / 'changed.py').write_text('fixture = True\n', encoding='utf-8')
        self.commit()
        with self.assertRaises(ValueError):
            TOOL['check_implementation'](self.root, self.implementation, TOOL['git'](self.root, 'rev-parse', 'HEAD'))

    def test_ux_receipt_keeps_three_commits_and_only_allows_presentation_paths(self):
        distribution = self.sha
        path = self.root / 'src/corpustrail/local_app/assets/app.js'
        path.parent.mkdir(parents=True)
        path.write_text('const presentation = true;\n', encoding='utf-8')
        self.commit()
        source = TOOL['git'](self.root, 'rev-parse', 'HEAD')
        receipt = TOOL['check_implementation'](self.root, self.implementation, source, distribution=distribution)
        self.assertEqual(receipt['previous_distribution_commit_sha'], distribution)
        self.assertEqual(receipt['implementation_commit_sha'], self.implementation)
        self.assertFalse(receipt['application_source_unchanged'])
        self.assertTrue(receipt['scientific_source_unchanged'])
        self.assertEqual(receipt['presentation_paths_changed'], ['src/corpustrail/local_app/assets/app.js'])
        TOOL['bundle'](self.root, source, self.validation, self.output,
                       implementation=self.implementation, distribution=distribution, context=self.context)
        bundled = json.loads((self.output / 'build-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(bundled['source']['commit_sha'], source)
        self.assertEqual(bundled['checkpoint']['implementation_commit_sha'], self.implementation)
        self.assertEqual(bundled['checkpoint']['previous_distribution_commit_sha'], distribution)
        self.assertFalse(bundled['checkpoint']['application_source_unchanged'])
        scientific = self.root / 'src/corpustrail/curation/service.py'
        scientific.parent.mkdir()
        scientific.write_text('unexpected = True\n', encoding='utf-8')
        self.commit()
        with self.assertRaises(ValueError):
            TOOL['check_implementation'](self.root, self.implementation, TOOL['git'](self.root, 'rev-parse', 'HEAD'), distribution=distribution)


if __name__ == '__main__':
    unittest.main()
