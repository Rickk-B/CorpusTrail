"""Frozen local context artifacts, not classifier runs or remote invocations."""
from dataclasses import asdict
import json
from corpustrail import __version__

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, digest_bytes, identifier, timestamp
from corpustrail.populations.contracts import command_id, page
from corpustrail.populations.service import PopulationService
from corpustrail.models.contracts import safe_data
from .contracts import CONTEXT_SCHEMA, POLICY, ContextStrategy, DerivedDependency, bounded_text, exact_id,implementation_hash,STRATEGY
from .service import definition
from . import storage, evidence


def dependency(db,did):
    exact_id(did,'reference-dependency')
    row=db.execute('SELECT * FROM ct_reference_dependencies WHERE dependency_id=?',(did,)).fetchone()
    if row is None:raise ContractError('derived dependency is not in this project')
    data=json.loads(row['payload_json'])
    if (identifier('reference-dependency',data)!=did or digest_bytes(row['body'])!=row['body_sha256']
            or row['body_sha256']!=data['body_sha256'] or row['version_id']!=data['reference_version_id']):
        raise ContractError('derived dependency integrity changed')
    return data,bytes(row['body']).decode('utf-8')


def register_dependency(project,*,version_id,contract,body,actor,created_at):
    if not isinstance(contract,DerivedDependency):raise ContractError('typed derived dependency contract required')
    contract.validate();timestamp(created_at);bounded_text(actor,'derived artifact registrar',200)
    if not isinstance(body,bytes) or len(body)>16000:raise ContractError('derived content must fit the declared 16-kB artifact bound')
    try:body.decode('utf-8')
    except UnicodeError as exc:raise ContractError('derived context must be UTF-8 text, never executable data') from exc
    safe_data({'actor':actor,'body':body.decode('utf-8')})
    with connection(project.database_path,write=True) as db:
        head,members=storage.stored(db,version_id)
        if any(aid not in members for aid in contract.source_assignment_ids):raise ContractError('derived artifact sources must belong to its exact reference version')
        value={'schema':'corpustrail-reference-dependency/v1','reference_version_id':version_id,
            'reference_manifest_sha256':head['manifest_sha256'],'contract':asdict(contract),'actor':actor,
            'created_at':created_at,'body_sha256':digest_bytes(body),'bytes':len(body),
            'authority':'non_authoritative','source_assignments_sha256':content_hash(sorted(contract.source_assignment_ids))}
        if len(canonical(value).encode())>1_000_000:raise ContractError('derived dependency metadata exceeds its resource bound')
        did=identifier('reference-dependency',value)
        if db.execute('SELECT 1 FROM ct_reference_dependencies WHERE dependency_id=?',(did,)).fetchone():dependency(db,did)
        else:db.execute('INSERT INTO ct_reference_dependencies VALUES (?,?,?,?,?)',(did,version_id,canonical(value),body,digest_bytes(body)))
        return {'dependency_id':did,'body_sha256':value['body_sha256'],'validation_state':'unvalidated','authority':'non_authoritative'}


def fields(request_id,version_id,actor,created_at,config_event_id,target_paper_id,target_basis,held_out_paper_ids,strategy,dependency_ids,held_out_population_version=None):
    command_id(request_id);timestamp(created_at);bounded_text(actor,'context preparation actor',200)
    safe_data({'actor':actor})
    if not isinstance(strategy,ContextStrategy):raise ContractError('typed context strategy required')
    strategy.validate();exact_id(target_paper_id,'ct-paper');exact_id(version_id,'reference-version')
    if held_out_population_version is not None:exact_id(held_out_population_version,'population-version')
    if target_basis not in {'metadata','abstract','structured_text'}:raise ContractError('choose the exact target evidence to include')
    if not isinstance(held_out_paper_ids,list) or not isinstance(dependency_ids,list):raise ContractError('explicit held-out/dependency lists required')
    for value in held_out_paper_ids:exact_id(value,'ct-paper')
    for value in dependency_ids:exact_id(value,'reference-dependency')
    if len(set(held_out_paper_ids))!=len(held_out_paper_ids) or len(set(dependency_ids))!=len(dependency_ids):raise ContractError('context source IDs cannot repeat')
    return {'request_id':request_id,'version_id':version_id,'actor':actor,'created_at':created_at,
        'config_event_id':config_event_id,'target_paper_id':target_paper_id,'target_basis':target_basis,
        'held_out_paper_ids':sorted(held_out_paper_ids),'strategy':strategy.to_dict(),'dependency_ids':sorted(dependency_ids),
        'held_out_population_version':held_out_population_version}


