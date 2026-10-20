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
        references = (root/'src/corpustrail/references/service.py').is_file()
        if references:
            if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',REFERENCE_COMMIT,expected]).returncode:
                raise ValueError('References must descend from their reviewed implementation')
            for name,expected_hash in REFERENCE_HASHES.items():
                path=root/name
                frozen=subprocess.check_output(['git','-C',str(root),'show',REFERENCE_COMMIT+':'+name])
                if (path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash
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
        return {**previous, 'name': 'Checkpoint 7 — large reference collections and context provenance' if references else 'Checkpoint 6 — origin-independent candidate populations' if populations else 'Checkpoint 5 — guided human review and explicit corpus membership' if guided_review else 'Checkpoint 4 — evidence acquisition and inspection' if checkpoint4 else 'Checkpoint 3 — exact discovery and local jobs' if checkpoint3 else 'Checkpoint 2 — guided project/configuration and definition',
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
                    'source_sha256':{name:POPULATION_HASHES.get(name,value) if populations else value for name,value in GUIDED_REVIEW_HASHES.items()},
                    'pre_population_source_sha256':GUIDED_REVIEW_HASHES,
                    'legacy_authority_unchanged':True,
                    'schema_migrations':False,
                    'notice':'Versioned guided lifecycle; build identity is source.commit_sha, not this historical implementation receipt.'} if guided_review else None,
                'populations': {'schema':'corpustrail-population-code-review/v1',
                    'implementation_commit_sha':POPULATION_COMMIT,
                    'source_sha256':{name:REFERENCE_HASHES.get(name,value) if references else value for name,value in POPULATION_HASHES.items()},
                    'pre_reference_source_sha256':POPULATION_HASHES,
                    'population_schema':'corpustrail-candidate-population/v1','policy':'exact-canonical-union/v1',
                    'migration':38,'read_compatible_schema':37,'upgrade':'explicit_with_backup',
                    'production_importers':False,'membership_authority_unchanged':True} if populations else None,
                'references':{'schema':'corpustrail-reference-code-review/v1','implementation_commit_sha':REFERENCE_COMMIT,
                    'source_sha256':REFERENCE_HASHES,'reference_schema':'corpustrail-reference-set/v1',
                    'context_schema':'corpustrail-selected-reference-context/v1','eligibility_policy':'explicit-human-unconflicted/v1',
                    'selection_strategy':'canonical-reference-order/v1','migration':39,'read_compatible_schema':[37,38],
                    'upgrade':'explicit_with_backup','real_engines':False,'membership_authority_unchanged':True} if references else None,
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
