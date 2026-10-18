"""Opt-in Python Playwright runner over an installed wheel and real loopback API."""
import argparse
import hashlib
import html
import io
import json
import os
from pathlib import Path
import platform
import ssl
import xml.parsers.expat
from importlib.metadata import version
import re
import sys
import subprocess
import time
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VIEWPORTS={'desktop':{'width':1440,'height':900},'laptop':{'width':1280,'height':800},'narrow':{'width':390,'height':844}}
BASELINES=ROOT/'browser_tests'/'baselines'/'linux-chromium'
PRIVACY_MASK='#root-location,#intended-location,#trash-location,#configuration-location,#configuration-definition,#project-list .project-location,#summary dl dd:last-child,#evidence-raw,#plan-details,#document-position,#technical-identifiers input,#population-header,#population-lineage,#population-issues'


def baseline_directory(environment):
    if environment.get('platform') not in {'linux','darwin'} or environment.get('browser') not in {'chromium','webkit'}:
        raise ValueError('Unsupported baseline platform or browser')
    return ROOT/'browser_tests'/'baselines'/(environment['platform']+'-'+environment['browser'])
LIMITED={'laptop':{'welcome','wizard-reviewer','wizard-summary','empty-dashboard','catalogue','discovery-preview','discovery-approval','evidence-availability','evidence-result','evidence-mismatch','missing-pmcid'},
         'narrow':{'welcome','projects','wizard','wizard-reviewer','wizard-summary','empty-dashboard','settings','catalogue','trash-confirmation','discovery-preview','discovery-approval','evidence-availability','evidence-result','evidence-mismatch','missing-pmcid'}}
for names in LIMITED.values():
    names.add('evidence-footnotes')
    names.update({'review-session-selection','review-session-selection-skip','review-session-selection-unauthorized',
        'review-active','review-verified-text','review-long-title',
        'review-missing-evidence','review-assessment','review-summary','review-completed','review-publication',
        'review-unauthorized','review-empty','review-finished-dashboard','review-confirmed',
        'journal-results','journal-no-results','review-completed-overview'})
    names.update({'population-empty','population-preview','population-frozen','population-combined',
        'population-history','population-review','population-conflict','population-upgrade'})
    names.update({'population-lineage','population-review-selection','population-successor','population-review-completed',
                  'population-upgraded','discovery-transport-error'})


