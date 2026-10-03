"""Source/import and CLI gates for the isolated candidate."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sys
import subprocess
import tempfile
import tomllib
import unittest
from importlib import resources
from pathlib import Path
from unittest.mock import patch

import corpustrail
from corpustrail.cli import main
from corpustrail.project import Project


class IsolationTests(unittest.TestCase):
    def test_package_is_regular_not_a_cross_checkout_namespace(self):
        self.assertEqual(len(corpustrail.__path__), 1)
        for name in ("upe", "screening_shadow", "controlled_screening_evaluation", "asreview_export"):
            self.assertIsNone(importlib.util.find_spec("corpustrail." + name))

    def test_all_python_imports_are_standalone_or_standard_library(self):
        root = Path(corpustrail.__file__).parent
        denied = {"socket", "urllib", "http", "requests", "subprocess"}
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    for name in names:
                        top = name.split(".")[0]
                        if isinstance(node, ast.ImportFrom) and node.level:
                            continue
                        optional = {'sklearn','numpy','scipy'} if path.relative_to(root).as_posix()=='prioritization/_algorithm.py' else set()
                        self.assertIn(top, sys.stdlib_module_names | {"corpustrail"} | optional, (path, name))
                        allowed_network = {"providers/network.py", "providers/metadata.py", "curation/http.py",
                                           "models/integrations/compatible_endpoint.py"}
                        if path.relative_to(root).as_posix() not in allowed_network:
                            self.assertNotIn(top, denied, (path, name))
                if isinstance(node, ast.Call):
                    self.assertFalse(isinstance(node.func, ast.Name) and node.func.id in {"__import__", "eval", "exec"}, path)
                    self.assertFalse(isinstance(node.func, ast.Attribute) and node.func.attr in {"import_module", "spec_from_file_location", "extend_path"}, path)

    def test_core_has_no_project_specific_literal_paths_or_semantics(self):
        root = Path(corpustrail.__file__).parent
        forbidden = (r"\bupe\b", r"is_human", r"UPE_Library", r"biophoton", r"mitogenetic",
                     r"scripts/", r"pipeline_data/", r"(?<![\w-])review/", r"PYTHONPATH", r"search_terms\.yaml")
        for path in root.rglob("*.py"):
            body = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                self.assertIsNone(re.search(pattern, body, re.I), (path, pattern))
        # Historical SQL resources are the one frozen, documented compatibility exception.

    def test_research_path_gate_does_not_reject_versioned_generic_contracts(self):
        pattern = r"(?<![\w-])review/"
        self.assertIsNotNone(re.search(pattern, 'Path("review/research_packet.json")'))
        self.assertIsNone(re.search(pattern, '"corpustrail-broad-corpus-review/v1"'))

    def test_schema_resource_allowlist_and_hashes(self):
        root = resources.files("corpustrail.operational")
        manifest = json.loads(root.joinpath("schema_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["historical_count"], 31)
        self.assertEqual(manifest["origin_commit"], "1911f29dc2de0430d2f3c28324a672b78c5f150e")
        self.assertEqual([x["version"] for x in manifest["migrations"]], list(range(1, 38)))
        for entry in manifest["migrations"]:
            self.assertEqual("sha256:" + hashlib.sha256(root.joinpath("schema", entry["name"]).read_bytes()).hexdigest(), entry["sha256"])
            self.assertEqual(entry["origin_path"] is None, entry["version"] >= 32)

    def test_importing_services_does_not_load_an_optional_model_or_integration(self):
        from corpustrail.identity import IdentityService
        from corpustrail.curation import ReviewService
        self.assertTrue(IdentityService and ReviewService)
        # Other tests may explicitly fit the optional model. Check a fresh interpreter.
        code = 'import sys; from corpustrail.project import Project; from corpustrail.export import ExportService; from corpustrail.prioritization import PrioritizationService; from corpustrail.knowledge import KnowledgeStore,KnowledgeView,Registry; from corpustrail.curation.http import make_server; assert not set(sys.modules)&'+repr(set(('anthropic','openai','asreview','sklearn','yaml','upe_core','upe_relevance','search_databases')))
        subprocess.run([sys.executable,'-B','-c',code],check=True,capture_output=True)

    def test_cli_version_and_invalid_init(self):
        with self.assertRaises(SystemExit) as result, patch("sys.stdout"):
            main(["--version"])
        self.assertEqual(result.exception.code, 0)
        with tempfile.TemporaryDirectory() as temp, patch("sys.stderr"):
            target = Path(temp) / "bad"
            code = main(["project", "init", str(target), "--created-by", "fixture"])
            self.assertEqual(code, 2)
            self.assertFalse(target.exists())

    def test_cli_init_status_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as temp, patch("sys.stdout"), patch("sys.stderr"):
            target = Path(temp) / "cli-project"
            argv = ["project", "init", str(target), "--project-id", "fixture", "--name", "Materials",
                    "--description", "A synthetic fixture", "--created-by", "fixture"]
            self.assertEqual(main(argv), 0)
            before = Project.open(target).database_path.read_bytes()
            self.assertEqual(main(["project", "status", str(target)]), 0)
            self.assertEqual(main(argv), 2)
            self.assertEqual(Project.open(target).database_path.read_bytes(), before)

    def test_version_metadata_agrees_in_source_distribution(self):
        candidate = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((candidate / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], corpustrail.__version__)
        self.assertEqual(metadata["project"]["dependencies"], [])
        self.assertNotIn("data-files", metadata.get("tool", {}).get("setuptools", {}))

    def test_native_parser_migration_retains_original_algorithm_bytes(self):
        candidate = Path(__file__).resolve().parents[1]
        receipt = json.loads((candidate / "docs/phase2b_migration_origins.json").read_text(encoding="utf-8"))
        entry = receipt["sources"][0]
        body = (Path(corpustrail.__file__).parent / "evidence/native_parsers.py").read_bytes()
        # The historical receipt remains immutable. Security hardening is a new
        # explicit adaptation, not a rewrite of the historical migration claim.
        current = json.loads(resources.files('corpustrail.resources').joinpath('origins.json').read_text(encoding='utf-8'))
        adaptation = current['xml_adaptation']
        self.assertEqual(adaptation['previous_destination_sha256'], entry['destination_sha256'])
        self.assertEqual(adaptation['historical_source_sha256'], entry['sha256'])
        self.assertEqual('sha256:' + hashlib.sha256(body).hexdigest(), adaptation['destination_sha256'])

    def test_prioritizer_migration_retains_original_generic_algorithm_bytes(self):
        candidate = Path(__file__).resolve().parents[1]
        receipt = json.loads((candidate/'docs/phase2c_migration_origins.json').read_text(encoding='utf-8'))
        entry = receipt['sources'][0]
        body = (Path(corpustrail.__file__).parent/'prioritization/_algorithm.py').read_bytes()
        self.assertEqual('sha256:'+hashlib.sha256(body).hexdigest(),entry['source_prefix_sha256'])
        self.assertEqual(entry['source_prefix_sha256'],entry['destination_sha256'])
        self.assertTrue(entry['prefix_equal'])
        self.assertEqual(receipt['compatibility_shims'],[])


if __name__ == "__main__":
    unittest.main()
