"""Disposable fixtures only. Native Trash tests require an explicit CI opt-in."""
import concurrent.futures
from contextlib import nullcontext
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from corpustrail.application.projects import ProjectController, ProjectCommandError, SCHEMA as FORM
from corpustrail.application.project_use import acquire_project_use, ProjectBusy, ProjectUseError, creation_use
from corpustrail.application.trash import ProjectRemoval, MacOSTrash, TrashResult, SCHEMA
from corpustrail.identity import BibliographicRecord, SourceReference
from corpustrail.project import Project, ProjectConfig

CHILD = r'''
import sys, runpy
from pathlib import Path
import corpustrail.application.project_use as guard
root, directory, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
guard.lock_directory = lambda: directory
if mode in ('app', 'review', 'cli', 'status', 'tutorial'):
    from corpustrail.cli import main
    from corpustrail.project import Project
    if mode == 'cli':
        original = Project.status
        def held(self):
            print('READY', flush=True); sys.stdin.readline(); return original(self)
        Project.status = held
    if mode == 'tutorial':
        original = Project.create
        def held(cls, *args, **kwargs):
            p = original(*args, **kwargs); print('READY', flush=True); sys.stdin.readline(); return p
        Project.create = classmethod(held)
        sys.argv = ['corpustrail.tutorial', str(root)]
        runpy.run_module('corpustrail.tutorial', run_name='__main__'); sys.exit(0)
    args = (['app', str(root), '--port', '0'] if mode == 'app' else
            ['review', 'serve', str(root), '--session-id', 'session', '--port', '0'] if mode == 'review' else
            ['project', 'status', str(root)])
    sys.exit(main(args))
try:
    with guard.acquire_project_use(root, exclusive=mode != 'shared'):
        if mode == 'move':
            destination=root.parent/'controlled-move'; assert not destination.exists(); root.rename(destination)
        print('READY', flush=True); sys.stdin.readline()
except guard.ProjectUseError as e:
    print(str(e), flush=True); sys.exit(3)
'''


