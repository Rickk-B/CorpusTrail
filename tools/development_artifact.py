"""CI-only development-wheel receipt. Never changes package/scientific state."""

import argparse
import ast
from datetime import datetime, timezone
import email
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = {'corpustrail/local_app/assets/index.html',
            'corpustrail/local_app/assets/home.html',
            'corpustrail/local_app/assets/app.css', 'corpustrail/local_app/assets/app.js'}
FRONTEND.update({'corpustrail/local_app/assets/discovery.html', 'corpustrail/local_app/assets/discovery.js'})
FRONTEND.add('corpustrail/local_app/assets/evidence.js')
FRONTEND.update({'corpustrail/local_app/assets/review.html', 'corpustrail/local_app/assets/review.js'})
FRONTEND.update({'corpustrail/local_app/assets/populations.html', 'corpustrail/local_app/assets/populations.js'})
FRONTEND.update({'corpustrail/local_app/assets/references.html', 'corpustrail/local_app/assets/references.js'})
FRONTEND.update({'corpustrail/local_app/assets/curation.html', 'corpustrail/local_app/assets/curation.js'})
FRONTEND.update({'corpustrail/local_app/assets/handoff.html', 'corpustrail/local_app/assets/handoff.js'})
FRONTEND.update({'corpustrail/local_app/assets/ris.html','corpustrail/local_app/assets/ris.js'})
FRONTEND.update({'corpustrail/local_app/assets/chatgpt.html','corpustrail/local_app/assets/chatgpt.js'})
# Explicitly reviewed presentation boundary, not permission for scientific changes.
PRESENTATION_PATHS = {'src/' + name for name in FRONTEND} | {'src/corpustrail/application/reads.py'}
# Checkpoint 2 delegates writes to unchanged scientific/configuration services.
CHECKPOINT2_PATHS = {
    'src/corpustrail/application/projects.py', 'src/corpustrail/cli.py',
    'src/corpustrail/local_app/server.py', 'src/corpustrail/local_app/__init__.py',
    'src/corpustrail/local_app/assets/index.html', 'src/corpustrail/local_app/assets/app.js',
    'src/corpustrail/local_app/assets/app.css', 'src/corpustrail/local_app/assets/projects.html',
    'src/corpustrail/local_app/assets/projects.js'}
CHECKPOINT2_PATHS.add('src/corpustrail/local_app/assets/home.html')
CHECKPOINT2_PATHS.update({'src/corpustrail/application/project_use.py', 'src/corpustrail/application/trash.py',
                         'src/corpustrail/_internal/loopback_http.py',
                         'src/corpustrail/curation/http.py', 'src/corpustrail/tutorial.py'})
CHECKPOINT3_PATHS = {'src/corpustrail/application/discovery.py', 'src/corpustrail/application/_workflow_files.py',
                    'src/corpustrail/discovery/service.py', 'src/corpustrail/providers/metadata.py',
                    'src/corpustrail/local_app/assets/discovery.html', 'src/corpustrail/local_app/assets/discovery.js'}
CHECKPOINT4_PATHS = {'src/corpustrail/application/evidence.py', 'src/corpustrail/evidence/service.py',
                    'src/corpustrail/local_app/assets/evidence.js'}
# Frozen reviewed implementation, not approval for arbitrary scientific changes.
# A future core edit needs a new explicitly reviewed receipt and tests.
XML_COMPATIBILITY_COMMIT = '6b964bc660676935bff249b462ab242b837202d1'
XML_COMPATIBILITY_HASHES = {
    'src/corpustrail/_internal/xml_safety.py': '23704b9d56723ed244d30b0fc16a1a66e01a28a571cdd875d120fb8a594b7eae',
    'src/corpustrail/evidence/native_parsers.py': '3440d2b07df9cf7935f5a6099ad9a6b281cf0b7cbfa3894792ee36f2ef3d284e',
    'src/corpustrail/evidence/service.py': '70c7fc643af9ebcb1613f577ba7a627af9c22c838125475ef09ba6a2d6770305',
    'src/corpustrail/application/evidence.py': '76e5e29c81a77b7a66b3c8f0b7a4922d8592b550a7262c4013e047cb862854a7',
    'src/corpustrail/resources/origins.json': '0bf601fb89fd7b1d85d8e57e64d308a18696558e38db91369e9b8ec613f50829'}
XML_COMPATIBILITY_EXTRA_PATHS = set(XML_COMPATIBILITY_HASHES) - CHECKPOINT4_PATHS
# New scientific lifecycle is an explicitly versioned, frozen boundary; not a
# broad allowance for changing historical review authority or evidence policy.
GUIDED_REVIEW_COMMIT = '05437f6d23c0c56855183b29903bf87f3a9cfff3'
GUIDED_REVIEW_HASHES = {
    'src/corpustrail/curation/sessions.py': '2e5f350763e353b1ef7cb567df83fb9f3b655df6275421faf2d7d0c804f8908e',
    'src/corpustrail/curation/guided.py': '4868325dbb8e5e456d525d68346cc0b968d4c6439929697b5cf8c3a991e462f8',
    'src/corpustrail/application/review.py': 'b8f56e7d64735563c284a5c1d8d02a2a4d83321fdce8e84b001ad2037e9dceff'}
GUIDED_REVIEW_ASSETS = {'src/corpustrail/local_app/assets/review.html', 'src/corpustrail/local_app/assets/review.js'}
# Checkpoint 6's additive schema and narrow existing-service integration are
# frozen separately. Historical authority, XML and renderer boundaries remain.
POPULATION_COMMIT = '9ab5ebfad2091cbe65b95cae00ce8bb10df51f1e'
POPULATION_HASHES = {
    'src/corpustrail/populations/__init__.py': '145dd5bda53d53ebe63688b0367991fb946bd637386a2581e27d4f62cca1c9b3',
    'src/corpustrail/populations/contracts.py': '496158f1c4c37ffff510d598cfff07956147c9da38762e8629216ff91008da4f',
    'src/corpustrail/populations/service.py': '218a0c2d89d72e3bb30d97de4fc78d2ab2a4f8a9a9399532f4d8e145f57fd99b',
    'src/corpustrail/application/populations.py': 'ff0ec2ee2500cfe576f756fdae8d2045c2fd585325d0a008dda7d48970296837',
    'src/corpustrail/application/review.py': 'cd233adcb261abbff7c1c47387236450172ae2d34f71dab3f1e969e4f3ee4f27',
    'src/corpustrail/curation/guided.py': 'ae396145df9e27a9472ac7074495b8639555a2c0e98dd71aac0f7acbae7e625f',
    'src/corpustrail/_internal/database.py': '475407a624bd658b137edefd6fe6840a29abc71ce4b912ae8e31a96a1077479f',
    'src/corpustrail/project/service.py': 'b29af05e5ab4d06eaec6783f67ec3cf491e6bc855a8a7d4eed6ef3c706d5a194',
    'src/corpustrail/operational/schema/038_candidate_populations.sql': '2994a7ebbb615febd6137ab29c9d97e3012b38dd5003a668769ebf979e7c1242',
    'src/corpustrail/operational/schema_manifest.json': 'b11e186a2736f509f7fc567f4dd688ff3a9cd5f4219b3677b779c27deb8a6a64'}
