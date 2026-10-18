"""Explicit reference batches; never writes review or corpus-membership tables."""
import json

from corpustrail import __version__
from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.pipeline import artifact_in_connection
from corpustrail._internal.values import ContractError, canonical, content_hash, identifier, timestamp
from corpustrail.curation.service import _history, _PRODUCER_TYPES
from corpustrail.populations.contracts import command_id, page
from corpustrail.models.contracts import safe_data
from .contracts import SCHEMA, POLICY, LABELS, bounded_text, exact_id,implementation_hash
from . import storage, evidence


def definition(config):
    return {'scope':config['review']['scope'] or config['description'],'policy_id':config['review']['policy_id']}


class ReferenceService:
    def __init__(self,project):self.project=project

    def ready(self):
        with connection(self.project.database_path) as db:return storage.ready(db)

    def _prepare(self,db,*,request_id,name,actor,parent,changes,config_event_id,created_at):
        storage.require(db);command_id(request_id);timestamp(created_at)
        bounded_text(name,'reference collection name',200);bounded_text(actor,'explicit reference actor',200)
        revision,config=latest_config(db)
        if revision!=config_event_id:raise ContractError('configuration changed; preview this reference batch again')
        scope=definition(config);scope_sha=content_hash(scope)
        if not isinstance(changes,list) or not 1<=len(changes)<=500:
            raise ContractError('choose 1–500 changes per batch; the collection itself has no item cap')
        safe_data({'name':name,'actor':actor,'changes':changes})
        members={};prior=None
        if parent is not None:
            prior,members=storage.stored(db,parent)
            head=db.execute('SELECT version_id FROM ct_reference_versions WHERE collection_id=? ORDER BY version DESC LIMIT 1',(prior['collection_id'],)).fetchone()[0]
            if head!=parent:raise ContractError('reference collection changed; inspect its latest version before editing')
            if scope_sha!=prior['definition_sha256']:raise ContractError('corpus definition changed; create explicitly reassessed references, not a silent reinterpretation')
        new={};operations=[]
        for position,change in enumerate(changes):
            if not isinstance(change,dict):raise ContractError('reference change must be a structured operation')
            if change.get('action')=='remove':
                if set(change)!={'action','assignment_id','reason'}:raise ContractError('unsupported reference removal fields')
                aid=change['assignment_id'];bounded_text(change['reason'],'removal reason')
                if aid not in members:raise ContractError('removed assignment is not active in this version')
                del members[aid];operations.append(change);continue
            fields={'action','paper_id','label','producer','human_attested','rationale','evidence_used','supersedes','source_assignment_ids','source_event_id','source_artifact_sha256','source_record'}
            if set(change)!=fields or change['action']!='assign':raise ContractError('unsupported reference-assignment fields')
            pid=exact_id(change['paper_id'],'ct-paper')
            if not isinstance(change['label'],str) or change['label'] not in LABELS:raise ContractError('choose Known in-scope or Known out-of-scope')
            bounded_text(change['rationale'],'reference rationale',empty=True)
            producer=change['producer']
            if not isinstance(producer,dict) or set(producer)!={'type','id','version'} or producer['type'] not in _PRODUCER_TYPES:
                raise ContractError('explicit existing producer type, identity and version required')
            for key,value in producer.items():bounded_text(value,'producer '+key,200)
            if type(change['human_attested']) is not bool:raise ContractError('explicit human-attestation choice required')
            if change['human_attested'] and (producer['type']!='human' or producer['id']!=actor):
                raise ContractError('a nonhuman producer or another identity cannot claim this actor’s human attestation')
            for key in ('supersedes','source_assignment_ids'):
                if not isinstance(change[key],list) or any(not isinstance(a,str) for a in change[key]) or len(change[key])!=len(set(change[key])) or len(change[key])>500:
                    raise ContractError('exact unique bounded assignment lineage required')
                for aid in change[key]:
                    old=storage.assignment(db,aid) if aid not in new else new[aid]
                    if old['paper_id']!=pid:raise ContractError('reference correction/source must identify the same canonical publication')
                    if key=='supersedes' and aid not in members:raise ContractError('correction does not name an active assignment')
            if producer['type']!='human' and change['supersedes']:
                raise ContractError('machine/import proposals cannot retire earlier reference assignments')
            source_event=None
            if change['source_event_id'] is not None:
                matches=[e for e in _history(db,pid) if e['event_id']==change['source_event_id']]
                expected='included' if change['label']=='in_scope' else 'excluded'
                if not matches or matches[0]['state']!=expected or matches[0]['policy_id']!=scope['policy_id']:
                    raise ContractError('source review event must be an exact same-paper matching judgment under this policy')
                source_event={'event_id':matches[0]['event_id'],'sha256':content_hash(matches[0])}
            source_artifact=change['source_artifact_sha256']
            if source_artifact is not None:artifact_in_connection(self.project,db,source_artifact)
            if change['source_record'] is not None:bounded_text(change['source_record'],'source record locator',500)
            if producer['type']!='human' and source_artifact is None and source_event is None:
                raise ContractError('nonhuman/import reference proposals require preserved source provenance')
            snapshot=evidence.freeze(self.project,db,pid,change['evidence_used'])
            payload={'schema':'corpustrail-reference-assignment/v1','project_id':config['project_id'],
                'paper_id':pid,'label':change['label'],'producer':producer,'human_attested':change['human_attested'],
                'actor':actor,'created_at':created_at,'request_id':request_id,'batch_position':position,
                'rationale':change['rationale'],'evidence':snapshot,'evidence_sha256':content_hash(snapshot),
                'definition':scope,'definition_sha256':scope_sha,'config_event_id':revision,
                'supersedes':sorted(change['supersedes']),'source_assignment_ids':sorted(change['source_assignment_ids']),
                'source_event':source_event,'source_artifact_sha256':source_artifact,'source_record':change['source_record'],
                'availability':'recorded','validation_state':'human_attested' if change['human_attested'] else 'unattested_proposal'}
            aid=identifier('reference-assignment',payload)
            for old in change['supersedes']:del members[old]
            members[aid]=payload;new[aid]=payload
            operations.append({'action':'assign','assignment_id':aid,'supersedes':payload['supersedes']})
        parts=storage.chunks(members);refs=[{k:v for k,v in p.items() if k!='ids'} for p in parts]
        fields={'request_id':request_id,'name':name,'actor':actor,'parent':parent,'changes':changes,
            'config_event_id':config_event_id,'created_at':created_at}
        data={'schema':SCHEMA,'policy':POLICY,'project_id':config['project_id'],'name':name,'actor':actor,
            'created_at':created_at,'software_version':__version__,'definition':scope,'definition_sha256':scope_sha,
            'implementation_sha256':implementation_hash(),
            'config_event_id':revision,'request_id':request_id,'request_sha256':content_hash(fields),
            'collection_id':prior['collection_id'] if prior else identifier('reference-collection',{'project':config['project_id'],'request':request_id}),
            'version':prior['version']+1 if prior else 1,'parent_id':parent,'chunks':refs,
            'manifest_sha256':content_hash(refs),'changes_sha256':content_hash(operations),
            'change_hashes':[content_hash(c) for c in operations],'counts':storage.summary(members)}
        return data,new,operations,parts,fields

    @staticmethod
    def public(data):
        return {k:v for k,v in data.items() if k not in {'chunks','request_sha256','change_hashes'}}

    def preview(self,**fields):
        with connection(self.project.database_path) as db:
            data,new,operations,parts,_=self._prepare(db,**fields)
            return {**self.public(data),'preview_sha256':content_hash(data),
                'new_assignments':[{'assignment_id':aid,**{k:value[k] for k in ('paper_id','label','human_attested','validation_state')}} for aid,value in list(new.items())[:20]],
                'change_count':len(operations),'preview_display_limit':20}

    def commit(self,*,expected_preview_sha256,**fields):
        command_id(fields['request_id'])
        with connection(self.project.database_path,write=True) as db:
            storage.require(db)
            prior=db.execute('SELECT version_id,request_sha256 FROM ct_reference_versions WHERE request_id=?',(fields['request_id'],)).fetchone()
            if prior:
                if prior['request_sha256']!=content_hash(fields):raise ContractError('completed reference command cannot be reused with different content')
                data=storage.header(db,prior['version_id'])
                if content_hash(data)!=expected_preview_sha256:raise ContractError('completed reference preview differs')
                return {'version_id':prior['version_id'],**self.public(data),'replayed':True}
            data,new,operations,parts,_=self._prepare(db,**fields)
            if content_hash(data)!=expected_preview_sha256:raise ContractError('reference preview is stale; inspect and preview again')
            vid=identifier('reference-version',data)
            storage.insert_version(db,vid,data,new,operations,parts)
            return {'version_id':vid,**self.public(data),'replayed':False}

    def versions(self,*,offset=0,limit=20,cutoff=None):
        page(offset,limit)
        with connection(self.project.database_path) as db:
            if not storage.ready(db):return {'available':False,'items':[],'total':0,'next_offset':None}
            maximum=db.execute('SELECT COALESCE(MAX(sequence),0) FROM ct_reference_versions').fetchone()[0]
            if cutoff is None:cutoff=maximum
            if type(cutoff) is not int or not 0<=cutoff<=maximum:raise ContractError('invalid reference list cutoff')
            total=db.execute('SELECT COUNT(*) FROM ct_reference_versions WHERE sequence<=?',(cutoff,)).fetchone()[0]
            if offset>total:raise ContractError('reference page is beyond this saved list')
            rows=db.execute('SELECT version_id FROM ct_reference_versions WHERE sequence<=? ORDER BY sequence DESC LIMIT ? OFFSET ?',(cutoff,limit,offset))
            return {'available':True,'items':[{'version_id':r[0],**self.public(storage.header(db,r[0]))} for r in rows],
                'total':total,'cutoff':cutoff,'next_offset':offset+limit if offset+limit<total else None}

    def inspect(self,vid):
        with connection(self.project.database_path) as db:return {'version_id':vid,**self.public(storage.header(db,vid))}

    def verify(self,vid):
        with connection(self.project.database_path) as db:
            data,members=storage.stored(db,vid)
            return {'version_id':vid,'verified':True,'manifest_sha256':data['manifest_sha256'],'counts':data['counts']}

    def members(self,vid,*,offset=0,limit=20,label=None):
        page(offset,limit)
        if label is not None and label not in LABELS:raise ContractError('choose an existing reference label filter')
        with connection(self.project.database_path) as db:
            head=storage.header(db,vid)
            query=' FROM ct_reference_version_chunks v JOIN ct_reference_chunk_items i ON i.chunk_id=v.chunk_id JOIN ct_reference_assignments a ON a.assignment_id=i.assignment_id WHERE v.version_id=?'
            params=[vid]
            if label is not None:query+=' AND a.label=?';params.append(label)
            rows=db.execute('SELECT i.chunk_id,i.assignment_id'+query+' ORDER BY v.bucket,v.ordinal,i.position LIMIT ? OFFSET ?',(*params,limit,offset)).fetchall()
            checked=set();items=[]
            for row in rows:
                if row['chunk_id'] not in checked:storage.checked_chunk(db,row['chunk_id']);checked.add(row['chunk_id'])
                data=storage.assignment(db,row['assignment_id'])
                # Per-page indexed lookup, not an entire collection in the DTO.
                labels={r[0] for r in db.execute('SELECT DISTINCT a.label FROM ct_reference_version_chunks v JOIN ct_reference_chunk_items i ON i.chunk_id=v.chunk_id JOIN ct_reference_assignments a ON a.assignment_id=i.assignment_id WHERE v.version_id=? AND a.paper_id=?',(vid,data['paper_id']))}
                items.append({'assignment_id':row['assignment_id'],'paper_id':data['paper_id'],'label':data['label'],
                    'actor':data['actor'],'producer':data['producer'],'human_attested':data['human_attested'],
                    'rationale':data['rationale'],'created_at':data['created_at'],'evidence_used':data['evidence']['used'],
                    'bibliography':data['evidence']['available']['metadata']['bibliography'],
                    'conflicting':len(labels)>1,'eligible':len(labels)==1 and data['human_attested'] and data['producer']['type']=='human'})
            total=head['counts']['assignment_count'] if label is None else db.execute('SELECT COUNT(*)'+query,params).fetchone()[0]
            return {'version_id':vid,'items':items,'total':total,'next_offset':offset+limit if offset+limit<total else None,
                'ordering':'sha256-paper-bucket/ascending-paper-and-assignment/v1'}

    def provenance(self,vid,*,offset=0,limit=20):
        page(offset,limit)
        with connection(self.project.database_path) as db:
            head=storage.header(db,vid)
            rows=db.execute('SELECT * FROM ct_reference_changes WHERE version_id=? ORDER BY position LIMIT ? OFFSET ?',(vid,limit+1,offset)).fetchall()
            items=[]
            for r in rows[:limit]:
                value=json.loads(r['payload_json'])
                if content_hash(value)!=r['content_sha256'] or r['content_sha256']!=head['change_hashes'][r['position']]:raise ContractError('reference correction integrity changed')
                items.append({**value,**({'assignment':storage.assignment(db,value['assignment_id'])} if value['action']=='assign' else {})})
            return {'items':items,'next_offset':offset+limit if len(rows)>limit else None}

    def assignment(self,vid,aid):
        """Explicit single-assignment provenance, including inherited members."""
        with connection(self.project.database_path) as db:
            storage.header(db,vid);exact_id(aid,'reference-assignment')
            row=db.execute('SELECT i.chunk_id FROM ct_reference_version_chunks v JOIN ct_reference_chunk_items i ON i.chunk_id=v.chunk_id WHERE v.version_id=? AND i.assignment_id=?',(vid,aid)).fetchone()
            if row is None:raise ContractError('assignment is not active in this exact reference version')
            storage.checked_chunk(db,row['chunk_id'])
            value=storage.assignment(db,aid)
            origin=db.execute('SELECT version_id FROM ct_reference_versions WHERE request_id=?',(value['request_id'],)).fetchone()
            if origin is None:raise ContractError('assignment origin version is unavailable')
            return {'version_id':vid,'assignment_id':aid,'assignment':value,
                'origin_version':{'version_id':origin[0],**self.public(storage.header(db,origin[0]))}}

    def prepare_context(self,**fields):
        from .context import prepare
        return prepare(self.project,**fields)

    def commit_context(self,**fields):
        from .context import commit
        return commit(self.project,**fields)

    def context(self,cid,**paging):
        from .context import inspect
        return inspect(self.project,cid,**paging)

    def contexts(self,**paging):
        from .context import listing
        return listing(self.project,**paging)

    def register_dependency(self,**fields):
        from .context import register_dependency
        return register_dependency(self.project,**fields)
