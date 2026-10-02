"""Private alpha hardening contracts; no scientific labels or provider calls."""
import ast
import hashlib
from importlib import resources
import json
import runpy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dataclasses import replace

from corpustrail.cli import main
from corpustrail.errors import ContractError
from corpustrail.project import Project, ProjectConfig, ProviderConfig
from corpustrail.tutorial import run
from corpustrail.providers.metadata import MetadataProvider


class AlphaAcceptanceTests(unittest.TestCase):
    def test_installed_tutorial_identity_membership_and_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'topic'
            result = run(root)
            self.assertEqual((result['raw_observations'],result['canonical_papers']), (9,8))
            self.assertEqual(result['round_trip_records'], [3,3])
            self.assertEqual(result['preview']['records'], 3)
            self.assertEqual(result['preview']['membership_counts']['insufficient_evidence'], 1)
            self.assertTrue(result['membership_unchanged'])
            before = Project.open(root).status()
            with self.assertRaises((ContractError, FileExistsError)):
                run(root)
            self.assertEqual(before, Project.open(root).status())

    def test_provenance_resource_and_declarative_sdist_inclusion(self):
        value = json.loads(resources.files('corpustrail.resources').joinpath('origins.json').read_text(encoding='utf-8'))
        root = Path(__file__).resolve().parents[1]
        for path, sha in value['immutable_origin_receipts'].items():
            self.assertEqual('sha256:'+hashlib.sha256((root/path).read_bytes()).hexdigest(), sha)
            self.assertIn(path, (root/'MANIFEST.in').read_text(encoding='utf-8'))
        self.assertFalse(value['scientific_data_included'])

    def test_only_shared_boundary_builds_xml_trees(self):
        root = Path(resources.files('corpustrail'))
        for file in root.rglob('*.py'):
            if file.relative_to(root).as_posix()=='_internal/xml_safety.py':
                continue
            tree = ast.parse(file.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, {'fromstring', 'XML', 'iterparse'}, file)

    def test_configuration_revision_and_no_plaintext_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'topic'
            project = Project.create(root, ProjectConfig('fixture','Materials','Invented'), created_by='fixture')
            config = replace(project.config, config_version=2)
            input_path = Path(temp)/'config.json'
            input_path.write_text(json.dumps(config.to_dict()), encoding='utf-8')
            guard = project.status()['config_event_id']
            args = ['project','configure',str(root),'--config',str(input_path),'--expected-event-id',guard,'--created-by','fixture']
            with patch('sys.stdout'), patch('sys.stderr'):
                self.assertEqual(main(args), 0)
                self.assertEqual(main(args), 2)
            self.assertEqual(len(project.configuration_history()), 2)
            with self.assertRaises(ContractError):
                ProjectConfig.from_dict({**config.to_dict(),'api_key':'not-a-real-token'})
            with self.assertRaises(ContractError):
                ProviderConfig('wrong','openalex').validate()

    def test_help_names_plan_only_writes_and_confirmation(self):
        from io import StringIO
        for args, expected in ((['knowledge','assert','--help'],'Plan one assertion ONLY'),
                               (['discover','--help'],'Explicit authorization'),
                               (['review','prepare','--help'],'reviewer must be authorized')):
            out = StringIO()
            with patch('sys.stdout', out), self.assertRaises(SystemExit) as result:
                main(args)
            self.assertEqual(result.exception.code, 0)
            self.assertIn(expected, ' '.join(out.getvalue().split()))

    def test_missing_credentials_preserve_typed_failure_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Project.create(Path(temp)/'topic', ProjectConfig(
                'fixture', 'Materials', 'Invented', providers=(ProviderConfig(
                    'openalex', 'openalex', credential_env='CORPUSTRAIL_TEST_TOKEN'),)), created_by='fixture')
            provider = MetadataProvider('openalex')
            plan = project.discovery.plan(provider, run_id='credential-check', query='synthetic')
            with patch.dict('os.environ', {}, clear=True), patch(
                    'corpustrail.providers.network.UrlLibTransport.request', side_effect=AssertionError('no network')):
                result = project.discovery.execute(plan, provider, confirm_external=True)
            self.assertEqual(result['outcome'], 'requires_configuration')
            self.assertEqual(result['error'], 'missing_credential')
            self.assertEqual(result['physical_attempts'], 0)
            self.assertIn('CORPUSTRAIL_TEST_TOKEN', result['message'])
            self.assertIn('new run ID', result['message'])

    def test_release_population_is_code_only_and_hash_checked(self):
        root = Path(__file__).resolve().parents[1]
        staging = runpy.run_path(str(root/'tools/release_manifest.py'))
        result = staging['build'](root)
        self.assertFalse(result['release_ready'])
        self.assertFalse(staging['eligible']('docs/developer/ALPHA_HARDENING_REPORT.md'))
        for path in ('review/packet.json', '.secrets/api.key', 'data/project.sqlite3',
                     'examples/article.pdf', 'src/corpustrail/__pycache__/cache.py'):
            self.assertFalse(staging['eligible'](path), path)
        for record in result['files']:
            self.assertEqual(record['sha256'], 'sha256:'+hashlib.sha256((root/record['path']).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
