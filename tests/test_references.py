"""Real reference/context stores; invented publications and no external services."""
from dataclasses import replace
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from corpustrail._internal.database import connection,migrations
from corpustrail._internal.values import ContractError,canonical,content_hash
from corpustrail.project import Project,ProjectConfig
from corpustrail.references.contracts import ContextStrategy,DerivedDependency

AT='2026-01-01T00:00:00+00:00'


def change(pid,*,actor='curator',label='in_scope',**extra):
    return {'action':'assign','paper_id':pid,'label':label,
        'producer':{'type':'human','id':actor,'version':'manual/v1'},'human_attested':True,
        'rationale':'Invented reference judgment','evidence_used':['metadata'],'supersedes':[],
        'source_assignment_ids':[],'source_event_id':None,'source_artifact_sha256':None,
        'source_record':None,**extra}


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        from test_populations import PopulationTests
        helper=PopulationTests();helper.setUp();self.addCleanup(helper.doCleanups)
        self.helper=helper;self.project=helper.project;self.service=self.project.references;self.ids=helper.ids

    def fields(self,changes=None,parent=None,**extra):
        return {'request_id':uuid.uuid4().hex,'name':'Synthetic topic references','actor':'curator','parent':parent,
            'changes':changes if changes is not None else [change(p) for p in self.ids],
            'config_event_id':self.project.configuration_history()[-1]['event_id'],'created_at':AT,**extra}

    def commit(self,changes=None,parent=None,**extra):
        fields=self.fields(changes,parent,**extra);preview=self.service.preview(**fields)
        return self.service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])

    def context_fields(self,version,**extra):
        return {'request_id':uuid.uuid4().hex,'version_id':version,'actor':'curator','created_at':AT,
            'config_event_id':self.project.configuration_history()[-1]['event_id'],'target_paper_id':self.ids[0],
            'target_basis':'metadata','held_out_paper_ids':[],'strategy':ContextStrategy(),'dependency_ids':[],**extra}

    def context(self,version,**extra):
        fields=self.context_fields(version,**extra);preview=self.service.prepare_context(**fields)
        return self.service.commit_context(**fields,expected_preview_sha256=preview['preview_sha256'])

    def test_preview_reads_do_not_write_or_manufacture_reference_truth(self):
        from test_populations import fingerprint
        before=fingerprint(self.project.root)
        with patch('socket.create_connection',side_effect=AssertionError('No network')):
            self.assertEqual(self.service.versions()['total'],0)
            preview=self.service.preview(**self.fields())
        self.assertEqual(preview['counts']['paper_count'],3)
        self.assertEqual(before,fingerprint(self.project.root))
        self.assertTrue(all(self.project.reviews.membership(p)['state']=='not_reviewed' for p in self.ids))
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))

    def test_successor_move_remove_and_history_are_immutable(self):
        first=self.commit();vid=first['version_id'];old=self.service.members(vid)
        selected=old['items'][0]
        moved=self.commit([change(selected['paper_id'],label='out_of_scope',supersedes=[selected['assignment_id']])],vid)
        current=self.service.members(moved['version_id'])
        self.assertEqual(moved['version'],2);self.assertEqual(moved['counts']['out_of_scope'],1)
        self.assertEqual(self.service.members(vid),old)
        retired=self.commit([{'action':'remove','assignment_id':current['items'][0]['assignment_id'],'reason':'Explicit synthetic correction'}],moved['version_id'])
        self.assertEqual(retired['counts']['assignment_count'],2)
        self.assertTrue(self.service.verify(vid)['verified'])
        self.assertEqual(Project.open(self.project.root).references.members(vid),old)
        self.assertTrue(all(not self.project.reviews.history(p) for p in self.ids))
        provenance=self.service.provenance(moved['version_id'])['items'][0]
        self.assertEqual(provenance['assignment']['supersedes'],[selected['assignment_id']])

    def test_contradictions_are_preserved_and_not_context_eligible_until_resolved(self):
        first=self.commit([change(self.ids[1]),change(self.ids[1],label='out_of_scope'),change(self.ids[2])])
        self.assertEqual(first['counts']['conflicts'],1)
        self.assertEqual(sum(x['conflicting'] for x in self.service.members(first['version_id'])['items']),2)
        context=self.context(first['version_id'])
        self.assertEqual(context['omission_counts']['conflicting_labels'],2)
        conflict=[p for p in self.service.members(first['version_id'])['items'] if p['paper_id']==self.ids[1]]
        corrected=self.commit([change(self.ids[1],supersedes=[p['assignment_id'] for p in conflict])],first['version_id'])
        self.assertEqual(corrected['counts']['conflicts'],0)
        self.assertEqual(first['counts']['assignment_count'],3)
        with connection(self.project.database_path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_reference_assignments').fetchone()[0],4)

    def test_unattested_human_and_import_proposals_do_not_gain_eligibility(self):
        artifact=self.helper.project.identities.observations(self.ids[1])[0]['source']['source_sha256']
        imported=change(self.ids[1],producer={'type':'imported','id':'synthetic-adapter','version':'fixture/v1'},
            human_attested=False,source_artifact_sha256=artifact,source_record='record-1')
        first=self.commit([imported,change(self.ids[2],human_attested=False)])
        self.assertEqual(first['counts']['unattested'],2)
        self.assertEqual(self.context(first['version_id'])['selected_count'],0)
        with self.assertRaisesRegex(ContractError,'attestation'):self.commit([{**imported,'human_attested':True}])
        proposal=self.service.members(first['version_id'])['items'][0]
        attested=self.commit([change(proposal['paper_id'],supersedes=[proposal['assignment_id']],source_assignment_ids=[proposal['assignment_id']])],first['version_id'])
        self.assertEqual(attested['counts']['unattested'],1)

    def test_replay_changed_commands_stale_heads_and_configuration_fail_closed(self):
        fields=self.fields();preview=self.service.preview(**fields)
        one=self.service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
        two=self.service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
        self.assertTrue(two['replayed']);self.assertEqual(one['version_id'],two['version_id'])
        with self.assertRaises(ContractError):self.service.commit(**{**fields,'actor':'other'},expected_preview_sha256=preview['preview_sha256'])
        self.commit([change(self.ids[0])],one['version_id'])
        with self.assertRaisesRegex(ContractError,'latest'):self.commit([change(self.ids[0])],one['version_id'])
        with self.assertRaisesRegex(ContractError,'configuration'):self.service.preview(**self.fields(config_event_id='stale'))

    def test_failure_after_inserts_rolls_back_all_reference_state(self):
        from corpustrail.references import storage
        original=storage.insert_version
        def fail(*args):original(*args);raise RuntimeError('Controlled interruption')
        fields=self.fields();preview=self.service.preview(**fields)
        with patch.object(storage,'insert_version',side_effect=fail):
            with self.assertRaises(RuntimeError):self.service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
        with connection(self.project.database_path) as db:
            for table in ('ct_reference_versions','ct_reference_assignments','ct_reference_chunks','ct_reference_changes'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_parallel_identical_replay_produces_one_atomic_version(self):
        fields=self.fields();preview=self.service.preview(**fields);results=[];failures=[]
        def work():
            try:results.append(self.service.commit(**fields,expected_preview_sha256=preview['preview_sha256']))
            except Exception as error:failures.append(type(error).__name__)
        threads=[threading.Thread(target=work) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(10);self.assertFalse(t.is_alive())
        self.assertEqual(failures,[]);self.assertEqual(len({r['version_id'] for r in results}),1)
        self.assertEqual(self.service.versions()['total'],1)

    def test_context_actual_input_exact_passages_self_match_and_held_out_labels(self):
        version=self.commit()['version_id']
        result=self.context(version,held_out_paper_ids=[self.ids[1]])
        self.assertEqual(result['selected_count'],1)
        self.assertEqual(result['omission_counts'],{'self_match':1,'held_out':1})
        read=self.service.context(result['context_id'],verify=True)
        selected=[i for i in read['items'] if i['decision']=='selected']
        self.assertEqual(selected[0]['paper_id'],self.ids[2]);self.assertTrue(selected[0]['text'])
        self.assertEqual(selected[0]['source_range']['end'],len(selected[0]['text']))
        with connection(self.project.database_path) as db:
            body=json.loads(db.execute('SELECT input_bytes FROM ct_reference_contexts').fetchone()[0])
        self.assertEqual([r['paper_id'] for r in body['references']],[self.ids[2]])
        self.assertNotIn(self.ids[1],canonical(body))
        self.assertEqual(Project.open(self.project.root).references.context(result['context_id']),self.service.context(result['context_id']))

    def test_context_preview_is_read_only_and_replay_is_durable(self):
        from test_populations import fingerprint
        version=self.commit()['version_id'];fields=self.context_fields(version);before=fingerprint(self.project.root)
        preview=self.service.prepare_context(**fields)
        self.assertEqual(fingerprint(self.project.root),before)
        one=self.service.commit_context(**fields,expected_preview_sha256=preview['preview_sha256'])
        two=Project.open(self.project.root).references.commit_context(**fields,expected_preview_sha256=preview['preview_sha256'])
        self.assertTrue(two['replayed']);self.assertEqual(one['context_id'],two['context_id'])
        self.assertEqual(self.service.contexts()['items'][0]['context_id'],one['context_id'])

    def test_derived_provenance_is_unvalidated_and_contamination_is_refused(self):
        vid=self.commit()['version_id'];members=self.service.members(vid)['items']
        aid=next(r['assignment_id'] for r in members if r['paper_id']==self.ids[1])
        contract=DerivedDependency('profile',{'type':'deterministic','id':'synthetic-fixture','version':'v1'},(aid,),{'method':'invented hand-authored fixture'})
        result=self.service.register_dependency(version_id=vid,contract=contract,body=b'Invented unvalidated profile.',actor='curator',created_at=AT)
        self.assertEqual(result['validation_state'],'unvalidated')
        with self.assertRaisesRegex(ContractError,'explicit inclusion'):self.context(vid,dependency_ids=[result['dependency_id']])
        accepted=self.context(vid,dependency_ids=[result['dependency_id']],strategy=ContextStrategy(include_unvalidated_derived=True))
        self.assertEqual(accepted['dependency_ids'],[result['dependency_id']])
        self.assertFalse(accepted['independent_evaluation'])
        with self.assertRaisesRegex(ContractError,'held-out'):
            self.context(vid,held_out_paper_ids=[self.ids[1]],dependency_ids=[result['dependency_id']],strategy=ContextStrategy(include_unvalidated_derived=True))
        with connection(self.project.database_path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_review_events').fetchone()[0],0)

    def test_explicit_truncation_and_omission_never_silently_drop_text(self):
        vid=self.commit()['version_id']
        omitted=self.context(vid,strategy=ContextStrategy(max_per_reference=5))
        self.assertEqual(omitted['selected_count'],0)
        self.assertEqual(omitted['omission_counts']['representation_exceeds_budget'],2)
        chosen=self.context(vid,strategy=ContextStrategy(max_per_reference=5,allow_truncation=True))
        rows=self.service.context(chosen['context_id'])['items']
        self.assertTrue(all(r['truncated'] and len(r['text'])==5 and r['omitted_characters']>0 for r in rows if r['decision']=='selected'))

    def test_frozen_records_reject_updates_and_detect_context_corruption(self):
        vid=self.commit()['version_id'];cid=self.context(vid)['context_id']
        with connection(self.project.database_path,write=True) as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE ct_reference_assignments SET label=?',('out_of_scope',))
            db.execute('DROP TRIGGER ct_reference_contexts_no_update')
            db.execute('UPDATE ct_reference_contexts SET input_bytes=? WHERE context_id=?',(b'{}',cid))
        with self.assertRaisesRegex(ContractError,'integrity'):self.service.context(cid)

    def test_schema_38_opens_without_write_then_explicit_backup_preserves_old_data(self):
        from test_populations import fingerprint
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'legacy'
            with patch('corpustrail._internal.database.migrations',return_value=migrations()[:38]):
                old=Project.create(path,ProjectConfig('old-references','Old reference fixture','Synthetic topic'),created_by='fixture',created_at=AT)
            before=fingerprint(path);opened=Project.open(path)
            self.assertFalse(opened.references.ready());self.assertEqual(before,fingerprint(path))
            with self.assertRaisesRegex(ContractError,'backed-up'):opened.references.preview(**self.fields())
            new=Project.upgrade(path,backup='backups/before-references.sqlite3',created_at=AT)
            self.assertTrue(new.references.ready())
            with sqlite3.connect(path/'backups/before-references.sqlite3') as db:
                self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0],38)
            self.assertEqual(old.config,new.config)

    def test_paginated_inherited_assignment_provenance_and_label_filter(self):
        first=self.commit();items=self.service.members(first['version_id'])['items']
        successor=self.commit([change(self.ids[0],label='out_of_scope',supersedes=[p['assignment_id'] for p in items if p['paper_id']==self.ids[0]])],first['version_id'])
        remaining=next(p for p in items if p['paper_id']!=self.ids[0])
        inherited=self.service.assignment(successor['version_id'],remaining['assignment_id'])
        self.assertEqual(inherited['assignment']['evidence']['identity']['entity']['paper_id'],remaining['paper_id'])
        self.assertEqual(self.service.members(successor['version_id'],label='out_of_scope')['total'],1)
        self.assertEqual(self.service.members(successor['version_id'],label='in_scope',limit=1)['next_offset'],1)
        with self.assertRaises(ContractError):self.service.members(first['version_id'],limit=101)
        retired=next(p for p in items if p['paper_id']==self.ids[0])
        with self.assertRaises(ContractError):self.service.assignment(successor['version_id'],retired['assignment_id'])

    def test_held_out_frozen_population_preserves_exact_exclusions_after_new_candidates(self):
        first=self.commit();held=self.helper.freeze([{'kind':'selection','paper_ids':[self.ids[1]]}])
        fields=self.context_fields(first['version_id'],held_out_population_version=held['version_id'])
        preview=self.service.prepare_context(**fields)
        self.helper.enroll('later-source')
        saved=self.service.commit_context(**fields,expected_preview_sha256=preview['preview_sha256'])
        current=self.service.context(saved['context_id'])
        self.assertEqual(current['held_out_paper_ids'],[self.ids[1]])
        self.assertEqual(current['held_out_population_version'],held['version_id'])
        self.assertEqual(current['omission_counts']['held_out'],1)
        self.assertNotIn(self.ids[1],{v['paper_id'] for v in current['input']['references']})

    def test_identity_lineage_unknown_ids_and_false_evidence_claims_fail_closed(self):
        for invalid in (change('ct-paper:'+'0'*64),change(self.ids[0],evidence_used=['structured_text']),
                        change(self.ids[0],human_attested=True,producer={'type':'human','id':'another-person','version':'manual/v1'}),
                        change(self.ids[0],source_event_id='review:'+'0'*64)):
            with self.assertRaises(ContractError):self.commit([invalid])
        self.assertEqual(self.service.versions()['total'],0)

    def test_frozen_reference_evidence_does_not_expand_after_acquisition(self):
        doi='10.1234/p.0'
        first=self.commit([change(self.ids[0])]);before=self.service.members(first['version_id'])
        xml=('<article><front><article-meta><article-id pub-id-type="doi">'+doi+'</article-id></article-meta></front><body><p>Invented later verified scientific body.</p></body></article>').encode()
        self.project.evidence.preserve_document(self.ids[0],xml,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://later-reference-document',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='v1',created_at=AT)
        self.assertEqual(self.service.members(first['version_id']),before)
        aid=before['items'][0]['assignment_id'];old=self.service.assignment(first['version_id'],aid)['assignment']
        self.assertNotIn('structured_text',old['evidence']['available'])
        reassessed=self.commit([change(self.ids[0],evidence_used=['structured_text'],supersedes=[aid])],first['version_id'])
        context=self.context(reassessed['version_id'],target_paper_id=self.ids[1])
        self.assertIn('Invented later verified scientific body.',self.service.context(context['context_id'])['input']['references'][0]['text'])

    def test_upgrade_writer_revision_guard_and_interrupted_migration_keep_backup(self):
        from test_populations import fingerprint
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'legacy';prefix=migrations()[:38]
            with patch('corpustrail._internal.database.migrations',return_value=prefix):
                old=Project.create(path,ProjectConfig('upgrade-reference','Synthetic upgrade','Synthetic topic'),created_by='fixture',created_at=AT)
            before=fingerprint(path)
            with self.assertRaisesRegex(ContractError,'configuration changed'):
                Project.upgrade(path,backup='backups/stale.sqlite3',expected_config_event='stale',created_at=AT)
            self.assertEqual(before,fingerprint(path));self.assertFalse((path/'backups/stale.sqlite3').exists())
            latest=migrations()[-1]
            broken=(latest[0],latest[1]+'\nINSERT INTO missing_reference_fixture_table VALUES (1);\n')
            with patch('corpustrail._internal.database.migrations',return_value=prefix+(broken,)):
                with self.assertRaises(sqlite3.DatabaseError):Project.upgrade(path,backup='backups/interrupted.sqlite3',created_at=AT)
            self.assertTrue((path/'backups/interrupted.sqlite3').is_file());self.assertFalse(Project.open(path).references.ready())
            with connection(old.database_path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],38)
                self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='ct_reference_assignments'").fetchone())

    def test_independent_process_replay_and_process_crash_are_atomic(self):
        fields=self.fields();preview=self.service.preview(**fields)
        command={**fields,'expected_preview_sha256':preview['preview_sha256']}
        code='import json,sys; from corpustrail.project import Project; p=Project.open(sys.argv[1]); print(p.references.commit(**json.loads(sys.argv[2]))["version_id"])'
        environment={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
        processes=[subprocess.Popen([sys.executable,'-c',code,str(self.project.root),canonical(command)],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        output=[p.communicate(timeout=30) for p in processes]
        self.assertEqual([p.returncode for p in processes],[0,0],output)
        self.assertEqual(output[0][0],output[1][0]);self.assertEqual(self.service.versions()['total'],1)
        fields=self.fields(parent=self.service.versions()['items'][0]['version_id']);preview=self.service.preview(**fields)
        command={**fields,'expected_preview_sha256':preview['preview_sha256']}
        crash='''import os,json,sys
from corpustrail.project import Project
from corpustrail.references import storage
original=storage.insert_version
def fail(*args,**kwargs):
    original(*args,**kwargs)
    os._exit(23)
storage.insert_version=fail
Project.open(sys.argv[1]).references.commit(**json.loads(sys.argv[2]))
'''
        result=subprocess.run([sys.executable,'-c',crash,str(self.project.root),canonical(command)],env=environment,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,23,result.stderr);self.assertEqual(self.service.versions()['total'],1)
        with connection(self.project.database_path) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM ct_reference_assignments').fetchone()[0],3)

    def test_membership_is_not_reference_truth_but_explicit_source_event_is_preserved(self):
        from corpustrail.curation import ReviewEvent,EvidenceBasis
        source=self.project.identities.observations(self.ids[0])[0]['source']
        event=ReviewEvent(self.ids[0],'included','sufficient','metadata','Invented authoritative membership','curator',AT,
            (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),authority_state='human_authorized')
        eid=self.project.reviews.apply(self.project.reviews.plan(event),recorded_at=AT)
        self.assertEqual(self.service.versions()['total'],0)
        history=self.project.reviews.history(self.ids[0]);version=self.commit([change(self.ids[0],source_event_id=eid)])
        aid=self.service.members(version['version_id'])['items'][0]['assignment_id']
        stored=self.service.assignment(version['version_id'],aid)['assignment']
        self.assertEqual(stored['source_event']['event_id'],eid);self.assertTrue(stored['human_attested'])
        self.assertEqual(self.project.reviews.history(self.ids[0]),history)
        with self.assertRaisesRegex(ContractError,'matching judgment'):self.commit([change(self.ids[1],source_event_id=eid)])

    def test_reference_v3_context_survives_v4_correction_without_rerun(self):
        version=self.commit()
        for number in range(2):
            old=next(x for x in self.service.members(version['version_id'])['items'] if x['paper_id']==self.ids[1])
            version=self.commit([change(self.ids[1],label='out_of_scope' if number==0 else 'in_scope',supersedes=[old['assignment_id']])],version['version_id'])
        self.assertEqual(version['version'],3)
        context=self.context(version['version_id']);before=self.service.context(context['context_id'])
        old=next(x for x in self.service.members(version['version_id'])['items'] if x['paper_id']==self.ids[1])
        later=self.commit([change(self.ids[1],label='out_of_scope',supersedes=[old['assignment_id']])],version['version_id'])
        self.assertEqual(later['version'],4);self.assertEqual(self.service.context(context['context_id']),before)
        self.assertEqual(self.service.verify(version['version_id'])['counts'],version['counts'])
        self.assertEqual(self.service.contexts()['items'][0]['context_id'],context['context_id'])

    def test_reference_corrections_do_not_change_frozen_method_blind_session(self):
        from corpustrail.application.review import ReviewController
        from corpustrail.curation.guided import GuidedReviewService
        config=ReviewController().configuration(self.project);frozen=self.helper.freeze()
        session=GuidedReviewService(self.project).create(command_id=uuid.uuid4().hex,reviewer_id='curator',
            selection=frozen['version_id'],population_sha256=frozen['members_sha256'],config_event_id=config['config_event_id'],mode='method-blind')
        handle=session['session_id'].split(':')[1];before=ReviewController().view(self.project,handle)
        version=self.commit();old=self.service.members(version['version_id'])['items'][0]
        self.commit([change(old['paper_id'],label='out_of_scope',supersedes=[old['assignment_id']])],version['version_id'])
        self.context(version['version_id'])
        self.assertEqual(ReviewController().view(self.project,handle),before)
        self.assertNotIn('reference-assignment:',canonical(before))

    def test_implementation_change_invalidates_unsaved_previews_not_history(self):
        fields=self.fields();preview=self.service.preview(**fields)
        with patch('corpustrail.references.service.implementation_hash',return_value='sha256:'+'0'*64):
            with self.assertRaisesRegex(ContractError,'stale'):self.service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
        version=self.service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
        context_fields=self.context_fields(version['version_id']);preview=self.service.prepare_context(**context_fields)
        with patch('corpustrail.references.context.implementation_hash',return_value='sha256:'+'0'*64):
            with self.assertRaisesRegex(ContractError,'changed'):self.service.commit_context(**context_fields,expected_preview_sha256=preview['preview_sha256'])
        self.assertEqual(self.service.inspect(version['version_id'])['implementation_sha256'],version['implementation_sha256'])

    def test_derived_contract_rejects_credentials_and_empty_dependencies(self):
        version=self.commit()['version_id'];aid=self.service.members(version)['items'][0]['assignment_id']
        contract=DerivedDependency('index',{'type':'deterministic','id':'synthetic-fixture','version':'v1'},(aid,),{'normalization':'none','seed':1})
        for invalid in (replace(contract,settings={'api_key':'synthetic-private-value'}),replace(contract,source_assignment_ids=())):
            with self.assertRaises(ContractError):self.service.register_dependency(version_id=version,contract=invalid,body=b'Invented unvalidated index fixture',actor='curator',created_at=AT)


if __name__=='__main__':unittest.main()
