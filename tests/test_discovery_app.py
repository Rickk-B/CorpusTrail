"""Offline exact-plan application acceptance; no scholarly endpoint is contacted."""
from dataclasses import replace
import concurrent.futures
from importlib import resources
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from corpustrail.application.discovery import DiscoveryController, SCHEMA, BOUNDS
from corpustrail.application import _workflow_files as files
from corpustrail.application.projects import ProjectController, ProjectCommandError
from corpustrail.application.project_use import acquire_project_use, ProjectBusy
from corpustrail.discovery import SearchPlan
from corpustrail.curation import EvidenceBasis, ReviewEvent
from corpustrail.local_app import make_server
from corpustrail.project import Project, ProjectConfig, ProviderConfig, SearchConcept, ReviewPolicy
from corpustrail.providers.network import HttpResponse

OA = {'results': [
    {'id':'https://openalex.org/W1','doi':'10.1234/discovery.1','title':'Synthetic porous ceramic'},
    {'id':'https://openalex.org/W2','title':'Synthetic porous ceramic'},
    {'id':'https://openalex.org/W3','doi':'10.1234/discovery.2','title':'Synthetic porous ceramics'}],
    'meta':{'count':3,'next_cursor':None}}
CR = {'message':{'items':[
    {'DOI':'10.1234/discovery.1','title':['Synthetic porous ceramic']},
    {'DOI':'10.1234/discovery.3','title':['Invented glass study']},
    {'DOI':'10.1234/discovery.4','title':['Invented metals study']}], 'total-results':3}}


def fingerprint(path):
    return {str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file()}


class Transport:
    network = False
    def __init__(self):
        self.calls=[]; self.fail_crossref=False; self.block=None; self.entered=threading.Event()
        self.responses=[]
    def request(self,url,**kwargs):
        self.calls.append((url,kwargs)); self.entered.set()
        if self.block is not None: self.block.wait(20)
        if self.responses:
            response=self.responses.pop(0)
            if isinstance(response,Exception): raise response
            status,body,headers=response
        else:
            status=503 if self.fail_crossref and 'crossref' in url else 200
            body=CR if 'crossref' in url else OA; headers={}
        return HttpResponse(status,headers,json.dumps(body).encode('utf-8'),url)


class DiscoveryFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ct-discovery-disposable-'); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve(); self.root=self.base/'projects'/'materials'
        self.project=Project.create(self.root,ProjectConfig('discovery-fixture','Invented materials','Synthetic scope',
            providers=tuple(ProviderConfig(x,x) for x in ('openalex','crossref','europepmc','semantic_scholar')),
            search=(SearchConcept('ceramic','porous ceramic'),)),created_by='fixture')
        self.locks=self.base/'locks'
        p=patch('corpustrail.application.project_use.lock_directory',return_value=self.locks);p.start();self.addCleanup(p.stop)
        self.controller=ProjectController(projects_root=self.root.parent,project=self.project);self.addCleanup(self.controller.close)
        self.transport=Transport();self.manager=DiscoveryController(self.controller,transport_factory=lambda:self.transport)
        self.addCleanup(self.stop_workers)
    def stop_workers(self):
        if self.transport.block:self.transport.block.set()
        self.manager.close()
        for thread,_ in list(self.manager._workers.values()):thread.join(25)
    def prepare(self,providers=None,request_id='prepare-command',**overrides):
        args={'request_id':request_id,'config_event_id':self.project.configuration_history()[-1]['event_id'],
              'query':'porous ceramic','providers':providers or ['openalex','crossref'],'bounds':dict(BOUNDS)}
        args.update(overrides);return self.manager.prepare(self.project,**args)
    def approve(self,preview,request_id='approve-command'):
        return self.manager.approve(self.project,handle=preview['handle'],request_id=request_id,
            preview_nonce=preview['preview_nonce'],confirm_external=True,approve_identities=True)
    def wait(self,handle):
        for _ in range(400):
            value=self.manager.inspect(self.project,handle)
            if value['status'] not in ('running','queued'):return value
            time.sleep(.025)
        self.fail('disposable discovery did not finish')
    def execute_run(self,preview,request_id='start-command'):
        self.approve(preview);self.manager.start(self.project,handle=preview['handle'],request_id=request_id)
        return self.wait(preview['handle'])