def fingerprint(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ct-disposable-removal-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'projects'
        self.path = self.root / 'disposable'
        self.locks = self.base / 'app-owned' / 'locks'
        self.project = Project.create(self.path, ProjectConfig('disposable-fixture', 'Disposable project', 'Synthetic topic'), created_by='fixture')
        source = SourceReference('fixture://record', 'one', 'sha256:'+'0'*64, 0, 'fixture', '2026-01-01T00:00:00+00:00')
        pid = self.project.identities.apply(self.project.identities.plan(BibliographicRecord('Invented paper'), source),
                     approve_new_identity=True, approve_aliases=True)
        self.project.review_sessions.prepare('session', reviewer_id='fixture', paper_ids=[pid])
        self.controller = ProjectController(projects_root=self.root)
        self.addCleanup(self.controller.close)
        self.patcher = patch('corpustrail.application.project_use.lock_directory', return_value=self.locks)
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def child(self, mode, ready=True, path=None):
        proc = subprocess.Popen([sys.executable, '-I', '-u', '-c', CHILD, str(path or self.path), str(self.locks), mode],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop, proc)
        if ready:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(proc.stdout.readline)
                try: line = future.result(timeout=20)
                except concurrent.futures.TimeoutError:
                    self.stop(proc); raise
            self.assertTrue(line.startswith(('READY', 'CorpusTrail local application:', 'Review session:')), repr(line))
        return proc

    @staticmethod
    def stop(proc):
        if proc.poll() is None: proc.kill()
        proc.communicate(timeout=20)


class GuardTests(Fixture):
    def test_independent_launchers_review_cli_and_shared_access(self):
        before = fingerprint(self.path)
        for pair in (('app', 'app'), ('app', 'review'), ('app', 'cli'), ('shared', 'shared')):
            with self.subTest(pair=pair):
                a, b = self.child(pair[0]), self.child(pair[1])
                with acquire_project_use(self.path): pass
                with self.assertRaises(ProjectBusy): acquire_project_use(self.path, exclusive=True)
                self.stop(a)
                with self.assertRaises(ProjectBusy): acquire_project_use(self.path, exclusive=True)
                self.stop(b)
                with acquire_project_use(self.path, exclusive=True): pass
        self.assertEqual(before, fingerprint(self.path))

    def test_exclusive_blocks_new_operations_and_nested_upgrades(self):
        with acquire_project_use(self.path):
            with acquire_project_use(self.path): pass
            with self.assertRaises(ProjectBusy): acquire_project_use(self.path, exclusive=True)
        with acquire_project_use(self.path, exclusive=True):
            with self.assertRaises(ProjectBusy): acquire_project_use(self.path)
            for mode in ('app', 'review', 'status', 'shared'):
                proc = self.child(mode, ready=False)
                out, err = proc.communicate(timeout=20)
                self.assertNotEqual(proc.returncode, 0); self.assertIn('in use', out+err)

    def test_crash_recovery_repeated_leases_and_persistent_anchors(self):
        proc = self.child('exclusive')
        with self.assertRaises(ProjectBusy): acquire_project_use(self.path)
        anchors = list(self.locks.iterdir()); self.assertEqual(len(anchors), 2)
        self.stop(proc)
        for _ in range(3):
            with acquire_project_use(self.path, exclusive=True): pass
        self.assertEqual(set(anchors), set(self.locks.iterdir()))

    def test_interrupted_controlled_move_keeps_identity_coordination(self):
        before = fingerprint(self.path)
        proc = self.child('move'); destination = self.root / 'controlled-move'
        with self.assertRaises(ProjectBusy): acquire_project_use(destination)
        self.stop(proc)
        with acquire_project_use(destination): self.assertEqual(before, fingerprint(destination))
        with self.assertRaises(ProjectUseError): acquire_project_use(self.path)

    def test_server_close_controller_switch_and_failures_release(self):
        from corpustrail.local_app import make_server
        from corpustrail.curation.http import make_server as review_server
        other = Project.create(self.root/'other', ProjectConfig('other-fixture', 'Other', 'Synthetic topic'), created_by='fixture')
        handle = next(x['handle'] for x in self.controller.entry()['items'] if x['name'] == 'Disposable project')
        self.controller.open(handle)
        with self.assertRaises(ProjectBusy): acquire_project_use(self.path, exclusive=True)
        handle2 = next(x['handle'] for x in self.controller.entry()['items'] if x['name'] == 'Other')
        self.controller.open(handle2)
        with acquire_project_use(self.path, exclusive=True): pass
        server = make_server(controller=self.controller, port=0); server.server_close()
        with acquire_project_use(other.root, exclusive=True): pass
        with self.assertRaises(KeyError): review_server(self.project, 'absent', port=0)
        server = review_server(self.project, 'session', port=0)
        server.server_close(); server.server_close()
        with acquire_project_use(self.path, exclusive=True): pass

    def test_cli_error_and_creation_tutorial_release(self):
        from corpustrail.cli import main
        with patch.object(Project, 'status', side_effect=ValueError('fixture failure')):
            self.assertEqual(main(['project', 'status', str(self.path)]), 2)
        with acquire_project_use(self.path, exclusive=True): pass
        target = self.root/'tutorial-disposable'
        proc = self.child('tutorial', path=target)
        with self.assertRaises(ProjectBusy): acquire_project_use(target, exclusive=True)
        proc.stdin.write('\n'); proc.stdin.flush()
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err); self.assertIn('"network_used": false', out)
        with acquire_project_use(target, exclusive=True): pass

    def test_creation_unicode_and_environment_stability(self):
        original = self.patcher.temp_original
        expected = original()
        with patch.dict(os.environ, {'HOME': str(self.base), 'TEMP': str(self.base), 'XDG_STATE_HOME': str(self.base)}):
            self.assertEqual(original(), expected)
        target = self.root/'Matériaux-科学'
        with creation_use(target):
            Project.create(target, ProjectConfig('unicode-fixture', 'Unicode', 'Synthetic'), created_by='fixture')
            with self.assertRaises(ProjectBusy): acquire_project_use(target, exclusive=True)
        with acquire_project_use(target): pass

    def test_unsafe_paths_and_lock_failures(self):
        with self.assertRaises(ProjectUseError): acquire_project_use(self.root/'missing')
        with patch('corpustrail.application.project_use._kernel_lock', side_effect=OSError('private diagnostic')):
            with self.assertRaises(ProjectUseError) as e: acquire_project_use(self.path)
            self.assertNotIn('private diagnostic', str(e.exception))
        try: (self.base/'alias').symlink_to(self.path, target_is_directory=True)
        except OSError: return
        with self.assertRaises(ProjectUseError): acquire_project_use(self.base/'alias')


