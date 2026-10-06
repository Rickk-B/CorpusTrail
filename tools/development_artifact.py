"""CI-only development-wheel receipt. Never changes package/scientific state."""

import argparse
from datetime import datetime, timezone
import email
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = {'corpustrail/local_app/assets/index.html',
            'corpustrail/local_app/assets/app.css', 'corpustrail/local_app/assets/app.js'}
# Explicitly reviewed presentation boundary, not permission for scientific changes.
PRESENTATION_PATHS = {'src/' + name for name in FRONTEND} | {'src/corpustrail/application/reads.py'}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def check_source(root, expected):
    if not re.fullmatch(r'[0-9a-f]{40}', expected):
        raise ValueError('expected commit must be a full GitHub commit SHA')
    if git(root, 'rev-parse', 'HEAD') != expected:
        raise ValueError('checkout differs from the requested exact commit')
    if git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('development artifact requires a clean source checkout')
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    version = config['project']['version']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+a[0-9]+\.dev[0-9]+', version):
        raise ValueError('development artifacts require an alpha .dev version, not a release version')
    return {'commit_sha': expected, 'tree_sha': git(root, 'rev-parse', 'HEAD^{tree}'), 'version': version}


def check_implementation(root, implementation, expected, *, distribution=None):
    """Keep the completed scientific checkpoint distinct from CI follow-up source."""
    if not re.fullmatch(r'[0-9a-f]{40}', implementation):
        raise ValueError('implementation commit must be a full commit SHA')
    if git(root, 'cat-file', '-t', implementation) != 'commit':
        raise ValueError('implementation identity must refer to a commit')
    relation = subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', implementation, expected])
    if relation.returncode != 0:
        raise ValueError('artifact source must descend from the implementation checkpoint')
    changed = set(git(root, 'diff', '--name-only', implementation, expected, '--', 'src/corpustrail/').splitlines())
    if changed and (distribution is None or changed - PRESENTATION_PATHS):
        raise ValueError('Checkpoint 1 application/scientific source must remain unchanged')
    if distribution is not None:
        if not re.fullmatch(r'[0-9a-f]{40}', distribution) or git(root, 'cat-file', '-t', distribution) != 'commit':
            raise ValueError('distribution follow-up must be a full commit identity')
        for earlier, later in ((implementation, distribution), (distribution, expected)):
            if subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', earlier, later]).returncode:
                raise ValueError('implementation, distribution and artifact source lineage must be ordered')
        if git(root, 'diff', '--name-only', implementation, distribution, '--', 'src/corpustrail/'):
            raise ValueError('original CI/distribution follow-up must preserve implementation source')
    return {'name': 'Checkpoint 1 — read-only dashboard and paper browser',
            'implementation_commit_sha': implementation,
            'implementation_tree_sha': git(root, 'rev-parse', implementation + '^{tree}'),
            'application_source_unchanged': not bool(changed),
            'scientific_source_unchanged': True,
            'presentation_paths_changed': sorted(changed),
            'previous_distribution_commit_sha': distribution,
            'notice': 'Implementation lineage, not the artifact build/source commit.'}


