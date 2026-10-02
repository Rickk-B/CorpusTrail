"""Invented, offline software demonstration; no scientific validation or real labels."""

import argparse
import json
from pathlib import Path

from corpustrail._internal.values import canonical
from corpustrail.curation import EvidenceBasis, ReviewEvent
from corpustrail.identity import Identifier
from corpustrail.project import Project, ProjectConfig, ProviderConfig, ReviewPolicy
from corpustrail.providers.metadata import MetadataProvider
from corpustrail.providers.network import HttpResponse

AT='2026-01-01T00:00:00+00:00'
LATER='2026-01-02T00:00:00+00:00'


class RecordedTransport:
    network=False
    def __init__(self,response):
        self.response=response
    def request(self,url,*,method,headers,body):
        return HttpResponse(200,{},canonical(self.response).encode('utf-8'),url)


def fixture(target):
    project=Project.create(target,ProjectConfig('synthetic-curation','Porous materials',
        'Invented offline software fixture, not a scientific benchmark',
        providers=(ProviderConfig('openalex','openalex'),),
        review=ReviewPolicy(authorized_reviewers=('fixture_reviewer',))),created_by='fixture',created_at=AT)
    titles=['Porous ceramic sensor experiment','Porous ceramic measurement',
            'Invoice accounting procedure','Shipping ledger bookkeeping',
            'Untitled material evidence gap','Porous ceramic sensor follow-up',
            'Porosity measurement apparatus','Catalog invoice entry',
            'Porous material comparison','Synthetic inventory appendix']
    records=[]
    for i,title in enumerate(titles):
        row={'id':'https://openalex.org/W'+str(1000+i),'doi':'https://doi.org/10.1234/fixture.'+str(i),
             'title':title,'publication_year':2020+i%4}
        if i not in {4,7}:
            row['abstract_inverted_index']={word:[j] for j,word in enumerate(title.split())}
        records.append(row)
    provider=MetadataProvider('openalex')
    provider.network=False
    plan=project.discovery.plan(provider,run_id='fixture-discovery',query='synthetic fixture',created_at=AT)
    project.discovery.execute(plan,provider,transport=RecordedTransport({'results':records,
        'meta':{'count':len(records),'next_cursor':None}}),clock=lambda:AT)
    project.discovery.canonicalize(plan.run_id,approve_new_identities=True,approve_aliases=True)
    ids=[project.identities.exact_owner(Identifier('doi','10.1234/fixture.'+str(i))) for i in range(len(titles))]
    xml=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/fixture.0</article-id></article-meta></front><body><sec><title>Methods</title><p>A synthetic porous ceramic measurement used a fixture sensor. This is invented software evidence.</p></sec></body></article>'
    project.evidence.preserve_document(ids[0],xml,representation='jats_xml',media_type='application/xml',
        source_uri='fixture://verified-document',legitimate_basis='synthetic_fixture',
        resolver='fixture',resolver_version='1',created_at=AT)
    project.evidence.preserve_document(ids[5],b'%PDF-1.4\nPending fixture PDF',representation='pdf',
        media_type='application/pdf',source_uri='fixture://pending-document',legitimate_basis='synthetic_fixture',
        resolver='fixture',resolver_version='1',created_at=AT)
    return project,ids


def review(project,paper_id,state,*,at=AT):
    source=project.identities.observations(paper_id)[0]['source']
    event=ReviewEvent(paper_id,state,'insufficient' if state=='insufficient_evidence' else 'sufficient',
        'metadata','Invented software-fixture label only','fixture_reviewer',at,
        (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
        authority_state='human_authorized',supersedes=project.reviews.membership(paper_id)['current_event_id'])
    return project.reviews.apply(project.reviews.plan(event),recorded_at=at)


def run(target):
    project,ids=fixture(target)
    for pid,state in zip(ids[:5],('included','included','excluded','excluded','insufficient_evidence')):
        review(project,pid,state)
    snapshot=project.prioritization.snapshot(label_cutoff=AT,created_at=AT)
    model=project.prioritization.train(snapshot['artifact_id'],created_at=AT)
    remaining=ids[4:]
    first=project.prioritization.rank(model['artifact_id'],run_id='fixture-ranking-1',paper_ids=remaining,created_at=AT)
    project.review_sessions.prepare('fixture-session',reviewer_id='fixture_reviewer',paper_ids=remaining,
        mode='operational',authority_state='human_authorized',created_at=AT)
    view=project.review_sessions.view('fixture-session')
    project.review_sessions.update('fixture-session',expected_revision=view['revision'],action='bind_ranking',value='fixture-ranking-1')
    view=project.review_sessions.view('fixture-session')
    project.review_sessions.update('fixture-session',expected_revision=view['revision'],action='ordering',value='priority')
    review(project,ids[5],'included',at=LATER)
    second_snapshot=project.prioritization.snapshot(label_cutoff=LATER,created_at=LATER,parent_snapshot_id=snapshot['artifact_id'])
    second_model=project.prioritization.train(second_snapshot['artifact_id'],parent_model_id=model['artifact_id'],created_at=LATER)
    second=project.prioritization.rank(second_model['artifact_id'],run_id='fixture-ranking-2',paper_ids=remaining,
        created_at=LATER,previous_run_id='fixture-ranking-1')
    assert len(first['scores'])==len(second['scores'])==len(remaining)
    assert project.prioritization.run('fixture-ranking-1')==first
    reopened=Project.open(target)
    assert reopened.reviews.corpus()==project.reviews.corpus()
    assert reopened.review_sessions.view('fixture-session')==project.review_sessions.view('fixture-session')
    return {'warning':'Synthetic software fixture only; no scientific performance claim',
        'network_used':False,'papers':len(ids),'membership':project.status()['membership'],
        'training_rows':len(snapshot['rows']),'binary_training_rows':sum(x['label']!='insufficient_evidence' for x in snapshot['rows']),
        'training_snapshot_id':snapshot['artifact_id'],'model_id':model['artifact_id'],
        'ranking_run_ids':['fixture-ranking-1','fixture-ranking-2'],'remaining_population':remaining,
        'first_ranking':first['scores'],'second_ranking':second['scores'],'low_priority_tail_preserved':True,
        'pending_documents':project.evidence.status(ids[5])['pending_identity'],
        'session_id':'fixture-session','question':project.status()['review_question']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path)
    print(json.dumps(run(parser.parse_args().project),ensure_ascii=False,sort_keys=True,indent=2))
