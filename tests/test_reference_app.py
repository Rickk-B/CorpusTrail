"""Real protected reference HTTP operations, not mocked scientific results."""
import json
import unittest
import uuid
from dataclasses import asdict

from corpustrail.application.references import SCHEMA
from corpustrail.references import ContextStrategy
from test_references import change,AT


class ReferenceHttpTests(unittest.TestCase):
    def setUp(self):
        from test_guided_review import GuidedReviewHttpTests
        helper=GuidedReviewHttpTests();helper.setUp();self.addCleanup(helper.doCleanups)
        self.helper=helper;self.project=helper.project;self.call=helper.request
        self.ids=self.project.identities.papers()

    def fields(self):
        return {'schema':SCHEMA,'request_id':uuid.uuid4().hex,'name':'Synthetic reference truth','actor':'curator',
            'parent':None,'changes':[change(p) for p in self.ids[:3]],'created_at':AT,
            'config_event_id':self.project.configuration_history()[-1]['event_id']}

    def preview(self,fields=None):
        fields=fields or self.fields();status,_,response=self.call('POST','/api/v1/references/preview',fields)
        self.assertEqual(status,200,response);return fields,json.loads(response)['reference']

    def commit(self):
        fields,preview=self.preview();command={**fields,'expected_preview_sha256':preview['preview_sha256']}
        status,_,response=self.call('POST','/api/v1/references/commit',command)
        self.assertEqual(status,200,response);return json.loads(response)['reference'],command

    def test_workspace_and_readonly_preview_preserve_scientific_state(self):
        from test_populations import fingerprint
        before=fingerprint(self.project.root)
        for path in ('/references','/assets/references.js','/api/v1/references/configuration',
                     '/api/v1/references/versions','/api/v1/references/contexts'):
            status,headers,body=self.call('GET',path);self.assertEqual(status,200,body)
            self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.preview();self.assertEqual(before,fingerprint(self.project.root))

    def test_explicit_attestation_bad_types_and_cross_origin_are_rejected(self):
        from test_populations import fingerprint
        before=fingerprint(self.project.root);fields=self.fields()
        for bad in ({'human_attested':False},{'producer':{'type':'model','id':'curator','version':'manual/v1'}}):
            self.assertEqual(self.call('POST','/api/v1/references/preview',{**fields,'changes':[{**fields['changes'][0],**bad}]})[0],409)
        for bad in (['not an assignment'],[],fields['changes']*10):
            self.assertEqual(self.call('POST','/api/v1/references/preview',{**fields,'changes':bad})[0],409)
        self.assertEqual(self.call('POST','/api/v1/references/commit',fields,auth=False)[0],403)
        self.assertEqual(self.call('GET','/api/v1/references/versions',headers={'Origin':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.call('POST','/api/v1/references/preview',{'data':'x'*66000})[0],413)
        secret='Bearer synthetic-private-value'
        status,_,response=self.call('POST','/api/v1/references/preview',{**fields,'actor':secret})
        self.assertEqual(status,409);self.assertNotIn(secret,response)
        self.assertEqual(before,fingerprint(self.project.root))

    def test_commit_replay_bounded_pages_and_context_input_persist(self):
        from test_populations import fingerprint
        created,command=self.commit();vid=created['version_id'].split(':')[1]
        before=fingerprint(self.project.root)
        status,_,replay=self.call('POST','/api/v1/references/commit',command)
        self.assertEqual(status,200);self.assertTrue(json.loads(replay)['reference']['replayed'])
        first=json.loads(self.call('GET','/api/v1/references/versions/'+vid+'/members?limit=2')[2])
        self.assertEqual(len(first['items']),2);self.assertEqual(first['next_offset'],2)
        aid=first['items'][0]['assignment_id'].split(':')[1]
        status,_,body=self.call('GET','/api/v1/references/versions/'+vid+'/assignments/'+aid)
        self.assertEqual(status,200,body);self.assertTrue(json.loads(body)['assignment']['human_attested'])
        self.assertEqual(self.call('GET','/api/v1/references/versions?limit=101')[0],400)
        self.assertEqual(self.call('GET','/api/v1/references/versions?label=in_scope')[0],400)
        self.assertEqual(self.call('GET','/api/v1/references/versions?cutoff=99999')[0],400)
        self.assertEqual(before,fingerprint(self.project.root))
        context={'schema':SCHEMA,'request_id':uuid.uuid4().hex,'version_id':created['version_id'],'actor':'curator','created_at':AT,
            'config_event_id':command['config_event_id'],'target_paper_id':self.ids[0],'target_basis':'metadata',
            'held_out_paper_ids':[],'held_out_population_version':None,'strategy':asdict(ContextStrategy()),'dependency_ids':[]}
        status,_,body=self.call('POST','/api/v1/references/context_preview',context)
        self.assertEqual(status,200,body);preview=json.loads(body)
        self.assertIn('input',preview);self.assertNotIn('held_out_paper_ids',preview)
        self.assertEqual(before,fingerprint(self.project.root))
        status,_,body=self.call('POST','/api/v1/references/context_commit',{**context,'expected_preview_sha256':preview['preview_sha256']})
        self.assertEqual(status,200,body);cid=json.loads(body)['context_id'].split(':')[1]
        detail=json.loads(self.call('GET','/api/v1/references/contexts/'+cid+'?limit=1')[2])
        self.assertEqual(len(detail['items']),1);self.assertEqual(detail['input'],preview['input'])
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))

    def test_references_remain_outside_method_blind_review_dtos(self):
        self.commit()
        config=json.loads(self.call('GET','/api/v1/review/configuration')[2])
        body={'schema':'corpustrail-guided-review/v1','command_id':uuid.uuid4().hex,'reviewer_id':'configuration_author',
            'selection':'all','population_sha256':config['populations'][0]['sha256'],
            'config_event_id':config['config_event_id'],'mode':'method-blind'}
        # The configuration DTO's population ordering is not an authority rule.
        body['selection']=config['populations'][0]['selection']
        status,_,response=self.call('POST','/api/v1/review/create',body)
        self.assertEqual(status,200,response)
        session=json.loads(response)['handle'];view=self.call('GET','/api/v1/review/sessions/'+session)[2]
        self.assertNotIn('Synthetic reference truth',view);self.assertNotIn('reference-assignment:',view)
        self.assertNotIn('Invented reference judgment',view)

    def test_upgrade_rejects_stale_selection_without_backup_or_write(self):
        from test_populations import fingerprint
        before=fingerprint(self.project.root)
        request={'schema':SCHEMA,'request_id':uuid.uuid4().hex,'confirm_backup':True,
            'project_id':'another-project','config_event_id':self.fields()['config_event_id']}
        self.assertEqual(self.call('POST','/api/v1/references/upgrade',request)[0],409)
        self.assertEqual(before,fingerprint(self.project.root))
