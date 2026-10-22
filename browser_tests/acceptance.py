"""Actual Chromium / packaged HTTP end-to-end tests; no frontend API mocks."""
import json
import re
import queue
import subprocess
import sys
import threading
import unittest

from playwright.sync_api import expect
from .fixtures import ApplicationFixture, ABSTRACT, SCOPE, TITLE, FOOTNOTE, AT, fingerprint
from .lifecycle import RequestLedger, finalize_case, settle_reads


class BrowserAcceptance(unittest.TestCase):
    runtime = None  # Explicit runner-owned browser/report; never auto-discovered.

    def tools_page(self,path):
        self.visit(path);expect(self.page.locator('#tools-content')).to_have_attribute('aria-busy','false')

    def confirm_tools(self,label,*,remote=False):
        expect(self.page.locator('#tools-operation')).to_be_visible()
        self.page.locator('#tools-confirm').check()
        if remote:self.page.locator('#tools-transfer').check()
        self.page.get_by_role('button',name=label,exact=True).click()
        expect(self.page.locator('#operation-summary .badge')).to_contain_text('complete',timeout=15000)
        self.assertEqual(self.page.locator('#tools-message.error').count(),0)

    def test_handoff_empty_workspaces_and_read_only_navigation(self):
        self.open_project();before=fingerprint(self.fixture.root)
        for path,title in (('/prioritization','Review order'),('/knowledge','Knowledge'),('/models','Models'),('/export','Export')):
            self.tools_page(path);expect(self.page.locator('#tools-title')).to_have_text(title)
            self.layout()
        expect(self.page.locator('#tools-content')).to_contain_text('No confirmed corpus members yet')
        expect(self.page.get_by_role('button',name='Preview bibliography export')).to_have_count(0)
        self.snapshot('handoff-empty-export')
        self.page.locator('nav details > summary').focus();self.page.keyboard.press('Enter')
        expect(self.page.locator('nav details')).to_have_attribute('open','')
        self.page.get_by_role('link',name='Models',exact=True).click()
        expect(self.page.locator('#tools-title')).to_have_text('Models')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.model_wire.calls,[]);self.assertEqual(self.fixture.transport.calls,[])

    def test_handoff_knowledge_assertion_authority_history_and_restart(self):
        from dataclasses import replace
        p=self.fixture.project
        p.configure(replace(p.config,config_version=p.config.config_version+1,review=replace(p.config.review,authorized_reviewers=('fixture_reviewer',))),
            expected_event_id=p.configuration_history()[-1]['event_id'],created_by='fixture',created_at=AT)
        self.open_project();self.tools_page('/knowledge');self.layout();self.snapshot('handoff-knowledge')
        self.page.locator('#tools-paper-query').fill('Evidence reference')
        self.page.get_by_role('button',name='Search project',exact=True).click()
        self.page.get_by_role('button',name='Use this publication',exact=True).click()
        self.page.locator('#tools-actor').fill('fixture_reviewer');self.page.locator('#knowledge-field').select_option('ct.organism_population')
        self.page.locator('#knowledge-value').fill('Invented material specimen')
        self.page.locator('#knowledge-evidence').select_option(index=1)
        self.page.locator('#knowledge-rationale').fill('Synthetic human reading; not a model or membership decision.')
        self.page.get_by_role('button',name='Preview human observation',exact=True).click()
        expect(self.page.locator('#operation-summary')).to_contain_text('non-authoritative')
        self.assertEqual(p.knowledge_store.assertions(),[]);self.layout();self.snapshot('handoff-assertion-preview')
        self.confirm_tools('Confirm Knowledge Record');self.page.get_by_role('button',name='Refresh this workspace',exact=True).click()
        expect(self.page.locator('#tools-content')).to_have_attribute('aria-busy','false')
        self.page.locator('#knowledge-predicate').select_option('ct.organism_population')
        expect(self.page.get_by_role('button',name='Inspect evidence, conflicts and history',exact=True)).to_have_count(1)
        self.page.get_by_role('button',name='Inspect evidence, conflicts and history',exact=True).click()
        expect(self.page.locator('#knowledge-detail')).to_contain_text('Invented material specimen')
        self.page.locator('#event-reviewer').fill('fixture_reviewer');self.page.locator('#event-rationale').fill('Explicit synthetic claim validation, not membership.')
        self.page.get_by_role('button',name='Preview Knowledge event',exact=True).click()
        self.confirm_tools('Confirm Knowledge Record')
        self.tools_page('/knowledge');self.page.locator('#knowledge-predicate').select_option('ct.organism_population')
        expect(self.page.get_by_role('button',name='Inspect evidence, conflicts and history',exact=True)).to_have_count(1)
        self.page.get_by_role('button',name='Inspect evidence, conflicts and history',exact=True).click()
        self.page.get_by_role('button',name='Inspect history page',exact=True).click()
        expect(self.page.locator('#knowledge-detail')).to_contain_text('validates');self.layout();self.snapshot('handoff-knowledge-detail')
        self.assertEqual(len(p.knowledge_store.assertions()),1)
        self.assertTrue(all(p.reviews.membership(pid)['state']=='not_reviewed' for pid in self.fixture.papers))
        before=fingerprint(self.fixture.root);self.restart();self.open_project();self.tools_page('/knowledge')
        self.assertEqual(before,fingerprint(self.fixture.root));self.assertEqual(self.fixture.model_wire.calls,[])

    def test_handoff_model_configuration_synthetic_connection_and_exact_task(self):
        from dataclasses import replace
        from corpustrail.models import ModelConfig
        p=self.fixture.project
        p.configure(replace(p.config,config_version=p.config.config_version+1,models=(ModelConfig('synthetic-task','synthetic-wire','synthetic-model'),)),
            expected_event_id=p.configuration_history()[-1]['event_id'],created_by='fixture',created_at=AT)
        self.open_project();self.tools_page('/models');self.layout();self.snapshot('handoff-models')
        for selector,text in (('#tools-actor','fixture_reviewer'),('#model-workflow','local-experimental'),('#model-name','user-configured-model'),('#model-endpoint','http://127.0.0.1:9/v1')):
            self.page.locator(selector).fill(text)
        self.page.locator('#model-execution').select_option('local');self.page.locator('#model-frozen').check()
        self.page.get_by_role('button',name='Preview model configuration',exact=True).click()
        expect(self.page.locator('#operation-summary')).to_contain_text('Configuration only')
        self.assertEqual(len(p.config.models),1);self.layout();self.snapshot('handoff-model-configuration')
        self.confirm_tools('Save Model Configuration');self.assertEqual(len(p.config.models),2)
        self.tools_page('/models');self.page.locator('#model-existing').select_option('local-experimental')
        expect(self.page.locator('#model-endpoint')).to_have_value('http://127.0.0.1:9/v1')
        expect(self.page.locator('#model-workflow')).to_have_value('local-experimental')
        self.page.locator('#model-test-actor').fill('fixture_reviewer')
        self.page.locator('article').filter(has=self.page.get_by_role('heading',name='synthetic-task',exact=True)).get_by_role('button',name='Preview synthetic connection test').click()
        self.assertEqual(self.fixture.model_wire.calls,[]);self.layout();self.snapshot('handoff-connection')
        self.confirm_tools('Run Synthetic Connection Test',remote=True)
        self.assertEqual([v[0] for v in self.fixture.model_wire.calls],['connection'])
        self.assertEqual(p.knowledge_store.assertions(),[])
        self.page.locator('#tools-paper-query').fill('Evidence reference');self.page.get_by_role('button',name='Search project',exact=True).click()
        self.page.get_by_role('button',name='Use this publication',exact=True).click()
        self.page.locator('#task-actor').fill('fixture_reviewer');self.page.locator('#task-workflow').select_option('synthetic-task')
        self.page.locator('#task-instructions').fill('Invented offline characterization; no scientific-performance claim.')
        self.page.locator('#task-predicate').select_option('ct.organism_population')
        self.page.get_by_role('button',name='Preview exact Knowledge task',exact=True).click()
        self.page.get_by_text('Inspect exact frozen plan and input',exact=True).click()
        expect(self.page.locator('#operation-summary > details').filter(has=self.page.get_by_text('Inspect exact frozen plan and input',exact=True)).locator('pre')).to_contain_text('Evidence reference')
        self.layout();self.snapshot('handoff-task')
        self.confirm_tools('Authorize and Run This Exact Task',remote=True)
        self.assertEqual([v[0] for v in self.fixture.model_wire.calls],['connection','task'])
        self.assertEqual(len(p.knowledge_store.assertions()),1)
        self.assertEqual(p.knowledge_store.assertions()[0]['payload']['initial_authority'],'non_authoritative')
        self.assertTrue(all(p.reviews.membership(pid)['state']=='not_reviewed' for pid in self.fixture.papers))
        self.assertEqual(self.fixture.transport.calls,[])

    def test_handoff_ordering_preserves_complete_tail_and_authority(self):
        from corpustrail.curation import ReviewEvent,EvidenceBasis
        from dataclasses import replace
        p=self.fixture.project
        p.configure(replace(p.config,config_version=p.config.config_version+1,review=replace(p.config.review,authorized_reviewers=('fixture_reviewer',))),
            expected_event_id=p.configuration_history()[-1]['event_id'],created_by='fixture',created_at=AT)
        for pid,state in zip(self.fixture.papers[:2],('included','excluded')):
            source=p.identities.observations(pid)[0]['source']
            event=ReviewEvent(pid,state,'sufficient','metadata','Invented training decision','fixture_reviewer',AT,
                (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
                producer_type='human',authority_state='human_authorized')
            p.reviews.apply(p.reviews.plan(event),recorded_at=AT)
        members={pid:p.reviews.membership(pid) for pid in self.fixture.papers}
        self.open_project();self.tools_page('/prioritization')
        expect(self.page.locator('#tools-content')).to_contain_text('Synthetic')
        self.page.locator('#tools-actor').fill('fixture_reviewer')
        self.page.get_by_role('button',name='Preview review ordering',exact=True).click()
        self.confirm_tools('Create Review Ordering')
        self.page.get_by_role('button',name='Refresh this workspace',exact=True).click()
        self.page.get_by_role('button',name='Inspect ordering',exact=True).click()
        expect(self.page.locator('#tools-ranking article')).to_have_count(5)
        expect(self.page.locator('#tools-ranking')).to_contain_text('not calibrated')
        self.layout();self.snapshot('handoff-ordering')
        self.assertEqual(members,{pid:p.reviews.membership(pid) for pid in self.fixture.papers})
        self.assertEqual(self.fixture.transport.calls,[])

    def curation_seed(self):
        from .curation_fixtures import seed
        return seed(self.fixture)

    def test_curation_manual_methods_and_no_implicit_operations(self):
        self.open_project();before=fingerprint(self.fixture.root)
        self.click_after_reads('a[href="/curation"]')
        expect(self.page.locator('#curation-methods')).to_contain_text('Manual only')
        expect(self.page.locator('#curation-runs')).to_contain_text('No assessment runs')
        expect(self.page.locator('#curation-methods')).to_contain_text('Unavailable')
        expect(self.page.locator('#curation-planner')).to_be_hidden()
        self.assertEqual(before,fingerprint(self.fixture.root));self.layout();self.snapshot('curation-manual')
        self.page.get_by_role('link',name='Start or resume method-blind manual review').click()
        expect(self.page.locator('#review-overview')).to_be_visible()

    def open_curation_fixture(self):
        data=self.curation_seed();self.open_project();self.visit('/curation#'+data['runs'][0].split(':')[1])
        expect(self.page.locator('#curation-result-count')).to_contain_text('5 matching candidates')
        return data

    def curation_audit(self,*,primary='',capture='curation-audit-preview'):
        self.page.locator('#curation-primary').select_option(primary)
        self.page.locator('#curation-results-form button').click()
        expect(self.page.locator('#curation-result-count')).to_contain_text('frozen candidates')
        if not self.page.locator('#curation-audit-builder').evaluate('e=>e.open'):
            self.click_after_reads('#curation-audit-builder > summary')
        self.page.locator('#curation-audit-name').fill('Synthetic boundary audit')
        self.page.locator('#curation-audit-actor').fill('fixture_reviewer')
        self.page.locator('#curation-audit-mode').select_option('random')
        self.page.locator('#curation-audit-form button').click()
        expect(self.page.locator('#curation-audit-preview')).to_be_visible()
        self.layout();self.snapshot(capture)
        self.page.locator('#curation-audit-commit').click()
        expect(self.page.locator('#curation-audit-status')).to_contain_text('immutable selected candidates')
        return self.fixture.project

    def test_curation_results_disagreement_audit_correction_and_explicit_reassessment(self):
        from corpustrail.classification.curation import CurationService
        data=self.open_curation_fixture();project=self.fixture.project;service=CurationService(project)
        original=data['service'].results(data['runs'][0]);members={p:project.reviews.membership(p) for p in self.fixture.papers}
        self.layout();self.snapshot('curation-results')
        self.page.locator('#curation-compare').select_option(data['runs'][1])
        self.page.locator('#curation-overlay').select_option('disagreement')
        self.page.locator('#curation-results-form button').click()
        expect(self.page.locator('#curation-results')).to_contain_text('Comparison observation')
        self.layout();self.snapshot('curation-disagreement')
        self.page.locator('#curation-overlay').select_option('')
        self.curation_audit(primary='exclude')
        self.assertEqual(service.audits()['total'],1);audit=service.audits()['items'][0]
        self.assertGreater(audit['selected_count'],0);self.layout();self.snapshot('curation-audit')
        self.page.locator('#curation-audit-members button').first.click()
        expect(self.page.locator('#curation-paper')).to_be_visible()
        expect(self.page.locator('#curation-paper-text')).not_to_be_empty()
        self.layout();self.snapshot('curation-input')
        self.page.locator('#curation-correction-actor').fill('fixture_reviewer')
        self.page.locator('#curation-correction-label').select_option('in_scope')
        self.page.locator('#curation-correction-evidence').select_option('metadata')
        self.page.locator('#curation-correction-rationale').fill('Explicit invented reference correction after audit; not scientific validation.')
        self.page.locator('#curation-correction-attest').check()
        self.page.locator('#curation-correction-form button[type=submit]').click()
        expect(self.page.locator('#curation-correction-preview')).to_be_visible()
        self.layout();self.snapshot('curation-correction')
        self.page.locator('#curation-correction-commit').click()
        expect(self.page.locator('#curation-correction-result')).to_contain_text('Successor reference version')
        history=service.workflow();self.assertEqual(history['total'],1)
        successor=history['items'][0]['reference_version_id'];self.assertNotEqual(successor,data['reference'])
        self.assertEqual(data['service'].results(data['runs'][0]),original)
        self.assertEqual(members,{p:project.reviews.membership(p) for p in self.fixture.papers})
        self.layout();self.snapshot('curation-successor')
        self.page.locator('#curation-reassess').click()
        self.page.locator('#curation-name').fill('Synthetic explicit successor assessment')
        self.page.locator('#curation-actor').fill('fixture_reviewer')
        self.page.locator('#curation-reference').select_option(successor)
        self.page.locator('#curation-plan-form button[type=submit]').click()
        expect(self.page.locator('#curation-plan-preview')).to_be_visible();self.layout();self.snapshot('curation-plan')
        self.page.locator('#curation-plan-commit').click();expect(self.page.locator('#curation-plan-saved')).to_be_visible()
        self.assertEqual(data['service'].runs()['total'],2)
        self.page.locator('#curation-start').click();expect(self.page.locator('#curation-run-status')).to_contain_text('planned')
        self.assertEqual(service.workflow()['total'],2)
        self.assertEqual(data['service'].runs()['items'][-1]['processed'],0)
        self.layout();self.snapshot('curation-reassessment')
        # Poll lightweight run progress, not a whole-population result join.
        # The real offline engine is held at its execution boundary; no API
        # response or scientific result is fabricated by this browser test.
        from unittest.mock import patch
        engine,_=self.fixture.curation_registry.get('synthetic.curation-a','fixture/v1')
        assess=engine.assess;release=threading.Event();requests=[]
        path='/api/v1/curation/runs/'+data['service'].runs()['items'][-1]['run_id'].split(':')[1]
        def record(request):
            if request.url.startswith(self.fixture.origin+path):requests.append(request.url.removeprefix(self.fixture.origin))
        def gated(plan,chunk):
            if not release.wait(30):raise AssertionError('controlled curation engine was not released')
            return assess(plan,chunk)
        self.page.on('request',record)
        try:
            with patch.object(engine,'assess',side_effect=gated):
                self.page.locator('#curation-execute').click()
                expect(self.page.locator('#curation-run-status')).to_contain_text('running')
                for _ in range(2):
                    with self.page.expect_response(lambda response:response.url==self.fixture.origin+path,timeout=5000):pass
                self.assertFalse(any('/results' in value for value in requests),requests)
                self.assertEqual(data['service'].runs()['items'][-1]['processed'],0)
                with self.page.expect_response(lambda response:response.url.startswith(self.fixture.origin+path+'/results?'),timeout=15000):
                    release.set()
                    expect(self.page.locator('#curation-run-status')).to_contain_text('completed',timeout=15000)
                from corpustrail.classification.curation_views import CurationReads
                total=CurationReads(project).results(data['service'].runs()['items'][-1]['run_id'],
                    primary=self.page.locator('#curation-primary').input_value(),overlay=self.page.locator('#curation-overlay').input_value())['filtered_total']
                expect(self.page.locator('#curation-result-count')).to_contain_text(str(total)+' matching candidates')
        finally:
            release.set();self.page.remove_listener('request',record)
        self.assertEqual(data['service'].results(data['runs'][0]),original)
        self.assertEqual(members,{p:project.reviews.membership(p) for p in self.fixture.papers})
        before=fingerprint(self.fixture.root);self.restart();self.open_project();self.visit('/curation')
        expect(self.page.locator('#curation-history')).to_contain_text('Human-attested successor reference')
        expect(self.page.locator('#curation-history')).to_contain_text('Explicit reassessment request')
        self.assertEqual(before,fingerprint(self.fixture.root))

    def test_curation_assisted_audit_human_confirmation_and_blinded_isolation(self):
        from corpustrail.classification.curation import CurationService
        from corpustrail.application.review import ReviewController,_handle
        from corpustrail._internal.values import ContractError
        data=self.open_curation_fixture();project=self.fixture.project
        self.curation_audit(primary='exclude',capture='curation-assisted-audit-preview');service=CurationService(project)
        self.page.locator('#curation-reviewer').fill('fixture_reviewer');self.page.locator('#curation-assisted-confirm').check()
        self.page.locator('#curation-assisted-form button').click()
        expect(self.page.locator('#review-assisted')).to_be_visible()
        self.assertFalse(self.page.locator('input[name=assessment]:checked').count())
        self.assertEqual(self.page.locator('#review-extent').input_value(),'')
        sid=service.assisted_sessions(service.audits()['items'][0]['audit_id'])['items'][0]['session_id']
        with self.assertRaises(ContractError):ReviewController().view(project,_handle(sid))
        self.layout();self.snapshot('curation-assisted')
        self.page.locator('input[name=assessment][value=included]').check()
        self.page.locator('#review-extent').select_option('metadata')
        self.page.locator('#review-rationale').fill('Explicit invented human correction, separate from the engine.')
        self.page.locator('#review-save-next').click()
        expect(self.page.locator('#review-message')).to_contain_text('Human observation saved')
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        self.page.locator('#review-finish').click()
        expect(self.page.locator('#review-completion-heading')).to_have_text('Review completed — read only')
        self.layout();self.snapshot('curation-assisted-completed')
        self.page.locator('#review-prepare-publication').click();expect(self.page.locator('#review-publication')).to_be_visible()
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        self.page.locator('#review-publish').click();expect(self.page.locator('#review-message')).to_contain_text('confirmed decisions')
        self.assertEqual(sum(project.reviews.membership(p)['state']=='included' for p in self.fixture.papers),1)
        self.layout();self.snapshot('curation-assisted-confirmed')
        outcomes=service.outcomes(service.audits()['items'][0]['audit_id'])
        self.assertEqual({v['kind'] for v in outcomes['items']},{'observation','authorization'})
        self.assertEqual(data['service'].inspect_run(data['runs'][0])['processed'],5)

    def test_curation_failed_and_unassessed_candidates_remain_accessible(self):
        from corpustrail.classification import Budgets,AssessmentFailure
        from unittest.mock import patch
        data=self.curation_seed();project=self.fixture.project;engine,_=self.fixture.curation_registry.get('synthetic.curation-a','fixture/v1')
        fields=dict(request_id='c'*32,name='Synthetic partial failure',actor='fixture_reviewer',created_at=AT,
            config_event_id=project.configuration_history()[-1]['event_id'],population_version_id=data['population'],reference_version_id=data['reference'],
            engine_id='synthetic.curation-a',engine_version='fixture/v1',budgets=Budgets(chunk_size=1,max_items_per_execution=1))
        service=data['service'];preview=service.prepare(**fields);plan=service.commit_plan(**fields,expected_preview_sha256=preview['preview_sha256'])
        run=service.start_run(plan['plan_id'],request_id='d'*32,actor='fixture_reviewer',created_at=AT)['run_id']
        with patch.object(engine,'assess',side_effect=lambda p,units:tuple(AssessmentFailure(u.input()['target']['paper_id'],'unavailable') for u in units)):
            service.execute(run,expected_revision=service.inspect_run(run)['revision'],clock=lambda:AT)
        self.open_project();self.visit('/curation#'+run.split(':')[1]);expect(self.page.locator('#curation-result-count')).to_contain_text('5 matching candidates')
        self.page.locator('#curation-primary').select_option('failed');self.page.locator('#curation-results-form button').click()
        expect(self.page.locator('#curation-result-count')).to_contain_text('1 matching candidate')
        self.page.locator('#curation-primary').select_option('not_assessed');self.page.locator('#curation-results-form button').click()
        expect(self.page.locator('#curation-result-count')).to_contain_text('4 matching candidates')
        self.layout();self.snapshot('curation-tail')
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))

    def test_curation_bounded_context_picker_and_exact_reference_inspection(self):
        from corpustrail.references import ContextStrategy
        data=self.curation_seed();project=self.fixture.project;contexts=[]
        for index,pid in enumerate(self.fixture.papers):
            fields=dict(request_id=str(index+5)*32,version_id=data['reference'],target_paper_id=pid,
                target_basis='metadata',actor='fixture_reviewer',created_at=AT,
                config_event_id=project.configuration_history()[-1]['event_id'],held_out_paper_ids=[],dependency_ids=[],
                strategy=ContextStrategy(in_scope=2,out_of_scope=2))
            preview=project.references.prepare_context(**fields)
            contexts.append(project.references.commit_context(**fields,expected_preview_sha256=preview['preview_sha256'])['context_id'])
        self.open_project();self.visit('/curation');expect(self.page.locator('#curation-engine')).to_be_visible()
        self.page.locator('#curation-name').fill('Synthetic bounded-context curation')
        self.page.locator('#curation-actor').fill('fixture_reviewer')
        self.page.locator('#curation-engine').select_option('synthetic.curation-a|fixture/v1')
        self.page.locator('#curation-population').select_option(data['population'])
        self.page.locator('#curation-reference').select_option(data['reference'])
        self.page.locator('#curation-input-mode').select_option('bounded_context')
        expect(self.page.locator('#curation-contexts input')).to_have_count(5)
        for box in self.page.locator('#curation-contexts input').all():box.check()
        self.page.locator('#curation-plan-form button[type=submit]').click()
        expect(self.page.locator('#curation-plan-preview')).to_be_visible();self.layout();self.snapshot('curation-bounded-plan')
        self.page.locator('#curation-plan-commit').click();expect(self.page.locator('#curation-plan-saved')).to_be_visible()
        self.page.locator('#curation-start').click();expect(self.page.locator('#curation-run-status')).to_contain_text('planned')
        self.page.locator('#curation-execute').click();expect(self.page.locator('#curation-run-status')).to_contain_text('completed',timeout=15000)
        run=data['service'].runs()['items'][-1];plan=data['service'].inspect_plan(run['plan_id'])
        self.assertEqual(plan['input_mode'],'bounded_context')
        self.assertEqual({data['service'].exact_input(run['plan_id'],pid)['context_id'] for pid in self.fixture.papers},set(contexts))
        self.page.locator('#curation-results button').first.click();expect(self.page.locator('#curation-input-references')).to_contain_text('Reference')
        self.page.locator('#curation-input-references button').first.click();expect(self.page.locator('#curation-reference-text')).not_to_be_empty()
        self.layout();self.snapshot('curation-bounded-input')
        self.assertTrue(data['service'].verify_run(run['run_id'])['verified'])
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))

    def setUp(self):
        # Review order uses canonical IDs. Stabilize only synthetic visual IDs;
        # every run still has a private root, lock directory and browser context.
        self.fixture = ApplicationFixture(project_id='browser-handoff-fixture' if 'handoff' in self._testMethodName else 'browser-curation-fixture' if 'curation' in self._testMethodName else 'browser-guided-fixture' if 'review' in self._testMethodName else
            'browser-population-fixture' if 'population' in self._testMethodName else
            'browser-reference-fixture' if 'reference' in self._testMethodName else None,
            long_path='long_paths' in self._testMethodName,
            alpha_workflow=self._testMethodName=='test_review_guided_save_finish_publish_and_resume')
        self.addCleanup(self.fixture.close)
        self.context = self.runtime.browser.new_context(viewport=self.runtime.viewport,
            device_scale_factor=1, locale='en-US', timezone_id='UTC', color_scheme='light',
            reduced_motion='reduce', service_workers='block')
        self.addCleanup(self.runtime.close_context, self)
        self.context.tracing.start(screenshots=True, snapshots=False, sources=False)
        if 'reference' in self._testMethodName or 'curation' in self._testMethodName or 'handoff' in self._testMethodName:
            # Control only synthetic form operation IDs at their generation
            # boundary. Same-paper contradictory assignments otherwise change
            # hash order across independent screenshots. Counter survives this
            # synthetic tab's navigations; never installed in production assets.
            self.context.add_init_script('''(() => {
              let n=Number(window.name||0);
              Object.defineProperty(crypto,'randomUUID',{value:()=>{
                window.name=String(++n);return '00000000-0000-4000-8000-'+n.toString(16).padStart(12,'0');
              }});
            })();''')
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.diagnostics = []
        self.tokens = set()
        self.expected_http_errors = set()
        self.expected_console_errors = []
        self.expected_transport_failure = False
        self.local_requests=0
        self.external_requests=0
        self.csp_enforcement_checks=0
        self.request_ledger=RequestLedger(self.fixture.origin)
        self.pending_requests=self.request_ledger.pending
        self.navigation_timeouts=[]
        self.page.on('request',self.request_ledger.begin)
        self.page.on('response',self.request_ledger.response)
        self.page.on('requestfinished',lambda request:self.request_ledger.end(request,'finished'))
        self.page.on('requestfailed',lambda request:self.request_ledger.end(request,'failed'))
        def route(request_route):
            request = request_route.request
            if not request.url.startswith(self.fixture.origin+'/'):
                self.external_requests+=1
                self.diagnostics.append('Unexpected external browser request')
                request_route.abort()
            else:
                self.local_requests+=1
                request_route.continue_()
        self.context.route('**/*', route)
        self.page.on('pageerror', lambda error: self.diagnostics.append('JavaScript: '+str(error)))
        def console(msg):
            if msg.type!='error':return
            if msg.text in self.expected_console_errors:
                self.expected_console_errors.remove(msg.text);return
            if not (self.expected_transport_failure and 'net::ERR_FAILED' in msg.text):
                self.diagnostics.append('Console: '+msg.text)
        self.page.on('console',console)
        self.page.on('requestfailed', lambda req: self.diagnostics.append('Failed local request: '+req.method+' '+req.url.split('?')[0])
            if not (self.expected_transport_failure and req.url.endswith('/api/v1/review/command')) else None)
        self.page.on('response', lambda response: self.diagnostics.append('HTTP '+str(response.status)+' '+response.url.split('?')[0])
            if response.status>=400 and response.status not in self.expected_http_errors else None)
        self.visit('/')

    def tearDown(self):
        finalize_case(self)

    def visit(self, path):
        # A visible heading can precede a page's final read-only requests.
        # Let them finish before test-driven navigation; never suppress aborted
        # requests or relax diagnostics to accommodate WebKit's reporting.
        self.settle_reads()
        self.page.goto(self.fixture.origin+path, wait_until='networkidle')
        token=self.page.locator('meta[name="corpustrail-session"]').get_attribute('content')
        if token: self.tokens.add(token)
        expect(self.page.locator('main h1:visible')).to_have_count(1)

    def reload(self):
        self.settle_reads()
        self.page.reload(wait_until='networkidle')

    def restart(self):
        self.settle_reads()
        self.fixture.restart()

    def settle_reads(self):
        # load-state networkidle can already be satisfied when a fresh routed
        # request is queued. Observe actual request completion and a continuous
        # quiet interval instead of trusting that stale load-state flag.
        settle_reads(self)

    def open_paper_provenance(self):
        # Bibliographic status renders before the independent evidence read.
        # Its history/eligibility text expands the panel above this native
        # summary. A pointer press across that reflow can land on the panel
        # instead; await actual rendered history and completed reads first.
        expect(self.page.locator('#evidence-history li').first).to_be_visible()
        self.settle_reads()
        self.page.locator('#advanced > summary').click()
        expect(self.page.locator('#advanced')).to_have_attribute('open', '')

    def click_after_reads(self,selector):
        # Do not navigate while a preceding UI action's read is intercepted.
        # Keep orphaned/unfinished requests visible; never clear them on unload.
        self.settle_reads()
        self.page.locator(selector).click()

    def open_project(self):
        self.visit('/projects')
        expect(self.page.locator('#project-list article')).to_have_count(1)
        self.page.get_by_role('button', name='Open Project', exact=True).click()
        expect(self.page.locator('#project-name')).to_have_text('Synthetic materials')

    def snapshot(self, name, full_page=True,subject=None,anchor=None):
        self.runtime.snapshot(self, name, full_page=full_page,subject=subject,anchor=anchor)

    def layout(self):
        result=self.page.evaluate('''() => {
          const visible=e=>e.getClientRects().length>0;
          const fields=[...document.querySelectorAll('input,textarea,select')].filter(visible);
          const unnamed=fields.filter(e=>!e.labels?.length&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')).length;
          const buttons=[...document.querySelectorAll('button,a,summary')].filter(visible);
          const anonymous=buttons.filter(e=>!e.textContent.trim()&&!e.getAttribute('aria-label')).length;
          const escaped=buttons.filter(e=>{const r=e.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).length;
          return {overflow:document.documentElement.scrollWidth-innerWidth,unnamed,anonymous,escaped};
        }''')
        self.assertLessEqual(result['overflow'],1,result)
        self.assertEqual((result['unnamed'],result['anonymous'],result['escaped']),(0,0,0),result)
        # Presentation-only contract: check the actual packaged theme tokens,
        # including secondary text, warning text and keyboard/control boundaries.
        contrast=self.page.evaluate('''() => {
          const s=getComputedStyle(document.documentElement);
          const color=name=>s.getPropertyValue('--'+name).trim();
          const luminance=hex=>{
            const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255)
              .map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
            return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
          };
          const ratio=(a,b)=>{const x=luminance(color(a)),y=luminance(color(b));
            return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
          return {
            text:['canvas','surface','selection'].every(b=>ratio('ink',b)>=4.5),
            secondary:['canvas','surface'].every(b=>ratio('muted',b)>=4.5),
            actions:['canvas','surface','selection'].every(b=>ratio('accent',b)>=4.5),
            warnings:['canvas','surface'].every(b=>ratio('warning',b)>=4.5&&ratio('danger',b)>=4.5),
            boundaries:['canvas','surface'].every(b=>ratio('control-border',b)>=3),
            primary:ratio('surface','accent')>=4.5
          };
        }''')
        self.assertTrue(all(contrast.values()),contrast)

    def fixture_path_checks(self,name):
        """Private local checks; publish hashes/geometry, never pathname bytes."""
        import hashlib
        root=self.fixture.root
        project=root/'disposable-browser-project'
        if name=='wizard':
            fields=[(self.page.locator('#intended-location'),'Will be saved at: '+str(root/self.page.locator('#folder').input_value()))]
        elif name=='wizard-summary':fields=[(self.page.locator('#summary dl dd').last,str(project))]
        elif name=='trash-confirmation':fields=[(self.page.locator('#trash-location'),str(project))]
        elif name=='projects':
            fields=[(self.page.locator('#root-location'),'Projects location: '+str(root))]
            for node in self.page.locator('#project-list .project-location').all():
                text=node.inner_text()
                self.assertIn(text,{str(project),str(root/'materials')},'Unexpected fixture project location')
                fields.append((node,text))
        else:raise AssertionError('No path exception for this capture')
        checks=[]
        for node,expected in fields:
            text=node.inner_text();self.assertEqual(text,expected)
            geometry=node.evaluate('''e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e),range=document.createRange();
              range.selectNodeContents(e);return {height:r.height,line_height:parseFloat(s.lineHeight),
                overflow:e.scrollWidth-e.clientWidth,contained:[...range.getClientRects()].every(t=>
                  t.left>=r.left-1&&t.right<=r.right+1&&t.top>=r.top-1&&t.bottom<=r.bottom+1)};}''')
            checks.append({**geometry,'truthful':True,'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
        self.layout()
        return checks

    def test_home_catalogue_readonly(self):
        before=fingerprint(self.fixture.root)
        if self.runtime.environment['browser']=='webkit':
            # The test-only driver adapter must not bypass production CSP.
            self.expected_console_errors.append("Refused to apply a stylesheet because its hash, its nonce, or 'unsafe-inline' does not appear in the style-src directive of the Content Security Policy.")
            blocked=self.page.evaluate('''() => {
                const style=document.createElement('style');style.textContent='html { outline: 99px solid red !important; }';
                document.head.append(style);const blocked=style.sheet===null;style.remove();return blocked;
            }''')
            self.assertTrue(blocked,'Production CSP must still refuse arbitrary inline CSS')
            self.csp_enforcement_checks+=1
        expect(self.page.get_by_role('heading',name='Welcome to CorpusTrail')).to_be_visible()
        expect(self.page.locator('.workflow li')).to_have_count(7)
        self.assertEqual(self.page.locator('.step-number').all_text_contents(),[str(i) for i in range(1,8)])
        self.assertTrue(self.page.locator('.workflow li').evaluate_all("cards => cards.every(card => ['none','normal',''].includes(getComputedStyle(card, '::after').content))"))
        self.layout();self.snapshot('welcome')
        self.page.get_by_role('link',name='Open Existing Project',exact=True).click()
        expect(self.page.locator('#project-list article')).to_have_count(1)
        self.open_project();self.snapshot('dashboard')
        self.page.get_by_role('link',name='Explore More Publications',exact=True).click()
        expect(self.page.get_by_role('heading',name='Explore',exact=True)).to_be_visible()
        expect(self.page.locator('#providers input')).to_have_count(4)
        self.assertEqual(self.fixture.transport.calls,[])
        self.visit('/papers')
        expect(self.page.locator('#paper-list article')).to_have_count(5)
        self.layout();self.snapshot('catalogue')
        # Existing macOS filter-box regression: compare actual boxes, not labels.
        if self.runtime.viewport['width']>=1000:
            boxes=[self.page.locator(s).bounding_box() for s in ('#sort','#page-size','#filters button[type="submit"]')]
            self.assertLessEqual(max(b['y'] for b in boxes)-min(b['y'] for b in boxes),1)
            self.assertLessEqual(max(b['height'] for b in boxes)-min(b['height'] for b in boxes),1)
        self.page.get_by_role('combobox',name='Sort by',exact=True).select_option('year_newest')
        self.page.get_by_role('combobox',name='Results per page',exact=True).select_option('50')
        self.page.get_by_role('combobox',name='Evidence',exact=True).select_option('pending')
        self.page.get_by_role('button',name='Apply filters').click()
        expect(self.page.locator('#paper-list article')).to_have_count(1)
        expect(self.page.locator('#paper-list')).to_contain_text('Pending documents: 1')
        self.page.get_by_role('combobox',name='Evidence',exact=True).select_option('')
        self.page.get_by_role('combobox',name='Sort by',exact=True).select_option('title')
        self.page.get_by_role('combobox',name='Results per page',exact=True).select_option('25')
        self.page.get_by_role('button',name='Apply filters').click()
        expect(self.page.locator('#paper-list article')).to_have_count(5)
        self.page.get_by_label('Search papers').fill('without a PMCID')
        self.page.get_by_role('button',name='Apply filters').click()
        expect(self.page.locator('#paper-list article')).to_have_count(1)
        self.page.get_by_role('link',name='Publication without a PMCID',exact=True).click()
        expect(self.page.locator('#evidence-eligibility')).to_contain_text('PMCID')
        expect(self.page.locator('#retrieve-evidence')).to_be_hidden()
        expect(self.page.locator('#paper-status')).to_contain_text('Awaiting corpus decision')
        expect(self.page.locator('#paper-status')).to_contain_text('Human review recorded')
        self.layout();self.snapshot('missing-pmcid')
        for link in self.page.locator('#identifiers a').all():
            self.assertEqual(link.get_attribute('target'),'_blank')
            self.assertTrue(link.get_attribute('href').startswith('https://doi.org/'))
        self.page.locator('#advanced summary').first.click()
        expect(self.page.get_by_role('button',name='Copy CorpusTrail paper ID')).to_be_visible()
        expect(self.page.locator('#raw-details')).not_to_have_attribute('open','')
        self.page.locator('#raw-details summary').click()
        expect(self.page.locator('#provenance-text')).not_to_be_empty()
        self.page.get_by_role('link',name='Home',exact=True).click()
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.transport.calls,[])
        # Actual keyboard focus, not merely a CSS string assertion.
        self.page.keyboard.press('Alt+Tab' if self.runtime.environment['browser']=='webkit' else 'Tab')
        focus=self.page.evaluate('''() => {const e=document.activeElement,c=getComputedStyle(e);return {tag:e.tagName,outline:c.outlineStyle,width:parseFloat(c.outlineWidth)};}''')
        self.assertNotEqual(focus['tag'],'BODY');self.assertNotEqual(focus['outline'],'none');self.assertGreater(focus['width'],0)
        # Resting visual captures must not achieve stability by removing actual
        # hover/focus feedback. Exercise both through normal user input in every
        # engine/viewport, separately from the reviewed resting screenshots.
        action=self.page.get_by_role('link',name='Create New Project',exact=True)
        action.hover()
        expect(action).to_have_css('background-color','rgb(63, 80, 58)')
        self.runtime.prepare_resting_pointer(self)
        expect(action).to_have_css('background-color','rgb(82, 99, 76)')
        action.hover()
        expect(action).to_have_css('background-color','rgb(63, 80, 58)')
        self.runtime.prepare_resting_pointer(self)

    def test_project_journal_search_and_filters(self):
        import hashlib
        from urllib.parse import parse_qs, urlsplit
        from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
        from corpustrail.application.reads import ProjectReads
        project=self.fixture.project
        journal='Journal of Tests: Science & Methods (Series A)'
        for number,source_name in ((6,journal),(7,None)):
            raw=('journal-fixture-'+str(number)).encode()
            source=SourceReference('fixture://journal/'+str(number),str(number),
                'sha256:'+hashlib.sha256(raw).hexdigest(),len(raw),'fixture_discovery',
                '2026-01-01T00:00:00+00:00',identity_status='verified')
            record=BibliographicRecord('Journal search fixture '+str(number),source=source_name,
                identifiers=(Identifier('doi','10.1234/journal.'+str(number)),))
            project.identities.apply(project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
        before=fingerprint(self.fixture.root)
        self.open_project();self.visit('/papers')
        def search(query,expected):
            self.page.get_by_label('Search papers').fill(query)
            with self.page.expect_response(lambda response:'/api/v1/papers?' in response.url) as received:
                self.page.get_by_role('button',name='Apply filters',exact=True).click()
            response=received.value
            data=response.json()
            self.assertEqual(response.status,200)
            self.assertEqual(parse_qs(urlsplit(response.url).query,keep_blank_values=True)['q'],[query.strip()])
            self.assertEqual(data['total'],expected)
            expect(self.page.locator('#paper-list article')).to_have_count(expected)
            self.assertEqual(sorted(self.page.locator('#paper-list h2').all_text_contents()),
                sorted(item['bibliography']['title'] for item in data['items']))
            self.assertEqual(data['total'],ProjectReads(project).papers(q=query.strip(),
                evidence=self.page.locator('#evidence-filter').input_value())['total'])
        for query in ('Synthetic Journal','Synthetic','sYnThEtIc JOURNAL','  Synthetic Journal  '):
            search(query,5)
        search(journal,1);self.layout();self.snapshot('journal-results')
        search('Science & Methods',1)
        self.page.locator('#evidence-filter').select_option('structured_text')
        search(journal,0)
        expect(self.page.locator('#page-count')).to_contain_text('No matching papers')
        self.page.get_by_role('button',name='Clear search and filters',exact=True).click()
        expect(self.page.locator('#paper-list article')).to_have_count(7)
        expect(self.page.locator('#evidence-filter')).to_have_value('')
        expect(self.page.get_by_label('Search papers')).to_have_value('')
        search('Journal search fixture 7',1)  # Missing journal, still searchable by title.
        search('',7)
        search('Legitimately unmatched journal',0);self.layout();self.snapshot('journal-no-results')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.transport.calls,[])

    def test_project_long_paths_wrap_and_keyboard_navigation(self):
        # Behavior coverage, separate from the fixed reviewed visual fixture.
        # The displayed location must still be the complete actual directory.
        before=fingerprint(self.fixture.root)
        self.page.get_by_role('link',name='Create New Project',exact=True).click()
        expect(self.page.locator('#progress')).to_have_text('Step 1 of 6')
        self.page.get_by_label('Project name',exact=True).fill('Disposable browser project')
        self.page.get_by_label('Brief scientific topic description').fill('A synthetic browser-only topic.')
        location=self.page.locator('#intended-location')
        expected='Will be saved at: '+str(self.fixture.root/'disposable-browser-project')
        expect(location).to_have_text(expected)
        geometry=location.evaluate('''e=>{
          const r=e.getBoundingClientRect(),s=getComputedStyle(e),range=document.createRange();
          range.selectNodeContents(e);
          return {height:r.height,lineHeight:parseFloat(s.lineHeight),overflow:e.scrollWidth-e.clientWidth,
            wrap:s.overflowWrap,whitespace:s.whiteSpace,
            contained:[...range.getClientRects()].every(x=>x.left>=r.left-1&&x.right<=r.right+1&&x.top>=r.top-1&&x.bottom<=r.bottom+1)};
        }''')
        self.assertGreater(geometry['height'],geometry['lineHeight'])
        self.assertLessEqual(geometry['overflow'],1)
        self.assertTrue(geometry['contained'])
        self.assertEqual((geometry['wrap'],geometry['whitespace']),('anywhere','pre-wrap'))
        self.layout()
        self.page.get_by_label('Project folder name').focus()
        self.page.keyboard.press('Alt+Tab' if self.runtime.environment['browser']=='webkit' else 'Tab')
        expect(self.page.get_by_role('button',name='Next',exact=True)).to_be_focused()
        self.page.keyboard.press('Enter')
        expect(self.page.locator('#progress')).to_have_text('Step 2 of 6')
        self.layout()
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.transport.calls,[])

    def test_project_wizard_settings_and_confirmation(self):
        self.page.get_by_role('link',name='Create New Project',exact=True).click()
        expect(self.page.locator('#progress')).to_have_text('Step 1 of 6')
        self.page.get_by_role('button',name='Next',exact=True).click()
        expect(self.page.locator('#progress')).to_have_text('Step 1 of 6')
        self.page.get_by_label('Project name',exact=True).fill('Disposable browser project')
        self.page.get_by_label('Brief scientific topic description').fill('A synthetic browser-only topic.')
        self.snapshot('wizard');self.layout()
        self.page.get_by_role('button',name='Next',exact=True).click()
        self.page.get_by_role('textbox',name='Broad-corpus definition',exact=True).fill(SCOPE)
        self.page.get_by_role('button',name='Next',exact=True).click()
        for label in ('OpenAlex','Europe PMC'):
            self.page.get_by_role('checkbox',name=label,exact=True).check()
        self.page.locator('#concepts').fill('porous materials')
        self.page.get_by_role('button',name='Next',exact=True).click()
        self.page.get_by_role('checkbox',name='Europe PMC',exact=True).check()
        self.page.get_by_role('button',name='Next',exact=True).click()
        self.page.get_by_label('Configuration author',exact=True).fill('browser_reviewer')
        expect(self.page.locator('#no-authority')).to_be_checked()
        expect(self.page.locator('#grant-authority')).not_to_be_checked()
        for choice in self.page.locator('.authority-choice').all():
            box=choice.locator('input').bounding_box();label=choice.locator('span').bounding_box()
            self.assertLess(box['x']+box['width'],label['x'])
            self.assertLess(abs(box['y']-label['y']),8)
        self.snapshot('wizard-reviewer');self.layout()
        # Deliberate authority choice, not an implicit first-user privilege.
        self.page.get_by_role('radio',name=re.compile('Authorize corpus decisions')).check()
        self.page.get_by_role('button',name='Next',exact=True).click()
        expect(self.page.locator('#summary')).to_contain_text('OpenAlex, Europe PMC')
        self.assertIn('Authorized corpus reviewers\nbrowser_reviewer',self.page.locator('#summary').inner_text())
        expect(self.page.locator('#authority-confirmation')).to_be_hidden()
        expect(self.page.locator('#creation-confirmation')).to_contain_text('explicit authority choice')
        self.snapshot('wizard-summary');self.layout()
        self.page.get_by_role('button',name='Create Project',exact=True).click()
        expect(self.page.locator('#project-name')).to_have_text('Disposable browser project')
        created=self.fixture.controller.project(self.fixture.controller.active_handle)
        self.assertEqual(created.config.review.authorized_reviewers,('browser_reviewer',))
        self.assertEqual(created.configuration_history()[0]['created_by'],'browser_reviewer')
        self.snapshot('empty-dashboard');self.layout()
        self.page.get_by_role('link',name='Explore Publications',exact=True).click()
        expect(self.page.locator('#history button')).to_have_count(0)
        self.assertEqual(self.fixture.transport.calls,[])
        self.visit('/settings');self.snapshot('settings');self.layout()
        saved=self.page.locator('#description').input_value()
        self.page.locator('#description').fill('Discard this unsaved edit.')
        expect(self.page.locator('#saved-status')).to_contain_text('Unsaved changes')
        self.page.get_by_role('button',name='Discard Changes').click()
        expect(self.page.locator('#description')).to_have_value(saved)
        self.page.locator('#description').fill('Updated topic description from the actual browser.')
        self.page.get_by_role('button',name='Save Changes').click()
        expect(self.page.locator('#message')).to_contain_text('configuration version 2')
        self.page.get_by_role('button',name='Save Changes').click()
        expect(self.page.locator('#message')).to_contain_text('No configuration fields changed')
        self.visit('/projects')
        expect(self.page.locator('.active-project')).to_contain_text('Active project')
        self.snapshot('projects');self.layout()
        expect(self.page.locator('.active-project').get_by_role('button',name='Move to Trash…')).to_be_disabled()
        self.page.get_by_role('button',name='Close Project',exact=True).click()
        expect(self.page.locator('#project-list article')).to_have_count(2)
        expect(self.page.get_by_role('button',name='Close Project',exact=True)).to_have_count(0)
        card=self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Disposable browser project',exact=True))
        before=fingerprint(self.fixture.root)
        card.get_by_role('button',name='Move to Trash…').click()
        expect(self.page.locator('#trash-name')).to_have_text('Disposable browser project')
        expect(self.page.locator('#trash-location')).to_contain_text('disposable-browser-project')
        self.page.locator('#trash-folder').fill('wrong')
        expect(self.page.locator('#trash-execute')).to_be_disabled()
        self.page.locator('#trash-folder').fill('disposable-browser-project')
        expect(self.page.locator('#trash-execute')).to_be_enabled()
        self.snapshot('trash-confirmation');self.layout()
        self.page.get_by_role('button',name='Cancel',exact=True).click()
        expect(self.page.locator('#message')).to_contain_text('Confirmation closed. Cancelling does not move or restore any project.')
        expect(self.page.locator('#project-list article')).to_have_count(2)
        self.assertEqual(before,fingerprint(self.fixture.root))
        # Hold a real cooperating process lease; current-launcher close is not
        # evidence that a project is globally unused.
        root=self.fixture.root/'disposable-browser-project'
        code="import sys;from pathlib import Path;import corpustrail.application.project_use as g;g.lock_directory=lambda:Path(sys.argv[2]);lease=g.acquire_project_use(Path(sys.argv[1]));print('READY',flush=True);sys.stdin.readline()"
        child=subprocess.Popen([sys.executable,'-I','-u','-c',code,str(root),str(self.fixture.base/'locks')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            ready=queue.Queue()
            threading.Thread(target=lambda:ready.put(child.stdout.readline()),daemon=True).start()
            self.assertEqual(ready.get(timeout=10).strip(),'READY')
            self.visit('/projects')
            card=self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Disposable browser project',exact=True))
            expect(card.get_by_role('button',name='Move to Trash…')).to_be_disabled()
            expect(card).to_contain_text(re.compile('in use|another|busy',re.I))
        finally:
            if child.poll() is None:child.kill()
            child.communicate(timeout=10)
        self.visit('/projects');card=self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Disposable browser project',exact=True))
        card.get_by_role('button',name='Open Project').click()
        expect(self.page).to_have_url(re.compile('/dashboard$'))
        expect(self.page.locator('#project-name')).to_have_text('Disposable browser project')
        self.visit('/settings')
        expect(self.page.locator('#description')).to_have_value('Updated topic description from the actual browser.')
        self.page.locator('#configuration-info summary').click()
        expect(self.page.locator('#configuration-history li')).to_have_count(2)
        self.assertEqual(self.fixture.transport.calls,[])

    def prepare_discovery(self):
        self.visit('/discovery')
        expect(self.page.locator('#providers input')).to_have_count(4)
        self.snapshot('discovery-configuration');self.layout()
        self.page.get_by_label('Exact search query').fill('porous materials — microstructure '+('and scientific characterization '*5))
        for checkbox in self.page.locator('[data-provider]').all():checkbox.check()
        self.page.get_by_text('Search limits and retries',exact=True).click()
        self.page.locator('#bound-page_size').fill('5')
        self.page.locator('#bound-max_pages').fill('1')
        self.page.get_by_role('button',name='Preview Search Plan').click()
        expect(self.page.locator('#plan-providers article')).to_have_count(4)
        expect(self.page.locator('#message')).to_have_text('Exact plan saved locally. No database has been contacted.')
        expect(self.page.locator('#approve')).to_be_enabled()
        expect(self.page.locator('#history button')).to_have_count(1)
        self.layout();self.snapshot('discovery-preview')
        self.assertEqual(self.fixture.transport.calls,[])
        expect(self.page.locator('#plan-advanced')).not_to_have_attribute('open','')
        self.page.locator('#plan-advanced summary').click()
        self.assertIn('per_page',self.page.locator('#plan-details').inner_text())
        self.page.locator('#plan-advanced summary').click()
        self.page.locator('#approval-area').scroll_into_view_if_needed()
        self.snapshot('discovery-approval',full_page=False)
        expect(self.page.locator('#approval-providers')).to_have_text('OpenAlex, Crossref, Europe PMC, Semantic Scholar')
        expect(self.page.locator('#approval-disclosure')).to_contain_text('I authorize this exact search')
        expect(self.page.locator('#organization-disclosure')).to_contain_text('I also authorize organizing')
        expect(self.page.locator('#organization-disclosure')).to_contain_text('No corpus-membership decisions')
        expect(self.page.locator('#run')).to_be_hidden()
        self.page.get_by_role('button',name='Approve Search Plan').click()
        expect(self.page.locator('#run')).to_be_visible()
        expect(self.page.locator('#plan-notice')).to_contain_text('Approved — not yet run')
        self.assertEqual(self.fixture.transport.calls,[])

    def test_discovery_exact_approval_execution_and_history(self):
        self.open_project();self.prepare_discovery()
        self.fixture.transport.gate=threading.Event()
        self.page.get_by_role('button',name='Run Search',exact=True).click()
        expect(self.page.locator('#job-status')).to_contain_text('Running')
        expect(self.page.locator('#repeat')).to_be_enabled()
        expect(self.page.locator('#provider-progress li').first).to_have_text(
            'OpenAlex: running · 0 observations preserved · 1 request attempts started')
        self.page.locator('#job-section').scroll_into_view_if_needed()
        # Capture the resting progress state. Scrolling can otherwise place
        # Stop under the old Run-click pointer and unintentionally test hover.
        self.page.mouse.move(0,0)
        self.assertFalse(self.page.locator('#cancel').evaluate("e=>e.matches(':hover')"))
        self.snapshot('discovery-progress',full_page=False,anchor='#job-section')
        self.fixture.transport.gate.set()
        expect(self.page.locator('#job-status')).to_contain_text('4/4 providers finished',timeout=15000)
        expect(self.page.locator('#job-status')).to_contain_text('Completed bounded search')
        expect(self.page.locator('#result-papers a')).to_have_count(5)
        expect(self.page.locator('#history button').first).to_contain_text('Completed bounded search')
        results=self.page.locator('#results').inner_text()
        for text in ('Provider observations preserved\n8','Unique publications linked\n5',
                     'Publications created by this search\n4','Previously known publications\n1'):
            self.assertIn(text,results)
        self.snapshot('discovery-results',subject='#results');self.layout()
        self.assertEqual(len(self.fixture.transport.calls),4)
        self.reload()
        expect(self.page.locator('#history button')).to_have_count(1)
        self.page.locator('#history button').click()
        expect(self.page.locator('#job-status')).to_contain_text('Completed bounded search')
        self.assertEqual(len(self.fixture.transport.calls),4)
        self.page.locator('#result-papers a').filter(has_text='Discovered glass scaffold').first.click()
        expect(self.page.locator('#paper-status')).to_contain_text('Awaiting corpus decision')
        self.open_paper_provenance()
        expect(self.page.locator('#provenance-sources')).to_contain_text(re.compile('Crossref|OpenAlex'))
        self.visit('/discovery');self.page.locator('#history button').click()
        self.page.get_by_role('button',name='Prepare a new search from these settings').click()
        self.page.get_by_role('button',name='Preview Search Plan').click()
        self.page.get_by_role('button',name='Approve Search Plan').click()
        self.fixture.transport.fail_crossref=True
        self.page.get_by_role('button',name='Run Search',exact=True).click()
        expect(self.page.locator('#job-status')).to_contain_text('partial',timeout=15000)
        self.assertIn('Publications created by this search\n0',self.page.locator('#results').inner_text())
        self.assertIn('Previously known publications\n4',self.page.locator('#results').inner_text())
        self.assertEqual(len(self.fixture.project.identities.papers()),9)
        for pid in self.fixture.project.identities.papers():
            self.assertEqual(self.fixture.project.reviews.membership(pid)['state'],'not_reviewed')
        # Terminal counts render before the final preserved-history read.
        expect(self.page.locator('#history button').filter(has_text='Completed with errors / partial')).to_have_count(1)
        self.reload()
        expect(self.page.locator('#history button')).to_have_count(2)
        self.assertEqual(len(self.fixture.transport.calls),8)

    def test_discovery_transport_error_is_not_a_confirmed_rate_limit(self):
        # History is populated asynchronously. Fix the stored plan timestamp,
        # rather than relying on a one-time screenshot rewrite of its DOM row.
        self.fixture.freeze_discovery_clock()
        initial={pid:self.fixture.project.reviews.history(pid) for pid in self.fixture.papers}
        self.open_project();self.visit('/discovery')
        self.fixture.transport.discovery_transport_error=True
        self.page.locator('#query').fill('synthetic transport diagnostic')
        for checkbox in self.page.locator('[data-provider]').all():
            if checkbox.is_enabled():checkbox.set_checked(checkbox.input_value()=='europepmc')
        self.page.get_by_role('button',name='Preview Search Plan',exact=True).click()
        self.page.get_by_role('button',name='Approve Search Plan',exact=True).click()
        self.assertEqual(self.fixture.transport.calls,[])
        self.page.get_by_role('button',name='Run Search',exact=True).click()
        expect(self.page.locator('#job-status')).to_contain_text('1/1 providers finished',timeout=15000)
        expect(self.page.locator('#provider-progress')).to_contain_text('TLS certificate verification failed')
        self.assertNotIn('rate limit',self.page.locator('#provider-progress').inner_text().lower())
        self.assertEqual(len(self.fixture.transport.calls),1)
        from corpustrail._internal.pipeline import events
        records=events(self.fixture.project,kind='request_result')
        self.assertEqual(records[-1]['payload']['error'],'ProviderCertificateError')
        self.assertIsNone(records[-1]['payload']['http_status'])
        self.assertEqual(self.fixture.discovery.history(self.fixture.project)['items'][0]['created_at'],AT)
        expect(self.page.locator('#history button')).to_have_text(
            'synthetic transport diagnostic · Failed — inspect preserved work · '+AT)
        self.settle_reads()
        self.layout();self.snapshot('discovery-transport-error')
        self.reload()
        self.page.locator('#history button').click()
        expect(self.page.locator('#provider-progress')).to_contain_text('TLS certificate verification failed')
        self.assertEqual(len(self.fixture.transport.calls),1)
        for pid in self.fixture.papers:
            self.assertEqual(self.fixture.project.reviews.history(pid),initial[pid])
            self.assertEqual(self.fixture.project.reviews.membership(pid)['state'],'not_reviewed')

    def test_evidence_table_footnotes_persist(self):
        self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click()
        self.fixture.transport.footnotes=True
        self.assertEqual(self.fixture.transport.calls,[])
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-history')).to_contain_text('Exact document identity verified',timeout=15000)
        def read_notes():
            self.page.get_by_role('button',name='Read verified structured text').click()
            expect(self.page.locator('#document-text')).to_contain_text(FOOTNOTE.strip())
            reader=self.page.locator('#document-text').inner_text()
            self.assertEqual(reader.count('Second distinct footnote paragraph.'),1)
            self.assertEqual(reader.count('Independent footnote.'),1)
            self.assertIn('a\n\n'+FOOTNOTE.strip()+'\n\nSecond distinct footnote paragraph.\n\nb\n\nIndependent footnote.',reader)
            self.layout()
        read_notes()
        self.snapshot('evidence-footnotes',subject='#document-text')
        reachable=self.page.locator('#document-text').evaluate('''element => {
          element.scrollTop=element.scrollHeight;
          return element.scrollTop+element.clientHeight>=element.scrollHeight-1;
        }''')
        self.assertTrue(reachable,'Long footnotes must remain reachable by reader scrolling')
        self.reload();read_notes()
        before=fingerprint(self.fixture.root)
        self.restart();self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click();read_notes()
        expect(self.page.locator('#evidence-operations button')).to_have_count(1)
        self.assertEqual(len(self.fixture.transport.calls),1)
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.project.reviews.history(self.fixture.papers[0]),[])
        self.assertEqual(self.fixture.project.reviews.membership(self.fixture.papers[0])['state'],'not_reviewed')

    def start_guided_review(self,reviewer='fixture_reviewer',selection_snapshot='review-session-selection'):
        self.visit('/review')
        expect(self.page.locator('#reviewer')).to_have_value('')
        expect(self.page.locator('#review-population')).to_have_value('')
        self.snapshot(selection_snapshot);self.layout()
        self.page.locator('#reviewer').fill(reviewer)
        self.page.locator('#review-population').select_option('all')
        self.page.get_by_role('button',name='Start Guided Review',exact=True).click()
        expect(self.page.locator('#review-workspace')).to_be_visible()
        expect(self.page.locator('#review-definition')).to_have_text(SCOPE)

    def reference_label(self,query,label='in_scope',extent='metadata',from_current=False):
        self.page.locator('#reference-search').fill(query)
        self.page.locator('#reference-find').click()
        expect(self.page.locator('#reference-find')).to_be_enabled()
        expect(self.page.locator('#reference-choices article')).to_have_count(1)
        row=self.page.locator('#reference-choices article')
        expect(row.locator('h3')).to_contain_text(re.compile(re.escape(query),re.I))
        row.locator('select').select_option(extent)
        row.get_by_role('button',name='Stage Current Corpus Decision as Reference' if from_current else 'Stage Known '+('In-scope' if label=='in_scope' else 'Out-of-scope'),exact=True).click()
        expect(self.page.locator('#reference-message')).to_contain_text('staged only')

    def reference_commit(self):
        self.page.locator('#reference-attest').check()
        self.page.get_by_role('button',name='Preview Reference Batch',exact=True).click()
        expect(self.page.locator('#reference-preview')).to_be_visible()
        self.page.get_by_role('button',name='Commit Reference Version',exact=True).evaluate('b=>{b.click();b.click();}')
        expect(self.page.locator('#reference-message')).to_contain_text('Reference version committed')

    def test_reference_batches_successors_and_restart(self):
        from dataclasses import replace
        from corpustrail.curation import ReviewEvent,EvidenceBasis
        project=self.fixture.project;self.fixture.freeze_reference_clock()
        project.configure(replace(project.config,config_version=2,review=replace(project.config.review,authorized_reviewers=('fixture_reviewer',))),
            expected_event_id=project.configuration_history()[-1]['event_id'],created_by='fixture',created_at=AT)
        pid=self.fixture.papers[1];source=project.identities.observations(pid)[0]['source']
        event=ReviewEvent(pid,'included','sufficient','metadata','Invented explicit prior membership','fixture_reviewer',AT,
            (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),authority_state='human_authorized')
        source_event=project.reviews.apply(project.reviews.plan(event),recorded_at=AT)
        initial={p:project.reviews.history(p) for p in self.fixture.papers}
        self.open_project();before=fingerprint(self.fixture.root)
        self.page.get_by_role('link',name='Reference Collections',exact=True).click()
        expect(self.page.locator('#reference-empty')).to_contain_text('No saved reference versions')
        self.assertEqual(before,fingerprint(self.fixture.root));self.layout();self.snapshot('reference-empty')
        self.page.locator('#reference-name').fill('Synthetic scope examples');self.page.locator('#reference-actor').fill('fixture_reviewer')
        self.page.locator('#reference-rationale').fill('Explicit invented boundary judgment.')
        self.reference_label('without a PMCID',from_current=True);self.reference_label('Metadata-only','out_of_scope')
        self.assertFalse(self.page.locator('#reference-attest').is_checked())
        self.assertEqual(project.references.versions()['total'],0)
        self.page.locator('#reference-attest').check();self.page.locator('#reference-rationale').fill('Explicit invented boundary judgment, reaffirmed before preview.')
        self.assertFalse(self.page.locator('#reference-attest').is_checked())
        self.page.locator('#reference-attest').check();before=fingerprint(self.fixture.root)
        self.page.get_by_role('button',name='Preview Reference Batch',exact=True).click()
        expect(self.page.locator('#reference-preview')).to_be_visible();self.assertEqual(before,fingerprint(self.fixture.root))
        self.layout();self.snapshot('reference-preview')
        self.page.get_by_role('button',name='Commit Reference Version',exact=True).evaluate('b=>{b.click();b.click();}')
        expect(self.page.locator('#reference-message')).to_contain_text('Reference version committed')
        self.assertEqual(project.references.versions()['total'],1);first=project.references.versions()['items'][0]
        linked=next(x for x in project.references.members(first['version_id'])['items'] if x['paper_id']==pid)
        self.assertEqual(project.references.assignment(first['version_id'],linked['assignment_id'])['assignment']['source_event']['event_id'],source_event)
        self.layout();self.snapshot('reference-frozen')
        self.page.locator('#reference-rationale').fill('Explicit correction after reconsideration.')
        row=self.page.locator('#reference-members article').filter(has=self.page.get_by_role('heading',name='Publication without a PMCID',exact=True))
        row.locator('select').select_option('metadata');row.get_by_role('button',name='Stage Corrected Label in Successor',exact=True).click()
        self.reference_commit();second=project.references.versions()['items'][0]
        self.assertEqual(second['version'],2);self.assertEqual(first['counts']['in_scope'],1);self.assertEqual(second['counts']['out_of_scope'],2)
        self.layout();self.snapshot('reference-successor')
        self.page.locator('#reference-versions article').filter(has=self.page.get_by_role('heading',name='Synthetic scope examples · Version 1',exact=True)).get_by_role('button').click()
        expect(self.page.locator('#reference-detail-heading')).to_have_text('Synthetic scope examples · Version 1')
        self.assertEqual(project.references.inspect(first['version_id']),first)
        self.page.locator('#reference-provenance summary').click();expect(self.page.locator('#reference-changes pre')).to_have_count(2)
        self.layout();self.snapshot('reference-history')
        self.reload();expect(self.page.locator('#reference-detail-heading')).to_have_text('Synthetic scope examples · Version 1')
        self.restart();self.open_project();self.visit('/references#'+second['version_id'].split(':')[1])
        expect(self.page.locator('#reference-detail-heading')).to_have_text('Synthetic scope examples · Version 2')
        self.assertEqual(initial,{p:project.reviews.history(p) for p in self.fixture.papers});self.assertEqual(self.fixture.transport.calls,[])
        self.assertEqual(project.reviews.membership(pid)['state'],'included')

    def exercise_classification_boundary(self, project, version, context, held):
        """Actual CP8 services; no result API mocks or new assisted-review UI."""
        import uuid
        from corpustrail.classification import ClassificationService, EngineRegistry, ValidationProtocol
        from corpustrail.curation.guided import GuidedReviewService
        from tools.classification_acceptance import StreamingFixture
        target = context['input']['target']['paper_id']
        fields = {'request_id': uuid.uuid4().hex, 'name': 'Synthetic classifier target', 'actor': 'fixture',
                  'sources': [{'kind': 'selection', 'paper_ids': [target]}]}
        preview = project.populations.preview(**fields)
        population = project.populations.create(**fields, expected_preview_sha256=preview['preview_sha256'], created_at=AT)
        session = GuidedReviewService(project).create(command_id=uuid.uuid4().hex, reviewer_id='fixture_reviewer',
            selection=population['version_id'], population_sha256=population['members_sha256'],
            config_event_id=project.configuration_history()[-1]['event_id'], mode='method-blind')
        handle = session['session_id'].split(':')[1]
        token = self.page.locator('meta[name="corpustrail-session"]').get_attribute('content')
        headers = {'X-CorpusTrail-Session': token}
        url = self.fixture.origin + '/api/v1/review/sessions/' + handle
        before = self.context.request.get(url, headers=headers).json()
        registry = EngineRegistry(); engines = [StreamingFixture('synthetic.browser-a'), StreamingFixture('synthetic.browser-b')]
        for engine in engines: registry.register(engine)
        service = ClassificationService(project, registry=registry); runs = []
        for mode, engine in zip(('full_set', 'bounded_context'), engines):
            command = {'request_id': uuid.uuid4().hex, 'name': 'Offline browser contract fixture', 'actor': 'fixture',
                'created_at': AT, 'config_event_id': project.configuration_history()[-1]['event_id'],
                'population_version_id': population['version_id'], 'reference_version_id': version['version_id'],
                'engine_id': engine.identity, 'engine_version': 'fixture/v1', 'input_mode': mode,
                'evidence_basis': 'frozen_context' if mode == 'bounded_context' else 'metadata',
                'context_ids': (context['context_id'],) if mode == 'bounded_context' else (),
                'validation': ValidationProtocol(held_out_population_version=held['version_id'])}
            preview = service.prepare(**command)
            plan = service.commit_plan(**command, expected_preview_sha256=preview['preview_sha256'])
            rid = service.start_run(plan['plan_id'], request_id=uuid.uuid4().hex, actor='fixture', created_at=AT)['run_id']
            self.assertEqual(service.execute(rid, expected_revision=service.inspect_run(rid)['revision'], clock=lambda: AT)['status'], 'completed')
            self.assertTrue(service.verify_run(rid)['verified']); runs.append(rid)
        self.assertEqual(before, self.context.request.get(url, headers=headers).json())
        for forbidden in ('assessment-run:', 'synthetic.browser', 'reference-assignment:'):
            self.assertNotIn(forbidden, json.dumps(before))
        self.restart(); self.open_project(); self.visit('/review#' + handle)
        expect(self.page.locator('#review-workspace')).to_be_visible()
        for rid in runs: self.assertTrue(self.fixture.project.classification.verify_run(rid)['verified'])
        self.assertEqual(project.reviews.membership(target)['state'], 'not_reviewed')
        self.assertEqual(self.fixture.transport.calls, [])

    def test_reference_context_conflicts_and_exact_passage_persistence(self):
        from .fixtures import XML
        from corpustrail.references import ContextStrategy
        import uuid
        project=self.fixture.project;self.fixture.freeze_reference_clock()
        project.evidence.preserve_document(self.fixture.papers[0],XML,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://reference-verified-text',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='v1',created_at=AT)
        initial={p:project.reviews.history(p) for p in self.fixture.papers}
        population_fields={'request_id':uuid.uuid4().hex,'name':'Held-out invented boundary','actor':'fixture',
            'sources':[{'kind':'selection','paper_ids':[self.fixture.papers[2]]}],'parent':None}
        preview=project.populations.preview(**population_fields)
        held=project.populations.create(**population_fields,expected_preview_sha256=preview['preview_sha256'],created_at=AT)
        self.open_project();self.visit('/references');self.page.locator('#reference-name').fill('Positive and negative context examples')
        self.page.locator('#reference-actor').fill('fixture_reviewer');self.page.locator('#reference-rationale').fill('Invented context boundary, not corpus membership.')
        self.reference_label('Evidence reference',extent='structured_text');self.reference_label('without a PMCID','out_of_scope')
        self.reference_label('Long scientific');self.reference_label('Pending document');self.reference_label('Pending document','out_of_scope')
        self.reference_commit();version=project.references.versions()['items'][0]
        self.assertEqual(version['counts']['conflicts'],1);expect(self.page.locator('#reference-members')).to_contain_text('Conflicting labels — ineligible')
        self.layout();self.snapshot('reference-conflict')
        self.page.locator('#context-builder summary').click();self.page.locator('#context-actor').fill('fixture_reviewer')
        self.page.locator('#context-target-search').fill('Metadata-only');self.page.locator('#context-find').click()
        expect(self.page.locator('#context-choices article')).to_have_count(1)
        self.page.get_by_role('button',name='Select Target',exact=True).click();self.page.locator('#context-basis').select_option('metadata')
        self.page.locator('#context-held-out').select_option(held['version_id'])
        before=fingerprint(self.fixture.root);self.page.get_by_role('button',name='Preview Selected Context',exact=True).click()
        expect(self.page.locator('#context-preview-status')).to_contain_text('2 selected references')
        self.assertEqual(before,fingerprint(self.fixture.root));self.layout();self.snapshot('reference-context-preview')
        self.page.get_by_role('button',name='Freeze Selected Context',exact=True).evaluate('b=>{b.click();b.click();}')
        expect(self.page.locator('#reference-message')).to_contain_text('Exact selected context frozen')
        expect(self.page.locator('#context-input')).to_contain_text('Invented structured scientific fixture text.')
        saved=project.references.contexts()['items'][0];context=project.references.context(saved['context_id'],verify=True)
        self.assertEqual(context['selected_count'],2);self.assertEqual(context['omission_counts'],{'conflicting_labels':2,'held_out':1})
        self.assertNotIn(self.fixture.papers[2],{r['paper_id'] for r in context['input']['references']})
        self.assertEqual(context['strategy']['strategy_id'],ContextStrategy().strategy_id)
        self.layout();self.snapshot('reference-context')
        self.reload();expect(self.page.locator('#context-input')).to_contain_text('Invented structured scientific fixture text.')
        self.restart();self.open_project();self.visit('/references#context-'+saved['context_id'].split(':')[1])
        expect(self.page.locator('#context-input')).to_contain_text('Invented structured scientific fixture text.')
        self.page.get_by_role('button',name='Verify Stored Context Integrity',exact=True).click()
        expect(self.page.locator('#context-status')).to_contain_text('Integrity verified');self.layout();self.snapshot('reference-context-restarted')
        self.assertEqual(initial,{p:project.reviews.history(p) for p in self.fixture.papers});self.assertEqual(self.fixture.transport.calls,[])
        self.exercise_classification_boundary(project, version, context, held)

    def test_reference_large_pages_do_not_accumulate_in_browser(self):
        import uuid
        from corpustrail._internal.pipeline import preserve
        from corpustrail.identity import BibliographicRecord,Identifier,SourceReference
        from tools.reference_acceptance import assignment
        project=self.fixture.project;self.fixture.freeze_reference_clock();ids=[]
        for number in range(30):
            raw=('invented-reference-page-'+str(number)).encode();sha=preserve(project,raw,'application/json',AT)
            record=BibliographicRecord('Synthetic paginated reference '+str(number),identifiers=(Identifier('doi','10.1234/reference.page.'+str(number)),))
            source=SourceReference('fixture://reference-pages',str(number),sha,len(raw),'synthetic-fixture',AT,identity_status='verified')
            ids.append(project.identities.apply(project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True))
        first=None
        for number in range(22):
            fields={'request_id':uuid.uuid4().hex,'name':'Paginated references' if number==0 else 'Other reference family '+str(number),
                'actor':'synthetic-curator','parent':None,'config_event_id':project.configuration_history()[-1]['event_id'],'created_at':AT,
                'changes':[assignment(pid) for pid in (ids if number==0 else ids[:1])]}
            preview=project.references.preview(**fields);saved=project.references.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
            if first is None:first=saved
        self.open_project();self.visit('/references');before=fingerprint(self.fixture.root)
        expect(self.page.locator('#reference-versions article')).to_have_count(20)
        self.page.get_by_role('button',name='More Reference Versions',exact=True).click()
        expect(self.page.locator('#reference-versions article')).to_have_count(2)
        self.page.locator('#reference-versions article').filter(has=self.page.get_by_role('heading',name='Paginated references · Version 1',exact=True)).get_by_role('button').click()
        expect(self.page.locator('#reference-members article')).to_have_count(20)
        self.page.get_by_role('button',name='More Reference Assignments',exact=True).click()
        expect(self.page.locator('#reference-members article')).to_have_count(10)
        self.layout();self.snapshot('reference-pagination')
        self.page.get_by_role('button',name='Previous Reference Assignments',exact=True).click()
        expect(self.page.locator('#reference-members article')).to_have_count(20)
        self.page.locator('#reference-provenance summary').click()
        expect(self.page.locator('#reference-changes pre')).to_have_count(20)
        self.page.get_by_role('button',name='More Correction History',exact=True).click()
        expect(self.page.locator('#reference-changes pre')).to_have_count(10)
        self.page.get_by_role('button',name='Previous Reference Versions',exact=True).click()
        expect(self.page.locator('#reference-versions article')).to_have_count(20)
        self.assertEqual(project.references.verify(first['version_id'])['counts']['paper_count'],30)
        self.assertEqual(before,fingerprint(self.fixture.root));self.assertEqual(self.fixture.transport.calls,[])

    def test_reference_stale_batch_and_explicit_legacy_upgrade(self):
        from unittest.mock import patch
        import uuid
        from corpustrail._internal.database import migrations
        from corpustrail.project import Project,ProjectConfig,ReviewPolicy
        project=self.fixture.project;self.fixture.freeze_reference_clock();self.open_project();self.visit('/references')
        self.page.locator('#reference-name').fill('Concurrent correction fixture');self.page.locator('#reference-actor').fill('fixture_reviewer')
        self.reference_label('Metadata-only');self.reference_commit();version=project.references.versions()['items'][0]
        self.page.locator('#reference-successor').click();self.reference_label('without a PMCID')
        self.page.locator('#reference-attest').check();self.page.get_by_role('button',name='Preview Reference Batch',exact=True).click()
        expect(self.page.locator('#reference-preview')).to_be_visible()
        from . import fixtures
        from corpustrail.references.contracts import POLICY
        self.assertEqual(version['policy'],POLICY)
        fields={'request_id':uuid.uuid4().hex,'name':version['name'],'actor':'another-fixture-actor','parent':version['version_id'],
            'changes':[{'action':'remove','assignment_id':project.references.members(version['version_id'])['items'][0]['assignment_id'],'reason':'Controlled concurrent correction'}],
            'config_event_id':project.configuration_history()[-1]['event_id'],'created_at':fixtures.AT}
        preview=project.references.preview(**fields);project.references.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
        self.expected_http_errors.add(409);self.expected_console_errors.append('Failed to load resource: the server responded with a status of 409 (Conflict)')
        self.page.get_by_role('button',name='Commit Reference Version',exact=True).click()
        expect(self.page.locator('#reference-message')).to_contain_text('latest version')
        expect(self.page.locator('#reference-staged')).to_contain_text('Publication without a PMCID');self.assertEqual(project.references.versions()['total'],2)
        self.layout();self.snapshot('reference-stale')
        # Discard only unsaved synthetic UI proposals before navigating. No
        # scientific save is implied by leaving the page.
        self.page.get_by_role('button',name='Unstage',exact=True).click()
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:38]):
            legacy=Project.create(self.fixture.root/'legacy-reference',ProjectConfig('legacy-reference','Legacy reference fixture','Synthetic older project',review=ReviewPolicy(scope=SCOPE)),created_by='fixture',created_at=AT)
        self.visit('/projects');self.page.locator('#project-list article').filter(has=self.page.get_by_role('heading',name='Legacy reference fixture',exact=True)).get_by_role('button',name='Open Project').click()
        expect(self.page.locator('#project-name')).to_have_text('Legacy reference fixture');self.visit('/references')
        expect(self.page.locator('#reference-upgrade')).to_be_visible();self.assertFalse(legacy.references.ready())
        self.layout();self.snapshot('reference-upgrade');self.page.get_by_role('button',name='Back Up and Enable References',exact=True).click()
        expect(self.page.locator('#reference-message')).to_contain_text('Reference storage enabled')
        self.assertTrue(legacy.references.ready());self.assertEqual(len(list((legacy.root/legacy.config.data_directory/'reference-upgrades').glob('*.sqlite3'))),1)
        self.layout();self.snapshot('reference-upgraded');self.assertEqual(self.fixture.transport.calls,[])

    def test_population_freeze_combine_review_and_restart(self):
        import hashlib
        import uuid
        from corpustrail._internal.pipeline import preserve
        from corpustrail.identity import BibliographicRecord,Identifier,SourceReference
        from corpustrail.populations import ImportedSource
        from corpustrail.providers import metadata_provider
        project=self.fixture.project
        initial_reviews={p:project.reviews.history(p) for p in self.fixture.papers}
        self.open_project()
        before=fingerprint(self.fixture.root)
        self.page.get_by_role('link',name='Candidate Populations',exact=True).click()
        expect(self.page.locator('#population-list-status')).to_contain_text('No saved population versions')
        self.assertEqual(before,fingerprint(self.fixture.root));self.assertEqual(self.fixture.transport.calls,[])
        self.assertEqual(self.page.locator('input[type=file]').count(),0)
        self.layout();self.snapshot('population-empty')
        self.page.get_by_label('Population name',exact=True).fill('Initial collected candidates')
        self.page.get_by_label('Created by',exact=True).fill('fixture_reviewer')
        self.page.locator('#population-all').check()
        before=fingerprint(self.fixture.root)
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        expect(self.page.locator('#population-preview-counts')).to_contain_text('5')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.layout();self.snapshot('population-preview')
        self.page.get_by_role('button',name='Freeze Population',exact=True).evaluate('b=>{b.click();b.click();}')
        expect(self.page.locator('#population-message')).to_contain_text('Candidate population frozen')
        expect(self.page.locator('#population-detail-counts')).to_contain_text('5')
        self.assertEqual(project.populations.versions()['total'],1)
        first=project.populations.versions()['items'][0]
        self.layout();self.snapshot('population-frozen')
        # Controlled future-adapter contract: real enrollment + preserved source,
        # no production format parser or HTTP import endpoint.
        body=b'{"synthetic_export":["known publication","new publication"]}'
        sha=preserve(project,body,'application/json','2026-01-01T00:00:00+00:00')
        observations=[]
        for i,doi in enumerate(('10.1234/evidence.1','10.1234/population-import.6')):
            record=BibliographicRecord('Synthetic adapter candidate '+str(i),identifiers=(Identifier('doi',doi),))
            source=SourceReference('fixture://population-adapter',str(i),sha,len(body),'synthetic-adapter',
                '2026-01-01T00:00:00+00:00',identity_status='verified')
            plan=project.identities.plan(record,source)
            pid=project.identities.apply(plan,approve_new_identity=True,approve_aliases=True)
            observations.extend(x['observation_id'] for x in project.identities.observations(pid) if x['source']['source_uri']=='fixture://population-adapter')
        imported=project.populations.freeze_import_source(ImportedSource('synthetic-source-v1','synthetic-adapter','v1',sha,tuple(observations)),
            request_id=uuid.uuid4().hex,name='Synthetic source interface',actor='fixture')
        provider=metadata_provider('openalex')
        plan=project.discovery.plan(provider,run_id='population-discovery',query='synthetic porous materials',max_pages=1,max_attempts=1)
        project.discovery.execute(plan,provider,transport=self.fixture.transport,confirm_external=True)
        project.discovery.canonicalize(plan.run_id,approve_new_identities=True,approve_aliases=True)
        calls=len(self.fixture.transport.calls)
        self.assertEqual(len(project.identities.papers()),7)
        self.reload()
        self.page.get_by_label('Population name',exact=True).fill('Combined origin candidates')
        self.page.get_by_label('Created by',exact=True).fill('fixture_reviewer')
        for name in ('Initial collected candidates','Synthetic source interface'):
            self.page.get_by_role('checkbox',name='Use '+name+' · Version 1 in a combination',exact=True).check()
        self.page.locator('#population-form details').filter(has=self.page.get_by_text('Completed discovery sources',exact=True)).locator('summary').click()
        self.page.get_by_role('checkbox',name=re.compile('openalex · synthetic porous materials')).check()
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        expect(self.page.locator('#population-preview')).to_be_visible()
        self.page.get_by_role('button',name='Freeze Population',exact=True).click()
        expect(self.page.locator('#population-detail-heading')).to_have_text('Combined origin candidates · Version 1')
        combined=project.populations.versions()['items'][0]
        self.assertEqual(combined['member_count'],7);self.assertEqual(combined['unresolved_count'],0)
        expect(self.page.locator('#population-detail-sources')).to_contain_text('Initial collected candidates')
        expect(self.page.locator('#population-detail-sources')).to_contain_text('Synthetic source interface')
        expect(self.page.locator('#population-detail-sources')).to_contain_text('openalex')
        self.page.get_by_role('button',name='Verify Stored Integrity',exact=True).click()
        expect(self.page.locator('#population-verify-result')).to_contain_text('integrity verified')
        self.layout();self.snapshot('population-combined')
        self.page.locator('#population-provenance summary').click()
        expect(self.page.locator('#population-lineage')).to_contain_text('fixture')
        self.snapshot('population-lineage',subject='#population-detail');self.layout()
        self.assertEqual({p:project.reviews.history(p) for p in self.fixture.papers},initial_reviews)
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in project.identities.papers()))
        self.page.get_by_role('link',name='Review This Frozen Version',exact=True).click()
        expect(self.page.locator('#review-population')).to_have_value(combined['version_id'])
        expect(self.page.locator('#reviewer')).to_have_value('')
        self.snapshot('population-review-selection');self.layout()
        self.page.locator('#reviewer').fill('fixture_reviewer')
        self.page.get_by_role('button',name='Start Guided Review',exact=True).click()
        expect(self.page.locator('#review-progress')).to_contain_text('of 7')
        expect(self.page.locator('#review-population-version')).to_contain_text('Version 1')
        self.snapshot('population-review');self.layout()
        review_handle=self.page.url.split('#')[1]
        # An addition and explicit successor cannot expand the earlier session.
        raw=b'new candidate after the frozen review'
        record=BibliographicRecord('Later candidate outside frozen population',identifiers=(Identifier('doi','10.1234/population-later.8'),))
        source=SourceReference('fixture://later-population','later','sha256:'+hashlib.sha256(raw).hexdigest(),len(raw),'fixture',
            '2026-01-01T00:00:00+00:00',identity_status='verified')
        project.identities.apply(project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
        self.visit('/populations')
        card=self.page.locator('#population-versions article').filter(has=self.page.get_by_role('heading',name='Combined origin candidates · Version 1 · Frozen',exact=True))
        card.get_by_role('button',name='Create Successor Version',exact=True).click()
        self.page.get_by_label('Created by',exact=True).fill('fixture_reviewer');self.page.locator('#population-all').check()
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        self.page.get_by_role('button',name='Freeze Population',exact=True).click()
        expect(self.page.locator('#population-detail-heading')).to_have_text('Combined origin candidates · Version 2')
        self.assertEqual(project.populations.versions()['items'][0]['member_count'],8)
        self.snapshot('population-successor');self.layout()
        self.assertEqual(project.populations.inspect(first['version_id'])['member_count'],5)
        self.assertEqual(project.populations.inspect(combined['version_id'])['member_count'],7)
        self.snapshot('population-history');self.layout()
        before=fingerprint(self.fixture.root);self.restart();self.open_project()
        self.visit('/review#'+review_handle)
        expect(self.page.locator('#review-progress')).to_contain_text('of 7')
        expect(self.page.locator('#review-population-version')).to_contain_text('Version 1')
        self.visit('/populations#'+combined['version_id'].split(':')[1])
        expect(self.page.locator('#population-detail-heading')).to_have_text('Combined origin candidates · Version 1')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(calls,len(self.fixture.transport.calls))
        self.assertTrue(project.populations.verify(combined['version_id'])['verified'])
        self.visit('/review#'+review_handle)
        self.page.get_by_role('button',name='Finish Review',exact=True).click()
        expect(self.page).to_have_url(re.compile('/dashboard#review-completed-'))
        self.visit('/review#'+review_handle)
        expect(self.page.locator('#review-completion-heading')).to_contain_text('Review completed')
        self.snapshot('population-review-completed');self.layout()
        self.assertEqual({pid:project.reviews.history(pid) for pid in self.fixture.papers},initial_reviews)
        self.assertTrue(all(project.reviews.membership(pid)['state']=='not_reviewed' for pid in project.identities.papers()))
        self.assertEqual(imported['member_count'],2)

    def test_population_selection_stale_preview_and_legacy_upgrade(self):
        from unittest.mock import patch
        from corpustrail._internal.database import migrations
        from corpustrail.project import Project,ProjectConfig,ReviewPolicy
        self.open_project();self.visit('/populations')
        self.page.locator('#population-name').fill('Explicit selected candidate')
        self.page.locator('#population-actor').fill('fixture')
        self.page.get_by_text('Select individual publications',exact=True).click()
        self.page.locator('#population-search').fill('without a PMCID')
        self.page.get_by_role('button',name='Find Publications',exact=True).click()
        self.page.get_by_role('checkbox',name='Publication without a PMCID',exact=True).check()
        # Delay the REAL controller response, not its scientific result. Editing
        # during a pending preview must not let its late response reappear.
        from corpustrail.application.populations import PopulationController
        entered,released=threading.Event(),threading.Event()
        original=PopulationController.command
        def delayed(controller,project,action,body):
            value=original(controller,project,action,body)
            if action=='preview':
                entered.set()
                if not released.wait(10):raise AssertionError('Preview gate timed out')
            return value
        try:
            with patch.object(PopulationController,'command',new=delayed):
                self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
                self.assertTrue(entered.wait(5))
                self.page.locator('#population-name').fill('Edited selection invalidates preview')
                with self.page.expect_response(lambda response:response.url.endswith('/api/v1/populations/preview')):released.set()
        finally:released.set()
        expect(self.page.locator('#population-preview')).to_be_hidden()
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        expect(self.page.locator('#population-preview')).to_be_visible()
        expect(self.page.get_by_role('button',name='Freeze Population',exact=True)).to_be_enabled()
        # Real configuration revision invalidates a stale prepared population.
        from dataclasses import replace
        project=self.fixture.project
        project.configure(replace(project.config,config_version=2,name='Renamed fixture'),
            expected_event_id=project.configuration_history()[-1]['event_id'],created_by='fixture')
        self.expected_http_errors.add(409)
        self.expected_console_errors.append('Failed to load resource: the server responded with a status of 409 (Conflict)')
        self.page.get_by_role('button',name='Freeze Population',exact=True).click()
        expect(self.page.locator('#population-message')).to_contain_text('preview again')
        self.assertEqual(project.populations.versions()['total'],0)
        self.snapshot('population-conflict');self.layout()
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:37]):
            legacy=Project.create(self.fixture.root/'legacy-population',ProjectConfig('legacy-population','Legacy population fixture',
                'Synthetic older project',review=ReviewPolicy(scope=SCOPE)),created_by='fixture')
        self.visit('/projects')
        self.page.locator('#project-list article').filter(has=self.page.get_by_role('heading',name='Legacy population fixture',exact=True)).get_by_role('button',name='Open Project').click()
        expect(self.page.locator('#project-name')).to_have_text('Legacy population fixture')
        self.visit('/populations');expect(self.page.locator('#population-upgrade')).to_be_visible()
        self.assertFalse(legacy.populations.ready());self.snapshot('population-upgrade');self.layout()
        self.page.get_by_role('button',name='Back Up and Enable Populations',exact=True).click()
        expect(self.page.locator('#population-message')).to_contain_text('Population storage enabled')
        self.assertTrue(legacy.populations.ready());self.assertEqual(len(list((legacy.root/legacy.config.data_directory/'population-upgrades').glob('*.sqlite3'))),1)
        self.snapshot('population-upgraded');self.layout()
        self.assertEqual(self.fixture.transport.calls,[])

    def test_review_guided_save_finish_publish_and_resume(self):
        from dataclasses import replace
        from .fixtures import XML
        project=self.fixture.project
        project.configure(replace(project.config,config_version=project.config.config_version+1,
            review=replace(project.config.review,authorized_reviewers=('fixture_reviewer',))),
            expected_event_id=project.configuration_history()[-1]['event_id'],created_by='fixture')
        project.evidence.preserve_document(self.fixture.papers[0],XML,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://verified-review-evidence',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='v1')
        initial={p:project.reviews.history(p) for p in self.fixture.papers}
        self.open_project();self.start_guided_review()
        self.assertEqual(len(project.identities.observations(self.fixture.papers[0])),2)
        self.assertEqual(sum(len(project.identities.observations(p)) for p in self.fixture.papers),6)
        self.snapshot('review-active');self.layout()
        outcomes=['included','excluded','insufficient_evidence','included','excluded']
        captured_missing=False
        for i,outcome in enumerate(outcomes):
            expect(self.page.locator('#review-progress')).to_contain_text('Paper '+str(i+1)+' of 5')
            title=self.page.locator('#review-paper-title').inner_text()
            if title==TITLE:
                expect(self.page.locator('#review-abstract')).to_have_text(ABSTRACT)
                self.page.get_by_role('button',name='Read verified structured text',exact=True).click()
                expect(self.page.locator('#review-document')).to_contain_text('Invented structured scientific fixture text')
                expect(self.page.locator('#review-extent')).to_have_value('')
                expect(self.page.locator('#review-extent option[value=""]')).to_be_disabled()
                expect(self.page.locator('#review-extent option[value="full_document"]')).to_have_text('Verified structured text — full document')
                self.assertFalse(project.reviews.history(self.fixture.papers[0]))
                self.snapshot('review-verified-text')
            elif 'Long scientific title' in title:self.snapshot('review-long-title')
            elif self.page.locator('#review-abstract').inner_text()=='Invented second abstract-best source.':
                expect(self.page.locator('#review-evidence-status')).not_to_contain_text('No abstract available')
            else:
                expect(self.page.locator('#review-evidence-status')).to_contain_text('No abstract available')
                expect(self.page.locator('#review-extent option[value="full_document"]')).to_have_count(0)
                expect(self.page.locator('#review-extent option[value="sections"]')).to_have_count(0)
                if not captured_missing:
                    self.snapshot('review-missing-evidence');captured_missing=True
            self.page.locator('input[name="assessment"][value="'+outcome+'"]').check()
            self.page.locator('#review-extent').select_option('full_document' if title==TITLE else 'abstract' if self.page.locator('#review-abstract').inner_text()=='Invented second abstract-best source.' else 'metadata')
            self.page.locator('#review-rationale').fill('Invented human assessment '+str(i+1))
            expect(self.page.locator('#review-save-state')).to_contain_text('Draft saved')
            if i==0:
                self.snapshot('review-assessment')
                # A transport interruption, not a mocked scientific/API success.
                self.expected_transport_failure=True
                self.page.route('**/api/v1/review/command',lambda route: route.abort('failed'))
                self.page.locator('#review-save-next').click()
                expect(self.page.locator('#review-message')).to_contain_text('current input is retained')
                expect(self.page.locator('#review-progress')).to_contain_text('Paper 1 of 5')
                expect(self.page.locator('#review-rationale')).to_have_value('Invented human assessment 1')
                self.assertEqual({p:project.reviews.history(p) for p in self.fixture.papers},initial)
                self.page.unroute('**/api/v1/review/command');self.expected_transport_failure=False
            self.page.locator('#review-save-next').evaluate('button=>{button.click();button.click();}')
            expect(self.page.locator('#review-message')).to_contain_text('Human observation saved')
            expect(self.page.locator('#review-recover')).to_be_hidden()
            expect(self.page.locator('#review-progress')).to_contain_text(str(i+1)+' with saved observations')
        self.assertEqual(sum(len(project.reviews.history(p))-len(initial[p]) for p in self.fixture.papers),5)
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        handle=self.page.url.split('#')[1]
        self.reload()
        expect(self.page.locator('#review-progress')).to_contain_text('5 with saved observations')
        before=fingerprint(self.fixture.root);self.restart();self.open_project();self.visit('/review')
        self.page.get_by_role('button',name='Open review session',exact=True).click()
        expect(self.page.locator('#review-progress')).to_contain_text('5 with saved observations')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.page.locator('#review-show-summary').click()
        expect(self.page.locator('#review-summary')).to_be_visible();self.snapshot('review-summary')
        self.page.get_by_role('button',name='Finish Review',exact=True).evaluate('button=>{button.click();button.click();}')
        expect(self.page).to_have_url(self.fixture.origin+'/dashboard#review-completed-'+handle)
        expect(self.page.locator('#dashboard-review-result')).to_contain_text('Finishing did not change corpus membership')
        self.snapshot('review-finished-dashboard');self.layout()
        self.page.locator('#dashboard-review-summary').click()
        expect(self.page.locator('#review-completion-heading')).to_have_text('Review completed — read only')
        expect(self.page.locator('#assessment-form')).to_be_hidden()
        expect(self.page.locator('#review-finish')).to_be_hidden()
        expect(self.page.locator('#review-summary-papers')).to_contain_text('Invented human assessment 1')
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        self.snapshot('review-completed',subject='main')
        observations={p:project.reviews.history(p) for p in self.fixture.papers}
        self.page.get_by_role('button',name='Preview corpus updates',exact=True).click()
        expect(self.page.locator('#review-publication')).to_be_visible()
        expect(self.page.locator('#review-prepare-publication')).to_be_hidden()
        expect(self.page.locator('#review-summary-counts')).to_contain_text('Proposed included publications')
        self.assertEqual(observations,{p:project.reviews.history(p) for p in self.fixture.papers})
        self.snapshot('review-publication',subject='main');self.layout()
        self.page.get_by_role('button',name='Back to Review Summary',exact=True).click()
        expect(self.page.locator('#review-publication')).to_be_hidden()
        expect(self.page.locator('#review-prepare-publication')).to_be_visible()
        self.reload()
        expect(self.page.locator('#review-publication')).to_be_hidden()
        expect(self.page.locator('#assessment-form')).to_be_hidden()
        self.page.get_by_role('button',name='Preview corpus updates',exact=True).click()
        self.page.get_by_role('button',name='Confirm corpus updates',exact=True).click()
        expect(self.page.locator('#review-message')).to_contain_text('confirmed decisions updated')
        self.snapshot('review-confirmed',subject='main')
        states=[project.reviews.membership(p)['state'] for p in self.fixture.papers]
        self.assertEqual(states.count('included'),2);self.assertEqual(states.count('excluded'),2)
        self.assertEqual(states.count('insufficient_evidence'),1)
        self.assertEqual(self.fixture.transport.calls,[])
        self.visit('/dashboard');expect(self.page.locator('#summaries')).to_contain_text('In corpus: 2')
        self.assertTrue(handle)
        self.tools_page('/export');self.page.locator('#tools-actor').fill('fixture_reviewer')
        self.page.get_by_role('button',name='Preview bibliography export',exact=True).click()
        expect(self.page.locator('#operation-summary')).to_contain_text('included: 2')
        self.assertEqual(self.fixture.handoff.list(project,'exports')['total'],0)
        self.layout();self.snapshot('handoff-export-preview')
        self.confirm_tools('Create Frozen Export')
        with self.page.expect_download() as saved:
            self.page.locator('#operation-actions').get_by_role('button',name='Download Bibliography CSV',exact=True).click()
        import csv
        from pathlib import Path
        body=Path(saved.value.path()).read_text(encoding='utf-8')
        import io
        records=list(csv.DictReader(io.StringIO(body)))
        self.assertEqual(len(records),2);self.assertNotIn('asreview_label',records[0])
        self.assertEqual({r['corpustrail_paper_id'] for r in records},{p for p in self.fixture.papers if project.reviews.membership(p)['state']=='included'})
        self.tools_page('/export');self.layout();self.snapshot('handoff-export')
        self.page.get_by_role('button',name='Use this export for returned results',exact=True).click()
        for selector,text in (('#mapping-actor','fixture_reviewer'),('#mapping-question','Invented downstream review question'),('#mapping-review','Synthetic ASReview results')):
            self.page.locator(selector).fill(text)
        returned='corpustrail_paper_id,asreview_label\n'+'\n'.join(r['corpustrail_paper_id']+',0' for r in reversed(records))+'\n'
        self.page.locator('#mapping-file').set_input_files({'name':'synthetic-returned.csv','mimeType':'text/csv','buffer':returned.encode()})
        self.page.get_by_role('button',name='Preview question-specific mapping',exact=True).click()
        expect(self.page.locator('#operation-summary')).to_contain_text('will not change broad-corpus membership')
        self.layout();self.snapshot('handoff-mapping');self.confirm_tools('Map Question-specific Results')
        self.assertEqual(states,[project.reviews.membership(p)['state'] for p in self.fixture.papers])

    def test_review_skip_frozen_population_and_draft_resume(self):
        from corpustrail.identity import BibliographicRecord,Identifier,SourceReference
        import hashlib
        project=self.fixture.project
        before={p:project.reviews.history(p) for p in self.fixture.papers}
        self.open_project();self.start_guided_review(selection_snapshot='review-session-selection-skip')
        # A newly collected canonical publication must not enter this snapshot.
        raw=b'new canonical fixture outside frozen review'
        source=SourceReference('fixture://later-collection','later','sha256:'+hashlib.sha256(raw).hexdigest(),
            len(raw),'fixture_discovery','2026-01-01T00:00:00+00:00',identity_status='verified')
        project.identities.apply(project.identities.plan(BibliographicRecord('Later collected publication',
            identifiers=(Identifier('doi','10.1234/later.6'),)),source),approve_new_identity=True,approve_aliases=True)
        self.page.locator('#review-rationale').fill('Incomplete draft retained without a judgment')
        expect(self.page.locator('#review-save-state')).to_contain_text('Draft saved')
        self.page.get_by_role('button',name='Skip for now',exact=True).click()
        expect(self.page.locator('#review-progress')).to_contain_text('Paper 2 of 5')
        self.page.get_by_role('button',name='Previous',exact=True).click()
        expect(self.page.locator('#review-rationale')).to_have_value('Incomplete draft retained without a judgment')
        self.reload()
        expect(self.page.locator('#review-rationale')).to_have_value('Incomplete draft retained without a judgment')
        expect(self.page.locator('#review-progress')).to_contain_text('0 with saved observations')
        self.assertEqual(before,{p:project.reviews.history(p) for p in self.fixture.papers})
        # Failure must leave the draft/session in place, never redirect early.
        self.expected_transport_failure=True
        self.page.route('**/api/v1/review/command',lambda route:route.abort('failed'))
        self.page.locator('#review-finish').click()
        expect(self.page.locator('#review-message')).to_contain_text('current input is retained')
        expect(self.page.locator('#review-rationale')).to_have_value('Incomplete draft retained without a judgment')
        self.assertIn('/review#',self.page.url)
        self.page.unroute('**/api/v1/review/command');self.expected_transport_failure=False
        self.page.locator('#review-finish').click()
        expect(self.page.locator('#dashboard-review-result')).to_contain_text('Unassessed papers remain undecided')
        self.page.locator('#dashboard-review-summary').click()
        expect(self.page.locator('#review-summary-counts')).to_contain_text('5')
        expect(self.page.locator('#review-summary-counts')).to_contain_text('Incomplete drafts')
        self.assertEqual(before,{p:project.reviews.history(p) for p in self.fixture.papers})
        self.assertEqual(self.fixture.transport.calls,[]);self.layout()

    def test_review_unauthorized_and_empty_project(self):
        self.open_project();self.start_guided_review(reviewer='configuration_author',
            selection_snapshot='review-session-selection-unauthorized')
        self.page.locator('input[name="assessment"][value="included"]').check()
        self.page.locator('#review-extent').select_option('metadata')
        self.page.locator('#review-rationale').fill('Invented non-authoritative observation')
        self.page.locator('#review-save-next').click()
        expect(self.page.locator('#review-message')).to_contain_text('Human observation saved')
        self.page.locator('#review-show-summary').click()
        self.click_after_reads('#review-finish')
        expect(self.page.locator('#dashboard-review-result')).to_contain_text('Finishing did not change corpus membership')
        self.page.locator('#dashboard-review-summary').click()
        expect(self.page.locator('#review-authority-status')).to_contain_text('not authorized')
        expect(self.page.locator('#review-prepare-publication')).to_be_hidden()
        # Capture the real content bounds, not Chromium's transient old scroll
        # extent after the taller assessment panel has collapsed. Nothing in
        # main is hidden/masked for this screenshot; page overflow is still checked.
        self.snapshot('review-unauthorized',subject='main');self.layout()
        expect(self.page.locator('#assessment-form')).to_be_hidden()
        expect(self.page.locator('#review-save-next')).to_be_hidden()
        token=self.page.locator('meta[name="corpustrail-session"]').get_attribute('content')
        handle=self.page.url.split('#')[1]
        headers={'X-CorpusTrail-Session':token,'X-CorpusTrail-CSRF':token,'Origin':self.fixture.origin}
        current=self.context.request.get(self.fixture.origin+'/api/v1/review/sessions/'+handle,headers=headers).json()
        import uuid
        refused=self.context.request.post(self.fixture.origin+'/api/v1/review/command',headers=headers,
            data={'schema':'corpustrail-guided-review/v1','handle':handle,'command_id':uuid.uuid4().hex,
                  'expected_revision':current['revision'],'action':'prepare_publication','value':None})
        self.assertEqual(refused.status,409)
        self.assertTrue(all(self.fixture.project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        self.page.get_by_role('button',name='Back to Review Overview',exact=True).click()
        expect(self.page.locator('#review-overview')).to_be_visible()
        self.snapshot('review-completed-overview');self.layout()
        self.page.get_by_role('button',name='View Review Summary',exact=True).click()
        expect(self.page.locator('#review-summary')).to_be_visible()
        self.page.get_by_role('link',name='Back to Project Dashboard',exact=True).click()
        expect(self.page.locator('#project-name')).to_have_text('Synthetic materials')
        from corpustrail.project import Project,ProjectConfig,ReviewPolicy
        empty=Project.create(self.fixture.root/'empty',ProjectConfig('empty-review','Empty review project','Invented empty fixture',review=ReviewPolicy(scope=SCOPE)),created_by='fixture')
        self.visit('/projects')
        self.page.locator('#project-list article').filter(has=self.page.get_by_role('heading',name='Empty review project',exact=True)).get_by_role('button',name='Open Project').click()
        expect(self.page).to_have_url(self.fixture.origin+'/dashboard')
        expect(self.page.locator('#project-name')).to_have_text('Empty review project')
        self.visit('/review');expect(self.page.locator('#review-empty')).to_contain_text('No publications')
        self.snapshot('review-empty');self.layout()
        self.assertEqual(empty.identities.papers(),[])
        self.assertEqual(self.fixture.transport.calls,[])

    def test_evidence_verification_mismatch_and_refresh(self):
        self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click()
        expect(self.page.locator('#abstract')).to_have_text(ABSTRACT)
        expect(self.page.locator('#abstract-source')).to_contain_text('Bibliographic/discovery metadata abstract')
        self.assertEqual(self.fixture.transport.calls,[])
        expect(self.page.locator('#evidence-eligibility')).to_contain_text('PMC123')
        self.snapshot('evidence-availability');self.layout()
        self.fixture.transport.gate=threading.Event()
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-result')).to_contain_text(re.compile('running|queued'))
        self.fixture.transport.gate.set()
        expect(self.page.locator('#evidence-history')).to_contain_text('Exact document identity verified',timeout=15000)
        expect(self.page.get_by_role('button',name='Read verified structured text')).to_be_visible()
        self.page.get_by_role('button',name='Read verified structured text').click()
        expect(self.page.locator('#document-text')).to_contain_text('Invented structured scientific fixture text')
        self.snapshot('evidence-result');self.layout()
        self.page.locator('#advanced-evidence summary').click()
        self.page.get_by_role('button',name='Show complete provenance records').click()
        expect(self.page.locator('#evidence-raw')).to_contain_text('representation')
        expect(self.page.locator('#evidence-raw')).to_contain_text('bounded-inert-jats/v2')
        expect(self.page.locator('#evidence-raw')).to_contain_text('xml_parse_input_sha256')
        self.snapshot('evidence-provenance')
        valid=self.fixture.project.evidence.representations(self.fixture.papers[0],trusted_only=True)
        self.fixture.transport.mismatch=True
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-history')).to_contain_text('Document identity mismatch — not trusted',timeout=15000)
        self.assertEqual(valid,self.fixture.project.evidence.representations(self.fixture.papers[0],trusted_only=True))
        self.snapshot('evidence-mismatch')
        self.fixture.transport.mismatch=False;self.fixture.transport.invalid=True
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-history')).to_contain_text('Invalid document — not trusted',timeout=15000)
        self.assertEqual(valid,self.fixture.project.evidence.representations(self.fixture.papers[0],trusted_only=True))
        self.layout()
        self.reload()
        expect(self.page.locator('#evidence-history')).to_contain_text('Document identity mismatch — not trusted')
        expect(self.page.locator('#evidence-operations button')).to_have_count(3)
        self.assertEqual(len(self.fixture.transport.calls),3)
        self.assertEqual(self.fixture.project.reviews.history(self.fixture.papers[0]),[])
        self.assertEqual(self.fixture.project.reviews.membership(self.fixture.papers[0])['state'],'not_reviewed')
        self.page.get_by_role('button',name='Read verified structured text').click()
        expect(self.page.locator('#document-text')).to_contain_text('Invented structured scientific fixture text')
        before_restart=fingerprint(self.fixture.root)
        self.restart()
        self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click()
        expect(self.page.locator('#evidence-operations button')).to_have_count(3)
        expect(self.page.locator('#evidence-history')).to_contain_text('Exact document identity verified')
        expect(self.page.locator('#evidence-history')).to_contain_text('Document identity mismatch — not trusted')
        expect(self.page.locator('#evidence-history')).to_contain_text('Invalid document — not trusted')
        self.page.get_by_role('button',name='Read verified structured text').click()
        expect(self.page.locator('#document-text')).to_contain_text('Invented structured scientific fixture text')
        self.assertEqual(len(self.fixture.transport.calls),3)
        self.assertEqual(before_restart,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.project.reviews.history(self.fixture.papers[0]),[])
        self.assertEqual(self.fixture.project.reviews.membership(self.fixture.papers[0])['state'],'not_reviewed')