class DiscoveryWorkflowTests(DiscoveryFixture):
    def test_all_four_adapter_previews_are_explicit_and_network_free(self):
        p=self.prepare(['openalex','crossref','europepmc','semantic_scholar'])
        expected={'openalex':'search','crossref':'query.bibliographic','europepmc':'query','semantic_scholar':'query'}
        for child in p['plan']['providers']:
            params={x['name']:x['value'] for x in child['request_preview']['parameters']}
            self.assertEqual(params[expected[child['provider']]],p['plan']['query'])
            self.assertIn(child['request_preview']['cursor_parameter'],params)
        self.assertEqual(self.transport.calls,[])
    def test_prepare_approve_reads_no_network_or_scientific_database_mutation(self):
        before=self.project.database_path.read_bytes(); config=self.project.configuration_history()
        p=self.prepare();self.assertEqual(p['status'],'prepared');self.approve(p)
        snapshot=fingerprint(self.root)
        self.manager.inspect(self.project,p['handle']);self.manager.history(self.project);self.manager.configuration(self.project)
        self.assertEqual(snapshot,fingerprint(self.root));self.assertEqual(before,self.project.database_path.read_bytes())
        self.assertEqual(config,self.project.configuration_history());self.assertEqual(self.transport.calls,[])
        for child in p['plan']['providers']:
            from corpustrail.providers import metadata_provider
            plan=SearchPlan(**child['plan'])
            self.assertEqual(child['plan_id'],plan.plan_id)
            self.assertEqual(child['request_preview']['initial_request']['url'],metadata_provider(child['provider']).request(plan,None).url)
    def test_six_observations_five_publications_exact_repeat_no_membership(self):
        p=self.prepare();a=self.execute_run(p)
        self.assertEqual(a['status'],'completed');self.assertEqual(a['summary']['observations_preserved'],6)
        self.assertEqual(a['summary']['unique_publications'],5);self.assertEqual(a['summary']['publications_created_by_run'],5)
        self.assertEqual(len(self.project.identities.papers()),5)
        for pid in self.project.identities.papers():self.assertEqual(self.project.reviews.membership(pid)['state'],'not_reviewed')
        original=files.read(files.location(self.project)/'plans'/(p['handle']+'.json'))
        from corpustrail._internal.pipeline import events
        for child in p['plan']['providers']:
            self.assertEqual(events(self.project,kind='discovery_plan',scope_id=child['plan']['run_id'])[0]['payload'],child['plan'])
        self.manager.start(self.project,handle=p['handle'],request_id='start-command')
        self.assertEqual(len(self.transport.calls),2)
        with self.assertRaises(ProjectCommandError):self.manager.start(self.project,handle=p['handle'],request_id='other-start-command')
        b=self.prepare(request_id='repeat-prepare-command');self.approve(b,request_id='repeat-approve-command')
        self.manager.start(self.project,handle=b['handle'],request_id='repeat-start-command');b=self.wait(b['handle'])
        self.assertEqual(b['summary']['unique_publications'],5);self.assertEqual(b['summary']['previously_known_publications'],5)
        self.assertEqual(b['summary']['publications_created_by_run'],0);self.assertEqual(len(self.project.discovery.observations()),12)
        self.assertEqual(len(self.project.identities.papers()),5)
        self.assertEqual(original,files.read(files.location(self.project)/'plans'/(p['handle']+'.json')))
        page=self.manager.papers(self.project,p['handle'],limit=2)
        self.assertEqual(len(page['items']),2);self.assertIsNotNone(page['next_offset'])
        for item in page['items']:self.assertTrue(item['url'].startswith('/papers/'));self.assertNotIn('raw_record',item)
        events=self.manager.provenance(self.project,p['handle'],provider='openalex',limit=2)
        self.assertEqual(len(events['items']),2);self.assertIsNotNone(events['next_offset'])
    def test_subset_partial_failure_preserves_records_and_explicit_repeat(self):
        self.transport.fail_crossref=True;p=self.prepare();result=self.execute_run(p)
        self.assertEqual(result['status'],'partial');self.assertEqual(result['summary']['observations_preserved'],3)
        self.assertEqual(len(self.project.identities.papers()),3)
        self.assertEqual([x['status'] for x in result['providers']],['completed','failed'])
        self.assertEqual(len(self.transport.calls),2)
        self.manager.inspect(self.project,p['handle']);self.manager.history(self.project);self.assertEqual(len(self.transport.calls),2)
    def test_rediscovery_preserves_existing_reviews_membership_evidence_and_frozen_session(self):
        config=self.project.config
        self.project.configure(replace(config,config_version=2,review=ReviewPolicy(authorized_reviewers=('fixture_reviewer',))),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
        self.execute_run(self.prepare())
        ids=self.project.identities.papers();pid=ids[0]
        source=self.project.identities.observations(pid)[0]['source']
        event=ReviewEvent(pid,'included','sufficient','metadata','Synthetic human attestation','fixture_reviewer',
            '2026-01-01T00:00:00+00:00',
            (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
            authority_state='human_authorized')
        self.project.reviews.apply(self.project.reviews.plan(event))
        self.project.evidence.preserve_document(pid,b'<article><body>Invented unidentified text</body></article>',
            representation='jats_xml',media_type='application/xml',source_uri='fixture://unidentified-document',
            legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='1')
        self.project.review_sessions.prepare('frozen-fixture',reviewer_id='fixture_reviewer',paper_ids=ids)
        view=self.project.review_sessions.view('frozen-fixture')
        self.project.review_sessions.update('frozen-fixture',expected_revision=view['revision'],action='draft',
            value={'sufficiency':'sufficient','decision':'included','review_extent':'metadata','rationale':'Synthetic saved draft'})
        def preserved():
            return (self.project.configuration_history(),
                    [self.project.reviews.history(p) for p in ids],
                    [self.project.reviews.membership(p) for p in ids],
                    [self.project.evidence.representations(p) for p in ids],
                    self.project.review_sessions.view('frozen-fixture'))
        before=preserved()
        preview=self.prepare(request_id='preservation-repeat-prepare')
        self.approve(preview,request_id='preservation-repeat-approve')
        self.manager.start(self.project,handle=preview['handle'],request_id='preservation-repeat-start')
        result=self.wait(preview['handle'])
        self.assertEqual(result['status'],'completed');self.assertEqual(result['summary']['previously_known_publications'],5)
        self.assertEqual(before,preserved());self.assertEqual(len(self.project.identities.papers()),5)
        self.assertEqual(self.project.evidence.representations(pid)[0]['payload']['artifact_validity'],'pending_identity')
    def test_query_settings_and_consent_revision_validation(self):
        for args in ({'query':''},{'providers':['unknown']},{'providers':['openalex','openalex']},{'bounds':{'date':'2020'}},
                     {'bounds':{**BOUNDS,'page_size':True}}, {'config_event_id':'old-revision'}):
            with self.subTest(args=args),self.assertRaises((ProjectCommandError,ValueError,TypeError)):self.prepare(**args)
        p=self.prepare(['openalex'])
        with self.assertRaises(ProjectCommandError):self.manager.start(self.project,handle=p['handle'],request_id='no-approval-start')
        for consent in (False,None):
            with self.assertRaises(ProjectCommandError):self.manager.approve(self.project,handle=p['handle'],request_id='no-consent-'+str(consent),
                preview_nonce=p['preview_nonce'],confirm_external=consent,approve_identities=True)
        with self.assertRaises(ProjectCommandError):self.manager.approve(self.project,handle=p['handle'],request_id='forged-preview-command',
                preview_nonce='forged',confirm_external=True,approve_identities=True)
        self.approve(p);self.manager.invalidate(self.project,handle=p['handle'])
        with self.assertRaises(ProjectCommandError):self.manager.start(self.project,handle=p['handle'],request_id='invalidated-start')
        p=self.prepare(request_id='another-preparation');self.approve(p,request_id='another-approval')
        config=self.project.config
        self.project.configure(replace(config,config_version=config.config_version+1,name='Updated project'),
            expected_event_id=p['plan']['config_event_id'],created_by='fixture')
        with self.assertRaises(ProjectCommandError):self.manager.start(self.project,handle=p['handle'],request_id='stale-plan-start')
        self.assertEqual(self.manager.inspect(self.project,p['handle'])['plan'],p['plan']);self.assertEqual(self.transport.calls,[])
    def test_credentials_presence_no_persistence_and_remote_error_redaction(self):
        config=self.project.config
        self.project.configure(replace(config,config_version=2,providers=(ProviderConfig('openalex','openalex','CT_TEST_CREDENTIAL'),)),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
        status=self.manager.configuration(self.project)['providers'][0];self.assertFalse(status['ready'])
        with self.assertRaises(ProjectCommandError):self.prepare(['openalex'])
        secret='synthetic-private-credential-12345'
        with patch.dict(os.environ,{'CT_TEST_CREDENTIAL':secret}):
            self.assertTrue(self.manager.configuration(self.project)['providers'][0]['credential_present'])
            p=self.prepare(['openalex']);result=self.execute_run(p)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(self.transport.calls[0][1]['headers']['Authorization'],'Bearer '+secret)
            for raw in fingerprint(self.root).values():self.assertNotIn(secret.encode(),raw)
            with self.assertRaises(ValueError):self.prepare(['openalex'],request_id='bad-secret-query',query=secret)
            self.transport.responses=[(401,{'echo':secret},{})]
            p=self.prepare(['openalex'],request_id='echo-prepare-command');self.approve(p,request_id='echo-approve-command')
            self.manager.start(self.project,handle=p['handle'],request_id='echo-start-command');result=self.wait(p['handle'])
            self.assertEqual(result['status'],'failed')
            for raw in fingerprint(self.root).values():self.assertNotIn(secret.encode(),raw)
            self.assertNotIn(secret,json.dumps(result))
    def test_timeouts_rate_limits_bounded_retry_and_runtime_cursor(self):
        self.transport.responses=[(429,{}, {'Retry-After':'0'}),(200,{**OA,'meta':{'next_cursor':'cursor/next+value','count':6}},{}),(200,OA,{})]
        p=self.prepare(['openalex'],bounds={**BOUNDS,'max_pages':2,'max_attempts':2,'retry_delay_seconds':0})
        result=self.execute_run(p);self.assertEqual(result['status'],'completed');self.assertEqual(len(self.transport.calls),3)
        self.assertIn('cursor%2Fnext%2Bvalue',self.transport.calls[-1][0])
        self.assertEqual(result['summary']['observations_preserved'],6)
        self.transport.responses=[TimeoutError('untrusted remote details')]
        p=self.prepare(['openalex'],request_id='timeout-prepare');self.approve(p,request_id='timeout-approve')
        self.manager.start(self.project,handle=p['handle'],request_id='timeout-start');result=self.wait(p['handle'])
        self.assertEqual(result['status'],'failed');self.assertNotIn('untrusted remote details',json.dumps(result))
    def test_malformed_response_and_exact_identifier_conflicts_remain_inspectable(self):
        self.transport.responses=[(200,{'unexpected':'shape'}, {})]
        p=self.prepare(['openalex']);result=self.execute_run(p)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['providers'][0]['completion']['outcome'],'malformed_response')
        p=self.prepare(request_id='seed-prepare');self.approve(p,request_id='seed-approve')
        self.manager.start(self.project,handle=p['handle'],request_id='seed-start');self.wait(p['handle'])
        self.transport.responses=[(200,{'results':[{'id':'https://openalex.org/W1','doi':'10.1234/discovery.2','title':'Unchanged similar title'}],
            'meta':{'next_cursor':None,'count':1}}, {})]
        p=self.prepare(['openalex'],request_id='conflict-prepare');self.approve(p,request_id='conflict-approve')
        self.manager.start(self.project,handle=p['handle'],request_id='conflict-start');result=self.wait(p['handle'])
        self.assertEqual(result['summary']['observations_not_linked'],1);self.assertEqual(result['summary']['unique_publications'],0)
        self.assertEqual(len(self.project.identities.papers()),5)
        from corpustrail._internal.pipeline import events
        self.assertTrue(events(self.project,kind='identity_issue'))
    def test_worker_lease_survives_controller_close_and_cancel_boundary(self):
        self.transport.block=threading.Event();p=self.prepare();self.approve(p)
        self.manager.start(self.project,handle=p['handle'],request_id='blocking-start-command')
        self.assertTrue(self.transport.entered.wait(5));self.controller.close()
        with self.assertRaises(ProjectBusy):acquire_project_use(self.root,exclusive=True)
        before=fingerprint(self.root);self.manager.inspect(self.project,p['handle']);self.assertEqual(before,fingerprint(self.root))
        self.manager.cancel(self.project,handle=p['handle']);self.transport.block.set()
        result=self.wait(p['handle']);self.assertEqual(result['status'],'cancelled');self.assertEqual(len(self.transport.calls),1)
        for _ in range(100):
            try:
                with acquire_project_use(self.root,exclusive=True):break
            except ProjectBusy:time.sleep(.01)
        else:self.fail('worker did not release use')
    def test_expired_approval_thread_start_failure_and_provider_changes_fail_closed(self):
        p=self.prepare(['openalex'])
        token=self.manager._previews[p['preview_nonce']]
        self.manager._previews[p['preview_nonce']]=(*token[:2],0,token[3])
        with self.assertRaises(ProjectCommandError):self.approve(p)
        p=self.prepare(['openalex'],request_id='valid-preview-command');self.approve(p,request_id='valid-approval-command')
        with patch('corpustrail.application.discovery._implementation_hash',return_value='sha256:'+'0'*64):
            with self.assertRaises(ProjectCommandError):self.manager.start(self.project,handle=p['handle'],request_id='changed-adapter-command')
        with patch('threading.Thread.start',side_effect=RuntimeError('untrusted startup details')):
            with self.assertRaises(ProjectCommandError):self.manager.start(self.project,handle=p['handle'],request_id='startup-failure-command')
        self.assertEqual(self.manager.inspect(self.project,p['handle'])['status'],'interrupted')
        self.assertEqual(self.manager._workers,{})
        self.assertEqual(self.transport.calls,[])
    def test_foreign_scientific_run_binding_is_not_attributed_to_prepared_plan(self):
        from corpustrail._internal.pipeline import append
        p=self.prepare(['openalex'])
        child=p['plan']['providers'][0]
        foreign={**child['plan'],'query':'different scientific query'}
        append(self.project,'discovery_plan',child['plan']['run_id'],foreign)
        with self.assertRaises(ProjectCommandError):self.approve(p)
        with self.assertRaises(ProjectCommandError):self.manager.inspect(self.project,p['handle'])
        self.assertEqual(self.transport.calls,[])
    def test_configuration_change_during_request_records_interruption_not_success(self):
        self.transport.block=threading.Event();p=self.prepare(['openalex']);self.approve(p)
        self.manager.start(self.project,handle=p['handle'],request_id='config-race-start')
        self.assertTrue(self.transport.entered.wait(5))
        self.project.configure(replace(self.project.config,config_version=2,name='Changed configuration'),
            expected_event_id=p['plan']['config_event_id'],created_by='fixture')
        self.transport.block.set();result=self.wait(p['handle'])
        self.assertEqual(result['status'],'interrupted');self.assertEqual(len(self.transport.calls),1)
        self.assertEqual(result['summary']['unique_publications'],0)
    def test_plan_corruption_symlinks_immutable_publication_and_receipts(self):
        p=self.prepare();same=self.prepare();self.assertEqual(p['handle'],same['handle'])
        with self.assertRaises(ProjectCommandError):self.prepare(query='different query')
        path=files.location(self.project)/'plans'/(p['handle']+'.json')
        with self.assertRaises(ValueError):files.publish(path,{'different':'content'})
        with self.assertRaises(ProjectCommandError):self.manager.inspect(self.project,'../other')
        original=path.read_bytes();path.write_bytes(original.replace(b'porous ceramic',b'different topic'))
        with self.assertRaises(ValueError):self.manager.inspect(self.project,p['handle'])
        path.write_bytes(original)
        # Explicitly test a symlink final record without following its target.
        path2=files.location(self.project)/'plans'/('f'*64+'.json')
        try:path2.symlink_to(path)
        except OSError:return
        with self.assertRaises(ValueError):self.manager.inspect(self.project,'f'*64)

    def test_crashed_independent_worker_is_interrupted_without_implicit_replay(self):
        script = r'''
import sys,json,threading
from pathlib import Path
import corpustrail.application.project_use as guard
guard.lock_directory=lambda:Path(sys.argv[2])
from corpustrail.project import Project
from corpustrail.application.projects import ProjectController
from corpustrail.application.discovery import DiscoveryController,BOUNDS
p=Project.open(sys.argv[1]);c=ProjectController(projects_root=p.root.parent,project=p)
class WaitingTransport:
 network=False
 def request(self,*args,**kwargs):
  print('READY',flush=True);threading.Event().wait(60);raise TimeoutError()
m=DiscoveryController(c,transport_factory=WaitingTransport)
v=m.prepare(p,request_id='child-preparation',config_event_id=p.configuration_history()[-1]['event_id'],query='invented ceramic',providers=['openalex'],bounds=BOUNDS)
m.approve(p,handle=v['handle'],request_id='child-approval',preview_nonce=v['preview_nonce'],confirm_external=True,approve_identities=True)
print(v['handle'],flush=True)
m.start(p,handle=v['handle'],request_id='child-execution')
sys.stdin.readline()
'''
        proc=subprocess.Popen([sys.executable,'-I','-u','-c',script,str(self.root),str(self.locks)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def stop():
            if proc.poll() is None:proc.kill()
            proc.communicate(timeout=20)
        self.addCleanup(stop)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            def lines():return proc.stdout.readline().strip(),proc.stdout.readline().strip()
            future=pool.submit(lines)
            try:handle,ready=future.result(timeout=20)
            except concurrent.futures.TimeoutError:
                proc.kill();self.fail('disposable child startup timed out')
        self.assertEqual(ready,'READY');self.assertEqual(self.manager.inspect(self.project,handle)['status'],'running')
        stop();before=fingerprint(self.root)
        self.assertEqual(self.manager.inspect(self.project,handle)['status'],'interrupted')
        self.assertEqual(before,fingerprint(self.root));self.assertEqual(self.transport.calls,[])
        with self.assertRaises(ProjectCommandError):self.manager.start(self.project,handle=handle,request_id='new-request-old-plan')
        self.assertEqual(self.transport.calls,[])


class DiscoveryHttpTests(DiscoveryFixture):
    @unittest.skipUnless(shutil.which('node'),'Optional developer Node harness, not a runtime dependency')
    def test_packaged_javascript_researcher_workflow_against_actual_local_api(self):
        assets=resources.files('corpustrail.local_app').joinpath('assets')
        harness=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8')),nodes=[],elements={},requests=[];
class Element{
 constructor(tag){this.tag=tag;this.textContent='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.dataset={};this.children=[];nodes.push(this);}
 append(...args){this.children.push(...args);}prepend(...args){this.children.unshift(...args);}replaceChildren(...args){this.children=[...args];}focus(){}
}
for(const m of input.html.matchAll(/id="([^"]+)"/g))elements[m[1]]=new Element('element');
const document={getElementById:id=>elements[id]||nodes.find(e=>e.id===id),createElement:tag=>new Element(tag),
 querySelector:()=>({content:input.token}),querySelectorAll:s=>{assert.equal(s,'[data-provider]');return nodes.filter(e=>e.dataset.provider);}};
const context={document,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,console,
 fetch:async(path,options)=>{requests.push({path,options});return fetch(input.origin+path,{...options,headers:{...options.headers,Origin:input.origin}});}};
vm.createContext(context);vm.runInContext(input.script,context);
async function until(condition){for(let i=0;i<500;i++){if(condition())return;await new Promise(r=>setTimeout(r,10));}throw Error('UI did not reach expected state: '+elements.message.textContent);}
async function preview(){elements['search-form'].onsubmit({preventDefault(){}});await until(()=>vm.runInContext('view !== null && !busy',context));}
(async()=>{
 await until(()=>elements.history.children.length===0&&vm.runInContext('configuration !== undefined',context));
 assert.equal(requests.filter(r=>r.options.method==='POST').length,0);
 elements.query.value='porous ceramic';for(const e of nodes.filter(e=>e.dataset.provider))e.checked=['openalex','crossref'].includes(e.value);
 await preview();assert.equal(elements['plan-query'].textContent,'porous ceramic');
 assert.equal(elements['plan-providers'].children.length,2);assert(!elements['approval-area'].hidden);
 assert.equal(requests.filter(r=>r.path.endsWith('/start')).length,0);
 await elements.approve.onclick();assert.match(elements.message.textContent,/explicitly/);
 elements.transfer.checked=true;elements.identity.checked=true;await elements.approve.onclick();
 assert(!elements.run.hidden);assert.equal(requests.filter(r=>r.path.endsWith('/start')).length,0);
 await elements.run.onclick();await until(()=>vm.runInContext('view.status === "completed"',context)&&elements['result-papers'].children.length===5);
 assert.equal(elements.results.children.find(e=>e.textContent==='Unique publications linked').tag,'dt');
 assert.equal(elements['result-papers'].children[0].children[0].tag,'a');assert.equal(elements.provenance.textContent,'');
 elements['provenance-provider'].value='openalex';await elements['show-provenance'].onclick();assert.match(elements.provenance.textContent,/discovery_plan/);
 const starts=requests.filter(r=>r.path.endsWith('/start')).length;await elements.repeat.onclick();
 assert(!elements['search-setup'].hidden);assert.equal(requests.filter(r=>r.path.endsWith('/start')).length,starts);
 await preview();elements.transfer.checked=true;elements.identity.checked=true;await elements.approve.onclick();await elements.run.onclick();
 await until(()=>vm.runInContext('view.status === "completed" && view.summary.previously_known_publications === 5',context));
 vm.runInContext('stopPolling()',context);console.log('Packaged Discovery UI exact-preview, consent, explicit run, provenance and repeat passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',harness],input=json.dumps({'html':assets.joinpath('discovery.html').read_text(encoding='utf-8'),
            'script':assets.joinpath('discovery.js').read_text(encoding='utf-8'),'token':self.token,'origin':self.origin}),
            text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(len(self.project.identities.papers()),5)
    def setUp(self):
        super().setUp();self.server=make_server(controller=self.controller,discovery=self.manager,port=0)
        thread=threading.Thread(target=self.server.serve_forever);thread.start()
        self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),thread.join()))
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        _,html=self.call('GET','/discovery',auth=False)
        self.token=re.search('name="corpustrail-session" content="([^"]+)"',html).group(1)
    def call(self,method,path,body=None,auth=True,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        base={'Content-Type':'application/json','Origin':self.origin}
        if auth:base.update({'X-CorpusTrail-Session':self.token,'X-CorpusTrail-CSRF':self.token})
        base.update(headers or {})
        if isinstance(body,dict):body=json.dumps({'schema':SCHEMA,**body})
        conn.request(method,path,body=body,headers=base);r=conn.getresponse();data=r.read().decode('utf-8');status=r.status;conn.close();return status,data
    def test_navigation_reads_security_and_no_network(self):
        before=fingerprint(self.root)
        for path in ('/discovery','/assets/discovery.js','/api/v1/discovery/configuration','/api/v1/discovery/history'):
            self.assertEqual(self.call('GET',path)[0],200)
        self.assertEqual(before,fingerprint(self.root));self.assertEqual(self.transport.calls,[])
        for headers in ({'Host':'outside.test'},{'Origin':'https://outside.test'}):
            self.assertEqual(self.call('GET','/discovery',headers=headers)[0],403)
        self.assertEqual(self.call('POST','/api/v1/discovery/prepare',{},auth=False)[0],403)
        self.assertEqual(self.call('POST','/api/v1/discovery/prepare','x'*65537)[0],413)
        self.assertEqual(self.call('GET','/api/v1/discovery/start')[0],404)
        self.assertEqual(self.call('POST','/api/v1/discovery/prepare',{'url':'https://outside.test'})[0],400)
        self.controller.close();self.assertEqual(self.call('GET','/discovery')[0],409)
    def test_complete_offline_http_workflow_and_history(self):
        config=json.loads(self.call('GET','/api/v1/discovery/configuration')[1])
        payload={'request_id':'http-prepare-command','config_event_id':config['config_event_id'],
                 'query':'porous ceramic','providers':['openalex','crossref'],'bounds':BOUNDS}
        status,body=self.call('POST','/api/v1/discovery/prepare',payload);self.assertEqual(status,200,body);p=json.loads(body)
        self.assertEqual(self.transport.calls,[])
        status,body=self.call('POST','/api/v1/discovery/approve',{'handle':p['handle'],'request_id':'http-approve-command',
            'preview_nonce':p['preview_nonce'],'confirm_external':True,'approve_identities':True});self.assertEqual(status,200,body)
        self.assertEqual(self.transport.calls,[])
        self.assertEqual(self.call('POST','/api/v1/discovery/start',{'handle':p['handle'],'request_id':'http-start-command'})[0],200)
        self.assertEqual(self.wait(p['handle'])['summary']['unique_publications'],5)
        self.assertEqual(len(json.loads(self.call('GET','/api/v1/discovery/history')[1])['items']),1)
        self.assertEqual(self.call('GET','/api/v1/discovery/plans/'+p['handle']+'/papers?limit=2')[0],200)
        self.assertEqual(self.call('GET','/api/v1/discovery/plans/'+p['handle']+'/provenance?provider=openalex&limit=2')[0],200)
        assets=resources.files('corpustrail.local_app').joinpath('assets')
        js=assets.joinpath('discovery.js').read_text(encoding='utf-8')
        self.assertNotIn('innerHTML',js);self.assertNotIn('localStorage',js);self.assertNotIn('http://',js)
        self.assertIn('Discovery workflow in this UI',assets.joinpath('home.html').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