# CP7 is a new reviewed scientific boundary, not a broad override of CP1–6.
REFERENCE_COMMIT = '5b2e603fdf4825502c89cd22edc670531a27728e'
REFERENCE_HASHES = {
    'src/corpustrail/references/__init__.py': 'b341b07854df3b1d6af6eaca360851bbd5c07de26f45448db3a94fb82efd833e',
    'src/corpustrail/references/context.py': '40a03313d722bded22a98af0593ceb6efdf6e9cfccaa6e5bfadceeadff60f204',
    'src/corpustrail/references/contracts.py': 'f89d415f2598d3f54eae004156f034774589f30470901be9c9bf658fb84c75f4',
    'src/corpustrail/references/evidence.py': '849802da896427a5c98cec344f7ef99bb143268f9a44db3d9da155411644bb70',
    'src/corpustrail/references/service.py': '938a75274f55975bfd241fbb29a4cf75ef19a058755501b32e5c5e900fa82b2d',
    'src/corpustrail/references/storage.py': 'a7493eaf5bb385550c427c7794cc5973ca28f6c8c2ec690e4fb53c2a89325b12',
    'src/corpustrail/application/references.py': 'b711214a3afec322a5f8dd287ddf14d18ebae7f78b3df9b24cb32e3ec3acbf12',
    'src/corpustrail/operational/schema/039_reference_collections.sql': 'bc48d9c686705dabfec0b00922571541dd0abf241bc480f74af67b3101f9bace',
    'src/corpustrail/operational/schema_manifest.json': '0a59b4b011019c10f24aac6c6cf7de91ae47b72c18d7ba1a3734f5cb8f152f12',
    'src/corpustrail/project/service.py': '6ece7df51295f150b94cf7ee1b1b1899f423f014b2ff82d3a4d4c268b1c623cb',
    'src/corpustrail/_internal/database.py': '8712383fcba6c5be8544e206a03d7876bf44c3443dece87be8a1c06e53f4198d'}
# CP8 freezes its additive implementation independently. Earlier migration and
# review/reference bytes remain checked against their historical commits below.
CLASSIFICATION_COMMIT = 'e81366d007ab44595880e47d340016b59e76e07a'
CLASSIFICATION_HASHES = {
    'src/corpustrail/classification/__init__.py': '5d7387aa598078823c523ed5aa08d2c32c95a413914103a2bce4de370adc4566',
    'src/corpustrail/classification/contracts.py': 'e8dbe40f574b2a2f8850e37e9e46b3ae2241ddae1701dd6ea13ece8d2c7f20e2',
    'src/corpustrail/classification/inputs.py': '351fbf6dfcc7d95064f3073b7a1be978a86ad3106790e084d5d98758a577e599',
    'src/corpustrail/classification/registry.py': '33db203c45124a0f85078cd9923d93f7d96b0de447182b342bacb131921cfcb6',
    'src/corpustrail/classification/service.py': 'b5428ef150875dd0ad97495189bad08a3fe6b0087964b7148e0deb5461a8980c',
    'src/corpustrail/classification/storage.py': 'a4d6ffc00e475e3efd07ea63b75cc35a82faa3f4d3c85d705c37242a53cec4d8',
    'src/corpustrail/classification/validation.py': '2ed15fee344f62f4e88e2eab5ba8db96aa8f482d6688f2e9b3e811e17be4ae39',
    'src/corpustrail/references/context.py': 'f6cdfbd647f532854e3b992d3ade6294e33fe4b75f49856c8a9eb3b4f18713ab',
    'src/corpustrail/_internal/database.py': '83bc0e264ca00eb1c59405c99140cab7f62ee4d0c6ee78c34c0c1ffb505cfcc9',
    'src/corpustrail/project/service.py': '6acbd3f81f337f3badcd5bfe2f3da9ffc5cd2a44a97efac3c7ac883892261270',
    'src/corpustrail/application/project_use.py': 'f1ca74ed6e16c5594884f360fcadbb2157dc53ba0832fb07ed950ef9fdcbf064',
    'src/corpustrail/operational/schema_manifest.json': '0a1875d21a89a494a28a730326a72a8e7ddf1805cdd23e1b30a727af6471d231',
    'src/corpustrail/operational/schema/040_classifier_assessments.sql': '5194cf72c8ea2bfe72d87d456c84ce892efea00cf89b18318d897a4bf75a8fa1'}


# CP9 composes existing services in an explicit transaction and adds immutable
# audit/workflow lineage. Historical frozen hashes above remain verified.
CURATION_COMMIT = '29cc58e342d6f10b3c7edf778b4f24f4ff103bc2'
CURATION_HASHES = {
    'src/corpustrail/_internal/database.py': '9c55f03409d7a44a49481156c01518178875904a59d6db808e0dd69f62c56f77',
    'src/corpustrail/project/service.py': '4578ee3e59043d507a57cca7639f7d63ae99f4f2c58b5440397a0cbb9ca9a419',
    'src/corpustrail/operational/schema_manifest.json': 'bb6172a060e5fbd1a60629f244f3489ea71f41ce7d31f997d6b8ee33910d745c',
    'src/corpustrail/operational/schema/041_curation_audits.sql': '1b6149142f58530e769cb256df29a9c98651f663794bb67c362ed6096b42fd76',
    'src/corpustrail/references/service.py': '866b8ae2ed637810988468e0f7871e6be89dc062e67bb6edca245012e1342a5e',
    'src/corpustrail/curation/guided.py': '50f1828513738b4507dd4e8d99c93779b76c9104aa3ce3af848933ecd6b4da41',
    'src/corpustrail/application/review.py': '2431285f994f766f5777dd8515ca414330ab9b25547b2da048976a509e2e7a90',
    'src/corpustrail/classification/service.py': '04353fc123ed921b1750827a4a83ea1050951df4fb6be18638128d3ca0450a1c',
    'src/corpustrail/classification/curation.py': 'f5bc7f7b5b6c8c47e13ae7b8bc84a663c5ea4b64c6d0b51733f142f9bfca156e',
    'src/corpustrail/classification/curation_views.py': '4e7e02d7f70759af11a8a7c7353a7937288d8aed416effb04df3a39c158dbc5e',
    'src/corpustrail/application/curation.py': '2d40397873018a4a6648d27da5efca2d16c759d5eb76f7b34919dc039e13a96c',
    'src/corpustrail/local_app/server.py': '274ecb07c45473ca72294334f649a7f898266c68522a0a73a2699a7d0b104a18'}


# CP10 may change the HTTP presentation/composition boundary, not the CP9
# scientific implementation. No scientific/migration digest may be overridden.
HANDOFF_BASELINE = 'ad4a5496bea422c56cc8ea3cd512a0887ae442c1'
HANDOFF_COMMIT = '175f7b48478371bb8fb63ff58fe85b4457bcc307'
HANDOFF_HASHES = {
    'src/corpustrail/application/_workflow_files.py':'7b9e6fa277c6accc8060bec05ab6db753db86a72bc16a90e7e06179cb41741db',
    'src/corpustrail/application/handoff.py':'9ce8251567ea407ae0d44f0afd46fa03cded2b3c68a36090db134dca9356fa9e',
    'src/corpustrail/knowledge/service.py':'fb5d97391dec62c9bc7c4a1fba2ea3bd5e1d37a370ef347366733bea91bdb307',
    'src/corpustrail/knowledge/storage.py':'086c9ec62f0264f954009a590c96a8357a2d2dacd98b573baa159705dabff764',
    'src/corpustrail/local_app/assets/app.css':'0145071e25d42b37c5b06d1e8bec57141fc8a78c1a84318bc06f1e1026fcd88c',
    'src/corpustrail/local_app/assets/app.js':'1b785756ab7fe9ed622294efe67cb43bb7b3ce14075270eebdb8a26c5917aca7',
    'src/corpustrail/local_app/assets/curation.html':'3c98cf06b885852881e3d5b057b4939be73f47c93394b3cc031116c06f0ffda0',
    'src/corpustrail/local_app/assets/discovery.html':'045171ed593c2e7d9f635a3ad68b1f502d5358d727a835d6e339ccb77c5f6d12',
    'src/corpustrail/local_app/assets/discovery.js':'e389ffc260836424ed038e4343c7a9a463fadd42efa0515a4a69c9b30891b028',
    'src/corpustrail/local_app/assets/handoff.html':'887e226b9e28401cea7dbacfe7b7cf6cce47321fb59f95c5957edc50297f9887',
    'src/corpustrail/local_app/assets/handoff.js':'c9fa1152b5aa08570c94da549e1f84f693bd549208b3e89753851b35d0f8717f',
    'src/corpustrail/local_app/assets/home.html':'b753d4d9438dc5fdbf0337c6cbc97e7ccb3dffb4c86b0f8d2568e4870455585d',
    'src/corpustrail/local_app/assets/index.html':'0bf15e2aebe14d770ad531dc1611b763b0438e288578e12acbf3896334c8a69c',
    'src/corpustrail/local_app/assets/populations.html':'623993339f59b2a6c954fa9c58a726a7e0230949ae9b9623792e2e759428221d',
    'src/corpustrail/local_app/assets/projects.html':'724959c01236401f4a8671b9eaabffe01ee84a9d5353f9b9abee39c7c203f2d1',
    'src/corpustrail/local_app/assets/projects.js':'40fc01b2e4882ab4c7a436f02e1a6ec68c14c38329dc87b92f20b7573dbf64e1',
    'src/corpustrail/local_app/assets/references.html':'b5849dc6547324bec71959e721daa5005f0c6012e5a714789f477ef565ed2275',
    'src/corpustrail/local_app/assets/review.html':'271921901cb30c32b9abade6bd11b4ffb5220ff95515a735447e73b0845a017c',
    'src/corpustrail/local_app/assets/review.js':'9248755f42946dc8113b14120aca43de960e30d77a78ab595b38daca726f4d86',
    'src/corpustrail/local_app/server.py':'7ec72eae556c9fb4d264222455dba5457b4ee1661b734efec3d1e4c94829813b'}
