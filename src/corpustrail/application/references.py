"""Bounded operational DTOs; never used by method-blind review endpoints."""
from pathlib import Path
import re

from corpustrail._internal.database import connection,latest_config
from corpustrail._internal.values import ContractError,now,content_hash
from corpustrail.curation.service import membership_in_connection
from corpustrail.populations.contracts import command_id,page
from corpustrail.project import Project
from corpustrail.references import ContextStrategy
from corpustrail.references.service import definition
from .project_use import no_links
from .projects import ProjectCommandError,ProjectController
from corpustrail.models.contracts import safe_data
from .reads import _paper_id

SCHEMA='corpustrail-local-references/v1'


def handle(value,namespace):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ContractError('choose a saved reference item')
    return namespace+':'+value


def bounded_context(value):
    result={k:v for k,v in value.items() if k not in {'decision_chunk_hashes','held_out_paper_ids','request_sha256'}}
    if 'held_out_paper_ids' in value:
        result['held_out_count']=len(value['held_out_paper_ids']);result['held_out_sha256']=content_hash(value['held_out_paper_ids'])
    return result


class ReferenceController:
    def configuration(self,project):
        with connection(project.database_path) as db:
            revision,config=latest_config(db)
        return {'schema':SCHEMA,'available':project.references.ready(),'project_id':config['project_id'],
            'config_event_id':revision,'definition':definition(config),'suggested_time':now(),
            'production_imports_available':False,'engines_available':False}

    def paper(self,project,paper_handle):
        with connection(project.database_path) as db:
            pid=_paper_id(paper_handle);project.populations._identity(db,pid)
            current=membership_in_connection(db,pid)
            return {'paper_id':pid,'source_event_id':current['current_event_id'],'state':current['state'],
                'notice':'Using a current decision as a reference requires a separate explicit human attestation.'}

    def contexts(self,project,**paging):
        value=project.references.contexts(**paging)
        return {**value,'items':[bounded_context(v) for v in value['items']]}

    def context(self,project,cid,**paging):
        return bounded_context(project.references.context(cid,**paging))

    def command(self,project,action,body):
        try:
            safe_data(body,secrets=ProjectController._secrets(project.config))
            if action=='upgrade':
                if set(body)!={'request_id','confirm_backup','project_id','config_event_id'} or body['confirm_backup'] is not True:
                    raise ContractError('explicitly confirm the backed-up reference storage upgrade')
                command_id(body['request_id']);configuration=self.configuration(project)
                if body['project_id']!=configuration['project_id'] or body['config_event_id']!=configuration['config_event_id']:
                    raise ContractError('project selection or configuration changed; reopen References before upgrading')
                if configuration['available']:return {'schema':SCHEMA,'available':True,'already_enabled':True}
                no_links(project.root)
                relative=project.config.data_directory+'/reference-upgrades/'+body['request_id']+'.sqlite3'
                no_links(project.root/Path(relative),missing=True)
                Project.upgrade(project.root,backup=relative,expected_config_event=body['config_event_id'])
                return {'schema':SCHEMA,'available':True,'backup_created':True}
            if action=='verify':
                if set(body)!={'version_id'}:raise ContractError('choose a reference version to verify')
                return {'schema':SCHEMA,**project.references.verify(body['version_id'])}
            if action in {'context_preview','context_commit'}:
                fields={'request_id','version_id','actor','created_at','config_event_id','target_paper_id','target_basis','held_out_paper_ids','strategy','dependency_ids','held_out_population_version'}
                if action=='context_commit':fields.add('expected_preview_sha256')
                if set(body)!=fields or body['dependency_ids']!=[]:raise ContractError('unsupported context form fields; derived registration is a scientific API interface only')
                body={**body,'strategy':ContextStrategy(**body['strategy'])}
                operation=project.references.prepare_context if action=='context_preview' else project.references.commit_context
                return {'schema':SCHEMA,**bounded_context(operation(**body))}
            fields={'request_id','name','actor','parent','changes','config_event_id','created_at'}
            if action=='commit':fields.add('expected_preview_sha256')
            elif action!='preview':raise ContractError('unsupported reference operation')
            if set(body)!=fields or not isinstance(body['changes'],list) or not 1<=len(body['changes'])<=20:
                raise ContractError('choose 1–20 staged changes per browser batch; collections have no item cap')
            for value in body['changes']:
                if not isinstance(value,dict):raise ContractError('each staged change must be a structured operation')
                if value.get('action')=='assign' and (value.get('producer')!={'type':'human','id':body['actor'],'version':'manual/v1'} or value.get('human_attested') is not True):
                    raise ContractError('explicitly attest your staged human reference labels')
            operation=project.references.preview if action=='preview' else project.references.commit
            return {'schema':SCHEMA,'reference':operation(**body)}
        except (ContractError,TypeError,ValueError) as error:
            if isinstance(error,ContractError):message=str(error)
            else:message='Unsupported reference form fields or types; no automatic retry occurred.'
            raise ProjectCommandError(message,code='reference_conflict',status=409) from error
