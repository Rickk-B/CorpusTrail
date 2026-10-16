"""Scientific population contracts over actual project services; synthetic data only."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from corpustrail._internal.database import connection, migrations
from corpustrail._internal.pipeline import preserve
from corpustrail._internal.values import ContractError, canonical, content_hash
from corpustrail.application.populations import PopulationController
from corpustrail.application.review import ReviewController
from corpustrail.curation.guided import GuidedReviewService
from corpustrail.curation.sessions import _load
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.populations import ImportedSource
from corpustrail.project import Project, ProjectConfig, ProviderConfig, ReviewPolicy
from corpustrail.providers import metadata_provider
from corpustrail.providers.network import HttpResponse

AT = '2026-01-01T00:00:00+00:00'


def fingerprint(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class PopulationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ct-population-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'project'
        self.project = Project.create(self.root, ProjectConfig('population-fixture', 'Invented materials',
            'Synthetic topic', providers=(ProviderConfig('openalex','openalex'),),
            review=ReviewPolicy(scope='Broad synthetic materials',authorized_reviewers=('curator',))),created_by='fixture',created_at=AT)
        self.service = self.project.populations
        self.ids = [self.enroll(str(i), doi='10.1234/p.'+str(i)) for i in range(3)]

    def enroll(self, key, *, uri='fixture://observations', doi=None, ids=(), body=None):
        record = BibliographicRecord('Invented scientific title — 材料', authors=('Synthetic Author',),
            identifiers=tuple(ids) + ((Identifier('doi',doi),) if doi else ()))
        raw = body or canonical({'key':key,'uri':uri,'record':record.title}).encode()
        sha = preserve(self.project, raw, 'application/json', AT)
        source = SourceReference(uri,key,sha,len(raw),'synthetic-import-adapter',AT,identity_status='verified')
        return self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)

    def fields(self, sources=None, parent=None, **extra):
        return {'request_id':uuid.uuid4().hex,'name':'Synthetic candidate set','actor':'fixture',
            'sources':sources or [{'kind':'all'}],'parent':parent,**extra}

    def freeze(self, sources=None, parent=None, accept_unresolved=False, **extra):
        fields = self.fields(sources,parent,**extra)
        preview = self.service.preview(**fields)
        return self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'],created_at=AT,accept_unresolved=accept_unresolved)

    def discover(self, run='fixture-discovery'):
        provider = metadata_provider('openalex')
        body = json.dumps({'results':[
            {'id':'https://openalex.org/W1','doi':'10.1234/p.0','title':'Repeated observation'},
            {'id':'https://openalex.org/W2','doi':'10.1234/discovered.4','title':'Discovered candidate'},
            {'id':'https://openalex.org/W3','doi':'invalid doi','title':'Preserved identity conflict'}],
            'meta':{'count':3,'next_cursor':None}}).encode()
        class Transport:
            network = False
            def request(self,url,**kwargs): return HttpResponse(200,{},body,url)
        plan = self.project.discovery.plan(provider,run_id=run,query='synthetic materials',created_at=AT)
        self.project.discovery.execute(plan,provider,transport=Transport(),confirm_external=True,clock=lambda:AT)
        self.project.discovery.canonicalize(run,approve_new_identities=True,approve_aliases=True)
        return run

    def test_preview_and_all_read_views_are_byte_preserving(self):
        before = fingerprint(self.root)
        preview = self.service.preview(**self.fields())
        self.assertEqual(preview['member_count'],3)
        self.assertEqual(self.service.versions()['total'],0)
        self.assertEqual(fingerprint(self.root),before)
        version = self.freeze()['version_id']; before = fingerprint(self.root)
        for action in (lambda:self.service.inspect(version),lambda:self.service.members(version),
                       lambda:self.service.lineage(version),lambda:self.service.issues(version),
                       lambda:self.service.verify(version),lambda:self.service.versions()): action()
        self.assertEqual(fingerprint(self.root),before)
        self.assertTrue(all(self.project.reviews.membership(p)['state']=='not_reviewed' for p in self.ids))
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))

    def test_snapshot_successor_preserves_earlier_members_and_identity(self):
        first = self.freeze(); old = self.service.members(first['version_id'])
        pid = self.enroll('later',doi='10.1234/later.5')
        self.enroll('same-new-alias',uri='fixture://second',doi='10.1234/p.0',ids=(Identifier('pmid','123456'),))
        next_version = self.freeze(parent=first['version_id'])
        self.assertEqual(next_version['version'],2);self.assertEqual(next_version['member_count'],4)
        self.assertEqual(self.service.members(first['version_id']),old)
        self.assertNotIn(pid,[x['paper_id'] for x in old['items']])
        self.assertTrue(self.service.verify(first['version_id'])['verified'])
        self.assertEqual(Project.open(self.root).populations.inspect(first['version_id']),self.service.inspect(first['version_id']))

    def test_deterministic_union_retains_observations_not_duplicate_publications(self):
        self.enroll('repeated',uri='fixture://independent-source',doi='10.1234/p.0')
        a = self.freeze([{'kind':'selection','paper_ids':self.ids[:2]}])
        b = self.freeze([{'kind':'selection','paper_ids':self.ids[1:]}])
        sources = [{'kind':'version','version_id':x['version_id']} for x in (a,b)]
        one = self.freeze(sources); two = self.freeze(list(reversed(sources)))
        for key in ('member_count','lineage_count','manifest_sha256','members_sha256','parents'):
            self.assertEqual(one[key],two[key])
        self.assertEqual(one['member_count'],3);self.assertEqual(one['lineage_count'],4)
        self.assertEqual(one['overlapping_publications'],1)
        self.assertEqual(len(self.project.identities.observations(self.ids[0])),2)

    def test_doi_missing_and_similar_titles_remain_distinct_exact_ids(self):
        a = self.enroll('no-doi-a');b = self.enroll('no-doi-b')
        result = self.freeze([{'kind':'selection','paper_ids':[b,a,b]}])
        self.assertNotEqual(a,b);self.assertEqual(result['member_count'],2)
        self.assertEqual([x['paper_id'] for x in self.service.members(result['version_id'])['items']],sorted((a,b)))

    def test_discovery_run_and_union_preserve_unlinked_issues(self):
        run = self.discover()
        fields = self.fields([{'kind':'discovery','run_id':run}]);preview = self.service.preview(**fields)
        self.assertEqual(preview['member_count'],2);self.assertEqual(preview['unresolved_count'],1)
        before = fingerprint(self.root)
        with self.assertRaises(ContractError):self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'])
        self.assertEqual(fingerprint(self.root),before)
        result = self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'],accept_unresolved=True)
        self.assertEqual(len(self.service.issues(result['version_id'])['items']),1)
        union = self.freeze([{'kind':'version','version_id':result['version_id']},{'kind':'all'}],accept_unresolved=True)
        self.assertTrue(union['member_count'] >= 4)

    def test_running_or_unknown_sources_are_refused_without_network(self):
        for source in ({'kind':'discovery','run_id':'unknown'},{'kind':'bibtex','path':'/private/file'},
                       {'kind':'selection','paper_ids':['../../etc/passwd']},{'kind':'import_interface'}):
            with self.assertRaises(ContractError):self.service.preview(**self.fields([source]))

    def test_import_interface_is_origin_independent_and_confers_no_trust(self):
        body = b'{"synthetic_export": ["one", "two"]}'
        shared = self.enroll('import-a',uri='fixture://export',doi='10.1234/p.0',body=body)
        other = self.enroll('import-b',uri='fixture://export',doi='10.1234/imported.6',body=body)
        observations = [x for pid in (shared,other) for x in self.project.identities.observations(pid) if x['source']['source_uri']=='fixture://export']
        source = ImportedSource('synthetic-export-v1','synthetic-adapter','v1',observations[0]['source']['source_sha256'],
            tuple(x['observation_id'] for x in observations))
        result = self.service.freeze_import_source(source,request_id=uuid.uuid4().hex,name='Synthetic imported-source interface',actor='fixture')
        self.assertEqual(result['member_count'],2)
        self.assertEqual(self.project.identities.exact_owner(Identifier('doi','10.1234/p.0')),self.ids[0])
        union = self.freeze([{'kind':'version','version_id':result['version_id']},{'kind':'all'}])
        self.assertEqual(union['member_count'],4)
        self.assertTrue(all(not self.project.evidence.representations(p) and not self.project.reviews.history(p) for p in (shared,other)))
        with self.assertRaises(ContractError):self.service.freeze_import_source(replace(source,artifact_sha256='sha256:'+'0'*64),
            request_id=uuid.uuid4().hex,name='Invalid',actor='fixture')

    def test_changed_sources_or_config_invalidate_preview(self):
        fields = self.fields();preview = self.service.preview(**fields)
        self.enroll('after-preview')
        with self.assertRaises(ContractError):self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'])
        preview = self.service.preview(**fields)
        self.project.configure(replace(self.project.config,config_version=2,name='Edited name'),
            expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
        with self.assertRaises(ContractError):self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'])

    def test_replay_survives_restart_and_changed_request_is_refused(self):
        fields = self.fields();preview = self.service.preview(**fields)
        original = self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'])
        before = fingerprint(self.root);self.enroll('later')
        before = fingerprint(self.root)
        result = Project.open(self.root).populations.create(**fields,expected_preview_sha256=preview['preview_sha256'])
        self.assertTrue(result['replayed']);self.assertEqual(result['version_id'],original['version_id'])
        self.assertEqual(fingerprint(self.root),before)
        with self.assertRaises(ContractError):self.service.create(**{**fields,'name':'Altered'},expected_preview_sha256=preview['preview_sha256'])

    def test_immutable_tables_and_integrity_detection(self):
        result = self.freeze();vid = result['version_id']
        for table in ('ct_population_versions','ct_population_members','ct_population_lineage'):
            with self.assertRaises(sqlite3.IntegrityError):
                with connection(self.project.database_path,write=True) as db:db.execute('DELETE FROM '+table)
        with connection(self.project.database_path,write=True) as db:
            db.execute('DROP TRIGGER ct_population_members_no_update')
            db.execute("UPDATE ct_population_members SET identity_json='{}' WHERE version_id=?",(vid,))
        with self.assertRaises(ContractError):self.service.verify(vid)
        with self.assertRaises(ContractError):self.service.members(vid)

    def test_transaction_failure_rolls_back_every_version_row(self):
        fields = self.fields();preview = self.service.preview(**fields)
        before = fingerprint(self.root)
        def fail(value):
            if isinstance(value,dict) and 'entity' in value:raise RuntimeError('controlled interruption')
            return canonical(value)
        with patch('corpustrail.populations.service.canonical',side_effect=fail):
            with self.assertRaises(RuntimeError):self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'])
        self.assertEqual(self.service.versions()['total'],0)
        self.assertEqual(fingerprint(self.root),before)
        self.assertEqual(self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'])['member_count'],3)

    def test_frozen_review_link_is_persistent_and_method_blind(self):
        version = self.freeze(name='private-provider-arm')
        service = GuidedReviewService(self.project)
        result = service.create(command_id=uuid.uuid4().hex,reviewer_id='explicit-reviewer',selection=version['version_id'],
            population_sha256=version['members_sha256'],config_event_id=self.project.configuration_history()[-1]['event_id'],mode='method-blind')
        self.enroll('later')
        self.freeze(parent=version['version_id'])
        view = ReviewController().view(Project.open(self.root),result['session_id'].split(':')[1])
        self.assertEqual(view['total'],3);self.assertEqual(view['candidate_population']['version_id'],version['version_id'])
        self.assertNotIn('private-provider-arm',json.dumps(view));self.assertNotIn('synthetic-import-adapter',json.dumps(view))
        with connection(self.project.database_path) as db:
            packet,_,_,_ = _load(db,result['session_id'])
            self.assertEqual(packet['population_sha256'],version['members_sha256'])
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))

    def test_existing_unlinked_review_sessions_remain_unchanged(self):
        service = GuidedReviewService(self.project)
        session = service.create(command_id=uuid.uuid4().hex,reviewer_id='reviewer',selection='all',
            population_sha256=content_hash(self.ids if self.ids==sorted(self.ids) else sorted(self.ids)),
            config_event_id=self.project.configuration_history()[-1]['event_id'],mode='method-blind')
        before = ReviewController().view(self.project,session['session_id'].split(':')[1])
        self.freeze();self.enroll('later')
        after = ReviewController().view(self.project,session['session_id'].split(':')[1])
        self.assertEqual(before,after);self.assertIsNone(after['candidate_population'])

    def test_empty_populations_and_foreign_versions(self):
        empty = self.freeze([{'kind':'corpus'}]);self.assertEqual(empty['member_count'],0)
        with self.assertRaises(ContractError):GuidedReviewService(self.project).create(command_id=uuid.uuid4().hex,reviewer_id='reviewer',
            selection=empty['version_id'],population_sha256=empty['members_sha256'],config_event_id=self.project.configuration_history()[-1]['event_id'],mode='method-blind')
        with self.assertRaises(ContractError):self.service.inspect('population-version:'+'0'*64)

    def test_stable_version_and_member_pagination(self):
        versions = [self.freeze() for _ in range(3)]
        first = self.service.versions(limit=1);self.freeze()
        second = self.service.versions(offset=1,limit=1,cutoff=first['cutoff'])
        self.assertEqual(second['total'],3);self.assertEqual(second['items'][0]['version_id'],versions[1]['version_id'])
        vid = versions[0]['version_id'];a = self.service.members(vid,limit=1);self.enroll('after-page')
        b = self.service.members(vid,offset=a['next_offset'],limit=2)
        self.assertEqual([p['paper_id'] for p in a['items']+b['items']],sorted(self.ids))

    def test_conflicting_exact_owners_remain_unlinked_discovery_issues(self):
        self.enroll('pmid-owner',ids=(Identifier('pmid','123456'),))
        provider=metadata_provider('openalex')
        body=json.dumps({'results':[{'id':'https://openalex.org/W9','doi':'10.1234/p.0',
            'ids':{'pmid':'https://pubmed.ncbi.nlm.nih.gov/123456'},'title':'Conflicting exact owners'}],
            'meta':{'count':1,'next_cursor':None}}).encode()
        class Transport:
            network=False
            def request(self,url,**kwargs):return HttpResponse(200,{},body,url)
        plan=self.project.discovery.plan(provider,run_id='conflicting-owners',query='fixture',created_at=AT)
        self.project.discovery.execute(plan,provider,transport=Transport(),confirm_external=True,clock=lambda:AT)
        self.project.discovery.canonicalize('conflicting-owners',approve_new_identities=True,approve_aliases=True)
        before=self.project.identities.papers()
        version=self.freeze([{'kind':'discovery','run_id':'conflicting-owners'}],accept_unresolved=True)
        self.assertEqual(version['member_count'],0);self.assertEqual(version['unresolved_count'],1)
        self.assertEqual(before,self.project.identities.papers())
        self.assertNotEqual(self.project.identities.exact_owner(Identifier('doi','10.1234/p.0')),
            self.project.identities.exact_owner(Identifier('pmid','123456')))

    def test_large_selection_has_bounded_deterministic_read_pages(self):
        # Actual scientific enrollment, not synthetic rows bypassing identity.
        for n in range(150):self.enroll('scale-'+str(n),doi='10.1234/scale.'+str(n))
        version=self.freeze();ids=[];offset=0
        while True:
            result=self.service.members(version['version_id'],offset=offset,limit=17)
            self.assertLessEqual(len(result['items']),17)
            ids.extend(p['paper_id'] for p in result['items'])
            if result['next_offset'] is None:break
            offset=result['next_offset']
        self.assertEqual(len(ids),153);self.assertEqual(ids,sorted(set(ids)))
        self.assertTrue(self.service.verify(version['version_id'])['verified'])

    def test_review_link_must_match_immutable_creation_receipt(self):
        first=self.freeze();second=self.freeze()
        result=GuidedReviewService(self.project).create(command_id=uuid.uuid4().hex,reviewer_id='reviewer',
            selection=first['version_id'],population_sha256=first['members_sha256'],
            config_event_id=self.project.configuration_history()[-1]['event_id'],mode='method-blind')
        # Even a self-consistent replacement link cannot redirect an old session.
        with connection(self.project.database_path,write=True) as db:
            db.execute('DROP TRIGGER ct_population_review_links_no_update')
            row=db.execute('SELECT payload_json FROM ct_population_review_links').fetchone()
            value=json.loads(row[0]);value['version_id']=second['version_id']
            db.execute('UPDATE ct_population_review_links SET version_id=?,payload_json=?,content_sha256=?',
                (second['version_id'],canonical(value),content_hash(value)))
        with self.assertRaisesRegex(ContractError,'creation receipt'):
            ReviewController().view(self.project,result['session_id'].split(':')[1])
        with connection(self.project.database_path,write=True) as db:
            db.execute('DROP TRIGGER ct_population_review_links_no_delete')
            db.execute('DELETE FROM ct_population_review_links')
        with self.assertRaisesRegex(ContractError,'link is missing'):
            ReviewController().view(self.project,result['session_id'].split(':')[1])

    def test_upgrade_failure_rolls_back_all_schema_38_ddl_and_retains_schema_37_backup(self):
        legacy_root=self.root.parent/'legacy-interrupted'
        existing=migrations()
        with patch('corpustrail._internal.database.migrations',return_value=existing[:37]):
            legacy=Project.create(legacy_root,self.project.config,created_by='fixture',created_at=AT)
        self.project=legacy;self.enroll('preserved',doi='10.1234/preserved-before-upgrade')
        with connection(legacy.database_path) as db:before=list(db.iterdump())
        backup=legacy_root/'data'/'interrupted-upgrade.sqlite3'
        # Inject a failure AFTER all actual migration-038 DDL, inside the real
        # upgrade transaction, before its history insert/commit. No fake store.
        broken=existing[:-1]+((existing[-1][0],existing[-1][1]+'\nSELECT nonexistent_checkpoint6_function();\n'),)
        with patch('corpustrail._internal.database.migrations',return_value=broken):
            with self.assertRaises(sqlite3.OperationalError):Project.upgrade(legacy_root,backup=backup.relative_to(legacy_root).as_posix(),created_at=AT)
        self.assertFalse(Project.open(legacy_root).populations.ready())
        for path in (legacy.database_path,backup):
            with connection(path) as db:
                self.assertEqual(list(db.iterdump()),before)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        # A new, explicitly chosen backup is required; no implicit resume/retry.
        upgraded=Project.upgrade(legacy_root,backup='data/explicit-retry.sqlite3',created_at=AT)
        self.assertTrue(upgraded.populations.ready())

    def test_backup_creation_failure_prevents_migration(self):
        legacy_root=self.root.parent/'legacy-backup-failure'
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:37]):
            legacy=Project.create(legacy_root,self.project.config,created_by='fixture',created_at=AT)
        before=legacy.database_path.read_bytes()
        with patch('corpustrail._internal.database.os.open',side_effect=OSError('Synthetic backup failure')):
            with self.assertRaises(OSError):Project.upgrade(legacy_root,backup='data/refused-backup.sqlite3',created_at=AT)
        self.assertEqual(legacy.database_path.read_bytes(),before)
        self.assertFalse(Project.open(legacy_root).populations.ready())

    def test_process_exit_during_upgrade_rolls_back_and_releases_project_use(self):
        # macOS /var is a symlink. Pass the same canonical root that the
        # application registers, rather than weakening the project's no-link guard.
        legacy_root=(self.root.parent/'legacy-process-exit').resolve()
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:37]):
            legacy=Project.create(legacy_root,self.project.config,created_by='fixture',created_at=AT)
        with connection(legacy.database_path) as db:before=list(db.iterdump())
        script='''
import os,sqlite3,sys
from pathlib import Path
from unittest.mock import patch
from corpustrail.project import Project
from corpustrail.application.project_use import acquire_project_use
original=sqlite3.connect
def connect(*args,**kwargs):
 db=original(*args,**kwargs)
 def trace(sql):
  if sql.upper().replace(' ','').startswith('INSERTINTOSCHEMA_MIGRATIONSVALUES(38,'):os._exit(23)
 db.set_trace_callback(trace)
 return db
with acquire_project_use(Path(sys.argv[1])):
 with patch('corpustrail._internal.database.sqlite3.connect',side_effect=connect):
  Project.upgrade(sys.argv[1],backup='data/process-exit-backup.sqlite3',created_at='2026-01-01T00:00:00+00:00')
'''
        result=subprocess.run([sys.executable,'-I','-c',script,str(legacy_root)],capture_output=True,timeout=25)
        self.assertEqual(result.returncode,23,result.stderr.decode('utf-8',errors='replace'))
        reopened=Project.open(legacy_root);self.assertFalse(reopened.populations.ready())
        for path in (reopened.database_path,legacy_root/'data'/'process-exit-backup.sqlite3'):
            with connection(path) as db:self.assertEqual(list(db.iterdump()),before)
        from corpustrail.application.project_use import acquire_project_use
        with acquire_project_use(legacy_root,exclusive=True):pass

    def test_previous_schema_opens_without_writes_and_explicit_upgrade_preserves_history(self):
        legacy_root = self.root.parent/'legacy'
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:37]):
            legacy = Project.create(legacy_root,self.project.config,created_by='fixture',created_at=AT)
        self.project=legacy
        pid=self.enroll('legacy',doi='10.1234/legacy')
        guided=GuidedReviewService(legacy)
        session=guided.create(command_id=uuid.uuid4().hex,reviewer_id='curator',selection='all',
            population_sha256=content_hash([pid]),config_event_id=legacy.configuration_history()[-1]['event_id'],mode='method-blind')
        with connection(legacy.database_path) as db:revision=_load(db,session['session_id'])[2]
        guided.command(session['session_id'],command_id=uuid.uuid4().hex,expected_revision=revision,action='save_next',
            value={'sufficiency':'sufficient','decision':'included','review_extent':'metadata','rationale':'Synthetic legacy observation','location':None})
        historical=legacy.reviews.history(pid)
        before = fingerprint(legacy_root);legacy = Project.open(legacy_root)
        with connection(legacy.database_path) as db:
            original_dump = list(db.iterdump())
        legacy.status();legacy.populations.versions();ReviewController().configuration(legacy)
        self.assertFalse(legacy.populations.ready());self.assertEqual(before,fingerprint(legacy_root))
        with self.assertRaises(ContractError):legacy.populations.preview(**self.fields())
        with self.assertRaises(ContractError):PopulationController().command(legacy,'upgrade',{'request_id':uuid.uuid4().hex,'confirm_backup':False})
        req = {'request_id':uuid.uuid4().hex,'confirm_backup':True,'project_id':legacy.config.project_id,
               'config_event_id':legacy.configuration_history()[-1]['event_id']}
        for mismatch in ({'project_id':'another-project'},{'config_event_id':'stale'}):
            with self.assertRaisesRegex(ContractError,'project selection or configuration changed'):
                PopulationController().command(legacy,'upgrade',{**req,**mismatch})
            self.assertEqual(before,fingerprint(legacy_root))
        result = PopulationController().command(legacy,'upgrade',req)
        self.assertTrue(result['backup_created']);self.assertTrue(Project.open(legacy_root).populations.ready())
        backup = legacy_root/legacy.config.data_directory/'population-upgrades'/(req['request_id']+'.sqlite3')
        # SQLite backup preserves logical bytes/records, not page-header counters.
        with connection(backup) as db:
            self.assertEqual(list(db.iterdump()),original_dump)
        self.assertEqual((legacy_root/'corpustrail.project.json').read_bytes(),(self.root/'corpustrail.project.json').read_bytes())
        self.assertTrue(PopulationController().command(legacy,'upgrade',req)['already_enabled'])
        self.assertEqual(legacy.configuration_history(),self.project.configuration_history())
        self.assertEqual(historical,Project.open(legacy_root).reviews.history(pid))
        self.assertEqual(legacy.reviews.membership(pid)['state'],'not_reviewed')
        self.assertIsNone(ReviewController().view(legacy,session['session_id'].split(':')[1])['candidate_population'])

    def test_independent_process_revision_race(self):
        parent = self.freeze()['version_id'];processes=[]
        script = '''import json,sys
from corpustrail.project import Project
from corpustrail.application.project_use import project_use
from corpustrail.errors import ContractError
p=Project.open(sys.argv[1]);fields=json.loads(sys.argv[2])
with project_use(p.root):
 preview=p.populations.preview(**fields);print('ready',flush=True);sys.stdin.read(1)
 try:p.populations.create(**fields,expected_preview_sha256=preview['preview_sha256']);print('created')
 except ContractError:print('stale')
'''
        try:
            for _ in range(2):
                process = subprocess.Popen([sys.executable,'-I','-c',script,str(self.root),json.dumps(self.fields(parent=parent))],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                processes.append(process);self.assertEqual(process.stdout.readline().strip(),'ready')
            results=[]
            for process in processes:
                out,err=process.communicate('x',timeout=20);self.assertEqual(process.returncode,0,err);results.append(out.strip())
            self.assertEqual(sorted(results),['created','stale']);self.assertEqual(self.service.versions()['total'],2)
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.communicate()

    def test_actual_process_crash_rolls_back_and_releases_lease(self):
        fields=self.fields()
        script = '''import json,os,sys
from unittest.mock import patch
from corpustrail.project import Project
from corpustrail._internal.values import canonical
from corpustrail.application.project_use import project_use
p=Project.open(sys.argv[1]);f=json.loads(sys.argv[2])
def fail(value):
 if isinstance(value,dict) and 'entity' in value:os._exit(23)
 return canonical(value)
with project_use(p.root):
 preview=p.populations.preview(**f)
 with patch('corpustrail.populations.service.canonical',side_effect=fail):p.populations.create(**f,expected_preview_sha256=preview['preview_sha256'])
'''
        result=subprocess.run([sys.executable,'-I','-c',script,str(self.root),json.dumps(fields)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,23,result.stderr);self.assertEqual(self.service.versions()['total'],0)
        preview=self.service.preview(**fields)
        self.assertEqual(self.service.create(**fields,expected_preview_sha256=preview['preview_sha256'])['member_count'],3)

    def test_population_tables_cannot_masquerade_as_previous_schema(self):
        with connection(self.project.database_path,write=True) as db:
            db.execute('DELETE FROM schema_migrations WHERE version=38')
        with self.assertRaisesRegex(ContractError,'complete registered schema history'):
            Project.open(self.root)

    def test_population_operations_preserve_existing_evidence_membership_and_session_rows(self):
        from test_curation_prioritization import CurationTests
        fixture=CurationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.label(fixture.ids[0]);fixture.document(fixture.ids[0]);fixture.prepare()
        project=fixture.project
        def scientific_rows():
            with connection(project.database_path) as db:
                names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                       if not r[0].startswith(('ct_population_','sqlite_'))]
                return {name:[tuple(r) for r in db.execute('SELECT * FROM "'+name+'"')] for name in names}
        before=scientific_rows();fields=self.fields()
        preview=project.populations.preview(**fields)
        version=project.populations.create(**fields,expected_preview_sha256=preview['preview_sha256'])
        project.populations.verify(version['version_id']);project.populations.members(version['version_id'])
        self.assertEqual(before,scientific_rows())
        self.assertEqual(project.reviews.membership(fixture.ids[0])['state'],'included')

    def test_legacy_upgrade_preserves_existing_scientific_tables_and_backup(self):
        from test_curation_prioritization import CurationTests
        fixture=CurationTests()
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:37]):
            fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.label(fixture.ids[0]);fixture.document(fixture.ids[0]);fixture.prepare()
        project=fixture.project
        with connection(project.database_path) as db:
            original_dump=list(db.iterdump())
            names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                   if r[0] not in ('schema_migrations','sqlite_sequence')]
            before={name:[tuple(r) for r in db.execute('SELECT * FROM "'+name+'"')] for name in names}
        fields={'request_id':uuid.uuid4().hex,'confirm_backup':True,
            'project_id':project.config.project_id,'config_event_id':project.configuration_history()[-1]['event_id']}
        result=PopulationController().command(project,'upgrade',fields)
        self.assertTrue(result['backup_created'])
        upgraded=Project.open(project.root)
        self.assertTrue(upgraded.populations.ready())
        with connection(upgraded.database_path) as db:
            self.assertEqual(before,{name:[tuple(r) for r in db.execute('SELECT * FROM "'+name+'"')] for name in names})
        backup=project.root/project.config.data_directory/'population-upgrades'/(fields['request_id']+'.sqlite3')
        with connection(backup) as db:self.assertEqual(list(db.iterdump()),original_dump)
        self.assertEqual(upgraded.reviews.membership(fixture.ids[0])['state'],'included')
        self.assertTrue(upgraded.evidence.representations(fixture.ids[0],trusted_only=True))