HANDOFF_HTTP = 'src/corpustrail/local_app/server.py'
HANDOFF_READ_SUPPORT = {'src/corpustrail/knowledge/service.py', 'src/corpustrail/knowledge/storage.py',
    'src/corpustrail/application/_workflow_files.py', 'src/corpustrail/application/handoff.py'}



# Separately authorized post-alpha RIS/demo boundary; all CP1–10 receipts remain frozen.
RIS_BASELINE = 'f077bb7722ac2b6f3c911a434cb8a541dc8a5745'
RIS_COMMIT = 'f367af1a701f62e13c892e63f046695a0e95c32f'
RIS_PATHS = {'src/corpustrail/local_app/assets/home.html', 'src/corpustrail/resources/ris-demo-initial.ris', 'src/corpustrail/demo.py', 'src/corpustrail/imports/ris.py', 'src/corpustrail/resources/ris-demo-import.ris', 'src/corpustrail/imports/service.py', 'src/corpustrail/application/populations.py', 'src/corpustrail/cli.py', 'src/corpustrail/imports/__init__.py', 'src/corpustrail/application/ris.py', 'src/corpustrail/local_app/assets/ris.js', 'src/corpustrail/local_app/server.py', 'src/corpustrail/local_app/assets/populations.html', 'src/corpustrail/local_app/assets/ris.html', 'src/corpustrail/identity/service.py', 'src/corpustrail/local_app/assets/handoff.js'}
RIS_HASHES = {'src/corpustrail/application/populations.py': '279d738f347211cd52f933c27ecba8b1d5c004eedc4da15fc43ce3f2e18f6772', 'src/corpustrail/application/ris.py': '25ae3fbfa1d21869f673c3bedc4ee7e191cef807fadb4b34a64fb83b54128e55', 'src/corpustrail/cli.py': 'e4a826c1a07c63392c3a61e39ff0b1999374ae59bd9be478c5bc1a7fbd05392e', 'src/corpustrail/demo.py': 'a5154789f18d4d9c40a842eefd9afda0916255d8365194894f30992c72dcb446', 'src/corpustrail/identity/service.py': '5a20522b35605cdc3a4e31194993e324da399898f36a90dd29cedfdb312cc230', 'src/corpustrail/imports/__init__.py': '7dcbc87c8d2c13f928950ceea90fb3b19c34e0700fd40f13473f2148dc8e9348', 'src/corpustrail/imports/ris.py': '5c44ec245ff6a268664cffd7e86e418bf855fdeeef975de8cb8fb9f8d907a4e2', 'src/corpustrail/imports/service.py': '41a833d9b37e3ec570ca303a1372e0a85ce8946b5479639c598c0704e786df61', 'src/corpustrail/local_app/assets/handoff.js': 'a500659b416f0e68f30b01d04694a3ac3d4b334d82aa4fbe4875816c89e93f46', 'src/corpustrail/local_app/assets/home.html': '96502282c9aa55cd0c35a13736f9601769344f9e970936a4706826f2c5dc2a30', 'src/corpustrail/local_app/assets/populations.html': 'f88c7ebef6db1f1fd3fcdaae5c844def452b8abaaf3c9aea9f274270ff5eaeaf', 'src/corpustrail/local_app/assets/ris.html': 'e8f4564cfff4ff93b5f46b35545bfebe7ecd97961e858081624dfae909cae5e5', 'src/corpustrail/local_app/assets/ris.js': 'b9ca3f17f4f7243ad8647612fbd7117ea676143a28dad8e3c2526f1e8cf1fede', 'src/corpustrail/local_app/server.py': '804f6928423f18f1498a9acaaed9813ec319e817fd09043848a071527f1d3c21', 'src/corpustrail/resources/ris-demo-import.ris': '5ba4252a7919279c27e34bc7e80c41e6da79c8fc8f3a0dc69ec25e0815e44635', 'src/corpustrail/resources/ris-demo-initial.ris': 'c7485b3728602b93e2dcd58ac86d169f57b3ad4862a2c2987f061eaa7c20274f'}

def check_identity_composition(old, new):
    """Only factor the exact old transaction body; no identity-policy bypass."""
    import copy
    original=ast.parse(old);current=ast.parse(new)
    a=next(n for n in original.body if isinstance(n,ast.ClassDef) and n.name=='IdentityService')
    b=next(n for n in current.body if isinstance(n,ast.ClassDef) and n.name=='IdentityService')
    before={n.name:n for n in a.body if isinstance(n,ast.FunctionDef)}
    after={n.name:n for n in b.body if isinstance(n,ast.FunctionDef)}
    if set(after)!=set(before)|{'_apply'}:raise ValueError('RIS may only factor the existing identity transaction')
    expected=before['apply'].body[1].body+before['apply'].body[2:]
    if [ast.dump(n) for n in expected]!=[ast.dump(n) for n in after['_apply'].body[1:]]:
        raise ValueError('RIS changed native identity validation or approval guards')
    public=after['apply'];old_apply=before['apply']
    delegation=ast.parse('self._apply(db, plan, approve_new_identity=approve_new_identity, approve_aliases=approve_aliases)',mode='eval').body
    if (len(public.body)!=2 or not isinstance(public.body[1],ast.With)
            or ast.dump(public.body[1].items[0])!=ast.dump(old_apply.body[1].items[0])
            or len(public.body[1].body)!=1 or not isinstance(public.body[1].body[0],ast.Return)
            or ast.dump(public.body[1].body[0].value)!=ast.dump(delegation)):
        raise ValueError('RIS must preserve the public enrollment transaction and explicit approval flags')
    restored=copy.deepcopy(current)
    owner=next(n for n in restored.body if isinstance(n,ast.ClassDef) and n.name=='IdentityService')
    owner.body=[copy.deepcopy(old_apply) if isinstance(n,ast.FunctionDef) and n.name=='apply' else n
                for n in owner.body if not (isinstance(n,ast.FunctionDef) and n.name=='_apply')]
    if ast.dump(restored)!=ast.dump(original):raise ValueError('RIS changed identity behavior beyond transaction composition')


