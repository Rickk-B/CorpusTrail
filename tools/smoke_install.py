"""Build/install only the candidate in temporary directories, without network."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import tarfile
from pathlib import Path
from datetime import datetime, timezone


def invoke(argv, cwd, env):
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv!r}\n{result.stdout}\n{result.stderr}")
    return result.stdout, result.stderr


def sdist_smoke(root, payload, outside, env, *, dependency_wheels=None):
    """Test the actual declarative sdist, not a checkout pretending to be one."""
    output = root / 'sdist'
    output.mkdir()
    invoke([sys.executable, '-c', 'from setuptools.build_meta import build_sdist; build_sdist(' + repr(str(output)) + ')'], payload, env)
    archive, = output.glob('*.tar.gz')
    extracted = root / 'extracted'
    extracted.mkdir()
    with tarfile.open(archive) as handle:
        for item in handle.getmembers():
            destination = (extracted / item.name).resolve()
            if not destination.is_relative_to(extracted) or not (item.isfile() or item.isdir()):
                raise RuntimeError('unsafe source-distribution member')
        # Python 3.11 compatibility: members above are confined regular files/dirs.
        handle.extractall(extracted)
    source, = extracted.iterdir()
    for required in ('docs/phase2b_migration_origins.json', 'docs/phase2c_migration_origins.json',
                     'docs/user/TUTORIAL.md', 'docs/user/MODELS.md', 'docs/developer/MODEL_ADAPTERS.md',
                     'docs/v0.1.0a3-implementation-plan.md', 'docs/user/LOCAL_UI.md',
                     'src/corpustrail/local_app/assets/index.html',
                     'src/corpustrail/local_app/assets/app.css', 'src/corpustrail/local_app/assets/app.js',
                     'src/corpustrail/resources/origins.json'):
        if not (source / required).is_file():
            raise RuntimeError('sdist omitted required provenance/tutorial: ' + required)
    wheels = root / 'sdist-wheels'
    wheels.mkdir()
    invoke([sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps', '--no-build-isolation',
            '--no-cache-dir', '--wheel-dir', str(wheels), str(source)], outside, env)
    wheel, = wheels.glob('*.whl')
    reports = {}
    for mode in (('core', 'ml') if dependency_wheels else ('core',)):
        venv = root / ('sdist-' + mode)
        invoke([sys.executable, '-m', 'venv', str(venv)], outside, env)
        python = venv / 'bin/python'
        command = [str(python), '-m', 'pip', 'install', '--no-index']
        command += ['--find-links', str(dependency_wheels), str(wheel) + '[prioritization]'] if mode == 'ml' else ['--no-deps', str(wheel)]
        invoke(command, outside, env)
        out, err = invoke([str(python), '-I', '-B', '-m', 'unittest', 'discover', '-s', str(source/'tests'), '-p', 'test_*.py'], outside, env)
        project = root / ('sdist-tutorial-' + mode)
        tutorial, _ = invoke([str(python), '-I', '-B', '-m', 'corpustrail.tutorial', str(project)] +
                             (['--prioritize'] if mode == 'ml' else []), outside, env)
        status, _ = invoke([str(venv/'bin/corpustrail'), 'project', 'status', str(project)], outside, env)
        invoke([str(python), '-m', 'pip', 'uninstall', '-y', 'corpus-trail'], outside, env)
        invoke(command, outside, env)
        reopened, _ = invoke([str(venv/'bin/corpustrail'), 'project', 'status', str(project)], outside, env)
        if json.loads(status) != json.loads(reopened):
            raise RuntimeError('uninstall/reinstall changed project state')
        reports[mode] = {'tests': (out+err).strip(), 'tutorial': json.loads(tutorial), 'reinstall_reopen': True}
    return {'sdist_sha256': 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest(),
            'wheel_from_sdist_sha256': 'sha256:' + hashlib.sha256(wheel.read_bytes()).hexdigest(), 'environments': reports}


def run(*, dependency_wheels=None) -> dict:
    candidate = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="corpustrail-phase2d2-smoke-") as temp:
        root = Path(temp)
        payload = root / "candidate"
        # No ancestor/workspace copy. No ignored runtime state enters the build.
        shutil.copytree(candidate, payload, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", "*.egg-info", "build", "dist", ".venv", "*.sqlite3*"))
        wheels = root / "wheels"
        wheels.mkdir()
        outside = root / "unrelated-working-directory"
        outside.mkdir()
        invoke([sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
                "--no-cache-dir", "--wheel-dir", str(wheels), str(payload)], outside, env)
        wheel, = wheels.glob("*.whl")
        with zipfile.ZipFile(wheel) as archive:
            wheel_entries = sorted(archive.namelist())
        for required in ('corpustrail/local_app/assets/index.html',
                         'corpustrail/local_app/assets/app.css', 'corpustrail/local_app/assets/app.js'):
            if required not in wheel_entries:
                raise RuntimeError('wheel omitted local frontend asset: ' + required)
        if any(not name.startswith(("corpustrail/", "corpus_trail-")) for name in wheel_entries):
            raise RuntimeError("wheel contains unexpected external assets")
        venv = root / "venv"
        invoke([sys.executable, "-m", "venv", str(venv)], outside, env)
        python = venv / "bin" / "python"
        cli = venv / "bin" / "corpustrail"
        invoke([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], outside, env)
        check = """import pathlib,sys,importlib.util,importlib.metadata,json,corpustrail
