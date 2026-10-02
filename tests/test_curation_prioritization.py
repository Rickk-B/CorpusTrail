"""Portable safety/curation tests; synthetic inputs and optional learned backend."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
from contextlib import closing
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from corpustrail._internal.database import connection,create_database,migrations
from corpustrail._internal.values import ContractError,canonical,content_hash
from corpustrail.cli import main
from corpustrail.curation import EvidenceBasis,ReviewEvent
from corpustrail.curation.http import HTML,make_server
from corpustrail.identity import BibliographicRecord,Identifier,SourceReference
from corpustrail.prioritization import TfidfLogistic
from corpustrail.prioritization import _algorithm
from corpustrail.project import Project,ProjectConfig,ReviewPolicy

AT='2026-01-01T00:00:00+00:00'
LATER='2026-01-02T00:00:00+00:00'
HAS_ML=importlib.util.find_spec('sklearn') is not None


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'topic'
        self.config=ProjectConfig('fixture-topic','Porous materials','Synthetic unrelated topic',
            review=ReviewPolicy(authorized_reviewers=('reviewer_one','reviewer_two')))
        self.project=Project.create(self.root,self.config,created_by='fixture',created_at=AT)
        self.ids=[self.enroll(i) for i in range(8)]

    def enroll(self,i,*,abstract=True):
        title=('Porous ceramic measurement sensor' if i<2 else 'Accounting invoice ledger' if i<4
               else 'Synthetic material evidence')+' '+str(i)
        record=BibliographicRecord(title=title,abstract=('Invented '+title) if abstract and i!=4 else None,
            identifiers=(Identifier('doi','10.1234/fixture.'+str(i)),))
        body=canonical({'record':title,'hidden_model_judgment':'do not expose','arm':'secret-arm'}).encode()
        src=SourceReference('fixture://provider-private-query/'+str(i),'record-'+str(i),
            'sha256:'+hashlib.sha256(body).hexdigest(),len(body),'fixture_provider',AT,identity_status='verified')
        return self.project.identities.apply(self.project.identities.plan(record,src),
            approve_new_identity=True,approve_aliases=True)

    def event(self,pid,state='included',*,at=AT,authority='human_authorized',producer='human',reviewer='reviewer_one'):
        src=self.project.identities.observations(pid)[0]['source']
        return ReviewEvent(pid,state,{'included':'sufficient','excluded':'sufficient','insufficient_evidence':'insufficient','unresolved':'undetermined'}[state],
            'metadata','Invented fixture rationale',reviewer,at,
            (EvidenceBasis('metadata',src['source_sha256'],src['source_uri'],artifact_validity='verified'),),
            producer_type=producer,authority_state=authority,
            supersedes=self.project.reviews.membership(pid)['current_event_id'] if authority=='human_authorized' else None)

    def label(self,pid,state='included',**kwargs):
        event=self.event(pid,state,**kwargs)
        return self.project.reviews.apply(self.project.reviews.plan(event),recorded_at=kwargs.get('at',AT))

    def prepare(self,**kwargs):
        return self.project.review_sessions.prepare('session',reviewer_id='reviewer_one',paper_ids=self.ids,
            authority_state='human_authorized',created_at=AT,**kwargs)

    def update(self,action,value=None,*,session='session'):
        service=self.project.review_sessions
        return service.update(session,expected_revision=service.view(session)['revision'],action=action,value=value)

    def draft(self,**kwargs):
        return {'sufficiency':'sufficient','decision':'included','review_extent':'metadata',
                'rationale':'Synthetic human explanation',**kwargs}

    def document(self,pid,*,valid=True):
        body=('<article><front><article-meta><article-id pub-id-type="doi">'+
              ('10.1234/fixture.0' if valid else '10.1234/wrong')+
              '</article-id></article-meta></front><body><sec><title>Methods</title><p>'+('Invented material instrument and measurements. '*20)+
              '</p></sec></body></article>').encode()
        return self.project.evidence.preserve_document(pid,body,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://verified-document',legitimate_basis='synthetic_fixture',
            resolver='fixture',resolver_version='1',created_at=AT)

    def test_draft_autosave_resume_without_membership_mutation(self):
        self.prepare()
        self.update('draft',self.draft())
        before=self.project.review_sessions.view('session')
        self.assertEqual(before['counts']['complete'],1)
        self.assertEqual(before['recorded_count'],0)
        self.assertEqual(self.project.reviews.history(self.ids[0]),[])
        self.assertEqual(Project.open(self.root).review_sessions.view('session'),before)
        with connection(self.project.database_path) as db:
            payload=json.loads(db.execute('SELECT payload_json FROM ct_review_session_events').fetchone()[0])
        self.assertNotIn('state',payload)
        self.assertEqual(set(payload['delta']),{'drafts'})
        self.assertEqual(set(payload['delta']['drafts']),{self.ids[0]})

    def test_explicit_human_commit_and_append_only_correction(self):
        self.prepare()
        self.update('draft',self.draft())
        self.update('commit')
        old=self.project.reviews.history(self.ids[0])[0]
        self.update('draft',self.draft(decision='excluded',rationale='Changed synthetic human decision'))
        self.update('commit')
        history=self.project.reviews.history(self.ids[0])
        self.assertEqual(history[0],old)
        self.assertEqual(history[1]['supersedes'],old['event_id'])
        self.assertEqual(self.project.reviews.membership(self.ids[0])['state'],'excluded')

    def test_partial_cannot_be_committed(self):
        self.prepare()
        for change in ({'decision':None},{'rationale':''},{'review_extent':None}):
            self.update('draft',self.draft(**change))
            self.assertEqual(self.project.review_sessions.view('session')['counts']['partial'],1)
            with self.assertRaises(ContractError):self.update('commit')
        self.assertEqual(self.project.reviews.history(self.ids[0]),[])

    def test_insufficient_is_not_exclusion(self):
        self.prepare()
        self.update('draft',self.draft(sufficiency='insufficient',decision=None,review_extent=None,rationale='Need evidence'))
        self.update('commit')
        self.assertEqual(self.project.reviews.membership(self.ids[0])['state'],'insufficient_evidence')
        with self.assertRaises(ContractError):self.update('draft',self.draft(sufficiency='insufficient'))

    def test_unresolved_is_not_exclusion(self):
        self.prepare()
        self.update('draft',self.draft(sufficiency='undetermined',decision=None,rationale='Defer'))
        self.update('commit')
        self.assertEqual(self.project.reviews.membership(self.ids[0])['state'],'unresolved')

    def test_metadata_review_without_abstract_or_document(self):
        self.prepare()
        self.update('navigate',5)
        view=self.project.review_sessions.view('session')
        self.assertIsNone(view['abstract'])
        self.assertEqual(view['review_options'],['metadata'])
        self.update('draft',self.draft())
        self.update('commit')
        self.assertEqual(self.project.reviews.membership(self.ids[4])['state'],'included')

    def test_abstract_review_does_not_require_document(self):
        self.prepare()
        self.update('draft',self.draft(review_extent='abstract'))
        self.update('commit')
        self.assertEqual(self.project.reviews.history(self.ids[0])[0]['evidence'][0]['representation'],'abstract')

    def test_sections_and_full_paper_require_verified_opened_document(self):
        self.document(self.ids[0])
        self.prepare()
        for extent in ('sections','full_document'):
            with self.assertRaises(ContractError):self.update('draft',self.draft(review_extent=extent))
        self.update('open')
        self.assertIn('Invented material',self.project.review_sessions.document('session',self.ids[0]).read_text())
        for extent in ('sections','full_document'):
            self.update('draft',self.draft(review_extent=extent))
            self.update('commit')
        self.assertEqual(self.project.reviews.history(self.ids[0])[-1]['review_extent'],'full_document')

    def test_pending_pdf_unavailable_and_no_provenance_leak(self):
        self.project.evidence.preserve_document(self.ids[0],b'%PDF-1.4\nsecret content',representation='pdf',
            media_type='application/pdf',source_uri='fixture://private-provider-arm',legitimate_basis='synthetic_fixture',
            resolver='private-resolver',resolver_version='1',created_at=AT)
        view=self.prepare()
        self.assertEqual(view['pending_documents'],1)
        self.assertFalse(view['document_available'])
        with self.assertRaises(ContractError):self.update('open')
        with self.assertRaises(ContractError):self.project.review_sessions.document('session',self.ids[0])
        rendered=canonical(view)
        for hidden in ('private-provider-arm','private-resolver','fixture_provider','provider-private-query','secret-arm','hidden_model_judgment'):
            self.assertNotIn(hidden,rendered)

    def test_wrong_document_is_not_an_option(self):
        self.document(self.ids[0],valid=False)
        view=self.prepare()
        self.assertEqual(view['review_options'],['metadata','abstract'])

    def test_label_blind_to_existing_human_or_model_events(self):
        self.label(self.ids[0])
        event=replace(self.event(self.ids[0],authority='non_authoritative',producer='model'),rationale='HIDDEN MODEL RATIONALE')
        self.project.reviews.apply(self.project.reviews.plan(event),recorded_at=AT)
        view=self.prepare()
        self.assertIsNone(view['review']['decision'])
        self.assertNotIn('HIDDEN MODEL RATIONALE',canonical(view))
        self.assertNotIn('Invented fixture rationale',canonical(view))
        self.assertNotIn('authority_state',view)

    def test_independent_sessions_do_not_expose_each_others_drafts(self):
        self.prepare()
        self.update('draft',self.draft(rationale='PRIVATE FIRST REVIEW'))
        other=self.project.review_sessions.prepare('independent',reviewer_id='reviewer_two',paper_ids=self.ids)
        self.assertNotIn('PRIVATE FIRST REVIEW',canonical(other))

    def test_independent_non_authoritative_reviews_can_both_commit(self):
        service=self.project.review_sessions
        for session,reviewer in (('first','reviewer_one'),('second','reviewer_two')):
            service.prepare(session,reviewer_id=reviewer,paper_ids=self.ids)
        self.update('draft',self.draft(),session='first')
        self.update('draft',self.draft(decision='excluded',rationale='Independent second explanation'),session='second')
        self.update('commit',session='first')
        self.update('commit',session='second')
        history=self.project.reviews.history(self.ids[0])
        self.assertEqual([x['state'] for x in history],['included','excluded'])
        self.assertTrue(all(x['authority_state']=='non_authoritative' and x['supersedes'] is None for x in history))
        self.assertEqual(self.project.reviews.membership(self.ids[0])['state'],'not_reviewed')
        self.assertNotIn('Independent second explanation',canonical(service.view('first')))

    def test_no_clobber_session_and_stale_autosave(self):
        view=self.prepare()
        with self.assertRaises(FileExistsError):self.prepare()
        self.update('draft',self.draft())
        with self.assertRaises(ContractError):
            self.project.review_sessions.update('session',expected_revision=view['revision'],action='draft',value=self.draft(decision='excluded'))

    def test_non_authoritative_human_is_not_membership(self):
        self.project.review_sessions.prepare('session',reviewer_id='unapproved',paper_ids=self.ids)
        self.update('draft',self.draft())
        self.update('commit')
        self.assertEqual(self.project.reviews.membership(self.ids[0])['state'],'not_reviewed')

    def test_authority_cannot_be_requested_by_unapproved_reviewer(self):
        with self.assertRaises(ContractError):
            self.project.review_sessions.prepare('session',reviewer_id='unapproved',authority_state='human_authorized')

    def test_external_history_change_blocks_session_commit(self):
        self.prepare()
        self.update('draft',self.draft())
        self.label(self.ids[0],'excluded')
        with self.assertRaises(ContractError):self.update('commit')
        self.assertEqual(len(self.project.reviews.history(self.ids[0])),1)

    def test_navigation_and_overview_preserve_all_papers(self):
        self.prepare()
        self.update('draft',self.draft(review_extent=None))
        self.update('navigate','last')
        self.assertEqual(self.project.review_sessions.view('session')['number'],8)
        self.update('navigate','next_partial')
        self.assertEqual(self.project.review_sessions.view('session')['number'],1)
        self.update('navigate','next_incomplete')
        self.assertEqual(self.project.review_sessions.view('session')['number'],2)
        self.update('navigate','previous_incomplete')
        self.assertEqual(self.project.review_sessions.view('session')['number'],1)
        for navigation,number in ((5,5),('first',1),('next',2),('previous',1),('last',8)):
            self.update('navigate',navigation)
            self.assertEqual(self.project.review_sessions.view('session')['number'],number)
        with self.assertRaises(ContractError):self.update('navigate',0)
        self.assertEqual(len(self.project.review_sessions.view('session')['overview']),8)

    def test_neutral_ordering_does_not_mutate_reviews(self):
        self.prepare()
        self.update('draft',self.draft())
        before=self.project.reviews.corpus()
        self.update('ordering','paper_id')
        self.update('ordering','original')
        self.assertEqual(self.project.reviews.corpus(),before)
        self.assertEqual(self.project.review_sessions.view('session')['review']['decision'],'included')

    def test_session_and_review_storage_immutable(self):
        self.prepare()
        self.update('draft',self.draft())
        self.update('commit')
        for table in ('ct_review_sessions','ct_review_session_events','ct_review_events','ct_review_availability'):
            for verb in ('UPDATE','DELETE'):
                with self.subTest(table=table,verb=verb),self.assertRaises(sqlite3.IntegrityError):
                    with connection(self.project.database_path,write=True) as db:
                        db.execute(('DELETE FROM '+table) if verb=='DELETE' else 'UPDATE '+table+' SET '+('event_id=event_id' if table!='ct_review_sessions' else 'session_id=session_id'))

    def test_reads_are_side_effect_free_and_deterministic(self):
        self.prepare()
        before=self.project.database_path.read_bytes()
        view=self.project.review_sessions.view('session')
        self.assertEqual(self.project.review_sessions.view('session'),view)
        self.project.reviews.corpus(states=['not_reviewed'])
        self.assertEqual(self.project.database_path.read_bytes(),before)

    def test_frontend_has_no_stopping_behavior_and_has_safe_controls(self):
        for control in ('first','last','next_partial','next_incomplete','previous_incomplete','jump','record','ordering'):
            self.assertIn(control,HTML)
        self.assertIn('textContent',HTML)
        self.assertNotIn('innerHTML',HTML)
        self.assertNotIn('raw_score',HTML)
        self.assertNotIn('threshold',HTML)

    def test_phase2b_upgrade_preserves_existing_review_and_conservatively_dates_availability(self):
        target=Path(self.temp.name)/'old-project'
        target.mkdir()
        raw=self.config.to_dict()
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:33]):
            create_database(target/self.config.database,raw,AT,'fixture')
            (target/'corpustrail.project.json').write_text(canonical(raw)+'\n',encoding='utf-8')
            old=Project.open(target)
            self.project=old
            pid=self.enroll(99)
            event=self.event(pid)
            # Exact pre-034 ledger fixture; availability did not exist in Phase 2B.
            with connection(old.database_path,write=True) as db:
                from corpustrail._internal.database import latest_config
                db.execute('INSERT INTO ct_review_events '
                    '(event_id,paper_id,membership_state,producer_type,authority_state,supersedes,payload_json,content_sha256,config_event_id) '
                    'VALUES (?,?,?,?,?,?,?,?,?)',
                    (event.event_id,pid,event.state,event.producer_type,event.authority_state,event.supersedes,
                     canonical(event.to_dict()),content_hash(event.to_dict()),latest_config(db)[0]))
            history=old.reviews.history(pid)
            before=old.reviews.membership(pid)
        self.project=Project.upgrade(target,backup='data/backups/phase2b.sqlite3',created_at=LATER)
        self.assertEqual(self.project.reviews.history(pid),history)
        self.assertEqual(self.project.reviews.membership(pid),before)
        with connection(self.project.database_path) as db:
            self.assertEqual(db.execute('SELECT recorded_at FROM ct_review_availability WHERE event_id=?',(event.event_id,)).fetchone()[0],LATER)
        with closing(sqlite3.connect(target/'data/backups/phase2b.sqlite3')) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],33)
            self.assertEqual(db.execute('SELECT payload_json FROM ct_review_events').fetchone()[0],canonical(event.to_dict()))

    def test_verified_document_abstract_has_exact_lineage(self):
        pid=self.ids[4]
        xml=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/fixture.4</article-id><abstract><p>A legitimate synthetic abstract.</p></abstract></article-meta></front><body><p>Invented document body.</p></body></article>'
        self.project.evidence.preserve_document(pid,xml,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://abstract-document',legitimate_basis='synthetic_fixture',resolver='fixture',
            resolver_version='1',created_at=AT)
        self.prepare()
        self.update('navigate',5)
        self.assertIn('abstract',self.project.review_sessions.view('session')['review_options'])
        self.update('draft',self.draft(review_extent='abstract'))
        self.update('commit')
        event=self.project.reviews.history(pid)[0]
        self.assertEqual(event['evidence'][0]['source_uri'],'fixture://abstract-document')

    def test_invalid_enum_drafts_and_unavailable_evidence_fail_closed(self):
        self.prepare()
        for kwargs in ({'sufficiency':'maybe'},{'decision':'reject'},{'review_extent':'fulltext'},{'review_extent':'sections'}):
            with self.assertRaises(ContractError):self.update('draft',self.draft(**kwargs))
        self.assertEqual(self.project.review_sessions.view('session')['counts']['blank'],8)

    def test_cli_review_and_corpus_are_workspace_independent(self):
        with patch('sys.stdout'),patch('sys.stderr'):
            self.assertEqual(main(['review','prepare',str(self.root),'--session-id','session','--reviewer','reviewer_one','--authoritative']),0)
            self.assertEqual(main(['review','status',str(self.root),'--session-id','session']),0)
            self.assertEqual(main(['corpus',str(self.root),'--state','not_reviewed']),0)

    def test_http_origin_csrf_and_resume(self):
        self.prepare()
        server=make_server(self.project,'session',port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(method,path,body=None,headers=None):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                client.request(method,path,body=body,headers=headers or {})
                response=client.getresponse()
                return response.status,response.read().decode(),dict(response.getheaders())
            finally:client.close()
        code,page,headers=request('GET','/')
        self.assertEqual(code,200)
        self.assertEqual(headers['Cache-Control'],'no-store')
        token=re.search("const token='([^']+)'",page).group(1)
        code,body,_=request('GET','/api/state')
        self.assertEqual(code,200)
        state=json.loads(body)
        data=json.dumps({'expected_revision':state['revision'],'action':'draft','value':self.draft()})
        self.assertEqual(request('POST','/api/update',data,{'Content-Type':'application/json'})[0],403)
        good={'Content-Type':'application/json','X-CorpusTrail-CSRF':token}
        self.assertEqual(request('POST','/api/update',data,{**good,'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(request('GET','/api/state',headers={'Host':'evil.invalid'})[0],403)
        self.assertEqual(request('POST','/api/update',data,good)[0],200)
        self.assertEqual(Project.open(self.root).review_sessions.view('session')['review']['decision'],'included')
        self.assertEqual(request('GET','/document?paper_id='+self.ids[0])[0],400)

    @unittest.skipUnless(shutil.which('node'),'optional JavaScript test runner unavailable')
    def test_browser_autosave_insufficient_navigation_and_pending_guard(self):
        script=HTML.split('<script nonce="TOKEN">')[1].split('</script>')[0].replace('TOKEN','fixture-token')
        harness=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements={},radios={sufficiency:[{value:'sufficient'},{value:'insufficient'}],decision:[{value:'included'},{value:'excluded'}]},listeners={},requests=[];
for(const id of ['question','recording_notice','counts','priority','message','title','bib','identifiers','abstract','position','jump','evidence','document','extent','rationale','location','recorded','assigned','ordering','overview','rationale_label','form','go','record'])elements[id]={value:'',textContent:'',disabled:false,children:[],addEventListener:(k,f)=>listeners[id+':'+k]=f,replaceChildren(){this.children=[];},append(b){this.children.push(b);}};
elements.extent.options=['','metadata','abstract','sections','full_document'].map(value=>({value}));
const initial={revision:null,question:'Broad materials corpus?',number:1,total:2,title:'Fixture',authors:[],identifiers:[],review:{sufficiency:null,decision:null,review_extent:null,rationale:'',location:null},review_options:['metadata','abstract'],document_available:false,document_opened:false,pending_documents:1,overview:['blank','blank'],counts:{complete:0,blank:2,insufficient:0,partial:0},recorded:false,recorded_count:0,remaining_count:2,ordering:'original',assigned_order_available:false,mode:'method-blind'};
const context={console,setTimeout,clearTimeout,document:{getElementById:id=>elements[id],querySelector:selector=>(radios[selector.match(/name="([^"]+)"/)[1]]||[]).find(x=>x.checked),querySelectorAll:selector=>selector==='[data-nav]'?[]:radios[selector.match(/name="([^"]+)"/)[1]],createElement:()=>({})},window:{addEventListener:(k,f)=>listeners[k]=f,open:()=>({close(){}})},fetch:async(url,options)=>{if(!options)return {json:async()=>structuredClone(initial)};const request=JSON.parse(options.body);requests.push(request);const state=structuredClone(initial);state.revision='revision-'+requests.length;if(request.action==='draft')state.review=request.value;state.overview=['insufficient','blank'];state.counts={complete:0,blank:1,insufficient:1,partial:0};return {ok:true,json:async()=>state};}};
vm.createContext(context);vm.runInContext(SCRIPT,context);
(async()=>{await new Promise(resolve=>setImmediate(resolve));radios.sufficiency[1].checked=true;radios.decision[0].checked=true;elements.extent.value='metadata';elements.rationale.value='Need more evidence';listeners['form:input']();assert.equal(radios.decision[0].checked,false);assert.equal(radios.decision[0].disabled,true);let warned=false;listeners.beforeunload({preventDefault(){warned=true;}});assert(warned);await vm.runInContext('flush()',context);assert.equal(requests[0].value.decision,null);assert.equal(requests[0].value.sufficiency,'insufficient');assert(elements.counts.textContent.includes('insufficient: 1'));await vm.runInContext("perform('navigate','last')",context);assert.equal(requests[1].action,'navigate');assert.equal(requests[1].expected_revision,'revision-1');assert.equal(elements.extent.options.find(x=>x.value==='sections').disabled,true);assert.equal(elements.document.disabled,true);console.log('browser fixture passed');})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('SCRIPT',json.dumps(script))
        result=subprocess.run([shutil.which('node')],input=harness,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_method_blind_session_identifier_not_exposed(self):
        self.prepare()
        self.assertNotIn('session_id',self.project.review_sessions.view('session'))

    def test_composite_metadata_retains_field_provenance_privately(self):
        record=BibliographicRecord(authors=('Example Researcher',),year=2024,source='Fixture Journal',
            identifiers=(Identifier('doi','10.1234/fixture.0'),))
        body=b'Invented supplemental metadata'
        src=SourceReference('fixture://secondary-private-provider','record-extra',
            'sha256:'+hashlib.sha256(body).hexdigest(),len(body),'second_fixture_provider',AT,identity_status='verified')
        self.project.identities.apply(self.project.identities.plan(record,src))
        self.prepare()
        self.update('draft',self.draft())
        self.update('commit')
        with connection(self.project.database_path) as db:
            packet=json.loads(db.execute('SELECT payload_json FROM ct_review_sessions').fetchone()[0])
        lineage=packet['papers'][0]['canonical_metadata_provenance']
        self.assertEqual(lineage['field_provenance'],self.project.discovery.metadata(self.ids[0])['field_provenance'])
        self.assertEqual(len(lineage['source_observations']),2)
        browser=self.project.review_sessions.view('session')
        self.assertEqual(browser['year'],2024)
        self.assertNotIn('canonical_metadata_provenance',browser)
        self.assertNotIn('secondary-private-provider',canonical(browser))


@unittest.skipUnless(HAS_ML,'optional prioritization extra not installed')
class PrioritizationTests(CurationTests):
    # Inherit curation tests deliberately: ensure they remain valid after numerical imports.
    def train(self):
        for pid,state in zip(self.ids[:5],('included','included','excluded','excluded','insufficient_evidence')):
            self.label(pid,state)
        snapshot=self.project.prioritization.snapshot(label_cutoff=AT,created_at=AT)
        model=self.project.prioritization.train(snapshot['artifact_id'],created_at=AT)
        return snapshot,model

    def test_exact_snapshot_event_ids_and_insufficient_preserved_not_fit(self):
        snapshot,model=self.train()
        self.assertEqual(len(snapshot['rows']),5)
        self.assertEqual([x['label'] for x in snapshot['rows']].count('insufficient_evidence'),1)
        for row in snapshot['rows']:
            self.assertEqual(row['source_record'],self.project.reviews.membership(row['paper_id'])['current_event_id'])
        self.assertNotIn('gap',model['vocabulary'])
        self.assertEqual(model['training_snapshot_id'],snapshot['artifact_id'])

    def test_deterministic_model_and_ranking_reproduction(self):
        snapshot,model=self.train()
        self.assertEqual(TfidfLogistic().fit(snapshot,purpose='operational'),model)
        first=self.project.prioritization.rank(model['artifact_id'],run_id='first',created_at=AT)
        self.assertEqual(self.project.prioritization.rank(model['artifact_id'],run_id='first',created_at=AT),first)
        self.assertEqual(_algorithm.rank(TfidfLogistic(),model,self.project.prioritization.inputs(),created_at=AT,
            population_source_sha256=content_hash(self.project.prioritization.inputs())),first)

    def test_ranking_never_mutates_membership_or_low_tail(self):
        _,model=self.train()
        before=self.project.reviews.corpus()
        ranking=self.project.prioritization.rank(model['artifact_id'],run_id='all',created_at=AT)
        self.assertEqual(len(ranking['scores']),8)
        self.assertEqual(self.project.reviews.corpus(),before)
        self.assertEqual({x['paper_id'] for x in ranking['scores']},set(self.ids))
        self.assertTrue(all(x['non_authoritative'] for x in ranking['scores']))

    def test_temporal_availability_excludes_late_backdated_labels(self):
        for pid,state in zip(self.ids[:4],('included','included','excluded','excluded')):self.label(pid,state)
        later=self.event(self.ids[5])
        self.project.reviews.apply(self.project.reviews.plan(later),recorded_at=LATER)
        snapshot=self.project.prioritization.snapshot(label_cutoff=AT,created_at=LATER)
        self.assertNotIn(self.ids[5],{x['paper_id'] for x in snapshot['rows']})
        self.assertIn(self.ids[5],{x['paper_id'] for x in self.project.prioritization.snapshot(label_cutoff=LATER,created_at=LATER)['rows']})

    def test_future_cutoff_rejected(self):
        self.train()
        with self.assertRaises(ContractError):self.project.prioritization.snapshot(label_cutoff=LATER,created_at=AT)

    def test_model_and_ranking_cannot_be_backdated_before_inputs(self):
        snapshot,_=self.train()
        later=self.project.prioritization.snapshot(label_cutoff=AT,created_at=LATER)
        with self.assertRaises(ContractError):self.project.prioritization.train(later['artifact_id'],created_at=AT)
        model=self.project.prioritization.train(later['artifact_id'],created_at=LATER)
        with self.assertRaises(ContractError):self.project.prioritization.rank(model['artifact_id'],run_id='backdated',created_at=AT)

    def test_model_non_authority_and_question_specific_policy_not_training(self):
        self.train()
        self.label(self.ids[5],authority='non_authoritative',producer='model')
        self.label(self.ids[6],authority='non_authoritative',reviewer='reviewer_two')
        snapshot=self.project.prioritization.snapshot(label_cutoff=AT,created_at=AT)
        self.assertEqual(len(snapshot['rows']),5)
        with self.assertRaises(ContractError):
            self.project.reviews.plan(replace(self.event(self.ids[7]),policy_id='systematic-review-question/v1'))

    def test_rerank_new_lineage_does_not_overwrite_run(self):
        snapshot,model=self.train()
        old=self.project.prioritization.rank(model['artifact_id'],run_id='first',created_at=AT)
        self.label(self.ids[5],at=LATER)
        updated=self.project.prioritization.snapshot(label_cutoff=LATER,created_at=LATER,parent_snapshot_id=snapshot['artifact_id'])
        new=self.project.prioritization.train(updated['artifact_id'],parent_model_id=model['artifact_id'],created_at=LATER)
        result=self.project.prioritization.rank(new['artifact_id'],run_id='second',created_at=LATER,previous_run_id='first')
        self.assertEqual(self.project.prioritization.run('first'),old)
        self.assertEqual(result['previous_run_id'],'first')
        self.assertEqual(new['parent_model_id'],model['artifact_id'])
        with self.assertRaises(ContractError):self.project.prioritization.rank(new['artifact_id'],run_id='first',created_at=LATER)

    def test_training_and_run_tables_immutable(self):
        _,model=self.train()
        self.project.prioritization.rank(model['artifact_id'],run_id='first',created_at=AT)
        for table in ('ct_priority_artifacts','ct_priority_runs'):
            with self.assertRaises(sqlite3.IntegrityError):
                with connection(self.project.database_path,write=True) as db:db.execute('DELETE FROM '+table)

    def test_priority_queue_method_blind_and_no_automatic_rerank(self):
        _,model=self.train()
        ranking=self.project.prioritization.rank(model['artifact_id'],run_id='first',created_at=AT)
        self.prepare()
        view=self.update('bind_ranking','first')
        self.assertEqual(view['ordering'],'original')
        view=self.update('ordering','priority')
        for hidden in ('raw_score','method','training_snapshot_id','model_id','priority'):
            self.assertNotIn(hidden,view)
        self.assertEqual(view['ordering'],'assigned')
        self.assertEqual(view['total'],8)
        old_order=view['overview']
        self.project.prioritization.rank(model['artifact_id'],run_id='second',created_at=LATER,previous_run_id='first')
        self.assertEqual(self.project.review_sessions.view('session')['overview'],old_order)
        self.update('navigate','last')
        self.assertEqual(self.project.review_sessions.view('session')['paper_id'],ranking['scores'][-1]['paper_id'])

    def test_operational_priority_notice_separate_from_decision(self):
        _,model=self.train()
        self.project.prioritization.rank(model['artifact_id'],run_id='first',created_at=AT)
        self.prepare(mode='operational')
        view=self.update('bind_ranking','first')
        self.assertIn('priority',view)
        self.assertIsNone(view['review']['decision'])
        self.assertIn('not an eligibility',view['priority_notice'])

    def test_mismatched_ranking_population_rejected(self):
        _,model=self.train()
        self.project.prioritization.rank(model['artifact_id'],run_id='subset',paper_ids=self.ids[:2],created_at=AT)
        self.prepare()
        with self.assertRaises(ContractError):self.update('bind_ranking','subset')

    def test_evidence_changes_require_new_frozen_session(self):
        _,model=self.train()
        self.prepare()
        self.document(self.ids[0])
        self.project.prioritization.rank(model['artifact_id'],run_id='new-evidence',created_at=AT)
        with self.assertRaises(ContractError):self.update('bind_ranking','new-evidence')

    def test_rank_provenance_records_exact_feature_sources(self):
        _,model=self.train()
        self.project.prioritization.rank(model['artifact_id'],run_id='all',created_at=AT)
        provenance=self.project.prioritization.run_provenance('all')
        self.assertEqual(set(provenance['feature_sources']),set(self.ids))
        self.assertEqual(provenance['feature_sources'][self.ids[0]]['metadata']['field_provenance'],
                         self.project.discovery.metadata(self.ids[0])['field_provenance'])
        self.assertEqual(Project.open(self.root).prioritization.run_provenance('all'),provenance)

    def test_missing_abstract_kept_in_ranking(self):
        _,model=self.train()
        run=self.project.prioritization.rank(model['artifact_id'],run_id='all',created_at=AT)
        row=next(x for x in run['scores'] if x['paper_id']==self.ids[4])
        self.assertEqual(row['evidence_inputs_used'],['title'])

    def test_label_cutoff_remains_frozen_after_human_supersession(self):
        initial,_=self.train()
        self.label(self.ids[0],'excluded',at=LATER)
        old=self.project.prioritization.snapshot(label_cutoff=AT,created_at=LATER)
        by_id={x['paper_id']:x for x in old['rows']}
        self.assertEqual(by_id[self.ids[0]]['label'],'include')
        self.assertEqual(by_id[self.ids[0]]['source_record'],next(x for x in initial['rows'] if x['paper_id']==self.ids[0])['source_record'])


if __name__=='__main__':unittest.main()
