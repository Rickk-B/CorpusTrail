"""Explicit synthetic reference scale acceptance over real scientific services.

Only creates a NEW project at the supplied output path. No network, engines,
real research data, direct identity-table inserts or implicit membership.
"""
import argparse
import hashlib
from importlib import resources
import json
from pathlib import Path
import platform
import time
from unittest.mock import patch

try:
    import resource
except ImportError:  # Optional engineering measurement; service acceptance still runs.
    resource=None

from corpustrail._internal.database import connection
from corpustrail._internal.pipeline import preserve
from corpustrail._internal.values import canonical,content_hash
from corpustrail.identity import BibliographicRecord,Identifier,SourceReference
from corpustrail.project import Project,ProjectConfig,ReviewPolicy
from corpustrail.references import ContextStrategy
from corpustrail.references.storage import chunks

AT='2026-01-01T00:00:00+00:00'


def assignment(pid,**extra):
    return {'action':'assign','paper_id':pid,'label':'in_scope','producer':{'type':'human','id':'synthetic-curator','version':'manual/v1'},
        'human_attested':True,'rationale':'Synthetic scale fixture only','evidence_used':['metadata'],
        'supersedes':[],'source_assignment_ids':[],'source_event_id':None,'source_artifact_sha256':None,'source_record':None,**extra}


def exercise(root,count):
    if root.exists() or root.is_symlink():raise ValueError('output project must not already exist')
    started=time.perf_counter()
    project=Project.create(root,ProjectConfig('reference-scale','Synthetic reference scale','Invented scale test',
        review=ReviewPolicy(scope='Invented scale corpus')),created_by='synthetic-fixture',created_at=AT)
    source=canonical({'schema':'synthetic-bibliography/v1','records':count}).encode()
    sha=preserve(project,source,'application/json',AT)
    ids=[]
    for number in range(count):
        record=BibliographicRecord('Invented reference '+str(number)+' — 材料',authors=('Synthetic Author',),
            identifiers=(Identifier('doi','10.1234/synthetic.reference.'+str(number)),))
        origin=SourceReference('fixture://reference-scale',str(number),sha,len(source),'synthetic-fixture',AT,identity_status='verified')
        ids.append(project.identities.apply(project.identities.plan(record,origin),approve_new_identity=True,approve_aliases=True))
    enrolled=time.perf_counter();revision=project.configuration_history()[-1]['event_id'];service=project.references;parent=None;versions=[]
    for number,start in enumerate(range(0,count,500)):
        fields={'request_id':f'{number+1:032x}','name':'Synthetic measured references','actor':'synthetic-curator','parent':parent,
            'config_event_id':revision,'created_at':AT,'changes':[assignment(pid) for pid in ids[start:start+500]]}
        preview=service.preview(**fields);frozen=service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
        parent=frozen['version_id'];versions.append(frozen)
    created=time.perf_counter()
    pages=0;offset=0;observed=set();maximum_page_bytes=0
    while True:
        data=service.members(parent,offset=offset,limit=100);pages+=1
        maximum_page_bytes=max(maximum_page_bytes,len(canonical(data).encode()))
        observed.update(item['paper_id'] for item in data['items'])
        if data['next_offset'] is None:break
        offset=data['next_offset']
    if observed!=set(ids):raise AssertionError('paginated reference reconstruction differs')
    paged=time.perf_counter();old=service.inspect(parent);item=service.members(parent,limit=1)['items'][0]
    fields={'request_id':'f'*32,'name':old['name'],'actor':'synthetic-curator','parent':parent,'config_event_id':revision,'created_at':AT,
        'changes':[assignment(item['paper_id'],label='out_of_scope',supersedes=[item['assignment_id']])]}
    preview=service.preview(**fields);successor=service.commit(**fields,expected_preview_sha256=preview['preview_sha256'])
    if service.inspect(parent)!=old:raise AssertionError('earlier reference version changed')
    with connection(project.database_path) as db:
        from corpustrail.references.storage import stored
        header,members=stored(db,parent)
        if chunks(members)!=chunks(dict(reversed(list(members.items())))):raise AssertionError('manifest depends on source iteration order')
        actual_assignments=db.execute('SELECT COUNT(*) FROM ct_reference_assignments').fetchone()[0]
        shared_chunks=db.execute('SELECT COUNT(*) FROM ct_reference_chunks').fetchone()[0]
        physical_memberships=db.execute('SELECT COUNT(*) FROM ct_reference_chunk_items').fetchone()[0]
        if db.execute('SELECT COUNT(*) FROM ct_review_events').fetchone()[0]:raise AssertionError('reference operation published review/membership')
    ctx={'request_id':'e'*32,'version_id':successor['version_id'],'actor':'synthetic-curator','created_at':AT,'config_event_id':revision,
        'target_paper_id':ids[0],'target_basis':'metadata','held_out_paper_ids':[ids[-1]],'dependency_ids':[],'strategy':ContextStrategy()}
    preview=service.prepare_context(**ctx);saved=service.commit_context(**ctx,expected_preview_sha256=preview['preview_sha256'])
    context=Project.open(root).references.context(saved['context_id'],limit=100,verify=True)
    if len(context['items'])>100 or context['decision_count']!=count:raise AssertionError('context provenance is not paginated')
    if any(v['paper_id'] in {ids[0],ids[-1]} for v in context['input']['references']):raise AssertionError('self/held-out label leaked')
    if Project.open(root).references.verify(parent)['counts']['paper_count']!=count:raise AssertionError('restart lost references')
    finished=time.perf_counter()
    return {'schema':'corpustrail-reference-scale-measurement/v1','synthetic_only':True,'python':platform.python_version(),
        'platform':platform.system(),'canonical_publications':count,'assignments_after_correction':actual_assignments,
        'versions':len(versions)+1,'last_version':successor['version_id'],'historical_manifest_sha256':header['manifest_sha256'],
        'reference_pages':pages,'page_limit':100,'maximum_page_bytes':maximum_page_bytes,
        'unique_shared_chunks':shared_chunks,'physical_chunk_memberships':physical_memberships,
        'database_bytes':project.database_path.stat().st_size,'source_artifact_bytes':len(source),
        'enrollment_seconds':enrolled-started,'reference_creation_seconds':created-enrolled,'pagination_seconds':paged-created,
        'correction_context_integrity_seconds':finished-paged,'elapsed_seconds':finished-started,
        'process_peak_rss_native_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None,
        'rss_unit':'KiB on Linux; bytes on macOS','assertions':'exact canonical IDs, complete pages, stable historical versions, deterministic manifest, context leakage guards, restart, no review/membership',
        'fixture_manifest_sha256':content_hash(sorted(ids)),
        'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reference_source_sha256':{name:hashlib.sha256(resources.files('corpustrail.references').joinpath(name).read_bytes()).hexdigest()
            for name in ('__init__.py','contracts.py','service.py','storage.py','evidence.py','context.py')}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True,type=Path);parser.add_argument('--papers',type=int,default=2000)
    args=parser.parse_args()
    if not 1000<=args.papers<=10000:parser.error('measurement workload must be between 1000 and 10000 synthetic papers; not a collection limit')
    with patch('socket.create_connection',side_effect=AssertionError('scale acceptance must remain offline')):
        result=exercise(args.project,args.papers)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
