"""Freeze the existing exact population/evidence/reference contracts once.

Planning retains compact hashes; a commit streams bounded records into the store.
Full reference text is stored once per content hash and is streamed to engines.
"""
from datetime import datetime
from importlib import resources
import json

from corpustrail import __version__
from corpustrail._internal.database import latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, digest_bytes
from corpustrail.populations.service import _stored, PopulationService
from corpustrail.references import storage as refs, evidence, context
from corpustrail.references.contracts import POLICY
from corpustrail.references.service import definition
from .contracts import SCHEMA, json_value


def implementation_hash():
    package = resources.files('corpustrail.classification')
    return content_hash({p.name: digest_bytes(p.read_bytes()) for p in package.iterdir() if p.name.endswith('.py')})


def freeze(project, db, fields, *, sink=None):
    revision, config = latest_config(db)
    if revision != fields['config_event_id']:
        raise ContractError('assessment configuration changed; prepare a new plan explicitly')
    scope = definition(config); scope_sha = content_hash(scope)
    population, candidates, _ = _stored(db, fields['population_version_id'])
    if population['project_id'] != config['project_id']:
        raise ContractError('candidate population belongs to another project')
    reference, assignments = refs.stored(db, fields['reference_version_id'])
    if reference['definition_sha256'] != scope_sha:
        raise ContractError('reference scope differs from the current corpus definition')
    protocol = fields['validation']
    role_ids = {}; labels = {}; label_sources = {}
    paper_labels = {}
    for aid, data in assignments.items(): paper_labels.setdefault(data['paper_id'], set()).add(data['label'])
    cutoff = datetime.fromisoformat(protocol['label_cutoff']) if protocol['label_cutoff'] else None
    if cutoff and cutoff > datetime.fromisoformat(fields['created_at']):
        raise ContractError('label cutoff cannot be after plan preparation')
    for role in ('calibration', 'held_out'):
        vid = protocol[role + '_population_version']
        role_ids[role] = set(project.populations.review_ids(db, vid)) if vid else set()
    if role_ids['calibration'] & role_ids['held_out']:
        raise ContractError('calibration and held-out populations must be disjoint')
    for pid in role_ids['calibration'] | role_ids['held_out']:
        choices = [(aid, a) for aid, a in assignments.items() if a['paper_id'] == pid and a['human_attested']
                   and a['producer']['type'] == 'human' and a['definition_sha256'] == scope_sha
                   and (cutoff is None or datetime.fromisoformat(a['created_at']) <= cutoff)]
        if len(paper_labels.get(pid, set())) != 1 or not choices:
            raise ContractError('validation requires exact unconflicted human reference labels available at the cutoff')
        aid, value = sorted(choices)[0]
        labels[pid] = value['label']
        label_sources[pid] = {'assignment_id': aid, 'assignment_sha256': content_hash(value),
            'label': value['label'], 'source_event': value['source_event'], 'available_at': value['created_at'],
            'reference_version_id': fields['reference_version_id'], 'definition_sha256': scope_sha}
    purpose = protocol['purpose']
    role = 'held_out' if purpose == 'held_out_evaluation' else 'calibration'
    if purpose != 'operational' and not set(candidates) <= role_ids[role]:
        raise ContractError('validation candidates must belong to the declared frozen validation role')
    excluded = role_ids['calibration'] | role_ids['held_out']
    reference_rows = []; omission_counts = {}; seen = set(); reference_bytes = 0
    for aid, value in sorted(assignments.items(), key=lambda pair: (pair[1]['paper_id'], pair[0])):
        pid = value['paper_id']; reason = None
        if pid in excluded: reason = 'validation_role'
        elif len(paper_labels[pid]) != 1: reason = 'conflicting_labels'
        elif not value['human_attested'] or value['producer']['type'] != 'human': reason = 'unattested_source'
        elif value['definition_sha256'] != scope_sha: reason = 'definition_mismatch'
        elif cutoff and datetime.fromisoformat(value['created_at']) > cutoff: reason = 'after_label_cutoff'
        elif not value['evidence']['used']: reason = 'no_attested_evidence'
        elif pid in seen: reason = 'duplicate_canonical_reference'
        record = {'paper_id': pid, 'assignment_id': aid, 'assignment_sha256': content_hash(value),
                  'decision': 'omitted' if reason else 'eligible', 'reason': reason}
        body = None
        if reason:
            omission_counts[reason] = omission_counts.get(reason, 0) + 1
        else:
            PopulationService._identity(db, pid)
            kind = next(k for k in ('structured_text', 'abstract', 'metadata') if k in value['evidence']['used'])
            representation = value['evidence']['available'][kind]
            if fields['input_mode'] == 'full_set':
                payload = {'paper_id': pid, 'assignment_id': aid, 'label': value['label'],
                    'producer': value['producer'], 'human_attested': True, 'rationale': value['rationale'],
                    'representation': {'kind': kind, 'sha256': representation['sha256']},
                    'text': evidence.resolve(project, db, pid, representation)}
                body = json_value(payload, fields['budgets']['max_input_bytes']).encode()
                reference_bytes += len(body)
            seen.add(pid)
            record.update(input_blob_sha256=digest_bytes(body) if body is not None else None,
                          evidence_sha256=representation['sha256'], label=value['label'],
                          input_bytes=len(body) if body is not None else 0)
        if sink: sink('reference', len(reference_rows), record, body)
        reference_rows.append(record)
    if reference_bytes > fields['budgets']['max_reference_bytes']:
        raise ContractError('full reference input exceeds its explicit byte budget; no references were silently dropped')
    full_root = content_hash(reference_rows)
    contexts = {}
    if fields['input_mode'] == 'bounded_context':
        for cid in fields['context_ids']:
            head, body = context.verify_in_connection(db, cid)
            target = json.loads(body)['target']['paper_id']
            if target in contexts or target not in candidates: raise ContractError('one exact selected context per candidate required')
            if head['reference_version_id'] != fields['reference_version_id'] or head['config_event_id'] != revision:
                raise ContractError('selected context uses another reference/configuration version')
            if head['definition_sha256'] != scope_sha or head['eligibility_policy'] != POLICY:
                raise ContractError('selected context eligibility/scope differs')
            if not excluded <= set(head['held_out_paper_ids']):
                raise ContractError('selected context does not exclude every validation role')
            if head['strategy']['self_match'] != protocol['self_match']:
                raise ContractError('selected context self-match policy differs')
            payload = json.loads(body)
            selected = payload['references']
            eligible_ids = {r['assignment_id'] for r in reference_rows if r['decision'] == 'eligible'}
            if any(r['assignment_id'] not in eligible_ids for r in selected):
                raise ContractError('selected context includes a label ineligible for this assessment protocol')
            if purpose != 'operational' and (payload['derived'] or not head['independent_evaluation']):
                raise ContractError('independent validation cannot consume contaminated derived context')
            contexts[target] = (cid, head, payload)
        if set(contexts) != set(candidates): raise ContractError('bounded input requires a frozen context for every exact candidate')
    elif fields['context_ids']:
        raise ContractError('full-set inputs cannot silently also consume bounded contexts')
    input_hashes = []; input_total = 0
    for position, pid in enumerate(sorted(candidates)):
        identity = PopulationService._identity(db, pid)
        if fields['input_mode'] == 'full_set':
            available = evidence.freeze(project, db, pid, [])
            basis = fields['evidence_basis']
            if basis == 'best_available': basis = next(k for k in ('structured_text', 'abstract', 'metadata') if k in available['available'])
            if basis not in available['available']: raise ContractError('explicit candidate evidence basis is unavailable; replan without silent fallback')
            snapshot = evidence.freeze(project, db, pid, [basis])
            entry = snapshot['available'][basis]
            selected = [r for r in reference_rows if r['decision'] == 'eligible' and (protocol['self_match'] != 'exclude' or r['paper_id'] != pid)]
            target = {'paper_id': pid, 'representation': {'kind': basis, 'sha256': entry['sha256']},
                      'text': evidence.resolve(project, db, pid, entry)}
            payload = {'schema': 'corpustrail-classifier-input/v1', 'definition': scope, 'target': target,
                'reference_version_id': fields['reference_version_id'], 'eligibility_policy': POLICY,
                'reference_input_manifest_sha256': content_hash([r['input_blob_sha256'] for r in selected]),
                'reference_source_manifest_sha256': full_root,
                'reference_selection': {'strategy': 'complete-eligible-reference-set/v1', 'self_match': protocol['self_match']}}
            # Full-set reference evidence is normalized in the shared reference
            # manifest, not copied N times into N candidate inspection rows.
            hashes = [entry['sha256']]
            context_id = None; selected_count = len(selected)
        else:
            context_id, head, payload = contexts[pid]
            snapshot = head['target_evidence']; target = payload['target']
            selected_count = head['selected_count']
            hashes = sorted({r['representation']['sha256'] for r in payload['references']} | {target['representation']['sha256']} | {r['body_sha256'] for r in payload['derived']})
        body = json_value(payload, fields['budgets']['max_input_bytes']).encode()
        record = {'paper_id': pid, 'identity_sha256': content_hash(identity), 'evidence_snapshot': snapshot,
            'evidence_snapshot_sha256': content_hash(snapshot), 'context_id': context_id,
            'context_input_sha256': head['input_sha256'] if context_id else None,
            'reference_count': selected_count, 'inline_evidence_hashes': hashes,
            'input_blob_sha256': digest_bytes(body), 'input_bytes': len(body)}
        if sink: sink('candidate', position, record, body)
        input_hashes.append(content_hash(record)); input_total += len(body)
    descriptor = {'schema': SCHEMA, 'project_id': config['project_id'], 'population_version_id': fields['population_version_id'],
        'population_manifest_sha256': population['manifest_sha256'], 'candidate_count': len(candidates),
        'definition': scope, 'definition_sha256': scope_sha, 'config_event_id': revision,
        'reference_version_id': fields['reference_version_id'], 'reference_manifest_sha256': reference['manifest_sha256'],
        'eligibility_policy': POLICY, 'input_mode': fields['input_mode'], 'evidence_basis': fields['evidence_basis'],
        'policy': fields['policy'], 'calibration': fields['calibration'], 'validation_protocol_sha256': content_hash(protocol),
        'self_match': protocol['self_match'], 'budgets': fields['budgets'],
        'reference_input_manifest_sha256': full_root, 'reference_decision_count': len(reference_rows),
        'eligible_reference_count': len(seen), 'reference_omission_counts': omission_counts,
        'reference_input_bytes': reference_bytes, 'candidate_input_bytes': input_total,
        'input_manifest_sha256': content_hash(input_hashes),
        'input_chunk_hashes': [content_hash(input_hashes[n:n + 100]) for n in range(0, len(input_hashes), 100)],
        'software_version': __version__, 'implementation_sha256': implementation_hash()}
    return descriptor, {'protocol': protocol, 'role_population_ids': {k: sorted(v) for k, v in role_ids.items()},
                        'label_sources': label_sources, 'labels': labels}
