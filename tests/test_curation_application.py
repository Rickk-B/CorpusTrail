"""Real assisted HTTP boundary, explicit commands and restart-safe CP9 lists."""
import http.client
import json
import re
import threading
import unittest
import uuid
from unittest.mock import patch

from corpustrail._internal.database import connection
from corpustrail._internal.values import ContractError, content_hash
from corpustrail.application.curation import CurationController, SCHEMA
from corpustrail.application.projects import ProjectController
from corpustrail.application.review import _handle
from corpustrail.classification import ClassifierPolicy, ValidationProtocol
from corpustrail.curation.guided import GuidedReviewService
from corpustrail.local_app import make_server


class CurationApplicationTests(unittest.TestCase):
    def setUp(self):
        from test_curation_workflow import CurationWorkflowTests
        helper = CurationWorkflowTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        self.h = helper; self.project = helper.project
        self.app = CurationController(registry=helper.h.registry, synthetic=True, clock=lambda:'2026-01-01T00:00:00+00:00')
        self.addCleanup(self.app.close)
        guard = patch('corpustrail.application.project_use.lock_directory', return_value=self.project.root.parent/'locks')
        guard.start(); self.addCleanup(guard.stop)
        self.controller = ProjectController(projects_root=self.project.root.parent, project=self.project)
        self.addCleanup(self.controller.close)
        self.server = make_server(controller=self.controller, curation=self.app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        self.origin = 'http://127.0.0.1:'+str(self.server.server_port)
        _, raw = self.request('GET','/curation',auth=False)
        self.token = re.search('name="corpustrail-session" content="([^"]+)"',raw).group(1)

    def close(self):
        self.server.shutdown(); self.thread.join(10); self.server.server_close()

    def request(self, method, path, body=None, *, auth=True):
        client = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            headers = {'Origin':self.origin}
            if auth: headers.update({'X-CorpusTrail-Session':self.token,'X-CorpusTrail-CSRF':self.token})
            if body is not None: headers['Content-Type']='application/json'
            client.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
            response=client.getresponse(); return response.status,response.read().decode()
        finally: client.close()

    def get(self,path):
        status,raw=self.request('GET','/api/v1/'+path)
        self.assertEqual(status,200,raw);return json.loads(raw)

    def post(self,action,fields,status=200):
        code,raw=self.request('POST','/api/v1/curation/'+action,{'schema':SCHEMA,**fields})
        self.assertEqual(code,status,raw);return json.loads(raw)

    def test_open_and_inspection_are_read_only_and_methods_do_not_claim_real_models(self):
        from test_populations import fingerprint
        before=fingerprint(self.project.root)
        data=self.get('curation/configuration')
        self.assertFalse(data['default_engine_selected']);self.assertTrue(data['methods'][0]['available'])
        self.assertTrue(any(x.get('synthetic_example') for x in data['methods']))
        self.assertEqual([x for x in data['methods'] if x['id']=='external_llm'][0]['available'],False)
        run=self.h.run.split(':')[1];paper=self.h.ids[0].split(':')[1]
        self.get('curation/runs');self.get('curation/history');self.get('curation/audits')
        self.get('curation/runs/'+run);self.get('curation/runs/'+run+'/results')
        for section in ('target','references','provenance'):
            self.get('curation/runs/'+run+'/papers/'+paper+'?section='+section+'&limit=10')
        self.assertEqual(before,fingerprint(self.project.root))
        default=CurationController();self.addCleanup(default.close)
        self.assertFalse(any(x['available'] and x['id']!='manual' for x in default.configuration(self.project)['methods']))

    def test_assisted_and_method_blind_routes_cannot_be_swapped(self):
        audit=self.h.audit();sid=self.h.review(audit);handle=_handle(sid)
        value=self.get('curation/review/sessions/'+handle)
        self.assertIn('assisted_sources',value);self.assertEqual(value['mode'],'operational')
        for suffix in ('','/summary','/document'):
            code,_=self.request('GET','/api/v1/review/sessions/'+handle+suffix)
            self.assertNotEqual(code,200)
        blind=GuidedReviewService(self.project).create(reviewer_id='curator',selection='all',
            population_sha256=content_hash(sorted(self.project.identities.papers())),
            config_event_id=self.h.revision,mode='method-blind',command_id=uuid.uuid4().hex)
        blind_handle=_handle(blind['session_id'])
        data=self.get('review/sessions/'+blind_handle)
        self.assertNotIn('assisted_sources',data);self.assertNotIn('source_provenance',data)
        code,_=self.request('GET','/api/v1/curation/review/sessions/'+blind_handle)
        self.assertNotEqual(code,200)
        listing=self.get('review/configuration')
        self.assertNotIn(handle,[x['handle'] for x in listing['sessions']])

    def test_repeated_http_save_is_one_observation_with_atomic_assessment_lineage(self):
        audit=self.h.audit();sid=self.h.review(audit);view=self.app.assisted(self.project,_handle(sid))
        command={'handle':_handle(sid),'command_id':uuid.uuid4().hex,'expected_revision':view['revision'],
            'action':'save_next','value':dict(sufficiency='insufficient',decision=None,review_extent='metadata',rationale='Explicit human uncertainty.')}
        a=self.post('review/command',command);b=self.post('review/command',command)
        self.assertEqual(a['revision'],b['revision']);self.assertEqual(len(self.h.service.outcomes(audit['audit_id'])['items']),1)
        selected=self.get('curation/audits/'+audit['audit_id'].split(':')[1])
        self.assertTrue(selected['items'][0]['publication']['bibliography']['title'])
        outcome=self.get('curation/audits/'+audit['audit_id'].split(':')[1]+'/outcomes')['items'][0]
        self.assertEqual(outcome['human_observation']['state'],'insufficient_evidence')
        self.assertEqual(outcome['human_observation']['authority_state'],'non_authoritative')
        self.assertTrue(all(self.project.reviews.membership(pid)['state']=='not_reviewed' for pid in self.h.ids))

    def test_bounded_queries_and_authentication_fail_closed(self):
        run=self.h.run.split(':')[1]
        for query in ('limit=101','overlay=anything','compare='+run,'offset=1','cutoff=1'):
            status,_=self.request('GET','/api/v1/curation/runs/'+run+'/results?'+query)
            self.assertNotEqual(status,200)
        self.assertEqual(self.request('GET','/api/v1/curation/configuration',auth=False)[0],403)
        self.post('execute',{'run_id':self.h.run,'expected_revision':'invented'},status=409)
        self.post('plan_preview',{'arbitrary_url':'https://example.invalid'},status=409)

    def test_append_only_list_cutoffs_preserve_pages_across_new_records(self):
        first=self.h.audit();second=self.h.audit()
        page=self.h.service.audits(limit=1)
        self.h.audit()
        next_page=self.h.service.audits(offset=1,limit=1,cutoff=page['cutoff'])
        self.assertEqual(next_page['items'][0]['audit_id'],first['audit_id'])
        self.assertEqual(page['items'][0]['audit_id'],second['audit_id'])
        with self.assertRaises(ContractError):self.h.service.audits(offset=1)
        self.assertEqual(self.get('curation/audits?offset=1&limit=1&cutoff='+str(page['cutoff']))['items'],next_page['items'])

    def test_reassessment_plan_inherits_explicit_policy_and_validation_not_fresh_evaluation(self):
        parent=self.h.h.plan(policy=ClassifierPolicy(policy_id='explicit-fixture-policy',uncertainty_rule='Fixture uncertainty remains explicit.'))
        rid=self.h.h.start(parent['plan_id'])
        fields={**self.h.h.fields(),'parent_run_id':rid,'input_mode':'full_set','context_ids':[]}
        old=self.app.classifier(self.project).inspect_plan(parent['plan_id'])
        preview=self.post('plan_preview',fields)
        self.assertEqual(preview['policy'],old['policy'])
        saved=self.post('plan_commit',{**fields,'expected_preview_sha256':preview['preview_sha256']})
        service=self.app.classifier(self.project)
        self.assertEqual(service.validation_protocol(saved['plan_id'])['protocol'],service.validation_protocol(parent['plan_id'])['protocol'])
        self.assertEqual(self.h.h.engine.calls,1)

    def test_frozen_migration_bytes_and_rollback_guard_remain_effective(self):
        with connection(self.project.database_path) as db:
            self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0],41)
        self.assertTrue(self.h.service.verify_audit(self.h.audit()['audit_id'])['verified'])

    def test_operational_results_cannot_masquerade_as_independent_validation(self):
        self.post('validate',{'run_id':self.h.run},status=409)
        self.assertEqual(self.get('curation/runs/'+self.h.run.split(':')[1]+'/validations')['total'],0)

    def test_worker_cleanup_cannot_overtake_the_lifecycle_status_read(self):
        service=self.h.h.service;original=service.inspect_run
        inspecting=threading.Event();release=threading.Event();attempted=threading.Event();removed=threading.Event()
        key=(str(self.project.root),self.h.run);self.app._workers[key]=(threading.current_thread(),threading.Event())
        values=[]
        def inspect(rid):
            value=original(rid);inspecting.set()
            if not release.wait(5):raise AssertionError('controlled status read was not released')
            return {**value,'status':'running'}
        def cleanup():
            attempted.set()
            with self.app._lock:self.app._workers.pop(key,None);removed.set()
        with patch.object(self.app,'classifier',return_value=service),patch.object(service,'inspect_run',side_effect=inspect):
            reader=threading.Thread(target=lambda:values.append(self.app.run(self.project,self.h.run)))
            reader.start();self.assertTrue(inspecting.wait(5))
            finisher=threading.Thread(target=cleanup);finisher.start();self.assertTrue(attempted.wait(5))
            try:self.assertFalse(removed.wait(.05),'cleanup overtook the lifecycle read')
            finally:release.set();reader.join(5);finisher.join(5)
        self.assertEqual(len(values),1);self.assertTrue(values[0]['local_worker_active'])
        self.assertTrue(removed.is_set())

    def test_frozen_validation_reports_preserve_denominators_and_role_qualification(self):
        plan=self.h.h.plan(validation=ValidationProtocol(purpose='held_out_evaluation',held_out_population_version=self.h.h.pop,
            label_cutoff='2026-01-01T00:00:00+00:00'))
        run=self.h.h.start(plan['plan_id']);self.h.h.execute(run)
        result=self.post('validate',{'run_id':run})
        self.assertFalse(result['scientific_performance_claim']);self.assertEqual(result['result_count'],3)
        self.assertNotIn('result_ids',result)
        self.assertEqual(sum(sum(row.values()) for row in result['matrix'].values()),3)
        self.assertEqual(result['known_inclusion_recall']['denominator']+result['known_exclusion_specificity']['denominator'],3)
        saved=self.get('curation/runs/'+run.split(':')[1]+'/validations')
        self.assertEqual(saved['items'][0]['validation_id'],result['validation_id'])
        self.assertIn('Sparse or synthetic',result['qualification'])


if __name__=='__main__':unittest.main()
