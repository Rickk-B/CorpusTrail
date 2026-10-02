"""Offline software fixture, not scientific assertions about real literature."""
import json
from pathlib import Path
import sys

from corpustrail._internal.values import digest_bytes
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.knowledge.registry import VERSION
from corpustrail.project import Project, ProjectConfig, ReviewPolicy

AT = '2026-01-01T00:00:00+00:00'


def demonstrate(root):
    project = Project.create(root, ProjectConfig('synthetic-knowledge','Materials characterization',
        'Invented records solely for testing scientific assertion storage',
        review=ReviewPolicy(authorized_reviewers=('fixture_reviewer',))),created_by='fixture',created_at=AT)
    body = b'{"synthetic":true}'
    source = SourceReference('fixture://bibliography','one',digest_bytes(body),len(body),'fixture',AT,identity_status='verified')
    pid = project.identities.apply(project.identities.plan(BibliographicRecord(
        title='An invented materials report',abstract='Invented characterization methods.',
        identifiers=(Identifier('fixture.record','one'),)),source),approve_new_identity=True,approve_aliases=True)
    obs = project.identities.observations(pid)[0]['observation_id']
    base = {'subject_type':'paper','subject_id':pid,'paper_id':pid,'predicate':'ct.report_role',
        'vocabulary_version':VERSION,'raw_value':'methods','value_datatype':'string',
        'producer_type':'human','producer_id':'fixture_reviewer','created_at':AT,
        'evidence_representation':'abstract','source':{'reference':'fixture://bibliography','artifact_sha256':digest_bytes(body)},
        'lineage_ref':'fixture-read-one','evidence_reference':{'kind':'bibliographic_observation','observation_id':obs,'field':'abstract'}}
    store = project.knowledge_store
    drafts = [base, {**base,'producer_type':'parser/document','producer_id':'fixture_parser','lineage_ref':'independent-source'},
              {**base,'raw_value':'theory','producer_type':'imported/external','producer_id':'fixture_export','lineage_ref':'conflicting-source'},
              {**base,'predicate':'ct.intervention_exposure','raw_value':None,'value_datatype':'unknown','lineage_ref':'unknown-value'}]
    plan = store.plan_batch(drafts); first = store.apply(plan)
    duplicate = store.apply(plan)
    assertion = plan['assertions'][0]['id']
    event = {'target_assertion_id':assertion,'relation':'validates','actor_type':'human','actor_id':'fixture_reviewer',
        'created_at':AT,'rationale':'Synthetic validation demonstration, not real scientific truth',
        'source':{'reference':'fixture://explicit-validation','artifact_sha256':digest_bytes(b'fixture-approval')},
        'lineage_ref':'validation-demo','purpose':'knowledge.organization','policy_id':'fixture-validation/v1'}
    approval_plan = store.plan_batch(events=[event])
    approval = {'plan_sha256':approval_plan['plan_sha256'],'reviewer_id':'fixture_reviewer',
        'purposes':[event['purpose']],'policy_id':event['policy_id'],'decision_source':event['source']}
    store.apply(approval_plan,human_authorization=approval)
    before = project.knowledge.observations(pid)
    assert Project.open(root).knowledge.observations(pid)==before
    assert project.reviews.membership(pid)['state']=='not_reviewed'
    return {'paper_id':pid,'assertions_added':first['assertions'],'identical_replay':duplicate,
        'knowledge_observations':len(before),'candidate_conflicts':len(project.knowledge.conflicts(pid)),
        'authority_grants':len(store.authoritative('knowledge.organization')),
        'membership':project.reviews.membership(pid)['state'],'verification':store.verify(),
        'unknown_value_preserved':store.assertions(predicate='ct.intervention_exposure')[0]['payload']['raw_value'] is None}


if __name__=='__main__':
    print(json.dumps(demonstrate(Path(sys.argv[1])),sort_keys=True))
