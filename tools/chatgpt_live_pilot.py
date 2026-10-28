"""Owner-run preparation for ONE synthetic pilot; never signs in or sends requests.

Run with the delivered wheel installed. This helper is not part of the wheel.
No credential or token is printed. Provider controls are observed, never changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

from corpustrail._internal.pipeline import preserve
from corpustrail._internal.values import ContractError, canonical, now
from corpustrail.application.project_use import creation_use, no_links, project_use
from corpustrail.chatgpt.connection import DIRECT
from corpustrail.chatgpt.credentials import CredentialStore
from corpustrail.identity import BibliographicRecord, SourceReference
from corpustrail.project import Project, ProjectConfig, ReviewPolicy

MARKER = 'chatgpt-one-paper-pilot.json'
SCHEMA = 'corpustrail-owner-one-paper-pilot/v1'
CONFIRMATION = 'I observed CorpusTrail plan usage enabled and credit fallback disabled'
TITLE = 'Synthetic sensor measurement — one-paper interoperability pilot'
ABSTRACT = ('This invented paper describes a sensor measurement method for a fictional materials sample. '
            'It is synthetic software-test text, not a real publication or scientific evidence.')
SCOPE = ('Synthetic materials-sensor literature for software interoperability evaluation only. '
         'Relevant measurement or methods papers are in scope. Missing evidence is not exclusion.')


def prepare(root):
    """Create new material via existing services; no human judgments are seeded."""
    target = no_links(Path(root).expanduser().absolute(), missing=True)
    with creation_use(target):
        project = Project.create(target, ProjectConfig('chatgpt-pilot-' + uuid.uuid4().hex,
            'ONE synthetic paper — ChatGPT interoperability pilot', SCOPE,
            review=ReviewPolicy(scope=SCOPE, authorized_reviewers=('pilot_owner',))),
            created_by='synthetic-pilot-preparation')
        created = now()
        raw = canonical({'synthetic': True, 'title': TITLE, 'abstract': ABSTRACT}).encode('utf-8')
        sha = preserve(project, raw, 'application/json', created)
        record = BibliographicRecord(TITLE, authors=('Invented Author',), abstract=ABSTRACT)
        source = SourceReference('fixture://chatgpt-one-paper-pilot', 'one', sha, len(raw),
            'synthetic-pilot-preparation', created, identity_status='verified')
        pid = project.identities.apply(project.identities.plan(record, source),
            approve_new_identity=True, approve_aliases=True)
        fields = {'request_id': uuid.uuid4().hex, 'name': 'ONE synthetic assessment target',
            'actor': 'synthetic-pilot-preparation', 'sources': [{'kind': 'all'}]}
        preview = project.populations.preview(**fields)
        pop = project.populations.create(**fields, expected_preview_sha256=preview['preview_sha256'])
        # Required version identity without inventing a human-attested label.
        # This source proposal is ineligible; self-match is also excluded.
        fields = {'request_id': uuid.uuid4().hex, 'name': 'Synthetic placeholder — NO eligible examples',
            'actor': 'synthetic-pilot-preparation', 'parent': None, 'created_at': created,
            'config_event_id': project.configuration_history()[-1]['event_id'],
            'changes': [{'action': 'assign', 'paper_id': pid, 'label': 'in_scope',
                'producer': {'type': 'imported', 'id': 'synthetic-pilot-preparation', 'version': 'v1'},
                'human_attested': False, 'rationale': 'Unattested synthetic placeholder, not human reference truth.',
                'evidence_used': [], 'supersedes': [], 'source_assignment_ids': [], 'source_event_id': None,
                'source_artifact_sha256': sha, 'source_record': 'one'}]}
        preview = project.references.preview(**fields)
        ref = project.references.commit(**fields, expected_preview_sha256=preview['preview_sha256'])
        if (pop['member_count'] != 1 or ref['counts']['unattested'] != 1
                or project.reviews.membership(pid)['state'] != 'not_reviewed'
                or project.reviews.history(pid)):
            raise ContractError('Synthetic preparation did not preserve the required one-paper authority boundary.')
        marker = {'schema': SCHEMA, 'project_id': project.config.project_id, 'synthetic': True,
            'paper_id': pid, 'title': TITLE, 'abstract': ABSTRACT,
            'population_version_id': pop['version_id'], 'reference_version_id': ref['version_id'],
            'source_sha256': sha, 'created_at': created,
            'membership_before': 'not_reviewed', 'human_observations_before': 0,
            'human_attested_references': 0, 'network_used': False}
        with (target / MARKER).open('x', encoding='utf-8') as out:
            out.write(json.dumps(marker, indent=2, ensure_ascii=False) + '\n')
    return {'prepared': True, 'synthetic': True, 'publications': 1, 'human_judgments': 0,
        'membership_decisions': 0, 'eligible_reference_examples': 0, 'network_used': False,
        'next': 'Launch this project, then Research tools → Models → Open ChatGPT assessment.'}


def inspect(root):
    """Read only; do not retry, execute, refresh credentials or contact a provider."""
    target = no_links(Path(root).expanduser().absolute())
    with project_use(target):
        marker = json.loads((target / MARKER).read_text(encoding='utf-8'))
        if marker.get('schema') != SCHEMA or marker.get('synthetic') is not True:
            raise ContractError('Inspect only the explicitly prepared synthetic pilot.')
        project = Project.open(target)
        if project.config.project_id != marker['project_id'] or project.identities.papers() != [marker['paper_id']]:
            raise ContractError('Pilot project identity or candidate count changed.')
        project.populations.verify(marker['population_version_id'])
        project.references.verify(marker['reference_version_id'])
        membership = project.reviews.membership(marker['paper_id'])['state']
        history = project.reviews.history(marker['paper_id'])
        runs = project.classification.runs(limit=20)
        items = []
        for item in runs['items']:
            rid = item['run_id']; run = project.classification.inspect_run(rid)
            results = project.classification.results(rid)['items']
            items.append({'run_id': rid, 'status': run['status'], 'processed': run['processed'],
                'candidates': run['candidate_count'], 'results': [
                    {'kind': r['kind'], 'outcome': r.get('assessment', {}).get('outcome'),
                     'reported_model': r.get('assessment', {}).get('reported_model'),
                     'failure_category': r.get('failure', {}).get('diagnostics', {}).get('category')}
                    for r in results]})
        return {'synthetic': True, 'publications': 1, 'membership': membership,
            'membership_unchanged': membership == marker['membership_before'],
            'human_observations': len(history), 'assessment_runs': runs['total'], 'runs': items,
            'network_used': False,
            'warning': 'More than one run exceeds the one-request pilot; do not retry ambiguous outcomes.' if runs['total'] > 1 else None}


def record_no_charge(confirmation, *, store=None):
    """Record an owner's actual observation, not inference consent or a setting change."""
    if confirmation != CONFIRMATION:
        raise ContractError('Record only an actual observed app-specific credit-fallback OFF control.')
    store = store if store is not None else CredentialStore()
    observed = now()
    evidence = {'schema': 'corpustrail-owner-plan-only-observation/v1', 'observed_at': observed,
        'source': 'https://chatgpt.com/settings/usage', 'app': 'CorpusTrail',
        'plan_usage_enabled': True, 'credits_after_plan_limits_enabled': False,
        'owner_statement': CONFIRMATION, 'purpose': 'One explicitly approved synthetic interoperability request.'}
    digest = hashlib.sha256(canonical(evidence).encode('utf-8')).hexdigest()
    with store.transaction() as state:
        profile = state['profiles'].get(state['active'])
        if (not isinstance(profile, dict) or not all(isinstance(profile.get(k), str) and profile[k]
                for k in ('client_id', 'subject', 'refresh_token', 'scope'))
                or DIRECT not in profile['scope'].split()):
            raise ContractError('Complete eligible sign-in on this same installation first.')
        profile['plan_only_permit'] = {'client_id': profile['client_id'], 'subject': profile['subject'],
            'credits_disabled_verified': True, 'owner_evidence_sha256': digest,
            'owner_evidence': evidence, 'expires_at': time.time() + 1800}
    return {'recorded': True, 'owner_evidence_sha256': digest, 'valid_for_minutes': 30,
        'provider_settings_changed': False, 'inference_authorized': False, 'network_used': False,
        'next': 'Prepare a new exact preview; obtain separate owner approval of its model/payload before submission.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('prepare', 'inspect'):
        sub.add_parser(name).add_argument('project')
    sub.add_parser('record-no-charge')
    args = parser.parse_args()
    try:
        if args.action == 'record-no-charge':
            print('Only if you actually observed BOTH controls for this CorpusTrail registration:')
            print('Use ChatGPT plan: enabled. Use credits after plan limits: disabled.')
            print('A percentage cap, zero balance or successful sign-in alone is insufficient.')
            print('No provider setting or billing change will be made. No assessment will be sent.')
            print('Type exactly: ' + CONFIRMATION)
            result = record_no_charge(input('Owner observation: '))
        else:
            result = prepare(args.project) if args.action == 'prepare' else inspect(args.project)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ContractError, OSError, KeyError, ValueError, TypeError, AttributeError, EOFError, KeyboardInterrupt):
        # Never dump credential records, raw exceptions or account-specific paths.
        print('Pilot operation stopped. Check the fresh project path or required owner observation; no request was sent.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
