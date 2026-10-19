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
    def test_geometry_uses_the_exact_capture_mask_visibility_engine(self):
        from tools.browser_acceptance import Runtime,PRIVACY_MASK
        page=Mock();page.evaluate.return_value={'viewport':[1280,800],'content':[1280,2844]}
        page.locator.return_value.filter.return_value.evaluate_all.return_value=[[80,1002,1120,24]]
        geometry=Runtime.capture_geometry(page)
        page.locator.assert_called_once_with(PRIVACY_MASK)
        page.locator.return_value.filter.assert_called_once_with(visible=True)
        self.assertEqual(geometry['masks'],[[80,1002,1120,24]])

    def test_navigation_click_completes_prior_reads_and_keeps_failed_waits_visible(self):
        from .acceptance import BrowserAcceptance
        case=object.__new__(BrowserAcceptance);case.page=Mock();case.settle_reads=Mock()
        order=Mock();order.attach_mock(case.settle_reads,'settle');order.attach_mock(case.page,'page')
        case.click_after_reads('#review-finish')
        self.assertEqual([call[0] for call in order.mock_calls],['settle','page.locator','page.locator().click'])
        case.page.reset_mock();case.settle_reads.side_effect=AssertionError('unfinished read')
        with self.assertRaisesRegex(AssertionError,'unfinished read'):case.click_after_reads('#review-finish')
        case.page.locator.assert_not_called()

    def capture_double(self,*,changed_geometry=False,read_failure=False):
        from unittest.mock import patch
        from tools.browser_acceptance import Runtime
        runtime=object.__new__(Runtime);runtime.output=self.root;runtime.viewport_name='desktop'
        (self.root/'screenshots').mkdir()
        runtime.environment={'browser':'controlled'};runtime.mode='capture';runtime.screenshots=[]
        page=Mock();page.evaluate.return_value=1
        pending={'real-read'};events=[]
        def ready():
            events.append('readiness')
            if read_failure:raise AssertionError('unfinished read')
            pending.clear()
        def screenshot(**options):
            self.assertFalse(pending,'Cannot measure/mask an unfinished render')
            self.assertEqual(options['mask_color'],'#e2ecee')
            events.append('capture');Image.new('RGB',(20,20),'white').save(options['path'])
        page.screenshot.side_effect=screenshot
        before={'content':[1280,2844],'masks':[[0,1002,10,24]]}
        after={'content':[1280,2804],'masks':[[0,962,10,24]]} if changed_geometry else before
        case=types.SimpleNamespace(page=page,settle_reads=ready,assertEqual=self.assertEqual)
        with patch.object(runtime,'capture_geometry',side_effect=(before,after)):
            if read_failure or changed_geometry:
                with self.assertRaisesRegex(AssertionError,'unfinished read|geometry changed'):
                    runtime.snapshot(case,'controlled-readiness')
            else:runtime.snapshot(case,'controlled-readiness')
        return page,events,runtime

    def test_capture_waits_for_prior_reads_before_measuring_and_masking(self):
        page,events,runtime=self.capture_double()
        self.assertEqual(events,['readiness','capture'])
        self.assertEqual(len(runtime.screenshots),1)
        self.assertIn('delete window.__ctScreenshotNodes',page.evaluate.call_args[0][0])

    def test_capture_does_not_bypass_unfinished_reads(self):
        page,events,runtime=self.capture_double(read_failure=True)
        self.assertEqual(events,['readiness']);page.screenshot.assert_not_called()
        self.assertEqual(runtime.screenshots,[])

    def test_changed_mask_geometry_fails_without_retry_and_restores_text(self):
        page,events,runtime=self.capture_double(changed_geometry=True)
        self.assertEqual(events,['readiness','capture']);page.screenshot.assert_called_once()
        self.assertIn('delete window.__ctScreenshotNodes',page.evaluate.call_args[0][0])
        self.assertTrue((self.root/'screenshots/desktop-controlled-readiness.png').exists())
        self.assertEqual(runtime.screenshots,[])

    def test_provenance_click_waits_for_rendered_history_and_completed_reads(self):
        from unittest.mock import patch
        from .acceptance import BrowserAcceptance
        case=object.__new__(BrowserAcceptance)
        case.page=Mock()
        case.settle_reads=Mock()
        order=Mock()
        rendered=Mock()
        opened=Mock()
        with patch('browser_tests.acceptance.expect',side_effect=(rendered,opened)):
            order.attach_mock(rendered,'rendered')
            order.attach_mock(case.settle_reads,'settle')
            order.attach_mock(case.page.locator.return_value,'target')
            order.attach_mock(opened,'opened')
            case.open_paper_provenance()
        self.assertEqual([call[0] for call in order.mock_calls],
            ['rendered.to_be_visible','settle','target.click','opened.to_have_attribute'])
        self.assertEqual(case.page.locator.call_args_list,
            [unittest.mock.call('#evidence-history li'),unittest.mock.call('#advanced > summary'),
             unittest.mock.call('#advanced')])
        opened.to_have_attribute.assert_called_once_with('open','')

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

    def test_repeated_capture_path_is_refused_before_browser_use(self):
        from tools.browser_acceptance import Runtime
        self.candidate()
        path=self.root/'screenshots'/'desktop-example.png'
        before=path.read_bytes()
        runtime=object.__new__(Runtime)
        runtime.viewport_name='desktop';runtime.output=self.root
        with self.assertRaisesRegex(AssertionError,'distinct capture name'):
            runtime.snapshot(None,'example')
        self.assertEqual(path.read_bytes(),before)

    def test_repeated_capture_record_cannot_be_approved(self):
        self.candidate(screenshots=[{'path':'screenshots/desktop-example.png'}]*2)
        with self.assertRaisesRegex(ValueError,'Repeated screenshot path'):
            approve(self.root,self.root/'approved',reviewed=True)
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

    def test_discovery_fixture_clock_controls_stored_plan_and_restores_on_close(self):
        from corpustrail.application import discovery
        from corpustrail._internal import values
        from .fixtures import ApplicationFixture, AT
        original=discovery.now
        fixture=ApplicationFixture()
        try:
            fixture.freeze_discovery_clock()
            self.assertEqual(discovery.now(),AT)
            self.assertIs(values.now,original)  # Do not replace scientific/global time.
            preview=fixture.discovery.prepare(fixture.project,
                request_id='fixed-discovery-clock',
                config_event_id=fixture.project.configuration_history()[-1]['event_id'],
                query='synthetic transport diagnostic',providers=['europepmc'],
                bounds=dict(discovery.BOUNDS))
            self.assertEqual(preview['plan']['created_at'],AT)
            self.assertEqual(preview['plan']['providers'][0]['plan']['created_at'],AT)
            self.assertEqual(fixture.discovery.history(fixture.project)['items'][0]['created_at'],AT)
            self.assertEqual(fixture.transport.calls,[])
        finally:
            fixture.close()
        self.assertIs(discovery.now,original)

    def test_navigation_wait_observes_new_requests_and_continuous_quiet(self):
        from unittest.mock import patch
        from .lifecycle import settle_reads
        clock=[0.0];request=object();pending=set()
        def pump(milliseconds):
            clock[0]+=milliseconds/1000
            if .2<=clock[0]<.8:pending.add(request)
            else:pending.discard(request)
        case=types.SimpleNamespace(pending_requests=pending,
            page=types.SimpleNamespace(wait_for_timeout=pump),fail=self.fail)
        with patch('browser_tests.lifecycle.time.monotonic',side_effect=lambda:clock[0]):
            settle_reads(case)
        self.assertGreaterEqual(clock[0],1.3)
        self.assertFalse(pending)

    def test_navigation_wait_is_bounded_and_does_not_hide_unfinished_requests(self):
        from unittest.mock import patch
        from .lifecycle import settle_reads
        clock=[0.0];pending={object()}
        def pump(milliseconds):clock[0]+=milliseconds/1000
        case=types.SimpleNamespace(pending_requests=pending,navigation_timeouts=[],
            request_ledger=types.SimpleNamespace(snapshot=lambda:{'pending_count':1}),
            page=types.SimpleNamespace(wait_for_timeout=pump),fail=self.fail)
        with patch('browser_tests.lifecycle.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(AssertionError,'requests did not finish'):
                settle_reads(case)
        self.assertLessEqual(clock[0],10.1)
        self.assertTrue(pending)
        self.assertEqual(case.navigation_timeouts,[{'pending_count':1}])

    def test_navigation_wait_credits_observed_quiet_after_pumping_events(self):
        from unittest.mock import patch
        from .lifecycle import RequestLedger, settle_reads
        clock=[0.0]
        ledger=RequestLedger('http://127.0.0.1:1234',clock=lambda:clock[0])
        clock[0]=2.0
        pumps=[]
        def pump(milliseconds):
            pumps.append(milliseconds);clock[0]+=milliseconds/1000
        case=types.SimpleNamespace(pending_requests=ledger.pending,request_ledger=ledger,
            page=types.SimpleNamespace(wait_for_timeout=pump),fail=self.fail)
        with patch('browser_tests.lifecycle.time.monotonic',side_effect=lambda:clock[0]):
            settle_reads(case)
        self.assertEqual(pumps,[50])  # Drain events even when prior quiet is sufficient.
        self.assertGreaterEqual(clock[0]-ledger.last_activity,.5)

    def test_navigation_wait_new_and_same_pump_requests_reset_observed_quiet(self):
        from unittest.mock import patch
        from .lifecycle import RequestLedger, settle_reads
        for complete_in_same_pump in (False,True):
            with self.subTest(complete_in_same_pump=complete_in_same_pump):
                clock=[0.0];events=[]
                ledger=RequestLedger('http://127.0.0.1:1234',clock=lambda:clock[0])
                # Request objects, like Playwright's, must be stable dictionary keys.
                request=Mock(url='http://127.0.0.1:1234/api/v1/review',method='GET')
                clock[0]=2.0
                def pump(milliseconds):
                    clock[0]+=milliseconds/1000
                    if not events:
                        ledger.begin(request);events.append('begin')
                    if ledger.pending and (complete_in_same_pump or clock[0]>=2.4):
                        ledger.response(types.SimpleNamespace(request=request,status=200))
                        ledger.end(request,'finished');events.append('finished')
                case=types.SimpleNamespace(pending_requests=ledger.pending,request_ledger=ledger,
                    page=types.SimpleNamespace(wait_for_timeout=pump),fail=self.fail)
                with patch('browser_tests.lifecycle.time.monotonic',side_effect=lambda:clock[0]):
                    settle_reads(case)
                self.assertEqual(events,['begin','finished'])
                self.assertGreaterEqual(clock[0]-ledger.last_activity,.5)
                self.assertFalse(ledger.pending)
                self.assertGreaterEqual(clock[0],2.55 if complete_in_same_pump else 2.9)

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

    def test_request_ledger_reports_pending_response_and_completion_without_secrets(self):
        from .lifecycle import RequestLedger
        clock=[0.0]
        ledger=RequestLedger('http://127.0.0.1:1234',clock=lambda:clock[0])
        # Hashable browser Request stand-in; no browser dependency for this check.
        request=Mock(url='http://127.0.0.1:1234/api/v1/review/sessions/private-path?token=private-value',method='GET')
        ledger.begin(request);clock[0]=2
        ledger.response(types.SimpleNamespace(request=request,status=200))
        report=ledger.snapshot()
        self.assertEqual(report['pending'][0]['response_status'],200)
        self.assertEqual(report['pending'][0]['age_seconds'],2)
        self.assertNotIn('private',json.dumps(report))
        self.assertTrue(report['pending'][0]['query_present'])
        ledger.end(request,'finished');ledger.end(request,'finished')
        self.assertEqual(ledger.snapshot()['pending_count'],0)
        self.assertEqual(ledger.snapshot()['unmatched_completions'],1)
        self.assertEqual(ledger.snapshot()['recent'][0]['event'],'finished')

    def test_reference_request_diagnostics_keep_routes_but_not_handles_or_queries(self):
        from .lifecycle import RequestLedger
        ledger=RequestLedger('http://127.0.0.1:1234')
        request=Mock(url='http://127.0.0.1:1234/api/v1/references/versions/private-handle/members?secret=private-value',method='GET')
        ledger.begin(request)
        report=ledger.snapshot()
        self.assertEqual(report['pending'][0]['route'],'/api/v1/references/versions/<id>/members')
        self.assertTrue(report['pending'][0]['query_present'])
        self.assertNotIn('private',json.dumps(report))
        self.assertNotIn('secret',json.dumps(report))

    def controlled_failure(self, *, screenshot_error=False, trace_error=False, in_teardown=False):
        """Real unittest failure plumbing, with a clock/event-pump double only."""
        from unittest.mock import patch
        from .lifecycle import RequestLedger, finalize_case, settle_reads
        from tools.browser_acceptance import Runtime
        output=self.root/'controlled';output.mkdir()
        runtime=Runtime(types.SimpleNamespace(version='test-renderer'),output,'capture','all',['desktop'])
        runtime.viewport_name='desktop'
        clock=[0.0]
        fixture=types.SimpleNamespace(base=self.root,origin='http://127.0.0.1:1234',errors=[],
            transport=types.SimpleNamespace(calls=[],errors=[]))
        context=Mock();page=Mock()
        def trace(*,path):
            if trace_error:raise RuntimeError('private trace exception')
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('trace.json','{"session":"private-token"}')
        context.tracing.stop.side_effect=trace
        def screenshot(**args):
            if screenshot_error:raise TimeoutError('private screenshot exception')
            Image.new('RGB',(10,10),'white').save(args['path'])
        page.screenshot.side_effect=screenshot
        page.wait_for_timeout.side_effect=lambda milliseconds:clock.__setitem__(0,clock[0]+milliseconds/1000)
        class Controlled(unittest.TestCase):
            def runTest(self):
                if not in_teardown:settle_reads(self)
            def tearDown(self):finalize_case(self)
        case=Controlled();case.fixture=fixture;case.page=page;case.context=context;case.runtime=runtime
        case.tokens={'private-token'};case.diagnostics=[];case.navigation_timeouts=[];case.local_requests=1
        case.request_ledger=RequestLedger(fixture.origin,clock=lambda:clock[0])
        request=Mock(url=fixture.origin+'/api/v1/dashboard?private-query',method='GET')
        case.request_ledger.begin(request);case.pending_requests=case.request_ledger.pending
        case.settle_reads=lambda:settle_reads(case)
        result=unittest.TestResult()
        with patch('browser_tests.lifecycle.time.monotonic',side_effect=lambda:clock[0]):case.run(result)
        self.assertEqual(len(result.failures),1);self.assertEqual(result.errors,[])
        self.assertIn('requests did not finish',result.failures[0][1])
        self.assertLessEqual(clock[0],10.1)  # No second ten-second teardown wait.
        self.assertFalse(runtime.cases[0]['passed'])
        self.assertEqual(len(case.navigation_timeouts),1)
        pending=json.loads((output/'diagnostics'/'desktop-runTest-requests.json').read_text(encoding='utf-8'))
        self.assertEqual(pending['at_failure'][0]['pending_count'],1)
        self.assertNotIn('private',json.dumps(pending))
        page.screenshot.assert_called_once();context.tracing.stop.assert_called_once()
        self.assertEqual(page.screenshot.call_args.kwargs['timeout'],3000)
        self.assertIn('mask',page.screenshot.call_args.kwargs)
        return output,runtime,case,result

    def test_original_navigation_failure_survives_screenshot_failure_and_trace_is_saved(self):
        output,runtime,case,result=self.controlled_failure(screenshot_error=True)
        self.assertEqual(runtime.cases[0]['diagnostic_errors'],['Failure screenshot: TimeoutError'])
        with zipfile.ZipFile(output/'traces'/'desktop-runTest.zip') as trace:
            self.assertNotIn(b'private-token',trace.read('trace.json'))
        self.assertNotIn('private screenshot exception',json.dumps(runtime.cases))

    def test_teardown_wait_failure_still_preserves_screenshot_when_trace_fails(self):
        output,runtime,case,result=self.controlled_failure(trace_error=True,in_teardown=True)
        self.assertTrue((output/'failures'/'desktop-runTest.png').is_file())
        self.assertEqual(runtime.cases[0]['diagnostic_errors'],['Trace finalization: RuntimeError'])
        self.assertFalse((output/'traces'/'desktop-runTest.zip').exists())

    def test_context_cleanup_failure_is_recorded_without_replacing_primary_failure(self):
        output,runtime,case,result=self.controlled_failure()
        case.context.close.side_effect=TimeoutError('private cleanup exception')
        # unittest clears _outcome after run; recreate its completed result here.
        case._outcome=types.SimpleNamespace(result=result)
        runtime.close_context(case)
        self.assertEqual(len(result.failures),1)
        self.assertIn('Context cleanup: TimeoutError',runtime.cases[0]['diagnostic_errors'])
        self.assertTrue((output/'diagnostics'/'desktop-runTest-cleanup.json').exists())

    def test_diagnostic_deadline_interrupts_and_restores_signal_handler(self):
        import signal
        import time
        from .lifecycle import diagnostic_deadline
        previous=signal.getsignal(signal.SIGALRM);started=time.monotonic()
        with self.assertRaises(TimeoutError),diagnostic_deadline(.02):signal.pause()
        self.assertLess(time.monotonic()-started,1)
        self.assertEqual(signal.getsignal(signal.SIGALRM),previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))


if __name__=='__main__':unittest.main()
