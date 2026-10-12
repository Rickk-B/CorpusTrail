"""Offline Checkpoint 4 evidence workflow; disposable projects only."""
from dataclasses import replace
import http.client
from importlib import resources
import json
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

from corpustrail.application.evidence import EvidenceController, SCHEMA
from corpustrail.application.projects import ProjectController, ProjectCommandError
from corpustrail.application.project_use import acquire_project_use, ProjectBusy
from corpustrail.application.reads import ProjectReads
from corpustrail.curation import ReviewEvent, EvidenceBasis
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail._internal.values import canonical, digest_bytes, ContractError
from corpustrail._internal.pipeline import events
from corpustrail.local_app import make_server
from corpustrail.project import Project, ProjectConfig, EvidencePolicy, ReviewPolicy
from corpustrail.providers.network import HttpResponse

AT='2026-01-01T00:00:00+00:00'
XML=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/evidence.1</article-id><article-id pub-id-type="pmc">PMC123</article-id><abstract><p>Invented acquired abstract.</p></abstract></article-meta></front><body><sec><title>Methods</title><p>Invented structured scientific fixture text.</p></sec></body></article>'


def fingerprint(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


class Transport:
    network=False
    def __init__(self):
        self.calls=[];self.responses=[];self.block=None;self.entered=threading.Event()
    def request(self,url,**kwargs):
        self.calls.append((url,kwargs));self.entered.set()
        if self.block:self.block.wait(20)
        response=self.responses.pop(0) if self.responses else (200,XML,{})
        if isinstance(response,Exception):raise response
        status,body,headers=response
        return HttpResponse(status,headers,body,url)


class EvidenceFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ct-evidence-disposable-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.root=self.base/'projects'/'materials';self.locks=self.base/'locks'
        patcher=patch('corpustrail.application.project_use.lock_directory',return_value=self.locks);patcher.start();self.addCleanup(patcher.stop)
        self.project=Project.create(self.root,ProjectConfig('evidence-fixture','Synthetic materials','Invented broad topic',
            evidence=EvidencePolicy(('europepmc',),max_attempts=2,max_retry_wait_seconds=2),
            review=ReviewPolicy(authorized_reviewers=('fixture_reviewer',))),created_by='fixture',created_at=AT)
        self.ids=[self.enroll(i,pmcid=i==1) for i in range(1,6)]
        self.pid=self.ids[0];self.paper=self.pid.split(':')[1]
        self.controller=ProjectController(projects_root=self.root.parent,project=self.project);self.addCleanup(self.controller.close)
        self.transport=Transport();self.manager=EvidenceController(self.controller,transport_factory=lambda:self.transport)
        self.addCleanup(self.finish)
    def enroll(self,i,*,pmcid=False,abstract=True):
        record=BibliographicRecord('Invented materials '+str(i),'<script>fixture text, not executable</script>' if abstract else None,
            identifiers=(Identifier('doi','10.1234/evidence.'+str(i)),)+((Identifier('pmcid','PMC123'),) if pmcid else ()))
        body=canonical({'fixture':i}).encode()
        source=SourceReference('fixture://bibliography/'+str(i),str(i),digest_bytes(body),len(body),'fixture_discovery',AT,identity_status='verified')
        return self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
    def finish(self):
        if self.transport.block:self.transport.block.set()
        self.manager.close()
        for thread in list(self.manager._workers.values()):thread.join(25)
    def start(self,request_id='evidence-request-command',paper=None,**overrides):
        paper=paper or self.paper
        args={'paper':paper,'request_id':request_id,'eligibility_hash':self.manager.availability(self.project,paper)['eligibility_hash'],'confirm_external':True}
        args.update(overrides);return self.manager.start(self.project,**args)
    def wait(self,handle):
        for _ in range(500):
            value=self.manager.inspect(self.project,handle)
            if value['status'] not in ('queued','running','not_started'):return value
            time.sleep(.02)
        self.fail('fixture retrieval did not finish')


class EvidenceWorkflowTests(EvidenceFixture):
    def test_reads_are_side_effect_free_eligibility_and_no_enrichment(self):
        before=fingerprint(self.root)
        view=self.manager.view(self.project,self.paper)
        self.assertTrue(view['availability']['eligible']);self.assertEqual(view['availability']['pmcid'],'PMC123')
        self.assertEqual(view['abstract_source']['origin'],'Bibliographic/discovery metadata abstract')
        missing=self.manager.availability(self.project,self.ids[1].split(':')[1])
        self.assertFalse(missing['eligible']);self.assertIn('PMCID',missing['reason'])
        self.manager.history(self.project,self.paper)
        self.assertEqual(before,fingerprint(self.root));self.assertEqual(self.transport.calls,[])
        with self.assertRaises(ProjectCommandError):self.start(paper=self.ids[1].split(':')[1])
        with self.assertRaises(ProjectCommandError):self.start(confirm_external=False)
        self.assertEqual(before,fingerprint(self.root))

    def test_verified_acquisition_provenance_reader_and_command_replay(self):
        value=self.start();result=self.wait(value['handle'])
        self.assertEqual(result['status'],'completed');self.assertEqual(result['network_outcome'],'success')
        self.assertEqual(len(self.transport.calls),1)
        self.assertTrue(self.transport.calls[0][0].endswith('PMC123/fullTextXML'))
        reps=self.project.evidence.representations(self.pid,trusted_only=True)
        structured=next(r for r in reps if r['payload']['representation']=='structured_text')
        text=ProjectReads(self.project).document(self.paper,structured['event_id'].split(':')[1])
        self.assertIn('Invented structured',text['text'])
        self.assertEqual(self.project.reviews.membership(self.pid)['state'],'not_reviewed')
        self.assertEqual(self.project.reviews.history(self.pid),[])
        self.start();self.assertEqual(len(self.transport.calls),1)
        self.assertEqual(self.manager.view(self.project,self.paper,advanced=True)['activity']['items'][0]['kind'],'acquisition_result')
        self.assertTrue(events(self.project,kind='resolution_plan'))
        normal=self.manager.view(self.project,self.paper)['activity']['items']
        self.assertNotIn('payload',normal[0]);self.assertNotIn('request',str(normal[0].keys()))

    def test_mismatch_invalid_pending_and_prior_valid_evidence_preserved(self):
        self.wait(self.start()['handle']);valid=self.project.evidence.representations(self.pid,trusted_only=True)
        wrong=XML.replace(b'PMC123',b'PMC999').replace(b'evidence.1',b'wrong.9')
        for i,body,expected in ((1,wrong,'mismatch'),(2,b'not xml','invalid'),
                                 (3,b'<article><body><p>Unidentified document</p></body></article>','pending_identity')):
            self.transport.responses=[(200,body,{})]
            result=self.wait(self.start(request_id='explicit-retry-'+str(i))['handle'])
            self.assertEqual(result['network_outcome'],'success')
            rep=self.project.evidence.representations(self.pid)[-1]
            self.assertEqual(rep['payload']['artifact_validity'],expected);self.assertFalse(rep['payload']['trusted'])
            with self.assertRaises(ContractError):ProjectReads(self.project).document(self.paper,rep['event_id'].split(':')[1])
        self.assertEqual(valid,self.project.evidence.representations(self.pid,trusted_only=True))
        self.assertEqual(self.project.evidence.status(self.pid)['verified_structured_text'],1)

    def test_unavailable_empty_malformed_timeout_rate_limit_bounded_retry(self):
        for i,responses in enumerate(([(404,b'',{})],[(200,b'',{})],[(200,b'<article>',{})],
            [TimeoutError('private diagnostic'),TimeoutError('private diagnostic')],
            [(429,b'limited',{'Retry-After':'3600'})])):
            self.transport.responses=list(responses)
            result=self.wait(self.start(request_id='failure-operation-'+str(i))['handle'])
            self.assertNotIn('private diagnostic',canonical(result))
            if i in (0,3,4):self.assertEqual(result['status'],'unsuccessful')
        self.transport.responses=[(429,b'limited',{'Retry-After':'0'}),(200,XML,{})]
        result=self.wait(self.start(request_id='explicit-bounded-retry')['handle'])
        self.assertEqual(result['status'],'completed')
        outcomes=events(self.project,scope_id=result['resolution_id'],kind='acquisition_result')
        self.assertEqual([e['payload'].get('http_status') for e in outcomes if 'http_status' in e['payload']],[429,200])

    def test_disabled_unsupported_stale_configuration_and_changed_identifiers(self):
        old=self.manager.availability(self.project,self.paper)
        for resolvers in ((),('unsupported',),('europepmc','unsupported')):
            config=self.project.config
            self.project.configure(replace(config,config_version=config.config_version+1,evidence=EvidencePolicy(resolvers)),
                expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
            self.assertFalse(self.manager.availability(self.project,self.paper)['eligible'])
            with self.assertRaises(ProjectCommandError):self.start(eligibility_hash=old['eligibility_hash'])
        self.assertEqual(self.transport.calls,[])

    def test_ambiguous_or_unverified_pmcid_refuses_without_inference(self):
        with patch.object(type(self.project.identities),'exact_owner',return_value=None):
            self.assertFalse(self.manager.availability(self.project,self.paper)['eligible'])
            with self.assertRaises(ProjectCommandError):self.start()
        record=BibliographicRecord('Synthetic alias',identifiers=(Identifier('doi','10.1234/evidence.1'),Identifier('pmcid','PMC999')))
        source=SourceReference('fixture://extra-identifier','extra',digest_bytes(b'extra'),5,'fixture',AT,identity_status='verified')
        self.project.identities.apply(self.project.identities.plan(record,source),approve_aliases=True,approve_new_identity=True)
        self.assertIn('Multiple',self.manager.availability(self.project,self.paper)['reason'])
        with self.assertRaises(ProjectCommandError):self.start()
        self.assertEqual(self.transport.calls,[])

    def test_acquired_abstract_front_matter_not_full_document_and_safe_source(self):
        record=BibliographicRecord('Invented no-abstract paper',identifiers=(Identifier('doi','10.1234/evidence.6'),Identifier('pmcid','PMC456')))
        source=SourceReference('fixture://no-abstract','six',digest_bytes(b'six'),3,'fixture',AT,identity_status='verified')
        pid=self.project.identities.apply(self.project.identities.plan(record,source),approve_aliases=True,approve_new_identity=True)
        body=XML.replace(b'evidence.1',b'evidence.6').replace(b'PMC123',b'PMC456').split(b'<body>')[0]+b'</article>'
        self.transport.responses=[(200,body,{})]
        self.wait(self.start(paper=pid.split(':')[1],request_id='acquire-abstract-fixture')['handle'])
        view=self.manager.view(self.project,pid.split(':')[1])
        self.assertEqual(view['abstract_source']['origin'],'Retrieved document abstract')
        self.assertEqual(view['evidence']['best_available'],'abstract')
        self.assertEqual(view['evidence']['verified_structured_text'],0)
        self.assertEqual(self.project.discovery.metadata(pid)['fields']['abstract'],'Invented acquired abstract.')
        structured=next(r for r in self.project.evidence.representations(pid) if r['payload']['representation']=='structured_text')
        with self.assertRaises(ContractError):ProjectReads(self.project).document(pid.split(':')[1],structured['event_id'].split(':')[1])

    def test_liveness_completion_race_and_startup_failure(self):
        self.transport.block=threading.Event();value=self.start()
        self.assertTrue(self.transport.entered.wait(5));thread=next(iter(self.manager._workers.values()));probe=self.manager._alive
        def finish(project,handle):
            self.transport.block.set();thread.join(10);self.assertFalse(thread.is_alive());return probe(project,handle)
        with patch.object(self.manager,'_alive',side_effect=finish):self.assertEqual(self.manager.inspect(self.project,value['handle'])['status'],'completed')
        with patch('threading.Thread.start',side_effect=RuntimeError('fixture startup')):
            with self.assertRaises(ProjectCommandError):self.start(request_id='startup-failure-fixture')
        history=self.manager.history(self.project,self.paper)
        self.assertEqual(history['items'][0]['status'],'interrupted')
        self.assertEqual(len(self.transport.calls),1)

    def test_changed_configuration_during_request_preserves_interruption(self):
        self.transport.block=threading.Event();value=self.start()
        self.assertTrue(self.transport.entered.wait(5));config=self.project.config
        self.project.configure(replace(config,config_version=config.config_version+1,name='Updated synthetic project'),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
        self.transport.block.set();self.assertEqual(self.wait(value['handle'])['status'],'interrupted')
        self.assertEqual(self.project.evidence.representations(self.pid),[])

    def test_history_pagination_symlink_and_command_collision(self):
        first=self.start();self.wait(first['handle'])
        self.wait(self.start(request_id='second-evidence-fixture')['handle'])
        page=self.manager.history(self.project,self.paper,limit=1)
        self.assertEqual(len(page['items']),1);self.assertEqual(page['next_offset'],1)
        with self.assertRaises(ProjectCommandError):self.start(eligibility_hash='altered-content')
        with self.assertRaises(ContractError):self.manager.view(self.project,self.paper,limit=1000)
        from corpustrail.application import _workflow_files as files
        plan=files.location(self.project,family='evidence')/'plans'/(first['handle']+'.json')
        backup=plan.with_suffix('.saved');plan.rename(backup)
        try:plan.symlink_to(backup)
        except OSError:
            backup.rename(plan);return
        with self.assertRaises((ContractError,OSError)):self.manager.inspect(self.project,first['handle'])
        plan.unlink();backup.rename(plan)
        value=files.read(plan);value['resolver_version']='altered-version'
        plan.unlink();files.publish(plan,value)
        with self.assertRaises(ContractError):self.manager.inspect(self.project,first['handle'])

    def test_no_secret_persistence_and_size_xml_policy_guards(self):
        for i,body in enumerate((b'Bearer synthetic_credential_value',b'x'*20_000_001,
            b'<!DOCTYPE article [<!ENTITY a "evil">]><article>&a;</article>')):
            self.transport.responses=[(200,body,{})]
            result=self.wait(self.start(request_id='unsafe-response-'+str(i))['handle'])
            self.assertFalse(self.project.evidence.representations(self.pid,trusted_only=True))
            self.assertNotIn('synthetic_credential_value',canonical(result))
        self.assertFalse(any(b'synthetic_credential_value' in data for data in fingerprint(self.root).values()))

    def test_worker_lease_survives_project_close_and_no_unintended_duplicate(self):
        self.transport.block=threading.Event();value=self.start()
        self.assertTrue(self.transport.entered.wait(5));self.controller.close()
        with self.assertRaises(ProjectBusy):acquire_project_use(self.root,exclusive=True)
        self.start();self.assertEqual(len(self.transport.calls),1)
        with self.assertRaises(ProjectCommandError):self.start(request_id='another-concurrent-operation')
        self.transport.block.set();self.wait(value['handle'])
        for thread in list(self.manager._workers.values()):thread.join(5)
        lease=acquire_project_use(self.root,exclusive=True);lease.close()

    def test_existing_five_paper_research_history_frozen_session_preserved(self):
        source=self.project.identities.observations(self.pid)[0]['source']
        review=ReviewEvent(self.pid,'included','sufficient','metadata','Synthetic human assessment','fixture_reviewer',AT,
            (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),authority_state='human_authorized')
        self.project.reviews.apply(self.project.reviews.plan(review))
        self.project.review_sessions.prepare('frozen',reviewer_id='fixture_reviewer',paper_ids=self.ids)
        before=(self.project.configuration_history(),self.project.reviews.history(self.pid),
                self.project.reviews.membership(self.pid),self.project.review_sessions.view('frozen'))
        self.wait(self.start()['handle'])
        after=(self.project.configuration_history(),self.project.reviews.history(self.pid),
               self.project.reviews.membership(self.pid),self.project.review_sessions.view('frozen'))
        self.assertEqual(before,after)

    def test_real_process_interruption_lock_recovery_read_only_status(self):
        self.controller.close()
        script=r'''
import sys,threading,time
from pathlib import Path
from corpustrail.project import Project
from corpustrail.application.projects import ProjectController
from corpustrail.application.evidence import EvidenceController
import corpustrail.application.project_use as guards
guards.lock_directory=lambda:Path(sys.argv[2])
p=Project.open(Path(sys.argv[1]));c=ProjectController(projects_root=p.root.parent,project=p)
class Transport:
 network=False
 def request(self,*args,**kwargs):
  print('REQUEST_STARTED',flush=True);threading.Event().wait(60)
m=EvidenceController(c,transport_factory=Transport)
paper=sys.argv[3];a=m.availability(p,paper)
v=m.start(p,paper=paper,request_id='process-interruption-fixture',eligibility_hash=a['eligibility_hash'],confirm_external=True)
print(v['handle'],flush=True);c.close();threading.Event().wait(60)
'''
        child=subprocess.Popen([sys.executable,'-I','-c',script,str(self.root),str(self.locks),self.paper],stdout=subprocess.PIPE,text=True)
        self.addCleanup(lambda:child.kill() if child.poll() is None else None)
        lines=[child.stdout.readline().strip(),child.stdout.readline().strip()]
        self.assertIn('REQUEST_STARTED',lines);handle=next(x for x in lines if re.fullmatch('[0-9a-f]{64}',x))
        with self.assertRaises(ProjectBusy):acquire_project_use(self.root,exclusive=True)
        child.kill();child.wait(10);child.stdout.close()
        before=fingerprint(self.root)
        self.assertEqual(self.manager.inspect(self.project,handle)['status'],'interrupted')
        self.assertEqual(before,fingerprint(self.root));self.assertEqual(self.transport.calls,[])
        lease=acquire_project_use(self.root,exclusive=True);lease.close()


class EvidenceHttpTests(EvidenceFixture):
    def setUp(self):
        super().setUp();self.server=make_server(controller=self.controller,evidence=self.manager,port=0)
        thread=threading.Thread(target=self.server.serve_forever);thread.start()
        self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),thread.join()))
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        _,html=self.call('GET','/papers/'+self.paper,auth=False)
        self.token=re.search('name="corpustrail-session" content="([^"]+)"',html).group(1)
    def call(self,method,path,body=None,auth=True,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        values={'Content-Type':'application/json','Origin':self.origin}
        if auth:values.update({'X-CorpusTrail-Session':self.token,'X-CorpusTrail-CSRF':self.token})
        values.update(headers or {})
        if isinstance(body,dict):body=json.dumps({'schema':SCHEMA,**body})
        c.request(method,path,body=body,headers=values);response=c.getresponse();data=response.read().decode();status=response.status;c.close();return status,data
    def test_security_read_fingerprints_explicit_retrieval_and_provenance(self):
        before=fingerprint(self.root);base='/api/v1/evidence/papers/'+self.paper
        for path in ('/papers/'+self.paper,base,base+'/history',base+'/provenance','/assets/evidence.js'):
            self.assertEqual(self.call('GET',path)[0],200)
        self.assertEqual(before,fingerprint(self.root));self.assertEqual(self.transport.calls,[])
        for header in ({'Host':'outside.test'},{'Origin':'https://outside.test'}):self.assertEqual(self.call('GET',base,headers=header)[0],403)
        self.assertEqual(self.call('POST','/api/v1/evidence/start',{},auth=False)[0],403)
        self.assertEqual(self.call('POST','/api/v1/evidence/start','x'*65537)[0],413)
        self.assertEqual(self.call('POST','/api/v1/evidence/start',{'url':'https://outside.test'})[0],400)
        self.assertEqual(self.call('GET',base+'?path=../../outside')[0],400)
        availability=json.loads(self.call('GET',base)[1])['availability']
        payload={'paper':self.paper,'request_id':'http-evidence-command','eligibility_hash':availability['eligibility_hash'],'confirm_external':True}
        status,body=self.call('POST','/api/v1/evidence/start',payload);self.assertEqual(status,200,body)
        self.wait(json.loads(body)['handle'])
        self.assertEqual(self.call('POST','/api/v1/evidence/start',payload)[0],200);self.assertEqual(len(self.transport.calls),1)

    @unittest.skipUnless(shutil.which('node'),'Developer DOM harness only')
    def test_packaged_browser_workflow_no_automatic_requests(self):
        assets=resources.files('corpustrail.local_app').joinpath('assets')
        script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),input=JSON.parse(require('node:fs').readFileSync(0,'utf8')),elements={},requests=[];