def inspect_wheel(path, version):
    if path.is_symlink() or not path.is_file():
        raise ValueError('wheel must be a regular build artifact')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_paths = [name for name in names if name.endswith('.dist-info/METADATA')]
        if len(metadata_paths) != 1 or not FRONTEND <= set(names):
            raise ValueError('wheel metadata or packaged frontend is incomplete')
        metadata = email.message_from_bytes(archive.read(metadata_paths[0]))
        if metadata['Name'] != 'corpus-trail' or metadata['Version'] != version:
            raise ValueError('wheel package/version differs from source configuration')
        if metadata['License-Expression'] != 'MIT' or any(metadata.get(key) for key in (
                'Author', 'Author-email', 'Maintainer', 'Maintainer-email')):
            raise ValueError('wheel license/privacy metadata differs from project policy')
        for key in metadata.get_all('Requires-Dist', []):
            if 'extra ==' not in key:
                raise ValueError('core wheel unexpectedly requires a runtime dependency')
    return {'filename': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


def installed_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def bundle(root, expected, validation_dir, output_dir, *, implementation, context, distribution=None):
    source = check_source(root, expected)
    checkpoint = check_implementation(root, implementation, expected, distribution=distribution)
    wheels = list((root / 'dist').glob('*.whl'))
    if len(wheels) != 1:
        raise ValueError('expected exactly one newly built wheel')
    wheel = inspect_wheel(wheels[0], source['version'])
    tests = validation_dir / 'development-tests.txt'
    tutorial = validation_dir / 'development-tutorial.json'
    installed = validation_dir / 'development-version.txt'
    if not re.search(r'\nRan \d+ tests in ', tests.read_text(encoding='utf-8')) or not re.search(
            r'\nOK(?: \(skipped=\d+\))?\s*$', tests.read_text(encoding='utf-8')):
        raise ValueError('successful installed-wheel test receipt is required')
    if installed.read_text(encoding='utf-8').strip() != source['version']:
        raise ValueError('installed CLI version differs from wheel/source')
    if json.loads(tutorial.read_text(encoding='utf-8')).get('network_used') is not False:
        raise ValueError('offline tutorial receipt is required')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', context['repository']):
        raise ValueError('repository identity is required, not an arbitrary URL')
    if not context['ref'].startswith('refs/heads/development/'):
        raise ValueError('only a development branch can publish a development artifact')
    if any(not re.fullmatch(r'[0-9]+', context[key]) for key in ('run_id', 'run_attempt')):
        raise ValueError('numeric workflow run identity is required')
    name = 'corpustrail-dev-' + source['version'] + '-' + expected + '-run-' + context['run_id'] + '-' + context['run_attempt']
    output_dir.mkdir(parents=True, exist_ok=False)  # Never overwrite a prior bundle.
    files = {}
    for path in (wheels[0], tests, tutorial, installed):
        shutil.copyfile(path, output_dir / path.name)
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {'schema': 'corpustrail-development-artifact/v1', 'status': 'unreleased_development_checkpoint',
              'source': source, 'checkpoint': checkpoint, 'wheel': wheel, 'workflow': context, 'artifact_name': name,
              'validation': {'upstream_python_matrix': ['3.11', '3.12', '3.13'],
                             'installed_artifact_python': sys.version.split()[0],
                             'installed_core_tests': 'passed', 'offline_tutorial': 'passed'},
              'build': {'python': sys.version.split()[0],
                        'setuptools': installed_version('setuptools')},
              'created_at': datetime.now(timezone.utc).isoformat(), 'files_sha256': files,
              'notice': 'Not a GitHub Release or PyPI package. Verify the source SHA against the workflow run. '
                        'The receipt is not a cryptographic attestation. No real provider/model calls were used.'}
    (output_dir / 'build-provenance.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    (output_dir / 'SHA256SUMS').write_text(''.join(f'{value}  {key}\n' for key, value in sorted(files.items())) +
        hashlib.sha256((output_dir / 'build-provenance.json').read_bytes()).hexdigest() + '  build-provenance.json\n', encoding='utf-8')
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check-source', 'bundle'))
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--implementation-commit', required=True)
    parser.add_argument('--distribution-commit')
    parser.add_argument('--validation-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.action == 'check-source':
        print(json.dumps({'source': check_source(ROOT, args.expected_commit),
                          'checkpoint': check_implementation(ROOT, args.implementation_commit, args.expected_commit,
                                                             distribution=args.distribution_commit)}))
        return
    if args.validation_dir is None or args.output_dir is None:
        parser.error('bundle requires --validation-dir and --output-dir')
    # Explicit allowlist only; never dump environment, token, actor or Git identity.
    context = {key: os.environ[env] for key, env in (
        ('repository', 'GITHUB_REPOSITORY'), ('ref', 'GITHUB_REF'),
        ('run_id', 'GITHUB_RUN_ID'), ('run_attempt', 'GITHUB_RUN_ATTEMPT'))}
    name = bundle(ROOT, args.expected_commit, args.validation_dir, args.output_dir,
                  implementation=args.implementation_commit, distribution=args.distribution_commit, context=context)
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as handle:
        handle.write('artifact_name=' + name + '\n')
    print(name)


if __name__ == '__main__':
    main()
