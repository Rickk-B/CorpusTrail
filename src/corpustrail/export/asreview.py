"""Immutable unlabeled bibliography; downstream labels never curate the corpus.

Adapted from the generic historical corpus exporter, not benchmark interchange.
No ASReview SDK or external process is used. Persistence is no-clobber files only.
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import re
import uuid

from corpustrail import __version__
from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import canonical, content_hash, digest_bytes, confined, text, timestamp, now, ContractError
from corpustrail.curation.service import membership_in_connection

SNAPSHOT_SCHEMA = 'corpustrail-standalone-asreview-corpus-snapshot/v0'
EXPORT_SCHEMA = 'corpustrail-standalone-asreview-corpus-export/v0'
MAPPING_SCHEMA = 'corpustrail-standalone-asreview-result-mapping/v0'
SELECTION_RULE = 'authoritative-broad-corpus-members/v0'
FIELD_MAPPING = 'standalone-canonical-metadata-and-verified-aliases/v0'
FORMAT = 'csv-utf8-lf/v0'
FIELDS = ('corpustrail_paper_id','title','abstract','authors','year','journal_or_source',
          'doi','url','pmid','pmcid','openalex_id','semantic_scholar_id','corpustrail_identifiers')
IDENTIFIERS = {'doi':'doi','pmid':'pmid','pmcid':'pmcid','openalex':'openalex_id','semantic_scholar':'semantic_scholar_id'}
ASREVIEW_VERSION_SPEC = '>=2.2,<3'
LABEL_SEMANTICS = 'downstream_question_specific_not_broad_corpus_membership'


def _name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',value):
        raise ContractError('export, review and mapping IDs must be safe stable identifiers')
    return value


def _bytes(value):
    return (canonical(value)+'\n').encode('utf-8')


def _load(path):
    result=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(result,dict):
        raise ContractError('artifact must be a JSON object')
    return result


def _csv_rows(body):
    # Historical v0 CSV structure validation, with the standalone public error.
    reader=csv.DictReader(io.StringIO(body.decode('utf-8-sig'),newline=''))
    if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):
        raise ContractError('missing or duplicate CSV headers')
    rows=list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ContractError('malformed CSV row')
    return reader.fieldnames,rows


def _write_bytes(path,body):
    """Historical fsync/exclusive-hard-link publication; never replace a target."""
    target=Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError('refusing to overwrite export artifact')
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=target.parent/f'.{target.name}.{uuid.uuid4().hex}.tmp'
    try:
        with temporary.open('xb') as handle:
            os.chmod(temporary,0o600)
            handle.write(body); handle.flush(); os.fsync(handle.fileno())
        os.link(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)


def validate_snapshot(snapshot):
    content={k:v for k,v in snapshot.items() if k!='snapshot_sha256'}
    if snapshot.get('schema_version')!=SNAPSHOT_SCHEMA or content_hash(content)!=snapshot.get('snapshot_sha256'):
        raise ContractError('snapshot schema/hash mismatch')
    _name(snapshot['export_id']); text(snapshot['project_id'],'project ID'); timestamp(snapshot['created_at'])
    if (snapshot.get('fields')!=list(FIELDS) or snapshot.get('label_policy')!='none' or
            snapshot.get('automatic_seeds') is not False or snapshot.get('selection_rule')!=SELECTION_RULE or
            snapshot.get('field_mapping')!=FIELD_MAPPING or snapshot.get('format')!=FORMAT):
        raise ContractError('unsupported export selection, field mapping or label policy')
    records=snapshot.get('records')
    if not isinstance(records,list) or not records or any(not isinstance(r,dict) or set(r)!=set(FIELDS) or
            any(not isinstance(v,str) for v in r.values()) for r in records):
        raise ContractError('nonempty, strictly bibliographic records required')
    ids=[r['corpustrail_paper_id'] for r in records]
    if ids!=sorted(set(ids)) or any(not x.strip() or x!=x.strip() for x in ids):
        raise ContractError('invalid canonical export population')
    if content_hash(ids)!=snapshot.get('population_sha256'):
        raise ContractError('population hash mismatch')
    lineage=snapshot.get('lineage',[])
    if [r.get('paper_id') for r in lineage]!=ids or any(r.get('record_sha256')!=content_hash(record)
            for r,record in zip(lineage,records)):
        raise ContractError('snapshot lineage mismatch')
    for record,line in zip(records,lineage):
        if not record['title'].strip() and not record['abstract'].strip():
            raise ContractError('every member needs a title or abstract; none is silently dropped')
        if not line.get('membership_event_id'):
            raise ContractError('members must have explicit authoritative review provenance')
    membership=snapshot['membership_snapshot']
    if content_hash(membership['states'])!=membership['sha256']:
        raise ContractError('membership snapshot mismatch')
    states=membership['states']
    counts=dict.fromkeys(('included','excluded','insufficient_evidence','unresolved','not_reviewed'),0)
    if [r['paper_id'] for r in states]!=sorted(set(r['paper_id'] for r in states)):
        raise ContractError('membership snapshot must preserve unique canonical IDs')
    for state in states:
        if state['state'] not in counts:raise ContractError('unknown membership state')
        counts[state['state']]+=1
    if counts!=snapshot['membership_counts']:raise ContractError('membership counts mismatch')
    config=snapshot['configuration']; database=snapshot['database_snapshot']
    if (content_hash(config['config'])!=config['sha256'] or config['config']['project_id']!=snapshot['project_id'] or
            content_hash({k:v for k,v in database.items() if k!='snapshot_sha256'})!=database['snapshot_sha256'] or
            database['membership_sha256']!=membership['sha256'] or
            database['selected_metadata_sha256']!=content_hash(lineage) or
            snapshot['corpus_snapshot_id']!='corpus:'+database['snapshot_sha256'][7:]):
        raise ContractError('configuration/database snapshot provenance mismatch')
    members=[r['paper_id'] for r in membership['states'] if r['state']=='included']
    if members!=ids or snapshot['membership_counts']['included']!=len(ids):
        raise ContractError('selection must contain all and only frozen authoritative members')


def render_export(snapshot):
    """Pure historical v0 CSV/sidecar rendering with standalone snapshot contracts."""
    validate_snapshot(snapshot)
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator='\n')
    writer.writeheader(); writer.writerows(snapshot['records'])
    body=stream.getvalue().encode('utf-8')
    sidecar={'schema_version':EXPORT_SCHEMA,'export_id':snapshot['export_id'],'project_id':snapshot['project_id'],
        'snapshot':snapshot,'dataset_sha256':digest_bytes(body),'row_count':len(snapshot['records']),
        'identity_column':'corpustrail_paper_id','label_policy':'none'}
    sidecar['sidecar_sha256']=content_hash(sidecar)
    return body,sidecar


class ExportService:
    """Read/plan plus explicit file writes; never a corpus or ASReview state writer."""
    def __init__(self,project):
        self.project=project

    def _freeze(self,export_id,*,created_at=None,software_commit=None,selection_rule=SELECTION_RULE):
        _name(export_id)
        if selection_rule!=SELECTION_RULE:
            raise ContractError('v0 supports only explicit authoritative broad-corpus membership')
        created_at=created_at or now(); timestamp(created_at)
        if software_commit is not None and not re.fullmatch(r'[0-9a-f]{40,64}',software_commit):
            raise ContractError('software commit must be an explicit full Git hash or unknown')
        with connection(self.project.database_path) as db:
            config_id,config=latest_config(db)
            papers=[dict(r) for r in db.execute('SELECT * FROM paper_entities ORDER BY paper_id')]
            aliases=[dict(r) for r in db.execute("SELECT * FROM paper_identifiers WHERE status='verified' ORDER BY paper_id,scheme,normalized_value,identifier_id")]
            versions=[dict(r) for r in db.execute('SELECT version,name,code_sha256 FROM schema_migrations ORDER BY version')]
            states=[]; records=[]; lineage=[]
            counts=dict.fromkeys(('included','excluded','insufficient_evidence','unresolved','not_reviewed'),0)
            owner={}
            for alias in aliases:
                key=(alias['scheme'],alias['normalized_value'])
                if key in owner and owner[key]!=alias['paper_id']:
                    raise ContractError('verified identifier belongs to multiple canonical papers')
                owner[key]=alias['paper_id']
            for entity in papers:
                pid=entity['paper_id']; current=membership_in_connection(db,pid)
                counts[current['state']]+=1
                states.append({'paper_id':pid,'state':current['state'],'membership_event_id':current['current_event_id']})
                if current['state']!='included': continue
                if entity['identity_state']!='active':
                    raise ContractError('member identity is not active; explicitly resolve identity before export')
                metadata=self.project.discovery._metadata(db,pid)
                fields=metadata['fields']; record=dict.fromkeys(FIELDS,'')
                record.update(corpustrail_paper_id=pid,title=fields['title'] or '',abstract=fields['abstract'] or '',
                    authors='; '.join(fields['authors']),year=str(fields['year']) if fields['year'] is not None else '',
                    journal_or_source=fields['source'] or '')
                verified=[r for r in aliases if r['paper_id']==pid]
                for scheme,field in IDENTIFIERS.items():
                    values=sorted({r['normalized_value'] for r in verified if r['scheme']==scheme})
                    if len(values)==1: record[field]=values[0]
                if record['doi']: record['url']='https://doi.org/'+record['doi']
                record['corpustrail_identifiers']=canonical([{'scheme':r['scheme'],'value':r['normalized_value']} for r in verified])
                records.append(record)
                lineage.append({'paper_id':pid,'membership_event_id':current['current_event_id'],
                    'record_sha256':content_hash(record),'metadata':metadata,'verified_identifiers':verified})
            membership={'states':states,'sha256':content_hash(states),
                'semantics':'current_authoritative_event_projection_not_retrospective_time_query',
                'frozen_at':created_at}
            database_snapshot={'schema_family':'corpustrail-standalone/v2','path':config['database'],
                'schema_versions':versions,'membership_sha256':membership['sha256'],
                'verified_aliases_sha256':content_hash(aliases),'selected_metadata_sha256':content_hash(lineage)}
            database_snapshot['snapshot_sha256']=content_hash(database_snapshot)
            bootstrap_sha=db.execute('SELECT bootstrap_sha256 FROM ct_project_identity WHERE singleton=1').fetchone()[0]
            snapshot={'schema_version':SNAPSHOT_SCHEMA,'export_id':export_id,'created_at':created_at,
                'project_id':config['project_id'],'project_bootstrap_sha256':bootstrap_sha,
                'configuration':{'event_id':config_id,'sha256':content_hash(config),'config':config},
                'database_snapshot':database_snapshot,'corpus_snapshot_id':'corpus:'+database_snapshot['snapshot_sha256'][7:],
                'membership_snapshot':membership,'membership_counts':counts,'selection_rule':SELECTION_RULE,
                'format':FORMAT,'field_mapping':FIELD_MAPPING,'fields':list(FIELDS),'label_policy':'none','automatic_seeds':False,
                'asreview_compatibility':{'format_contract':'ASReview tabular bibliography','tested_version':'2.2',
                    'result_mapping_version_spec':ASREVIEW_VERSION_SPEC,'integration_required':False},
                'software':{'version':__version__,'commit':software_commit,
                    'commit_provenance':'caller_declared' if software_commit else 'unknown_not_inferred_from_project_directory',
                    'implementation_sha256':digest_bytes(Path(__file__).read_bytes())},
                'population_sha256':content_hash([r['corpustrail_paper_id'] for r in records]),'records':records,'lineage':lineage}
            snapshot['snapshot_sha256']=content_hash(snapshot)
            return snapshot

    def preview(self):
        snapshot=self._freeze('preview')
        records=snapshot['records']
        return {'selection_rule':SELECTION_RULE,'target_format':FORMAT,'records':len(records),
            'membership_counts':snapshot['membership_counts'],'missing_title':sum(not r['title'].strip() for r in records),
            'missing_abstract':sum(not r['abstract'].strip() for r in records),
            'doi_present':sum(bool(r['doi']) for r in records),'doi_missing':sum(not r['doi'] for r in records),
            'missing_title_and_abstract':sum(not r['title'].strip() and not r['abstract'].strip() for r in records),
            'duplicate_identity_safety':'exact_unique_canonical_ids_and_verified_identifier_owners',
            'label_policy':'none','automatic_seeds':False,'side_effects':'none'}

    def plan(self,export_id,**kwargs):
        snapshot=self._freeze(export_id,**kwargs); validate_snapshot(snapshot)
        return snapshot

    def write_snapshot(self,snapshot,out):
        validate_snapshot(snapshot); self._project_guard(snapshot)
        target=confined(self.project.root,out)
        _write_bytes(target,_bytes(snapshot))
        return {'snapshot_sha256':snapshot['snapshot_sha256'],'output':out}

    def _project_guard(self,snapshot):
        with connection(self.project.database_path) as db:
            marker=db.execute('SELECT * FROM ct_project_identity WHERE singleton=1').fetchone()
        if snapshot['project_id']!=marker['project_id'] or snapshot['project_bootstrap_sha256']!=marker['bootstrap_sha256']:
            raise ContractError('export snapshot belongs to a different project')

    def _export_path(self,export_id):
        return confined(self.project.root,self.project.config.data_directory+'/asreview/exports/'+_name(export_id))

    def create(self,snapshot):
        body,sidecar=render_export(snapshot)
        self._project_guard(snapshot)
        directory=self._export_path(snapshot['export_id'])
        if directory.exists():
            old=self.inspect(snapshot['export_id'])
            if old!=sidecar:
                raise FileExistsError('export ID already belongs to another snapshot; never clobber')
            return {'export':old,'paths':self._paths(directory),'reused':True}
        directory.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        directory.mkdir(mode=0o700)  # Exclusive ID reservation; never rename over a target.
        # Interrupted multi-file publication is retained, not silently repaired/deleted.
        _write_bytes(directory/'snapshot.json',_bytes(snapshot))
        _write_bytes(directory/'dataset.csv',body)
        _write_bytes(directory/'export.json',_bytes(sidecar))
        verified=self.inspect(snapshot['export_id'])
        return {'export':verified,'paths':self._paths(directory),'reused':False}

    def _paths(self,directory):
        return {name:(directory/name).relative_to(self.project.root).as_posix()
                for name in ('snapshot.json','dataset.csv','export.json')}

    def inspect(self,export_id):
        directory=self._export_path(export_id)
        sidecar=_load(directory/'export.json')
        raw={k:v for k,v in sidecar.items() if k!='sidecar_sha256'}
        if sidecar.get('schema_version')!=EXPORT_SCHEMA or content_hash(raw)!=sidecar.get('sidecar_sha256'):
            raise ContractError('export schema/hash mismatch')
        self._project_guard(sidecar['snapshot'])
        expected,regenerated=render_export(sidecar['snapshot'])
        if (sidecar!=regenerated or sidecar['export_id']!=export_id or
                (directory/'dataset.csv').read_bytes()!=expected or _load(directory/'snapshot.json')!=sidecar['snapshot']):
            raise ContractError('export artifacts do not match frozen snapshot')
        return sidecar

    def create_from_path(self,path):
        return self.create(_load(confined(self.project.root,path)))

    def mapping(self,review_id,mapping_id):
        directory=confined(self.project.root,self.project.config.data_directory+'/asreview/downstream/'+_name(review_id))
        value=_load(directory/(_name(mapping_id)+'.json'))
        body={k:v for k,v in value.items() if k!='mapping_sha256'}
        if (value.get('schema_version')!=MAPPING_SCHEMA or content_hash(body)!=value.get('mapping_sha256') or
                value.get('review_id')!=review_id or value.get('mapping_id')!=mapping_id or
                value.get('label_semantics')!=LABEL_SEMANTICS or
                any(value.get(k) is not False for k in ('corpus_membership_changes','authority_changes','asreview_state_changes'))):
            raise ContractError('downstream mapping identity/hash/semantics mismatch')
        binding=_load(directory/'review.json')
        if any(value.get(k)!=v for k,v in binding.items() if k!='schema_version'):
            raise ContractError('downstream review binding mismatch')
        exported=self.inspect(value['export_id'])
        if value['snapshot_sha256']!=exported['snapshot']['snapshot_sha256']:
            raise ContractError('downstream source snapshot mismatch')
        records=value.get('records',[])
        if (value.get('dataset_sha256')!=exported['dataset_sha256'] or
                value.get('sidecar_sha256')!=exported['sidecar_sha256'] or
                [r.get('paper_id') for r in records]!=[r['corpustrail_paper_id'] for r in exported['snapshot']['records']] or
                any(r.get('authority')!='none' or r.get('identity_method')!='exact_exported_corpustrail_paper_id' or
                    (r.get('question_specific_label') is not None and type(r.get('question_specific_label')) is not int) or
                    r.get('question_specific_label') not in (None,0,1) for r in records)):
            raise ContractError('downstream mapping population/provenance mismatch')
        return value

    def map_results(self,export_id,*,results,review_id,question_id,mapping_id,
                    asreview_version,created_at=None):
        """Exact exported IDs, not row positions/titles; stores downstream-only observations."""
        for value in (review_id,question_id,mapping_id):_name(value)
        match=re.fullmatch(r'2\.(\d+)(?:\.\d+)?',asreview_version)
        if match is None or int(match.group(1))<2:
            raise ContractError('v0 result mapping requires an explicitly declared ASReview >=2.2,<3 version')
        created_at=created_at or now(); timestamp(created_at)
        exported=self.inspect(export_id)
        source_path=Path(results)
        if not source_path.is_absolute():source_path=confined(self.project.root,source_path.as_posix())
        source_bytes=source_path.read_bytes(); headers,rows=_csv_rows(source_bytes)
        if not {'corpustrail_paper_id','asreview_label'}.issubset(headers):
            raise ContractError('results must preserve corpustrail_paper_id and asreview_label')
        expected={r['corpustrail_paper_id']:r for r in exported['snapshot']['records']}
        seen=set(); mapped=[]
        for row in rows:
            pid=row['corpustrail_paper_id']
            if pid not in expected or pid in seen:
                raise ContractError('unknown or duplicate result paper_id')
            seen.add(pid)
            for field in ('title','doi'):
                if field in row and row[field]!=expected[pid][field]:
                    raise ContractError('result bibliographic identity guard mismatch')
            raw=row['asreview_label'].strip()
            if raw not in {'','-1','-1.0','0','0.0','1','1.0'}:
                raise ContractError('invalid downstream question-specific ASReview label')
            label=None if raw in {'','-1','-1.0'} else int(float(raw))
            mapped.append({'paper_id':pid,'question_specific_label':label,'original_label':row['asreview_label'],
                'authority':'none','identity_method':'exact_exported_corpustrail_paper_id'})
        if seen!=set(expected):
            raise ContractError('results must contain the complete frozen export; no partial or title-only joins')
        binding={'schema_version':'corpustrail-downstream-review-binding/v0','project_id':exported['project_id'],
            'review_id':review_id,'question_id':question_id,'export_id':export_id,
            'snapshot_sha256':exported['snapshot']['snapshot_sha256'],'label_semantics':LABEL_SEMANTICS}
        result={'schema_version':MAPPING_SCHEMA,'mapping_id':mapping_id,'created_at':created_at,**binding,
            'dataset_sha256':exported['dataset_sha256'],'sidecar_sha256':exported['sidecar_sha256'],
            'results_sha256':digest_bytes(source_bytes),'asreview_version':asreview_version,
            'corpus_membership_changes':False,'authority_changes':False,'asreview_state_changes':False,
            'records':sorted(mapped,key=lambda r:r['paper_id'])}
        result['schema_version']=MAPPING_SCHEMA; result['mapping_sha256']=content_hash(result)
        directory=confined(self.project.root,self.project.config.data_directory+'/asreview/downstream/'+review_id)
        target=directory/(mapping_id+'.json'); binding_path=directory/'review.json'
        if binding_path.exists() and _load(binding_path)!=binding:
            raise ContractError('downstream review ID already bound to another question/export')
        if not binding_path.exists():
            try:_write_bytes(binding_path,_bytes(binding))
            except FileExistsError:
                if _load(binding_path)!=binding:raise ContractError('concurrent downstream binding mismatch')
        if target.exists():
            if target.read_bytes()!=_bytes(result):
                raise FileExistsError('mapping ID already exists; append a new mapping, never overwrite')
        else:_write_bytes(target,_bytes(result))
        return result
