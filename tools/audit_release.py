"""Read-only code-only staged-tree checks; no secret values are printed.

Bounded heuristics plus a frozen file population, not a comprehensive rights,
privacy or security certification. Use on the pristine pre-Git release tree.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

MANIFEST = 'release_candidate_manifest_v0.1.0a1.anonymized.json'
PATTERNS = {
    'credential_signature': r'(?:sk-ant-api\d+-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})',
    'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'private_local_path': r'(?:/(?:home|Users)/[A-Za-z0-9._-]+/|[A-Z]:\\Users\\[^\\\s]+\\)',
    'credential_url': r'https?://[^/\s:@]+:[^/\s@]+@',
    'questionable_acquisition_url': r'https?://[^/\s]*(?:sci-hub|libgen|z-library|z-lib\.)',
    'email': r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
    'orcid_identifier': r'(?<![\w-])\d{4}-\d{4}-\d{4}-\d{3}[\dX](?![\w-])',
    'personal_contact_field': r'(?im)^\s*["\']?(?:author_email|maintainer_email|affiliation|institutional_address|phone_number|postal_address|personal_website|orcid)["\']?\s*[:=]\s*["\']?[^\s"\'\],}]+',
}
SAFE_PLACEHOLDER_EMAIL = re.compile(r'^[^@]+@(?:example\.(?:com|org|net|test)|[^@]+\.test)$')
NEUTRAL_GIT_EMAIL = 'noreply@corpustrail.invalid'


def inspect_text(text, path, *, private_terms=()):
    """Return redacted match categories, never matched identity/credential values.

    Known owner identities are supplied locally, not committed to this tool.
    Third-party/fixture matches must be reviewed, not deleted automatically.
    """
    text = unicodedata.normalize('NFKC', text)
    findings, classified = [], []
    for category, pattern in PATTERNS.items():
        matches = re.findall(pattern, text)
        if category == 'email':
            matches = [x for x in matches if not SAFE_PLACEHOLDER_EMAIL.fullmatch(x)
                       and x != NEUTRAL_GIT_EMAIL]
        if matches:
            findings.append({'path': path, 'category': category, 'count': len(matches)})
    for term in private_terms:
        if not isinstance(term, str) or not term.strip():
            raise ValueError('private identity terms must be non-empty strings')
        term = unicodedata.normalize('NFKC', term)
        matches = list(re.finditer(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I))
        if not matches:
            continue
        # Short initials can also be a standard Python binary file mode. Exempt
        # only an actual .open('mode') call, never attribution/free prose matches.
        modes = list(re.finditer(r'\.open\(\s*[\'"](?P<mode>[rawx]b|b[rawx])[\'"]', text)) if path.endswith('.py') else []
        remaining = [m for m in matches if not any(m.span() == mode.span('mode') for mode in modes)]
        if len(remaining) != len(matches):
            classified.append({'path': path, 'category': 'python_binary_file_mode_not_personal_initials'})
        if remaining:
            findings.append({'path': path, 'category': 'known_personal_identity', 'count': len(remaining)})
    if re.search(r'\bUPE\b|is_human|biophoton|mitogenetic', text, re.I):
        classified.append({'path': path, 'category': 'legacy_scope_marker_requires_context'})
    return findings, classified


def audit(root, *, private_terms=()):
    root = Path(root).resolve()
    manifest_path = root / MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError('regular frozen release manifest required')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    expected = {x['path']: x for x in manifest['files']}
    if len(expected) != len(manifest['files']):
        raise ValueError('duplicate manifest paths')
    findings, classified = [], []
    actual = set()
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            findings.append({'path': name, 'category': 'symlink'})
            continue
        if path.is_dir():
            if name == '.git':
                findings.append({'path': name, 'category': 'unexpected_git_history'})
            continue
        actual.add(name)
        if name not in expected and name != MANIFEST:
            findings.append({'path': name, 'category': 'outside_frozen_population'})
            continue
        raw = path.read_bytes()
        if name in expected and (len(raw) != expected[name]['bytes'] or
                'sha256:' + hashlib.sha256(raw).hexdigest() != expected[name]['sha256']):
            findings.append({'path': name, 'category': 'content_hash_changed'})
        if raw.startswith((b'%PDF', b'SQLite format 3', b'PK\x03\x04', b'\x1f\x8b')):
            findings.append({'path': name, 'category': 'forbidden_binary_signature'})
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            findings.append({'path': name, 'category': 'unexpected_binary'})
            continue
        found, contexts = inspect_text(text, name, private_terms=private_terms)
        findings.extend(found)
        classified.extend(contexts)
        named, _ = inspect_text(name, name, private_terms=private_terms)
        findings.extend(named)
    for missing in sorted(set(expected) - actual):
        findings.append({'path': missing, 'category': 'missing_frozen_file'})
    return {'schema': 'corpustrail-clean-tree-audit/v2', 'product_files': len(expected),
            'total_files': len(actual), 'manifest_sha256': 'sha256:' + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'findings': findings, 'scope_markers': classified, 'ok': not findings,
            'private_identity_terms_checked': len(private_terms),
            'limitations': 'Heuristics do not prove absence of opaque secrets or article text; fixture/source provenance must also be inspected.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--private-terms', type=Path, help='Local JSON string list of known identity variants; never bundle/commit it')
    args = parser.parse_args()
    terms = json.loads(args.private_terms.read_text(encoding='utf-8')) if args.private_terms else []
    if not isinstance(terms, list):
        parser.error('private identity terms must be a JSON list')
    result = audit(args.root, private_terms=terms)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
