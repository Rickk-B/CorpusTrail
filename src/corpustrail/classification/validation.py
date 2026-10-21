"""Frozen-role validation and audit hooks, without CP9's curation workflow.

Synthetic fixtures establish software behavior, never scientific performance.
Calibration registration preserves provenance, not a fitted/validated calibrator.
"""
import json

from corpustrail._internal.database import connection
from corpustrail._internal.values import ContractError, canonical, content_hash, identifier
from .contracts import AuditProtocol
from . import storage


def record_validation(project, rid):
    with connection(project.database_path, write=True) as db:
        run = storage.run(db, rid); plan = storage.plan(db, run['plan_id'])
        frozen = json.loads(storage.blob(db, plan['validation_snapshot_sha256']))
        protocol = frozen['protocol']
        if protocol['purpose'] == 'operational':
            raise ContractError('operational/reference agreement is not independent validation; freeze explicit validation roles first')
        matrix = {label: {key: 0 for key in ('include', 'exclude', 'uncertain', 'failed', 'not_assessed')}
                  for label in ('in_scope', 'out_of_scope')}
        overlays = {'insufficient': 0, 'unknown_sufficiency': 0}
        source_ids = []; label_sources = []
        for offset in range(0, plan['candidate_count'], 100):
            for index, item in enumerate(storage.items(db, run['plan_id'], offset=offset, limit=100), offset):
                pid = item['paper_id']; label = frozen['labels'][pid]
                source = frozen['label_sources'][pid]; label_sources.append(source)
                result = storage.result(db, rid, index)
                if result is None: key = 'not_assessed'
                elif result['kind'] == 'failure': key = 'failed'; source_ids.append(result['result_id'])
                else:
                    assessment = result['assessment']; key = assessment['outcome']; source_ids.append(result['result_id'])
                    if assessment['evidence_sufficiency'] == 'insufficient': overlays['insufficient'] += 1
                    elif assessment['evidence_sufficiency'] == 'unknown': overlays['unknown_sufficiency'] += 1
                matrix[label][key] += 1
        positive = sum(matrix['in_scope'].values()); negative = sum(matrix['out_of_scope'].values())
        predicted_positive = matrix['in_scope']['include'] + matrix['out_of_scope']['include']
        def fraction(numerator, denominator):
            return {'numerator': numerator, 'denominator': denominator,
                    'value': numerator / denominator if denominator else None}
        value = {'schema': 'corpustrail-assessment-validation/v1', 'run_id': rid, 'plan_id': run['plan_id'],
            'population_version_id': plan['population_version_id'], 'reference_version_id': plan['reference_version_id'],
            'protocol': protocol, 'protocol_sha256': content_hash(protocol),
            'frozen_label_sources_sha256': content_hash(label_sources), 'result_ids': source_ids,
            'matrix': matrix, 'overlay_counts': overlays,
            'known_inclusion_recall': fraction(matrix['in_scope']['include'], positive),
            'known_exclusion_specificity': fraction(matrix['out_of_scope']['exclude'], negative),
            'precision_on_known_binary_labels': fraction(matrix['in_scope']['include'], predicted_positive),
            'candidate_count': positive + negative,
            'authority': 'non_authoritative', 'scientific_performance_claim': False,
            'qualification': 'Frozen-label software evaluation only. Failures, abstentions and not-assessed cases remain explicit in denominators; they are not exclusions. Sparse or synthetic labels do not establish scientific performance, reliable exclusion, fresh independence or a stopping rule.'}
        vid = identifier('assessment-validation', value)
        row = db.execute('SELECT payload_json FROM ct_classifier_validations WHERE validation_id=?', (vid,)).fetchone()
        if row is None: db.execute('INSERT INTO ct_classifier_validations VALUES (?,?,?)', (vid, rid, canonical(value)))
        elif json.loads(row[0]) != value: raise ContractError('assessment validation integrity changed')
        return {'validation_id': vid, **value}


def audit_preview(project, run_ids, protocol):
    """A read-only sampling contract for CP9; it never records human outcomes."""
    if not isinstance(protocol, AuditProtocol): raise ContractError('typed audit protocol required')
    spec = protocol.to_dict()
    if not isinstance(run_ids, tuple) or not run_ids or len(run_ids) != len(set(run_ids)) or len(run_ids) > 20:
        raise ContractError('explicit unique bounded source runs required')
    papers = {}; sources = []
    with connection(project.database_path) as db:
        populations = set()
        for rid in sorted(run_ids):
            run = storage.run(db, rid); plan = storage.plan(db, run['plan_id']); populations.add(plan['population_version_id'])
            sources.append({'run_id': rid, 'plan_id': run['plan_id'], 'reference_version_id': plan['reference_version_id'],
                            'definition_sha256': plan['definition_sha256']})
            for row in db.execute('SELECT position FROM ct_classifier_results WHERE run_id=? ORDER BY position', (rid,)):
                result = storage.result(db, rid, row[0]); pid = result['paper_id']
                paper = papers.setdefault(pid, {'result_ids': [], 'groups': set(), 'outcomes': set()})
                paper['result_ids'].append(result['result_id'])
                if result['kind'] == 'failure': paper['groups'].add('failure')
                else:
                    output = result['assessment']; paper['outcomes'].add(output['outcome']); paper['groups'].add(output['outcome'])
                    if output['evidence_sufficiency'] == 'insufficient': paper['groups'].add('insufficient')
        if len(populations) != 1: raise ContractError('audit comparison requires the same exact frozen candidate population')
    for paper in papers.values():
        if len(paper['outcomes']) > 1: paper['groups'].add('disagreement')
    strata = []; selected = {}
    for group in spec['groups']:
        pool = sorted((pid for pid, p in papers.items() if group in p['groups']),
                      key=lambda pid: (content_hash({'seed': spec['seed'], 'group': group, 'paper_id': pid}), pid))
        choices = pool[:spec['per_group']]
        strata.append({'group': group, 'population_count': len(pool), 'selected_paper_ids': choices})
        for pid in choices:
            selected.setdefault(pid, {'paper_id': pid, 'strata': [], 'result_ids': sorted(papers[pid]['result_ids'])})['strata'].append(group)
    value = {'schema': 'corpustrail-assessment-audit-selection/v1', 'protocol': spec, 'sources': sources,
        'population_version_id': next(iter(populations)), 'strata': strata, 'selected': [selected[pid] for pid in sorted(selected)],
        'authority': 'non_authoritative', 'qualification': 'Policy-stratified sampling preview; overlapping strata are not a disjoint population total or an unbiased scientific performance estimate. No human outcome or corpus decision is recorded.'}
    return {**value, 'manifest_sha256': content_hash(value)}