class FakeTrash:
    def __init__(self, base, mode='moved'): self.base, self.mode, self.calls = base, mode, 0
    def capability(self): return {'available': True, 'reason': ''}
    def move(self, path):
        self.calls += 1
        if self.mode == 'failed': return TrashResult('failed', diagnostic='native_permission')
        if self.mode == 'interrupt': raise KeyboardInterrupt()
        self.base.mkdir(exist_ok=True)
        destination = self.base/(path.name+'-renamed')
        assert not destination.exists()
        path.rename(destination)
        return TrashResult(self.mode, destination if self.mode != 'no_destination' else None)


class RemovalTests(Fixture):
    def setup_removal(self, mode='moved'):
        backend = FakeTrash(self.base/'controlled-trash', mode)
        service = ProjectRemoval(self.controller, backend)
        self.controller._removal_service = service
        handle = next(x['handle'] for x in self.controller.entry()['items'] if x['name']=='Disposable project')
        return service, backend, handle

    def test_success_renaming_data_external_and_other_projects_preserved(self):
        service, backend, handle = self.setup_removal()
        before = fingerprint(self.path)
        other = Project.create(self.root/'other', ProjectConfig('other-fixture', 'Other', 'Synthetic'), created_by='fixture')
        external = self.base/'external-import.txt'; external.write_text('Invented original', encoding='utf-8')
        try: (self.path/'external-link').symlink_to(external)
        except OSError: pass
        before = fingerprint(self.path)
        other_before = fingerprint(other.root)
        plan = service.prepare(handle)
        self.assertEqual(before, fingerprint(self.path)); self.assertEqual(backend.calls, 0)
        with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'], 'wrong')
        result = service.execute(plan['confirmation'], self.path.name)
        self.assertEqual(result['status'], 'moved'); self.assertFalse(self.path.exists())
        self.assertEqual(before, fingerprint(Path(result['destination'])))
        self.assertEqual(other_before, fingerprint(other.root)); self.assertTrue(external.is_file())
        self.assertNotIn(handle, self.controller._registered)
        self.assertEqual([x['name'] for x in self.controller.entry()['items']], ['Other'])
        with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'], self.path.name)
        self.assertEqual(backend.calls, 1)

    def test_cancel_expired_incorrect_and_replayed_confirmations(self):
        service, backend, handle = self.setup_removal()
        before = fingerprint(self.path)
        plan = service.prepare(handle); service.cancel(plan['confirmation'])
        with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'], self.path.name)
        plan = service.prepare(handle); service.tokens[plan['confirmation']]['expires'] = 0
        with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'], self.path.name)
        self.assertEqual(backend.calls, 0); self.assertEqual(before, fingerprint(self.path))

    def test_active_and_other_processes_refused_then_recover(self):
        service, backend, handle = self.setup_removal()
        self.controller.open(handle)
        with self.assertRaises(ProjectCommandError): service.prepare(handle)
        self.controller.close()
        proc = self.child('app')
        with self.assertRaises(ProjectCommandError): service.prepare(handle)
        self.stop(proc)
        plan = service.prepare(handle)
        proc = self.child('shared')
        with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'], self.path.name)
        self.stop(proc)
        self.assertEqual(backend.calls, 0)
        fresh = service.prepare(handle)
        self.assertEqual(service.execute(fresh['confirmation'], self.path.name)['status'], 'moved')

    def test_changed_target_root_scope_database_and_identity_fail_closed(self):
        for change in ('bootstrap', 'database', 'replacement', 'root'):
            with self.subTest(change=change):
                service, backend, handle = self.setup_removal()
                plan = service.prepare(handle)
                if change == 'bootstrap':
                    p = self.path/'corpustrail.project.json'; body=p.read_bytes(); p.write_bytes(body+b' ')
                elif change == 'database':
                    from dataclasses import replace
                    cfg=self.project.config
                    self.project.configure(replace(cfg,config_version=2,name='Changed'),
                        expected_event_id=self.project.configuration_history()[-1]['event_id'],created_by='fixture')
                else:
                    target = self.path if change=='replacement' else self.root
                    saved = self.base/('saved-'+change); target.rename(saved)
                    if change=='root': self.root.mkdir()
                    Project.create(self.path, ProjectConfig('replacement-fixture','Replacement','Synthetic'),created_by='fixture')
                with self.assertRaises((ProjectCommandError, ProjectUseError)): service.execute(plan['confirmation'], 'disposable')
                self.assertEqual(backend.calls, 0)
                # Each subcase uses a fresh fixture; no real-data restoration/deletion.
                if change != 'root':
                    self.path.rename(self.base/('changed-'+change))
                    Project.create(self.path,ProjectConfig('disposable-fixture','Disposable project','Synthetic topic'),created_by='fixture')

    def test_arbitrary_root_parent_outside_nonproject_software_and_symlink_refused(self):
        service, backend, handle = self.setup_removal()
        for value in (str(self.path), '../disposable', str(self.root), str(self.root.parent), None):
            with self.assertRaises(ProjectCommandError): service.prepare(value)
        for target in (self.root, self.base, self.base/'outside'):
            if not target.exists(): target.mkdir()
            h = self.controller._register(target)
            with self.assertRaises(ProjectCommandError): service.prepare(h)
        nonproject=self.root/'plain'; nonproject.mkdir()
        with self.assertRaises(ProjectCommandError): service.prepare(self.controller._register(nonproject))
        (self.path/'.git').mkdir()
        with self.assertRaises(ProjectCommandError): service.prepare(handle)
        (self.path/'.git').rmdir()  # Empty, synthetic sentinel only.
        plan = service.prepare(handle)
        saved=self.root/'saved'; self.path.rename(saved)
        try: self.path.symlink_to(saved, target_is_directory=True)
        except OSError: return
        with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'], 'disposable')
        self.assertEqual(backend.calls, 0)

    def test_failed_and_uncertain_never_fallback_or_retry(self):
        for mode in ('failed', 'uncertain', 'no_destination', 'interrupt'):
            # Separate temporary project/handle for each case, without cleanup fallbacks.
            target=self.root/('case-'+mode)
            Project.create(target,ProjectConfig('case-'+mode,'Case '+mode,'Synthetic'),created_by='fixture')
            service=ProjectRemoval(self.controller, FakeTrash(self.base/('trash-'+mode),mode))
            handle=self.controller._register(target); before=fingerprint(target)
            plan=service.prepare(handle); result=service.execute(plan['confirmation'], target.name)
            self.assertEqual(result['status'], 'failed' if mode=='failed' else 'uncertain')
            self.assertNotEqual(result['status'],'moved')
            with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'],target.name)
            if mode=='failed': self.assertEqual(before,fingerprint(target))
            else:
                with self.assertRaises(ProjectCommandError): service.prepare(handle)
            self.assertEqual(service.backend.calls,1)

    def test_evidence_inventory_change_invalidates_confirmation(self):
        service, backend, handle = self.setup_removal()
        plan = service.prepare(handle)
        (self.path/'new-evidence.txt').write_text('Invented evidence', encoding='utf-8')
        with self.assertRaises(ProjectCommandError): service.execute(plan['confirmation'], self.path.name)
        self.assertEqual(backend.calls,0)

    def test_no_permanent_deletion_or_subprocess_fallback_in_production(self):
        import ast
        from corpustrail.application import trash
        tree=ast.parse(Path(trash.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                self.assertNotIn(node.func.attr, {'rmtree','unlink','rmdir','system','Popen','run'})

    def test_platform_capability_and_missing_dependency_no_native_import(self):
        for platform in ('linux','win32'):
            with patch('corpustrail.application.trash.sys.platform',platform):
                self.assertFalse(MacOSTrash().capability()['available'])
        from importlib.metadata import PackageNotFoundError
        with patch('corpustrail.application.trash.sys.platform','darwin'), \
             patch('corpustrail.application.trash.version',side_effect=PackageNotFoundError):
            self.assertFalse(MacOSTrash().capability()['available'])
            self.assertEqual(MacOSTrash().move(self.path).status,'failed')

    def test_native_adapter_result_destination_and_errors_with_mock_bindings(self):
        destination=self.base/'native-renamed'
        class URL:
            def getResourceValue_forKey_error_(self, _, key, __): return True, key=='local', None
            def isFileURL(self): return True
            def path(self): return str(destination)
        native=types.SimpleNamespace(trashItemAtURL_resultingItemURL_error_=lambda *args: (True,URL(),None))
        foundation=types.SimpleNamespace(NSFileManager=types.SimpleNamespace(defaultManager=lambda:native),
            NSURL=types.SimpleNamespace(fileURLWithPath_=lambda _:URL()), NSURLVolumeIsLocalKey='local', NSURLIsUbiquitousItemKey='cloud')
        with patch.dict(sys.modules, {'Foundation':foundation, 'objc':types.SimpleNamespace(autorelease_pool=nullcontext)}), \
             patch.object(MacOSTrash,'capability',return_value={'available':True}):
            result=MacOSTrash().move(self.path)
            self.assertEqual(result,TrashResult('moved',destination,None))
            native.trashItemAtURL_resultingItemURL_error_=lambda *args:(False,None,types.SimpleNamespace(code=lambda:13))
            self.assertEqual(MacOSTrash().move(self.path),TrashResult('failed',None,'native_13'))


class RemovalHttpTests(RemovalTests):
    def test_versioned_csrf_host_origin_size_get_and_no_path_api(self):
        from corpustrail.local_app import make_server
        service, backend, handle=self.setup_removal()
        server=make_server(controller=self.controller,port=0)
        thread=threading.Thread(target=server.serve_forever); thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        def call(method,path,body=None,authenticated=True,extra=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            headers={'Content-Type':'application/json'}
            if authenticated: headers.update({'Origin':origin,'X-CorpusTrail-CSRF':token,'X-CorpusTrail-Session':token})
            headers.update(extra or {})
            conn.request(method,path,body=json.dumps(body) if isinstance(body,dict) else body,headers=headers)
            r=conn.getresponse(); data=r.read().decode(); status=r.status; conn.close(); return status,data
        origin='http://127.0.0.1:'+str(server.server_port)
        _,html=call('GET','/projects',authenticated=False)
        token=re.search(r'name="corpustrail-session" content="([^"]+)"',html).group(1)
        body={'schema':SCHEMA,'handle':handle}
        self.assertEqual(call('POST','/api/v1/projects/trash/prepare',body,False)[0],403)
        self.assertEqual(call('POST','/api/v1/projects/trash/prepare',body,extra={'Origin':'http://foreign.test'})[0],403)
        self.assertEqual(call('POST','/api/v1/projects/trash/prepare',body,extra={'Host':'foreign.test'})[0],403)
        self.assertEqual(call('POST','/api/v1/projects/trash/prepare','x'*65537)[0],413)
        self.assertEqual(call('GET','/api/v1/projects/trash/execute')[0],404)
        self.assertEqual(call('POST','/api/v1/projects/trash/prepare',{'schema':SCHEMA,'path':str(self.path)})[0],400)
        status,data=call('POST','/api/v1/projects/trash/prepare',body); self.assertEqual(status,200,data)
        plan=json.loads(data)
        status,_=call('POST','/api/v1/projects/trash/cancel',{'schema':SCHEMA,'confirmation':plan['confirmation']})
        self.assertEqual(status,200); self.assertEqual(backend.calls,0)
        status,data=call('POST','/api/v1/projects/trash/prepare',body); plan=json.loads(data)
        execute={'schema':SCHEMA,'confirmation':plan['confirmation'],'folder':'disposable'}
        self.assertEqual(call('POST','/api/v1/projects/trash/execute',execute,False)[0],403)
        status,data=call('POST','/api/v1/projects/trash/execute',execute)
        self.assertEqual(status,200,data); self.assertEqual(json.loads(data)['status'],'moved')
        self.assertEqual(call('POST','/api/v1/projects/trash/execute',execute)[0],409)
        self.assertEqual(backend.calls,1)


@unittest.skipUnless(sys.platform=='darwin' and os.environ.get('CORPUSTRAIL_NATIVE_TRASH_TEST')=='1',
                     'Explicit native macOS disposable-project acceptance only')
class NativeTrashTests(Fixture):
    def test_actual_native_move_returned_url_and_os_restore(self):
        self.assertTrue(MacOSTrash().capability()['available'])
        service=ProjectRemoval(self.controller)
        handle=next(x['handle'] for x in self.controller.entry()['items'] if x['name']=='Disposable project')
        external=self.base/'external-original.txt'; external.write_text('Synthetic external original',encoding='utf-8')
        (self.path/'external-link').symlink_to(external)
        before=fingerprint(self.path); plan=service.prepare(handle)
        result=service.execute(plan['confirmation'],self.path.name)
        self.assertEqual(result['status'],'moved',result)
        destination=Path(result['destination'])
        self.assertTrue(destination.is_dir()); self.assertFalse(self.path.exists())
        self.assertEqual(before,fingerprint(destination))
        self.assertEqual(external.read_text(encoding='utf-8'),'Synthetic external original')
        # Restore only this exact disposable destination, never overwrite anything.
        self.assertFalse(self.path.exists()); destination.rename(self.path)
        self.assertEqual(Project.open(self.path).config.project_id,'disposable-fixture')


if __name__=='__main__': unittest.main()
