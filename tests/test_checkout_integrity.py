"""Repository-scoped byte preservation and native-command failure propagation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from corpustrail._internal.database import migrations
from corpustrail._internal.values import ContractError

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('git'), 'Checkout contracts require developer Git')
class CheckoutIntegrityTests(unittest.TestCase):
    def test_autocrlf_conversion_reproduces_hash_failure_and_attributes_preserve_exact_bytes(self):
        with tempfile.TemporaryDirectory(prefix='ct-checkout-fixture-') as directory:
            root=Path(directory);package=root/'src/corpustrail/operational'
            package.mkdir(parents=True)
            source=ROOT/'src/corpustrail/operational'
            names=['schema_manifest.json']+['schema/'+p.name for p in sorted((source/'schema').glob('*.sql'))]
            for name in names:
                target=package/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((source/name).read_bytes())
            subprocess.run(['git','init','--quiet',str(root)],check=True)
            def git(*args):
                subprocess.run(['git','-C',str(root),'-c','core.autocrlf=false','-c','core.hooksPath=/dev/null',*args],check=True)
            git('add','src')
            def checkout(name):
                target=root/name
                subprocess.run(['git','-C',str(root),'-c','core.autocrlf=true','checkout-index','--prefix',str(target)+'/', '--all'],check=True)
                return target/'src/corpustrail/operational'
            converted=checkout('converted')
            self.assertIn(b'\r\n',(converted/'schema/001_core.sql').read_bytes())
            with patch('corpustrail._internal.database.resources.files',return_value=converted):
                with self.assertRaisesRegex(ContractError,'schema resource hash mismatch'):migrations()
            (root/'.gitattributes').write_bytes((ROOT/'.gitattributes').read_bytes())
            git('add','.gitattributes')
            preserved=checkout('preserved')
            for name in names:self.assertEqual((preserved/name).read_bytes(),(source/name).read_bytes())
            manifest=json.loads((preserved/'schema_manifest.json').read_text(encoding='utf-8'))
            for entry in manifest['migrations']:
                body=(preserved/'schema'/entry['name']).read_bytes()
                self.assertEqual('sha256:'+hashlib.sha256(body).hexdigest(),entry['sha256'])
            with patch('corpustrail._internal.database.resources.files',return_value=preserved):
                self.assertEqual(len(migrations()),len(manifest['migrations']))
            # A real byte corruption is still refused, never normalized away.
            first=preserved/'schema/001_core.sql';first.write_bytes(first.read_bytes()+b' ')
            with patch('corpustrail._internal.database.resources.files',return_value=preserved):
                with self.assertRaisesRegex(ContractError,'schema resource hash mismatch'):migrations()

    def test_windows_lifecycle_step_uses_fail_closed_bash(self):
        workflow=(ROOT/'.github/workflows/standalone.yml').read_text(encoding='utf-8')
        step=workflow.split('      - name: Core installation and real-process guards (no native dependency)',1)[1].split('      - name:',1)[0]
        self.assertIn('shell: bash',step)
        self.assertNotIn('continue-on-error',step)
        self.assertIn("test_reference*.py",step)
        self.assertIn('test_xml_safety.py',step)

    @unittest.skipUnless(shutil.which('bash'), 'Native exit propagation needs the CI bash shell')
    def test_failed_native_command_prevents_later_success_from_hiding_it(self):
        result=subprocess.run(['bash','--noprofile','--norc','-e','-o','pipefail','-c',
            '"$1" -c "raise SystemExit(7)"\n"$1" -c "print(\"SHOULD_NOT_RUN\")"',
            'controlled-native-failure',__import__('sys').executable],capture_output=True,text=True)
        self.assertEqual(result.returncode,7)
        self.assertNotIn('SHOULD_NOT_RUN',result.stdout)
