"""Read-only, fail-closed pre-commit check. Never print a rejected identity."""
import argparse
import json
from pathlib import Path
import re
import subprocess

NEUTRAL_NAME = 'CorpusTrail'
NEUTRAL_EMAIL = 'noreply@corpustrail.invalid'


def verify(root, *, git_options=()):
    checks = []
    for role in ('AUTHOR', 'COMMITTER'):
        result = subprocess.run(['git', *git_options, 'var', 'GIT_' + role + '_IDENT'],
                                cwd=Path(root), text=True, capture_output=True)
        match = re.fullmatch(r'(.+) <([^<>]+)> \d+ [+-]\d{4}\s*', result.stdout)
        ok = bool(result.returncode == 0 and match and match.groups() == (NEUTRAL_NAME, NEUTRAL_EMAIL))
        checks.append({'role': role.lower(), 'ok': ok})
    return {'ok': all(x['ok'] for x in checks), 'checks': checks,
            'required_identity': {'name': NEUTRAL_NAME, 'email': NEUTRAL_EMAIL},
            'config_modified': False, 'account_linked': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path, default=Path('.'))
    result = verify(parser.parse_args().directory)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
