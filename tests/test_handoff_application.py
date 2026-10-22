"""CP10 real services/API: local operation, explicit provenance and no authority shortcuts."""
import base64
from dataclasses import replace
import hashlib
import http.client
import json
import os
import re
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from corpustrail._internal.database import connection
from corpustrail._internal.values import ContractError
from corpustrail.application.handoff import HandoffController, SCHEMA
from corpustrail.application.projects import ProjectController
from corpustrail.local_app import make_server
from corpustrail.models import AdapterRegistry, ModelConfig, ModelService
from corpustrail.models.contracts import AdapterInfo, ModelResponse


class OfflineWire:
    info=AdapterInfo('offline-wire','synthetic','v1',True,('structured_assertions/v1','connection_test/v1'))
    def __init__(self):self.calls=[]
    def connection_request(self):return {'message':'synthetic connection only'}
    def test_connection(self,request,*,credential=None):
        self.calls.append(request);return ModelResponse({},'synthetic-model',('synthetic-model',),False)
    def invoke(self,request,*,credential=None):
        self.calls.append(request);e=request['evidence'][0]
        return ModelResponse({'claims':[{'predicate':'ct.organism_population','raw_value':e['text'],
            'value_datatype':'string','evidence_id':e['evidence_id'],'quote':e['text']}]},'synthetic-model',('synthetic-model',),False)


