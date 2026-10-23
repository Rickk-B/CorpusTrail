"""Fresh, scoped RIS demonstration. Entirely synthetic; no human decisions seeded."""
import argparse
from importlib.resources import files
import json
import uuid

from corpustrail.application.ris import RISController
from corpustrail.imports.service import RISService
from corpustrail.project import Project, ProjectConfig, ReviewPolicy
from corpustrail._internal.values import digest_bytes


def create(root):
    project=Project.create(root,ProjectConfig('offline-demo-'+uuid.uuid4().hex,'Offline RIS demonstration',
        'Clearly synthetic materials-sensor papers; software evaluation only.',
        review=ReviewPolicy(scope='Synthetic materials-sensor literature for software evaluation. Include relevant measurement or methods papers; missing evidence is not exclusion.',
                            authorized_reviewers=('demo_reviewer',))),created_by='demo_creator')
    body=files('corpustrail.resources').joinpath('ris-demo-initial.ris').read_bytes()
    controller=RISController();upload=uuid.uuid4().hex
    import base64
    controller.upload(project,request_id=upload,offset=0,body=base64.b64encode(body).decode(),final=True,sha256=digest_bytes(body),filename='ris-demo-initial.ris')
    service=RISService(project);key=uuid.uuid4().hex
    prepared=service.prepare_import(request_id=key,upload=upload,actor='demo_creator',name='Synthetic starting candidates')
    result=service.commit_import(key=key,preview_sha256=prepared['preview_sha256'],confirmed=True)
    while result['status']!='complete':result=service.commit_import(key=key,preview_sha256=prepared['preview_sha256'],confirmed=True)
    ids=project.identities.papers()
    for pid in ids:
        title=project.discovery.metadata(pid)['fields']['title']
        if title=='Synthetic sensor measurement':
            xml=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/ris.demo.1</article-id></article-meta></front><body><sec><title>Methods</title><p>This invented experiment is demonstration text, not scientific evidence.</p></sec></body></article>'
            project.evidence.preserve_document(pid,xml,representation='jats_xml',media_type='application/xml',source_uri='fixture://ris-demo/verified',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='1')
        elif title=='Synthetic metadata-only methods':
            project.evidence.preserve_document(pid,b'%PDF-1.4\nSynthetic pending material',representation='pdf',media_type='application/pdf',source_uri='fixture://ris-demo/pending',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='1')
    return {'project':str(project.root),'synthetic':True,'network_used':False,'reviewer':'demo_reviewer',
            'canonical_candidates':len(ids),'human_observations':0,'membership_decisions':0,
            'next':'Launch corpustrail app with this project, then Research tools → RIS exchange to import the supplied sample.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project')
    args=parser.parse_args()
    from corpustrail.application.project_use import creation_use
    with creation_use(args.project):print(json.dumps(create(args.project),indent=2))