class Runtime:
    def __init__(self,browser,output,mode,suite,viewports,engine='chromium'):
        from browser_tests.visual import rendering_environment
        self.browser=browser;self.output=output;self.mode=mode;self.suite=suite;self.viewports=viewports
        self.environment=rendering_environment(browser.version,engine)
        self.baseline_directory=baseline_directory(self.environment)
        self.screenshots=[];self.cases=[];self.comparisons=[]
        self.baselines=None
        if mode=='compare':
            self.baselines=json.loads((self.baseline_directory/'manifest.json').read_text(encoding='utf-8'))
            if self.baselines['environment']!=self.environment:
                raise ValueError('Renderer differs from its reviewed platform/engine baseline. Capture and review explicitly; never silently update.')
        for folder in ('screenshots','failures','traces','diagnostics'):(output/folder).mkdir(parents=True)

    def snapshot(self,case,name,full_page=True,subject=None,anchor=None):
        if self.viewport_name in LIMITED and name not in LIMITED[self.viewport_name]:return
        path=self.output/'screenshots'/(self.viewport_name+'-'+name+'.png')
        if path.exists() or path.is_symlink():
            raise AssertionError('Screenshot path already exists; use a distinct capture name: '+path.name)
        page=case.page
        if self.environment['browser']=='webkit':
            case.assertEqual(page.evaluate('document.getAnimations().filter(a=>a.playState==="running").length'),0,
                'Pinned WebKit screenshot adapter requires the reduced-motion page to have no running animations')
        page.wait_for_load_state('networkidle')
        if sys.platform=='linux' and self.environment['browser']=='chromium':
            session=case.context.new_cdp_session(page)
            try:
                session.send('DOM.enable');session.send('CSS.enable')
                document=session.send('DOM.getDocument')
                page.evaluate('''() => {
                  const p=[...document.querySelectorAll('main p')].find(e=>e.getClientRects().length&&e.textContent.trim()&&Number(getComputedStyle(e).fontWeight)<600);
                  if(!p)throw Error('Normal text font probe unavailable');p.setAttribute('data-ct-font-probe','');
                }''')
                node=session.send('DOM.querySelector',{'nodeId':document['root']['nodeId'],'selector':'[data-ct-font-probe]'})
                fonts=session.send('CSS.getPlatformFontsForNode',{'nodeId':node['nodeId']})['fonts']
                case.assertTrue(fonts and all(f['familyName']=='DejaVu Sans' for f in fonts),'Linux test font fallback differs from controlled renderer')
            finally:
                page.evaluate('document.querySelector("[data-ct-font-probe]")?.removeAttribute("data-ct-font-probe")')
                session.detach()
        if full_page:
            page.evaluate('window.scrollTo(0,0)')
            page.evaluate('() => new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        # Controlled rendering only, not frontend API mocking or science edits.
        # Preserve geometry/content; normalize transient dates/elapsed times and
        # mask opaque raw payloads, hashes and disposable machine-specific paths.
        old=page.evaluate('''() => {
          const nodes=[],walk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
          while(walk.nextNode()){const n=walk.currentNode;const text=n.textContent;
            const clean=text.replace(/\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})/g,'2026-01-01T00:00:00+00:00').replace(/\\d+(?:\\.\\d+)? seconds elapsed/g,'0 seconds elapsed');
            if(clean!==text){nodes.push([n,text]);n.textContent=clean;}}
          window.__ctScreenshotNodes=nodes;return nodes.length;
        }''')
        if anchor:
            page.locator(anchor).evaluate('''element => {
                const padding=parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop)||0;
                window.scrollTo(0,element.getBoundingClientRect().top+window.scrollY-padding);
            }''')
            page.evaluate('() => new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        masks=page.locator(PRIVACY_MASK).filter(visible=True)
        try:
            if subject:
                page.locator(subject).screenshot(path=str(path),animations='disabled',caret='hide',mask=[masks],mask_color='#e2ecee')
            else:
                page.screenshot(path=str(path),full_page=full_page,animations='disabled',caret='hide',mask=[masks],mask_color='#e2ecee')
        finally:
            if old:page.evaluate('''() => {for(const [n,text] of window.__ctScreenshotNodes)n.textContent=text;delete window.__ctScreenshotNodes;}''')
        record={'name':name,'viewport':self.viewport_name,'path':str(path.relative_to(self.output)),'subject':subject or 'page'}
        self.screenshots.append(record)
        if self.mode=='compare':
            from browser_tests.visual import compare
            expected=self.baseline_directory/path.name
            wanted=self.baselines['images_sha256'].get(path.name)
            if not wanted or not expected.is_file() or hashlib.sha256(expected.read_bytes()).hexdigest()!=wanted:
                raise AssertionError('Reviewed baseline missing or hash changed: '+path.name)
            result=compare(expected,path,self.output/'failures'/(path.stem+'-diff.png'))
            self.comparisons.append({**record,**result})
            case.assertTrue(result['passed'],'Visual regression '+path.name+': '+json.dumps(result))

    def redact(self,value,case):
        for token in case.tokens:value=value.replace(token,'<redacted-session>')
        value=value.replace(str(case.fixture.base),'<disposable-root>').replace(case.fixture.origin,'<local-origin>')
        value=value.replace(str(ROOT),'<source>').replace(sys.prefix,'<test-environment>')
        return value

    def finish_case(self,case,errors,failed=False):
        from browser_tests.lifecycle import diagnostic_deadline
        result=case._outcome.result
        failed=failed or bool(errors) or any(test is case for test,_ in result.failures+result.errors)
        name=self.viewport_name+'-'+case._testMethodName
        trace=self.output/'traces'/(name+'.zip')
        diagnostic_errors=[]
        def attempt(label,operation):
            try:
                with diagnostic_deadline(5):operation()
            except Exception as error:
                # Exception messages may include protocol URLs, paths or tokens.
                diagnostic_errors.append(label+': '+type(error).__name__)
        ledger=getattr(case,'request_ledger',None)
        requests={'schema':'corpustrail-browser-request-lifecycle/v1',
            'at_failure':getattr(case,'navigation_timeouts',[]),
            'at_finalization':ledger.snapshot() if ledger else None}
        # Persist metadata BEFORE invoking any fallible browser protocol command.
        (self.output/'diagnostics'/(name+'-requests.json')).write_text(json.dumps(requests,indent=2)+'\n',encoding='utf-8')
        if failed:
            attempt('Failure screenshot',lambda:case.page.screenshot(
                path=str(self.output/'failures'/(name+'.png')),full_page=True,timeout=3000,
                mask=[case.page.locator(PRIVACY_MASK).filter(visible=True)],mask_color='#e2ecee'))
            # Raw protocol bytes never enter the uploaded report. Only a fully
            # sanitized archive is published, even if trace finalization fails.
            raw_trace=case.fixture.base/(name+'-private-trace.zip')
            attempt('Trace finalization',lambda:case.context.tracing.stop(path=str(raw_trace)))
            # Browser protocol archives can contain ephemeral local session
            # values. Redact before publishing; no network/body snapshots enabled.
            def sanitize():
                rewritten=io.BytesIO()
                with zipfile.ZipFile(raw_trace) as source,zipfile.ZipFile(rewritten,'w',zipfile.ZIP_DEFLATED) as target:
                    for entry in source.infolist():
                        body=source.read(entry.filename)
                        for token in case.tokens:body=body.replace(token.encode(),b'<redacted-session>')
                        try:body=self.redact(body.decode('utf-8'),case).encode('utf-8')
                        except UnicodeDecodeError:pass  # Synthetic screenshot bytes.
                        target.writestr(entry.filename,body)
                trace.write_bytes(rewritten.getvalue())
            if raw_trace.is_file():attempt('Trace sanitization',sanitize)
        else:attempt('Trace finalization',lambda:case.context.tracing.stop())
        diagnostic=self.redact('\n'.join(errors),case)
        (self.output/'diagnostics'/(name+'.txt')).write_text(diagnostic or 'No browser/runtime/network errors.\n',encoding='utf-8')
        (self.output/'diagnostics'/(name+'-collection.json')).write_text(json.dumps(diagnostic_errors,indent=2)+'\n',encoding='utf-8')
        self.cases.append({'scenario':case._testMethodName,'viewport':self.viewport_name,'passed':not (failed or diagnostic_errors),
            'errors':diagnostic.splitlines(),'diagnostic_errors':diagnostic_errors,
            'controlled_provider_requests':len(case.fixture.transport.calls),
            'csp_enforcement_checks':getattr(case,'csp_enforcement_checks',0),
            'local_http_requests':case.local_requests,
            'unexpected_external_requests':getattr(case,'external_requests',0)+len(case.fixture.errors)+len(case.fixture.transport.errors)})
        return diagnostic_errors

    def close_context(self,case):
        from browser_tests.lifecycle import already_failed, diagnostic_deadline
        try:
            with diagnostic_deadline(5):case.context.close()
        except Exception as error:
            failure='Context cleanup: '+type(error).__name__
            name=self.viewport_name+'-'+case._testMethodName
            (self.output/'diagnostics'/(name+'-cleanup.json')).write_text(json.dumps([failure])+'\n',encoding='utf-8')
            for record in self.cases:
                if record['scenario']==case._testMethodName and record['viewport']==self.viewport_name:
                    record['passed']=False;record['diagnostic_errors'].append(failure)
            if not already_failed(case):case.fail(failure)

    def report(self,passed,logs):
        # unittest tracebacks are synthetic but should not leak local home paths.
        logs=logs.replace(str(ROOT),'<source>').replace(sys.prefix,'<test-environment>')
        logs=re.sub(r'/tmp/ct-browser-disposable-[^/\s]+','<disposable-root>',logs)
        value={'schema':'corpustrail-browser-acceptance/v1','passed':passed,'mode':self.mode,'suite':self.suite,
            'viewports':self.viewports,'viewport_sizes':{k:VIEWPORTS[k] for k in self.viewports},
            'environment':self.environment,'os':platform.system()+' '+platform.release(),
            'runtime':{'python':platform.python_version(),'openssl':ssl.OPENSSL_VERSION,
                'expat':xml.parsers.expat.EXPAT_VERSION,'playwright':version('playwright'),
                'macos':platform.mac_ver()[0],'architecture':platform.machine()},
            'cases':self.cases,'screenshots':self.screenshots,'comparisons':self.comparisons,
            'source_sha':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
            'source_checkout_dirty':bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True).strip()),
            'limitations':['Headless hosted/browser automation; not native MacBook acceptance or WCAG certification. Playwright WebKit is not identical to Safari.',
                'Scientific providers are offline fixtures; native Trash is covered separately.',
                'Pixel comparisons require the exact reviewed platform/engine renderer; paths/raw IDs are masked.']}
        (self.output/'report.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        (self.output/'summary.txt').write_text(('PASS' if passed else 'FAIL')+'\n'+logs,encoding='utf-8')
        cards=''.join('<figure><figcaption>'+html.escape(x['viewport']+' — '+x['name'])+'</figcaption><a href="'+html.escape(x['path'])+'"><img alt="'+html.escape(x['name'])+'" loading="lazy" src="'+html.escape(x['path'])+'" width="640"></a></figure>' for x in self.screenshots)
        (self.output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>CorpusTrail browser acceptance</title><h1>'+('PASS' if passed else 'FAIL')+'</h1><p>Offline '+html.escape(self.environment['browser'])+' acceptance, not native user acceptance.</p><a href="report.json">Structured results</a><pre>'+html.escape(logs)+'</pre>'+cards+'</html>',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=('all','smoke','project','discovery','evidence','review','population'),default='all')
    parser.add_argument('--viewports',nargs='+',choices=tuple(VIEWPORTS),default=list(VIEWPORTS))
    parser.add_argument('--visual',choices=('capture','compare'),default='capture')
    parser.add_argument('--browser',choices=('chromium','webkit'),default='chromium')
    parser.add_argument('--output',type=Path,help='New output directory; existing reports are never overwritten')
    parser.add_argument('--approve-baselines',type=Path,help='Explicitly approve a passing complete capture report after image review')
    parser.add_argument('--reviewed',action='store_true')
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT))
    if args.approve_baselines:
        from browser_tests.visual import approve
        report=args.approve_baselines.resolve()
        environment=json.loads((report/'report.json').read_text(encoding='utf-8'))['environment']
        approve(report,baseline_directory(environment),reviewed=args.reviewed)
        return 0
    if args.output is None:parser.error('--output is required when running acceptance')
    args.output.mkdir(parents=True,exist_ok=False)
    try:
        return execute(args)
    except Exception as error:
        # Missing browser/libs/baselines are failures, not successful skips.
        message=str(error).replace(str(Path.home()),'<developer-home>').replace(str(ROOT),'<source>')
        value={'schema':'corpustrail-browser-acceptance/v1','passed':False,'phase':'setup_or_runner',
               'error':type(error).__name__,'message':message,'mode':args.visual,'viewports':args.viewports}
        (args.output/'report.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        (args.output/'summary.txt').write_text('FAIL: '+type(error).__name__+'\n'+message+'\n',encoding='utf-8')
        print('FAIL: '+type(error).__name__+'; see '+str(args.output/'summary.txt'))
        return 1


def execute(args):
    from playwright.sync_api import sync_playwright
    from browser_tests.acceptance import BrowserAcceptance
    from browser_tests.webkit_screenshots import driver_environment
    logs=io.StringIO();passed=True;started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='ct-browser-renderer-') as cache,driver_environment(args.browser),sync_playwright() as driver:
        env=dict(os.environ)
        if sys.platform=='linux':
            env.update(FONTCONFIG_FILE=str(ROOT/'browser_tests'/'fonts.conf'),XDG_CACHE_HOME=cache)
        browser=getattr(driver,args.browser).launch(env=env)
        try:
            runtime=Runtime(browser,args.output,args.visual,args.suite,args.viewports,args.browser)
            BrowserAcceptance.runtime=runtime
            methods=unittest.defaultTestLoader.getTestCaseNames(BrowserAcceptance)
            if args.suite=='smoke':methods=[m for m in methods if 'evidence' in m or 'home' in m or 'review' in m or 'journal' in m or 'population' in m]
            elif args.suite!='all':methods=[m for m in methods if args.suite in m]
            for name in args.viewports:
                runtime.viewport_name=name;runtime.viewport=VIEWPORTS[name]
                tests=unittest.TestSuite(BrowserAcceptance(m) for m in methods)
                result=unittest.TextTestRunner(stream=logs,verbosity=2).run(tests)
                passed=passed and result.wasSuccessful()
            runtime.report(passed,logs.getvalue())
        finally:browser.close()
    print(('PASS' if passed else 'FAIL')+' browser acceptance in '+str(round(time.monotonic()-started,1))+'s; report '+str(args.output/'index.html'))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