# Independently reviewed adapter extension; historical receipts stay immutable.
CHATGPT_BASELINE = '14443e5f790a317e22b62ecc09ecd862e5097684'
CHATGPT_COMMIT = '0000000000000000000000000000000000000000'
CHATGPT_PATHS = {
    'src/corpustrail/application/chatgpt.py',
    'src/corpustrail/application/curation.py',
    'src/corpustrail/chatgpt/__init__.py',
    'src/corpustrail/chatgpt/connection.py',
    'src/corpustrail/chatgpt/credentials.py',
    'src/corpustrail/chatgpt/engine.py',
    'src/corpustrail/chatgpt/transport.py',
    'src/corpustrail/classification/contracts.py',
    'src/corpustrail/classification/inputs.py',
    'src/corpustrail/classification/service.py',
    'src/corpustrail/local_app/assets/chatgpt.html',
    'src/corpustrail/local_app/assets/chatgpt.js',
    'src/corpustrail/local_app/assets/curation.js',
    'src/corpustrail/local_app/assets/handoff.js',
    'src/corpustrail/local_app/server.py',
}
CHATGPT_HASHES = {
    'src/corpustrail/application/chatgpt.py': '5e861c358818237e0c74c60f812aef3afe5193f74e0b75c3aedfee2568f5342b',
    'src/corpustrail/application/curation.py': '97e71eb8fe5e9cc61b1bb1ef7bcf8f554e984d75c56552b97ba1a534e62784c6',
    'src/corpustrail/chatgpt/__init__.py': '1c0d389d6e7df4e3a93d9870b5ddf690f1759fdb7f4e7710e91e679515df4591',
    'src/corpustrail/chatgpt/connection.py': 'e6021b86baf6cfe2a98f26ec89e9d3d68a79f1229dd96ce1782be89d21ea18c5',
    'src/corpustrail/chatgpt/credentials.py': '1fce99a2fd99f6ac363ac48406997ab954be64aad7ff7b05dba3d0103447856e',
    'src/corpustrail/chatgpt/engine.py': '20c4384d3e8462827e64771090d34c5ce4dfb2c0b06f2e1093d2f3b9a8c1e4a5',
    'src/corpustrail/chatgpt/transport.py': 'b7b3a3abaa3a323616e5c8f98f4319b28e8c5dcec6c4cbf405c46c8889aa2836',
    'src/corpustrail/classification/contracts.py': '9ef04c2c1f27911606d0885f6bf648664ac02e3d8f3a4acd5effc21002bb54d4',
    'src/corpustrail/classification/inputs.py': '6cb3d8f76478467436b634f3cff6ca79449293cca85b58a44eba04a222fd993b',
    'src/corpustrail/classification/service.py': '6e33792cc72b410ad31ff98c875c459fc56e900a86a15330f00919310aee9cc9',
    'src/corpustrail/local_app/assets/chatgpt.html': '03a6234888258965ef7a482451480c4744ee87346fa18dad92cf205a85b2330a',
    'src/corpustrail/local_app/assets/chatgpt.js': 'fd6625c26691c8f37e62ee887023a74eaf0e6682e85c21e50655d3f42649950a',
    'src/corpustrail/local_app/assets/curation.js': 'e98d1ad5625f09e7ed4f5336634b72040bb9f529e27cba5fd908f23f037c5e5e',
    'src/corpustrail/local_app/assets/handoff.js': '3a6dd2fb53df736d6145a976237e3d9045d3709fcd6a16432da789fbb3958cd8',
    'src/corpustrail/local_app/server.py': 'e77972eeb3f86e0c48d0b767e8e8f34e784e6e99ffe8e15ff6d475bc9c686b27',
}

def current_source_hash(name, historical, *, root=ROOT):
    # Called only after check_chatgpt in the artifact gate. Exact new hashes are
    # independently pinned; this does not alter any historical source receipt.
    return CHATGPT_HASHES.get(name, historical) if (root/'src/corpustrail/chatgpt/engine.py').is_file() else historical


def check_chatgpt(root, expected):
    fixed = {
        'src/corpustrail/application/chatgpt.py',
        'src/corpustrail/application/curation.py',
        'src/corpustrail/chatgpt/__init__.py',
        'src/corpustrail/chatgpt/connection.py',
        'src/corpustrail/chatgpt/credentials.py',
        'src/corpustrail/chatgpt/engine.py',
        'src/corpustrail/chatgpt/transport.py',
        'src/corpustrail/classification/contracts.py',
        'src/corpustrail/classification/inputs.py',
        'src/corpustrail/classification/service.py',
        'src/corpustrail/local_app/assets/chatgpt.html',
        'src/corpustrail/local_app/assets/chatgpt.js',
        'src/corpustrail/local_app/assets/curation.js',
        'src/corpustrail/local_app/assets/handoff.js',
        'src/corpustrail/local_app/server.py',
    }
    if CHATGPT_PATHS != fixed or set(CHATGPT_HASHES) != fixed:
        raise ValueError('ChatGPT cannot override other scientific services or frozen migrations')
    if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',CHATGPT_COMMIT,expected]).returncode:
        raise ValueError('ChatGPT must descend from its exact implementation')
    changed=set(git(root,'diff','--name-only',CHATGPT_BASELINE,CHATGPT_COMMIT,'--','src/corpustrail').splitlines())
    if changed != fixed: raise ValueError('ChatGPT receipt must cover its exact complete source delta')
    for name,wanted in CHATGPT_HASHES.items():
        path=root/name;frozen=subprocess.check_output(['git','-C',str(root),'show',CHATGPT_COMMIT+':'+name])
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=wanted or hashlib.sha256(frozen).hexdigest()!=wanted:
            raise ValueError('ChatGPT source differs from its exact implementation')
    name='src/corpustrail/classification/service.py'
    before=ast.parse(git(root,'show',CHATGPT_BASELINE+':'+name));after=ast.parse((root/name).read_text(encoding='utf-8'))
    def validator(tree):
        return next(n for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='ClassificationService'
                    for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='_validated_output')
    if ast.dump(validator(before)) != ast.dump(validator(after)):
        raise ValueError('ChatGPT may not change scientific outcome or sufficiency validation')
    name='src/corpustrail/classification/inputs.py'
    before=git(root,'show',CHATGPT_BASELINE+':'+name).split('    input_hashes = [];')[0]
    after=(root/name).read_text(encoding='utf-8').split('    input_hashes = [];')[0]
    if before != after: raise ValueError('ChatGPT may not change reference eligibility or held-out protections')


def check_ris(root, expected):
    fixed={'src/corpustrail/application/ris.py','src/corpustrail/cli.py','src/corpustrail/demo.py',
           'src/corpustrail/identity/service.py','src/corpustrail/imports/__init__.py',
           'src/corpustrail/imports/ris.py','src/corpustrail/imports/service.py',
           'src/corpustrail/local_app/assets/ris.html','src/corpustrail/local_app/assets/ris.js',
           'src/corpustrail/local_app/server.py','src/corpustrail/resources/ris-demo-import.ris',
           'src/corpustrail/resources/ris-demo-initial.ris',
           'src/corpustrail/application/populations.py','src/corpustrail/local_app/assets/home.html',
           'src/corpustrail/local_app/assets/populations.html','src/corpustrail/local_app/assets/handoff.js'}
    if set(RIS_HASHES)!=fixed or RIS_PATHS!=fixed or set(RIS_HASHES)&set(HANDOFF_HASHES)!={HANDOFF_HTTP,'src/corpustrail/local_app/assets/home.html','src/corpustrail/local_app/assets/populations.html','src/corpustrail/local_app/assets/handoff.js'}:
        raise ValueError('RIS cannot override other scientific services or frozen migrations')
    if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',RIS_COMMIT,expected]).returncode:
        raise ValueError('RIS delivery must descend from its exact reviewed implementation')
    changed=set(git(root,'diff','--name-only',RIS_BASELINE,RIS_COMMIT,'--','src/corpustrail').splitlines())
    if changed!=fixed:raise ValueError('RIS receipt must cover its exact complete source delta')
    for name,wanted in RIS_HASHES.items():
        path=root/name;frozen=subprocess.check_output(['git','-C',str(root),'show',RIS_COMMIT+':'+name])
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=current_source_hash(name,wanted,root=root) or hashlib.sha256(frozen).hexdigest()!=wanted:
            raise ValueError('RIS source differs from its exact reviewed implementation')
    name='src/corpustrail/identity/service.py'
    check_identity_composition(git(root,'show',RIS_BASELINE+':'+name),(root/name).read_text(encoding='utf-8'))
    name='src/corpustrail/application/populations.py'
    baseline=git(root,'show',RIS_BASELINE+':'+name)
    expected_population=baseline.replace("'production_imports_available': False","'production_imports_available': True, 'production_import_formats': ['ris']")
    if (root/name).read_text(encoding='utf-8').strip()!=expected_population.strip():
        raise ValueError('RIS may only update population capability metadata, not scientific operations')


