"""Freeze exact existing bibliography/evidence; never promote pending documents."""
import json

from corpustrail._internal.pipeline import artifact_in_connection, events_in_connection
from corpustrail._internal.values import ContractError, content_hash, digest_bytes
from corpustrail.populations.service import PopulationService


def freeze(project,db,pid,used):
    identity=PopulationService._identity(db,pid)
    metadata=project.discovery._metadata(db,pid)
    bibliography={k:metadata['fields'][k] for k in ('title','authors','year','source')}
    if len(json.dumps(bibliography,ensure_ascii=False).encode('utf-8'))>65536:
        raise ContractError('bibliographic snapshot exceeds the explicit 64-KiB per-assignment resource bound; no text was silently truncated')
    available={'metadata':{'kind':'metadata','bibliography':bibliography,'sha256':content_hash(bibliography),
        'field_provenance':{k:v for k,v in metadata['field_provenance'].items() if k!='abstract'},
        'selection_rule':metadata['selection_rule']}}
    abstract=metadata['fields']['abstract']
    if abstract:
        origin=metadata['field_provenance']['abstract']
        available['abstract']={'kind':'abstract','source_id':origin,'sha256':digest_bytes(abstract.encode()),'characters':len(abstract)}
    representations=events_in_connection(db,kind='representation',paper_id=pid)
    readable=[r for r in representations if r['payload']['trusted'] and r['payload']['artifact_validity']=='verified'
        and r['payload']['representation']=='structured_text' and r['payload'].get('evidence_depth')=='document_body']
    if readable:
        selected=readable[0]
        available['structured_text']={'kind':'structured_text','source_id':selected['event_id'],'sha256':selected['payload']['artifact_sha256']}
    if not isinstance(used,list) or any(not isinstance(x,str) for x in used) or len(used)!=len(set(used)) or any(x not in available for x in used):
        raise ContractError('evidence actually used must be an explicit subset of this frozen available evidence')
    result={'schema':'corpustrail-reference-evidence/v1','identity':identity,'available':available,'used':sorted(used)}
    # Hash-check every explicitly claimed basis, not simply its display status.
    for kind in used:resolve(project,db,pid,available[kind])
    return result


def resolve(project,db,pid,entry):
    if entry['kind']=='metadata':
        bibliography=entry['bibliography']
        if content_hash(bibliography)!=entry['sha256']:raise ContractError('frozen bibliographic evidence changed')
        return '\n'.join(str(bibliography[k]) for k in ('title','authors','year','source') if bibliography[k])
    if entry['kind']=='abstract':
        row=db.execute('SELECT 1 FROM ct_paper_observations WHERE observation_id=?',(entry['source_id'],)).fetchone()
        if row:
            source,data=PopulationService._observation(db,entry['source_id'])
            if source['paper_id']!=pid:raise ContractError('abstract belongs to another publication')
            value=data['record']['abstract']
        else:value=None
    else:value=None
    if value is None:
        matches=[r for r in events_in_connection(db,kind='representation',paper_id=pid) if r['event_id']==entry['source_id']]
        if not matches:raise ContractError('frozen document representation is unavailable')
        data=matches[0]['payload']
        if (not data['trusted'] or data['artifact_validity']!='verified' or data['representation']!=entry['kind']
                or data['artifact_sha256']!=entry['sha256'] or entry['kind']=='structured_text' and data.get('evidence_depth')!='document_body'):
            raise ContractError('frozen representation is not eligible verified text')
        value=artifact_in_connection(project,db,entry['sha256']).read_text(encoding='utf-8')
    if digest_bytes(value.encode())!=entry['sha256']:raise ContractError('frozen reference evidence bytes changed')
    return value
