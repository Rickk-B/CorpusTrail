"""Offline adapter tests through actual frozen plans, source stores and CP9."""
from contextlib import closing
import copy
import http.client
import json
from pathlib import Path
import re
import threading
import time
import unittest
import uuid

from corpustrail._internal.database import connection
from corpustrail._internal.values import ContractError, content_hash
from corpustrail.application.chatgpt import ChatGPTController, SCHEMA
from corpustrail.application.curation import CurationController
from corpustrail.application.projects import ProjectController, ProjectCommandError
from corpustrail.chatgpt.connection import ChatGPTConnection, DIRECT
from corpustrail.chatgpt.credentials import CredentialStore
from corpustrail.chatgpt.engine import ChatGPTEngine, DESTINATION
from corpustrail.chatgpt.transport import ConnectionFailure
from corpustrail.classification import AssessmentFailure, Budgets, ClassificationService
from corpustrail.local_app import make_server
from test_chatgpt_connection import FixtureTransport
import test_classification as baseline
from test_classification import scientific_state


class AssessmentTransport(FixtureTransport):
    def __init__(self):
        super().__init__(); self.sent = []; self.failure_at = None; self.alter = None
    def response(self, payload, *, bearer, cancelled=lambda: False):
        if cancelled(): raise ConnectionFailure('cancelled')
        self.sent.append(copy.deepcopy(payload))
        if self.failure_at == len(self.sent): raise ConnectionFailure('usage_limit')
        target = json.loads(payload['input'][0]['content'])['target']
        result = {'paper_id': target['paper_id'], 'outcome': 'uncertain', 'evidence_sufficiency': 'unknown',
            'rationale': 'Synthetic protocol fixture, not scientific inference.', 'uncertainty': 'Not independently validated.',
            'limitations': ['No real model call.'], 'evidence_hashes': target['source_hashes']}
        if self.alter: result = self.alter(result)
        response = {'id': 'synthetic-response', 'status': 'completed', 'model': 'fixture-reported-model',
            'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps(result)}]}],
            'usage': {'input_tokens': 10, 'output_tokens': 10}}
        return response, {'wire_request_sha256':content_hash(payload), 'terminal_event':'response.completed'}


class OfflineConnection(ChatGPTConnection):
    """Synthetic transport fixture, never an account or real eligibility claim."""
    def status(self):
        value = super().status(); value['installed'] = True
        return value


def synthetic_connection(root, *, permitted=True):
    store = CredentialStore(Path(root).resolve() / 'private-chatgpt-fixture')
    transport = AssessmentTransport(); client = OfflineConnection(store=store, transport=transport)
    with store.transaction() as state:
        state['active'] = 'synthetic-profile'; state['host_id'] = 'urn:uuid:00000000-0000-4000-8000-000000000001'
        state['profiles']['synthetic-profile'] = {'client_id':'oaiapp_synthetic', 'subject':'synthetic-subject',
            'label':'Synthetic offline registration', 'plan_notice_acknowledged':True, 'access_token':'synthetic-access', 'refresh_token':'synthetic-refresh',
            'scope':DIRECT, 'expires_at':time.time()+3600,
            'plan_only_permit': {'client_id':'oaiapp_synthetic','subject':'synthetic-subject',
                'credits_disabled_verified':permitted,'owner_evidence_sha256':'0'*64,'expires_at':time.time()+3600}}
    client._models={'synthetic-profile':transport.catalog['models'][:1]}
    return client