def check_handoff(root, expected):
    if not HANDOFF_HASHES or not re.fullmatch('[0-9a-f]{40}',HANDOFF_COMMIT):
        raise ValueError('UI handoff requires its exact implementation receipt')
    # This fixed overlap is deliberately narrower than a configurable hash
    # overlay: all CP9 scientific and migration checks below remain unchanged.
    if set(HANDOFF_HASHES)&set(CURATION_HASHES)!={HANDOFF_HTTP}:
        raise ValueError('UI handoff cannot override a frozen scientific or migration boundary')
    allowed=HANDOFF_READ_SUPPORT|{HANDOFF_HTTP}|{'src/'+name for name in FRONTEND}|{
        'src/corpustrail/local_app/assets/projects.html','src/corpustrail/local_app/assets/projects.js'}
    if set(HANDOFF_HASHES)-allowed:
        raise ValueError('UI handoff receipt exceeds its fixed composition/read/presentation scope')
    changed=set(subprocess.check_output(['git','-C',str(root),'diff','--name-only',HANDOFF_BASELINE,HANDOFF_COMMIT,'--','src/corpustrail'],text=True).splitlines())
    if changed!=set(HANDOFF_HASHES):raise ValueError('UI handoff receipt must cover its complete exact source delta')
    if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',HANDOFF_COMMIT,expected]).returncode:
        raise ValueError('UI handoff must descend from its reviewed implementation')
    ris=(root/'src/corpustrail/imports/service.py').is_file()
    if ris:check_ris(root,expected)
    for name,wanted in HANDOFF_HASHES.items():
        path=root/name
        frozen=subprocess.check_output(['git','-C',str(root),'show',HANDOFF_COMMIT+':'+name])
        if (path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=current_source_hash(name,RIS_HASHES[name] if ris and name in RIS_HASHES else wanted,root=root)
                or hashlib.sha256(frozen).hexdigest()!=wanted):
            raise ValueError('UI handoff source differs from its exact reviewed implementation')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def check_source(root, expected):
    if not re.fullmatch(r'[0-9a-f]{40}', expected):
        raise ValueError('expected commit must be a full GitHub commit SHA')
    if git(root, 'rev-parse', 'HEAD') != expected:
        raise ValueError('checkout differs from the requested exact commit')
    if git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('development artifact requires a clean source checkout')
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    version = config['project']['version']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+a[0-9]+\.dev[0-9]+', version):
        raise ValueError('development artifacts require an alpha .dev version, not a release version')
    return {'commit_sha': expected, 'tree_sha': git(root, 'rev-parse', 'HEAD^{tree}'), 'version': version}


