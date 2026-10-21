"""Explicit offline CP7/CP8 scale acceptance on a NEW synthetic project only."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from unittest.mock import patch

from corpustrail._internal.database import connection
from corpustrail._internal.values import canonical, content_hash, digest_bytes
from corpustrail.classification import (Assessment, AssessmentPlan, Budgets, ClassificationService,
    EngineDescription, EngineRegistry)
from corpustrail.project import Project
from corpustrail.references import ContextStrategy

AT = '2026-01-01T00:00:00+00:00'


class StreamingFixture:
    """No relevance inference. Read exact inputs and explicitly return uncertain."""
    def __init__(self, identity):
        self.identity = identity; self.seen = {}; self.maximum_chunk = 0

    def describe(self):
        return EngineDescription(self.identity, 'fixture/v1', digest_bytes(Path(__file__).read_bytes()),
            'synthetic-offline', 'synthetic-streaming-adapter', 'v1', 'no-model')

    def prepare(self, request):
        return AssessmentPlan(request.request_sha256, request.engine_sha256,
            content_hash(json.loads(request.settings_json)), {'synthetic_only': True})

    def assess(self, plan, chunk):
        self.maximum_chunk = max(self.maximum_chunk, len(chunk)); results = []
        for unit in chunk:
            value = unit.input(); hashes = []; count = 0
            for item in unit.references():
                if item['paper_id'] == value['target']['paper_id']: raise AssertionError('self label leaked')
                hashes.append(content_hash(item)); count += 1
            if count != unit.reference_count: raise AssertionError('streamed reference count differs')
            target = value['target']; pid = target['paper_id']
            self.seen[pid] = {'input_sha256': unit.input_sha256, 'references_sha256': content_hash(hashes), 'count': count}
            results.append(Assessment(pid, 'uncertain', 'unknown', 'Synthetic protocol exercise; no scientific prediction.',
                (target['representation']['sha256'],), 'No real model or scientific inference.', ('Architecture fixture only.',),
                usage={'reference_records_supplied': count}))
        return tuple(results)


def exercise(project, count):
    started = time.perf_counter(); registry = EngineRegistry()
    first, second = StreamingFixture('synthetic.streaming-a'), StreamingFixture('synthetic.streaming-b')
    registry.register(first); registry.register(second); service = ClassificationService(project, registry=registry)
    revision = project.configuration_history()[-1]['event_id']
    reference = project.references.versions()['items'][0]['version_id']
    with connection(project.database_path) as db:
        ids = [r[0] for r in db.execute('SELECT paper_id FROM paper_entities ORDER BY paper_id')]
        if len(ids) != count or project.config.project_id != 'reference-scale': raise AssertionError('expected the freshly created synthetic reference fixture')
    def population(request, papers):
        fields = {'request_id': request * 32, 'name': 'Synthetic classifier candidates', 'actor': 'synthetic-fixture',
                  'sources': [{'kind': 'selection', 'paper_ids': papers[n:n + 500]} for n in range(0, len(papers), 500)]}
        preview = project.populations.preview(**fields)
        return project.populations.create(**fields, expected_preview_sha256=preview['preview_sha256'], created_at=AT)['version_id']
    large = population('a', ids); small = population('b', ids[:7])
    def plan(request, population_id, engine, **extra):
        fields = {'request_id': request * 32, 'name': 'Synthetic classifier plan', 'actor': 'synthetic-fixture',
            'created_at': AT, 'config_event_id': revision, 'population_version_id': population_id,
            'reference_version_id': reference, 'engine_id': engine.identity, 'engine_version': 'fixture/v1',
            'budgets': Budgets(chunk_size=3, max_items_per_execution=100), **extra}
        preview = service.prepare(**fields)
        return service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256'])
    full = plan('c', large, first); planned = time.perf_counter()
    seen = set(); offset = 0; maximum_page_bytes = 0; pages = 0
    while True:
        data = service.plan_inputs(full['plan_id'], offset=offset, limit=100); pages += 1
        maximum_page_bytes = max(maximum_page_bytes, len(canonical(data).encode()))
        if maximum_page_bytes > 1_000_000: raise AssertionError('compact synthetic input inspection page exceeded its byte bound')
        seen.update(item['paper_id'] for item in data['items'])
        if data['next_offset'] is None: break
        offset = data['next_offset']
    if seen != set(ids): raise AssertionError('large classifier-input pages lost candidates')
    plans = [plan('d', small, first), plan('e', small, second)]
    if plans[0]['request_sha256'] != plans[1]['request_sha256']: raise AssertionError('engine choice changed the frozen scientific request')
    runs = []
    for number, frozen in enumerate(plans):
        rid = service.start_run(frozen['plan_id'], request_id=str(number + 1) * 32, actor='synthetic-fixture', created_at=AT)['run_id']
        result = service.execute(rid, expected_revision=service.inspect_run(rid)['revision'], clock=lambda: AT)
        if result['status'] != 'completed' or result['processed'] != 7: raise AssertionError('offline engine did not process the exact small population')
        runs.append(rid)
    if first.seen != second.seen: raise AssertionError('interchangeable engines received different inputs/context')
    full_done = time.perf_counter(); contexts = []
    for number, pid in enumerate(ids[:7]):
        fields = {'request_id': f'{number + 100:032x}', 'version_id': reference, 'actor': 'synthetic-fixture', 'created_at': AT,
            'config_event_id': revision, 'target_paper_id': pid, 'target_basis': 'metadata',
            'held_out_paper_ids': [], 'strategy': ContextStrategy(in_scope=5, out_of_scope=2), 'dependency_ids': []}
        preview = project.references.prepare_context(**fields)
        contexts.append(project.references.commit_context(**fields, expected_preview_sha256=preview['preview_sha256'])['context_id'])
    bounded = plan('f', small, first, input_mode='bounded_context', evidence_basis='frozen_context', context_ids=tuple(contexts))
    rid = service.start_run(bounded['plan_id'], request_id='3' * 32, actor='synthetic-fixture', created_at=AT)['run_id']
    result = service.execute(rid, expected_revision=service.inspect_run(rid)['revision'], clock=lambda: AT)
    if result['status'] != 'completed': raise AssertionError('bounded-context assessment failed')
    reopened = Project.open(project.root).classification
    for source in runs + [rid]:
        if not reopened.verify_run(source)['verified']: raise AssertionError('restart lost frozen inputs/results')
    with connection(project.database_path) as db:
        blobs = db.execute('SELECT COUNT(*),SUM(LENGTH(body)) FROM ct_classifier_blobs').fetchone()
        rows = db.execute('SELECT COUNT(*) FROM ct_classifier_references').fetchone()[0]
        if db.execute('SELECT COUNT(*) FROM ct_review_events').fetchone()[0] != 0: raise AssertionError('classifier wrote review/membership')
    return {'schema': 'corpustrail-classifier-scale-measurement/v1', 'synthetic_only': True,
        'python': platform.python_version(), 'platform': platform.system(), 'candidate_inputs': count,
        'reference_entries': count, 'large_input_pages': pages, 'page_limit': 100, 'maximum_page_bytes': maximum_page_bytes,
        'small_population_size': 7, 'full_set_engine_runs': 2, 'bounded_context_engine_runs': 1,
        'maximum_execution_chunk': max(first.maximum_chunk, second.maximum_chunk),
        'unique_input_output_blobs': blobs[0], 'physical_blob_bytes': blobs[1], 'reference_metadata_rows': rows,
        'database_bytes': project.database_path.stat().st_size, 'large_plan_seconds': planned - started,
        'pagination_and_full_set_runs_seconds': full_done - planned, 'context_and_restart_seconds': time.perf_counter() - full_done,
        'elapsed_seconds': time.perf_counter() - started, 'large_input_manifest_sha256': full['input_manifest_sha256'],
        'bounded_input_manifest_sha256': bounded['input_manifest_sha256'],
        'assertions': 'exact populations, 100-record pages, equivalent streamed inputs, complete full/bounded context lineage, no self labels, immutable restart recovery, no scientific authority mutation',
        'scientific_performance_claim': False}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--project', type=Path, required=True); parser.add_argument('--papers', type=int, default=2000)
    args = parser.parse_args()
    if not 1000 <= args.papers <= 10000: parser.error('choose a synthetic measurement workload between 1000 and 10000; not a scientific collection cap')
    # Explicit developer-tool import from this checkout, never user-supplied code.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import reference_acceptance
    with patch('socket.create_connection', side_effect=AssertionError('scale acceptance must remain offline')):
        reference_result = reference_acceptance.exercise(args.project, args.papers)
        result = exercise(Project.open(args.project), args.papers)
    print(json.dumps({'reference_acceptance': reference_result, 'classification_acceptance': result}, indent=2))


if __name__ == '__main__': main()
