"""Offline interoperability fixture, not scientific labels or a systematic review."""
import argparse
import csv
import json
from pathlib import Path

from corpustrail._internal.values import canonical
from corpustrail.curation import EvidenceBasis, ReviewEvent
from corpustrail.export.asreview import FIELDS
from corpustrail.identity import Identifier
from corpustrail.knowledge.registry import VERSION
from corpustrail.project import Project, ProjectConfig, ProviderConfig, ReviewPolicy
from corpustrail.providers.metadata import MetadataProvider
from corpustrail.providers.network import HttpResponse

AT='2026-01-01T00:00:00+00:00'


class RecordedTransport:
    network=False
    def __init__(self,response):self.response=response
    def request(self,url,*,method,headers,body):
        return HttpResponse(200,{},canonical(self.response).encode('utf-8'),url)


def run(root,*,prioritize=False):
    project=Project.create(root,ProjectConfig('synthetic-export','Materials sensors',
        'Invented software-interoperability fixture, not scientific reference evidence',
        providers=(ProviderConfig('openalex','openalex'),),
        review=ReviewPolicy(authorized_reviewers=('fixture_reviewer',))),created_by='fixture',created_at=AT)
    titles=['Porous ceramic sensor report','Porous ceramic sensor report','Porous ceramic methods',
            'A ledger bookkeeping report','An invoice ledger report','Evidence gap report',
            'Unreviewed materials appendix','Deferred materials note']
    response={'results':[{'id':'https://openalex.org/W'+str(500+i),'title':title,
        **({'doi':'https://doi.org/10.1234/fixture.'+str(i)} if i!=1 else {}),
        **({'abstract_inverted_index':{'Invented':[0],'materials':[1],'measurement':[2]}} if i!=1 else {})}
        for i,title in enumerate(titles)],'meta':{'count':len(titles),'next_cursor':None}}
    provider=MetadataProvider('openalex'); provider.network=False
    plan=project.discovery.plan(provider,run_id='fixture-discovery',query='invented materials',created_at=AT)
    project.discovery.execute(plan,provider,transport=RecordedTransport(response),clock=lambda:AT)
    links=project.discovery.canonicalize(plan.run_id,approve_new_identities=True,approve_aliases=True)
    ids=[project.identities.exact_owner(Identifier('openalex','W'+str(500+i))) for i in range(len(titles))]
    for pid,state in zip(ids,('included','included','included','excluded','excluded','insufficient_evidence',None,'unresolved')):
        if state is None:continue
        source=project.identities.observations(pid)[0]['source']
        event=ReviewEvent(pid,state,{'included':'sufficient','excluded':'sufficient','insufficient_evidence':'insufficient','unresolved':'undetermined'}[state],
            'metadata','Invented fixture review, not real scientific judgment','fixture_reviewer',AT,
            (EvidenceBasis('metadata',source['source_sha256'],source['source_uri'],artifact_validity='verified'),),
            authority_state='human_authorized')
        project.reviews.apply(project.reviews.plan(event),recorded_at=AT)
    xml=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/fixture.0</article-id></article-meta></front><body><p>Invented measurement used a synthetic sensor.</p></body></article>'
    project.evidence.preserve_document(ids[0],xml,representation='jats_xml',media_type='application/xml',
        source_uri='fixture://document',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='1',created_at=AT)
    rep=next(r for r in project.evidence.representations(ids[0]) if r['payload']['representation']=='structured_text')
    draft={'subject_type':'paper','subject_id':ids[0],'paper_id':ids[0],'predicate':'ct.measurement_modality',
        'vocabulary_version':VERSION,'raw_value':'synthetic sensor','value_datatype':'string',
        'producer_type':'parser/document','producer_id':'fixture-parser','created_at':AT,
        'evidence_representation':'structured_text','source':{'reference':'fixture://document'},
        'evidence_reference':{'kind':'representation','event_id':rep['event_id']},'lineage_ref':'fixture-knowledge'}
    project.knowledge_store.apply(project.knowledge_store.plan_batch([draft]))
    ranking=None
    if prioritize:
        training=project.prioritization.snapshot(label_cutoff=AT,created_at=AT)
        model=project.prioritization.train(training['artifact_id'],created_at=AT)
        ranking=project.prioritization.rank(model['artifact_id'],run_id='fixture-order',paper_ids=ids,created_at=AT)['scores']
    service=project.asreview; preview=service.preview(); snapshot=service.plan('fixture-corpus',created_at=AT)
    service.create(snapshot); original=project.reviews.corpus()
    mappings=[]
    for review,question in (('review-A','question-A'),('review-B','question-B')):
        rows=[dict(row,asreview_label=('0' if i==0 else '1') if review=='review-A' else '-1')
              for i,row in enumerate(snapshot['records'])]
        results=root/(review+'.csv')
        with results.open('x',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=[*FIELDS,'asreview_label']); writer.writeheader(); writer.writerows(rows)
        mappings.append(service.map_results('fixture-corpus',results=results,review_id=review,question_id=question,
            mapping_id='result-1',asreview_version='2.2',created_at=AT))
    assert project.reviews.corpus()==original
    assert Project.open(root).asreview.inspect('fixture-corpus')==service.inspect('fixture-corpus')
    return {'network_used':False,'warning':'Synthetic fixture only, no scientific validation',
        'canonical_papers':len(links),'preview':preview,'export_id':snapshot['export_id'],
        'dataset_sha256':service.inspect('fixture-corpus')['dataset_sha256'],
        'round_trip_records':[len(m['records']) for m in mappings],
        'downstream_review_ids':[m['review_id'] for m in mappings],
        'broad_member_can_be_downstream_excluded':any(r['question_specific_label']==0 for r in mappings[0]['records']),
        'prioritization_exercised':prioritize,'ranking':ranking,'membership_unchanged':True,
        'paths':service._paths(service._export_path('fixture-corpus'))}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path); parser.add_argument('--prioritize',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.project,prioritize=args.prioritize),sort_keys=True))
