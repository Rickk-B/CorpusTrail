"""Real CP9 services over disposable CP8 fixtures; no scientific performance claim."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from corpustrail._internal.database import connection, migrations
from corpustrail._internal.values import ContractError, content_hash
from corpustrail.classification import Assessment, AssessmentFailure, Budgets, ClassificationService
from corpustrail.classification.curation import CurationService, AuditSelection
from corpustrail.classification.curation_views import CurationReads
from corpustrail.curation.guided import GuidedReviewService
from corpustrail.curation.sessions import SessionService, _load
from corpustrail.project import Project, ProjectConfig
from classifier_fixtures import OfflineEngine
from test_references import AT


class CurationWorkflowTests(unittest.TestCase):
    def setUp(self):
        from test_classification import ClassificationTests
        helper = ClassificationTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        self.h = helper; self.project = helper.project; self.ids = sorted(helper.ids)
        self.service = CurationService(self.project); self.reads = CurationReads(self.project)
        self.revision = self.project.configuration_history()[-1]['event_id']
        def choices(plan, units):
            return tuple(Assessment(u.input()['target']['paper_id'], ('include', 'exclude', 'uncertain')[self.ids.index(u.input()['target']['paper_id'])],
                'unknown' if u.input()['target']['paper_id'] == self.ids[2] else 'sufficient',
                'Invented architecture result.', (u.input()['target']['representation']['sha256'],),
                'Fixture only.', ('Not scientific validation.',)) for u in units)
        helper.engine.response = choices
        self.plan = helper.plan(); self.run = helper.start(self.plan['plan_id']); helper.execute(self.run)

    def fields(self, **extra):
        return dict(request_id=uuid.uuid4().hex, name='Synthetic audit', actor='curator', created_at=AT,
            config_event_id=self.revision, run_id=self.run, compare_run_id=None,
            selection=AuditSelection('random', 17, 100), **extra)

    def audit(self, **extra):
        fields = self.fields(); fields.update(extra)
        preview = self.service.preview_audit(**fields)
        return self.service.commit_audit(**fields, expected_preview_sha256=preview['preview_sha256'])

    def review(self, audit, reviewer='curator'):
        return self.service.create_assisted(request_id=uuid.uuid4().hex, audit_id=audit['audit_id'],
            reviewer_id=reviewer, config_event_id=self.revision, confirm_assisted=True)['session_id']

    def command(self, sid, action, value=None):
        with connection(self.project.database_path) as db: revision = _load(db, sid)[2]
        return self.service.review_command(sid, command_id=uuid.uuid4().hex,
            expected_revision=revision, action=action, value=value)

    def test_primary_totals_overlays_failures_and_unassessed_tail_remain_accessible(self):
        value = self.reads.results(self.run)
        self.assertEqual(value['primary'], dict(include=1, exclude=1, uncertain=1, failed=0, not_assessed=0))
        self.assertEqual(value['population_total'], 3); self.assertEqual(value['overlays']['unknown_sufficiency'], 1)
        other = OfflineEngine('synthetic.failed', response=lambda p, units: tuple(AssessmentFailure(u.input()['target']['paper_id'], 'unavailable') for u in units))
        self.h.registry.register(other)
        plan = self.h.plan(engine_id=other.engine_id, budgets=Budgets(max_items_per_execution=1, chunk_size=1))
        run = self.h.start(plan['plan_id']); self.h.execute(run)
        data = self.reads.results(run)
        self.assertEqual(data['primary']['failed'], 1); self.assertEqual(data['primary']['not_assessed'], 2)
        self.assertEqual(len(self.reads.results(run, primary='not_assessed')['items']), 2)
        self.assertEqual(self.reads.results(self.run, primary='exclude')['filtered_total'], 1)
        self.assertEqual(self.reads.results(self.run)['population_total'], 3)

    def test_independent_disagreement_filter_is_an_overlay_not_an_added_total(self):
        engine = OfflineEngine('synthetic.other', outcome='include'); self.h.registry.register(engine)
        run = self.h.start(self.h.plan(engine_id=engine.engine_id)['plan_id']); self.h.execute(run)
        data = self.reads.results(self.run, compare_run_id=run)
        self.assertEqual(data['overlays']['disagreement'], 2)
        self.assertEqual(sum(data['primary'].values()), 3)
        self.assertEqual(self.reads.results(self.run, compare_run_id=run, overlay='disagreement')['filtered_total'], 2)
        with self.assertRaises(ContractError): self.reads.results(self.run, compare_run_id=self.run)

    def test_pagination_is_bounded_and_rejects_changed_live_views(self):
        first = self.reads.results(self.run, limit=1)
        self.assertEqual(len(first['items']), 1)
        with self.assertRaises(ContractError): self.reads.results(self.run, offset=1, limit=1)
        second = self.reads.results(self.run, offset=1, limit=1, expected_revision=first['revision'])
        self.assertNotEqual(first['items'][0]['paper_id'], second['items'][0]['paper_id'])
        sid = self.review(self.audit())
        self.command(sid, 'save_next', dict(sufficiency='sufficient', decision='included', review_extent='metadata', rationale='Explicit synthetic human observation.'))
        with self.assertRaises(ContractError): self.reads.results(self.run, offset=1, expected_revision=first['revision'])
        with self.assertRaises(ContractError): self.reads.results(self.run, overlay='unknown_sql OR 1=1')
        with self.assertRaises(ContractError): self.reads.results(self.run, limit=101)

    def test_preview_is_read_only_deterministic_and_commit_is_replay_safe(self):
        from test_populations import fingerprint
        fields = self.fields(); before = fingerprint(self.project.root)
        with patch('socket.create_connection', side_effect=AssertionError('No network')):
            a = self.service.preview_audit(**fields)
            b = self.service.preview_audit(**{**fields, 'request_id': uuid.uuid4().hex})
        self.assertEqual(before, fingerprint(self.project.root)); self.assertEqual(a['member_manifest_sha256'], b['member_manifest_sha256'])
        saved = self.service.commit_audit(**fields, expected_preview_sha256=a['preview_sha256'])
        again = self.service.commit_audit(**fields, expected_preview_sha256=a['preview_sha256'])
        self.assertTrue(again['replayed']); self.assertEqual(saved['audit_id'], again['audit_id'])
        with self.assertRaises(ContractError): self.service.commit_audit(**{**fields, 'name': 'changed'}, expected_preview_sha256=a['preview_sha256'])
        self.assertTrue(self.service.verify_audit(saved['audit_id'])['verified'])
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))

    def test_strata_overlap_and_empty_audits_are_explicit_and_never_hide_unsampled_papers(self):
        audit = self.audit(selection=AuditSelection('stratified', 91, 2, ('uncertain', 'unknown_sufficiency', 'exclude')))
        self.assertEqual(audit['selected_count'], 2); self.assertEqual(audit['selection_overlap_count'], 1)
        self.assertEqual(self.reads.results(self.run)['population_total'], 3)
        empty = self.audit(selection=AuditSelection('random', 4, 10, primary_filter='failed'))
        self.assertEqual(empty['selected_count'], 0)
        with self.assertRaises(ContractError): self.review(empty)

    def test_audits_remain_exact_after_source_progress_restart_and_ref_changes(self):
        plan = self.h.plan(); run = self.h.start(plan['plan_id'])
        saved = self.audit(run_id=run); old = self.service.audit(saved['audit_id'])
        self.assertTrue(all(x['primary_state'] == 'not_assessed' for x in old['items']))
        self.h.execute(run)
        reopened = CurationService(Project.open(self.project.root))
        self.assertEqual(old, reopened.audit(saved['audit_id']))
        self.assertTrue(reopened.verify_audit(saved['audit_id'])['verified'])

    def test_source_revision_changes_refuse_stale_audit_commit_and_atomic_failure(self):
        plan = self.h.plan(); run = self.h.start(plan['plan_id']); fields = self.fields(); fields['run_id'] = run
        preview = self.service.preview_audit(**fields); self.h.execute(run)
        with self.assertRaises(ContractError): self.service.commit_audit(**fields, expected_preview_sha256=preview['preview_sha256'])
        with connection(self.project.database_path, write=True) as db:
            db.execute("CREATE TRIGGER synthetic_fail_member BEFORE INSERT ON ct_curation_audit_members BEGIN SELECT RAISE(ABORT,'controlled rollback'); END")
        with self.assertRaises(sqlite3.DatabaseError): self.audit()
        self.assertEqual(self.service.audits()['total'], 0)

    def test_assisted_human_save_finish_authorization_and_atomic_source_links(self):
        audit = self.audit(); sid = self.review(audit)
        frozen = SessionService(self.project).view(sid)
        self.assertEqual(frozen['mode'], 'operational')
        with self.assertRaises(ContractError):
            GuidedReviewService(self.project).command(sid, command_id=uuid.uuid4().hex, expected_revision=frozen['revision'], action='skip')
        observed = self.command(sid, 'save_next', dict(sufficiency='sufficient', decision='included', review_extent='metadata', rationale='Explicit human read, fixture only.'))
        self.assertTrue(all(self.project.reviews.membership(p)['state'] == 'not_reviewed' for p in self.ids))
        self.command(sid, 'finish', {'preserve_undecided': True})
        prepared = self.command(sid, 'prepare_publication')['result']['plan_sha256']
        with connection(self.project.database_path, write=True) as db:
            db.execute("CREATE TRIGGER synthetic_fail_link BEFORE INSERT ON ct_classifier_authority_links WHEN json_extract(NEW.payload_json,'$.kind')='authorization' BEGIN SELECT RAISE(ABORT,'controlled source-link failure'); END")
        with self.assertRaises(sqlite3.DatabaseError): self.command(sid, 'publish', {'plan_sha256': prepared, 'confirm_authority': True})
        self.assertTrue(all(self.project.reviews.membership(p)['state'] == 'not_reviewed' for p in self.ids))
        with connection(self.project.database_path, write=True) as db: db.execute('DROP TRIGGER synthetic_fail_link')
        receipt = self.command(sid, 'publish', {'plan_sha256': prepared, 'confirm_authority': True})
        self.assertTrue(receipt['result']['membership_changed'])
        outcome = self.service.outcomes(audit['audit_id'])
        self.assertEqual({v['kind'] for v in outcome['items']}, {'observation', 'authorization'})
        self.assertIn(observed['result']['observation_event_id'], {v['review_event_id'] for v in outcome['items']})
        with connection(self.project.database_path) as db:
            links = [json.loads(r[0]) for r in db.execute('SELECT payload_json FROM ct_classifier_authority_links')]
        self.assertTrue(all(v['original_producer_unchanged'] for v in links))

    def test_unauthorized_reviewer_cannot_publish_and_does_not_gain_authority_from_assistance(self):
        audit = self.audit(); sid = self.review(audit, reviewer='not-authorized')
        self.command(sid, 'save_next', dict(sufficiency='insufficient', decision=None, review_extent='metadata', rationale='Cannot establish a judgment.'))
        self.command(sid, 'finish', {'preserve_undecided': True})
        with self.assertRaises(ContractError): self.command(sid, 'prepare_publication')
        self.assertTrue(all(self.project.reviews.membership(p)['state'] == 'not_reviewed' for p in self.ids))

    def correction(self, **extra):
        return dict(request_id=uuid.uuid4().hex, run_id=self.run, audit_id=None, paper_id=self.ids[0],
            reference_version_id=self.h.ref, actor='curator', created_at=AT, config_event_id=self.revision,
            label='out_of_scope', evidence_used=['metadata'], rationale='Explicit invented boundary correction.',
            attest=True, replace_existing=True, **extra)

    def test_reference_correction_is_a_successor_and_reassessment_is_separately_explicit(self):
        old_results = self.h.results(self.run); old_reference = self.project.references.inspect(self.h.ref)
        fields = self.correction(); preview = self.service.preview_correction(**fields)
        with self.assertRaises(ContractError): self.service.preview_correction(**{**fields, 'attest': False})
        saved = self.service.commit_correction(**fields, expected_preview_sha256=preview['preview_sha256'])
        self.assertTrue(self.service.commit_correction(**fields, expected_preview_sha256=preview['preview_sha256'])['replayed'])
        self.assertEqual(self.h.results(self.run), old_results)
        self.assertEqual(self.project.references.inspect(self.h.ref), old_reference)
        self.assertEqual(self.h.service.runs()['total'], 1)
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))
        new = self.h.plan(reference_version_id=saved['reference_version_id']); calls = self.h.engine.calls
        request = dict(registry=self.h.registry, request_id=uuid.uuid4().hex, plan_id=new['plan_id'], parent_run_id=self.run, actor='curator', created_at=AT)
        next_run = self.service.request_reassessment(**request)
        self.assertEqual(self.h.engine.calls, calls)
        self.assertEqual(self.h.service.inspect_run(next_run['run_id'])['status'], 'planned')
        self.h.execute(next_run['run_id'])
        self.assertEqual(self.h.service.inspect_plan(new['plan_id'])['reference_version_id'], saved['reference_version_id'])
        self.assertEqual(self.h.results(self.run), old_results)
        self.assertTrue(self.service.request_reassessment(**request)['replayed'])

    def test_schema40_open_is_read_only_and_explicit_upgrade_preserves_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'old'
            with patch('corpustrail._internal.database.migrations', return_value=migrations()[:40]):
                old = Project.create(root, ProjectConfig('cp9-legacy', 'Old fixture', 'Synthetic'), created_by='fixture', created_at=AT)
            body = old.database_path.read_bytes()
            reopened = Project.open(root); self.assertEqual(body, reopened.database_path.read_bytes())
            self.assertFalse(CurationService(reopened).audits()['available'])
            backup = 'backups/before-curation.sqlite3'
            with closing(sqlite3.connect(old.database_path)) as db:
                original_dump = list(db.iterdump())
            upgraded = Project.upgrade(root, backup=backup)
            # Existing upgrade uses SQLite's backup API, which can change page
            # header counters. Preserve every schema/data statement, not an
            # unsupported byte-identical database-file promise.
            with closing(sqlite3.connect(root / backup)) as db:
                self.assertEqual(list(db.iterdump()), original_dump)
            with closing(sqlite3.connect(upgraded.database_path)) as db:
                self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0], 41)

    def test_immutable_audit_members_and_corruption_refusal(self):
        saved = self.audit()
        with connection(self.project.database_path, write=True) as db:
            with self.assertRaises(sqlite3.DatabaseError): db.execute('DELETE FROM ct_curation_audit_members')
        with connection(self.project.database_path, write=True) as db:
            db.execute('DROP TRIGGER ct_curation_audit_members_no_update')
            db.execute("UPDATE ct_curation_audit_members SET payload_json='{}' WHERE position=0")
        with self.assertRaises(ContractError): self.service.verify_audit(saved['audit_id'])

    def test_concurrent_identical_audit_command_has_one_durable_selection(self):
        fields=self.fields();preview=self.service.preview_audit(**fields);results=[];errors=[]
        def freeze():
            try:results.append(self.service.commit_audit(**fields,expected_preview_sha256=preview['preview_sha256']))
            except Exception as error:errors.append(type(error).__name__)
        workers=[threading.Thread(target=freeze) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(10)
        self.assertFalse(errors);self.assertEqual(len(results),2)
        self.assertEqual(len({x['audit_id'] for x in results}),1);self.assertEqual(self.service.audits()['total'],1)
        self.assertEqual(sum(x['replayed'] for x in results),1)

    def test_correction_lineage_cannot_claim_an_unrelated_audit_run(self):
        audit=self.audit();other=self.h.start(self.h.plan()['plan_id'])
        fields={**self.correction(),'run_id':other,'audit_id':audit['audit_id']}
        with self.assertRaisesRegex(ContractError,'not a source'):self.service.preview_correction(**fields)

    def test_interrupted_correction_rolls_back_successor_and_workflow_together(self):
        fields=self.correction();preview=self.service.preview_correction(**fields)
        before=self.project.references.versions()['total']
        with connection(self.project.database_path,write=True) as db:
            db.execute("CREATE TRIGGER synthetic_fail_workflow BEFORE INSERT ON ct_curation_workflow_events BEGIN SELECT RAISE(ABORT,'controlled workflow failure'); END")
        with self.assertRaises(sqlite3.DatabaseError):self.service.commit_correction(**fields,expected_preview_sha256=preview['preview_sha256'])
        self.assertEqual(self.project.references.versions()['total'],before);self.assertEqual(self.service.workflow()['total'],0)

    def test_assisted_creation_replay_and_stale_configuration_do_not_duplicate_sessions(self):
        audit=self.audit();fields=dict(request_id=uuid.uuid4().hex,audit_id=audit['audit_id'],reviewer_id='curator',config_event_id=self.revision,confirm_assisted=True)
        first=self.service.create_assisted(**fields);second=self.service.create_assisted(**fields)
        self.assertEqual(first['session_id'],second['session_id']);self.assertEqual(self.service.assisted_sessions(audit['audit_id'])['total'],1)
        with self.assertRaises(ContractError):self.service.create_assisted(**{**fields,'reviewer_id':'another'})
        with self.assertRaises(ContractError):self.service.create_assisted(**{**fields,'request_id':uuid.uuid4().hex,'config_event_id':'stale'})

    def test_schema40_upgrade_preserves_real_frozen_cp8_results_and_reference_evidence(self):
        from test_classification import ClassificationTests
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:40]):
            old=ClassificationTests();old.setUp()
        self.addCleanup(old.doCleanups)
        plan=old.plan();run=old.start(plan['plan_id']);old.execute(run)
        results=old.results(run);reference=old.project.references.inspect(old.ref)
        before=old.project.database_path.read_bytes();root=old.project.root
        self.assertFalse(CurationService(Project.open(root)).audits()['available'])
        self.assertEqual(before,old.project.database_path.read_bytes())
        revision=old.project.configuration_history()[-1]['event_id']
        with self.assertRaises(ContractError):Project.upgrade(root,backup='backups/stale-curation.sqlite3',expected_config_event='stale')
        self.assertFalse((root/'backups/stale-curation.sqlite3').exists())
        upgraded=Project.upgrade(root,backup='backups/curation.sqlite3',expected_config_event=revision)
        self.assertEqual(ClassificationService(upgraded,registry=old.registry).results(run,limit=100)['items'],results)
        self.assertEqual(upgraded.references.inspect(old.ref),reference)
        self.assertTrue(upgraded.populations.verify(old.pop)['verified'])
        self.assertTrue(upgraded.classification.verify_run(run)['verified'])
        with closing(sqlite3.connect(root/'backups/curation.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0],40)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_classifier_results').fetchone()[0],3)

    def test_assisted_projection_cannot_substitute_another_same_paper_assessment(self):
        audit=self.audit();sid=self.review(audit);pid=SessionService(self.project).view(sid)['paper_id']
        other=OfflineEngine('synthetic.independent');self.h.registry.register(other)
        run=self.h.start(self.h.plan(engine_id=other.engine_id)['plan_id']);self.h.execute(run)
        result=next(v for v in self.h.results(run) if v['paper_id']==pid)
        with connection(self.project.database_path,write=True) as db:
            row=db.execute('SELECT payload_json FROM ct_curation_session_sources WHERE session_id=? AND paper_id=?',(sid,pid)).fetchone()
            value=json.loads(row[0]);value['result_ids']=[result['result_id']]
            db.execute('DROP TRIGGER ct_curation_session_sources_no_update')
            db.execute('UPDATE ct_curation_session_sources SET payload_json=?,content_sha256=? WHERE session_id=? AND paper_id=?',
                (json.dumps(value),content_hash(value),sid,pid))
        with self.assertRaises(ContractError):self.service.assisted_sources(sid,pid)