def build(project,db,raw,strategy):
    head,members=storage.stored(db,raw['version_id'])
    revision,config=latest_config(db)
    if revision!=raw['config_event_id'] or content_hash(definition(config))!=head['definition_sha256']:
        raise ContractError('context configuration/definition changed; prepare a new context explicitly')
    target=evidence.freeze(project,db,raw['target_paper_id'],[raw['target_basis']])
    target_entry=target['available'][raw['target_basis']]
    target_text=evidence.resolve(project,db,raw['target_paper_id'],target_entry)
    # Target text has its own explicit range/budget, never silent truncation.
    if len(target_text)>strategy.max_characters:raise ContractError('target evidence exceeds the context budget; choose a narrower basis')
    remaining=strategy.max_characters-len(target_text)
    held=set(raw['held_out_paper_ids'])
    if raw['held_out_population_version'] is not None:held.update(project.populations.review_ids(db,raw['held_out_population_version']))
    for pid in held:PopulationService._identity(db,pid)
    labels={}
    for data in members.values():labels.setdefault(data['paper_id'],set()).add(data['label'])
    items=[];selected=[];seen=set();counts={'in_scope':0,'out_of_scope':0};rank=0
    def eligible(data):
        if data['paper_id'] in held:return 'held_out'
        if data['paper_id']==raw['target_paper_id'] and strategy.self_match=='exclude':return 'self_match'
        if len(labels[data['paper_id']])>1:return 'conflicting_labels'
        if not data['human_attested'] or data['producer']['type']!='human':return 'unattested_source'
        if data['definition_sha256']!=head['definition_sha256']:return 'definition_mismatch'
        return None
    for aid,data in sorted(members.items(),key=lambda pair:(pair[1]['paper_id'],pair[1]['created_at'],pair[0])):
        pid=data['paper_id'];reason=eligible(data)
        record={'paper_id':pid,'assignment_id':aid,'decision':'omitted','reason':reason,'rank':None,'score':None}
        if reason is None:
            rank+=1;record['rank']=rank
            if pid in seen:reason='duplicate_canonical_reference'
            elif counts[data['label']]>=getattr(strategy,data['label']):reason='label_quota'
            elif remaining<=0:reason='character_budget'
            elif not data['evidence']['used']:reason='no_attested_evidence_text'
            else:
                # Existing exact identity service remains authoritative. Retired
                # canonical identities require explicit successor reassessment.
                PopulationService._identity(db,pid)
                basis=next(k for k in ('structured_text','abstract','metadata') if k in data['evidence']['used'])
                entry=data['evidence']['available'][basis]
                value=evidence.resolve(project,db,pid,entry)
                limit=min(strategy.max_per_reference,remaining)
                if len(value)>limit and not strategy.allow_truncation:reason='representation_exceeds_budget'
                else:
                    passage=value[:limit]
                    record.update(decision='selected',reason='canonical_identity_order',label=data['label'],
                        representation=entry,source_range={'unit':'Unicode codepoints','start':0,'end':len(passage)},
                        passage_sha256=digest_bytes(passage.encode()),truncated=len(passage)<len(value),
                        omitted_characters=max(0,len(value)-len(passage)))
                    selected.append({**record,'text':passage});counts[data['label']]+=1;remaining-=len(passage);seen.add(pid)
        if record['decision']=='omitted':record['reason']=reason
        items.append(record)
    derived=[]
    for did in raw['dependency_ids']:
        dep,body=dependency(db,did)
        if dep['reference_version_id']!=raw['version_id'] or dep['reference_manifest_sha256']!=head['manifest_sha256']:
            raise ContractError('derived dependency points to another reference version')
        if not strategy.include_unvalidated_derived:raise ContractError('unvalidated derived context requires explicit inclusion; it is not reference truth')
        for aid in dep['contract']['source_assignment_ids']:
            if aid not in members or eligible(members[aid]) is not None:
                raise ContractError('derived dependency contains held-out, self, conflicting or ineligible source labels')
        if len(body)>remaining:raise ContractError('derived artifact exceeds the remaining context budget; replan explicitly')
        remaining-=len(body)
        derived.append({'dependency_id':did,'producer':dep['contract']['producer'],
            'validation_state':dep['contract']['validation_state'],'authority':'non_authoritative',
            'source_assignments_sha256':dep['source_assignments_sha256'],'body_sha256':dep['body_sha256'],'text':body})
    payload={'schema':'corpustrail-exact-reference-context-input/v1','reference_version_id':raw['version_id'],
        'eligibility_policy':POLICY,'definition':head['definition'],
        'target':{'paper_id':raw['target_paper_id'],'representation':target_entry,'text':target_text},
        'references':selected,'derived':derived}
    body=canonical(payload).encode()
    if len(body)>1_000_000:raise ContractError('assembled context exceeds the explicit one-MB artifact bound')
    reasons={}
    for item in items:
        if item['decision']=='omitted':reasons[item['reason']]=reasons.get(item['reason'],0)+1
    header={'schema':CONTEXT_SCHEMA,'reference_version_id':raw['version_id'],'reference_manifest_sha256':head['manifest_sha256'],
        'producer':{'type':'deterministic','id':'corpustrail.references','version':STRATEGY},
        'software_version':__version__,'implementation_sha256':implementation_hash(),
        'evaluation_notice':'Selection policy provenance only; no assessment or independent scientific performance validation has been performed.',
        'eligibility_policy':POLICY,'strategy':strategy.to_dict(),'strategy_sha256':content_hash(strategy.to_dict()),
        'definition_sha256':head['definition_sha256'],'config_event_id':revision,'actor':raw['actor'],'created_at':raw['created_at'],
        'request_id':raw['request_id'],'request_sha256':content_hash(raw),'target_evidence':target,
        'held_out_paper_ids':sorted(held),'held_out_population_version':raw['held_out_population_version'],'dependency_ids':raw['dependency_ids'],
        'independent_evaluation':strategy.self_match=='exclude' and not derived,'selected_counts':counts,'selected_count':len(selected),
        'decision_count':len(items),'omission_counts':reasons,'decisions_sha256':content_hash(items),
        'decision_chunk_hashes':[content_hash(items[i:i+100]) for i in range(0,len(items),100)],
        'input_sha256':digest_bytes(body),'input_bytes':len(body),'text_characters':strategy.max_characters-remaining}
    return header,items,body


