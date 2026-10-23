"""Local RIS forms and confined uploads; no arbitrary filesystem-read endpoint."""
import base64
import binascii
from contextlib import closing
import hashlib
import os
import re

from corpustrail._internal.values import content_hash

from corpustrail._internal.values import ContractError
from corpustrail.application import _workflow_files as files
from corpustrail.application.project_use import no_links
from corpustrail.imports.ris import MAX_BYTES
from corpustrail.imports.service import RISService, SCHEMA
from corpustrail.populations.contracts import command_id, page


class RISController:
    def upload(self, project, *, request_id, offset, body, final, sha256, filename):
        command_id(request_id)
        if (type(offset) is not int or offset<0 or type(final) is not bool or not isinstance(sha256,str)
                or not re.fullmatch('sha256:[0-9a-f]{64}',sha256)
                or not isinstance(filename,str) or not 1<=len(filename)<=180
                or any(c in filename for c in '/\\\x00\r\n')):raise ContractError('Invalid RIS upload form.')
        try:raw=base64.b64decode(body,validate=True)
        except (ValueError,TypeError,binascii.Error) as error:raise ContractError('Invalid RIS upload encoding.') from error
        if len(raw)>32768 or offset+len(raw)>MAX_BYTES:raise ContractError('RIS upload exceeds the documented 4 MiB budget.')
        service=RISService(project);path=no_links(service.root/'source-files'/(request_id+'.ris'),missing=True)
        with closing(files.operation_lease(project,'ris-upload')):
            complete=service.path('uploads',request_id)
            identity=no_links(service.root/'upload-requests'/(request_id+'.json'),missing=True)
            files.publish(identity,{'sha256':sha256,'filename':filename})
            if complete.exists():
                value=files.read(complete)
                if (value['sha256'],value['filename'])!=(sha256,filename):raise ContractError('Upload identity belongs to different bytes.')
                if offset+len(raw)>value['bytes']:raise ContractError('Completed RIS upload retry exceeds the preserved source.')
                with path.open('rb') as source:source.seek(offset);previous=source.read(len(raw))
                if previous!=raw:raise ContractError('Completed RIS upload retry differs from preserved bytes.')
                return {'schema':SCHEMA,'id':request_id,'complete':True,'bytes':value['bytes']}
            path.parent.mkdir(parents=True,exist_ok=True);size=path.stat().st_size if path.exists() else 0
            if offset<size:
                with path.open('rb') as f:f.seek(offset);saved=f.read(len(raw))
                if offset+len(raw)>size or saved!=raw:raise ContractError('Conflicting RIS upload retry.')
            elif offset==size:
                with path.open('ab' if path.exists() else 'xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            else:raise ContractError('RIS upload offset does not follow saved bytes.')
            size=path.stat().st_size
            if final:
                with path.open('rb') as f:digest='sha256:'+hashlib.file_digest(f,'sha256').hexdigest()
                if digest!=sha256:raise ContractError('RIS upload digest mismatch; original received bytes retained, not imported.')
                files.publish(complete,{'path':path.relative_to(project.root).as_posix(),'sha256':digest,'filename':filename,'bytes':size})
            return {'schema':SCHEMA,'id':request_id,'complete':final,'bytes':size}

    def command(self, project, action, body):
        service=RISService(project)
        if action=='upload':return self.upload(project,**body)
        if action=='preview':return service.prepare_import(**body)
        if action=='commit':return service.commit_import(**body)
        if action=='export-preview':
            value=service.export_preview(**body)
            return self.export_summary(value)
        if action=='export-commit':
            value=service.export_commit(**body)
            return self.export_summary(value)|{'id':body['key']}
        raise ContractError('Unsupported RIS command.')

    @staticmethod
    def export_summary(value):
        return {k:value[k] for k in ('schema','scope','actor','version_id','record_count','abstracts','bytes','sha256','preview_sha256','label_policy')}

    def history(self,project,*,offset=0,limit=20,revision=None):
        page(offset,limit);service=RISService(project);items=[]
        for kind in ('prepared','exports'):
            directory=no_links(service.root/kind,missing=True)
            if directory.exists():
                for path in directory.glob('*.json'):
                    r=files.read(path)
                    items.append({'id':path.stem,'kind':r['kind'],'created_at':r['created_at'],'name':r.get('name',r.get('scope')),
                        'source_sha256':r.get('source_sha256',r.get('sha256')),'records':r.get('records') if kind=='prepared' else r['record_count'],'record_count_known':r.get('record_count_known',True)})
        items.sort(key=lambda r:(r['created_at'],r['id']),reverse=True)
        state=content_hash(items)
        if offset and revision!=state:raise ContractError('RIS history changed; start again from its first page.')
        return {'schema':SCHEMA,'revision':state,'items':items[offset:offset+limit],'total':len(items),
                'next_offset':offset+limit if offset+limit<len(items) else None}
