"""Dependency-free bibliography and exact-identity contract tests, synthetic only."""
from copy import deepcopy
from contextlib import closing
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from corpustrail._internal.database import connection
from corpustrail._internal.values import canonical, digest_bytes, content_hash, ContractError
from corpustrail.cli import main
from corpustrail.curation import ReviewEvent, EvidenceBasis
from corpustrail.export.asreview import FIELDS, render_export, validate_snapshot
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.knowledge.registry import VERSION
from corpustrail.project import Project, ProjectConfig, ReviewPolicy

AT='2026-01-01T00:00:00+00:00'
LATER='2026-01-02T00:00:00+00:00'


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'topic'
        self.project=Project.create(self.root,ProjectConfig('synthetic-topic','Materials sensors','Invented broad topic',
            review=ReviewPolicy(authorized_reviewers=('fixture-reviewer',))),created_by='fixture',created_at=AT)
        self.ids=[self.enroll(i) for i in range(7)]
        for pid,state in zip(self.ids,('included','included','included','excluded','insufficient_evidence','unresolved',None)):
            if state:self.review(pid,state)
        self.service=self.project.asreview
        self.snapshot=self.service.plan('test-export',created_at=AT)

    def enroll(self,i):
        aliases=(Identifier('fixture.record',str(i)),Identifier('openalex','W'+str(i+100)))
        if i!=1:aliases+= (Identifier('doi','10.1234/fixture.'+str(i)),)
        if i==0:aliases+=(Identifier('pmid','123'),Identifier('pmcid','PMC123'),Identifier('semantic_scholar','a'*40))
        record=BibliographicRecord(title='Same-looking report — 多言語',abstract='Invented abstract.' if i!=1 else None,
            authors=('Author A','Author B'),year=2020,source='Invented Journal',identifiers=aliases)
        source=SourceReference('fixture://bibliography',str(i),digest_bytes(b'fixture'),7,'fixture',AT,identity_status='verified')
        return self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)

    def review(self,pid,state,*,authority='human_authorized',producer='human',at=AT):
        source=self.project.identities.observations(pid)[0]['source']
        event=ReviewEvent(pid,state,{'included':'sufficient','excluded':'sufficient','insufficient_evidence':'insufficient','unresolved':'undetermined'}[state],
            'metadata','Hidden broad-corpus rationale','fixture-reviewer' if producer=='human' else 'fixture-model',at,
            (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
            producer_type=producer,authority_state=authority,
            supersedes=self.project.reviews.membership(pid)['current_event_id'] if authority=='human_authorized' else None)
        self.project.reviews.apply(self.project.reviews.plan(event),recorded_at=at)

    def results(self,rows=None,headers=None):
        path=Path(self.temp.name)/'results.csv'
        rows=rows if rows is not None else [dict(r,asreview_label=str(i%2)) for i,r in enumerate(self.snapshot['records'])]
        with path.open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=headers or [*FIELDS,'asreview_label']); writer.writeheader(); writer.writerows(rows)
        return path

    def map(self,rows=None,**kwargs):
        self.service.create(self.snapshot)
        return self.service.map_results('test-export',results=self.results(rows),review_id='review-A',question_id='question-A',
            mapping_id='results-1',asreview_version='2.2',created_at=AT,**kwargs)

    def test_population_counts_and_no_question_specific_labels_or_seeds(self):
        self.assertEqual(len(self.snapshot['records']),3)
        self.assertEqual(self.snapshot['membership_counts'],{'included':3,'excluded':1,'insufficient_evidence':1,'unresolved':1,'not_reviewed':1})
        body,_=render_export(self.snapshot)
        headers=list(csv.reader(io.StringIO(body.decode())))[0]
        self.assertEqual(headers,list(FIELDS))
        self.assertFalse(set(headers)&{'included','label','asreview_label','priority','rank','notes','relevant','exclusion_reason'})
        self.assertNotIn('Hidden broad-corpus',body.decode())
        self.assertFalse(self.snapshot['automatic_seeds'])

    def test_doi_missing_duplicate_titles_and_identifiers_are_preserved(self):
        records={r['corpustrail_paper_id']:r for r in self.snapshot['records']}
        self.assertEqual(records[self.ids[1]]['doi'],'')
        self.assertEqual(records[self.ids[1]]['abstract'],'')
        self.assertEqual(len({r['title'] for r in records.values()}),1)
        self.assertEqual(records[self.ids[0]]['doi'],'10.1234/fixture.0')
        self.assertEqual(records[self.ids[0]]['pmid'],'123')
        self.assertEqual(records[self.ids[0]]['pmcid'],'PMC123')
        self.assertIn({'scheme':'fixture.record','value':'0'},json.loads(records[self.ids[0]]['corpustrail_identifiers']))

    def test_same_snapshot_rendering_and_immutable_export_id(self):
        first=render_export(self.snapshot); created=self.service.create(self.snapshot)
        path=self.root/created['paths']['dataset.csv']; before=path.read_bytes()
        self.assertTrue(self.service.create(self.snapshot)['reused'])
        self.review(self.ids[0],'excluded',at=LATER)
        self.assertEqual(render_export(self.snapshot),first)
        with self.assertRaises(FileExistsError):self.service.create(self.service.plan('test-export',created_at=LATER))
        later=self.service.create(self.service.plan('later-export',created_at=LATER))
        self.assertEqual(later['export']['row_count'],2)
        self.assertEqual(path.read_bytes(),before)

    def test_preview_and_plan_have_no_side_effects(self):
        before=self.project.database_path.read_bytes(); files=sorted(str(p) for p in self.root.rglob('*'))
        preview=self.service.preview()
        self.assertEqual(preview['records'],3); self.assertEqual(preview['missing_abstract'],1)
        self.assertEqual(preview['doi_present'],2); self.assertEqual(preview['doi_missing'],1)
        self.service.plan('another-plan',created_at=AT)
        self.assertEqual(self.project.database_path.read_bytes(),before)
        self.assertEqual(sorted(str(p) for p in self.root.rglob('*')),files)

    def test_export_and_mapping_do_not_write_database_or_membership(self):
        before=self.project.database_path.read_bytes(); corpus=self.project.reviews.corpus()
        result=self.map()
        self.assertEqual(self.project.database_path.read_bytes(),before)
        self.assertEqual(self.project.reviews.corpus(),corpus)
        self.assertTrue(all(r['authority']=='none' for r in result['records']))
        self.assertEqual(self.service.mapping('review-A','results-1'),result)

    def test_exact_round_trip_reordered_records_no_title_join(self):
        rows=[dict(r,asreview_label='-1') for r in reversed(self.snapshot['records'])]
        rows[0]['asreview_label']='0.0'; rows[1]['asreview_label']='1.0'
        result=self.map(rows)
        self.assertEqual({r['paper_id'] for r in result['records']},set(self.ids[:3]))
        self.assertEqual(sum(r['question_specific_label'] is None for r in result['records']),1)
        self.assertIn(self.ids[1],{r['paper_id'] for r in result['records']})

    def test_stripped_custom_ids_fail_even_if_title_doi_are_present(self):
        self.service.create(self.snapshot)
        rows=[{k:v for k,v in dict(r,asreview_label='1').items() if k!='corpustrail_paper_id'} for r in self.snapshot['records']]
        path=self.results(rows,[k for k in [*FIELDS,'asreview_label'] if k!='corpustrail_paper_id'])
        with self.assertRaises(ContractError):self.service.map_results('test-export',results=path,review_id='A',question_id='A',mapping_id='A',asreview_version='2.2')

    def test_missing_duplicate_unknown_partial_and_invalid_labels_fail_closed(self):
        valid=[dict(r,asreview_label='1') for r in self.snapshot['records']]
        cases=[valid[:-1],[valid[0],valid[0],valid[2]],
            [dict(valid[0],corpustrail_paper_id='unknown'),*valid[1:]],
            [dict(valid[0],asreview_label='insufficient_evidence'),*valid[1:]],
            [dict(valid[0],doi='10.1234/wrong'),*valid[1:]],
            [dict(valid[0],title='Changed title'),*valid[1:]]]
        for rows in cases:
            with self.assertRaises(ContractError):self.map(rows)
        self.assertFalse((self.root/'data/asreview/downstream').exists())

    def test_multiple_downstream_projects_are_isolated(self):
        first=self.map()
        path=self.results([dict(r,asreview_label='-1') for r in self.snapshot['records']])
        second=self.service.map_results('test-export',results=path,review_id='review-B',question_id='question-B',
            mapping_id='results-1',asreview_version='2.2',created_at=AT)
        self.assertEqual(self.service.mapping('review-A','results-1'),first)
        self.assertEqual(self.service.mapping('review-B','results-1'),second)
        with self.assertRaises(ContractError):self.service.map_results('test-export',results=path,review_id='review-A',
            question_id='different',mapping_id='results-2',asreview_version='2.2',created_at=AT)

    def test_mapping_history_is_immutable_and_does_not_copy_identity_information(self):
        first=self.map(); rows=[dict(r,asreview_label='0',user_name='private fixture identity',user_email='private fixture contact') for r in self.snapshot['records']]
        path=self.results(rows,[*FIELDS,'asreview_label','user_name','user_email'])
        with self.assertRaises(FileExistsError):self.service.map_results('test-export',results=path,review_id='review-A',question_id='question-A',
            mapping_id='results-1',asreview_version='2.2',created_at=AT)
        result=self.service.map_results('test-export',results=path,review_id='review-A',question_id='question-A',mapping_id='results-2',asreview_version='2.2',created_at=LATER)
        self.assertNotIn('private fixture',canonical(result))
        self.assertEqual(self.service.mapping('review-A','results-1'),first)

    def test_model_observations_and_prioritization_cannot_select_population(self):
        body=render_export(self.snapshot)[0]
        self.review(self.ids[6],'included',authority='non_authoritative',producer='model')
        self.review(self.ids[0],'excluded',authority='non_authoritative',producer='model')
        draft={'subject_type':'paper','subject_id':self.ids[6],'paper_id':self.ids[6],
            'predicate':'ct.report_role','vocabulary_version':VERSION,'raw_value':'methods','value_datatype':'string',
            'producer_type':'model','producer_id':'fixture','created_at':AT,'evidence_representation':'none','source':{},'lineage_ref':'fixture-model'}
        self.project.knowledge_store.apply(self.project.knowledge_store.plan_batch([draft]))
        with patch.object(type(self.project.prioritization),'inputs',side_effect=AssertionError('ranking cannot be an export input')):
            self.assertEqual(render_export(self.service.plan('later',created_at=AT))[0],body)

    def test_metadata_selection_uses_existing_canonical_selector_and_provenance(self):
        pid=self.ids[0]
        source=SourceReference('fixture://another-source','later',digest_bytes(b'another'),7,'other-provider',LATER,identity_status='verified')
        record=BibliographicRecord('Later conflicting provider title',identifiers=(Identifier('doi','10.1234/fixture.0'),))
        self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
        snapshot=self.service.plan('later',created_at=LATER)
        record=next(r for r in snapshot['records'] if r['corpustrail_paper_id']==pid)
        metadata=self.project.discovery.metadata(pid)
        self.assertEqual(record['title'],metadata['fields']['title'])
        self.assertEqual(next(r for r in snapshot['lineage'] if r['paper_id']==pid)['metadata'],metadata)

    def test_deterministic_fixed_state_and_unknown_commit_not_inferred(self):
        self.assertEqual(self.snapshot,self.service.plan('test-export',created_at=AT))
        self.assertIsNone(self.snapshot['software']['commit'])
        explicit=self.service.plan('explicit',created_at=AT,software_commit='a'*40)
        self.assertEqual(explicit['software']['commit'],'a'*40)

    def test_snapshot_dataset_and_sidecar_tampering_fail_closed(self):
        bad=deepcopy(self.snapshot); bad['records'][0]['title']='Tampered'
        with self.assertRaises(ContractError):validate_snapshot(bad)
        created=self.service.create(self.snapshot); target=self.root/created['paths']['dataset.csv']; target.write_bytes(b'bad')
        with self.assertRaises(ContractError):self.service.inspect('test-export')

    def test_partial_output_is_preserved_not_repaired_or_clobbered(self):
        with patch('corpustrail.export.asreview._write_bytes',side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError):self.service.create(self.snapshot)
        directory=self.root/'data/asreview/exports/test-export'
        self.assertTrue(directory.exists())
        with self.assertRaises(OSError):self.service.create(self.snapshot)
        self.assertTrue(directory.exists())

    def test_snapshot_is_project_bound_and_paths_cannot_escape(self):
        other=Project.create(Path(self.temp.name)/'other',ProjectConfig('synthetic-topic','Different topic','Distinct bootstrap'),created_by='fixture',created_at=AT)
        with self.assertRaises(ContractError):other.asreview.create(self.snapshot)
        with self.assertRaises(ContractError):self.service.plan('../escape',created_at=AT)
        with self.assertRaises(ContractError):self.service.write_snapshot(self.snapshot,'../escape.json')
        self.service.write_snapshot(self.snapshot,'data/plans/test.json')
        with self.assertRaises(FileExistsError):self.service.write_snapshot(self.snapshot,'data/plans/test.json')

    def test_cli_preview_plan_create_inspect_and_map_from_other_directory(self):
        stdout=io.StringIO()
        with patch('sys.stdout',stdout):self.assertEqual(main(['export','asreview','plan',str(self.root),'--export-id','test-export','--created-at',AT]),0)
        validate_snapshot(json.loads(stdout.getvalue())['snapshot'])
        with patch('sys.stdout',io.StringIO()):
            self.assertEqual(main(['export','asreview','preview',str(self.root)]),0)
            self.assertEqual(main(['export','asreview','plan',str(self.root),'--export-id','test-export','--created-at',AT,'--out','data/plan.json']),0)
            self.assertEqual(main(['export','asreview','create',str(self.root),'--snapshot','data/plan.json']),0)
            self.assertEqual(main(['export','asreview','inspect',str(self.root),'--export-id','test-export']),0)
            path=self.results()
            self.assertEqual(main(['export','asreview','map',str(self.root),'--export-id','test-export','--results',str(path),
                '--review-id','review-A','--question-id','question-A','--mapping-id','results-1','--asreview-version','2.2','--created-at',AT]),0)

    def test_empty_project_preview_and_unsupported_population(self):
        empty=Project.create(Path(self.temp.name)/'empty',ProjectConfig('empty','Materials','Synthetic empty'),created_by='fixture',created_at=AT)
        self.assertEqual(empty.asreview.preview()['records'],0)
        with self.assertRaises(ContractError):empty.asreview.plan('empty',created_at=AT)
        with self.assertRaises(ContractError):self.service.plan('all',created_at=AT,selection_rule='all_candidates')

    def test_result_version_and_malformed_csv_fail_closed(self):
        self.service.create(self.snapshot); path=self.results()
        for version in ('2.1','3.0','unspecified'):
            with self.assertRaises(ContractError):self.service.map_results('test-export',results=path,review_id='A',question_id='A',mapping_id='A',asreview_version=version)
        path.write_text('corpustrail_paper_id,asreview_label,asreview_label\nx,0,1\n',encoding='utf-8')
        with self.assertRaises(ContractError):self.service.map_results('test-export',results=path,review_id='A',question_id='A',mapping_id='A',asreview_version='2.2')

    def test_snapshot_provenance_cannot_be_internally_inconsistent(self):
        for key in ('configuration','database_snapshot','membership_counts'):
            bad=deepcopy(self.snapshot)
            if key=='configuration':bad[key]['sha256']='sha256:'+'a'*64
            elif key=='database_snapshot':bad[key]['path']='different.sqlite3'
            else:bad[key]['excluded']=999
            bad['snapshot_sha256']=content_hash({k:v for k,v in bad.items() if k!='snapshot_sha256'})
            with self.assertRaises(ContractError):validate_snapshot(bad)

    def test_mapping_replay_and_relative_input_are_project_bound(self):
        self.service.create(self.snapshot)
        path=self.results(); local=self.root/'results.csv'; local.write_bytes(path.read_bytes())
        arguments=dict(results='results.csv',review_id='review-A',question_id='question-A',mapping_id='results-1',asreview_version='2.2',created_at=AT)
        first=self.service.map_results('test-export',**arguments)
        self.assertEqual(first,self.service.map_results('test-export',**arguments))
        self.assertEqual(first,self.service.mapping('review-A','results-1'))

    def test_freeze_is_consistent_during_concurrent_wal_write(self):
        import sqlite3
        # Read transaction already pins the ledger. A separate WAL writer may
        # commit; metadata and membership must still come from the same snapshot.
        with closing(sqlite3.connect(self.project.database_path)) as db, db:db.execute('PRAGMA journal_mode=WAL')
        original=self.project.discovery._metadata; changed=False
        def concurrent(db,pid):
            nonlocal changed
            if not changed:
                changed=True
                self.review(self.ids[0],'excluded',at=LATER)
                record=BibliographicRecord('A new provider title',identifiers=(Identifier('doi','10.1234/fixture.0'),))
                source=SourceReference('fixture://concurrent','new',digest_bytes(b'new'),3,'new',LATER,identity_status='verified')
                self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
            return original(db,pid)
        with patch.object(type(self.project.discovery),'_metadata',side_effect=concurrent):
            frozen=self.service.plan('consistent',created_at=AT)
        self.assertEqual(frozen['records'],self.snapshot['records'])
        self.assertEqual(frozen['lineage'],self.snapshot['lineage'])
        self.assertEqual(len(self.service.plan('after-concurrent',created_at=LATER)['records']),2)

    def test_verified_recovered_abstract_export_pending_document_ignored(self):
        self.project.evidence.preserve_document(self.ids[1],b'%PDF synthetic pending abstract',representation='pdf',
            media_type='application/pdf',source_uri='fixture://pending',legitimate_basis='synthetic_fixture',
            resolver='fixture',resolver_version='1',created_at=AT)
        before=self.service.plan('pending',created_at=AT)
        self.assertEqual(next(r for r in before['records'] if r['corpustrail_paper_id']==self.ids[1])['abstract'],'')
        record=BibliographicRecord('Recovered abstract report',identifiers=(Identifier('doi','10.1234/recovered'),))
        source=SourceReference('fixture://recover','recover',digest_bytes(b'recover'),7,'fixture',AT,identity_status='verified')
        pid=self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
        self.review(pid,'included')
        xml=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/recovered</article-id><abstract><p>Explicit recovered abstract.</p></abstract></article-meta></front><body><p>Invented body.</p></body></article>'
        self.project.evidence.preserve_document(pid,xml,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://verified',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='1',created_at=AT)
        frozen=self.service.plan('recovered',created_at=AT)
        result=next(r for r in frozen['records'] if r['corpustrail_paper_id']==pid)
        self.assertEqual(result['abstract'],'Explicit recovered abstract.')
        self.assertEqual(next(r for r in frozen['lineage'] if r['paper_id']==pid)['metadata'],self.project.discovery.metadata(pid))
        self.assertEqual(self.project.evidence.status(self.ids[1])['pending_identity'],1)

    def test_missing_title_and_abstract_blocks_export_without_dropping_member(self):
        record=BibliographicRecord(identifiers=(Identifier('doi','10.1234/empty'),))
        source=SourceReference('fixture://empty','empty',digest_bytes(b'empty'),5,'fixture',AT,identity_status='verified')
        pid=self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
        self.review(pid,'included')
        self.assertEqual(self.service.preview()['missing_title_and_abstract'],1)
        self.assertEqual(self.service.preview()['records'],4)
        with self.assertRaises(ContractError):self.service.plan('blocked',created_at=AT)
        self.assertFalse((self.root/'data/asreview').exists())


if __name__=='__main__':unittest.main()
