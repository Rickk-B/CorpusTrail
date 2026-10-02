"""Offline generic contracts: no historical data, extraction, or model dependencies."""
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch

from corpustrail._internal.database import connection, create_database, migrations
from corpustrail._internal.values import canonical, content_hash, digest_bytes, ContractError
from corpustrail.cli import main
from corpustrail.curation import ReviewEvent, EvidenceBasis
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.knowledge import Concept, Registry
from corpustrail.knowledge.registry import VERSION
from corpustrail.project import Project, ProjectConfig, ReviewPolicy, ConceptExtension

AT = '2026-01-01T00:00:00+00:00'
LATER = '2026-01-02T00:00:00+00:00'


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'topic'
        self.config = ProjectConfig('fixture-topic','Materials characterization','Synthetic unrelated topic',
            review=ReviewPolicy(authorized_reviewers=('reviewer',)),
            concept_extensions=(ConceptExtension('materials','v1',('materials.pore_structure',)),))
        self.project = Project.create(self.root,self.config,created_by='fixture',created_at=AT)
        self.ids = [self.enroll(i) for i in range(2)]

    def enroll(self,i):
        source = SourceReference('fixture://source',str(i),digest_bytes(b'fixture'),7,'fixture',AT,identity_status='verified')
        record = BibliographicRecord('Invented material '+str(i),'Synthetic abstract.' if i==0 else None,
            identifiers=(Identifier('doi','10.1234/fixture.'+str(i)),))
        return self.project.identities.apply(self.project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)

    def draft(self,**kwargs):
        pid = self.ids[0]
        source = self.project.identities.observations(pid)[0]
        return {'subject_type':'paper','subject_id':pid,'paper_id':pid,'predicate':'ct.organism_population',
            'vocabulary_version':VERSION,'raw_value':'human','value_datatype':'string','producer_type':'model',
            'producer_id':'synthetic-model','producer_version':'fixture-v1','created_at':AT,
            'evidence_representation':'abstract','source':{'reference':'fixture://source','artifact_sha256':digest_bytes(b'fixture')},
            'lineage_ref':'fixture-extraction','evidence_reference':{'kind':'bibliographic_observation',
                'observation_id':source['observation_id'],'field':'abstract'},**kwargs}

    def append(self,draft=None):
        plan=self.project.knowledge_store.plan_batch([draft or self.draft()])
        self.project.knowledge_store.apply(plan)
        return plan['assertions'][0]['id']

    def event(self,target,relation,**kwargs):
        return {'target_assertion_id':target,'relation':relation,'actor_type':'human','actor_id':'reviewer',
            'created_at':LATER,'rationale':'Explicit fixture event','source':{'reference':'fixture://review',
                'artifact_sha256':digest_bytes(b'approved fixture event')},'lineage_ref':'fixture-human-event',
            'purpose':'knowledge.organization','policy_id':'fixture-policy/v1',**kwargs}

    def apply_event(self,event):
        store=self.project.knowledge_store; plan=store.plan_batch(events=[event])
        return store.apply(plan,human_authorization={'plan_sha256':plan['plan_sha256'],
            'reviewer_id':event['actor_id'],'purposes':[event['purpose']],
            'policy_id':event['policy_id'],'decision_source':event['source']})

    def protected(self):
        with connection(self.project.database_path) as db:
            return {name:[tuple(r) for r in db.execute('SELECT * FROM '+name+' ORDER BY 1')] for name in
                ('paper_entities','ct_review_events','ct_priority_artifacts','ct_priority_runs','ct_pipeline_events','screening_events','screening_approvals')}

    def test_immutable_content_and_replace_protection(self):
        self.append()
        for table in ('knowledge_assertions','knowledge_concepts'):
            for sql in ('DELETE FROM '+table,'UPDATE '+table+' SET predicate=predicate',
                        'INSERT OR REPLACE INTO '+table+' SELECT * FROM '+table):
                with self.assertRaises(sqlite3.IntegrityError), connection(self.project.database_path,write=True) as db:
                    db.execute(sql)

    def test_same_import_idempotent_independent_support_preserved(self):
        plan=self.project.knowledge_store.plan_batch([self.draft()])
        self.assertEqual(self.project.knowledge_store.apply(plan)['assertions'],1)
        self.assertEqual(self.project.knowledge_store.apply(plan)['assertions'],0)
        self.append(self.draft(producer_id='another-model'))
        self.append(self.draft(lineage_ref='independent-evidence'))
        self.assertEqual(len(self.project.knowledge_store.assertions()),3)
        self.assertEqual(self.project.knowledge.conflicts(),[])

    def test_conflicts_preserve_unknown_and_multivalue_semantics(self):
        first=self.append(); self.append(self.draft(raw_value='rabbit',producer_id='another'))
        self.append(self.draft(raw_value=None,value_datatype='unknown',lineage_ref='unknown'))
        before=self.protected(); conflicts=self.project.knowledge.conflicts()
        self.assertEqual(len(conflicts),1)
        self.assertEqual(conflicts[0]['resolution'],'not_inferred')
        self.assertEqual(len(conflicts[0]['observations']),3)
        self.assertEqual(self.protected(),before)
        self.assertEqual(self.project.knowledge_store.assertions()[0]['payload']['initial_authority'],'non_authoritative')
        self.assertEqual(len(self.project.knowledge_store.assertions()),3)
        self.assertEqual(len(self.project.knowledge.query('ct.organism_population','human')),1)

    def test_producer_is_not_authority_human_validation_is_explicit(self):
        model=self.append(); human=self.append(self.draft(producer_type='human',producer_id='reviewer',lineage_ref='human-note'))
        self.assertEqual(self.project.knowledge_store.authoritative('knowledge.organization'),[])
        self.apply_event(self.event(model,'validates'))
        self.assertEqual(self.project.knowledge_store.authoritative('knowledge.organization'),[])
        self.apply_event(self.event(model,'grants_authority'))
        records=self.project.knowledge_store.authoritative('knowledge.organization')
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['assertion']['payload']['producer_type'],'model')
        self.assertEqual(self.project.knowledge_store.authoritative('knowledge.other'),[])
        self.assertEqual(self.project.reviews.membership(self.ids[0])['state'],'not_reviewed')

    def test_model_cannot_validate_or_grant(self):
        target=self.append()
        for relation in ('validates','grants_authority','revokes_authority'):
            with self.assertRaises(ValueError): self.project.knowledge_store.plan_batch(events=[self.event(target,relation,actor_type='model')])
        plan=self.project.knowledge_store.plan_batch(events=[self.event(target,'grants_authority')])
        with self.assertRaises(ValueError): self.project.knowledge_store.apply(plan)
        event=self.event(target,'grants_authority',actor_id='unconfigured')
        with self.assertRaises(ValueError):self.apply_event(event)

    def test_grant_revocation_targets_specific_grant_without_erasing_producer(self):
        target=self.append(); grant=self.event(target,'grants_authority'); self.apply_event(grant)
        grant_id=self.project.knowledge_store.history(target)[0]['id']
        self.apply_event(self.event(target,'revokes_authority',target_event_id=grant_id))
        self.assertEqual(self.project.knowledge_store.authoritative('knowledge.organization'),[])
        self.assertEqual(len(self.project.knowledge_store.validation_history(target)),2)
        self.assertEqual(self.project.knowledge_store.assertions()[0]['payload']['producer_type'],'model')

    def test_append_only_supersession_and_dispute(self):
        old=self.append(); before=self.project.knowledge_store.assertions()
        new=self.append(self.draft(raw_value='rabbit',lineage_ref='corrected-extraction'))
        self.apply_event(self.event(old,'supersedes',source_assertion_id=new))
        self.apply_event(self.event(old,'disputes'))
        self.assertIn(before[0],self.project.knowledge_store.assertions())
        self.assertEqual(len(self.project.knowledge_store.history(old)),2)
        self.assertEqual(len(self.project.knowledge.conflicts()),1)
        with self.assertRaises(sqlite3.IntegrityError), connection(self.project.database_path,write=True) as db:
            db.execute('DELETE FROM knowledge_events')

    def test_batch_transaction_rollback_and_no_production_state_effect(self):
        before=self.protected()
        plan=self.project.knowledge_store.plan_batch([self.draft(),self.draft(paper_id='missing',subject_id='missing')])
        with self.assertRaises(ValueError): self.project.knowledge_store.apply(plan)
        self.assertEqual(self.project.knowledge_store.assertions(),[])
        self.append(); self.apply_event(self.event(self.project.knowledge_store.assertions()[0]['id'],'grants_authority'))
        self.assertEqual(self.protected(),before)

    def test_read_paths_preserve_database_bytes_and_are_deterministic(self):
        target=self.append(); before=self.project.database_path.read_bytes()
        view=self.project.knowledge.observations()
        self.assertEqual(Project.open(self.root).knowledge.observations(),view)
        self.project.knowledge_store.verify(); self.project.knowledge.lineage(self.ids[0])
        self.project.knowledge.vocabulary(); self.project.knowledge.paper_sets(); self.project.knowledge.conflicts()
        self.project.knowledge_store.evidence(target); self.project.knowledge_store.authoritative('knowledge.organization')
        self.assertEqual(self.project.database_path.read_bytes(),before)

    def test_abstract_and_metadata_refs_same_paper_absence_not_inferred(self):
        target=self.append(); evidence=self.project.knowledge_store.evidence(target)
        self.assertTrue(evidence['resolved']['trusted'])
        with self.assertRaises(ValueError): self.append(self.draft(paper_id=self.ids[1],subject_id=self.ids[1]))
        obs=self.project.identities.observations(self.ids[1])[0]['observation_id']
        with self.assertRaises(ValueError): self.append(self.draft(paper_id=self.ids[1],subject_id=self.ids[1],
            evidence_reference={'kind':'bibliographic_observation','observation_id':obs}))
        unknown=self.append(self.draft(raw_value=None,value_datatype='unknown',evidence_representation='none',
            evidence_reference={'kind':'unavailable','reason':'No explicit evidence'},lineage_ref='no-evidence'))
        self.assertFalse(self.project.knowledge_store.evidence(unknown)['resolved']['trusted'])

    def test_pending_document_reference_does_not_confer_trust(self):
        event=self.project.evidence.preserve_document(self.ids[0],b'%PDF-1.4 synthetic pending',representation='pdf',
            media_type='application/pdf',source_uri='fixture://document',legitimate_basis='synthetic_fixture',
            resolver='fixture',resolver_version='1',created_at=AT)
        rep=self.project.evidence.representations(self.ids[0])[0]['payload']
        before=self.protected()
        target=self.append(self.draft(evidence_representation='pdf',source={'reference':'fixture://document',
            'artifact_sha256':rep['artifact_sha256']},evidence_reference={'kind':'representation','event_id':event}))
        self.apply_event(self.event(target,'validates'))
        self.assertFalse(self.project.knowledge_store.evidence(target)['resolved']['trusted'])
        self.assertEqual(self.project.knowledge_store.evidence(target)['resolved']['artifact_validity'],'pending_identity')
        self.assertEqual(self.protected(),before)
        self.assertEqual(self.project.knowledge.paper_sets()['full_text_supported'],[])

    def test_verified_structured_evidence_link_and_location(self):
        xml=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/fixture.0</article-id></article-meta></front><body><sec><title>Methods</title><p>Invented measurements.</p></sec></body></article>'
        self.project.evidence.preserve_document(self.ids[0],xml,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://verified',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='1',created_at=AT)
        rep=next(r for r in self.project.evidence.representations(self.ids[0]) if r['payload']['representation']=='structured_text')
        target=self.append(self.draft(evidence_representation='structured_text',evidence_location={'section':'Methods'},
            source={'artifact_sha256':rep['payload']['artifact_sha256'],'reference':'fixture://verified'},
            evidence_reference={'kind':'representation','event_id':rep['event_id']}))
        self.assertTrue(self.project.knowledge_store.evidence(target)['resolved']['trusted'])
        self.assertEqual(self.project.knowledge.paper_sets()['full_text_supported'],[self.ids[0]])

    def test_normalization_needs_provenance_and_unknown_remains_unknown(self):
        for draft in (self.draft(normalized_value='Human'),self.draft(raw_value=None,value_datatype='unknown',normalized_value='human')):
            with self.assertRaises(ValueError): self.project.knowledge_store.plan_batch([draft])
        self.append(self.draft(normalized_value='Human',normalization={'method':'explicit-test','version':'1','source_ref':'fixture'}))
        self.assertEqual(len(self.project.knowledge.query('ct.organism_population','Human')),1)

    def test_version_subject_datatype_and_unknown_predicate_validation(self):
        for change in ({'vocabulary_version':'wrong'},{'predicate':'organism'},{'value_datatype':'boolean'},
                       {'paper_id':self.ids[1]},{'raw_value':float('nan'),'value_datatype':'number'}):
            with self.assertRaises(ValueError): self.project.knowledge_store.plan_batch([self.draft(**change)])
        self.append(self.draft(subject_type='study',subject_id='synthetic-study',paper_id=None,
            evidence_representation='none',evidence_reference=None))
        self.assertEqual(len(self.project.knowledge_store.assertions(subject_type='study')),1)

    def test_scoped_fields_never_implicitly_become_generic_participation(self):
        for field in ('is_human','human_subject','animal_flag','unfamiliar_field'):
            self.assertEqual(Registry().field(field),'unmapped_field.'+field)
            with self.assertRaises(ValueError): self.project.knowledge_store.plan_batch([self.draft(
                predicate='ct.human_participation',raw_value=True,value_datatype='boolean',source={'field':field})])

    def register(self,concept=None):
        concept=concept or Concept('materials.pore_structure','v1','Pore structure','Explicit project-only fixture',('string','unknown'))
        plan=Registry.plan_extension(self.project,[concept],producer_id='fixture',created_at=AT,source={'reference':'fixture://vocabulary'})
        Registry.apply_extension(self.project,plan)
        return plan

    def test_project_extension_versions_and_no_core_collision(self):
        plan=self.register(); self.assertEqual(Registry.apply_extension(self.project,plan),plan['record_id'])
        self.append(self.draft(predicate='materials.pore_structure',vocabulary_version='v1',raw_value='porous'))
        with self.assertRaises(ContractError): self.register(Concept('ct.organism_population','v1','Bad','Override'))
        with self.assertRaises(ContractError): self.register(Concept('undeclared.organism','v1','Bad','Undeclared'))
        with self.assertRaises(ContractError): self.register(Concept('materials.pore_structure','v1','Changed','Redefined'))
        with self.assertRaises(sqlite3.IntegrityError), connection(self.project.database_path,write=True) as db:
            db.execute('DELETE FROM ct_knowledge_registry_records')

    def test_deprecation_preserves_old_definitions_and_assertions(self):
        self.register(); self.append(self.draft(predicate='materials.pore_structure',vocabulary_version='v1'))
        old=self.project.knowledge_store.assertions()
        config=replace(self.config,config_version=2,concept_extensions=(ConceptExtension('materials','v2',('materials.pore_structure','materials.structure')),))
        self.project.configure(config,expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture',created_at=LATER)
        self.register(Concept('materials.pore_structure','v2','Pore structure','Old concept retained',deprecated=True,superseded_by='materials.structure'))
        self.assertEqual(self.project.knowledge_store.assertions(),old)
        self.assertTrue(self.project.knowledge_store.verify()['ok'])
        self.assertEqual(len(self.project.knowledge.vocabulary()['project_vocabularies']),2)

    def test_stale_plans_and_unauthorized_purpose_are_rejected(self):
        plan=self.project.knowledge_store.plan_batch([self.draft()])
        self.register()
        with self.assertRaises(ValueError):self.project.knowledge_store.apply(plan)
        target=self.append()
        with self.assertRaises(ValueError):self.project.knowledge_store.plan_batch(events=[self.event(target,'grants_authority',purpose='corpus.membership')])

    def test_historical_compatibility_tables_not_read_or_populated(self):
        before=self.protected(); self.append()
        observations=self.project.knowledge.observations()
        self.assertEqual({o['origin'] for o in observations},{'stored','adapted'})
        self.assertTrue(all(o['source']['table'] in ('knowledge_assertions','ct_paper_observations') for o in observations))
        with connection(self.project.database_path) as db:
            for table in ('legacy_observations','category_assertions','taxonomy_nodes','screening_events'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(self.protected(),before)

    def test_prior_phase2c_database_upgrades_additively(self):
        target=Path(self.temp.name)/'old'; target.mkdir()
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:34]):
            create_database(target/self.config.database,self.config.to_dict(),AT,'fixture')
            (target/'corpustrail.project.json').write_text(canonical(self.config.to_dict())+'\n',encoding='utf-8')
            old=Project.open(target)
            original_project=self.project; self.project=old
            pid=self.enroll(0)
            source=old.identities.observations(pid)[0]['source']
            review=ReviewEvent(pid,'included','sufficient','metadata','Original fixture','reviewer',AT,
                (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
                authority_state='human_authorized')
            old.reviews.apply(old.reviews.plan(review),recorded_at=AT)
            adapted_before=old.knowledge.observations()
            protected_before=self.protected()
            self.project=original_project
            original=old.status(); original.pop('pending_capabilities')
        with self.assertRaises(ContractError): Project.open(target)
        upgraded=Project.upgrade(target,backup='data/backups/pre35.sqlite3',created_at=LATER)
        actual=upgraded.status(); actual.pop('pending_capabilities'); actual['checks']['migrations']=34
        self.assertEqual(actual,original)
        self.assertEqual(upgraded.knowledge.observations(),adapted_before)
        self.project=upgraded
        self.assertEqual(self.protected(),protected_before)
        with closing(sqlite3.connect(target/'data/backups/pre35.sqlite3')) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],34)

    def test_review_adapter_retains_authority_rationale_and_evidence_without_copying(self):
        pid=self.ids[0]; obs=self.project.identities.observations(pid)[0]['source']
        review=ReviewEvent(pid,'included','sufficient','abstract','Original fixture rationale','reviewer',AT,
            (EvidenceBasis('abstract',obs['source_sha256'],obs['source_uri'],artifact_validity='verified'),),
            authority_state='human_authorized')
        self.project.reviews.apply(self.project.reviews.plan(review),recorded_at=AT)
        before=self.protected(); count=len(self.project.knowledge_store.assertions())
        records=self.project.knowledge.observations(pid,predicate='ct.broad_corpus_membership')
        self.assertEqual(records[0]['authority']['source_status'],'human_authorized')
        self.assertEqual(records[0]['source']['original_review']['rationale'],'Original fixture rationale')
        self.assertEqual(len(self.project.knowledge_store.assertions()),count)
        self.append(); self.assertEqual(self.protected(),before)

    def test_model_supersession_cannot_revoke_human_knowledge_authority(self):
        old=self.append(); self.apply_event(self.event(old,'grants_authority'))
        new=self.append(self.draft(raw_value='rabbit',lineage_ref='different'))
        plan=self.project.knowledge_store.plan_batch(events=[self.event(old,'supersedes',source_assertion_id=new,
            actor_type='model',actor_id='fixture-model')])
        self.project.knowledge_store.apply(plan)
        self.assertEqual(self.project.knowledge_store.authoritative('knowledge.organization')[0]['assertion']['id'],old)
        self.assertEqual(len(self.project.knowledge.conflicts()),1)

    def test_wrong_representation_and_corrupted_artifact_rejected(self):
        event=self.project.evidence.preserve_document(self.ids[0],b'%PDF pending fixture',representation='pdf',
            media_type='application/pdf',source_uri='fixture://document',legitimate_basis='synthetic_fixture',
            resolver='fixture',resolver_version='1',created_at=AT)
        ref={'kind':'representation','event_id':event}
        with self.assertRaises(ValueError):self.append(self.draft(evidence_reference=ref))
        draft=self.draft(evidence_representation='pdf',source={},evidence_reference=ref)
        target=self.append(draft)
        sha=self.project.knowledge_store.evidence(target)['resolved']['artifact_sha256']
        from corpustrail._internal.pipeline import artifact
        artifact(self.project,sha).write_bytes(b'changed fixture only')
        with self.assertRaises(ValueError):self.project.knowledge_store.evidence(target)
        with self.assertRaises(ValueError):self.project.knowledge_store.verify()

    def test_front_matter_does_not_become_full_text_support(self):
        xml=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/fixture.0</article-id><abstract><p>Only abstract text.</p></abstract></article-meta></front></article>'
        self.project.evidence.preserve_document(self.ids[0],xml,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://front',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='1',created_at=AT)
        rep=next(r for r in self.project.evidence.representations(self.ids[0]) if r['payload']['representation']=='structured_text')
        self.append(self.draft(evidence_representation='structured_text',source={},
            evidence_reference={'kind':'representation','event_id':rep['event_id']}))
        self.assertEqual(self.project.knowledge.paper_sets()['full_text_supported'],[])

    def test_cli_plan_apply_verify_and_reads(self):
        source=Path(self.temp.name)/'draft.json'; source.write_text(canonical(self.draft()),encoding='utf-8')
        output=io.StringIO()
        with patch('sys.stdout',output):self.assertEqual(main(['knowledge','assert',str(self.root),'--input',str(source)]),0)
        plan=Path(self.temp.name)/'plan.json'; plan.write_text(output.getvalue(),encoding='utf-8')
        with patch('sys.stdout',io.StringIO()):
            self.assertEqual(main(['knowledge','apply',str(self.root),'--plan',str(plan),'--apply']),0)
            self.assertEqual(main(['knowledge','show',str(self.root),'--paper-id',self.ids[0]]),0)
            self.assertEqual(main(['knowledge','query',str(self.root),'--predicate','ct.organism_population','--value-json','"human"']),0)
            self.assertEqual(main(['knowledge','verify',str(self.root)]),0)

    def test_relations_preserve_originals_and_replay_events_is_idempotent(self):
        old=self.append(); new=self.append(self.draft(lineage_ref='independent'))
        for relation in ('duplicates','derived_from','retracts','rejects'):
            event=self.event(old,relation,source_assertion_id=new if relation in ('duplicates','derived_from') else None)
            plan=self.project.knowledge_store.plan_batch(events=[event])
            self.assertEqual(self.project.knowledge_store.apply(plan)['events'],1)
            self.assertEqual(self.project.knowledge_store.apply(plan)['events'],0)
        self.assertEqual(len(self.project.knowledge_store.assertions()),2)
        self.assertEqual(len(self.project.knowledge_store.history(old)),4)
        with self.assertRaises(ValueError):self.project.knowledge_store.plan_batch(events=[self.event(old,'supersedes',source_assertion_id=old)])

    def test_forged_hash_and_stale_lineage_fail_closed(self):
        plan=self.project.knowledge_store.plan_batch([self.draft()])
        corrupt=deepcopy(plan); corrupt['assertions'][0]['payload']['raw_value']='changed'
        with self.assertRaises(ValueError):self.project.knowledge_store.apply(corrupt)
        target=self.append(); stale=self.project.knowledge_store.plan_batch([self.draft(lineage_ref='second')])
        self.apply_event(self.event(target,'validates'))
        with self.assertRaises(ValueError):self.project.knowledge_store.apply(stale)

    def test_external_evidence_is_explicit_and_never_locally_verified(self):
        target=self.append(self.draft(evidence_representation='imported_metadata',source={'reference':'fixture://external'},
            evidence_reference={'kind':'external','uri':'fixture://external'}))
        self.assertFalse(self.project.knowledge_store.evidence(target)['resolved']['trusted'])
        self.assertEqual(self.project.knowledge_store.evidence(target)['resolved']['validity'],'unverified_external')


if __name__=='__main__':unittest.main()
