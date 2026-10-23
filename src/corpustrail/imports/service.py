"""Durable RIS operations composed from existing identity/population services.

No new scientific database or migration. Original bytes, prepared selections and
append-only chunk receipts are researcher-owned project material. Restart is a
read; continuing interrupted work requires another explicit confirmation.
"""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import sqlite3

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.pipeline import preserve, artifact
from corpustrail._internal.values import ContractError, content_hash, now
from corpustrail.application import _workflow_files as files
from corpustrail.application.project_use import no_links
from corpustrail.curation.service import membership_in_connection
from corpustrail.identity import SourceReference
from corpustrail.identity.service import _identity_snapshot
from corpustrail.populations import ImportedSource
from corpustrail.populations.contracts import command_id, page
from .ris import PROFILE, MEDIA, MAX_BYTES, parse, bibliography, serialize, implementation_hash

SCHEMA = 'corpustrail-ris-exchange/v1'
CHUNK = 20


class RISService:
    def __init__(self, project, *, clock=None): self.project=project;self.clock=clock or now

    @property
    def root(self):return no_links(files.location(self.project,family='handoff')/'ris',missing=True)

    def path(self, kind, key):
        command_id(key)
        if kind not in {'prepared','chunks','complete','exports','uploads'}:raise ContractError('unknown RIS record kind')
        return no_links(self.root/kind/(key+'.json'),missing=True)

    def state(self, db):return content_hash([latest_config(db)[0],_identity_snapshot(db)])

    def source(self, prepared, row):
        return SourceReference('ris://sha256/'+prepared['source_sha256'][7:], 'record:'+str(row['index']),
            prepared['source_sha256'], prepared['bytes'], 'ris/'+PROFILE+'/'+prepared['parser_sha256'][:12], prepared['created_at'],
            producer_type='imported',media_type=MEDIA,identity_status='verified')

    def _rows(self, prepared):
        self.source_bytes(prepared['id'])
        return [files.read(no_links(self.root/'parsed'/prepared['id']/(f'{i:08d}.json'))) for i in range(1,prepared['records']+1)]

    def source_bytes(self,key):
        prepared=files.read(self.path('prepared',key))
        if prepared['project_id']!=self.project.config.project_id:raise ContractError('Foreign RIS source.')
        path=no_links(self.project.root/prepared['source_path']);body=path.read_bytes()
        if len(body)!=prepared['bytes'] or len(body)>MAX_BYTES or 'sha256:'+hashlib.sha256(body).hexdigest()!=prepared['source_sha256']:
            raise ContractError('Selected RIS source changed; preserved input integrity failed.')
        return body

    def _apply(self, db, prepared, row):
        if row['error']:return {'index':row['index'],'status':'parse_error','error':row['error']}
        try:
            plan=self.project.identities._plan(db,bibliography(row['record']),self.source(prepared,row))
            known=db.execute('SELECT identity_state FROM paper_entities WHERE paper_id=?',(plan.paper_id,)).fetchone()
            if known is not None and known[0]!='active':raise ContractError('Existing exact identity is inactive; explicit identity resolution is required.')
            self.project.identities._apply(db,plan,approve_new_identity=True,approve_aliases=True)
            observation=db.execute('SELECT observation_id FROM ct_paper_observations WHERE plan_id=?',(plan.plan_id,)).fetchone()[0]
            return {'index':row['index'],'status':'linked' if known else 'new',
                    'paper_id':plan.paper_id,'observation_id':observation,'plan_id':plan.plan_id}
        except ContractError as error:
            return {'index':row['index'],'status':'identity_issue','error':str(error)}

    def prepare_import(self, *, request_id, upload, actor, name):
        command_id(request_id);command_id(upload)
        if not isinstance(actor,str) or not actor.strip() or len(actor)>200:raise ContractError('Enter the import actor.')
        if not isinstance(name,str) or not name.strip() or len(name)>200:raise ContractError('Name this imported collection.')
        with closing(files.operation_lease(self.project,'ris-prepare')):
            path=self.path('prepared',request_id)
            if path.exists():
                old=files.read(path)
                if (old['upload'],old['actor'],old['name'])!=(upload,actor,name):raise ContractError('Import request belongs to different inputs.')
                return self.inspect(request_id)
            source=files.read(self.path('uploads',upload));at=self.clock()
            body=no_links(self.project.root/source['path']).read_bytes()
            if 'sha256:'+hashlib.sha256(body).hexdigest()!=source['sha256']:raise ContractError('Changed uploaded source.')
            try:rows=parse(body)
            except ContractError as error:
                rows=[{'index':1,'line_start':1,'line_end':None,'fields':{},'record':None,'warnings':[],
                       'file_error':True,'error':str(error)+' Source record count unknown; original bytes retained.'}]
            with connection(self.project.database_path) as db:
                if not self.project.populations.ready():raise ContractError('Explicit backed-up population upgrade is required before RIS import.')
                state=self.state(db);revision=latest_config(db)[0]
                shadow=sqlite3.connect(':memory:');shadow.row_factory=sqlite3.Row
                try:
                    db.backup(shadow)
                    record={'schema':SCHEMA,'kind':'import','id':request_id,'upload':upload,'actor':actor,'name':name,
                        'project_id':self.project.config.project_id,'created_at':at,'state':state,'config_event_id':revision,
                        'source_path':source['path'],'source_sha256':source['sha256'],'bytes':len(body),'filename':source['filename'],
                        'profile':PROFILE,'parser_sha256':implementation_hash()}
                    results=[self._apply(shadow,record,row) for row in rows]
                finally:shadow.close()
            counts={key:sum(v['status']==key for v in results) for key in ('new','linked','parse_error','identity_issue')}
            record.update(records=len(rows),record_count_known=not any(r.get('file_error') for r in rows),counts=counts,proposed_unique_papers=len({v['paper_id'] for v in results if 'paper_id' in v}),
                          proposed_results_sha256=content_hash(results),partial_source=any(v['status'] in {'parse_error','identity_issue'} for v in results))
            for row in rows:
                saved={**row,'fields':{k:v for k,v in row['fields'].items() if k in {'TY','ID','VL','IS','SP','EP','SN','LA','KW','N1','UR'}}}
                files.publish(no_links(self.root/'parsed'/request_id/(f"{row['index']:08d}.json"),missing=True),saved)
            files.publish(no_links(self.root/'proposed'/(request_id+'.json'),missing=True),{'results':results})
            files.publish(path,record)
            return self.inspect(request_id)

    def inspect(self, key, *, offset=0, limit=20):
        page(offset,limit);p=files.read(self.path('prepared',key));rows=self._rows(p)
        chunks=self.chunks(key);results={r['index']:r for c in chunks for r in c['results']}
        final=self.path('complete',key);done=files.read(final) if final.exists() else None
        proposed={r['index']:r for r in files.read(no_links(self.root/'proposed'/(key+'.json')))['results']}
        items=[]
        for row in rows[offset:offset+limit]:
            value=row['record'] or {};saved=results.get(row['index']);result=saved or proposed.get(row['index'])
            items.append({'index':row['index'],'title':value.get('title'),'abstract':(value.get('abstract') or '')[:1200],
                'abstract_characters':len(value.get('abstract') or ''),'authors':value.get('authors',[])[:20],
                'year':value.get('year'),'journal':value.get('source'),'warnings':row['warnings'],
                'status':result['status'] if saved or result['status'] in {'parse_error','identity_issue'} else 'proposed_'+result['status'],
                'error':result.get('error') if result else row['error'],'paper_handle':result['paper_id'].split(':')[1] if saved and 'paper_id' in result else None})
        return {'schema':SCHEMA,'id':key,'kind':'import','name':p['name'],'actor':p['actor'],'filename':p['filename'],
            'records':p['records'],'record_count_known':p['record_count_known'],'counts':p['counts'],'proposed_unique_papers':p['proposed_unique_papers'],
            'partial_source':p['partial_source'],'processed':len(results),'status':'complete' if done else 'partial' if chunks else 'prepared',
            'preview_sha256':content_hash(p),'source_sha256':p['source_sha256'],'profile':p['profile'],
            'items':items,'next_offset':offset+limit if offset+limit<len(rows) else None,'result':done}

    def chunks(self,key):
        command_id(key);directory=no_links(self.root/'chunks'/key,missing=True)
        results=[]
        if directory.exists():
            for p in sorted(directory.glob('*.json')):
                value=files.read(p)
                if value['offset']!=sum(len(v['results']) for v in results):raise ContractError('RIS chunk history changed or is incomplete.')
                results.append(value)
        return results

    def commit_import(self, *, key, preview_sha256, confirmed, accept_partial=False):
        if confirmed is not True:raise ContractError('Confirm bibliographic enrollment and exact source-identifier approval explicitly.')
        with closing(files.operation_lease(self.project,'ris-execution')):
            p=files.read(self.path('prepared',key))
            if content_hash(p)!=preview_sha256 or p['project_id']!=self.project.config.project_id:raise ContractError('Changed or foreign RIS preview.')
            if p['partial_source'] and accept_partial is not True:raise ContractError('Explicitly accept the partial source; failed records remain preserved and unresolved.')
            if self.path('complete',key).exists():return self.inspect(key)
            if p['profile']!=PROFILE or p['parser_sha256']!=implementation_hash():
                raise ContractError('RIS parser changed; inspect preserved results and prepare a fresh preview before further enrollment.')
            chunks=self.chunks(key);offset=sum(len(v['results']) for v in chunks)
            expected=chunks[-1]['next_state'] if chunks else p['state'];rows=self._rows(p)
            # Source preservation is independent of a later record failure.
            body=no_links(self.project.root/p['source_path']).read_bytes()
            preserve(self.project,body,MEDIA,p['created_at'])
            reservation=no_links(self.root/'reservations'/key/(f'{offset:08d}.json'),missing=True)
            with connection(self.project.database_path,write=True) as db:
                current=self.state(db)
                if current!=expected:
                    saved=files.read(reservation) if reservation.exists() else None
                    if saved is None or saved['next_state']!=current or saved['prepared_sha256']!=preview_sha256:
                        raise ContractError('Identity or configuration changed since the last confirmed chunk; inspect preserved work and prepare a fresh import.')
                    output=[self._apply(db,p,row) for row in rows[offset:offset+CHUNK]]
                    comparable=[{k:v for k,v in row.items() if k!='status'} for row in output]
                    recorded=[{k:v for k,v in row.items() if k!='status'} for row in saved['results']]
                    if comparable!=recorded or self.state(db)!=current:
                        raise ContractError('Interrupted chunk does not match exact saved enrollment receipts.')
                    receipt=saved;output=saved['results']
                else:
                    output=[self._apply(db,p,row) for row in rows[offset:offset+CHUNK]]
                    receipt={'offset':offset,'results':output,'next_state':self.state(db),'prepared_sha256':preview_sha256}
                    # Durable reservation precedes transaction commit. Exact native
                    # replay can reconcile a committed chunk missing its file receipt.
                    files.publish(reservation,receipt)
            files.publish(no_links(self.root/'chunks'/key/(f'{offset:08d}.json'),missing=True),receipt)
            if offset+len(output)==len(rows):
                all_results=[r for c in self.chunks(key) for r in c['results']]
                observations=tuple(sorted({r['observation_id'] for r in all_results if 'observation_id' in r}))
                population=None
                if observations:
                    source=ImportedSource('ris-'+key,'ris',PROFILE,p['source_sha256'],observations)
                    selection={'request_id':key,'name':p['name']+(' — partial source' if p['partial_source'] else ''),'actor':p['actor'],'sources':[{'kind':'import_interface'}]}
                    preview=self.project.populations.preview(imported=source,**selection)
                    population=self.project.populations.create(imported=source,expected_preview_sha256=preview['preview_sha256'],created_at=p['created_at'],**selection)
                final={'source_sha256':p['source_sha256'],'partial_source':any(r['status'] in {'parse_error','identity_issue'} for r in all_results),
                    'counts':{s:sum(r['status']==s for r in all_results) for s in ('new','linked','parse_error','identity_issue')},
                    'unique_canonical_publications':len({r['paper_id'] for r in all_results if 'paper_id' in r}),
                    'population':population,'completed_at':self.clock(),'authority_effect':'none','original_source_preserved':True}
                files.publish(self.path('complete',key),final)
            return self.inspect(key)

    def export_preview(self, *, scope, actor, version_id=None):
        if scope not in {'confirmed','all_candidates','population'}:raise ContractError('Choose an explicit RIS export scope.')
        if not isinstance(actor,str) or not actor.strip() or len(actor)>200:raise ContractError('Enter the export actor.')
        if scope=='population':
            self.project.populations.verify(version_id)
            with connection(self.project.database_path) as db:
                ids=[r[0] for r in db.execute('SELECT paper_id FROM ct_population_members WHERE version_id=? ORDER BY paper_id',(version_id,))]
        else:ids=self.project.identities.papers()
        records=[];lineage=[];source_cache={}
        with connection(self.project.database_path) as db:
            for pid in ids:
                entity=db.execute('SELECT identity_state FROM paper_entities WHERE paper_id=?',(pid,)).fetchone()
                if entity is None or entity[0]!='active':raise ContractError('Selected identity is no longer active; resolve it explicitly before export.')
                state=membership_in_connection(db,pid)
                if scope=='confirmed' and state['state']!='included':continue
                metadata=self.project.discovery._metadata(db,pid);value=metadata['fields']
                supplemental={};publication_type='GEN';supplemental_sources=[]
                observations=sorted(self.project.identities._observations(db,pid),key=lambda r:(r['source']['observed_at'],r['observation_id']))
                for observation in observations:
                    source=observation['source']
                    if not source['source_uri'].startswith('ris://sha256/') or not source['record_locator'].startswith('record:'):continue
                    digest=source['source_sha256']
                    if digest not in source_cache:source_cache[digest]=parse(artifact(self.project,digest).read_bytes())
                    raw=source_cache[digest][int(source['record_locator'][7:])-1]['fields']
                    if publication_type=='GEN' and raw.get('TY'):publication_type=raw['TY'][0]
                    for tag in ('ID','VL','IS','SP','EP','SN','LA','KW','N1','UR'):
                        if tag not in supplemental and raw.get(tag):
                            supplemental[tag]=raw[tag];supplemental_sources.append({'tag':tag,'observation_id':observation['observation_id'],'source_sha256':digest})
                records.append({**value,'identifiers':metadata['identifiers'],'publication_type':publication_type,'supplemental':supplemental})
                lineage.append({'paper_id':pid,'field_provenance':metadata['field_provenance'],'record_sha256':content_hash(records[-1]),'membership_head':state['current_event_id'],
                                'membership_state':state['state'],'supplemental_sources':supplemental_sources})
            config=latest_config(db)[0]
        if not records:raise ContractError('The explicitly selected export set is empty; no file created.')
        if len(records)>2000:raise ContractError('RIS export exceeds the documented 2,000-record operation budget; choose a smaller population.')
        body=serialize(records)
        result={'schema':SCHEMA,'kind':'export','profile':PROFILE,'scope':scope,'actor':actor,
            'project_id':self.project.config.project_id,'config_event_id':config,'version_id':version_id,'parser_sha256':implementation_hash(),
            'records':records,'lineage':lineage,'bytes':len(body),'sha256':'sha256:'+hashlib.sha256(body).hexdigest(),
            'label_policy':'none','record_count':len(records),'abstracts':sum(bool(r['abstract']) for r in records)}
        result['preview_sha256']=content_hash(result)
        return result

    def export_commit(self, *, key, scope, actor, version_id, preview_sha256, confirmed):
        command_id(key)
        if confirmed is not True:raise ContractError('Confirm the selected bibliographic export explicitly.')
        with closing(files.operation_lease(self.project,'ris-execution')):
            path=self.path('exports',key)
            if path.exists():
                result=files.read(path)
                if result['preview_sha256']!=preview_sha256 or (result['scope'],result['actor'],result['version_id'])!=(scope,actor,version_id):raise ContractError('Export ID belongs to another selection.')
                return result
            result=self.export_preview(scope=scope,actor=actor,version_id=version_id)
            if result['preview_sha256']!=preview_sha256:raise ContractError('Export selection, metadata or membership changed; preview again.')
            body=serialize(result['records']);preserve(self.project,body,MEDIA,self.clock())
            result['records_sha256']=content_hash(result.pop('records'))
            result['created_at']=self.clock();files.publish(path,result)
            return result

    def export_bytes(self,key):
        value=files.read(self.path('exports',key));body=artifact(self.project,value['sha256']).read_bytes()
        if len(body)!=value['bytes'] or 'sha256:'+hashlib.sha256(body).hexdigest()!=value['sha256']:raise ContractError('RIS export manifest and bytes differ.')
        return body