class ChatGPTAssessmentTests(unittest.TestCase):
    def setUp(self):
        helper = baseline.ClassificationTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        self.h=helper; self.project=helper.project
        self.client=synthetic_connection(self.project.root.parent)
        self.curation=CurationController(registry=helper.registry, clock=lambda:'2026-01-01T00:00:00+00:00')
        self.app=ChatGPTController(self.curation, connection_client=self.client, clock=lambda:'2026-01-01T00:00:00+00:00',synthetic=True)
        self.addCleanup(self.curation.close); self.addCleanup(self.app.close)

    def preview(self, **extra):
        body={'request_id':uuid.uuid4().hex,'actor':'curator','population_version_id':self.h.pop,
            'reference_version_id':self.h.ref,'model':'fixture-model',**extra}
        return self.app.preview(self.project,body)

    def confirm(self, preview, **extra):
        body={'request_id':uuid.uuid4().hex,'preview_id':preview['preview_id'],'preview_sha256':preview['preview_sha256'],
              'confirmed':True,'confirm_external':True,**extra}
        return self.app.command(self.project,'confirm',body),body

    def wait(self, rid):
        end=time.monotonic()+10
        while time.monotonic()<end:
            value=self.curation.run(self.project,rid)
            if not value['local_worker_active']: return value
            time.sleep(.01)  # Background-worker unit test; no visual timing dependency.
        self.fail('Synthetic assessment worker did not finish')

    def test_exact_frozen_preview_execution_and_existing_curation_history(self):
        before=scientific_state(self.project)
        preview=self.preview(); self.assertEqual(self.client.transport.sent,[])
        self.assertEqual(before,scientific_state(self.project))
        self.assertEqual(len(preview['manifest']['requests']),3)
        for item in preview['manifest']['requests']:
            payload=item['payload']; self.assertIs(payload['store'],False); self.assertIs(payload['stream'],True)
            self.assertNotIn('tools',payload); self.assertNotIn('temperature',payload); self.assertNotIn('max_output_tokens',payload)
            self.assertEqual(content_hash({'destination':DESTINATION,'payload':payload}),item['wire_sha256'])
            source=json.loads(payload['input'][0]['content']); self.assertIn('abstract_missing',source['target'])
        result,body=self.confirm(preview); run=self.wait(result['run_id'])
        self.assertEqual(run['status'],'completed');self.assertEqual(run['processed'],3)
        rows=self.curation.results(self.project,result['run_id'])
        self.assertEqual(rows['primary']['uncertain'],3)
        service=self.curation.classifier(self.project)
        for row in service.results(result['run_id'])['items']:
            value=row['assessment'];self.assertEqual(value['reported_model'],'fixture-reported-model')
            self.assertIsNone(value['score']);self.assertIn('provider_response',value['usage'])
            self.assertEqual(row['authority'],'non_authoritative')
        self.assertTrue(service.verify_run(result['run_id'])['verified'])
        self.assertEqual(before,scientific_state(self.project))
        replay=self.app.command(self.project,'confirm',body);self.assertTrue(replay['replayed']);self.assertEqual(len(self.client.transport.sent),3)
        reopened=ChatGPTController(self.curation,connection_client=self.client,synthetic=True)
        self.assertEqual(reopened.inspect(self.project,preview['preview_id'])['manifest'],preview['manifest'])

    def test_changed_preview_hash_and_unconfirmed_transfer_make_no_request(self):
        preview=self.preview()
        for extra in ({'preview_sha256':'sha256:'+'0'*64},{'confirmed':False},{'confirm_external':False}):
            with self.assertRaises(ContractError):self.confirm(preview,**extra)
        self.assertEqual(self.client.transport.sent,[])

    def test_changed_actual_wire_invalidates_adapter_consent(self):
        preview=self.preview();engine=self.app._engines[('synthetic-profile','fixture-model')]
        engine.authorize(preview['plan_id'],preview['manifest'])
        service=self.curation.classifier(self.project)
        with connection(self.project.database_path) as db:
            from corpustrail.classification import storage
            head=storage.plan(db,preview['plan_id']);record=storage.items(db,preview['plan_id'],limit=1)[0]
        unit=service._unit(preview['plan_id'],head,record)
        original=engine.wire
        def changed(unit):
            wire=original(unit);wire['instructions']+=' Changed after consent.';return wire
        engine.wire=changed
        result=engine.assess(None,(unit,))[0]
        self.assertIsInstance(result,AssessmentFailure);self.assertEqual(result.diagnostics['category'],'consent_changed')
        self.assertEqual(self.client.transport.sent,[])

    def test_no_cost_gate_blocks_before_run_and_eligibility_is_independent(self):
        preview=self.preview()
        with self.client.store.transaction() as state:state['profiles']['synthetic-profile']['plan_only_permit']=None
        with self.assertRaises(ProjectCommandError) as error:self.confirm(preview)
        self.assertEqual(error.exception.code,'chatgpt_no_cost_not_verified')
        self.assertEqual(self.client.transport.sent,[])
        with self.client.store.transaction() as state:state['profiles']['synthetic-profile']['scope']='openid'
        with self.assertRaises(ConnectionFailure):self.preview()

    def test_usage_limit_preserves_completed_work_and_unattempted_tail(self):
        preview=self.preview();self.client.transport.failure_at=2
        result,_=self.confirm(preview);state=self.wait(result['run_id'])
        self.assertEqual(state['status'],'partial');self.assertEqual(state['primary_counts']['uncertain'],1)
        self.assertEqual(state['primary_counts']['failed'],1);self.assertEqual(state['primary_counts']['not_assessed'],1)
        self.assertEqual(len(self.client.transport.sent),2)
        rows=self.curation.classifier(self.project).results(result['run_id'])['items']
        self.assertEqual(rows[1]['failure']['diagnostics']['category'],'usage_limit')
        self.assertNotIn('outcome',rows[1]['failure'])

    def test_invalid_outputs_are_failures_not_judgments_and_credentials_are_not_retained(self):
        for alter in (lambda r:{**r,'membership':'included'},lambda r:{**r,'outcome':'exclude','evidence_sufficiency':'insufficient'},
                      lambda r:{**r,'rationale':'synthetic-access'},lambda r:{**r,'evidence_hashes':['sha256:'+'0'*64]}):
            self.client.transport.alter=alter;preview=self.preview();result,_=self.confirm(preview);state=self.wait(result['run_id'])
            self.assertEqual(state['processed'],1);self.assertEqual(state['primary_counts']['failed'],1)
            rows=self.curation.classifier(self.project).results(result['run_id'])
            self.assertNotIn('synthetic-access',json.dumps(rows))
            self.assertTrue(all(self.project.reviews.membership(pid)['state']=='not_reviewed' for pid in self.h.ids))

    def test_remote_contract_requires_exact_transmission_consent_and_legacy_failure_shape(self):
        self.assertEqual(AssessmentFailure(self.h.ids[0],'unavailable').to_dict(),
            {'paper_id':self.h.ids[0],'reason':'unavailable','retryable':False})
        preview=self.preview();service=self.curation.classifier(self.project)
        with self.assertRaises(ContractError):service.start_run(preview['plan_id'],request_id=uuid.uuid4().hex,
            actor='curator',created_at='2026-01-01T00:00:00+00:00',transfer_sha256=preview['plan_transfer_sha256'])
        # A historical offline plan remains readable/verifiable after using v2.
        plan=self.h.plan();self.assertEqual(service.inspect_plan(plan['plan_id'])['schema'],'corpustrail-assessment-plan/v1')
        self.assertTrue(service.verify_plan(plan['plan_id'])['verified'])

    def test_http_boundary_csrf_blinded_isolation_and_preview_persistence(self):
        controller=ProjectController(project=self.project)
        server=make_server(controller=controller,curation=self.curation,chatgpt=self.app,port=0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(method,path,body=None,auth=True):
            with closing(http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)) as client:
                headers={'Origin':'http://127.0.0.1:'+str(server.server_port)}
                if auth: headers.update({'X-CorpusTrail-Session':session,'X-CorpusTrail-CSRF':session})
                if body is not None:headers['Content-Type']='application/json'
                client.request(method,path,json.dumps(body) if body is not None else None,headers)
                r=client.getresponse();return r.status,r.read().decode()
        session=''
        try:
            code,html=request('GET','/chatgpt');self.assertEqual(code,200)
            session=re.search('name="corpustrail-session" content="([^"]+)"',html).group(1)
            code,raw=request('GET','/api/v1/chatgpt/configuration');self.assertEqual(code,200)
            self.assertNotIn('synthetic-access',raw)
            code,_=request('POST','/api/v1/chatgpt/disconnect',{'schema':SCHEMA,'confirmed':True},auth=False)
            self.assertEqual(code,403)
            for values in ({'confirmed':True,'credits_disabled_verified':True}, {'confirmed':True,'endpoint':'https://attacker.invalid'}):
                code,_=request('POST','/api/v1/chatgpt/models',{'schema':SCHEMA,**values});self.assertNotEqual(code,200)
            preview=self.preview();code,raw=request('GET','/api/v1/chatgpt/previews/'+preview['preview_id'])
            self.assertEqual(code,200);self.assertEqual(json.loads(raw)['manifest'],preview['manifest'])
            self.assertEqual(self.client.transport.sent,[])
        finally:
            server.shutdown();worker.join(10);server.server_close();controller.close()

    def test_cancel_inflight_retains_completed_proposal_and_unassessed_tail(self):
        preview=self.preview();entered=threading.Event();release=threading.Event();base=self.client.transport.response
        count=0
        def delayed(payload,**kwargs):
            nonlocal count
            count+=1
            if count==2:
                entered.set()
                if not release.wait(10):raise AssertionError('Controlled cancellation fixture did not release')
            return base(payload,**kwargs)
        self.client.transport.response=delayed
        try:
            result,_=self.confirm(preview);self.assertTrue(entered.wait(10))
            self.curation.command(self.project,'cancel',{'run_id':result['run_id']})
            release.set();state=self.wait(result['run_id'])
            self.assertEqual(state['status'],'interrupted');self.assertEqual(state['primary_counts']['uncertain'],1)
            self.assertEqual(state['primary_counts']['not_assessed'],1);self.assertEqual(state['primary_counts']['failed'],1)
            self.assertEqual(len(self.client.transport.sent),1)
        finally:release.set()

    def test_disconnect_does_not_cancel_an_unrelated_offline_assessment(self):
        before=scientific_state(self.project);plan=self.h.plan();rid=self.h.start(plan['plan_id'])
        entered=threading.Event();release=threading.Event();base=self.h.engine.assess
        def delayed(*args):
            entered.set()
            if not release.wait(10):raise AssertionError('Controlled offline worker did not release')
            return base(*args)
        self.h.engine.assess=delayed
        try:
            self.curation.execute(self.project,rid,self.h.service.inspect_run(rid)['revision'])
            self.assertTrue(entered.wait(10))
            event=self.curation._workers[(str(self.project.root),rid)][1]
            result=self.app.command(self.project,'disconnect',{'confirmed':True})
            self.assertTrue(result['local_tokens_removed']);self.assertFalse(event.is_set())
            release.set();state=self.wait(rid)
            self.assertEqual(state['status'],'completed');self.assertEqual(state['processed'],3)
            self.assertEqual(before,scientific_state(self.project))
        finally:
            release.set();self.wait(rid)

    def test_disconnect_cancels_only_its_remote_worker_and_preserves_completed_work(self):
        before=scientific_state(self.project);preview=self.preview()
        entered=threading.Event();release=threading.Event();base=self.client.transport.response;count=0;rid=None
        def delayed(payload,**kwargs):
            nonlocal count
            count+=1
            if count==2:
                entered.set()
                if not release.wait(10):raise AssertionError('Controlled disconnect fixture did not release')
            return base(payload,**kwargs)
        self.client.transport.response=delayed
        try:
            result,_=self.confirm(preview);rid=result['run_id'];self.assertTrue(entered.wait(10))
            event=self.curation._workers[(str(self.project.root),rid)][1]
            disconnected=self.app.command(self.project,'disconnect',{'confirmed':True})
            self.assertTrue(disconnected['local_tokens_removed']);self.assertTrue(event.is_set())
            release.set();state=self.wait(rid)
            self.assertEqual(state['status'],'interrupted');self.assertEqual(state['primary_counts']['uncertain'],1)
            self.assertEqual(state['primary_counts']['failed'],1);self.assertEqual(state['primary_counts']['not_assessed'],1)
            self.assertEqual(len(self.client.transport.sent),1);self.assertEqual(before,scientific_state(self.project))
        finally:
            release.set()
            if rid:self.wait(rid)

    def test_competing_confirmation_cannot_replace_active_consent_or_cancellation(self):
        first=self.preview();second=self.preview()
        entered=threading.Event();release=threading.Event();base=self.client.transport.response
        def delayed(payload,**kwargs):
            entered.set()
            if not release.wait(10):raise AssertionError('Controlled competing confirmation did not release')
            return base(payload,**kwargs)
        self.client.transport.response=delayed
        result=None
        try:
            result,command=self.confirm(first);self.assertTrue(entered.wait(10))
            engine=self.app._engine(first['manifest']['model'],first['manifest']['profile_id'])
            cancel=engine.cancelled
            # An identical retry still returns the same durable run, without resending.
            replay=self.app.command(self.project,'confirm',command)
            self.assertEqual(replay['run_id'],result['run_id']);self.assertTrue(replay['replayed'])
            with self.assertRaises(ContractError):self.confirm(second)
            self.assertIs(engine.cancelled,cancel)
            self.assertEqual(self.curation.classifier(self.project).runs()['total'],1)
            self.curation.command(self.project,'cancel',{'run_id':result['run_id']})
            release.set();state=self.wait(result['run_id'])
            self.assertEqual(state['primary_counts']['failed'],1)
            self.assertEqual(state['primary_counts']['not_assessed'],2)
            self.assertEqual(self.client.transport.sent,[])
            self.assertTrue(all(self.project.reviews.membership(pid)['state']=='not_reviewed' for pid in self.h.ids))
        finally:
            release.set()
            if result:self.wait(result['run_id'])

    def test_credentials_cannot_be_stored_inside_or_around_a_research_project(self):
        original=self.client.store
        try:
            for root in (self.project.root/'private-chatgpt', self.project.root.parent):
                self.client.store=CredentialStore(root)
                with self.assertRaises(ProjectCommandError) as error:self.app.configuration(self.project)
                self.assertEqual(error.exception.code,'chatgpt_storage_boundary')
        finally:self.client.store=original

    def test_configuration_does_not_mutate_or_transfer_and_no_credentials_in_preview(self):
        before=scientific_state(self.project);self.app.configuration(self.project)
        self.assertEqual(self.client.transport.calls,[]);self.assertEqual(before,scientific_state(self.project))
        preview=self.preview();body=json.dumps(preview)
        for value in ('synthetic-access','synthetic-refresh','oaiapp_synthetic','synthetic-subject'):
            self.assertNotIn(value,body)
