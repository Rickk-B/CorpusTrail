"""CP10 workflow composition over existing scientific services, not new truth.

Prepared forms and operation receipts are project-owned, hash-bound local files.
Opening a page never creates a record, upgrades a database or contacts a provider.
Only explicit commands execute work; interrupted reservations never auto-resend.
"""
from dataclasses import asdict, replace
from contextlib import closing
import base64
import binascii
import hashlib
from importlib.util import find_spec
import json
import os
import re
import threading

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, now
from corpustrail.application import _workflow_files as files
from corpustrail.application.project_use import acquire_project_use, no_links
from corpustrail.application.reads import ProjectReads, _paper_id, _revision
from corpustrail.knowledge.registry import CHARACTERIZATION
from corpustrail.models import ModelConfig, TaskSpec
from corpustrail.models.contracts import safe_data
from corpustrail.populations.contracts import page

SCHEMA = 'corpustrail-local-handoff/v1'
KINDS = {'priority', 'assertion', 'knowledge_event', 'model_configuration',
         'connection', 'extraction', 'resume', 'export', 'mapping'}


def token(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ContractError('invalid local workflow link')
    return value


def text(value, label, limit=8000, optional=False):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value or (not optional and not value.strip()):
        raise ContractError('Check '+label+'.')
    return value.strip()


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys()-set(required)-set(optional):
        raise ContractError('unsupported or missing workflow form fields')
    safe_data(value)


def bounded(value, maximum=2000):
    """Display excerpt only. Exact content is separately inspectable by segments."""
    body = value if isinstance(value, str) else canonical(value)
    return {'text': body[:maximum], 'characters': len(body), 'truncated': len(body)>maximum,
            'sha256': content_hash(value)}


class HandoffController:
    def __init__(self, *, clock=now, model_service=None, priority_adapter=None):
        self.clock = clock
        self._models = model_service
        self.priority_adapter = priority_adapter
        self._lock = threading.RLock()
        self._workers = {}
        self._closed = False

    def model(self, project):
        return self._models(project) if self._models else project.models

    @staticmethod
    def root(project):
        return files.location(project, family='handoff')

    def read(self, project, kind, key):
        return files.read(self.root(project)/kind/(token(key)+'.json'))

    def publish(self, project, kind, key, value):
        files.publish(self.root(project)/kind/(token(key)+'.json'), value)

    @staticmethod
    def state(project, db):
        extra = [tuple(db.execute(sql).fetchone()) for sql in (
            'SELECT COUNT(*) FROM knowledge_assertions', 'SELECT COUNT(*) FROM knowledge_events',
            'SELECT COUNT(*) FROM ct_priority_artifacts', 'SELECT COUNT(*) FROM ct_priority_runs')]
        return content_hash([_revision(db), extra])

    def configuration(self, project):
        with connection(project.database_path) as db:
            revision, config = latest_config(db)
            state = self.state(project, db)
        definitions = project.knowledge_store.registry.definitions()
        return {'schema': SCHEMA, 'revision': revision, 'state': state,
            'optional_ml_installed': all(find_spec(n) is not None for n in ('sklearn','numpy','scipy')),
            'priority_available': self.priority_adapter is not None or all(find_spec(n) is not None for n in ('sklearn','numpy','scipy')),
            'synthetic_priority': self.priority_adapter is not None,
            'reviewers': config['review']['authorized_reviewers'],
            'predicates': [{'id': d['concept_id'], 'version': d['version'], 'label': d['label'],
                            'description': d['description']} for d in definitions if d['concept_id'] in CHARACTERIZATION
                            or d['concept_id'].split('.')[0] not in {'ct','bibliography'}],
            'models': self.model(project).status(),
            'editable_models':[{'workflow':m.workflow_id,'model':m.model,'credential_env':m.credential_env or '',
                'endpoint':m.adapter_configuration.get('base_url',''),'execution':m.adapter_configuration.get('execution',''),
                'timeout':m.adapter_configuration.get('timeout_seconds',30),'temperature':m.settings.get('temperature',0),
                'max_tokens':m.settings.get('max_tokens',m.settings.get('max_completion_tokens',1024))}
                for m in project.config.models if m.adapter=='compatible-endpoint'],
            'notice': 'Operational tools, not a method-blind packet. Opening tools makes no network request or scientific change.'}

    def list(self, project, section, *, offset=0, limit=20, revision=None, paper=None, predicate=None):
        page(offset, limit)
        with connection(project.database_path) as db:
            state = self.state(project, db)
            if offset and revision != state: raise ContractError('Tools changed. Refresh to restart pagination.')
            if section == 'knowledge':
                query = ('SELECT observation_id AS id,paper_id,\'bibliography.record\' AS predicate FROM ct_paper_observations '
                    'UNION ALL SELECT event_id,paper_id,\'ct.broad_corpus_membership\' FROM ct_review_events '
                    'UNION ALL SELECT event_id,paper_id,\'ct.evidence_availability\' FROM ct_pipeline_events WHERE kind=\'representation\' '
                    'UNION ALL SELECT assertion_id,paper_id,predicate FROM knowledge_assertions')
                where, args = [], []
                if paper: where.append('paper_id=?'); args.append(_paper_id(paper))
                if predicate: where.append('predicate=?'); args.append(text(predicate,'predicate',200))
                sql = 'SELECT * FROM ('+query+')'+(' WHERE '+' AND '.join(where) if where else '')
                total = db.execute('SELECT COUNT(*) FROM ('+sql+')',args).fetchone()[0]
                ids = [r['id'] for r in db.execute(sql+' ORDER BY id LIMIT ? OFFSET ?',(*args,limit,offset))]
                records = project.knowledge._observations(db, selected=ids)
                items = []
                for value in records:
                    value = dict(value)
                    value['value'] = bounded(value.pop('raw_value'))
                    value['relation_count'] = len(value['relations'])
                    value.pop('relations'); value.pop('source'); value.pop('context'); value.pop('normalized_value')
                    validation = value.get('validation')
                    if validation: value['validation'] = {'initial':validation['initial'],'events':len(validation['history'])}
                    value['evidence'] = {k:v for k,v in (value['evidence'] or {}).items() if k not in {'bases','reference'}}
                    if len(canonical(value['evidence']))>2000:value['evidence']=bounded(value['evidence'])
                    for key in ('purposes','grant_ids'):
                        values=value['authority'].get(key,[])
                        if len(values)>20:
                            value['authority'][key]=values[:20]
                            value['authority'][key+'_omitted']=len(values)-20
                    value['handle'] = hashlib.sha256(value['observation_ref'].encode()).hexdigest()
                    value['publication'] = ProjectReads(project)._row(db,value['paper_id']) if value['paper_id'] else None
                    items.append(value)
            elif section == 'rankings':
                total = db.execute('SELECT COUNT(*) FROM ct_priority_runs').fetchone()[0]
                rows = db.execute('SELECT run_id,artifact_id FROM ct_priority_runs ORDER BY run_id LIMIT ? OFFSET ?',(limit,offset))
                items=[]
                for row in rows:
                    value=project.prioritization.run(row['run_id'])
                    items.append({'id':row['run_id'],'handle':hashlib.sha256(row['run_id'].encode()).hexdigest(),
                        'created_at':value['created_at'],'count':len(value['scores']),'method':value['method'],
                        'artifact_id':row['artifact_id'],'non_authoritative':True})
            elif section in {'exports','operations','connections','extractions','mappings'}:
                # Directory entries are navigation metadata; contents always pass native/hash validation.
                directory = (no_links(project.root/project.config.data_directory/'asreview'/'exports',missing=True)
                             if section=='exports' else self.root(project)/'prepared')
                candidates=sorted((p.name for p in directory.iterdir() if p.is_dir() and not p.is_symlink())) if section=='exports' and directory.exists() else []
                if section!='exports' and directory.exists():
                    wanted={'connections':'connection','extractions':'extraction','mappings':'mapping'}.get(section)
                    candidates=[p.stem for p in sorted(directory.glob('*.json')) if wanted is None or files.read(p)['kind']==wanted]
                total=len(candidates);items=[]
                for key in candidates[offset:offset+limit]:
                    if section=='exports':
                        try:
                            self.export_guard(project,key)
                            value=project.asreview.inspect(key)
                            items.append({'id':key,'handle':key,'count':value['row_count'],'created_at':value['snapshot']['created_at'],
                                'sha256':value['dataset_sha256'],'status':'complete'})
                        except (OSError,ValueError,KeyError,ContractError):
                            items.append({'id':key,'handle':key,'status':'incomplete_or_invalid','notice':'Preserved; not downloadable as a verified export.'})
                    else: items.append(self.operation(project,key))
            else: raise ContractError('unknown tools list')
        return {'schema':SCHEMA,'items':items,'total':total,'revision':state,
                'next_offset':offset+limit if offset+limit<total else None}

    def knowledge(self, project, handle, *, section='record', offset=0, limit=16000, revision=None):
        if section not in {'record','history','peers'}:raise ContractError('unknown observation section')
        if not isinstance(handle,str) or not re.fullmatch('[0-9a-f]{64}',handle): raise ContractError('invalid observation link')
        # Hash handles are resolved from exact existing IDs, never from titles or array position.
        with connection(project.database_path) as db:
            state=self.state(project,db)
            if offset and revision!=state:raise ContractError('Observation history changed or continuation lacks its revision; refresh inspection.')
            ids=(r[0] for r in db.execute('SELECT observation_id FROM ct_paper_observations UNION ALL '
                'SELECT event_id FROM ct_review_events UNION ALL SELECT event_id FROM ct_pipeline_events WHERE kind=\'representation\' '
                'UNION ALL SELECT assertion_id FROM knowledge_assertions'))
            oid=next((v for v in ids if hashlib.sha256(v.encode()).hexdigest()==handle),None)
            if oid is None: raise ContractError('unknown observation')
            value=project.knowledge._observations(db,selected=[oid])[0]
            peer_rows=list(db.execute('SELECT assertion_id FROM knowledge_assertions WHERE subject_id=? AND predicate=? ORDER BY assertion_id LIMIT ? OFFSET ?',
                (value['subject_id'],value['predicate'],min(limit,100),offset))) if value['origin']=='stored' else []
            peer_count=db.execute('SELECT COUNT(*) FROM knowledge_assertions WHERE subject_id=? AND predicate=?',
                (value['subject_id'],value['predicate'])).fetchone()[0] if value['origin']=='stored' else 0
            conflict=False
            if value['origin']=='stored':
                for candidate in db.execute('SELECT assertion_id,payload_json FROM knowledge_assertions WHERE subject_id=? AND predicate=?',
                        (value['subject_id'],value['predicate'])):
                    other=json.loads(candidate['payload_json'])
                    if other['raw_value'] is not None and value['raw_value'] is not None and canonical(other['raw_value'])!=canonical(value['raw_value']):
                        project.knowledge._observations(db,selected=[candidate['assertion_id']]);conflict=True;break
            if section=='peers':
                page(offset,limit)
                peers=project.knowledge._observations(db,selected=[r[0] for r in peer_rows])
                return {'schema':SCHEMA,'revision':state,'items':[{'handle':hashlib.sha256(v['observation_ref'].encode()).hexdigest(),
                    'value':bounded(v['raw_value']),'producer':v['producer'],'timestamp':v['timestamp']} for v in peers],
                    'total':peer_count,'next_offset':offset+limit if offset+limit<peer_count else None}
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=32000: raise ContractError('invalid inspection segment')
        if section=='history':
            page(offset,limit);rows=value['relations'];return {'schema':SCHEMA,'revision':state,'items':rows[offset:offset+limit],
                'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None}
        body=canonical(value)
        return {'schema':SCHEMA,'revision':state,'text':body[offset:offset+limit],'characters':len(body),
            'next_offset':offset+limit if offset+limit<len(body) else None,'sha256':content_hash(value),
            'summary':{'id':oid,'predicate':value['predicate'],'producer':value['producer'],'authority':value['authority'],
                'value':bounded(value['raw_value']),'evidence':bounded(value['evidence']),
                'conflicting_values':conflict,'peer_count':peer_count,'stored':value['origin']=='stored'}}

    def ranking(self, project, handle, *, offset=0, limit=20, section='scores'):
        if section=='scores':page(offset,limit)
        elif section!='provenance' or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=32000:
            raise ContractError('invalid ordering inspection')
        with connection(project.database_path) as db:
            key=next((r[0] for r in db.execute('SELECT run_id FROM ct_priority_runs') if hashlib.sha256(r[0].encode()).hexdigest()==handle),None)
            if key is None: raise ContractError('unknown ordering')
            value=project.prioritization.run(key);items=[]
            if section=='provenance':
                source={'ranking':value,'training_model':project.prioritization.artifact(value['model_id']),
                    'ranking_inputs':project.prioritization.run_provenance(key)}
                body=canonical(source)
                return {'schema':SCHEMA,'text':body[offset:offset+limit],'characters':len(body),'sha256':content_hash(source),
                    'next_offset':offset+limit if offset+limit<len(body) else None}
            for row in value['scores'][offset:offset+limit]:
                items.append({**row,'publication':ProjectReads(project)._row(db,row['paper_id'])})
        return {'schema':SCHEMA,'id':key,'items':items,'total':len(value['scores']),
            'next_offset':offset+limit if offset+limit<len(value['scores']) else None,
            'provenance':{k:v for k,v in value.items() if k not in {'scores','candidate_population'}},
            'notice':'Operational ranking score, not calibrated membership probability or independent validation. Every candidate remains accessible; no stopping rule.'}

    def model_history(self, project, *, offset=0, limit=20, revision=None, connection_tests=False, handle=None, event=None):
        if event is None:page(offset,limit)
        elif not handle or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=32000:
            raise ContractError('invalid exact history segment')
        with connection(project.database_path) as db:
            table,key=('ct_model_connection_events','run_id') if connection_tests else ('ct_model_events','scope_id')
            state=content_hash([latest_config(db)[0],db.execute('SELECT COALESCE(MAX(sequence),0) FROM '+table).fetchone()[0]])
            if offset and revision!=state:raise ContractError('Model history changed; refresh to restart.')
            total=db.execute('SELECT COUNT(DISTINCT '+key+') FROM '+table).fetchone()[0]
            if handle:
                rid=next((r[0] for r in db.execute('SELECT DISTINCT '+key+' FROM '+table) if hashlib.sha256(r[0].encode()).hexdigest()==handle),None)
                if rid is None:raise ContractError('unknown model history link')
                events=self.model(project).connection_history(rid) if connection_tests else self.model(project).inspect(rid)
                if event is not None:
                    selected=next((v for v in events if v['event_id']==event),None)
                    if selected is None:raise ContractError('unknown saved model event')
                    body=canonical(selected)
                    return {'schema':SCHEMA,'revision':state,'text':body[offset:offset+limit],'characters':len(body),'sha256':content_hash(selected),
                        'next_offset':offset+limit if offset+limit<len(body) else None}
                items=[{'event_id':v['event_id'],'kind':v['kind'],'payload':bounded(v)} for v in events[offset:offset+limit]]
                return {'schema':SCHEMA,'items':items,'total':len(events),'revision':state,
                    'next_offset':offset+limit if offset+limit<len(events) else None}
            ids=[r[0] for r in db.execute('SELECT '+key+' FROM '+table+' GROUP BY '+key+' ORDER BY '+key+' LIMIT ? OFFSET ?',(limit,offset))]
            items=[]
            for rid in ids:
                events=self.model(project).connection_history(rid) if connection_tests else self.model(project).inspect(rid)
                complete=next((v for v in reversed(events) if v['kind'] in {'complete','model_complete'}),None)
                first=events[0]['payload'];plan=next((v['payload']['plan'] for v in events if isinstance(v.get('payload',{}).get('plan'),dict)),{})
                items.append({'handle':hashlib.sha256(rid.encode()).hexdigest(),'workflow':plan.get('workflow_id','Saved model task'),
                    'created_at':plan.get('created_at',first.get('started_at')),'status':complete['payload'].get('status') if complete else 'interrupted_or_incomplete',
                    'saved_response_available':any(v['kind']=='model_response' for v in events),
                    'notice':'Synthetic connection test only; not scientific validation.' if connection_tests else 'Non-authoritative structured Knowledge task; never membership authority.'})
            return {'schema':SCHEMA,'items':items,'total':total,'revision':state,'next_offset':offset+limit if offset+limit<total else None}

    def evidence_choices(self, project, paper):
        pid=_paper_id(paper);items=[]
        for obs in project.identities.observations(pid):
            items.append({'key':obs['observation_id'],'label':'Source metadata — '+str(obs['source'].get('record_id','source record')),
                'representation':'metadata','reference':{'kind':'bibliographic_observation','observation_id':obs['observation_id']}})
            if obs['record'].get('abstract'):
                items.append({'key':obs['observation_id']+'/abstract','label':'Source abstract','representation':'abstract',
                    'reference':{'kind':'bibliographic_observation','observation_id':obs['observation_id'],'field':'abstract'}})
        for rep in project.evidence.representations(pid):
            if rep['payload'].get('trusted'):
                items.append({'key':rep['event_id'],'label':'Verified '+rep['payload']['representation'],
                    'representation':rep['payload']['representation'],'reference':{'kind':'representation','event_id':rep['event_id']}})
        return {'schema':SCHEMA,'items':items,'notice':'Available evidence is not an attestation that it was read.'}

    def prepare(self, project, kind, values, *, request_id):
        token(request_id)
        if kind not in KINDS: raise ContractError('unknown tools operation')
        path=self.root(project)/'prepared'/(request_id+'.json')
        with closing(files.operation_lease(project,'handoff-prepare')):
            if path.exists():
                old=files.read(path)
                if old['kind']!=kind or old['form']!=values: raise ContractError('request identity belongs to another form')
                return self.operation(project,request_id)
            fields(values,{'actor'},set(values)-{'actor'})
            actor=text(values['actor'],'actor',100)
            with connection(project.database_path) as db: revision,config=latest_config(db);state=self.state(project,db)
            at=self.clock();data={};summary={}
            if kind=='export':
                fields(values,{'actor'})
                snapshot=project.asreview.plan('ui-'+request_id,created_at=at)
                relative=project.config.data_directory+'/handoff-workflows/v1/export-plans/'+request_id+'.json'
                no_links(project.root/relative,missing=True)
                project.asreview.write_snapshot(snapshot,relative)
                data={'path':relative,'sha256':snapshot['snapshot_sha256'],'export_id':snapshot['export_id']}
                summary={'included':len(snapshot['records']),'membership_counts':snapshot['membership_counts'],
                    'missing_abstract':sum(not r['abstract'] for r in snapshot['records']),
                    'notice':'All and only these frozen confirmed members; unlabelled bibliography, no automatic ASReview seeds.'}
            elif kind=='assertion':
                fields(values,{'actor','paper','predicate','value','unknown','evidence','rationale'})
                pid=_paper_id(values['paper']);predicate=text(values['predicate'],'predicate',200)
                allowed={d['id']:d for d in self.configuration(project)['predicates']}
                if predicate not in allowed: raise ContractError('choose an existing characterization field, not membership')
                if type(values['unknown']) is not bool: raise ContractError('unknown must be explicit')
                choice=next((v for v in self.evidence_choices(project,values['paper'])['items'] if v['key']==values['evidence']),None)
                if choice is None: raise ContractError('choose actual evidence')
                rationale=text(values['rationale'],'rationale')
                value=None if values['unknown'] else text(values['value'],'observed value')
                draft={'subject_type':'paper','subject_id':pid,'paper_id':pid,'predicate':predicate,
                    'vocabulary_version':allowed[predicate]['version'],'raw_value':value,'value_datatype':'unknown' if value is None else 'string',
                    'producer_type':'human','producer_id':actor,'created_at':at,'evidence_representation':choice['representation'],
                    'evidence_reference':choice['reference'],'source':{'reference':'local-ui:'+request_id,'rationale':rationale},
                    'lineage_ref':'local-ui:'+request_id}
                data={'plan':project.knowledge_store.plan_batch([draft])};summary={'predicate':allowed[predicate]['label'],
                    'value':value,'rationale':rationale,'notice':'New unvalidated, non-authoritative human assertion. No membership change.'}
            elif kind=='knowledge_event':
                fields(values,{'actor','observation','relation','rationale','purpose','policy'}, {'source_observation','grant'})
                record=self.knowledge(project,values['observation'])['summary']
                if not record['stored']: raise ContractError('adapted observations are inspected at their original scientific service')
                relation=values['relation']
                if relation not in {'validates','rejects','disputes','grants_authority','revokes_authority','retracts','supersedes','duplicates','derived_from'}:
                    raise ContractError('unsupported relation')
                decision={'actor':actor,'target':record['id'],'relation':relation,'rationale':text(values['rationale'],'rationale'),
                          'purpose':text(values['purpose'],'Knowledge purpose',200),'policy':text(values['policy'],'Knowledge policy',200)}
                source={'reference':'local-ui:'+request_id,'artifact_sha256':content_hash(decision)}
                event={'target_assertion_id':record['id'],'relation':relation,'actor_type':'human','actor_id':actor,
                    'created_at':at,'rationale':decision['rationale'],'source':source,'lineage_ref':'local-ui:'+request_id,
                    'purpose':decision['purpose'],'policy_id':decision['policy']}
                if relation in {'supersedes','duplicates','derived_from'}:
                    event['source_assertion_id']=self.knowledge(project,values.get('source_observation',''))['summary']['id']
                if relation=='revokes_authority':event['target_event_id']=text(values.get('grant',''),'specific grant',200)
                plan=project.knowledge_store.plan_batch(events=[event])
                data={'plan':plan,'human_approval':{'plan_sha256':plan['plan_sha256'],'reviewer_id':actor,
                    'purposes':[decision['purpose']],'policy_id':decision['policy'],'decision_source':source}}
                summary={**decision,'notice':'Purpose-specific Knowledge event only. This cannot publish corpus membership or verify an untrusted document.'}
            elif kind=='priority':
                fields(values,{'actor'})
                if not self.configuration(project)['optional_ml_installed'] and self.priority_adapter is None:
                    raise ContractError('optional numerical libraries are not installed; manual review remains available')
                summary={'notice':'Explicitly freeze currently available human training labels, train operational TF-IDF ordering and rank all current candidates. Labels marked insufficient are not negatives. Features are captured at execution, not reconstructed at label cutoff. No automatic inclusion, exclusion or stopping.'}
                data={'label_cutoff':at,'run_id':'ui-'+request_id}
            elif kind=='model_configuration':
                fields(values,{'actor','workflow','model','endpoint','execution','credential_env','temperature','max_tokens','timeout','confirm_frozen'})
                if values['confirm_frozen'] is not True: raise ContractError('confirm the effect on frozen sessions')
                previous=next((m for m in project.config.models if m.workflow_id==values['workflow'] and m.adapter=='compatible-endpoint'),None)
                settings=dict(previous.settings) if previous else {}
                settings.update({'temperature':values['temperature'],
                    'max_completion_tokens' if 'max_completion_tokens' in settings else 'max_tokens':values['max_tokens']})
                configured=ModelConfig(text(values['workflow'],'workflow',100),'compatible-endpoint',text(values['model'],'model',200),
                    endpoint_id=text(values['workflow'],'endpoint name',100),credential_env=values['credential_env'] or None,
                    settings=settings,adapter_configuration={'base_url':values['endpoint'],'execution':values['execution'],'timeout_seconds':values['timeout']})
                configured.validate();self.model(project).registry.resolve(configured.adapter,configuration=configured)
                data={'configuration':asdict(configured)}
                summary={'workflow':configured.workflow_id,'model':configured.model,'execution':values['execution'],
                    'notice':'Configuration only, not a connection test, validated scientific capability or assessment engine. No secret value is stored. Existing frozen sessions retain their snapshots and may become stale.'}
            elif kind=='connection':
                fields(values,{'actor','workflow'})
                c=self.model(project)._config(values['workflow']);adapter=self.model(project).registry.resolve(c.adapter,configuration=c)
                if not callable(getattr(adapter,'connection_request',None)): raise ContractError('synthetic connection test unavailable')
                data={'workflow':c.workflow_id,'run_id':'ui-'+request_id,'remote':adapter.info.data_leaves_machine}
                summary={'request':adapter.connection_request(),'model':c.model,'execution':'remote' if data['remote'] else 'declared local',
                    'notice':'Fixed synthetic connection message only. No project evidence or scientific task. Success does not validate extraction or membership assessment.'}
            elif kind=='extraction':
                fields(values,{'actor','workflow','paper','instructions','predicates','mode'}, {'representation','start','end'})
                predicates=tuple(values['predicates'])
                allowed={d['id'] for d in self.configuration(project)['predicates']}
                if not predicates or not set(predicates)<=allowed: raise ContractError('choose registered characterization fields, not membership')
                spec=TaskSpec('user-characterization','v1',text(values['instructions'],'task instructions'),predicates)
                passages=((values['start'],values['end']),) if values['mode']=='selected_passages' else ()
                plan=self.model(project).plan(values['workflow'],spec,run_id='ui-'+request_id,paper_id=_paper_id(values['paper']),
                    mode=values['mode'],representation_id=values.get('representation'),passages=passages,created_at=at)
                relative=project.config.data_directory+'/handoff-workflows/v1/model-plans/'+request_id+'.json'
                no_links(project.root/relative,missing=True);self.model(project).write_plan(plan,relative)
                data={'path':relative,'sha256':plan['plan_sha256'],'run_id':plan['run_id'],'remote':plan['adapter']['data_leaves_machine']}
                summary={'paper':project.discovery.metadata(_paper_id(values['paper']))['fields'].get('title') or 'Untitled publication','mode':values['mode'],'evidence_characters':sum(len(v['text']) for v in plan['evidence']),
                    'model':plan['configuration']['model'],'task':spec.to_dict(),'remote':data['remote'],
                    'notice':'Experimental structured Knowledge assertions, not a CP8 membership engine. Exact input must be inspected and separately authorized. No real-server or scientific validation is implied.'}
            elif kind=='resume':
                fields(values,{'actor','run'})
                with connection(project.database_path) as db:
                    run=next((r[0] for r in db.execute('SELECT DISTINCT scope_id FROM ct_model_events') if hashlib.sha256(r[0].encode()).hexdigest()==values['run']),None)
                if run is None:raise ContractError('unknown saved model run')
                data={'run_id':run};summary={'notice':'Finish only an already saved response using the existing resume service. No model invocation, network resend, membership change or implicit new consent is performed.'}
            elif kind=='mapping':
                fields(values,{'actor','export','upload','question','review','asreview_version'})
                upload=self.read(project,'uploads',values['upload'])
                data={**values,'path':upload['path'],'sha256':upload['sha256'],'mapping_id':'ui-'+request_id}
                self.export_guard(project,values['export']);project.asreview.inspect(values['export'])
                text(values['question'],'question',128);text(values['review'],'review name',128)
                data['question_id']='question-'+hashlib.sha256(values['question'].encode()).hexdigest()[:24]
                data['review_id']='review-'+hashlib.sha256(values['review'].encode()).hexdigest()[:24]
                exported=project.asreview.inspect(values['export'])
                summary={'export':'Saved bibliography · '+exported['snapshot']['created_at'],'question':values['question'],'review':values['review'],
                    'notice':'Map the complete returned CSV by exact exported IDs, never titles or row positions. These question-specific results will not change broad-corpus membership, reference labels or ASReview state.'}
            safe_data(data,secrets=self.model(project)._secrets())
            record={'schema':SCHEMA,'id':request_id,'project_id':project.config.project_id,'kind':kind,'form':values,
                'actor':actor,'created_at':at,'config_event_id':revision,'state':state,'data':data,'summary':summary}
            safe_data(record,secrets=self.model(project)._secrets())
            self.publish(project,'prepared',request_id,record)
            return self.operation(project,request_id)

    def operation(self, project, key):
        value=self.read(project,'prepared',key)
        with self._lock: active=bool(self._workers.get((str(project.root),key)) and self._workers[str(project.root),key].is_alive())
        done=self.root(project)/'completed'/(key+'.json');started=self.root(project)/'started'/(key+'.json')
        result=files.read(done) if done.exists() else None
        return {'schema':SCHEMA,'id':key,'kind':value['kind'],'actor':value['actor'],'created_at':value['created_at'],
            'summary':value['summary'],'preview_sha256':content_hash(value),
            'status':result['status'] if result else 'running' if active else 'interrupted' if started.exists() else 'prepared',
            'result':result,'worker_active':active and result is None,
            'saved_ordering_stages':{name:self.read(project,name,key)['id'] for name in ('priority-snapshot','priority-model')
                if (self.root(project)/name/(key+'.json')).is_file()},
            'notice':'Opening never executes or retries. Interrupted requests require inspection and a new explicit operation.'}

    def exact_plan(self, project, key, *, offset=0, limit=16000):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=32000: raise ContractError('invalid exact-plan segment')
        record=self.read(project,'prepared',key);data=record['data']
        if record['kind']=='extraction':
            no_links(project.root/data['path']);value=self.model(project).read_plan(data['path'])
        elif record['kind']=='export': value=json.loads(no_links(project.root/data['path']).read_text(encoding='utf-8'))
        else:value=data
        body=canonical(value)
        return {'schema':SCHEMA,'text':body[offset:offset+limit],'characters':len(body),'sha256':content_hash(value),
            'next_offset':offset+limit if offset+limit<len(body) else None}

    def execute(self, project, key, *, preview_sha256, confirmed, confirm_external=False):
        token(key)
        if confirmed is not True or type(confirm_external) is not bool: raise ContractError('explicit confirmation required')
        with self._lock, closing(files.operation_lease(project,'handoff-execution')):
            if self._closed: raise ContractError('application is shutting down')
            prepared=self.read(project,'prepared',key)
            if prepared['project_id']!=project.config.project_id or content_hash(prepared)!=preview_sha256: raise ContractError('changed or foreign preview')
            existing=self.operation(project,key)
            if existing['status'] in {'complete','failed','running'}: return existing
            if existing['status']=='interrupted': raise ContractError('interrupted operation; inspect stored history before preparing another')
            if any(p==str(project.root) and t.is_alive() for (p,_),t in self._workers.items()): raise ContractError('another tools operation is active')
            with connection(project.database_path) as db:
                if latest_config(db)[0]!=prepared['config_event_id'] or self.state(project,db)!=prepared['state']:
                    raise ContractError('project changed since preview; prepare and inspect a fresh operation')
            if prepared['data'].get('remote') and confirm_external is not True: raise ContractError('explicit exact remote-transfer approval required')
            lease=acquire_project_use(project.root)
            operation=files.operation_lease(project,'handoff-worker')
            try:self.publish(project,'started',key,{'prepared_sha256':preview_sha256,'confirmed':True,
                'confirm_external':confirm_external,'started_at':self.clock()})
            except BaseException:
                operation.close();lease.close();raise
            def work():
                try:
                    output=self._perform(project,prepared,confirm_external)
                    safe_data(output,secrets=self.model(project)._secrets())
                    self.publish(project,'completed',key,{'status':'failed' if output.get('status') in {'failed','error'} else 'complete',
                        'completed_at':self.clock(),'output':output})
                except Exception:
                    # Raw errors may contain endpoints, paths or secrets. Native partial artifacts remain intact.
                    self.publish(project,'completed',key,{'status':'failed','completed_at':self.clock(),
                        'message':'Operation failed; inspect saved scientific/operation history before preparing another. No automatic retry, rollback of earlier native stages or cleanup was attempted.'})
                finally:
                    operation.close();lease.close()
            worker=threading.Thread(target=work,name='corpustrail-local-tools',daemon=False)
            self._workers[str(project.root),key]=worker
            try:worker.start()
            except BaseException:
                operation.close();lease.close();raise
        return self.operation(project,key)

    def _perform(self, project, prepared, confirm_external):
        data=prepared['data'];kind=prepared['kind'];key=prepared['id'];actor=prepared['actor']
        if kind=='priority':
            service=project.prioritization
            snapshot=service.snapshot(label_cutoff=data['label_cutoff'],created_at=self.clock())
            self.publish(project,'priority-snapshot',key,{'id':snapshot['artifact_id']})
            model=service.train(snapshot['artifact_id'],adapter=self.priority_adapter,created_at=self.clock())
            self.publish(project,'priority-model',key,{'id':model['artifact_id']})
            ranked=service.rank(model['artifact_id'],run_id=data['run_id'],adapter=self.priority_adapter,created_at=self.clock())
            return {'run_id':data['run_id'],'count':len(ranked['scores']),'training_snapshot':snapshot['artifact_id'],
                'model_id':model['artifact_id'],'notice':'Ordering only; no corpus, evidence, review or downstream label change.'}
        if kind=='assertion': return project.knowledge_store.apply(data['plan'])
        if kind=='knowledge_event':return project.knowledge_store.apply(data['plan'],human_authorization=data['human_approval'])
        if kind=='model_configuration':
            configured=ModelConfig(**data['configuration']);current=project.config
            updated=replace(current,config_version=current.config_version+1,
                models=tuple(v for v in current.models if v.workflow_id!=configured.workflow_id)+(configured,))
            return {'configuration_event_id':project.configure(updated,expected_event_id=prepared['config_event_id'],created_by=actor,created_at=self.clock()),
                'notice':'Configured only. Existing snapshots/history retained; no connection or scientific request made.'}
        if kind=='connection':return self.model(project).test_connection(data['workflow'],run_id=data['run_id'],confirm_external=confirm_external,clock=self.clock)
        if kind=='resume':return self.model(project).resume(data['run_id'])
        if kind=='extraction':
            no_links(project.root/data['path']);service=self.model(project);plan=service.read_plan(data['path'])
            if plan['plan_sha256']!=data['sha256']:raise ContractError('changed exact input')
            consent=service.authorize(plan,actor_id=actor,confirm_external=confirm_external)
            return service.execute(plan,consent_event_id=consent,clock=self.clock)
        if kind=='export':
            self.export_guard(project,data['export_id'],missing=True)
            snapshot=json.loads(no_links(project.root/data['path']).read_text(encoding='utf-8'))
            if snapshot['snapshot_sha256']!=data['sha256']: raise ContractError('changed export plan')
            value=project.asreview.create(snapshot)
            return {'export_id':data['export_id'],'records':value['export']['row_count'],'dataset_sha256':value['export']['dataset_sha256']}
        if kind=='mapping':
            path=no_links(project.root/data['path'])
            if 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()!=data['sha256']:raise ContractError('changed result file')
            value=project.asreview.map_results(data['export'],results=path,review_id=data['review_id'],question_id=data['question_id'],
                mapping_id=data['mapping_id'],asreview_version=data['asreview_version'],created_at=self.clock())
            return {k:v for k,v in value.items() if k!='records'}|{'records':len(value['records'])}
        raise ContractError('unknown operation')

    def upload(self, project, *, request_id, offset, body, final, sha256):
        """One selected ASReview result CSV only; no arbitrary filesystem endpoint."""
        token(request_id)
        if type(offset) is not int or offset<0 or type(final) is not bool or not re.fullmatch('sha256:[0-9a-f]{64}',sha256): raise ContractError('invalid result upload')
        try:raw=base64.b64decode(body,validate=True)
        except (ValueError,TypeError,binascii.Error) as error:raise ContractError('invalid result upload encoding') from error
        if len(raw)>32768 or offset+len(raw)>128*1024**2:raise ContractError('result file exceeds explicit upload resource budget')
        path=no_links(self.root(project)/'result-files'/(request_id+'.csv'),missing=True)
        with closing(files.operation_lease(project,'handoff-upload')):
            path.parent.mkdir(parents=True,exist_ok=True)
            size=path.stat().st_size if path.exists() else 0
            if self.root(project).joinpath('uploads',request_id+'.json').exists():
                old=self.read(project,'uploads',request_id)
                if old['sha256']!=sha256: raise ContractError('upload ID belongs to different bytes')
                return {'schema':SCHEMA,'id':request_id,'complete':True,'bytes':old['bytes']}
            if offset<size:
                with path.open('rb') as stream:stream.seek(offset);existing=stream.read(len(raw))
                if offset+len(raw)>size or existing!=raw:raise ContractError('conflicting upload retry')
            elif offset==size:
                with path.open('ab' if path.exists() else 'xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            else:raise ContractError('upload offset does not follow saved bytes')
            size=path.stat().st_size
            if final:
                with path.open('rb') as stream:actual='sha256:'+hashlib.file_digest(stream,'sha256').hexdigest()
                if actual!=sha256:raise ContractError('result upload hash mismatch; bytes preserved, not mapped')
                self.publish(project,'uploads',request_id,{'path':path.relative_to(project.root).as_posix(),'sha256':actual,'bytes':size})
            return {'schema':SCHEMA,'id':request_id,'complete':final,'bytes':size}

    @staticmethod
    def export_guard(project, export_id, *, missing=False):
        if not isinstance(export_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',export_id):
            raise ContractError('invalid export identity')
        directory=no_links(project.root/project.config.data_directory/'asreview'/'exports'/export_id,missing=missing)
        for name in ('snapshot.json','dataset.csv','export.json'):no_links(directory/name,missing=missing)
        return directory

    def download(self, project, export_id, filename):
        if not re.fullmatch(r'ui-[0-9a-f]{32}|[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',export_id) or filename not in {'dataset.csv','snapshot.json','export.json'}:
            raise ContractError('invalid export download')
        directory=self.export_guard(project,export_id)
        project.asreview.inspect(export_id)
        path=no_links(directory/filename)
        if path.stat().st_size>128*1024**2:raise ContractError('export exceeds explicit 128 MiB download budget')
        return path.read_bytes()

    def close(self):
        with self._lock:self._closed=True;workers=list(self._workers.values())
        for worker in workers:worker.join()  # Existing bounded native calls finish; never abandon a scientific writer.
