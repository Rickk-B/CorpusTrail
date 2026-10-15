"""Offline guided lifecycle, atomic publication, immutable packets and legacy safety."""
from dataclasses import replace
import json
import http.client
import re
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
import uuid

import test_curation_prioritization as legacy
from corpustrail._internal.database import connection
from corpustrail._internal.values import ContractError, content_hash
from corpustrail.application.review import ReviewController
from corpustrail.curation.guided import GuidedReviewService
from corpustrail.curation.sessions import _load
from corpustrail.project import Project
from corpustrail.application.projects import ProjectController
from corpustrail.application.project_use import acquire_project_use, ProjectBusy
from corpustrail.local_app import make_server


def fingerprint(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


class GuidedReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=legacy.CurationTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.project=self.fixture.project
        config=replace(self.project.config,config_version=self.project.config.config_version+1,review=replace(self.project.config.review,scope='Invented broad-topic materials collection.'))
        self.project.configure(config,expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='configuration_author')
        self.service=GuidedReviewService(self.project);self.controller=ReviewController()

    def create(self,reviewer='reviewer_one',mode='method-blind',**overrides):
        values=dict(command_id=uuid.uuid4().hex,reviewer_id=reviewer,selection='all',
            population_sha256=content_hash(self.service.population('all')),
            config_event_id=self.project.configuration_history()[-1]['event_id'],mode=mode)
        values.update(overrides); result=self.service.create(**values)
        self.session=result['session_id'];self.handle=result['session_id'].split(':')[1]
        return result,values

    def state(self):
        with connection(self.project.database_path) as db:return _load(db,self.session)

    def command(self,action,value=None,**overrides):
        values=dict(command_id=uuid.uuid4().hex,expected_revision=self.state()[2],action=action,value=value)
        values.update(overrides);return self.service.command(self.session,**values)

    def draft(self,decision='included',rationale='Invented human rationale.'):
        return {'sufficiency':'insufficient' if decision=='insufficient_evidence' else 'sufficient',
            'decision':None if decision=='insufficient_evidence' else decision,
            'review_extent':'metadata','rationale':rationale,'location':None}

    def finish(self):return self.command('finish',{'preserve_undecided':True})
    def publish(self,**overrides):
        sha=self.state()[1]['publication_plan']['sha256']
        return self.command('publish',{'plan_sha256':sha,'confirm_authority':True},**overrides)

    def test_views_empty_and_existing_history_are_read_only(self):
        before=fingerprint(self.project.root)
        view=self.controller.configuration(self.project)
        self.assertEqual(view['sessions'],[]);self.assertEqual(view['populations'][0]['count'],8)
        self.assertEqual(before,fingerprint(self.project.root))
        self.create();before=fingerprint(self.project.root)
        self.controller.view(self.project,self.handle);self.controller.summary_page(self.project,self.handle)
        self.assertEqual(before,fingerprint(self.project.root))
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.fixture.ids))

    def test_creation_is_explicit_revision_bound_and_replay_safe(self):
        result,request=self.create();before=fingerprint(self.project.root)
        self.fixture.enroll(19)
        after=fingerprint(self.project.root)
        self.assertEqual(self.service.create(**request),result)
        self.assertEqual(after,fingerprint(self.project.root))
        with self.assertRaises(ContractError):self.service.create(**{**request,'reviewer_id':'someone_else'})
        self.assertEqual(self.state()[0]['question'],'Invented broad-topic materials collection.')
        self.assertNotEqual(before,after)

    def test_invalid_population_config_identity_and_scope_do_not_write(self):
        for values in ({'population_sha256':'sha256:'+'0'*64},{'config_event_id':'stale'},{'reviewer_id':''},{'selection':'imported'}, {'mode':'unknown'}):
            before=fingerprint(self.project.root)
            with self.subTest(values=values),self.assertRaises(ContractError):self.create(**values)
            self.assertEqual(before,fingerprint(self.project.root))
        config=replace(self.project.config,config_version=self.project.config.config_version+1,review=replace(self.project.config.review,scope=None))
        self.project.configure(config,expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
        with self.assertRaises(ContractError):self.create()

    def test_frozen_population_definition_evidence_and_method_blind_allowlist(self):
        self.fixture.label(self.fixture.ids[0]);self.create()
        packet=self.state()[0];self.fixture.enroll(20);self.fixture.document(self.fixture.ids[0])
        view=self.controller.view(self.project,self.handle)
        self.assertEqual(view['total'],8);self.assertFalse(view['document_available'])
        self.assertEqual(packet,self.state()[0])
        encoded=json.dumps(view)
        for secret in ('provider-private-query','secret-arm','hidden_model_judgment','current_event_id','source_observations'):
            self.assertNotIn(secret,encoded)
        self.create(mode='operational');self.assertIn('source_provenance',self.controller.view(self.project,self.handle))

    def test_partial_draft_autosave_skip_and_restart_are_not_observations(self):
        self.create();self.command('draft',{'rationale':'Incomplete but preserved.'});self.command('skip')
        self.assertEqual(sum(len(self.project.reviews.history(p)) for p in self.fixture.ids),0)
        self.project=Project.open(self.project.root);self.service=GuidedReviewService(self.project)
        self.command('navigate','previous')
        self.assertEqual(self.controller.view(self.project,self.handle)['review']['rationale'],'Incomplete but preserved.')
        self.finish();summary=self.state()[1]['completion']['summary']
        self.assertEqual(summary['undecided'],8);self.assertEqual(summary['incomplete_drafts'],1)

    def test_save_next_records_observation_and_advances_only_atomically(self):
        self.create();before=fingerprint(self.project.root)
        with self.assertRaises(ContractError):self.command('save_next',self.draft(rationale=''))
        self.assertEqual(before,fingerprint(self.project.root));self.assertEqual(self.state()[1]['index'],0)
        self.command('save_next',self.draft());self.assertEqual(self.state()[1]['index'],1)
        history=self.project.reviews.history(self.fixture.ids[0])
        self.assertEqual(len(history),1);self.assertEqual(history[0]['authority_state'],'non_authoritative')
        self.assertEqual(self.project.reviews.membership(self.fixture.ids[0])['state'],'not_reviewed')
        self.command('navigate','previous');self.command('save_next',self.draft())
        self.assertEqual(len(self.project.reviews.history(self.fixture.ids[0])),1)


    def test_save_command_replay_content_conflict_and_new_correction(self):
        self.create();values=dict(command_id=uuid.uuid4().hex,expected_revision=self.state()[2],action='save_next',value=self.draft())
        result=self.service.command(self.session,**values);before=fingerprint(self.project.root)
        self.assertEqual(self.service.command(self.session,**values),result);self.assertEqual(before,fingerprint(self.project.root))
        with self.assertRaises(ContractError):self.service.command(self.session,**{**values,'value':self.draft('excluded')})
        self.command('navigate','previous');self.command('save_next',self.draft('excluded'))
        history=self.project.reviews.history(self.fixture.ids[0]);self.assertEqual(len(history),2)
        self.assertTrue(all(x['supersedes'] is None for x in history))

    def test_metadata_only_and_insufficient_are_reviewable_not_automatic_exclusion(self):
        self.create()
        for i in range(8):self.command('save_next',self.draft('insufficient_evidence' if i==4 else 'included'))
        self.finish();self.assertEqual(self.state()[1]['completion']['summary']['counts']['insufficient_evidence'],1)
        self.assertTrue(all(self.project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.ids))

    def test_document_extent_requires_frozen_verified_document_and_explicit_open(self):
        self.fixture.document(self.fixture.ids[0]);self.create()
        draft={**self.draft(),'review_extent':'sections'}
        with self.assertRaises(ContractError):self.command('save_next',draft)
        self.command('open');self.assertIn('Invented material',self.controller.document(self.project,self.handle)['text'])
        self.command('save_next',draft)
        with self.assertRaises(ContractError):self.command('save_next',draft)

    def test_changed_unsaved_draft_is_not_selected_for_completion(self):
        self.create();self.command('save_next',self.draft());self.command('navigate','previous')
        self.command('draft',self.draft('excluded'));self.finish()
        completion=self.state()[1]['completion']
        self.assertEqual(completion['saved_events'],{});self.assertEqual(completion['summary']['changed_drafts'],1)
        self.assertEqual(len(self.project.reviews.history(self.fixture.ids[0])),1)

    def test_finish_never_publishes_and_completed_or_legacy_mutations_are_refused(self):
        self.create();self.command('save_next',self.draft());self.finish()
        self.assertEqual(self.state()[1]['lifecycle'],'completed')
        with self.assertRaises(ContractError):self.command('draft',self.draft())
        with self.assertRaises(ContractError):self.project.review_sessions.update(self.session,expected_revision=self.state()[2],action='commit')
        self.assertEqual(self.project.reviews.membership(self.fixture.ids[0])['state'],'not_reviewed')

    def test_authorized_atomic_publication_explicit_source_links_and_replay(self):
        self.create()
        for outcome in ('included','excluded','insufficient_evidence'):self.command('save_next',self.draft(outcome))
        self.finish();self.assertTrue(all(self.project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.ids))
        self.command('prepare_publication');values=dict(command_id=uuid.uuid4().hex,expected_revision=self.state()[2],
            action='publish',value={'plan_sha256':self.state()[1]['publication_plan']['sha256'],'confirm_authority':True})
        result=self.service.command(self.session,**values);self.assertEqual(self.service.command(self.session,**values),result)
        self.assertEqual([self.project.reviews.membership(p)['state'] for p in self.state()[1]['order'][:3]],['included','excluded','insufficient_evidence'])
        for link in result['result']['links']:
            events=self.project.reviews.history(link['paper_id'])
            self.assertEqual(events[0]['event_id'],link['observation_event_id']);self.assertEqual(events[1]['event_id'],link['authority_event_id'])
            self.assertEqual(events[1]['supersedes'],None)
        self.assertEqual(len(result['result']['links']),3)

    def test_unauthorized_identity_never_gains_authority_from_configuration_authorship(self):
        self.create(reviewer='configuration_author');self.command('save_next',self.draft());self.finish()
        before=fingerprint(self.project.root)
        with self.assertRaises(ContractError):self.command('prepare_publication')
        with self.assertRaises(ContractError):self.command('publish',{'confirm_authority':True})
        self.assertEqual(before,fingerprint(self.project.root))

    def test_publication_failure_rolls_back_every_decision_and_receipt(self):
        self.create();self.command('save_next',self.draft());self.command('save_next',self.draft('excluded'))
        self.finish();self.command('prepare_publication');before=fingerprint(self.project.root)
        original=type(self.project.reviews)._apply;calls=[]
        def fail(service,*args):
            calls.append(1)
            if len(calls)==2:raise ContractError('controlled second-item failure')
            return original(service,*args)
        with patch('corpustrail.curation.service.ReviewService._apply',fail),self.assertRaises(ContractError):self.publish()
        self.assertEqual(before,fingerprint(self.project.root))
        self.assertTrue(all(self.project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.ids))
        self.publish()

    def test_competing_history_requires_new_preview_and_explicit_supersession(self):
        self.create();self.command('save_next',self.draft());self.finish();self.command('prepare_publication')
        authority=self.fixture.label(self.fixture.ids[0],state='excluded')
        before=fingerprint(self.project.root)
        with self.assertRaises(ContractError):self.publish()
        self.assertEqual(before,fingerprint(self.project.root))
        self.command('prepare_publication');self.publish()
        current=self.project.reviews.membership(self.fixture.ids[0])
        self.assertEqual(current['decision_provenance']['supersedes'],authority)

    def test_scope_and_unrelated_config_revision_guards_are_preserved(self):
        self.create();self.project.configure(replace(self.project.config,config_version=self.project.config.config_version+1,description='Permitted changed description'),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
        before=fingerprint(self.project.root)
        with self.assertRaises(ContractError):self.command('save_next',self.draft())
        self.assertEqual(before,fingerprint(self.project.root));self.assertTrue(self.controller.view(self.project,self.handle)['stale'])
        self.create();self.command('save_next',self.draft());self.finish();self.command('prepare_publication');self.publish()
        with self.assertRaisesRegex(ContractError,'scope'):self.project.configure(replace(self.project.config,config_version=self.project.config.config_version+1,
            review=replace(self.project.config.review,scope='Different scope')),expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')

    def test_legacy_authorized_sessions_keep_immediate_per_paper_semantics(self):
        self.fixture.prepare();self.fixture.update('draft',self.fixture.draft());self.fixture.update('commit')
        self.assertEqual(self.project.reviews.membership(self.fixture.ids[0])['state'],'included')
        before=fingerprint(self.project.root);config=self.controller.configuration(self.project)
        self.assertTrue(config['sessions'][0]['legacy']);self.controller.view(self.project,config['sessions'][0]['handle'])
        self.assertEqual(before,fingerprint(self.project.root))

    def test_real_independent_process_duplicate_save_records_once(self):
        self.create();values=dict(command_id=uuid.uuid4().hex,expected_revision=self.state()[2],action='save_next',value=self.draft())
        code='import json,sys; from corpustrail.project import Project; from corpustrail.curation.guided import GuidedReviewService; p=Project.open(sys.argv[1]); print(json.dumps(GuidedReviewService(p).command(sys.argv[2],**json.loads(sys.argv[3]))))'
        args=[sys.executable,'-I','-c',code,str(self.project.root),self.session,json.dumps(values)]
        processes=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        results=[p.communicate(timeout=30) for p in processes]
        self.assertEqual([p.returncode for p in processes],[0,0],results)
        self.assertEqual(json.loads(results[0][0]),json.loads(results[1][0]))
        self.assertEqual(len(self.project.reviews.history(self.fixture.ids[0])),1)

    def test_concurrent_stale_commands_cannot_overwrite_a_saved_observation(self):
        self.create();revision=self.state()[2];results=[]
        def save():
            try:results.append(self.command('save_next',self.draft(),expected_revision=revision))
            except ContractError:results.append('stale')
        threads=[threading.Thread(target=save) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(10)
        self.assertEqual(results.count('stale'),1)
        self.assertEqual(len(self.project.reviews.history(self.fixture.ids[0])),1)



class GuidedReviewHttpTests(unittest.TestCase):
    def setUp(self):
        helper=GuidedReviewTests();helper.setUp();self.addCleanup(helper.doCleanups)
        self.helper,self.project=helper,helper.project
        patcher=patch('corpustrail.application.project_use.lock_directory',return_value=self.project.root.parent/'locks')
        patcher.start();self.addCleanup(patcher.stop)
        self.controller=ProjectController(projects_root=self.project.root.parent,project=self.project)
        self.addCleanup(self.controller.close)
        self.server=make_server(controller=self.controller,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        _,_,page=self.request('GET','/review',auth=False)
        self.token=re.search('name="corpustrail-session" content="([^"]+)"',page).group(1)

    def close(self):
        self.server.shutdown();self.thread.join(10);self.server.server_close()

    def request(self,method,path,body=None,*,auth=True,headers=None):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            sent={'Origin':self.origin}
            if auth:sent.update({'X-CorpusTrail-Session':self.token,'X-CorpusTrail-CSRF':self.token})
            if body is not None:sent['Content-Type']='application/json'
            sent.update(headers or {})
            client.request(method,path,body=json.dumps(body) if body is not None else None,headers=sent)
            response=client.getresponse();return response.status,dict(response.getheaders()),response.read().decode()
        finally:client.close()

    def create(self,reviewer='configuration_author'):
        _,_,raw=self.request('GET','/api/v1/review/configuration');config=json.loads(raw)
        request={'schema':'corpustrail-guided-review/v1','command_id':uuid.uuid4().hex,'reviewer_id':reviewer,
            'selection':'all','population_sha256':config['populations'][0]['sha256'],
            'config_event_id':config['config_event_id'],'mode':'method-blind'}
        status,_,body=self.request('POST','/api/v1/review/create',request)
        self.assertEqual(status,200,body);return json.loads(body)

    def test_host_origin_csrf_payload_and_gets_never_create_sessions(self):
        before=fingerprint(self.project.root)
        self.assertEqual(self.request('GET','/review',headers={'Host':'attacker.invalid'})[0],403)
        self.assertEqual(self.request('GET','/review',headers={'Origin':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/v1/review/create',{},auth=False)[0],403)
        self.assertEqual(self.request('POST','/api/v1/review/create',{},headers={'Origin':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/v1/review/create',{'large':'x'*66000})[0],413)
        self.assertEqual(self.request('GET','/api/v1/review/create')[0],404)
        self.assertEqual(before,fingerprint(self.project.root))

    def test_legitimate_http_save_replay_and_readonly_resume(self):
        result=self.create();path='/api/v1/review/sessions/'+result['handle']
        request={'schema':'corpustrail-guided-review/v1','handle':result['handle'],'command_id':uuid.uuid4().hex,
            'expected_revision':result['revision'],'action':'save_next','value':self.helper.draft()}
        status,headers,body=self.request('POST','/api/v1/review/command',request)
        self.assertEqual(status,200,body);self.assertIn("default-src 'none'",headers['Content-Security-Policy'])
        self.assertEqual(json.loads(self.request('POST','/api/v1/review/command',request)[2]),json.loads(body))
        before=fingerprint(self.project.root)
        status,_,view=self.request('GET',path);self.assertEqual(status,200)
        self.assertEqual(json.loads(view)['recorded_count'],1)
        self.assertEqual(before,fingerprint(self.project.root))
        self.assertNotIn('provider-private-query',view)

    def test_unsafe_handle_unknown_fields_and_authority_attempts_fail_closed(self):
        result=self.create();before=fingerprint(self.project.root)
        for action,value in (('publish',{'confirm_authority':True}),('draft',{'authority_state':'human_authorized'})):
            request={'schema':'corpustrail-guided-review/v1','handle':result['handle'],'command_id':uuid.uuid4().hex,
                'expected_revision':result['revision'],'action':action,'value':value}
            status,_,response=self.request('POST','/api/v1/review/command',request)
            self.assertEqual(status,409);self.assertNotIn(str(self.project.root),response)
        for suffix in ('../../etc/passwd','0'*64+'/document?path=/etc/passwd'):
            self.assertIn(self.request('GET','/api/v1/review/sessions/'+suffix)[0],(400,404))
        self.assertEqual(before,fingerprint(self.project.root))

    def test_review_save_holds_project_protection_until_transaction_finishes(self):
        result=self.create();entered=threading.Event();release=threading.Event();closed=threading.Event();responses=[]
        from corpustrail.curation.service import ReviewService
        original=ReviewService._apply
        def gated(service,*args):
            entered.set()
            if not release.wait(5):raise ContractError('controlled test timeout')
            return original(service,*args)
        request={'schema':'corpustrail-guided-review/v1','handle':result['handle'],'command_id':uuid.uuid4().hex,
            'expected_revision':result['revision'],'action':'save_next','value':self.helper.draft()}
        with patch.object(ReviewService,'_apply',gated):
            worker=threading.Thread(target=lambda:responses.append(self.request('POST','/api/v1/review/command',request)))
            closer=threading.Thread(target=lambda:(self.controller.close(),closed.set()))
            try:
                worker.start();self.assertTrue(entered.wait(3));closer.start()
                self.assertFalse(closed.wait(.05))
                with self.assertRaises(ProjectBusy):acquire_project_use(self.project.root,exclusive=True)
            finally:
                release.set();worker.join(10);closer.join(10)
        self.assertEqual(responses[0][0],200);self.assertTrue(closed.is_set())
        with acquire_project_use(self.project.root,exclusive=True):pass
