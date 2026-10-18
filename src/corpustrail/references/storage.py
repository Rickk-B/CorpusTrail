"""Immutable shared chunks; no delta-chain replay or evidence duplication."""
import hashlib
import json

from corpustrail._internal.values import ContractError, canonical, content_hash, identifier
from .contracts import SCHEMA, exact_id


def ready(db):
    return db.execute('SELECT 1 FROM schema_migrations WHERE version=39').fetchone() is not None


def require(db):
    if not ready(db):raise ContractError('Enable reference storage with an explicit backed-up project upgrade first.')


def assignment(db, aid):
    exact_id(aid,'reference-assignment')
    row=db.execute('SELECT * FROM ct_reference_assignments WHERE assignment_id=?',(aid,)).fetchone()
    if row is None:raise ContractError('reference assignment is not in this project')
    data=json.loads(row['payload_json'])
    if (identifier('reference-assignment',data)!=aid or content_hash(data)!=row['content_sha256']
            or row['paper_id']!=data['paper_id'] or row['label']!=data['label']):
        raise ContractError('reference assignment integrity changed')
    return data


def header(db, vid):
    require(db);exact_id(vid,'reference-version')
    row=db.execute('SELECT * FROM ct_reference_versions WHERE version_id=?',(vid,)).fetchone()
    if row is None:raise ContractError('reference version is not in this project')
    data=json.loads(row['payload_json'])
    if (identifier('reference-version',data)!=vid or data['schema']!=SCHEMA
            or any(row[k]!=data[k] for k in ('collection_id','version','parent_id','request_id','request_sha256','config_event_id'))
            or data['project_id']!=db.execute('SELECT project_id FROM ct_project_identity WHERE singleton=1').fetchone()[0]):
        raise ContractError('reference header integrity changed')
    refs=[dict(r) for r in db.execute('SELECT bucket,ordinal,chunk_id FROM ct_reference_version_chunks WHERE version_id=? ORDER BY bucket,ordinal',(vid,))]
    if refs!=data['chunks'] or content_hash(refs)!=data['manifest_sha256']:
        raise ContractError('reference membership root changed')
    return data


def chunks(members):
    buckets={}
    for aid,data in members.items():
        bucket=int(hashlib.sha256(data['paper_id'].encode()).hexdigest()[:2],16)
        buckets.setdefault(bucket,[]).append((data['paper_id'],aid))
    result=[]
    for bucket,items in sorted(buckets.items()):
        ordered=sorted(items)
        for start in range(0,len(ordered),256):
            ids=[x[1] for x in ordered[start:start+256]]
            result.append({'bucket':bucket,'ordinal':start//256,'chunk_id':identifier('reference-chunk',ids),'ids':ids})
    return result


def summary(members):
    labels={}
    for data in members.values():labels.setdefault(data['paper_id'],set()).add(data['label'])
    attested={d['paper_id'] for d in members.values() if d['human_attested'] and d['producer']['type']=='human'}
    return {'assignment_count':len(members),'paper_count':len(labels),
        'in_scope':sum(v=={'in_scope'} and pid in attested for pid,v in labels.items()),
        'out_of_scope':sum(v=={'out_of_scope'} and pid in attested for pid,v in labels.items()),
        'conflicts':sum(len(v)>1 for v in labels.values()),
        'unattested':sum(not v['human_attested'] for v in members.values())}


def checked_chunk(db,cid):
    row=db.execute('SELECT * FROM ct_reference_chunks WHERE chunk_id=?',(cid,)).fetchone()
    if row is None:raise ContractError('reference chunk missing')
    ids=json.loads(row['payload_json'])
    actual=[dict(r) for r in db.execute('SELECT position,assignment_id FROM ct_reference_chunk_items WHERE chunk_id=? ORDER BY position',(cid,))]
    if identifier('reference-chunk',ids)!=cid or len(ids)!=row['item_count'] or actual!=[{'position':i,'assignment_id':aid} for i,aid in enumerate(ids)]:
        raise ContractError('reference chunk integrity changed')
    return ids


def stored(db,vid):
    data=header(db,vid)
    refs=[dict(r) for r in db.execute('SELECT bucket,ordinal,chunk_id FROM ct_reference_version_chunks WHERE version_id=? ORDER BY bucket,ordinal',(vid,))]
    if refs!=data['chunks'] or content_hash(refs)!=data['manifest_sha256']:
        raise ContractError('reference version membership integrity changed')
    members={}
    for ref in refs:
        for aid in checked_chunk(db,ref['chunk_id']):
            if aid in members:raise ContractError('repeated reference membership')
            members[aid]=assignment(db,aid)
    if summary(members)!=data['counts']:raise ContractError('reference version count integrity changed')
    if [{k:v for k,v in c.items() if k!='ids'} for c in chunks(members)]!=refs:
        raise ContractError('reference chunk ordering changed')
    changes=[]
    for number,row in enumerate(db.execute('SELECT * FROM ct_reference_changes WHERE version_id=? ORDER BY position',(vid,))):
        body=json.loads(row['payload_json'])
        if row['position']!=number or content_hash(body)!=row['content_sha256'] or row['content_sha256']!=data['change_hashes'][number]:raise ContractError('reference correction integrity changed')
        changes.append(body)
    if content_hash(changes)!=data['changes_sha256']:raise ContractError('reference correction manifest changed')
    return data,members


def insert_version(db,vid,data,new_assignments,changes,parts):
    for aid,value in new_assignments.items():
        db.execute('INSERT INTO ct_reference_assignments(assignment_id,paper_id,label,payload_json,content_sha256) VALUES (?,?,?,?,?)',
            (aid,value['paper_id'],value['label'],canonical(value),content_hash(value)))
    db.execute('INSERT INTO ct_reference_versions(version_id,collection_id,version,parent_id,request_id,request_sha256,config_event_id,payload_json) VALUES (?,?,?,?,?,?,?,?)',
        (vid,*(data[k] for k in ('collection_id','version','parent_id','request_id','request_sha256','config_event_id')),canonical(data)))
    for part in parts:
        ids=part['ids'];cid=part['chunk_id']
        prior=db.execute('SELECT 1 FROM ct_reference_chunks WHERE chunk_id=?',(cid,)).fetchone()
        if prior:checked_chunk(db,cid)
        else:
            db.execute('INSERT INTO ct_reference_chunks VALUES (?,?,?)',(cid,canonical(ids),len(ids)))
            db.executemany('INSERT INTO ct_reference_chunk_items VALUES (?,?,?)',((cid,i,aid) for i,aid in enumerate(ids)))
        db.execute('INSERT INTO ct_reference_version_chunks VALUES (?,?,?,?)',(vid,part['bucket'],part['ordinal'],cid))
    db.executemany('INSERT INTO ct_reference_changes VALUES (?,?,?,?)',((vid,i,canonical(c),content_hash(c)) for i,c in enumerate(changes)))
