"""Protected localhost population API with real stores and scientific services."""
import json
import threading
import unittest
import uuid
from unittest.mock import patch

from corpustrail.application.populations import SCHEMA
from corpustrail.application.project_use import ProjectBusy, acquire_project_use
from corpustrail.errors import ContractError
from corpustrail.populations import PopulationService


class PopulationHttpTests(unittest.TestCase):
    def setUp(self):
        from test_guided_review import GuidedReviewHttpTests
        helper = GuidedReviewHttpTests();helper.setUp();self.addCleanup(helper.doCleanups)
        self.helper = helper;self.project = helper.project
        self.call = helper.request

    def fields(self):
        return {'schema':SCHEMA,'request_id':uuid.uuid4().hex,'name':'Frozen synthetic sources','actor':'configuration_author',
            'sources':[{'kind':'all'}],'parent':None}

    def preview(self, fields=None):
        fields = fields or self.fields()
        status,_,response = self.call('POST','/api/v1/populations/preview',fields)
        self.assertEqual(status,200,response)
        return fields,json.loads(response)['population']

    def test_page_navigation_and_read_api_have_no_scientific_writes(self):
        from test_populations import fingerprint
        before = fingerprint(self.project.root)
        status,headers,body = self.call('GET','/populations')
        self.assertEqual(status,200);self.assertIn('Candidate Populations',body)
        self.assertIn("default-src 'none'",headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin',headers)
        for path in ('/assets/populations.js','/api/v1/populations/configuration','/api/v1/populations/versions'):
            self.assertEqual(self.call('GET',path)[0],200)
        self.assertEqual(fingerprint(self.project.root),before)

    def test_host_origin_csrf_and_body_bounds(self):
        from test_populations import fingerprint
        before = fingerprint(self.project.root)
        for method,path,body,options in (
            ('GET','/populations',None,{'headers':{'Host':'attacker.invalid'}}),
            ('GET','/api/v1/populations/versions',None,{'auth':False}),
            ('GET','/api/v1/populations/versions',None,{'headers':{'Origin':'https://attacker.invalid'}}),
            ('POST','/api/v1/populations/create',self.fields(),{'auth':False}),
            ('POST','/api/v1/populations/preview',self.fields(),{'headers':{'Origin':'https://attacker.invalid'}})):
            self.assertEqual(self.call(method,path,body,**options)[0],403)
        self.assertEqual(self.call('POST','/api/v1/populations/preview',{'value':'x'*66000})[0],413)
        self.assertEqual(self.call('GET','/api/v1/populations/create')[0],404)
        self.assertEqual(fingerprint(self.project.root),before)

    def test_upgrade_is_bound_to_the_displayed_project_and_configuration(self):
        from test_populations import fingerprint
        status,_,body=self.call('GET','/api/v1/populations/configuration')
        self.assertEqual(status,200);config=json.loads(body)
        self.assertEqual(config['project_id'],self.project.config.project_id)
        before=fingerprint(self.project.root)
        request={'schema':SCHEMA,'request_id':uuid.uuid4().hex,'confirm_backup':True,
            'project_id':config['project_id'],'config_event_id':config['config_event_id']}
        for mismatch in ({'project_id':'another-project'},{'config_event_id':'stale'}):
            status,_,body=self.call('POST','/api/v1/populations/upgrade',{**request,**mismatch})
            self.assertEqual(status,409);self.assertIn('project selection or configuration changed',body)
            self.assertEqual(before,fingerprint(self.project.root))

    def test_preview_is_readonly_and_create_is_replay_safe(self):
        from test_populations import fingerprint
        before = fingerprint(self.project.root)
        fields,preview = self.preview()
        self.assertEqual(preview['member_count'],8);self.assertEqual(before,fingerprint(self.project.root))
        request = {**fields,'expected_preview_sha256':preview['preview_sha256'],'accept_unresolved':False}
        status,_,response = self.call('POST','/api/v1/populations/create',request)
        self.assertEqual(status,200,response)
        created = json.loads(response)['population'];before = fingerprint(self.project.root)
        status,_,replayed = self.call('POST','/api/v1/populations/create',request)
        self.assertEqual(status,200);self.assertTrue(json.loads(replayed)['population']['replayed'])
        self.assertEqual(before,fingerprint(self.project.root))
        handle = created['version_id'].split(':')[1]
        for section in ('','/members?limit=2','/lineage?limit=2','/issues'):
            self.assertEqual(self.call('GET','/api/v1/populations/versions/'+handle+section)[0],200)
        self.assertEqual(before,fingerprint(self.project.root))
        request['actor']='another actor'
        self.assertEqual(self.call('POST','/api/v1/populations/create',request)[0],409)
        self.assertEqual(before,fingerprint(self.project.root))

    def test_unknown_sources_paths_urls_and_fields_fail_closed(self):
        from test_populations import fingerprint
        before = fingerprint(self.project.root)
        for spec in ({'kind':'pdf','path':'/etc/passwd'},{'kind':'bibtex','url':'https://attacker.invalid'},
                     {'kind':'version','version_id':'../../other-project'},
                     {'kind':'import_interface'},{'kind':'all','authority_state':'human_authorized'}):
            status,_,body = self.call('POST','/api/v1/populations/preview',{**self.fields(),'sources':[spec]})
            self.assertEqual(status,409);self.assertNotIn(str(self.project.root),body)
        self.assertEqual(self.call('GET','/api/v1/populations/versions?limit=101')[0],400)
        self.assertEqual(self.call('GET','/api/v1/populations/versions?path=/etc/passwd')[0],400)
        self.assertEqual(self.call('GET','/api/v1/populations/versions/../../etc/passwd')[0],404)
        self.assertEqual(before,fingerprint(self.project.root))

    def test_frozen_version_review_uses_existing_authority_service(self):
        fields,preview = self.preview()
        created = json.loads(self.call('POST','/api/v1/populations/create',
            {**fields,'expected_preview_sha256':preview['preview_sha256'],'accept_unresolved':False})[2])['population']
        config = json.loads(self.call('GET','/api/v1/review/configuration')[2])
        request = {'schema':'corpustrail-guided-review/v1','command_id':uuid.uuid4().hex,'reviewer_id':'configuration_author',
            'selection':created['version_id'],'population_sha256':created['members_sha256'],
            'config_event_id':config['config_event_id'],'mode':'method-blind'}
        status,_,body = self.call('POST','/api/v1/review/create',request)
        self.assertEqual(status,200,body)
        handle = json.loads(body)['handle']
        view = json.loads(self.call('GET','/api/v1/review/sessions/'+handle)[2])
        self.assertFalse(view['can_publish']);self.assertEqual(view['total'],8)
        self.assertEqual(view['candidate_population']['version_id'],created['version_id'])
        self.assertNotIn(fields['name'],json.dumps(view));self.assertTrue(all(not self.project.reviews.history(p) for p in self.project.identities.papers()))

    def test_population_write_lease_blocks_close_and_exclusive_removal(self):
        fields,preview = self.preview()
        request = {**fields,'expected_preview_sha256':preview['preview_sha256'],'accept_unresolved':False}
        entered=threading.Event();release=threading.Event();closed=threading.Event();responses=[]
        original=PopulationService._prepare
        def gated(service,*args,**kwargs):
            entered.set()
            if not release.wait(5):raise ContractError('controlled fixture timeout')
            return original(service,*args,**kwargs)
        with patch.object(PopulationService,'_prepare',gated):
            worker=threading.Thread(target=lambda:responses.append(self.call('POST','/api/v1/populations/create',request)))
            closer=threading.Thread(target=lambda:(self.helper.controller.close(),closed.set()))
            try:
                worker.start();self.assertTrue(entered.wait(3));closer.start();self.assertFalse(closed.wait(.05))
                with self.assertRaises(ProjectBusy):acquire_project_use(self.project.root,exclusive=True)
            finally:
                release.set();worker.join(10);closer.join(10)
        self.assertEqual(responses[0][0],200);self.assertTrue(closed.is_set())
        with acquire_project_use(self.project.root,exclusive=True):pass