class HandoffApplicationTests(unittest.TestCase):
    def setUp(self):
        from test_knowledge import KnowledgeTests
        self.h=KnowledgeTests();self.h.setUp();self.addCleanup(self.h.doCleanups);self.project=self.h.project
        self.wire=OfflineWire();self.registry=AdapterRegistry([self.wire])
        self.app=HandoffController(clock=lambda:'2026-01-02T00:00:00+00:00',model_service=lambda p:ModelService(p,registry=self.registry))
        self.addCleanup(self.app.close)

    def prepare(self,kind,**fields):
        return self.app.prepare(self.project,kind,{'actor':'reviewer',**fields},request_id=uuid.uuid4().hex)

    def finish(self,op,*,external=False):
        result=self.app.execute(self.project,op['id'],preview_sha256=op['preview_sha256'],confirmed=True,confirm_external=external)
        deadline=time.monotonic()+20
        while result['status']=='running' and time.monotonic()<deadline:
            time.sleep(.01);result=self.app.operation(self.project,op['id'])
        self.assertNotEqual(result['status'],'running');return result

    def label(self,pid,state='included'):
        from corpustrail.curation import ReviewEvent,EvidenceBasis
        source=self.project.identities.observations(pid)[0]['source']
        event=ReviewEvent(pid,state,'sufficient','metadata','Invented human decision','reviewer','2026-01-01T00:00:00+00:00',
            (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
            producer_type='human',authority_state='human_authorized',supersedes=self.project.reviews.membership(pid)['current_event_id'])
        self.project.reviews.apply(self.project.reviews.plan(event),recorded_at='2026-01-01T00:00:00+00:00')

    def configured(self):
        current=self.project.config
        self.project.configure(replace(current,config_version=current.config_version+1,
            models=(ModelConfig('offline-task','offline-wire','synthetic-model'),)),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='reviewer')

    def assertion(self):
        return self.prepare('assertion',paper=self.h.ids[0].split(':')[1],predicate='ct.organism_population',
            value='Invented organism',unknown=False,evidence=self.project.identities.observations(self.h.ids[0])[0]['observation_id'],
            rationale='Explicit synthetic human reading.')

    def test_open_readers_are_read_only_and_bounded(self):
        from test_populations import fingerprint
        before=fingerprint(self.project.root)
        config=self.app.configuration(self.project);self.assertFalse(config['synthetic_priority'])
        for section in ('knowledge','rankings','exports','operations','connections','extractions','mappings'):
            r=self.app.list(self.project,section,limit=1);self.assertLessEqual(len(r['items']),1)
        self.assertEqual(before,fingerprint(self.project.root));self.assertEqual(self.wire.calls,[])
        with self.assertRaises(ContractError):self.app.list(self.project,'knowledge',limit=101)
        with self.assertRaises(ContractError):self.app.list(self.project,'knowledge',offset=1)

    def test_assertion_preview_commit_replay_restart_and_unknown(self):
        op=self.assertion();self.assertEqual(self.project.knowledge_store.assertions(),[])
        result=self.finish(op);self.assertEqual(result['status'],'complete',result)
        self.assertEqual(self.finish(op),result)
        restarted=HandoffController();self.addCleanup(restarted.close)
        self.assertEqual(restarted.operation(self.project,op['id'])['status'],'complete')
        assertion=self.project.knowledge_store.assertions()[0]['payload']
        self.assertEqual(assertion['producer_type'],'human');self.assertEqual(assertion['initial_authority'],'non_authoritative')
        self.assertTrue(all(self.project.reviews.membership(pid)['state']=='not_reviewed' for pid in self.h.ids))
        unknown=self.prepare('assertion',paper=self.h.ids[1].split(':')[1],predicate='ct.organism_population',value='',unknown=True,
            evidence=self.project.identities.observations(self.h.ids[1])[0]['observation_id'],rationale='Unknown, not a negative label.')
        self.assertEqual(self.finish(unknown)['status'],'complete')

    def test_bounded_knowledge_pages_preserve_default_view_and_current_heads(self):
        self.label(self.h.ids[0]);self.label(self.h.ids[0],'excluded')
        expected=self.project.knowledge.observations();actual=[];offset=0;revision=None
        while True:
            r=self.app.list(self.project,'knowledge',offset=offset,limit=1,revision=revision)
            actual.extend(r['items']);revision=r['revision']
            if r['next_offset'] is None:break
            offset=r['next_offset']
        self.assertEqual([v['observation_ref'] for v in actual],[v['observation_ref'] for v in expected])
        for value in expected:
            item=next(v for v in actual if v['observation_ref']==value['observation_ref'])
            self.assertEqual(item['authority'],value['authority'])
            full=self.app.knowledge(self.project,item['handle']);self.assertEqual(json.loads(full['text']),value)

    def test_explicit_knowledge_authority_is_purpose_scoped_and_unauthorized_refused(self):
        self.finish(self.assertion());row=self.app.list(self.project,'knowledge',predicate='ct.organism_population')['items'][0]
        event=self.prepare('knowledge_event',observation=row['handle'],relation='grants_authority',rationale='Explicit reviewed claim',
            purpose='knowledge.organization',policy='synthetic-human/v1')
        self.assertEqual(self.finish(event)['status'],'complete')
        self.assertEqual(self.project.reviews.membership(self.h.ids[0])['state'],'not_reviewed')
        refused=self.prepare('knowledge_event',actor='not-authorized',observation=row['handle'],relation='grants_authority',rationale='Not authorized',purpose='knowledge.organization',policy='synthetic-human/v1')
        self.assertEqual(self.finish(refused)['status'],'failed')
        self.assertEqual(len(self.project.knowledge_store.history(row['observation_ref'])),1)

    def test_contradictions_and_successor_relations_preserve_both_observations(self):
        self.finish(self.assertion());other=self.prepare('assertion',paper=self.h.ids[0].split(':')[1],predicate='ct.organism_population',value='Contradictory organism',unknown=False,
            evidence=self.project.identities.observations(self.h.ids[0])[0]['observation_id'],rationale='Independent explicit assertion')
        self.finish(other);rows=self.app.list(self.project,'knowledge',predicate='ct.organism_population')['items']
        value=self.app.knowledge(self.project,rows[0]['handle']);self.assertTrue(value['summary']['conflicting_values'])
        self.assertEqual(self.app.knowledge(self.project,rows[0]['handle'],section='peers',limit=1)['total'],2)
        correction=self.prepare('knowledge_event',observation=rows[0]['handle'],source_observation=rows[1]['handle'],relation='supersedes',
            rationale='Explicit correction, both originals retained',purpose='knowledge.organization',policy='synthetic/v1')
        self.assertEqual(self.finish(correction)['status'],'complete');self.assertEqual(len(self.project.knowledge_store.assertions()),2)

    def test_stale_and_changed_commands_reject_without_starting(self):
        op=self.assertion();self.h.enroll(9)
        with self.assertRaises(ContractError):self.finish(op)
        self.assertEqual(self.app.operation(self.project,op['id'])['status'],'prepared')
        with self.assertRaises(ContractError):self.app.execute(self.project,op['id'],preview_sha256='changed',confirmed=True)
        with self.assertRaises(ContractError):self.app.prepare(self.project,'priority',{'actor':'other'},request_id=op['id'])

    def test_exact_model_inputs_consent_and_non_authoritative_results(self):
        self.configured();op=self.prepare('extraction',workflow='offline-task',paper=self.h.ids[0].split(':')[1],instructions='Invented characterization fixture',predicates=['ct.organism_population'],mode='metadata')
        self.assertEqual(self.wire.calls,[]);exact=self.app.exact_plan(self.project,op['id']);self.assertIn('Invented material',exact['text'])
        with self.assertRaises(ContractError):self.finish(op)
        result=self.finish(op,external=True);self.assertEqual(result['status'],'complete',result)
        self.assertEqual(len(self.wire.calls),1);self.assertEqual(len(self.project.knowledge_store.assertions()),1)
        self.assertEqual(self.project.reviews.membership(self.h.ids[0])['state'],'not_reviewed')
        self.assertEqual(self.finish(op,external=True),result);self.assertEqual(len(self.wire.calls),1)
        history=self.app.model_history(self.project);self.assertEqual(history['total'],1)
        event=self.app.model_history(self.project,handle=history['items'][0]['handle'])['items'][0]
        fragments=[];offset=0
        while True:
            part=self.app.model_history(self.project,handle=history['items'][0]['handle'],event=event['event_id'],offset=offset,limit=2000,revision=history['revision'])
            fragments.append(part['text'])
            if part['next_offset'] is None:break
            offset=part['next_offset']
        exact=json.loads(''.join(fragments));self.assertEqual(exact['event_id'],event['event_id'])
        from corpustrail._internal.values import content_hash
        self.assertEqual(part['sha256'],content_hash(exact))

    def test_synthetic_connection_is_separate_and_never_reads_paper_evidence(self):
        self.configured();op=self.prepare('connection',workflow='offline-task')
        with patch.object(self.project.discovery.__class__,'metadata',side_effect=AssertionError('paper read forbidden')):
            result=self.finish(op,external=True)
        self.assertEqual(result['status'],'complete');self.assertEqual(self.wire.calls,[{'message':'synthetic connection only'}])
        self.assertFalse(result['result']['output']['external_evidence_transfer_authorized']);self.assertEqual(self.project.knowledge_store.assertions(),[])

    def test_export_confirmed_members_only_freezes_and_downloads_without_labels(self):
        self.label(self.h.ids[0]);op=self.prepare('export')
        self.assertFalse((self.project.root/self.project.config.data_directory/'asreview/exports').exists())
        result=self.finish(op);self.assertEqual(result['status'],'complete',result)
        eid=result['result']['output']['export_id'];body=self.app.download(self.project,eid,'dataset.csv')
        self.assertIn(b'Invented material',body);self.assertNotIn(b'asreview_label',body);self.assertNotIn(b'relevance',body)
        self.label(self.h.ids[1]);self.assertEqual(self.app.download(self.project,eid,'dataset.csv'),body)
        self.assertEqual(self.app.list(self.project,'exports')['items'][0]['count'],1)

    def test_complete_returned_results_exact_mapping_upload_retries_and_no_membership_change(self):
        self.label(self.h.ids[0]);result=self.finish(self.prepare('export'));eid=result['result']['output']['export_id']
        body=('corpustrail_paper_id,asreview_label\n'+self.h.ids[0]+',0\n').encode();uid=uuid.uuid4().hex
        sha='sha256:'+hashlib.sha256(body).hexdigest();encoded=base64.b64encode(body).decode()
        a=self.app.upload(self.project,request_id=uid,offset=0,body=encoded,final=True,sha256=sha)
        self.assertEqual(self.app.upload(self.project,request_id=uid,offset=0,body=encoded,final=True,sha256=sha),a)
        op=self.prepare('mapping',export=eid,upload=uid,question='synthetic-question',review='synthetic-review',asreview_version='2.2')
        mapped=self.finish(op);self.assertEqual(mapped['status'],'complete',mapped)
        self.assertEqual(self.project.reviews.membership(self.h.ids[0])['state'],'included')
        native=self.project.asreview.mapping(mapped['result']['output']['review_id'],mapped['result']['output']['mapping_id'])
        self.assertEqual(native['records'][0]['question_specific_label'],0);self.assertFalse(native['corpus_membership_changes'])

    def test_confinement_integrity_and_interrupted_reservation_never_auto_execute(self):
        op=self.assertion();self.app.publish(self.project,'started',op['id'],{'interrupted':True})
        self.assertEqual(self.app.operation(self.project,op['id'])['status'],'interrupted')
        with self.assertRaises(ContractError):self.finish(op)
        self.assertEqual(self.project.knowledge_store.assertions(),[])
        for key in ('../escape','/etc/passwd','a'*33):
            with self.assertRaises(ContractError):self.app.operation(self.project,key)
        with self.assertRaises(ContractError):self.app.download(self.project,'../escape','dataset.csv')
        with self.assertRaises(ContractError):self.app.prepare(self.project,'assertion',{'actor':'x','token':'not accepted'},request_id=uuid.uuid4().hex)

    def test_http_pages_security_queries_and_protected_commands(self):
        controller=ProjectController(projects_root=self.project.root.parent,project=self.project);self.addCleanup(controller.close)
        server=make_server(controller=controller,handoff=self.app,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(10),server.server_close()))
        def request(path,method='GET',payload=None,authenticated=True):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            try:
                headers={'Origin':'http://127.0.0.1:'+str(server.server_port)}
                if authenticated:headers.update({'X-CorpusTrail-Session':session,'X-CorpusTrail-CSRF':session})
                if payload:headers['Content-Type']='application/json'
                client.request(method,path,json.dumps(payload) if payload else None,headers)
                r=client.getresponse();return r.status,r.read().decode()
            finally:client.close()
        _,html=request('/home',authenticated=False);session=re.search('name="corpustrail-session" content="([^"]+)"',html).group(1)
        for path in ('/prioritization','/knowledge','/models','/export','/explore','/discovery'):
            status,body=request(path);self.assertEqual(status,200,body);self.assertIn('Explore',body)
        self.assertEqual(request('/api/v1/tools/configuration',authenticated=False)[0],403)
        self.assertEqual(request('/api/v1/tools/knowledge?limit=101')[0],400)
        status,body=request('/api/v1/tools/configuration');self.assertEqual(status,200,body)
        status,_=request('/api/v1/tools/prepare','POST',{'schema':SCHEMA,'kind':'export','values':{'actor':'reviewer'},'request_id':uuid.uuid4().hex},authenticated=False)
        self.assertEqual(status,403)

    def test_optional_real_tfidf_ordering_preserves_entire_tail_and_human_authority(self):
        if not self.app.configuration(self.project)['optional_ml_installed']:
            with self.assertRaises(ContractError):self.prepare('priority')
            return
        self.label(self.h.ids[0]);self.label(self.h.ids[1],'excluded')
        op=self.prepare('priority');result=self.finish(op);self.assertEqual(result['status'],'complete',result)
        self.assertEqual(result['result']['output']['count'],2)
        run=self.app.list(self.project,'rankings')['items'][0]
        ranked=self.app.ranking(self.project,run['handle'],limit=1)
        self.assertEqual(ranked['total'],2);self.assertEqual(ranked['next_offset'],1)
        self.assertEqual(self.project.reviews.membership(self.h.ids[0])['state'],'included')

    def test_large_native_history_pages_and_stale_continuations(self):
        drafts=[self.h.draft(raw_value='Synthetic value '+str(i),lineage_ref='scale-'+str(i)) for i in range(1000)]
        self.project.knowledge_store.apply(self.project.knowledge_store.plan_batch(drafts))
        first=self.app.list(self.project,'knowledge',predicate='ct.organism_population',limit=17)
        self.assertEqual(first['total'],1000);self.assertEqual(len(first['items']),17)
        self.assertLess(len(json.dumps(first)),100000)
        last=self.app.list(self.project,'knowledge',predicate='ct.organism_population',limit=17,offset=986,revision=first['revision'])
        self.assertEqual(len(last['items']),14);self.assertIsNone(last['next_offset'])
        self.h.append(self.h.draft(raw_value='Later independent value',lineage_ref='after-page'))
        with self.assertRaises(ContractError):self.app.list(self.project,'knowledge',offset=17,revision=first['revision'])

    def test_unknown_credentials_fields_and_unsafe_uploads_are_refused(self):
        for bad in ({'actor':'reviewer','password':'do-not-store'}, {'actor':'reviewer','unexpected':True}):
            with self.assertRaises(ContractError):self.app.prepare(self.project,'export',bad,request_id=uuid.uuid4().hex)
        for offset,body,sha in ((-1,'YQ==','sha256:'+'0'*64),(0,'not-base64','sha256:'+'0'*64),(0,'YQ==','sha256:'+'0'*64)):
            with self.assertRaises(ContractError):self.app.upload(self.project,request_id=uuid.uuid4().hex,offset=offset,body=body,final=True,sha256=sha)
        with self.assertRaises(ContractError):self.app.download(self.project,'unused','../dataset.csv')

    def test_runtime_secret_is_refused_in_the_entire_preview_not_only_its_plan(self):
        current=self.project.config
        self.project.configure(replace(current,config_version=current.config_version+1,
            models=(ModelConfig('offline-task','offline-wire','synthetic-model',credential_env='CT_SYNTHETIC_TEST_CREDENTIAL'),)),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='reviewer')
        with patch.dict(os.environ,{'CT_SYNTHETIC_TEST_CREDENTIAL':'invented-sensitive-value-for-guard'}):
            with self.assertRaises(ContractError):self.prepare('export',actor='invented-sensitive-value-for-guard')

    def test_export_symlink_and_tampering_are_not_verified_downloads(self):
        self.label(self.h.ids[0]);result=self.finish(self.prepare('export'));eid=result['result']['output']['export_id']
        folder=self.project.root/self.project.config.data_directory/'asreview'/'exports'/eid
        original=folder/'dataset.csv';saved=folder/'preserved-original.csv';original.rename(saved)
        try:original.symlink_to(saved.name)
        except (OSError,NotImplementedError):
            saved.rename(original)
        else:
            with self.assertRaises(ContractError):self.app.download(self.project,eid,'dataset.csv')
            original.unlink();saved.rename(original)
        original.write_bytes(original.read_bytes()+b'changed')
        with self.assertRaises(ValueError):self.app.download(self.project,eid,'dataset.csv')

    def test_foreign_results_fail_without_membership_or_mapping_mutation(self):
        self.label(self.h.ids[0]);result=self.finish(self.prepare('export'));eid=result['result']['output']['export_id']
        body=b'corpustrail_paper_id,asreview_label\nct:foreign,1\n';uid=uuid.uuid4().hex
        self.app.upload(self.project,request_id=uid,offset=0,body=base64.b64encode(body).decode(),final=True,sha256='sha256:'+hashlib.sha256(body).hexdigest())
        before=self.project.reviews.membership(self.h.ids[0])
        op=self.prepare('mapping',export=eid,upload=uid,question='Invented question',review='Invented review',asreview_version='2.2')
        self.assertEqual(self.finish(op)['status'],'failed')
        self.assertEqual(before,self.project.reviews.membership(self.h.ids[0]))

    def test_cross_controller_reservation_blocks_duplicate_execution(self):
        self.configured();op=self.prepare('extraction',workflow='offline-task',paper=self.h.ids[0].split(':')[1],instructions='Synthetic gated request',predicates=['ct.organism_population'],mode='metadata')
        entered=threading.Event();release=threading.Event();invoke=self.wire.invoke
        def gated(*args,**kwargs):
            entered.set()
            if not release.wait(10):raise AssertionError('fixture release missing')
            return invoke(*args,**kwargs)
        other=HandoffController(model_service=lambda p:ModelService(p,registry=self.registry));self.addCleanup(other.close)
        try:
            with patch.object(self.wire,'invoke',side_effect=gated):
                self.app.execute(self.project,op['id'],preview_sha256=op['preview_sha256'],confirmed=True,confirm_external=True)
                self.assertTrue(entered.wait(10))
                with self.assertRaises(ContractError):other.execute(self.project,op['id'],preview_sha256=op['preview_sha256'],confirmed=True,confirm_external=True)
                release.set();self.app.close()
        finally:release.set()
        self.assertEqual(self.app.operation(self.project,op['id'])['status'],'complete')
        self.assertEqual(len(self.wire.calls),1)

    def test_editing_native_endpoint_preserves_unedited_supported_settings(self):
        from corpustrail.models.integrations import register_reference_adapters
        register_reference_adapters(self.registry)
        current=self.project.config
        self.project.configure(replace(current,config_version=current.config_version+1,
            models=(ModelConfig('local-characterization','compatible-endpoint','fixture-model',
                settings={'top_p':.9,'max_completion_tokens':512},adapter_configuration={'base_url':'http://127.0.0.1:9/v1','execution':'local','timeout_seconds':10}),)),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='reviewer')
        editable=self.app.configuration(self.project)['editable_models'][0];self.assertEqual(editable['max_tokens'],512)
        op=self.prepare('model_configuration',workflow='local-characterization',model='fixture-model',endpoint=editable['endpoint'],execution='local',
            credential_env='',temperature=0,max_tokens=1024,timeout=15,confirm_frozen=True)
        self.assertEqual(self.finish(op)['status'],'complete')
        self.assertEqual(self.project.config.models[0].settings,{'top_p':.9,'temperature':0,'max_completion_tokens':1024})
        self.assertEqual(self.wire.calls,[])


if __name__=='__main__':unittest.main()
