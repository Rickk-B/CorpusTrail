"""Bounded operational views, never method-blind review DTOs or scientific truth."""
import json

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, content_hash
from corpustrail.populations.contracts import page
from . import storage

PRIMARY = ('include', 'exclude', 'uncertain', 'failed', 'not_assessed')
OVERLAYS = ('insufficient', 'unknown_sufficiency', 'disagreement', 'human_reviewed')


def query(db, run_id, compare_run_id=None):
    run = storage.run(db, run_id); head = storage.plan(db, run['plan_id'])
    sources = []
    for rid in (run_id, compare_run_id):
        if rid is None: continue
        other = storage.run(db, rid); plan = storage.plan(db, other['plan_id'])
        if plan['population_version_id'] != head['population_version_id'] or plan['definition_sha256'] != head['definition_sha256']:
            raise ContractError('compare runs under the same exact frozen population and corpus definition')
        sources.append({'run_id': rid, 'plan_id': other['plan_id'], 'reference_version_id': plan['reference_version_id'],
            'lifecycle_sha256': storage.event(db, rid)[1],
            'result_count': db.execute('SELECT COUNT(*) FROM ct_classifier_results WHERE run_id=?', (rid,)).fetchone()[0]})
    if compare_run_id == run_id: raise ContractError('choose another independent comparison run')
    watermark = [latest_config(db)[0], db.execute('SELECT COALESCE(MAX(sequence),0) FROM ct_review_events').fetchone()[0],
                 db.execute('SELECT COUNT(*) FROM ct_paper_observations').fetchone()[0]]
    revision = content_hash({'sources': sources, 'live_human_metadata_watermark': watermark})
    sql = """WITH candidates AS (
      SELECT i.position,i.paper_id,r.result_id,r.payload_json,x.result_id AS comparison_result_id,
        x.payload_json AS comparison_payload,
        COALESCE(CASE WHEN r.kind='failure' THEN 'failed' ELSE r.outcome END,'not_assessed') AS primary_state,
        COALESCE(json_extract(r.payload_json,'$.assessment.evidence_sufficiency')='insufficient',0) AS insufficient,
        COALESCE(json_extract(r.payload_json,'$.assessment.evidence_sufficiency')='unknown',0) AS unknown_sufficiency,
        CASE WHEN r.kind='assessment' AND x.kind='assessment' AND r.outcome!=x.outcome THEN 1 ELSE 0 END AS disagreement,
        EXISTS(SELECT 1 FROM ct_review_events h WHERE h.paper_id=i.paper_id AND h.producer_type='human') AS human_reviewed
      FROM ct_classifier_inputs i
      LEFT JOIN ct_classifier_results r ON r.run_id=? AND r.paper_id=i.paper_id
      LEFT JOIN ct_classifier_results x ON x.run_id=? AND x.paper_id=i.paper_id
      WHERE i.plan_id=?
    ) """
    return sql, (run_id, compare_run_id, run['plan_id']), head, sources, revision


def where(primary='', overlay=''):
    if primary not in ('', *PRIMARY) or overlay not in ('', *OVERLAYS):
        raise ContractError('choose a supported primary state or explicitly overlapping filter')
    return (' WHERE ' + ' AND '.join((['primary_state=?'] if primary else []) + ([overlay + '=1'] if overlay else []))
            if primary or overlay else ''), ([primary] if primary else [])


def counts(db, sql, params):
    primary = {key: 0 for key in PRIMARY}
    primary.update(dict(db.execute(sql + 'SELECT primary_state,COUNT(*) FROM candidates GROUP BY primary_state', params)))
    row = db.execute(sql + 'SELECT ' + ','.join('COALESCE(SUM(' + key + '),0)' for key in OVERLAYS) + ' FROM candidates', params).fetchone()
    return {'primary': primary, 'population_total': sum(primary.values()), 'overlays': dict(zip(OVERLAYS, row)),
        'count_semantics': 'Primary states are mutually exclusive and exhaust the frozen population. Overlays can overlap each other and primary states; never sum them into a population total. Human status is live and separate from engine judgments and current membership.'}


class CurationReads:
    def __init__(self, project): self.project = project

    def results(self, run_id, *, compare_run_id=None, primary='', overlay='', offset=0, limit=20, expected_revision=None):
        page(offset, limit); clause, values = where(primary, overlay)
        with connection(self.project.database_path) as db:
            sql, params, head, sources, revision = query(db, run_id, compare_run_id)
            if (offset and expected_revision is None) or expected_revision is not None and expected_revision != revision:
                raise ContractError('assessment results or live human status changed; restart pagination explicitly')
            total = db.execute(sql + 'SELECT COUNT(*) FROM candidates' + clause, (*params, *values)).fetchone()[0]
            rows = db.execute(sql + 'SELECT * FROM candidates' + clause + ' ORDER BY position LIMIT ? OFFSET ?',
                              (*params, *values, limit, offset))
            items = []
            for row in rows:
                value = {key: row[key] for key in ('position', 'paper_id', 'primary_state', 'result_id', 'comparison_result_id')}
                value['overlays'] = [key for key in OVERLAYS if row[key]]
                if row['result_id']:
                    exact = storage.result(db, run_id, row['position'])
                    value['observation'] = exact.get('assessment') or exact['failure']
                if row['comparison_result_id']:
                    position = db.execute('SELECT position FROM ct_classifier_results WHERE result_id=?', (row['comparison_result_id'],)).fetchone()[0]
                    exact = storage.result(db, compare_run_id, position)
                    value['comparison'] = exact.get('assessment') or exact['failure']
                items.append(value)
            return {'run_id': run_id, 'revision': revision, 'population_version_id': head['population_version_id'],
                'reference_version_id': head['reference_version_id'], 'sources': sources,
                **counts(db, sql, params), 'filtered_total': total, 'items': items,
                'filters': {'primary': primary, 'overlay': overlay},
                'next_offset': offset + limit if offset + limit < total else None,
                'notice': 'Operational assisted data. Differences may reflect different frozen inputs, not just engines. No exclusion removes a candidate; no stopping rule or corpus decision is inferred.'}

    def source(self, run_id, paper_id):
        with connection(self.project.database_path) as db:
            run = storage.run(db, run_id); head = storage.plan(db, run['plan_id'])
            row = db.execute('SELECT position FROM ct_classifier_inputs WHERE plan_id=? AND paper_id=?', (run['plan_id'], paper_id)).fetchone()
            if row is None: raise ContractError('paper is outside this exact run population')
            item = storage.items(db, run['plan_id'], offset=row[0], limit=1)[0]
            result = storage.result(db, run_id, row[0])
            return {'run_id': run_id, 'plan_id': run['plan_id'], 'paper_id': paper_id,
                'input_sha256': item['input_blob_sha256'], 'evidence_snapshot_sha256': item['evidence_snapshot_sha256'],
                'reference_version_id': head['reference_version_id'], 'context_id': item['context_id'],
                'result_id': result['result_id'] if result else None, 'kind': result['kind'] if result else 'not_assessed',
                'result': result, 'authority': 'non_authoritative'}


def is_assisted(db, session_id):
    return (db.execute("SELECT 1 FROM sqlite_master WHERE name='ct_curation_sessions'").fetchone() is not None
            and db.execute('SELECT 1 FROM ct_curation_sessions WHERE session_id=?', (session_id,)).fetchone() is not None)