def prepare(project,*,request_id,version_id,actor,created_at,config_event_id,target_paper_id,target_basis,held_out_paper_ids,strategy,dependency_ids,held_out_population_version=None):
    raw=fields(request_id,version_id,actor,created_at,config_event_id,target_paper_id,target_basis,held_out_paper_ids,strategy,dependency_ids,held_out_population_version)
    with connection(project.database_path) as db:
        header,items,body=build(project,db,raw,strategy)
        return {**header,'input':json.loads(body),'preview_sha256':content_hash(header)}


def commit(project,*,expected_preview_sha256,request_id,version_id,actor,created_at,config_event_id,target_paper_id,target_basis,held_out_paper_ids,strategy,dependency_ids,held_out_population_version=None):
    raw=fields(request_id,version_id,actor,created_at,config_event_id,target_paper_id,target_basis,held_out_paper_ids,strategy,dependency_ids,held_out_population_version)
    with connection(project.database_path,write=True) as db:
        storage.require(db)
        prior=db.execute('SELECT context_id,request_sha256 FROM ct_reference_contexts WHERE request_id=?',(request_id,)).fetchone()
        if prior:
            if prior['request_sha256']!=content_hash(raw):raise ContractError('completed context command cannot be reused with different inputs')
            header,body=checked(db,prior['context_id'])
            if content_hash(header)!=expected_preview_sha256:raise ContractError('completed context preview differs')
            return {'context_id':prior['context_id'],**header,'replayed':True}
        header,items,body=build(project,db,raw,strategy)
        if content_hash(header)!=expected_preview_sha256:raise ContractError('context preview changed; prepare and inspect again')
        cid=identifier('reference-context',header)
        db.execute('INSERT INTO ct_reference_contexts(context_id,version_id,request_id,request_sha256,payload_json,input_bytes,input_sha256) VALUES (?,?,?,?,?,?,?)',
            (cid,version_id,request_id,content_hash(raw),canonical(header),body,header['input_sha256']))
        db.executemany('INSERT INTO ct_reference_context_items VALUES (?,?,?,?,?,?,?)',
            ((cid,i,item['paper_id'],item['assignment_id'],item['decision'],canonical(item),content_hash(item)) for i,item in enumerate(items)))
        return {'context_id':cid,**header,'replayed':False}


