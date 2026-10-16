"""Developer-only self-tests for visual failure sensitivity and approval guards."""
import json
from pathlib import Path
import tempfile
import unittest
import types
import zipfile
from unittest.mock import Mock
from PIL import Image, ImageDraw
from .visual import approve, compare


class VisualInfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ct-visual-unit-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.before=self.root/'before.png';self.after=self.root/'after.png'
        self.difference=self.root/'difference.png'

    def test_identical_images_pass(self):
        image=Image.new('RGB',(200,200),'white');image.save(self.before);image.save(self.after)
        self.assertTrue(compare(self.before,self.after,self.difference)['passed'])
        self.assertFalse(self.difference.exists())

    def test_small_channel_noise_but_not_layout_shift_is_tolerated(self):
        Image.new('RGB',(200,200),(255,255,255)).save(self.before)
        Image.new('RGB',(200,200),(250,250,250)).save(self.after)
        self.assertTrue(compare(self.before,self.after,self.difference)['passed'])
        image=Image.open(self.after);ImageDraw.Draw(image).rectangle((20,20,60,60),fill='black');image.save(self.after)
        self.assertFalse(compare(self.before,self.after,self.difference)['passed'])
        self.assertTrue(self.difference.is_file())

    def test_concentrated_small_control_change_fails_local_tile_budget(self):
        Image.new('RGB',(1440,900),'white').save(self.before)
        image=Image.new('RGB',(1440,900),'white');ImageDraw.Draw(image).rectangle((1,1,20,20),fill='black');image.save(self.after)
        result=compare(self.before,self.after,self.difference)
        self.assertLess(result['changed_ratio'],.0005)
        self.assertFalse(result['passed'])

    def test_changed_dimensions_fail(self):
        Image.new('RGB',(200,200),'white').save(self.before)
        Image.new('RGB',(201,200),'white').save(self.after)
        self.assertFalse(compare(self.before,self.after,self.difference)['passed'])

    def candidate(self,**changes):
        (self.root/'screenshots').mkdir(exist_ok=True)
        Image.new('RGB',(10,10),'white').save(self.root/'screenshots'/'desktop-example.png')
        value={'mode':'capture','passed':True,'suite':'all','viewports':['desktop','laptop','narrow'],
               'environment':{'platform':'linux','browser':'chromium'},'screenshots':[{'path':'screenshots/desktop-example.png'}]}
        value.update(changes)
        (self.root/'report.json').write_text(json.dumps(value),encoding='utf-8')

    def test_explicit_review_is_required_and_manifest_records_hashes(self):
        self.candidate()
        with self.assertRaises(ValueError):approve(self.root,self.root/'approved',reviewed=False)
        approve(self.root,self.root/'approved',reviewed=True)
        value=json.loads((self.root/'approved'/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(value['images_sha256']['desktop-example.png']),64)

    def test_failed_compare_partial_or_other_platform_cannot_be_approved(self):
        for change in ({'passed':False},{'mode':'compare'},{'suite':'evidence'},
                       {'viewports':['desktop']},{'environment':{'platform':'unknown','browser':'chromium'}}):
            self.candidate(**change)
            with self.assertRaises(ValueError):approve(self.root,self.root/'approved',reviewed=True)
        self.assertFalse((self.root/'approved').exists())

    def test_platform_and_engine_baselines_are_separate_and_require_review(self):
        from tools.browser_acceptance import baseline_directory
        for engine in ('chromium','webkit'):
            self.candidate(environment={'platform':'darwin','browser':engine})
            self.assertEqual(baseline_directory({'platform':'darwin','browser':engine}).name,'darwin-'+engine)
            with self.assertRaises(ValueError):approve(self.root,self.root/engine,reviewed=False)
            approve(self.root,self.root/engine,reviewed=True)

    def test_webkit_adapter_is_pinned_in_memory_and_restores_environment(self):
        import hashlib
        import os
        import playwright
        from playwright.sync_api import sync_playwright
        from .webkit_screenshots import driver_environment,BUNDLE_SHA256
        bundle=Path(playwright.__file__).parent/'driver/package/lib/coreBundle.js'
        before=hashlib.sha256(bundle.read_bytes()).hexdigest()
        self.assertEqual(before,BUNDLE_SHA256)
        previous=os.environ.get('NODE_OPTIONS')
        with driver_environment('webkit'),sync_playwright() as driver:
            self.assertEqual(driver.webkit.name,'webkit')
        self.assertEqual(os.environ.get('NODE_OPTIONS'),previous)
        self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(),before)

    def test_webkit_adapter_refuses_unreviewed_driver_or_node_options(self):
        from unittest.mock import patch
        from .webkit_screenshots import driver_environment
        with patch('browser_tests.webkit_screenshots.version',return_value='unreviewed'):
            with self.assertRaises(ValueError),driver_environment('webkit'):pass
        with patch.dict('os.environ',{'NODE_OPTIONS':'--unexpected'}):
            with self.assertRaises(ValueError),driver_environment('webkit'):pass

    def test_navigation_wait_observes_new_requests_and_continuous_quiet(self):
        from unittest.mock import patch
        from .acceptance import BrowserAcceptance
        clock=[0.0];request=object();pending=set()
        def pump(milliseconds):
            clock[0]+=milliseconds/1000
            if .2<=clock[0]<.8:pending.add(request)
            else:pending.discard(request)
        case=types.SimpleNamespace(pending_requests=pending,
            page=types.SimpleNamespace(wait_for_timeout=pump),fail=self.fail)
        with patch('browser_tests.acceptance.time.monotonic',side_effect=lambda:clock[0]):
            BrowserAcceptance.settle_reads(case)
        self.assertGreaterEqual(clock[0],1.3)
        self.assertFalse(pending)

    def test_navigation_wait_is_bounded_and_does_not_hide_unfinished_requests(self):
        from unittest.mock import patch
        from .acceptance import BrowserAcceptance
        clock=[0.0];pending={object()}
        def pump(milliseconds):clock[0]+=milliseconds/1000
        case=types.SimpleNamespace(pending_requests=pending,
            page=types.SimpleNamespace(wait_for_timeout=pump),fail=self.fail)
        with patch('browser_tests.acceptance.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(AssertionError,'requests did not finish'):
                BrowserAcceptance.settle_reads(case)
        self.assertLessEqual(clock[0],10.1)
        self.assertTrue(pending)

    def test_candidate_paths_and_symlinks_are_confined(self):
        self.candidate(screenshots=[{'path':'../outside.png'}])
        with self.assertRaises(ValueError):approve(self.root,self.root/'approved',reviewed=True)
        self.candidate()
        image=self.root/'screenshots'/'desktop-example.png';image.unlink();image.symlink_to(self.root/'before.png')
        with self.assertRaises(ValueError):approve(self.root,self.root/'approved',reviewed=True)

    def test_failure_artifacts_exist_and_ephemeral_session_is_redacted(self):
        from tools.browser_acceptance import Runtime
        output=self.root/'report';output.mkdir()
        runtime=Runtime(types.SimpleNamespace(version='test-renderer'),output,'capture','all',['desktop'])
        runtime.viewport_name='desktop'
        token='ephemeral-browser-session-fixture'
        context=Mock()
        def trace(*,path):
            with zipfile.ZipFile(path,'w') as archive:archive.writestr('trace.json','{"session":"'+token+'"}')
        context.tracing.stop.side_effect=trace
        page=Mock()
        page.screenshot.side_effect=lambda **args:Image.new('RGB',(10,10),'white').save(args['path'])
        case=types.SimpleNamespace(tokens={token},fixture=types.SimpleNamespace(base=self.root,origin='http://127.0.0.1:1',
            transport=types.SimpleNamespace(calls=[],errors=[]),errors=[]),page=page,context=context,
            local_requests=1,_testMethodName='synthetic_failure')
        case._outcome=types.SimpleNamespace(result=types.SimpleNamespace(failures=[(case,'Synthetic failure')],errors=[]))
        runtime.finish_case(case,['Console: '+token])
        with zipfile.ZipFile(output/'traces'/'desktop-synthetic_failure.zip') as archive:
            self.assertNotIn(token.encode(),archive.read('trace.json'))
        self.assertTrue((output/'failures'/'desktop-synthetic_failure.png').is_file())
        self.assertNotIn(token,(output/'diagnostics'/'desktop-synthetic_failure.txt').read_text(encoding='utf-8'))
        self.assertFalse(runtime.cases[0]['passed'])


if __name__=='__main__':unittest.main()
