"""Exact code-only future-repository population; no copying/publication occurs."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT_FILES = {'README.md', 'LICENSE', 'NOTICE.md', 'CHANGELOG.md', 'CONTRIBUTING.md',
              'SECURITY.md', 'pyproject.toml', 'MANIFEST.in', '.gitignore'}
RECEIPTS = {'docs/phase2b_migration_origins.json', 'docs/phase2c_migration_origins.json'}
TOOLS = {'tools/smoke_install.py', 'tools/smoke_asreview.py', 'tools/release_manifest.py',
         'tools/validation-constraints.txt', 'tools/audit_release.py', 'tools/verify_git_identity.py'}
FIXTURE_DATA = {'examples/synthetic-materials/records.json', 'examples/synthetic-discovery/responses.json',
                'examples/synthetic-discovery/article.xml'}
EXCLUDED = ['docs/PHASE* engineering archives', 'docs/*_smoke*.json build/runtime receipts',
            'docs/*preservation*.json private research preservation receipts',
            'docs/developer/ALPHA_HARDENING_REPORT.md engineering checkpoint report',
            'docs/decisions/ archived pre-approval decision packet',
            'release_candidate_manifest.json (manifest itself; avoid recursive hashing)',
            'release_candidate_manifest_v0.1.0a1.json (companion manifest; avoid recursive hashing)',
            'release_candidate_manifest_v0.1.0a1.anonymized.json (privacy-scrub companion manifest)',
            'all files outside standalone candidate: research corpus/reviews/models/benchmarks',
            'PDFs, credentials, databases/backups, caches, logs, runtime and temporary files']


def eligible(path):
    if any(part in {'__pycache__', '.venv', 'build', 'dist'} or part.endswith('.egg-info') for part in Path(path).parts):
        return False
    if path in ROOT_FILES | RECEIPTS | TOOLS | FIXTURE_DATA:
        return True
    if path.startswith('src/corpustrail/'):
        return path.endswith(('.py', '.sql', '.json'))
    if path.startswith(('tests/', 'examples/')):
        return path.endswith('.py')
    if path == 'docs/developer/ALPHA_HARDENING_REPORT.md':
        return False
    if path.startswith(('docs/user/', 'docs/developer/')):
        return path.endswith(('.md', '.json'))
    return path == '.github/workflows/standalone.yml'


def build(root):
    records = []
    for file in sorted(root.rglob('*')):
        path = file.relative_to(root).as_posix()
        if not eligible(path):
            continue
        if file.is_symlink() or not file.is_file():
            raise ValueError('allowlisted content must be a regular non-symlink file: ' + path)
        raw = file.read_bytes()
        if raw.startswith(b'%PDF'):
            raise ValueError('real PDF signature forbidden in release population')
        records.append({'path': path, 'bytes': len(raw), 'sha256': 'sha256:' + hashlib.sha256(raw).hexdigest()})
    paths = {x['path'] for x in records}
    required = ROOT_FILES | RECEIPTS | TOOLS | FIXTURE_DATA | {
        'src/corpustrail/resources/origins.json', 'src/corpustrail/tutorial.py',
        '.github/workflows/standalone.yml', 'docs/user/TUTORIAL.md'}
    if required - paths:
        raise ValueError('missing required release files: ' + ', '.join(sorted(required - paths)))
    return {'schema': 'corpustrail-code-only-staging/v3', 'version': '0.1.0a1',
            'base_manifest_sha256': 'sha256:9edc813543439eb064cbe82d53a4d111cf6977eef904a7db69c8fce6b676b6c5',
            'previous_candidate_manifest_sha256': 'sha256:00e8a7680beaf85b5562ea8e3122394b17f416a107fc7c380207c2475f165ab8',
            'privacy_scrubbed': True,
            'neutral_git_identity': {'name': 'CorpusTrail', 'email': 'noreply@corpustrail.invalid', 'account_linked': False},
            'license': 'MIT', 'authors_and_maintainers': 'omitted', 'citation': 'deferred_optional',
            'release_ready': False, 'pending': ['explicit remote creation/publication authorization'],
            'files': records, 'exclusions': EXCLUDED,
            'privacy_note': 'Allowlist is technical staging, not proof of rights or secret-free free text.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path, help='Compare a frozen manifest; never overwrite/copy files')
    args = parser.parse_args()
    result = build(Path(__file__).resolve().parents[1])
    if args.check and json.loads(args.check.read_text(encoding='utf-8')) != result:
        parser.error('release-candidate file set/hash differs from frozen manifest')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