assert pathlib.Path(corpustrail.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix))
metadata=importlib.metadata.metadata('corpus-trail')
assert metadata['License-Expression']=='MIT'
assert metadata.get('Author') is None and metadata.get('Author-email') is None
assert metadata.get('Maintainer') is None and metadata.get('Maintainer-email') is None
assert set(metadata.get_all('License-File'))=={'LICENSE','NOTICE.md'}
for name in ('anthropic','openai','asreview','sklearn','yaml','upe_core','search_databases'):
 assert importlib.util.find_spec(name) is None, name
print(json.dumps({'version':corpustrail.__version__,'distribution':importlib.metadata.version('corpus-trail'),'isolated':True}))
"""
        imported, _ = invoke([str(python), "-I", "-B", "-c", check], outside, env)
        version, _ = invoke([str(cli), "--version"], outside, env)
        cli_project = root / "cli-project"
        initialized, _ = invoke([str(cli), "project", "init", str(cli_project), "--project-id", "smoke-topic",
            "--name", "Materials sensors", "--description", "Synthetic offline topic", "--created-by", "fixture"], outside, env)
        status, _ = invoke([str(cli), "project", "status", str(cli_project)], outside, env)
        if json.loads(initialized) != json.loads(status):
            raise RuntimeError("CLI reopen changed status")
        # Installed adapter configuration/status/help must be self-contained and
        # network-free; HTTP invocation is exercised only by loopback test fixtures.
        model_status, _ = invoke([str(cli), 'models', 'status', str(cli_project)], outside, env)
        if json.loads(model_status)['model_providers']:
            raise RuntimeError('fresh project unexpectedly configures a model')
        model_configured, _ = invoke([str(cli), 'models', 'configure', str(cli_project),
            '--workflow', 'local-reference', '--model', 'fixture-model', '--endpoint-id', 'fixture-endpoint',
            '--base-url', 'http://127.0.0.1:8000/v1', '--execution', 'local', '--created-by', 'fixture'], outside, env)
        if json.loads(model_configured)['model_providers'][0]['execution'] != 'local':
            raise RuntimeError('installed model locality/status mismatch')
        invoke([str(cli), 'models', 'test-connection', '--help'], outside, env)
        demonstration, _ = invoke([str(python), "-I", "-B", str(payload / "examples/synthetic-materials/run.py"),
                                    str(root / "demonstration")], outside, env)
        discovery, _ = invoke([str(python), "-I", "-B", str(payload / "examples/synthetic-discovery/run.py"),
                              str(root / "discovery-demonstration")], outside, env)
        knowledge, _ = invoke([str(python), '-I', '-B', str(payload/'examples/synthetic-knowledge/run.py'),
                               str(root/'knowledge-demonstration')],outside,env)
        knowledge_demo=json.loads(knowledge)
        invoke([str(cli),'knowledge','show',str(root/'knowledge-demonstration'),
                '--paper-id',knowledge_demo['paper_id']],outside,env)
        invoke([str(cli),'knowledge','conflicts',str(root/'knowledge-demonstration')],outside,env)
        invoke([str(cli),'knowledge','verify',str(root/'knowledge-demonstration')],outside,env)
        exported,_=invoke([str(python),'-I','-B',str(payload/'examples/synthetic-asreview/run.py'),
                           str(root/'export-demonstration')],outside,env)
        export_demo=json.loads(exported)
        invoke([str(cli),'export','asreview','preview',str(root/'export-demonstration')],outside,env)
        invoke([str(cli),'export','asreview','inspect',str(root/'export-demonstration'),
                '--export-id','fixture-corpus'],outside,env)
        invoke([str(cli),'export','asreview','mapping',str(root/'export-demonstration'),
                '--review-id','review-A','--mapping-id','result-1'],outside,env)
        tests_out, tests_err = invoke([str(python), "-I", "-B", "-m", "unittest", "discover", "-s",
                                      str(payload / "tests"), "-p", "test_*.py"], outside, env)
        packaged_tutorial, _ = invoke([str(python), '-I', '-B', '-m', 'corpustrail.tutorial',
                                      str(root/'packaged-tutorial')], outside, env)
        optional = None
        if dependency_wheels:
            # Separate clean environment: the base installation remains dependency-free.
            numerical = root / 'prioritization-venv'
            invoke([sys.executable,'-m','venv',str(numerical)],outside,env)
            ml_python = numerical / 'bin/python'
            ml_cli = numerical / 'bin/corpustrail'
            invoke([str(ml_python),'-m','pip','install','--no-index','--find-links',str(dependency_wheels),
                    str(wheel)+'[prioritization]'],outside,env)
            numerical_check = "import sys,json,importlib.metadata; print(json.dumps({k:importlib.metadata.version(k) for k in ('scikit-learn','numpy','scipy','joblib','threadpoolctl')}))"
            versions,_=invoke([str(ml_python),'-I','-B','-c',numerical_check],outside,env)
            curation,_=invoke([str(ml_python),'-I','-B',str(payload/'examples/synthetic-curation/run.py'),
                              str(root/'curation-demonstration')],outside,env)
            demo=json.loads(curation)
            integrated,_=invoke([str(ml_python),'-I','-B','-m','corpustrail.tutorial',
                                 str(root/'integrated-demonstration'),'--prioritize'],outside,env)
            # Installed CLI covers serve startup/resume in portable HTTP tests; explicit train/rank here.
            trained,_=invoke([str(ml_cli),'prioritize','train',str(root/'curation-demonstration'),
                '--label-cutoff','2026-01-02T00:00:00+00:00'],outside,env)
            model=json.loads(trained)['model_id']
            invoke([str(ml_cli),'prioritize','rank',str(root/'curation-demonstration'),
                '--model-id',model,'--run-id','installed-cli-ranking'],outside,env)
            invoke([str(ml_cli),'review','status',str(root/'curation-demonstration'),
                '--session-id','fixture-session'],outside,env)
            out,err=invoke([str(ml_python),'-I','-B','-m','unittest','discover','-s',str(payload/'tests'),
                '-p','test_*.py'],outside,env)
            optional={'separate_clean_venv':True,'dependency_versions':json.loads(versions),
                      'synthetic_curation':demo,'synthetic_integrated_export':json.loads(integrated),
                      'installed_train_rank_cli':True,'tests':(out+err).strip()}
        sdist = sdist_smoke(root, payload, outside, env, dependency_wheels=dependency_wheels)
        return {"schema_version": "corpustrail-install-smoke/v2", "network_used": False,
                "completed_at": datetime.now(timezone.utc).isoformat(), "build_python": sys.version,
                "build_setuptools": importlib.metadata.version("setuptools"),
                "candidate_only_copy": True, "editable_install": False, "isolated_interpreter": True,
                "import_check": json.loads(imported), "cli_version": version.strip(),
                "wheel_sha256": "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "wheel_entries": wheel_entries, "fresh_project": json.loads(status),
                "synthetic_demonstration": json.loads(demonstration),
                "synthetic_discovery": json.loads(discovery),
                "synthetic_knowledge":knowledge_demo,
                "installed_knowledge_cli":True,
                "synthetic_asreview_export":export_demo,"installed_export_cli":True,
                "optional_prioritization": optional, "packaged_tutorial": json.loads(packaged_tutorial), 'sdist': sdist,
                "tests": (tests_out + tests_err).strip()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependency-wheels',type=Path,help='Offline wheels for a second clean optional-ML environment')
    args=parser.parse_args()
    print(json.dumps(run(dependency_wheels=args.dependency_wheels), ensure_ascii=False, sort_keys=True, indent=2))
