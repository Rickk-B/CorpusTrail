"""CP8 contracts over real scientific stores and synthetic offline engines."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from corpustrail._internal.database import connection, migrations
from corpustrail._internal.values import ContractError, canonical, content_hash, digest_bytes
from corpustrail.classification import (Assessment, AssessmentFailure, AssessmentPlan, AuditProtocol,
    Budgets, CalibrationBinding, ClassificationService, ClassifierPolicy, EngineRegistry, Score, ValidationProtocol)
from corpustrail.project import Project, ProjectConfig
from corpustrail.references import ContextStrategy
from classifier_fixtures import OfflineEngine, fail_every_item
from test_references import change, AT


def scientific_state(project):
    with connection(project.database_path) as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'ct_classifier_%' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {table: [tuple(r) for r in db.execute('SELECT * FROM "' + table + '" ORDER BY rowid')] for table in tables}


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        from test_references import ReferenceTests
        helper = ReferenceTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        self.helper = helper; self.project = helper.project; self.ids = helper.ids
        self.pop = helper.helper.freeze()['version_id']
        self.ref = helper.commit([change(pid, label='out_of_scope' if i == 1 else 'in_scope') for i, pid in enumerate(self.ids)])['version_id']
        self.registry = EngineRegistry(); self.engine = OfflineEngine(); self.registry.register(self.engine)
        self.service = ClassificationService(self.project, registry=self.registry)

    def fields(self, **extra):
        return {'request_id': uuid.uuid4().hex, 'name': 'Synthetic frozen assessment', 'actor': 'curator', 'created_at': AT,
            'config_event_id': self.project.configuration_history()[-1]['event_id'],
            'population_version_id': self.pop, 'reference_version_id': self.ref,
            'engine_id': self.engine.engine_id, 'engine_version': 'v1', **extra}

    def plan(self, **extra):
        fields = self.fields(**extra); preview = self.service.prepare(**fields)
        return self.service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256'])

    def start(self, pid, **extra):
        return self.service.start_run(pid, request_id=uuid.uuid4().hex, actor='curator', created_at=AT, **extra)['run_id']

    def execute(self, rid):
        return self.service.execute(rid, expected_revision=self.service.inspect_run(rid)['revision'], clock=lambda: AT)

    def results(self, rid): return self.service.results(rid, limit=100)['items']

    def test_prepare_reads_no_write_and_freeze_replay_is_exact(self):
        from test_populations import fingerprint
        before = fingerprint(self.project.root); fields = self.fields()
        with patch('socket.create_connection', side_effect=AssertionError('No network')):
            preview = self.service.prepare(**fields)
        self.assertEqual(before, fingerprint(self.project.root)); self.assertEqual(self.engine.calls, 0)
        one = self.service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256'])
        two = self.service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256'])
        self.assertTrue(two['replayed']); self.assertEqual(one['plan_id'], two['plan_id'])
        self.assertTrue(self.service.verify_plan(one['plan_id'])['verified'])
        with self.assertRaises(ContractError): self.service.commit_plan(**{**fields, 'name': 'changed'}, expected_preview_sha256=preview['preview_sha256'])

    def test_interchangeable_engines_receive_equivalent_frozen_requests_without_mutation(self):
        baseline = scientific_state(self.project); other = OfflineEngine('synthetic.b'); self.registry.register(other)
        a = self.plan(); b = self.plan(engine_id='synthetic.b')
        self.assertEqual(a['request_sha256'], b['request_sha256'])
        runs = [self.start(p['plan_id']) for p in (a, b)]
        with patch('socket.create_connection', side_effect=AssertionError('No network')):
            for rid in runs: self.assertEqual(self.execute(rid)['status'], 'completed')
        self.assertEqual(self.engine.seen, other.seen)
        self.assertEqual(scientific_state(self.project), baseline)
        self.assertTrue(all(r['assessment']['outcome'] == 'uncertain' and r['authority'] == 'non_authoritative' for rid in runs for r in self.results(rid)))
        self.assertTrue(all(x['input']['target']['paper_id'] not in {r['paper_id'] for r in x['references']} for x in self.engine.seen))
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))

    def test_completed_replay_independent_runs_and_contradictions_preserve_lineage(self):
        self.engine.outcome = 'include'
        self.registry = EngineRegistry(); self.registry.register(self.engine); self.service.registry = self.registry
        plan = self.plan(); first = self.start(plan['plan_id']); self.execute(first); calls = self.engine.calls
        self.assertTrue(self.service.execute(first, expected_revision='old', clock=lambda: AT)['replayed'])
        self.assertEqual(self.engine.calls, calls)
        independent = self.start(plan['plan_id']); self.execute(independent)
        self.assertNotEqual(self.results(first)[0]['result_id'], self.results(independent)[0]['result_id'])
        other = OfflineEngine('synthetic.opposite', outcome='exclude'); self.registry.register(other)
        second = self.start(self.plan(engine_id=other.engine_id)['plan_id'], parent_run_id=first); self.execute(second)
        self.assertTrue(all(r['parent_assessment_id'] for r in self.results(second)))
        sample = self.service.audit_preview((first, second), AuditProtocol('synthetic-audit', 'v1', 42, 2))
        self.assertEqual(sample, self.service.audit_preview((second, first), AuditProtocol('synthetic-audit', 'v1', 42, 2)))
        self.assertEqual(next(s for s in sample['strata'] if s['group'] == 'disagreement')['population_count'], 3)
        self.assertTrue(all(self.project.reviews.membership(p)['state'] == 'not_reviewed' for p in self.ids))

    def test_bounded_context_preserves_actual_selected_input_and_hashes(self):
        contexts = tuple(self.helper.context(self.ref, target_paper_id=pid)['context_id'] for pid in self.ids)
        frozen = self.plan(input_mode='bounded_context', evidence_basis='frozen_context', context_ids=contexts)
        rid = self.start(frozen['plan_id']); self.execute(rid)
        for result in self.results(rid):
            exact = self.service.exact_input(frozen['plan_id'], result['paper_id'])
            original = self.project.references.context(result['context_id'], verify=True)
            self.assertEqual(exact['input'], original['input'])
            self.assertEqual(result['context_input_sha256'], original['input_sha256'])
        self.assertTrue(self.service.verify_plan(frozen['plan_id'])['verified'])

    def test_normalized_reference_evidence_remains_citable_without_per_target_duplication(self):
        frozen = self.plan(); pid = frozen['plan_id']
        for item in self.service.plan_inputs(pid, limit=100)['items']:
            self.assertEqual(len(item['inline_evidence_hashes']), 1)
        def cite_reference(plan, units):
            return tuple(Assessment(unit.input()['target']['paper_id'], 'uncertain', 'unknown',
                'Synthetic reference citation.', (next(unit.references())['representation']['sha256'],),
                'Not a scientific inference.', ()) for unit in units)
        self.engine.assess = cite_reference
        rid = self.start(pid)
        self.assertEqual(self.execute(rid)['status'], 'completed')
        self.assertTrue(all(r['kind'] == 'assessment' for r in self.results(rid)))

    def test_bounded_commit_verifies_context_in_its_existing_transaction(self):
        contexts = tuple(self.helper.context(self.ref, target_paper_id=pid)['context_id'] for pid in self.ids)
        with patch('corpustrail.references.context.connection', side_effect=AssertionError('Nested context connection would block a spilled writer')):
            frozen = self.plan(input_mode='bounded_context', evidence_basis='frozen_context', context_ids=contexts)
        self.assertTrue(self.service.verify_plan(frozen['plan_id'])['verified'])
        with connection(self.project.database_path, write=True) as db:
            db.execute('DROP TRIGGER ct_reference_context_items_no_update')
            db.execute('UPDATE ct_reference_context_items SET payload_json=? WHERE context_id=? AND position=0', ('{}', contexts[0]))
        with self.assertRaisesRegex(ContractError, 'manifest'):
            self.plan(input_mode='bounded_context', evidence_basis='frozen_context', context_ids=contexts)

    def test_partial_chunk_continuation_restart_and_failed_records_are_disjoint(self):
        pid = self.plan(budgets=Budgets(chunk_size=1, max_items_per_execution=1))['plan_id']; rid = self.start(pid)
        first = self.execute(rid); saved = self.results(rid)[0]
        self.assertEqual(first['status'], 'partial'); self.assertEqual(first['primary_counts']['not_assessed'], 2)
        reopened = ClassificationService(Project.open(self.project.root), registry=self.registry)
        self.service = reopened
        self.execute(rid); final = self.execute(rid)
        self.assertEqual(final['status'], 'completed'); self.assertEqual(self.results(rid)[0], saved)
        self.assertEqual(sum(final['primary_counts'].values()), 3); self.assertEqual(self.engine.calls, 3)
        with self.assertRaises(ContractError): self.service.results(rid, limit=101)
        self.assertEqual(self.service.results(rid, limit=1)['next_offset'], 1)

    def test_failures_are_not_uncertain_assessments_and_never_retry_implicitly(self):
        failure = OfflineEngine('synthetic.failure', response=fail_every_item); self.registry.register(failure)
        rid = self.start(self.plan(engine_id=failure.engine_id)['plan_id']); outcome = self.execute(rid)
        self.assertEqual(outcome['primary_counts'], {'include': 0, 'exclude': 0, 'uncertain': 0, 'failed': 3, 'not_assessed': 0})
        self.assertEqual(outcome['status'], 'failed'); self.assertTrue(all(r['failure']['retryable'] for r in self.results(rid)))
        self.execute(rid); self.assertEqual(failure.calls, 1)

    def test_malformed_authority_identity_evidence_scores_and_secrets_are_rejected(self):
        def invalid(kind):
            def output(plan, chunk):
                values = []
                for unit in chunk:
                    target = unit.input()['target']; pid = target['paper_id']
                    value = Assessment(pid, 'include', 'sufficient', 'Synthetic claim', (target['representation']['sha256'],), 'Explicit uncertainty', ())
                    if kind == 'authority': value = {**value.to_dict(), 'authority': 'human_authorized'}
                    elif kind == 'identity': value = replace(value, paper_id='ct-paper:' + '0' * 64)
                    elif kind == 'evidence': value = replace(value, evidence_hashes=('sha256:' + '0' * 64,))
                    elif kind == 'score': value = replace(value, score=Score(0.8, 'classifier_probability', 'not a similarity'))
                    elif kind == 'insufficient': value = replace(value, outcome='exclude', evidence_sufficiency='insufficient')
                    elif kind == 'secret': value = {'password': 'synthetic-private-value-not-for-storage'}
                    elif kind == 'size': value = {'data': 'x' * 70000}
                    values.append(value)
                return tuple(values)
            return output
        for kind in ('authority', 'identity', 'evidence', 'score', 'insufficient', 'secret', 'size'):
            with self.subTest(kind=kind):
                engine = OfflineEngine('synthetic.' + kind, response=invalid(kind)); self.registry.register(engine)
                rid = self.start(self.plan(engine_id=engine.engine_id)['plan_id']); self.execute(rid)
                self.assertTrue(all(r['kind'] == 'failure' and r['failure']['reason'] == 'invalid_output' for r in self.results(rid)))
        self.assertNotIn(b'synthetic-private-value-not-for-storage', self.project.database_path.read_bytes())

    def test_engine_exceptions_are_sanitized_and_no_hidden_fallback_occurs(self):
        def error(plan, chunk): raise RuntimeError('Bearer synthetic-private-diagnostic')
        engine = OfflineEngine('synthetic.error', response=error); self.registry.register(engine)
        rid = self.start(self.plan(engine_id=engine.engine_id)['plan_id']); self.execute(rid)
        self.assertTrue(all(r['failure']['reason'] == 'engine_error' for r in self.results(rid)))
        self.assertNotIn(b'synthetic-private-diagnostic', self.project.database_path.read_bytes())
        self.assertEqual(self.engine.calls, 0)
        with self.assertRaisesRegex(ContractError, 'not installed'): self.plan(engine_id='missing-engine')

    def test_cancellation_preserves_not_attempted_without_inventing_judgments(self):
        rid = self.start(self.plan()['plan_id']); revision = self.service.inspect_run(rid)['revision']
        stopped = self.service.execute(rid, expected_revision=revision, clock=lambda: AT, cancelled=lambda: True)
        self.assertEqual(stopped['status'], 'interrupted'); self.assertEqual(stopped['primary_counts']['not_assessed'], 3)
        self.assertEqual(self.results(rid), []); self.assertEqual(self.execute(rid)['status'], 'completed')

    def test_cooperative_time_budget_stops_at_a_safe_boundary_without_losing_candidates(self):
        rid = self.start(self.plan(budgets=Budgets(chunk_size=1, max_seconds_per_execution=1))['plan_id'])
        ticks = iter((0, 0, 2))
        result = self.service.execute(rid, expected_revision=self.service.inspect_run(rid)['revision'],
            clock=lambda: AT, monotonic=lambda: next(ticks))
        self.assertEqual(result['status'], 'partial'); self.assertEqual(result['processed'], 1)
        self.assertEqual(result['primary_counts']['not_assessed'], 2)
        self.assertEqual(self.execute(rid)['status'], 'completed')

    def test_interrupt_during_callback_preserves_failure_and_can_continue_remaining(self):
        def interrupted(plan, chunk): raise KeyboardInterrupt('Controlled interruption')
        engine = OfflineEngine('synthetic.interrupted', response=interrupted); self.registry.register(engine)
        rid = self.start(self.plan(engine_id=engine.engine_id, budgets=Budgets(chunk_size=1))['plan_id'])
        with self.assertRaises(KeyboardInterrupt): self.execute(rid)
        self.assertEqual(self.results(rid)[0]['failure']['reason'], 'interrupted_no_response')
        engine.response = None
        final = self.execute(rid)
        self.assertEqual(final['primary_counts']['failed'], 1); self.assertEqual(final['primary_counts']['uncertain'], 2)

    def test_validation_roles_cutoff_and_context_leakage_are_enforced(self):
        held = self.helper.helper.freeze([{'kind': 'selection', 'paper_ids': [self.ids[0]]}])['version_id']
        calibration = self.helper.helper.freeze([{'kind': 'selection', 'paper_ids': [self.ids[1]]}])['version_id']
        protocol = ValidationProtocol(purpose='held_out_evaluation', held_out_population_version=held,
            calibration_population_version=calibration, label_cutoff=AT)
        fields = self.fields(population_version_id=held, validation=protocol)
        preview = self.service.prepare(**fields)
        pid = self.service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256'])['plan_id']
        rid = self.start(pid); self.execute(rid)
        seen = self.engine.seen[0]
        self.assertEqual([r['paper_id'] for r in seen['references']], [self.ids[2]])
        self.assertNotIn('label_sources', canonical(seen['input']))
        result = self.service.validate(rid)
        self.assertEqual(result['known_inclusion_recall'], {'numerator': 0, 'denominator': 1, 'value': 0.0})
        self.assertEqual(result['matrix']['in_scope']['uncertain'], 1)
        self.assertFalse(result['scientific_performance_claim']); self.assertEqual(self.service.validate(rid), result)
        unsafe = self.helper.context(self.ref, target_paper_id=self.ids[0])['context_id']
        with self.assertRaisesRegex(ContractError, 'validation role'):
            self.plan(population_version_id=held, validation=protocol, input_mode='bounded_context',
                      evidence_basis='frozen_context', context_ids=(unsafe,))
        safe = self.helper.context(self.ref, target_paper_id=self.ids[0], held_out_paper_ids=self.ids[:2])['context_id']
        self.plan(population_version_id=held, validation=protocol, input_mode='bounded_context',
                  evidence_basis='frozen_context', context_ids=(safe,))
        for changed in (replace(protocol, self_match='include_operational'), replace(protocol, calibration_population_version=held),
                        replace(protocol, label_cutoff='2025-01-01T00:00:00+00:00')):
            with self.assertRaises(ContractError): self.plan(population_version_id=held, validation=changed)

    def test_calibration_is_versioned_provenance_not_an_invented_probability(self):
        engine = OfflineEngine('synthetic.score', score_type='similarity'); self.registry.register(engine)
        held = self.helper.helper.freeze([{'kind': 'selection', 'paper_ids': [self.ids[0]]}])['version_id']
        protocol = ValidationProtocol(purpose='calibration', calibration_population_version=held, label_cutoff=AT)
        policy = ClassifierPolicy(score_type='similarity', score_direction='higher_more_in_scope')
        pid = self.plan(engine_id=engine.engine_id, population_version_id=held, policy=policy, validation=protocol)['plan_id']
        rid = self.start(pid); self.execute(rid)
        body = b'{"fixture_only":true,"no_fitted_calibrator":true}'
        contract = CalibrationBinding('synthetic-calibration', 'v1', rid, content_hash(protocol.to_dict()), 'similarity', digest_bytes(body))
        binding = self.service.register_calibration(contract, body, actor='curator', created_at=AT)
        followup = self.plan(engine_id=engine.engine_id, policy=policy, calibration_binding_id=binding['binding_id'])
        self.assertEqual(followup['calibration_state'], 'declared_unvalidated')
        self.assertEqual(self.plan()['calibration_state'], 'not_calibrated')
        with self.assertRaises(ContractError): self.plan(calibration_binding_id=binding['binding_id'])
        with self.assertRaises(ContractError): replace(contract, validation_state='validated').to_dict()
        with self.assertRaises(ContractError): self.service.register_calibration(contract, b'changed', actor='curator', created_at=AT)
        uncalibrated = OfflineEngine('synthetic.probability', score_type='calibrated_probability', outcome='include')
        self.registry.register(uncalibrated)
        rid2 = self.start(self.plan(engine_id=uncalibrated.engine_id,
            policy=ClassifierPolicy(score_type='calibrated_probability'))['plan_id'])
        self.execute(rid2); self.assertTrue(all(r['kind'] == 'failure' for r in self.results(rid2)))

    def test_score_types_bands_and_missing_evidence_are_explicit(self):
        self.assertEqual(Score(0.8, 'similarity', 'similarity only').to_dict()['score_type'], 'similarity')
        for score in (Score(float('nan'), 'similarity', 'invalid'), Score(1.5, 'model_confidence', 'invalid'), Score(0.1, 'unknown', 'invalid')):
            with self.assertRaises(ContractError): score.to_dict()
        for policy in (ClassifierPolicy(include_band=(0.6, 1.0)),
                       ClassifierPolicy(score_type='similarity', score_direction='higher_more_in_scope', include_band=(0.4, 0.8), exclude_band=(0.1, 0.5))):
            with self.assertRaises(ContractError): policy.to_dict()
        engine = OfflineEngine('synthetic.band', outcome='include', score_type='similarity'); self.registry.register(engine)
        correct = ClassifierPolicy(score_type='similarity', score_direction='higher_more_in_scope', include_band=(0.7, 1.0), exclude_band=(0.0, 0.2))
        rid = self.start(self.plan(engine_id=engine.engine_id, policy=correct)['plan_id']); self.execute(rid)
        self.assertTrue(all(r['kind'] == 'assessment' for r in self.results(rid)))
        wrong = replace(correct, include_band=(0.8, 1.0))
        bad = self.start(self.plan(engine_id=engine.engine_id, policy=wrong)['plan_id']); self.execute(bad)
        self.assertTrue(all(r['kind'] == 'failure' for r in self.results(bad)))
        with self.assertRaisesRegex(ContractError, 'unavailable'): self.plan(evidence_basis='structured_text')

    def test_configuration_and_preview_changes_fail_before_any_invocation(self):
        fields = self.fields(); preview = self.service.prepare(**fields)
        self.project.configure(replace(self.project.config, config_version=2, name='New fixture title'),
            expected_event_id=fields['config_event_id'], created_by='curator', created_at=AT)
        with self.assertRaises(ContractError): self.service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256'])
        self.assertEqual(self.engine.calls, 0)

    def test_frozen_inputs_do_not_expand_when_metadata_references_or_population_change(self):
        from corpustrail._internal.pipeline import preserve
        from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
        first = self.plan(); before = [self.service.exact_input(first['plan_id'], pid) for pid in self.ids]
        body = b'{"synthetic_abstract":true}'; sha = preserve(self.project, body, 'application/json', AT)
        record = BibliographicRecord('Invented scientific title — 材料', abstract='New synthetic abstract', identifiers=(Identifier('doi', '10.1234/p.0'),))
        source = SourceReference('fixture://later', 'new-abstract', sha, len(body), 'synthetic-fixture', AT, identity_status='verified')
        self.project.identities.apply(self.project.identities.plan(record, source), approve_new_identity=True, approve_aliases=True)
        later = self.helper.helper.enroll('additional', doi='10.1234/new-candidate')
        pop2 = self.helper.helper.freeze(parent=self.pop)['version_id']
        ref2 = self.helper.commit([change(later)], parent=self.ref)['version_id']
        changed = self.plan(population_version_id=pop2, reference_version_id=ref2)
        self.assertNotEqual(changed['request_sha256'], first['request_sha256'])
        self.assertEqual([self.service.exact_input(first['plan_id'], pid) for pid in self.ids], before)
        self.assertEqual(self.service.inspect_plan(first['plan_id'])['candidate_count'], 3)
        self.assertEqual(changed['candidate_count'], 4)

    def test_parallel_identical_plan_commit_and_failed_insert_are_atomic(self):
        fields = self.fields(); preview = self.service.prepare(**fields); results = []; errors = []
        def work():
            try: results.append(self.service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256']))
            except Exception as error: errors.append(type(error).__name__)
        threads = [threading.Thread(target=work) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(15); self.assertFalse(thread.is_alive())
        self.assertEqual(errors, []); self.assertEqual(len({r['plan_id'] for r in results}), 1)
        from corpustrail.classification import inputs
        original = inputs.freeze
        def fail(*args, **kwargs):
            value = original(*args, **kwargs)
            if kwargs.get('sink'): raise RuntimeError('Controlled failure after candidate inserts')
            return value
        second = self.fields(); view = self.service.prepare(**second)
        with patch.object(inputs, 'freeze', side_effect=fail):
            with self.assertRaises(RuntimeError): self.service.commit_plan(**second, expected_preview_sha256=view['preview_sha256'])
        with connection(self.project.database_path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_classifier_plans').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_classifier_inputs').fetchone()[0], 3)

    def test_immutable_records_and_corruption_detection(self):
        pid = self.plan()['plan_id']; rid = self.start(pid); self.execute(rid)
        with connection(self.project.database_path, write=True) as db:
            for table in ('ct_classifier_plans', 'ct_classifier_inputs', 'ct_classifier_blobs', 'ct_classifier_runs', 'ct_classifier_results'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM ' + table)
            db.execute('DROP TRIGGER ct_classifier_blobs_no_update')
            db.execute('UPDATE ct_classifier_blobs SET body=? WHERE sha256=(SELECT input_blob_sha256 FROM ct_classifier_inputs LIMIT 1)', (b'{}',))
        with self.assertRaisesRegex(ContractError, 'integrity'): self.service.verify_plan(pid)

    def test_remote_declared_mock_requires_exact_payload_consent(self):
        mock = OfflineEngine('synthetic.remote-mock', locality='remote_declared_mock'); self.registry.register(mock)
        plan = self.plan(engine_id=mock.engine_id)
        for consent in (None, 'connection-test', 'sha256:' + '0' * 64):
            with self.assertRaisesRegex(ContractError, 'consent'): self.start(plan['plan_id'], transfer_sha256=consent)
        rid = self.start(plan['plan_id'], transfer_sha256=plan['transfer_sha256'])
        with patch('socket.create_connection', side_effect=AssertionError('Remote mock remains offline')):
            self.assertEqual(self.execute(rid)['status'], 'completed')
        changed = self.plan(engine_id=mock.engine_id, settings={'different_task_setting': True})
        with self.assertRaises(ContractError): self.start(changed['plan_id'], transfer_sha256=plan['transfer_sha256'])

    def test_blinded_review_dtos_and_frozen_session_remain_identical_after_assessment(self):
        from corpustrail.application.review import ReviewController
        from corpustrail.curation.guided import GuidedReviewService
        controller = ReviewController(); configuration = controller.configuration(self.project)
        session = GuidedReviewService(self.project).create(command_id=uuid.uuid4().hex, reviewer_id='curator',
            selection=self.pop, population_sha256=self.project.populations.inspect(self.pop)['members_sha256'],
            config_event_id=configuration['config_event_id'], mode='method-blind')
        handle = session['session_id'].split(':')[1]; before = controller.view(self.project, handle)
        rid = self.start(self.plan()['plan_id']); self.execute(rid)
        self.assertEqual(controller.view(self.project, handle), before)
        encoded = canonical(before)
        for forbidden in ('assessment-plan:', 'assessment-run:', 'reference-assignment:', 'synthetic.a', 'classifier_probability'):
            self.assertNotIn(forbidden, encoded)
        self.assertTrue(self.service.verify_run(rid)['verified'])

    def test_conflicting_and_unattested_assignments_stay_preserved_but_ineligible(self):
        version = self.helper.commit([change(self.ids[0], label='out_of_scope'), change(self.ids[2], human_attested=False)], parent=self.ref)
        plan = self.plan(reference_version_id=version['version_id'])
        self.assertEqual(plan['reference_omission_counts']['conflicting_labels'], 2)
        self.assertEqual(plan['reference_omission_counts']['unattested_source'], 1)
        self.assertTrue(self.project.references.verify(self.ref)['verified'])
        rid = self.start(plan['plan_id']); self.execute(rid)
        self.assertTrue(all(self.ids[0] not in {r['paper_id'] for r in x['references']} for x in self.engine.seen))

    def test_explicit_resource_exhaustion_and_unknown_input_identifiers_never_truncate(self):
        with self.assertRaisesRegex(ContractError, 'byte budget'):
            self.plan(budgets=Budgets(max_reference_bytes=1024))
        with self.assertRaises(ContractError): self.plan(population_version_id='population-version:' + '0' * 64)
        with self.assertRaises(ContractError): self.plan(context_ids=('reference-context:' + '0' * 64,))
        rid = self.start(self.plan()['plan_id']); self.execute(rid)
        result = self.service.reference_inputs(self.service.inspect_run(rid)['plan_id'], self.ids[0], limit=1)
        self.assertEqual(len(result['items']), 1); self.assertEqual(result['next_offset'], 1)

    def test_dead_process_reservation_requires_explicit_recovery_without_resend(self):
        pid = self.plan(budgets=Budgets(chunk_size=1))['plan_id']; rid = self.start(pid)
        # Installed-package execution in an independent process. No application
        # callbacks or external requests: reserve one exact input then crash.
        code = '''
import os,sys
from corpustrail.project import Project
from corpustrail._internal.database import connection
from corpustrail._internal.values import canonical,content_hash
from corpustrail.application.project_use import operation_use
from corpustrail.classification import storage
p=Project.open(sys.argv[1]);rid=sys.argv[2]
with operation_use(p.root,rid),connection(p.database_path,write=True) as db:
    run=storage.run(db,rid);event,revision=storage.event(db,rid)
    current=storage.append_event(db,rid,'running',sys.argv[3],expected=revision,actor='fixture')
    row=storage.items(db,run['plan_id'],offset=0,limit=1)[0]
    value={'run_id':rid,'position':0,'paper_id':row['paper_id'],'input_sha256':row['input_blob_sha256'],'started_at':sys.argv[3],'lifecycle_revision':current}
    db.execute('INSERT INTO ct_classifier_attempts VALUES (?,?,?,?)',(rid,0,canonical(value),content_hash(value)))
os._exit(23)
'''
        process = subprocess.run([sys.executable, '-I', '-c', code, str(self.project.root), rid, AT], capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 23, process.stderr)
        status = self.service.inspect_run(rid)
        with self.assertRaisesRegex(ContractError, 'recovered'): self.execute(rid)
        self.service.recover(rid, expected_revision=status['revision'], actor='curator', created_at=AT)
        final = self.execute(rid)
        self.assertEqual(final['primary_counts']['failed'], 1); self.assertEqual(final['primary_counts']['uncertain'], 2)
        self.assertEqual(self.engine.calls, 2)

    def test_live_operation_lock_refuses_concurrent_execute_and_recovery(self):
        from corpustrail.application.project_use import operation_use, ProjectBusy
        rid = self.start(self.plan()['plan_id']); revision = self.service.inspect_run(rid)['revision']
        with operation_use(self.project.root, rid):
            with self.assertRaises(ProjectBusy): self.service.execute(rid, expected_revision=revision)
            with self.assertRaises(ProjectBusy): self.service.recover(rid, expected_revision=revision, actor='curator', created_at=AT)
        self.assertEqual(self.execute(rid)['status'], 'completed')

    def test_independent_process_operation_lock_covers_the_whole_engine_call(self):
        from corpustrail.application.project_use import ProjectBusy
        rid = self.start(self.plan()['plan_id'])
        code = '''
import sys
from corpustrail.application.project_use import operation_use
from pathlib import Path
with operation_use(Path(sys.argv[1]),sys.argv[2]):
    print('held',flush=True)
    sys.stdin.readline()
'''
        process = subprocess.Popen([sys.executable, '-I', '-c', code, str(self.project.root), rid],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'held')
            with self.assertRaises(ProjectBusy): self.execute(rid)
            with self.assertRaises(ProjectBusy): self.service.recover(rid,
                expected_revision=self.service.inspect_run(rid)['revision'], actor='curator', created_at=AT)
        finally:
            stdout, stderr = process.communicate('release\n', timeout=20)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(self.execute(rid)['status'], 'completed')

    def test_result_transaction_failure_rolls_back_chunk_before_interruption_receipt(self):
        rid = self.start(self.plan(budgets=Budgets(chunk_size=2))['plan_id'])
        original = self.service._write_result; failed = False
        def interrupted(*args, **kwargs):
            nonlocal failed
            value = original(*args, **kwargs)
            if not failed:
                failed = True
                raise RuntimeError('Controlled result transaction interruption')
            return value
        with patch.object(self.service, '_write_result', side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, 'Controlled result'): self.execute(rid)
        self.assertEqual(len(self.results(rid)), 2)
        self.assertTrue(all(r['kind'] == 'failure' for r in self.results(rid)))
        final = self.execute(rid)
        self.assertEqual(final['primary_counts']['failed'], 2); self.assertEqual(final['primary_counts']['uncertain'], 1)
        self.assertTrue(self.service.verify_run(rid)['verified'])

    def test_schema39_open_is_read_only_and_upgrade_preserves_scientific_history(self):
        from test_references import ReferenceTests
        from test_populations import fingerprint
        from corpustrail.curation import ReviewEvent, EvidenceBasis
        old = ReferenceTests()
        with patch('corpustrail._internal.database.migrations', return_value=migrations()[:39]): old.setUp()
        self.addCleanup(old.doCleanups)
        project = old.project; pid = old.ids[0]
        source = project.identities.observations(pid)[0]['source']
        event = ReviewEvent(pid, 'included', 'sufficient', 'metadata', 'Invented historical judgment', 'curator', AT,
            (EvidenceBasis('metadata', source['source_sha256'], source['source_uri'], artifact_validity='verified'),), authority_state='human_authorized')
        project.reviews.apply(project.reviews.plan(event), recorded_at=AT)
        reference = old.commit()['version_id']; population = old.helper.freeze()['version_id']
        before = fingerprint(project.root); scientific = scientific_state(project)
        reopened = Project.open(project.root)
        self.assertFalse(reopened.classification.ready()); self.assertEqual(fingerprint(project.root), before)
        revision = reopened.configuration_history()[-1]['event_id']
        with self.assertRaises(ContractError):
            Project.upgrade(project.root, backup='backups/stale.sqlite3', expected_config_event='stale', created_at=AT)
        self.assertFalse((project.root/'backups/stale.sqlite3').exists())
        updated = Project.upgrade(project.root, backup='backups/before-classification.sqlite3', expected_config_event=revision, created_at=AT)
        self.assertTrue(updated.classification.ready())
        with closing(sqlite3.connect(project.root/'backups/before-classification.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0], 39)
        after = scientific_state(updated)
        after['schema_migrations'] = after['schema_migrations'][:-1]
        self.assertEqual(after, scientific)
        self.assertEqual(updated.reviews.membership(pid)['state'], 'included')
        self.assertTrue(updated.references.verify(reference)['verified']); self.assertTrue(updated.populations.verify(population)['verified'])
        self.assertEqual({p: h for p, h in fingerprint(project.root).items() if p != project.config.database and not p.startswith('backups/')},
                         {p: h for p, h in before.items() if p != project.config.database})

    def test_interrupted_additive_upgrade_rolls_back_and_retains_preupgrade_backup(self):
        from test_populations import fingerprint
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'legacy'
            with patch('corpustrail._internal.database.migrations', return_value=migrations()[:39]):
                project = Project.create(root, ProjectConfig('old-classifier', 'Old synthetic project', 'Invented'), created_by='fixture', created_at=AT)
            before = fingerprint(root)
            broken = list(migrations()); metadata, body = broken[-1]
            broken[-1] = (metadata, body + '\nINSERT INTO missing_table VALUES (1);\n')
            with patch('corpustrail._internal.database.migrations', return_value=tuple(broken)):
                with self.assertRaises(sqlite3.DatabaseError): Project.upgrade(root, backup='backups/interrupted.sqlite3', created_at=AT)
            self.assertEqual(fingerprint(root)[project.config.database], before[project.config.database])
            self.assertFalse(Project.open(root).classification.ready())
            self.assertTrue((root/'backups/interrupted.sqlite3').is_file())
