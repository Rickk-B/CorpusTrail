"""Real RIS/identity/population/evidence/authority integration, entirely offline."""
import base64
from contextlib import closing
import hashlib
from importlib.resources import files
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

from corpustrail._internal.database import connection
from corpustrail._internal.pipeline import artifact
from corpustrail._internal.values import ContractError
from corpustrail.application.ris import RISController
from corpustrail.application import _workflow_files as workflow_files
from corpustrail.demo import create
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.imports.ris import parse, bibliography, serialize, MAX_BYTES
from corpustrail.imports.service import RISService
from corpustrail.project import Project, ProjectConfig, ReviewPolicy

AT='2026-01-01T00:00:00+00:00'


class RISExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        locks=patch('corpustrail.application.project_use.lock_directory',return_value=Path(self.temp.name)/'locks')
        locks.start();self.addCleanup(locks.stop)
        self.root=Path(self.temp.name)/'project'
        self.project=Project.create(self.root,ProjectConfig('ris-test','Synthetic RIS test','Invented metadata only',
            review=ReviewPolicy(scope='Synthetic sensor literature',authorized_reviewers=('reviewer',))),created_by='fixture',created_at=AT)
        self.service=RISService(self.project,clock=lambda:AT);self.controller=RISController()

    def upload(self,body):
        key=uuid.uuid4().hex
        for offset in range(0,len(body),32768):
            part=body[offset:offset+32768]
            self.controller.upload(self.project,request_id=key,offset=offset,body=base64.b64encode(part).decode(),
                final=offset+len(part)==len(body),sha256='sha256:'+hashlib.sha256(body).hexdigest(),filename='input.ris')
        return key

    def prepare(self,body):return self.service.prepare_import(request_id=uuid.uuid4().hex,upload=self.upload(body),actor='fixture',name='Imported test candidates')
    def commit(self,value,partial=False):
        while value['status']!='complete':
            value=self.service.commit_import(key=value['id'],preview_sha256=value['preview_sha256'],confirmed=True,accept_partial=partial)
        return value
    def body(self):return files('corpustrail.resources').joinpath('ris-demo-initial.ris').read_bytes()
    def counts(self):
        with connection(self.project.database_path) as db:
            return {t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('paper_entities','ct_paper_observations','ct_review_events','ct_population_versions','knowledge_assertions','ct_reference_assignments')}

    def test_preview_is_scientifically_read_only_then_explicit_import(self):
        before=self.counts();value=self.prepare(self.body());self.assertEqual(self.counts(),before)
        self.assertTrue(all(row['paper_handle'] is None for row in value['items']))
        self.assertEqual(value['counts'],{'new':3,'linked':0,'parse_error':0,'identity_issue':0})
        with self.assertRaises(ContractError):self.service.commit_import(key=value['id'],preview_sha256=value['preview_sha256'],confirmed=False)
        result=self.commit(value);self.assertEqual(result['result']['unique_canonical_publications'],3)
        self.assertEqual(self.counts()['ct_review_events'],0);self.assertEqual(self.counts()['knowledge_assertions'],0)
        self.assertTrue(all(r['state']=='not_reviewed' for r in self.project.reviews.corpus()))
        self.assertEqual(artifact(self.project,result['source_sha256']).read_bytes(),self.body())
        population=result['result']['population'];self.assertTrue(self.project.populations.verify(population['version_id']))

    def test_unicode_variants_multiline_and_no_fuzzy_title_merge(self):
        body=('TY  - JOUR\r\nT1  - Δοκιμή — 光子\r\nA1  - Ирина, Zoë\r\nY1  - 2024/03/02\r\nJO  - Revue\r\nN2  - One line\r\n      Second line\r\nER  - \r\n\r\nTY  - JOUR\r\nTI  - Δοκιμή — 光子\r\nER  - \r\n').encode()
        rows=parse(body);self.assertEqual(rows[0]['record']['abstract'],'One line\nSecond line')
        self.assertEqual(rows[0]['record']['year'],2024);self.assertIsNone(rows[1]['record']['abstract'])
        result=self.commit(self.prepare(body));self.assertEqual(result['result']['unique_canonical_publications'],2)

    def test_partial_failure_preserves_failed_original_and_requires_ack(self):
        body=files('corpustrail.resources').joinpath('ris-demo-import.ris').read_bytes()
        value=self.prepare(body);self.assertTrue(value['partial_source']);self.assertEqual(value['counts']['parse_error'],1)
        with self.assertRaises(ContractError):self.commit(value)
        self.assertEqual(self.counts()['paper_entities'],0)
        result=self.commit(value,True);self.assertEqual(result['result']['unique_canonical_publications'],3)
        self.assertEqual(result['items'][-1]['status'],'parse_error');self.assertIsNone(result['items'][-1]['paper_handle'])
        self.assertEqual(artifact(self.project,result['source_sha256']).read_bytes(),body)
        self.assertIn('partial source',result['result']['population']['name'])

    def test_unicode_line_separator_and_taglike_abstract_roundtrip(self):
        abstract='First\u2028same abstract\nER  - this is text\nTY  - also text'
        raw={'title':'Synthetic','abstract':abstract,'authors':[],'year':2020,'source':None,'identifiers':[]}
        parsed=parse(serialize([raw]))
        self.assertEqual(len(parsed),1);self.assertEqual(parsed[0]['record']['abstract'],abstract)

    def test_old_parse_results_and_original_bytes_survive_parser_changes(self):
        value=self.commit(self.prepare(self.body()))
        with patch('corpustrail.imports.service.implementation_hash',return_value='f'*64):
            self.assertEqual(self.service.inspect(value['id'])['status'],'complete')
            self.assertEqual(self.service.source_bytes(value['id']),self.body())
        failed=self.prepare(b'\xff')
        self.assertFalse(failed['record_count_known'])

    def test_packaged_scope_options_have_real_start_tags(self):
        from html.parser import HTMLParser
        class Options(HTMLParser):
            def __init__(self):super().__init__();self.inside=False;self.values=[]
            def handle_starttag(self,tag,attrs):
                values=dict(attrs)
                if tag=='select':self.inside=values.get('id')=='ris-scope'
                if self.inside and tag=='option':self.values.append(values.get('value'))
            def handle_endtag(self,tag):
                if tag=='select':self.inside=False
        parser=Options();parser.feed(files('corpustrail.local_app').joinpath('assets/ris.html').read_text())
        self.assertEqual(parser.values,['','confirmed','all_candidates','population'])

    def test_exact_replay_and_repeated_import_keep_identity_and_observations(self):
        value=self.commit(self.prepare(self.body()));before=self.counts()
        self.commit(value);self.assertEqual(self.counts(),before)
        repeated=self.commit(self.prepare(self.body()));self.assertEqual(self.counts()['paper_entities'],3)
        self.assertEqual(repeated['result']['counts']['new'],0)
        self.assertEqual(repeated['result']['counts']['linked'],3)
        self.assertEqual(repeated['result']['unique_canonical_publications'],3)
        # Same source, locator and frozen time reuse exact scientific receipts.
        self.assertEqual(self.counts()['ct_paper_observations'],before['ct_paper_observations'])

    def test_roundtrip_supported_fields_and_opaque_origins_never_transfer_authority(self):
        body=('TY  - BOOK\nTI  - Unicode naïve 光子\nAU  - Doe, Zoë\nPY  - 2020\nJF  - Invented title\nAB  - First\n      Second\nVL  - 3\nSP  - 12\nEP  - 14\nKW  - 光子\nER  - \n').encode()
        self.commit(self.prepare(body));preview=self.service.export_preview(scope='all_candidates',actor='fixture')
        key=uuid.uuid4().hex;self.service.export_commit(key=key,scope='all_candidates',actor='fixture',version_id=None,preview_sha256=preview['preview_sha256'],confirmed=True)
        exported=self.service.export_bytes(key);rows=parse(exported)
        self.assertEqual(rows[0]['fields']['TY'],['BOOK']);self.assertEqual(rows[0]['fields']['VL'],['3'])
        self.assertEqual(rows[0]['record']['abstract'],'First\nSecond')
        before=len(self.project.identities.papers());self.commit(self.prepare(exported))
        self.assertEqual(len(self.project.identities.papers()),before)
        self.assertEqual(self.counts()['ct_review_events'],0)
        self.assertEqual(self.project.discovery.metadata(self.project.identities.papers()[0])['fields']['title'],'Unicode naïve 光子')

    def test_malformed_records_invalid_identifiers_and_utf8_are_not_judgments(self):
        for body in (b'TY  - JOUR\nTI  - unterminated',b'TY  - JOUR\nTI  - X\nDO  - invalid\nER  - \n',b'\xff'):
            with self.subTest(body=body):
                result=self.commit(self.prepare(body),True)
                self.assertEqual(result['result']['unique_canonical_publications'],0)
        self.assertEqual(self.counts()['ct_review_events'],0);self.assertEqual(self.counts()['paper_entities'],0)
        self.assertTrue(parse(b'TY  - JOUR\nTI  - x\x00\nER  - ')[0]['file_error'])
        with self.assertRaises(ContractError):parse(b'x'*(MAX_BYTES+1))

    def test_exact_conflicting_owners_remain_unresolved(self):
        initial=b'TY  - JOUR\nTI  - One\nDO  - 10.1234/one\nER  - \nTY  - JOUR\nTI  - Two\nPM  - 1234\nER  - \n'
        self.commit(self.prepare(initial));before=self.counts()
        value=self.prepare(b'TY  - JOUR\nTI  - Conflict\nDO  - 10.1234/one\nPM  - 1234\nER  - \n')
        self.assertEqual(value['counts']['identity_issue'],1);self.assertEqual(value['items'][0]['status'],'identity_issue')
        result=self.commit(value,True);self.assertEqual(result['result']['unique_canonical_publications'],0)
        self.assertEqual(self.counts()['paper_entities'],before['paper_entities'])
        self.assertEqual(self.counts()['ct_paper_observations'],before['ct_paper_observations'])

    def test_interrupted_after_sql_commit_reconciles_exact_native_receipts(self):
        value=self.prepare(self.body());original=workflow_files.publish
        def fail(path,payload):
            if 'chunks' in path.parts:raise OSError('controlled interruption after native commit')
            return original(path,payload)
        with patch('corpustrail.imports.service.files.publish',side_effect=fail):
            with self.assertRaises(OSError):self.commit(value)
        self.assertEqual(self.counts()['paper_entities'],3)
        result=self.commit(value);self.assertEqual(result['result']['counts']['new'],3)
        self.assertEqual(self.counts()['ct_paper_observations'],3)

    def test_interrupted_native_chunk_rolls_back_and_explicit_retry_works(self):
        value=self.prepare(self.body());original=self.project.identities.__class__._apply;calls=0
        def fail(owner,*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('controlled transaction interruption')
            return original(owner,*args,**kwargs)
        with patch('corpustrail.identity.service.IdentityService._apply',new=fail):
            with self.assertRaises(OSError):self.commit(value)
        self.assertEqual(self.counts()['paper_entities'],0)
        self.assertEqual(self.commit(value)['status'],'complete')

    def test_stale_preview_refused_and_prior_work_preserved(self):
        value=self.prepare(self.body());self.commit(self.prepare(b'TY  - JOUR\nTI  - Other\nER  - \n'))
        with self.assertRaises(ContractError):self.commit(value)
        self.assertEqual(self.counts()['paper_entities'],1)

    def test_export_requires_scope_and_membership_and_rejects_stale_selection(self):
        self.commit(self.prepare(self.body()))
        with self.assertRaises(ContractError):self.service.export_preview(scope='confirmed',actor='fixture')
        with self.assertRaises(ContractError):self.service.export_preview(scope='',actor='fixture')
        plan=self.service.export_preview(scope='all_candidates',actor='fixture')
        self.commit(self.prepare(b'TY  - JOUR\nTI  - Fourth\nER  - \n'))
        with self.assertRaises(ContractError):self.service.export_commit(key=uuid.uuid4().hex,scope='all_candidates',actor='fixture',version_id=None,preview_sha256=plan['preview_sha256'],confirmed=True)

    def test_attachments_and_script_metadata_are_never_executed_or_followed(self):
        value=self.commit(self.prepare(b'TY  - JOUR\nTI  - <script>alert(1)</script>\nL1  - file:///private/original.pdf\nUR  - https://example.invalid/private\nN1  - included=true; reviewed=true\nER  - \n'))
        self.assertEqual(value['status'],'complete');self.assertEqual(self.counts()['ct_review_events'],0)
        self.assertEqual(self.project.evidence.representations(self.project.identities.papers()[0]),[])

    def test_upload_retry_mismatch_and_unsafe_names_fail_closed(self):
        body=self.body();key=uuid.uuid4().hex;values=dict(request_id=key,offset=0,body=base64.b64encode(body).decode(),final=True,sha256='sha256:'+hashlib.sha256(body).hexdigest(),filename='safe.ris')
        self.controller.upload(self.project,**values);self.controller.upload(self.project,**values)
        with self.assertRaises(ContractError):self.controller.upload(self.project,**{**values,'body':base64.b64encode(b'changed').decode()})
        for name in ('../data.ris','/etc/passwd','C:\\private.ris','bad\n.ris'):
            with self.subTest(name=name),self.assertRaises(ContractError):self.controller.upload(self.project,**{**values,'request_id':uuid.uuid4().hex,'filename':name})
        with self.assertRaises(ContractError):self.controller.upload(self.project,**{**values,'sha256':'sha256:'+'0'*64})
        self.assertEqual(self.counts()['paper_entities'],0)

    def test_concurrent_execution_lease_is_fail_closed(self):
        value=self.prepare(self.body())
        with closing(workflow_files.operation_lease(self.project,'ris-execution')):
            with self.assertRaises(ContractError):self.commit(value)
        self.assertEqual(self.counts()['paper_entities'],0)
        self.assertEqual(self.commit(value)['status'],'complete')

    def test_import_rejects_legacy_without_automatic_migration(self):
        from corpustrail._internal.database import migrations
        root=Path(self.temp.name)/'schema37'
        existing=migrations()
        with patch('corpustrail._internal.database.migrations',return_value=existing[:37]):
            old=Project.create(root,self.project.config,created_by='fixture',created_at=AT)
        with connection(old.database_path) as db:before=list(db.iterdump())
        upload=uuid.uuid4().hex;body=self.body()
        RISController().upload(old,request_id=upload,offset=0,body=base64.b64encode(body).decode(),final=True,
            sha256='sha256:'+hashlib.sha256(body).hexdigest(),filename='old.ris')
        with self.assertRaises(ContractError):RISService(old).prepare_import(request_id=uuid.uuid4().hex,upload=upload,actor='fixture',name='Legacy import')
        with connection(old.database_path) as db:self.assertEqual(list(db.iterdump()),before)

    def test_operational_origin_tokens_do_not_leak_into_method_blind_views(self):
        from corpustrail.curation.guided import GuidedReviewService
        from corpustrail.application.review import ReviewController
        from corpustrail._internal.values import content_hash, canonical
        self.commit(self.prepare(self.body()));review=GuidedReviewService(self.project)
        created=review.create(command_id=uuid.uuid4().hex,reviewer_id='reviewer',selection='all',
            population_sha256=content_hash(review.population('all')),config_event_id=self.project.configuration_history()[-1]['event_id'],mode='method-blind')
        view=canonical(ReviewController().view(self.project,created['session_id'].split(':')[1]))
        for private in ('corpustrail.ris','ris://','source_provenance','import_interface'):
            self.assertNotIn(private,view)

    def test_reopen_inspection_does_not_replay_import(self):
        value=self.commit(self.prepare(self.body()));before=self.counts()
        reopened=RISService(Project.open(self.root),clock=lambda:AT)
        self.assertEqual(reopened.inspect(value['id'])['status'],'complete');self.assertEqual(self.counts(),before)

    def test_review_frozen_before_import_and_explicit_publication_only(self):
        from corpustrail.curation.guided import GuidedReviewService
        from corpustrail.curation.sessions import _load
        from corpustrail._internal.values import content_hash
        self.commit(self.prepare(self.body()));review=GuidedReviewService(self.project)
        session=review.create(command_id=uuid.uuid4().hex,reviewer_id='reviewer',selection='all',
            population_sha256=content_hash(review.population('all')),
            config_event_id=self.project.configuration_history()[-1]['event_id'],mode='method-blind')['session_id']
        def state():
            with connection(self.project.database_path) as db:return _load(db,session)
        before=state()[0]
        self.commit(self.prepare(files('corpustrail.resources').joinpath('ris-demo-import.ris').read_bytes()),True)
        self.assertEqual(state()[0],before);self.assertEqual(len(self.project.identities.papers()),5)
        def command(action,value=None):return review.command(session,command_id=uuid.uuid4().hex,expected_revision=state()[2],action=action,value=value)
        command('skip');self.assertEqual(self.counts()['ct_review_events'],0)
        command('save_next',{'sufficiency':'sufficient','decision':'included','review_extent':'metadata','rationale':'Invented explicit human reading','location':None})
        self.assertEqual(self.counts()['ct_review_events'],1)
        self.assertTrue(all(v['state']=='not_reviewed' for v in self.project.reviews.corpus()))
        command('finish',{'preserve_undecided':True})
        self.assertTrue(all(v['state']=='not_reviewed' for v in self.project.reviews.corpus()))
        command('prepare_publication')
        command('publish',{'plan_sha256':state()[1]['publication_plan']['sha256'],'confirm_authority':True})
        exported=self.service.export_preview(scope='confirmed',actor='fixture')
        self.assertEqual(exported['record_count'],1)
        self.assertEqual(self.service.export_preview(scope='all_candidates',actor='fixture')['record_count'],5)

    def test_real_http_security_sample_and_readonly_pages(self):
        import http.client
        import json
        import re
        import threading
        from corpustrail.application.projects import ProjectController
        from corpustrail.local_app import make_server
        from corpustrail.imports.service import SCHEMA
        controller=ProjectController(projects_root=self.root.parent,project=self.project)
        self.addCleanup(controller.close)
        server=make_server(controller=controller,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(10),server.server_close()))
        def request(path,method='GET',payload=None,auth=True):
            with closing(http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)) as client:
                headers={'Origin':'http://127.0.0.1:'+str(server.server_port)}
                if auth:headers.update({'X-CorpusTrail-Session':session,'X-CorpusTrail-CSRF':session})
                if payload:headers['Content-Type']='application/json'
                client.request(method,path,json.dumps(payload) if payload else None,headers)
                response=client.getresponse();return response.status,response.read()
        _,html=request('/home',auth=False)
        session=re.search(b'name="corpustrail-session" content="([^"]+)"',html)[1].decode()
        before=self.counts()
        self.assertEqual(request('/ris')[0],200)
        self.assertEqual(request('/api/v1/ris/history')[0],200)
        self.assertEqual(request('/api/v1/ris/sample')[1],files('corpustrail.resources').joinpath('ris-demo-import.ris').read_bytes())
        self.assertEqual(request('/api/v1/ris/history',auth=False)[0],403)
        self.assertEqual(request('/api/v1/ris/history?path=/etc/passwd')[0],400)
        self.assertEqual(request('/api/v1/ris/preview','POST',{'schema':SCHEMA},auth=False)[0],403)
        self.assertEqual(self.counts(),before)

    def test_pagination_resource_budget_and_no_authority_for_many_candidates(self):
        body=''.join('TY  - JOUR\nTI  - Synthetic '+str(i)+'\nER  - \n' for i in range(61)).encode()
        value=self.prepare(body);self.assertEqual(len(value['items']),20)
        first=self.service.commit_import(key=value['id'],preview_sha256=value['preview_sha256'],confirmed=True)
        self.assertEqual(first['processed'],20);self.assertEqual(first['status'],'partial')
        result=self.commit(first);self.assertEqual(result['result']['unique_canonical_publications'],61)
        self.assertEqual(self.service.inspect(value['id'],offset=60)['items'][0]['index'],61)
        self.assertEqual(self.counts()['ct_review_events'],0)

    def test_scoped_demo_has_no_reviews_and_refuses_existing_destination(self):
        path=Path(self.temp.name)/'demo';result=create(path);demo=Project.open(path)
        self.assertEqual(result['canonical_candidates'],3);self.assertFalse(result['network_used'])
        self.assertTrue(demo.config.review.scope);self.assertEqual(demo.config.review.authorized_reviewers,('demo_reviewer',))
        with connection(demo.database_path) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_review_events').fetchone()[0],0)
        with self.assertRaises(FileExistsError):create(path)


if __name__=='__main__':unittest.main()