def check_implementation(root, implementation, expected, *, distribution=None, accepted_checkpoint1=None):
    """Keep the completed scientific checkpoint distinct from CI follow-up source."""
    if accepted_checkpoint1 is not None:
        if not re.fullmatch(r'[0-9a-f]{40}', accepted_checkpoint1):
            raise ValueError('accepted Checkpoint 1 must be a full commit identity')
        previous = check_implementation(root, implementation, accepted_checkpoint1, distribution=distribution)
        if subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', accepted_checkpoint1, expected]).returncode:
            raise ValueError('Checkpoint 2 source must descend from accepted Checkpoint 1')
        changed = set(git(root, 'diff', '--name-only', accepted_checkpoint1, expected, '--', 'src/corpustrail/').splitlines())
        xml_compatibility = bool(changed & XML_COMPATIBILITY_EXTRA_PATHS)
        allowed = CHECKPOINT2_PATHS | CHECKPOINT3_PATHS | CHECKPOINT4_PATHS
        if (root/'src/corpustrail/chatgpt/engine.py').is_file():
            check_chatgpt(root,expected)
            allowed |= CHATGPT_PATHS
        ris=(root/'src/corpustrail/imports/service.py').is_file()
        if ris:check_ris(root,expected);allowed|=set(RIS_HASHES)
        handoff=(root/'src/corpustrail/application/handoff.py').is_file()
        if handoff:
            check_handoff(root,expected)
            allowed |= set(HANDOFF_HASHES)
        curation = (root/'src/corpustrail/application/curation.py').is_file()
        if curation:
            if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',CURATION_COMMIT,expected]).returncode:
                raise ValueError('Curation must descend from its reviewed implementation')
            for name,expected_hash in CURATION_HASHES.items():
                path=root/name
                frozen=subprocess.check_output(['git','-C',str(root),'show',CURATION_COMMIT+':'+name])
                # HTTP's new bytes were separately checked above against the
                # exact CP10 commit. Its original CP9 bytes stay verified here.
                current=frozen if handoff and name==HANDOFF_HTTP else path.read_bytes()
                current_expected=expected_hash if handoff and name==HANDOFF_HTTP else current_source_hash(name,expected_hash,root=root)
                if (path.is_symlink() or not path.is_file() or hashlib.sha256(current).hexdigest()!=current_expected
                        or hashlib.sha256(frozen).hexdigest()!=expected_hash):
                    raise ValueError('Curation source differs from the frozen reviewed implementation')
            allowed |= set(CURATION_HASHES) | {'src/corpustrail/local_app/assets/curation.html','src/corpustrail/local_app/assets/curation.js'}
        classification = (root/'src/corpustrail/classification/service.py').is_file()
        if classification:
            if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',CLASSIFICATION_COMMIT,expected]).returncode:
                raise ValueError('Classification must descend from its reviewed implementation')
            for name,expected_hash in CLASSIFICATION_HASHES.items():
                path=root/name
                frozen=subprocess.check_output(['git','-C',str(root),'show',CLASSIFICATION_COMMIT+':'+name])
                current_hash=CURATION_HASHES.get(name,expected_hash) if curation else expected_hash
                current_hash=current_source_hash(name,current_hash,root=root)
                if (path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=current_hash
                        or hashlib.sha256(frozen).hexdigest()!=expected_hash):
                    raise ValueError('Classification source differs from the frozen reviewed implementation')
            allowed |= set(CLASSIFICATION_HASHES)
        references = (root/'src/corpustrail/references/service.py').is_file()
        if references:
            if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',REFERENCE_COMMIT,expected]).returncode:
                raise ValueError('References must descend from their reviewed implementation')
            for name,expected_hash in REFERENCE_HASHES.items():
                path=root/name
                frozen=subprocess.check_output(['git','-C',str(root),'show',REFERENCE_COMMIT+':'+name])
                current_hash=CLASSIFICATION_HASHES.get(name,expected_hash) if classification else expected_hash
                if curation:current_hash=CURATION_HASHES.get(name,current_hash)
                current_hash=current_source_hash(name,current_hash,root=root)
                if (path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=current_hash
                        or hashlib.sha256(frozen).hexdigest()!=expected_hash):
                    raise ValueError('Reference source differs from the frozen reviewed implementation')
            allowed |= set(REFERENCE_HASHES) | {'src/corpustrail/local_app/assets/references.html',
                                                'src/corpustrail/local_app/assets/references.js'}
        populations = (root/'src/corpustrail/populations/service.py').is_file()
        if populations:
            if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',POPULATION_COMMIT,expected]).returncode:
                raise ValueError('Populations must descend from their reviewed implementation')
            for name, expected_hash in POPULATION_HASHES.items():
                if references and name in REFERENCE_HASHES:
                    historical=subprocess.check_output(['git','-C',str(root),'show',POPULATION_COMMIT+':'+name])
                    if hashlib.sha256(historical).hexdigest()!=expected_hash:
                        raise ValueError('Historical population implementation hash differs')
                    expected_hash=REFERENCE_HASHES[name]
                if classification and name in CLASSIFICATION_HASHES:
                    expected_hash=CLASSIFICATION_HASHES[name]
                if curation:expected_hash=CURATION_HASHES.get(name,expected_hash)
                if ris and name=='src/corpustrail/application/populations.py':
                    original=subprocess.check_output(['git','-C',str(root),'show',POPULATION_COMMIT+':'+name])
                    if hashlib.sha256(original).hexdigest()!=expected_hash:raise ValueError('Historical population controller bytes differ')
                    expected_hash=RIS_HASHES[name]
                path=root/name
                if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:
                    raise ValueError('Population source differs from the frozen reviewed implementation')
            allowed |= set(POPULATION_HASHES) | {'src/corpustrail/local_app/assets/populations.html',
                                                'src/corpustrail/local_app/assets/populations.js'}
        guided_review = bool(changed & set(GUIDED_REVIEW_HASHES))
        if guided_review:
            if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',GUIDED_REVIEW_COMMIT,expected]).returncode:
                raise ValueError('Guided review must descend from its reviewed implementation')
            for name, expected_hash in GUIDED_REVIEW_HASHES.items():
                if populations and name in POPULATION_HASHES:
                    historical = subprocess.check_output(['git','-C',str(root),'show',GUIDED_REVIEW_COMMIT+':'+name])
                    if hashlib.sha256(historical).hexdigest()!=expected_hash:
                        raise ValueError('Historical guided review implementation hash differs')
                    expected_hash = POPULATION_HASHES[name]  # Exact separately frozen integration, not an exception.
                if curation:expected_hash=CURATION_HASHES.get(name,expected_hash)
                path=root/name
                if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:
                    raise ValueError('Guided review source differs from the frozen reviewed implementation')
            allowed |= set(GUIDED_REVIEW_HASHES) | GUIDED_REVIEW_ASSETS
        if xml_compatibility:
            if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',XML_COMPATIBILITY_COMMIT,expected]).returncode:
                raise ValueError('XML compatibility must descend from its reviewed implementation')
            for name, expected_hash in XML_COMPATIBILITY_HASHES.items():
                path = root/name
                if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:
                    raise ValueError('XML compatibility source differs from the frozen reviewed implementation')
            allowed |= XML_COMPATIBILITY_EXTRA_PATHS
        if changed - allowed:
            raise ValueError('Checkpoint 2 may only change the approved guided application boundary')
        for path, marker in (('src/corpustrail/discovery/service.py', '    # Checkpoint 3 read projections.'),
                             ('src/corpustrail/evidence/service.py', '    # Checkpoint 4 read projections.'),
                             ('src/corpustrail/providers/metadata.py', '\ndef request_preview(')):
            if path in changed:
                if xml_compatibility and path == 'src/corpustrail/evidence/service.py':
                    continue  # Whole-file digest above, not a broad prefix/AST exception.
                baseline = git(root, 'show', accepted_checkpoint1 + ':' + path)
                current = (root/path).read_text(encoding='utf-8').split(marker)[0].strip()
                if current != baseline:
                    raise ValueError('Discovery scientific execution/normalization may only gain approved read helpers')
                tree = ast.parse((root/path).read_text(encoding='utf-8'))
                old_tree = ast.parse(baseline)
                if path.endswith(('discovery/service.py','evidence/service.py')):
                    cls = 'DiscoveryService' if path.endswith('discovery/service.py') else 'EvidenceService'
                    old_class = next(n for n in old_tree.body if isinstance(n, ast.ClassDef) and n.name==cls)
                    new_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name==cls)
                    names = [n.name for n in new_class.body if isinstance(n, ast.FunctionDef)]
                    old_names = [n.name for n in old_class.body if isinstance(n, ast.FunctionDef)]
                    additions = ['run_summary','run_papers','run_provenance'] if cls=='DiscoveryService' else ['acquisition_page']
                    if names != old_names+additions or len(tree.body)!=len(old_tree.body):
                        raise ValueError('Scientific executor cannot be overridden or monkeypatched by read helpers')
                elif any(not isinstance(n, ast.FunctionDef) for n in tree.body[len(old_tree.body):]) or [n.name for n in tree.body[len(old_tree.body):]] != ['request_preview','verify_preview_request']:
                    raise ValueError('Metadata adapter may only add the reviewed pure preview helpers')
        # Lifecycle wrappers are allowed, not arbitrary historical review/scientific changes.
        review_path = 'src/corpustrail/curation/http.py'
        if review_path in changed:
            baseline = git(root, 'show', accepted_checkpoint1 + ':' + review_path)
            current = (root / review_path).read_text(encoding='utf-8').strip()
            current = current.replace('from corpustrail.application.project_use import leased_server_factory\n', '')
            current = current.replace('@leased_server_factory\n', '')
            current = current.replace('from corpustrail._internal.loopback_http import LoopbackHTTPServer as ThreadingHTTPServer\n', '')
            current = current.replace('from http.server import BaseHTTPRequestHandler\n',
                                      'from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n')
            if current != baseline:
                raise ValueError('Review server may only add the approved lifecycle wrapper')
        tutorial_path = 'src/corpustrail/tutorial.py'
        if tutorial_path in changed:
            baseline = git(root, 'show', accepted_checkpoint1 + ':' + tutorial_path)
            current = (root / tutorial_path).read_text(encoding='utf-8')
            if current.split("if __name__=='__main__':")[0] != baseline.split("if __name__=='__main__':")[0]:
                raise ValueError('Tutorial scientific fixture functions must remain unchanged')
        checkpoint3 = (root/'src/corpustrail/application/discovery.py').is_file()
        checkpoint4 = (root/'src/corpustrail/application/evidence.py').is_file()
        scientific = {'src/corpustrail/discovery/service.py', 'src/corpustrail/providers/metadata.py', 'src/corpustrail/evidence/service.py'}
        return {**previous, 'name': 'Post-alpha scoped offline demo and production RIS exchange' if ris else 'Checkpoint 10 — complete UI handoff and alpha acceptance' if handoff else 'Checkpoint 9 — curation methods, audit views and iterative correction' if curation else 'Checkpoint 8 — generic classifier plans, assessment storage and validation hooks' if classification else 'Checkpoint 7 — large reference collections and context provenance' if references else 'Checkpoint 6 — origin-independent candidate populations' if populations else 'Checkpoint 5 — guided human review and explicit corpus membership' if guided_review else 'Checkpoint 4 — evidence acquisition and inspection' if checkpoint4 else 'Checkpoint 3 — exact discovery and local jobs' if checkpoint3 else 'Checkpoint 2 — guided project/configuration and definition',
                'accepted_checkpoint1_commit_sha': accepted_checkpoint1,
                'application_source_unchanged': not bool(changed),
                'configuration_writes_supported': True,
                'application_paths_changed_since_accepted_checkpoint1': sorted(changed),
                'scientific_source_unchanged': not bool(changed & scientific) and not guided_review and not references,
                'scientific_service_source_unchanged': not bool(changed & scientific) and not guided_review and not references,
                'scientific_execution_source_unchanged': not xml_compatibility and not guided_review and not references,
                'discovery_scientific_execution_source_unchanged': True,
                'xml_compatibility': {'schema':'corpustrail-xml-compatibility-code-review/v1',
                    'implementation_commit_sha':XML_COMPATIBILITY_COMMIT,
                    'policy':'bounded-inert-jats/v2',
                    'renderer_versions':['corpustrail-native-jats/v4','corpustrail-native-publisher-xml/v4'],
                    'source_sha256':XML_COMPATIBILITY_HASHES,
                    'notice':'Reviewed implementation lineage; not artifact build identity or researcher acceptance.'} if xml_compatibility else None,
                'discovery_workflow_supported': checkpoint3,
                'evidence_workflow_supported': checkpoint4,
                'guided_review_workflow_supported': guided_review,
                'guided_review': {'schema':'corpustrail-guided-review-code-review/v1',
                    'implementation_commit_sha':GUIDED_REVIEW_COMMIT,
                    'session_schema':'corpustrail-review-session/v2',
                    'policy':'deferred-human-publication/v1',
                    'source_sha256':{name:CURATION_HASHES.get(name,POPULATION_HASHES.get(name,value) if populations else value) if curation else POPULATION_HASHES.get(name,value) if populations else value for name,value in GUIDED_REVIEW_HASHES.items()},
                    'pre_population_source_sha256':GUIDED_REVIEW_HASHES,
                    'legacy_authority_unchanged':True,
                    'schema_migrations':False,
                    'notice':'Versioned guided lifecycle; build identity is source.commit_sha, not this historical implementation receipt.'} if guided_review else None,
                'populations': {'schema':'corpustrail-population-code-review/v1',
                    'implementation_commit_sha':POPULATION_COMMIT,
                    'source_sha256':{name:CURATION_HASHES.get(name,CLASSIFICATION_HASHES.get(name,REFERENCE_HASHES.get(name,value))) if curation else CLASSIFICATION_HASHES.get(name,REFERENCE_HASHES.get(name,value)) if classification else REFERENCE_HASHES.get(name,value) if references else value for name,value in POPULATION_HASHES.items()},
                    'pre_reference_source_sha256':POPULATION_HASHES,
                    'population_schema':'corpustrail-candidate-population/v1','policy':'exact-canonical-union/v1',
                    'migration':38,'read_compatible_schema':37,'upgrade':'explicit_with_backup',
                    'production_importers':ris,'production_import_formats':['ris'] if ris else [],'membership_authority_unchanged':True} if populations else None,
                'references':{'schema':'corpustrail-reference-code-review/v1','implementation_commit_sha':REFERENCE_COMMIT,
                    'source_sha256':{name:CURATION_HASHES.get(name,CLASSIFICATION_HASHES.get(name,value)) if curation else CLASSIFICATION_HASHES.get(name,value) if classification else value for name,value in REFERENCE_HASHES.items()},
                    'pre_classifier_source_sha256':REFERENCE_HASHES,'reference_schema':'corpustrail-reference-set/v1',
                    'context_schema':'corpustrail-selected-reference-context/v1','eligibility_policy':'explicit-human-unconflicted/v1',
                    'selection_strategy':'canonical-reference-order/v1','migration':39,'read_compatible_schema':[37,38],
                    'upgrade':'explicit_with_backup','real_engines':False,'membership_authority_unchanged':True} if references else None,
                'classification':{'schema':'corpustrail-classifier-code-review/v1',
                    'implementation_commit_sha':CLASSIFICATION_COMMIT,
                    'source_sha256':{name:CURATION_HASHES.get(name,value) if curation else value for name,value in CLASSIFICATION_HASHES.items()},
                    'pre_curation_source_sha256':CLASSIFICATION_HASHES,
                    'plan_schema':'corpustrail-assessment-plan/v1','assessment_schema':'corpustrail-immutable-assessment/v1',
                    'migration':40,'read_compatible_schema':[37,38,39],'upgrade':'explicit_with_backup',
                    'engine_execution':'explicitly_registered_offline_only','real_model_integration':False,
                    'scientific_performance_claim':False,'assessment_authority':'non_authoritative',
                    'membership_authority_unchanged':True,'calibration':'provenance_hooks_not_validated_calibrator',
                    'cp9_workflow_implemented':curation} if classification else None,
                'curation':{'schema':'corpustrail-curation-code-review/v1','implementation_commit_sha':CURATION_COMMIT,
                    'source_sha256':CURATION_HASHES,'migration':41,'read_compatible_schema':[37,38,39,40],
                    'upgrade':'explicit_with_backup','api_schema':'corpustrail-local-curation/v1',
                    'audit_schema':'corpustrail-frozen-curation-audit/v1','assessment_authority':'non_authoritative',
                    'human_authorization':'existing_guided_service_with_atomic_source_links','real_engines':False,
                    'automatic_reassessment':False,'membership_authority_unchanged':True,
                    'researcher_acceptance':False} if curation else None,
                'ui_handoff':{'schema':'corpustrail-ui-handoff-code-review/v1','implementation_commit_sha':HANDOFF_COMMIT,
                    'source_sha256':HANDOFF_HASHES,'api_schema':'corpustrail-local-handoff/v1','migration':None,
                    'alpha_baseline':True,'beta_release':False,'native_installer':False,'real_model_validation':False,
                    'production_importers':ris,'production_import_formats':['ris'] if ris else [],'membership_authority_unchanged':True,'researcher_acceptance':False} if handoff else None,
                'ris_exchange':{'schema':'corpustrail-ris-exchange-code-review/v1','implementation_commit_sha':RIS_COMMIT,
                    'accepted_alpha_baseline':RIS_BASELINE,'source_sha256':RIS_HASHES,'profile':'corpustrail-ris/v1',
                    'migration':None,'import_formats':['ris'],'export_formats':['ris'],'offline_scoped_demo':True,
                    'identity_policy_unchanged':True,'membership_authority_unchanged':True,'original_source_preserved':True,
                    'native_enrollment_change':'exact_transaction_body_factoring_only','researcher_acceptance':False} if ris else None,
                'chatgpt_assessment': {'schema':'corpustrail-chatgpt-adapter-review/v1','implementation_commit_sha':CHATGPT_COMMIT,
                    'source_sha256':CHATGPT_HASHES,'assessment_capability':'broad-corpus-assessment/v2',
                    'input_projection':'corpustrail-title-abstract-input/v1','transfer_consent':'exact-transmitted-payload',
                    'migration':None,'offline_protocol_verified':True,'live_interoperability_verified':False,
                    'membership_authority_unchanged':True,'assertion_extraction_unchanged':True,
                    'live_no_extra_charge_gate':'requires_separate_owner_evidence','researcher_acceptance':False}
                    if (root/'src/corpustrail/chatgpt/engine.py').is_file() else None,
                'notice': 'Original Checkpoint 1 and accepted visual baseline are historical lineage. '
                          'The source/build SHA identifies this development artifact; it is not built from an earlier checkpoint.'}
    if not re.fullmatch(r'[0-9a-f]{40}', implementation):
        raise ValueError('implementation commit must be a full commit SHA')
    if git(root, 'cat-file', '-t', implementation) != 'commit':
        raise ValueError('implementation identity must refer to a commit')
    relation = subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', implementation, expected])
    if relation.returncode != 0:
        raise ValueError('artifact source must descend from the implementation checkpoint')
    changed = set(git(root, 'diff', '--name-only', implementation, expected, '--', 'src/corpustrail/').splitlines())
    if changed and (distribution is None or changed - PRESENTATION_PATHS):
        raise ValueError('Checkpoint 1 application/scientific source must remain unchanged')
    if distribution is not None:
        if not re.fullmatch(r'[0-9a-f]{40}', distribution) or git(root, 'cat-file', '-t', distribution) != 'commit':
            raise ValueError('distribution follow-up must be a full commit identity')
        for earlier, later in ((implementation, distribution), (distribution, expected)):
            if subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', earlier, later]).returncode:
                raise ValueError('implementation, distribution and artifact source lineage must be ordered')
        if git(root, 'diff', '--name-only', implementation, distribution, '--', 'src/corpustrail/'):
            raise ValueError('original CI/distribution follow-up must preserve implementation source')
    return {'name': 'Checkpoint 1 — read-only dashboard and paper browser',
            'implementation_commit_sha': implementation,
            'implementation_tree_sha': git(root, 'rev-parse', implementation + '^{tree}'),
            'application_source_unchanged': not bool(changed),
            'scientific_source_unchanged': True,
            'presentation_paths_changed': sorted(changed),
            'previous_distribution_commit_sha': distribution,
            'notice': 'Implementation lineage, not the artifact build/source commit.'}