def checked(db,cid):
    storage.require(db);exact_id(cid,'reference-context')
    row=db.execute('SELECT * FROM ct_reference_contexts WHERE context_id=?',(cid,)).fetchone()
    if row is None:raise ContractError('selected context is not in this project')
    header=json.loads(row['payload_json']);body=bytes(row['input_bytes'])
    if (identifier('reference-context',header)!=cid or row['version_id']!=header['reference_version_id']
            or row['request_id']!=header['request_id'] or row['request_sha256']!=header['request_sha256']
            or digest_bytes(body)!=row['input_sha256'] or row['input_sha256']!=header['input_sha256']):
        raise ContractError('frozen selected-context integrity changed')
    return header,body


def verify_in_connection(db,cid):
    """Reuse frozen integrity checks within an existing read/write snapshot.

    Opening a second reader from a writer can deadlock after SQLite cache spill.
    This helper does not open a connection or change scientific context semantics.
    """
    header,body=checked(db,cid)
    decisions=[json.loads(r[0]) for r in db.execute('SELECT payload_json FROM ct_reference_context_items WHERE context_id=? ORDER BY position',(cid,))]
    if content_hash(decisions)!=header['decisions_sha256'] or len(decisions)!=header['decision_count']:
        raise ContractError('context decision manifest changed')
    storage.stored(db,header['reference_version_id'])
    for did in header['dependency_ids']:dependency(db,did)
    return header,body


def inspect(project,cid,*,offset=0,limit=20,verify=False):
    page(offset,limit)
    with connection(project.database_path) as db:
        header,body=checked(db,cid);items=[]
        for number in range(offset//100,(min(offset+limit,header['decision_count'])+99)//100):
            chunk=[json.loads(r[0]) for r in db.execute('SELECT payload_json FROM ct_reference_context_items WHERE context_id=? AND position>=? AND position<? ORDER BY position',(cid,number*100,(number+1)*100))]
            if content_hash(chunk)!=header['decision_chunk_hashes'][number]:raise ContractError('context decision chunk integrity changed')
        text_by_id={r['assignment_id']:r['text'] for r in json.loads(body)['references']}
        rows=db.execute('SELECT * FROM ct_reference_context_items WHERE context_id=? ORDER BY position LIMIT ? OFFSET ?',(cid,limit,offset))
        for row in rows:
            value=json.loads(row['payload_json'])
            if content_hash(value)!=row['content_sha256'] or any(value[k]!=row[k] for k in ('paper_id','assignment_id','decision')):
                raise ContractError('selected-context decision integrity changed')
            if value['decision']=='selected':
                text=text_by_id[value['assignment_id']]
                if digest_bytes(text.encode())!=value['passage_sha256']:raise ContractError('frozen passage integrity changed')
                value={**value,'text':text}
            items.append(value)
        if verify:
            verify_in_connection(db,cid)
        return {'context_id':cid,**header,'input':json.loads(body),'items':items,'verified':bool(verify),
            'next_offset':offset+limit if offset+limit<header['decision_count'] else None}


def listing(project,*,offset=0,limit=20,cutoff=None):
    page(offset,limit)
    with connection(project.database_path) as db:
        if not storage.ready(db):return {'available':False,'items':[],'next_offset':None}
        maximum=db.execute('SELECT COALESCE(MAX(sequence),0) FROM ct_reference_contexts').fetchone()[0]
        if cutoff is None:cutoff=maximum
        if type(cutoff) is not int or not 0<=cutoff<=maximum:raise ContractError('invalid context list cutoff')
        total=db.execute('SELECT COUNT(*) FROM ct_reference_contexts WHERE sequence<=?',(cutoff,)).fetchone()[0]
        if offset>total:raise ContractError('context page is beyond this saved list')
        rows=db.execute('SELECT context_id FROM ct_reference_contexts WHERE sequence<=? ORDER BY sequence DESC LIMIT ? OFFSET ?',(cutoff,limit+1,offset)).fetchall()
        return {'available':True,'total':total,'items':[{'context_id':r[0],**checked(db,r[0])[0]} for r in rows[:limit]],
            'cutoff':cutoff,'next_offset':offset+limit if len(rows)>limit else None}