class E{constructor(){this.textContent='';this.hidden=false;this.children=[];}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=[...x];}}
for(const m of input.html.matchAll(/id="([^"]+)"/g))elements[m[1]]=new E();
elements['evidence-acquisition'].hidden=false;
const context={location:{pathname:'/papers/'+input.paper},crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,
 document:{getElementById:id=>elements[id],querySelector:()=>({content:input.token}),createElement:()=>new E()},
 fetch:async(path,options)=>{requests.push({path,options});return fetch(input.origin+path,{...options,headers:{...options.headers,Origin:input.origin}});}};
vm.createContext(context);vm.runInContext(input.script,context);
async function until(check){for(let i=0;i<500;i++){if(check())return;await new Promise(r=>setTimeout(r,10));}throw Error(elements['evidence-result'].textContent);}
(async()=>{await until(()=>elements['evidence-request'].textContent.includes('PMCID')||elements['evidence-eligibility'].textContent.includes('PMC123'));
 assert.equal(requests.filter(r=>r.options.method==='POST').length,0);assert(!elements['retrieve-evidence'].hidden);
 await elements['retrieve-evidence'].onclick();await until(()=>elements['evidence-result'].textContent.includes('completed'));
 assert.equal(requests.filter(r=>r.options.method==='POST').length,1);assert.equal(elements['evidence-raw'].textContent,'');
 await elements['evidence-provenance'].onclick();assert.match(elements['evidence-raw'].textContent,/resolution_plan/);
 assert(elements['evidence-history'].children.some(e=>e.textContent.includes('verified')));
 console.log('Explicit evidence acquisition, updated history, safe provenance and no navigation-triggered requests passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',script],input=json.dumps({'html':assets.joinpath('index.html').read_text(encoding='utf-8'),
            'script':assets.joinpath('evidence.js').read_text(encoding='utf-8'),'token':self.token,'origin':self.origin,'paper':self.paper}),
            text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