def inspect_wheel(path, version):
    if path.is_symlink() or not path.is_file():
        raise ValueError('wheel must be a regular build artifact')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_paths = [name for name in names if name.endswith('.dist-info/METADATA')]
        if len(metadata_paths) != 1 or not FRONTEND <= set(names):
            raise ValueError('wheel metadata or packaged frontend is incomplete')
        metadata = email.message_from_bytes(archive.read(metadata_paths[0]))
        if metadata['Name'] != 'corpus-trail' or metadata['Version'] != version:
            raise ValueError('wheel package/version differs from source configuration')
        if metadata['License-Expression'] != 'MIT' or any(metadata.get(key) for key in (
                'Author', 'Author-email', 'Maintainer', 'Maintainer-email')):
            raise ValueError('wheel license/privacy metadata differs from project policy')
        for key in metadata.get_all('Requires-Dist', []):
            if 'extra ==' not in key:
                raise ValueError('core wheel unexpectedly requires a runtime dependency')
    return {'filename': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


def installed_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def validate_browser_acceptance(records,expected):
    """Current delivery gates: functional completeness, strict results, exact debt."""
    renderers={'linux-chromium','darwin-chromium','darwin-webkit'}
    if not isinstance(records,list) or len(records)!=3 or {r.get('renderer') for r in records}!=renderers:
        raise ValueError('Three distinct browser acceptance receipts are required')
    captures={v+'-'+n+'.png' for v in ('desktop','narrow') for n in ('wizard','projects','trash-confirmation')}
    captures.update(v+'-wizard-summary.png' for v in ('desktop','laptop','narrow'))
    for record in records:
        if (record.get('schema')!='corpustrail-browser-gate/v1' or record.get('source')!=expected
                or not all(record.get(k) is True for k in ('accepted','functional_passed','complete'))
                or not isinstance(record.get('executions'),int) or record['executions']<=0
                or not isinstance(record.get('comparisons'),int) or record['comparisons']<=0
                or not re.fullmatch('[0-9a-f]{64}',record.get('report_sha256',''))):
            raise ValueError('Incomplete, failed or wrong-source browser acceptance')
        exceptions=record.get('exceptions');strict=record.get('strict_passed')
        if not isinstance(exceptions,list) or not isinstance(strict,int) or not 0<=strict<=record['comparisons'] or strict+len(exceptions)!=record['comparisons']:
            raise ValueError('Every failed visual comparison needs exact exception evidence')
        if record.get('strict_visual_passed') is not (len(exceptions)==0):
            raise ValueError('Strict visual result must remain truthful')
        if record['renderer']=='linux-chromium' and exceptions:raise ValueError('Linux has no visual exception')
        if len({e.get('capture') for e in exceptions})!=len(exceptions):raise ValueError('Repeated visual exception')
        for entry in exceptions:
            if (entry.get('policy')!='researcher-approved-cp7-fixture-path-reflow/v1' or entry.get('verified') is not True
                    or entry.get('capture') not in captures or entry.get('strict_comparison_passed') is not False
                    or entry.get('all_other_pixels_accounted') is not True
                    or any(not re.fullmatch('[0-9a-f]{64}',entry.get(k,'')) for k in ('expected_sha256','actual_sha256','evidence_sha256'))):
                raise ValueError('Unapproved or unproved visual exception')
            body={k:v for k,v in entry.items() if k!='evidence_sha256'}
            if hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=entry['evidence_sha256']:
                raise ValueError('Visual exception evidence hash differs')
    return records


def bundle(root, expected, validation_dir, output_dir, *, implementation, context, distribution=None, accepted_checkpoint1=None,browser_acceptance=None):
    source = check_source(root, expected)
    checkpoint = check_implementation(root, implementation, expected, distribution=distribution, accepted_checkpoint1=accepted_checkpoint1)
    wheels = list((root / 'dist').glob('*.whl'))
    if len(wheels) != 1:
        raise ValueError('expected exactly one newly built wheel')
    wheel = inspect_wheel(wheels[0], source['version'])
    tests = validation_dir / 'development-tests.txt'
    tutorial = validation_dir / 'development-tutorial.json'
    installed = validation_dir / 'development-version.txt'
    if not re.search(r'\nRan \d+ tests in ', tests.read_text(encoding='utf-8')) or not re.search(
            r'\nOK(?: \(skipped=\d+\))?\s*$', tests.read_text(encoding='utf-8')):
        raise ValueError('successful installed-wheel test receipt is required')
    if installed.read_text(encoding='utf-8').strip() != source['version']:
        raise ValueError('installed CLI version differs from wheel/source')
    if json.loads(tutorial.read_text(encoding='utf-8')).get('network_used') is not False:
        raise ValueError('offline tutorial receipt is required')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', context['repository']):
        raise ValueError('repository identity is required, not an arbitrary URL')
    if not context['ref'].startswith('refs/heads/development/'):
        raise ValueError('only a development branch can publish a development artifact')
    if any(not re.fullmatch(r'[0-9]+', context[key]) for key in ('run_id', 'run_attempt')):
        raise ValueError('numeric workflow run identity is required')
    if browser_acceptance is not None:validate_browser_acceptance(browser_acceptance,expected)
    name = 'corpustrail-dev-' + source['version'] + '-' + expected + '-run-' + context['run_id'] + '-' + context['run_attempt']
    output_dir.mkdir(parents=True, exist_ok=False)  # Never overwrite a prior bundle.
    files = {}
    for path in (wheels[0], tests, tutorial, installed):
        shutil.copyfile(path, output_dir / path.name)
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {'schema': 'corpustrail-development-artifact/v1', 'status': 'unreleased_development_checkpoint',
              'source': source, 'checkpoint': checkpoint, 'wheel': wheel, 'workflow': context, 'artifact_name': name,
              'validation': {'upstream_python_matrix': ['3.11', '3.12', '3.13'],
                             'installed_artifact_python': sys.version.split()[0],
                             'installed_core_tests': 'passed', 'offline_tutorial': 'passed'},
              'build': {'python': sys.version.split()[0],
                        'setuptools': installed_version('setuptools')},
              'created_at': datetime.now(timezone.utc).isoformat(), 'files_sha256': files,
              'notice': 'Not a GitHub Release or PyPI package. Verify the source SHA against the workflow run. '
                        'The receipt is not a cryptographic attestation. No real provider/model calls were used.'}
    if browser_acceptance is not None:
        record['validation']['browser_acceptance']=browser_acceptance
        record['validation']['all_strict_visual_comparisons_passed']=all(r['strict_visual_passed'] for r in browser_acceptance)
    (output_dir / 'build-provenance.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    (output_dir / 'SHA256SUMS').write_text(''.join(f'{value}  {key}\n' for key, value in sorted(files.items())) +
        hashlib.sha256((output_dir / 'build-provenance.json').read_bytes()).hexdigest() + '  build-provenance.json\n', encoding='utf-8')
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check-source', 'bundle'))
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--implementation-commit', required=True)
    parser.add_argument('--distribution-commit')
    parser.add_argument('--accepted-checkpoint1')
    parser.add_argument('--validation-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--browser-acceptance-json',help='Three exact-source browser gate receipts, required for CI delivery')
    args = parser.parse_args()
    if args.action == 'check-source':
        print(json.dumps({'source': check_source(ROOT, args.expected_commit),
                          'checkpoint': check_implementation(ROOT, args.implementation_commit, args.expected_commit,
                                                             distribution=args.distribution_commit,
                                                             accepted_checkpoint1=args.accepted_checkpoint1)}))
        return
    if args.validation_dir is None or args.output_dir is None:
        parser.error('bundle requires --validation-dir and --output-dir')
    if args.browser_acceptance_json is None:parser.error('bundle requires explicit browser acceptance receipts')
    browser_acceptance=validate_browser_acceptance(json.loads(args.browser_acceptance_json),args.expected_commit)
    # Explicit allowlist only; never dump environment, token, actor or Git identity.
    context = {key: os.environ[env] for key, env in (
        ('repository', 'GITHUB_REPOSITORY'), ('ref', 'GITHUB_REF'),
        ('run_id', 'GITHUB_RUN_ID'), ('run_attempt', 'GITHUB_RUN_ATTEMPT'))}
    name = bundle(ROOT, args.expected_commit, args.validation_dir, args.output_dir,
                  implementation=args.implementation_commit, distribution=args.distribution_commit, context=context,
                  accepted_checkpoint1=args.accepted_checkpoint1,browser_acceptance=browser_acceptance)
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as handle:
        handle.write('artifact_name=' + name + '\n')
    print(name)


if __name__ == '__main__':
    main()
