"""Actual Chromium / packaged HTTP end-to-end tests; no frontend API mocks."""
import json
import re
import queue
import subprocess
import sys
import threading
import time
import unittest

from playwright.sync_api import expect
from .fixtures import ApplicationFixture, ABSTRACT, SCOPE, TITLE, FOOTNOTE, fingerprint


class BrowserAcceptance(unittest.TestCase):
    runtime = None  # Explicit runner-owned browser/report; never auto-discovered.

    def setUp(self):
        # Review order uses canonical IDs. Stabilize only synthetic visual IDs;
        # every run still has a private root, lock directory and browser context.
        self.fixture = ApplicationFixture(project_id='browser-guided-fixture' if 'review' in self._testMethodName else
            'browser-population-fixture' if 'population' in self._testMethodName else None)
        self.addCleanup(self.fixture.close)
        self.context = self.runtime.browser.new_context(viewport=self.runtime.viewport,
            device_scale_factor=1, locale='en-US', timezone_id='UTC', color_scheme='light',
            reduced_motion='reduce', service_workers='block')
        self.addCleanup(self.context.close)
        self.context.tracing.start(screenshots=True, snapshots=False, sources=False)
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.diagnostics = []
        self.tokens = set()
        self.expected_http_errors = set()
        self.expected_console_errors = []
        self.expected_transport_failure = False
        self.local_requests=0
        self.external_requests=0
        self.csp_enforcement_checks=0
        self.pending_requests=set()
        self.page.on('request',lambda request:self.pending_requests.add(request))
        self.page.on('requestfinished',lambda request:self.pending_requests.discard(request))
        self.page.on('requestfailed',lambda request:self.pending_requests.discard(request))
        def route(request_route):
            request = request_route.request
            if not request.url.startswith(self.fixture.origin+'/'):
                self.external_requests+=1
                self.diagnostics.append('Unexpected external browser request')
                request_route.abort()
            else:
                self.local_requests+=1
                request_route.continue_()
        self.context.route('**/*', route)
        self.page.on('pageerror', lambda error: self.diagnostics.append('JavaScript: '+str(error)))
        def console(msg):
            if msg.type!='error':return
            if msg.text in self.expected_console_errors:
                self.expected_console_errors.remove(msg.text);return
            if not (self.expected_transport_failure and 'net::ERR_FAILED' in msg.text):
                self.diagnostics.append('Console: '+msg.text)
        self.page.on('console',console)
        self.page.on('requestfailed', lambda req: self.diagnostics.append('Failed local request: '+req.method+' '+req.url.split('?')[0])
            if not (self.expected_transport_failure and req.url.endswith('/api/v1/review/command')) else None)
        self.page.on('response', lambda response: self.diagnostics.append('HTTP '+str(response.status)+' '+response.url.split('?')[0])
            if response.status>=400 and response.status not in self.expected_http_errors else None)
        self.visit('/')

    def tearDown(self):
        self.settle_reads()
        errors = self.diagnostics+self.fixture.errors+self.fixture.transport.errors
        self.runtime.finish_case(self, errors)
        self.assertEqual(errors, [], 'Browser/backend diagnostics must be clean')

    def visit(self, path):
        # A visible heading can precede a page's final read-only requests.
        # Let them finish before test-driven navigation; never suppress aborted
        # requests or relax diagnostics to accommodate WebKit's reporting.
        self.settle_reads()
        self.page.goto(self.fixture.origin+path, wait_until='networkidle')
        token=self.page.locator('meta[name="corpustrail-session"]').get_attribute('content')
        if token: self.tokens.add(token)
        expect(self.page.locator('main h1:visible')).to_have_count(1)

    def reload(self):
        self.settle_reads()
        self.page.reload(wait_until='networkidle')

    def restart(self):
        self.settle_reads()
        self.fixture.restart()

    def settle_reads(self):
        # load-state networkidle can already be satisfied when a fresh routed
        # request is queued. Observe actual request completion and a continuous
        # quiet interval instead of trusting that stale load-state flag.
        deadline=time.monotonic()+10
        quiet=None
        while time.monotonic()<deadline:
            self.page.wait_for_timeout(50)  # Pump real Playwright request events.
            if self.pending_requests:
                quiet=None
            elif quiet is None:
                quiet=time.monotonic()
            elif time.monotonic()-quiet>=0.5:
                return
        self.fail('Local application requests did not finish within the bounded navigation wait')

    def open_project(self):
        self.visit('/projects')
        expect(self.page.locator('#project-list article')).to_have_count(1)
        self.page.get_by_role('button', name='Open Project', exact=True).click()
        expect(self.page.locator('#project-name')).to_have_text('Synthetic materials')

    def snapshot(self, name, full_page=True,subject=None,anchor=None):
        self.runtime.snapshot(self, name, full_page=full_page,subject=subject,anchor=anchor)

    def layout(self):
        result=self.page.evaluate('''() => {
          const visible=e=>e.getClientRects().length>0;
          const fields=[...document.querySelectorAll('input,textarea,select')].filter(visible);
          const unnamed=fields.filter(e=>!e.labels?.length&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')).length;
          const buttons=[...document.querySelectorAll('button,a,summary')].filter(visible);
          const anonymous=buttons.filter(e=>!e.textContent.trim()&&!e.getAttribute('aria-label')).length;
          const escaped=buttons.filter(e=>{const r=e.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).length;
          return {overflow:document.documentElement.scrollWidth-innerWidth,unnamed,anonymous,escaped};
        }''')
        self.assertLessEqual(result['overflow'],1,result)
        self.assertEqual((result['unnamed'],result['anonymous'],result['escaped']),(0,0,0),result)

    def test_home_catalogue_readonly(self):
        before=fingerprint(self.fixture.root)
        if self.runtime.environment['browser']=='webkit':
            # The test-only driver adapter must not bypass production CSP.
            self.expected_console_errors.append("Refused to apply a stylesheet because its hash, its nonce, or 'unsafe-inline' does not appear in the style-src directive of the Content Security Policy.")
            blocked=self.page.evaluate('''() => {
                const style=document.createElement('style');style.textContent='html { outline: 99px solid red !important; }';
                document.head.append(style);const blocked=style.sheet===null;style.remove();return blocked;
            }''')
            self.assertTrue(blocked,'Production CSP must still refuse arbitrary inline CSS')
            self.csp_enforcement_checks+=1
        expect(self.page.get_by_role('heading',name='Welcome to CorpusTrail')).to_be_visible()
        expect(self.page.locator('.workflow li')).to_have_count(7)
        self.assertEqual(self.page.locator('.step-number').all_text_contents(),[str(i) for i in range(1,8)])
        self.assertTrue(self.page.locator('.workflow li').evaluate_all("cards => cards.every(card => ['none','normal',''].includes(getComputedStyle(card, '::after').content))"))
        self.layout();self.snapshot('welcome')
        self.page.get_by_role('link',name='Open Existing Project',exact=True).click()
        expect(self.page.locator('#project-list article')).to_have_count(1)
        self.open_project();self.snapshot('dashboard')
        self.page.get_by_role('link',name='Discover More Publications',exact=True).click()
        expect(self.page.get_by_role('heading',name='Discovery',exact=True)).to_be_visible()
        expect(self.page.locator('#providers input')).to_have_count(4)
        self.assertEqual(self.fixture.transport.calls,[])
        self.visit('/papers')
        expect(self.page.locator('#paper-list article')).to_have_count(5)
        self.layout();self.snapshot('catalogue')
        # Existing macOS filter-box regression: compare actual boxes, not labels.
        if self.runtime.viewport['width']>=1000:
            boxes=[self.page.locator(s).bounding_box() for s in ('#sort','#page-size','#filters button[type="submit"]')]
            self.assertLessEqual(max(b['y'] for b in boxes)-min(b['y'] for b in boxes),1)
            self.assertLessEqual(max(b['height'] for b in boxes)-min(b['height'] for b in boxes),1)
        self.page.get_by_role('combobox',name='Sort by',exact=True).select_option('year_newest')
        self.page.get_by_role('combobox',name='Results per page',exact=True).select_option('50')
        self.page.get_by_role('combobox',name='Evidence',exact=True).select_option('pending')
        self.page.get_by_role('button',name='Apply filters').click()
        expect(self.page.locator('#paper-list article')).to_have_count(1)
        expect(self.page.locator('#paper-list')).to_contain_text('Pending documents: 1')
        self.page.get_by_role('combobox',name='Evidence',exact=True).select_option('')
        self.page.get_by_role('combobox',name='Sort by',exact=True).select_option('title')
        self.page.get_by_role('combobox',name='Results per page',exact=True).select_option('25')
        self.page.get_by_role('button',name='Apply filters').click()
        expect(self.page.locator('#paper-list article')).to_have_count(5)
        self.page.get_by_label('Search papers').fill('without a PMCID')
        self.page.get_by_role('button',name='Apply filters').click()
        expect(self.page.locator('#paper-list article')).to_have_count(1)
        self.page.get_by_role('link',name='Publication without a PMCID',exact=True).click()
        expect(self.page.locator('#evidence-eligibility')).to_contain_text('PMCID')
        expect(self.page.locator('#retrieve-evidence')).to_be_hidden()
        expect(self.page.locator('#paper-status')).to_contain_text('Awaiting corpus decision')
        expect(self.page.locator('#paper-status')).to_contain_text('Human review recorded')
        self.layout();self.snapshot('missing-pmcid')
        for link in self.page.locator('#identifiers a').all():
            self.assertEqual(link.get_attribute('target'),'_blank')
            self.assertTrue(link.get_attribute('href').startswith('https://doi.org/'))
        self.page.locator('#advanced summary').first.click()
        expect(self.page.get_by_role('button',name='Copy CorpusTrail paper ID')).to_be_visible()
        expect(self.page.locator('#raw-details')).not_to_have_attribute('open','')
        self.page.locator('#raw-details summary').click()
        expect(self.page.locator('#provenance-text')).not_to_be_empty()
        self.page.get_by_role('link',name='Home',exact=True).click()
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.transport.calls,[])
        # Actual keyboard focus, not merely a CSS string assertion.
        self.page.keyboard.press('Alt+Tab' if self.runtime.environment['browser']=='webkit' else 'Tab')
        focus=self.page.evaluate('''() => {const e=document.activeElement,c=getComputedStyle(e);return {tag:e.tagName,outline:c.outlineStyle,width:parseFloat(c.outlineWidth)};}''')
        self.assertNotEqual(focus['tag'],'BODY');self.assertNotEqual(focus['outline'],'none');self.assertGreater(focus['width'],0)

    def test_project_journal_search_and_filters(self):
        import hashlib
        from urllib.parse import parse_qs, urlsplit
        from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
        from corpustrail.application.reads import ProjectReads
        project=self.fixture.project
        journal='Journal of Tests: Science & Methods (Series A)'
        for number,source_name in ((6,journal),(7,None)):
            raw=('journal-fixture-'+str(number)).encode()
            source=SourceReference('fixture://journal/'+str(number),str(number),
                'sha256:'+hashlib.sha256(raw).hexdigest(),len(raw),'fixture_discovery',
                '2026-01-01T00:00:00+00:00',identity_status='verified')
            record=BibliographicRecord('Journal search fixture '+str(number),source=source_name,
                identifiers=(Identifier('doi','10.1234/journal.'+str(number)),))
            project.identities.apply(project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
        before=fingerprint(self.fixture.root)
        self.open_project();self.visit('/papers')
        def search(query,expected):
            self.page.get_by_label('Search papers').fill(query)
            with self.page.expect_response(lambda response:'/api/v1/papers?' in response.url) as received:
                self.page.get_by_role('button',name='Apply filters',exact=True).click()
            response=received.value
            data=response.json()
            self.assertEqual(response.status,200)
            self.assertEqual(parse_qs(urlsplit(response.url).query,keep_blank_values=True)['q'],[query.strip()])
            self.assertEqual(data['total'],expected)
            expect(self.page.locator('#paper-list article')).to_have_count(expected)
            self.assertEqual(sorted(self.page.locator('#paper-list h2').all_text_contents()),
                sorted(item['bibliography']['title'] for item in data['items']))
            self.assertEqual(data['total'],ProjectReads(project).papers(q=query.strip(),
                evidence=self.page.locator('#evidence-filter').input_value())['total'])
        for query in ('Synthetic Journal','Synthetic','sYnThEtIc JOURNAL','  Synthetic Journal  '):
            search(query,5)
        search(journal,1);self.layout();self.snapshot('journal-results')
        search('Science & Methods',1)
        self.page.locator('#evidence-filter').select_option('structured_text')
        search(journal,0)
        expect(self.page.locator('#page-count')).to_contain_text('No matching papers')
        self.page.get_by_role('button',name='Clear search and filters',exact=True).click()
        expect(self.page.locator('#paper-list article')).to_have_count(7)
        expect(self.page.locator('#evidence-filter')).to_have_value('')
        expect(self.page.get_by_label('Search papers')).to_have_value('')
        search('Journal search fixture 7',1)  # Missing journal, still searchable by title.
        search('',7)
        search('Legitimately unmatched journal',0);self.layout();self.snapshot('journal-no-results')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.transport.calls,[])

    def test_project_wizard_settings_and_confirmation(self):
        self.page.get_by_role('link',name='Create New Project',exact=True).click()
        expect(self.page.locator('#progress')).to_have_text('Step 1 of 6')
        self.page.get_by_role('button',name='Next',exact=True).click()
        expect(self.page.locator('#progress')).to_have_text('Step 1 of 6')
        self.page.get_by_label('Project name',exact=True).fill('Disposable browser project')
        self.page.get_by_label('Brief scientific topic description').fill('A synthetic browser-only topic.')
        self.snapshot('wizard');self.layout()
        self.page.get_by_role('button',name='Next',exact=True).click()
        self.page.get_by_role('textbox',name='Broad-corpus definition',exact=True).fill(SCOPE)
        self.page.get_by_role('button',name='Next',exact=True).click()
        for label in ('OpenAlex','Europe PMC'):
            self.page.get_by_role('checkbox',name=label,exact=True).check()
        self.page.locator('#concepts').fill('porous materials')
        self.page.get_by_role('button',name='Next',exact=True).click()
        self.page.get_by_role('checkbox',name='Europe PMC',exact=True).check()
        self.page.get_by_role('button',name='Next',exact=True).click()
        self.page.get_by_label('Configuration author',exact=True).fill('browser_reviewer')
        expect(self.page.locator('#no-authority')).to_be_checked()
        expect(self.page.locator('#grant-authority')).not_to_be_checked()
        for choice in self.page.locator('.authority-choice').all():
            box=choice.locator('input').bounding_box();label=choice.locator('span').bounding_box()
            self.assertLess(box['x']+box['width'],label['x'])
            self.assertLess(abs(box['y']-label['y']),8)
        self.snapshot('wizard-reviewer');self.layout()
        # Deliberate authority choice, not an implicit first-user privilege.
        self.page.get_by_role('radio',name=re.compile('Authorize corpus decisions')).check()
        self.page.get_by_role('button',name='Next',exact=True).click()
        expect(self.page.locator('#summary')).to_contain_text('OpenAlex, Europe PMC')
        self.assertIn('Authorized corpus reviewers\nbrowser_reviewer',self.page.locator('#summary').inner_text())
        expect(self.page.locator('#authority-confirmation')).to_be_hidden()
        expect(self.page.locator('#creation-confirmation')).to_contain_text('explicit authority choice')
        self.snapshot('wizard-summary');self.layout()
        self.page.get_by_role('button',name='Create Project',exact=True).click()
        expect(self.page.locator('#project-name')).to_have_text('Disposable browser project')
        created=self.fixture.controller.project(self.fixture.controller.active_handle)
        self.assertEqual(created.config.review.authorized_reviewers,('browser_reviewer',))
        self.assertEqual(created.configuration_history()[0]['created_by'],'browser_reviewer')
        self.snapshot('empty-dashboard');self.layout()
        self.page.get_by_role('link',name='Start Literature Discovery',exact=True).click()
        expect(self.page.locator('#history button')).to_have_count(0)
        self.assertEqual(self.fixture.transport.calls,[])
        self.visit('/settings');self.snapshot('settings');self.layout()
        saved=self.page.locator('#description').input_value()
        self.page.locator('#description').fill('Discard this unsaved edit.')
        expect(self.page.locator('#saved-status')).to_contain_text('Unsaved changes')
        self.page.get_by_role('button',name='Discard Changes').click()
        expect(self.page.locator('#description')).to_have_value(saved)
        self.page.locator('#description').fill('Updated topic description from the actual browser.')
        self.page.get_by_role('button',name='Save Changes').click()
        expect(self.page.locator('#message')).to_contain_text('configuration version 2')
        self.page.get_by_role('button',name='Save Changes').click()
        expect(self.page.locator('#message')).to_contain_text('No configuration fields changed')
        self.visit('/projects')
        expect(self.page.locator('.active-project')).to_contain_text('Active project')
        self.snapshot('projects');self.layout()
        expect(self.page.locator('.active-project').get_by_role('button',name='Move to Trash…')).to_be_disabled()
        self.page.get_by_role('button',name='Close Project',exact=True).click()
        expect(self.page.locator('#project-list article')).to_have_count(2)
        expect(self.page.get_by_role('button',name='Close Project',exact=True)).to_have_count(0)
        card=self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Disposable browser project',exact=True))
        before=fingerprint(self.fixture.root)
        card.get_by_role('button',name='Move to Trash…').click()
        expect(self.page.locator('#trash-name')).to_have_text('Disposable browser project')
        expect(self.page.locator('#trash-location')).to_contain_text('disposable-browser-project')
        self.page.locator('#trash-folder').fill('wrong')
        expect(self.page.locator('#trash-execute')).to_be_disabled()
        self.page.locator('#trash-folder').fill('disposable-browser-project')
        expect(self.page.locator('#trash-execute')).to_be_enabled()
        self.snapshot('trash-confirmation');self.layout()
        self.page.get_by_role('button',name='Cancel',exact=True).click()
        expect(self.page.locator('#message')).to_contain_text('Confirmation closed. Cancelling does not move or restore any project.')
        expect(self.page.locator('#project-list article')).to_have_count(2)
        self.assertEqual(before,fingerprint(self.fixture.root))
        # Hold a real cooperating process lease; current-launcher close is not
        # evidence that a project is globally unused.
        root=self.fixture.root/'disposable-browser-project'
        code="import sys;from pathlib import Path;import corpustrail.application.project_use as g;g.lock_directory=lambda:Path(sys.argv[2]);lease=g.acquire_project_use(Path(sys.argv[1]));print('READY',flush=True);sys.stdin.readline()"
        child=subprocess.Popen([sys.executable,'-I','-u','-c',code,str(root),str(self.fixture.base/'locks')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            ready=queue.Queue()
            threading.Thread(target=lambda:ready.put(child.stdout.readline()),daemon=True).start()
            self.assertEqual(ready.get(timeout=10).strip(),'READY')
            self.visit('/projects')
            card=self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Disposable browser project',exact=True))
            expect(card.get_by_role('button',name='Move to Trash…')).to_be_disabled()
            expect(card).to_contain_text(re.compile('in use|another|busy',re.I))
        finally:
            if child.poll() is None:child.kill()
            child.communicate(timeout=10)
        self.visit('/projects');card=self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Disposable browser project',exact=True))
        card.get_by_role('button',name='Open Project').click()
        expect(self.page).to_have_url(re.compile('/dashboard$'))
        expect(self.page.locator('#project-name')).to_have_text('Disposable browser project')
        self.visit('/settings')
        expect(self.page.locator('#description')).to_have_value('Updated topic description from the actual browser.')
        self.page.locator('#configuration-info summary').click()
        expect(self.page.locator('#configuration-history li')).to_have_count(2)
        self.assertEqual(self.fixture.transport.calls,[])

    def prepare_discovery(self):
        self.visit('/discovery')
        expect(self.page.locator('#providers input')).to_have_count(4)
        self.snapshot('discovery-configuration');self.layout()
        self.page.get_by_label('Exact search query').fill('porous materials — microstructure '+('and scientific characterization '*5))
        for checkbox in self.page.locator('[data-provider]').all():checkbox.check()
        self.page.get_by_text('Search limits and retries',exact=True).click()
        self.page.locator('#bound-page_size').fill('5')
        self.page.locator('#bound-max_pages').fill('1')
        self.page.get_by_role('button',name='Preview Search Plan').click()
        expect(self.page.locator('#plan-providers article')).to_have_count(4)
        expect(self.page.locator('#message')).to_have_text('Exact plan saved locally. No database has been contacted.')
        expect(self.page.locator('#approve')).to_be_enabled()
        expect(self.page.locator('#history button')).to_have_count(1)
        self.layout();self.snapshot('discovery-preview')
        self.assertEqual(self.fixture.transport.calls,[])
        expect(self.page.locator('#plan-advanced')).not_to_have_attribute('open','')
        self.page.locator('#plan-advanced summary').click()
        self.assertIn('per_page',self.page.locator('#plan-details').inner_text())
        self.page.locator('#plan-advanced summary').click()
        self.page.locator('#approval-area').scroll_into_view_if_needed()
        self.snapshot('discovery-approval',full_page=False)
        expect(self.page.locator('#approval-providers')).to_have_text('OpenAlex, Crossref, Europe PMC, Semantic Scholar')
        expect(self.page.locator('#approval-disclosure')).to_contain_text('I authorize this exact search')
        expect(self.page.locator('#organization-disclosure')).to_contain_text('I also authorize organizing')
        expect(self.page.locator('#organization-disclosure')).to_contain_text('No corpus-membership decisions')
        expect(self.page.locator('#run')).to_be_hidden()
        self.page.get_by_role('button',name='Approve Search Plan').click()
        expect(self.page.locator('#run')).to_be_visible()
        expect(self.page.locator('#plan-notice')).to_contain_text('Approved — not yet run')
        self.assertEqual(self.fixture.transport.calls,[])

    def test_discovery_exact_approval_execution_and_history(self):
        self.open_project();self.prepare_discovery()
        self.fixture.transport.gate=threading.Event()
        self.page.get_by_role('button',name='Run Discovery',exact=True).click()
        expect(self.page.locator('#job-status')).to_contain_text('Running')
        expect(self.page.locator('#repeat')).to_be_enabled()
        expect(self.page.locator('#provider-progress li').first).to_have_text(
            'OpenAlex: running · 0 observations preserved · 1 request attempts started')
        self.page.locator('#job-section').scroll_into_view_if_needed()
        self.snapshot('discovery-progress',full_page=False,anchor='#job-section')
        self.fixture.transport.gate.set()
        expect(self.page.locator('#job-status')).to_contain_text('4/4 providers finished',timeout=15000)
        expect(self.page.locator('#job-status')).to_contain_text('Completed bounded search')
        expect(self.page.locator('#result-papers a')).to_have_count(5)
        expect(self.page.locator('#history button').first).to_contain_text('Completed bounded search')
        results=self.page.locator('#results').inner_text()
        for text in ('Provider observations preserved\n8','Unique publications linked\n5',
                     'Publications created by this search\n4','Previously known publications\n1'):
            self.assertIn(text,results)
        self.snapshot('discovery-results',subject='#results');self.layout()
        self.assertEqual(len(self.fixture.transport.calls),4)
        self.reload()
        expect(self.page.locator('#history button')).to_have_count(1)
        self.page.locator('#history button').click()
        expect(self.page.locator('#job-status')).to_contain_text('Completed bounded search')
        self.assertEqual(len(self.fixture.transport.calls),4)
        self.page.locator('#result-papers a').filter(has_text='Discovered glass scaffold').first.click()
        expect(self.page.locator('#paper-status')).to_contain_text('Awaiting corpus decision')
        self.page.locator('#advanced summary').first.click()
        expect(self.page.locator('#provenance-sources')).to_contain_text(re.compile('Crossref|OpenAlex'))
        self.visit('/discovery');self.page.locator('#history button').click()
        self.page.get_by_role('button',name='Prepare a new search from these settings').click()
        self.page.get_by_role('button',name='Preview Search Plan').click()
        self.page.get_by_role('button',name='Approve Search Plan').click()
        self.fixture.transport.fail_crossref=True
        self.page.get_by_role('button',name='Run Discovery',exact=True).click()
        expect(self.page.locator('#job-status')).to_contain_text('partial',timeout=15000)
        self.assertIn('Publications created by this search\n0',self.page.locator('#results').inner_text())
        self.assertIn('Previously known publications\n4',self.page.locator('#results').inner_text())
        self.assertEqual(len(self.fixture.project.identities.papers()),9)
        for pid in self.fixture.project.identities.papers():
            self.assertEqual(self.fixture.project.reviews.membership(pid)['state'],'not_reviewed')
        # Terminal counts render before the final preserved-history read.
        expect(self.page.locator('#history button').filter(has_text='Completed with errors / partial')).to_have_count(1)
        self.reload()
        expect(self.page.locator('#history button')).to_have_count(2)
        self.assertEqual(len(self.fixture.transport.calls),8)

    def test_discovery_transport_error_is_not_a_confirmed_rate_limit(self):
        initial={pid:self.fixture.project.reviews.history(pid) for pid in self.fixture.papers}
        self.open_project();self.visit('/discovery')
        self.fixture.transport.discovery_transport_error=True
        self.page.locator('#query').fill('synthetic transport diagnostic')
        for checkbox in self.page.locator('[data-provider]').all():
            if checkbox.is_enabled():checkbox.set_checked(checkbox.input_value()=='europepmc')
        self.page.get_by_role('button',name='Preview Search Plan',exact=True).click()
        self.page.get_by_role('button',name='Approve Search Plan',exact=True).click()
        self.assertEqual(self.fixture.transport.calls,[])
        self.page.get_by_role('button',name='Run Discovery',exact=True).click()
        expect(self.page.locator('#job-status')).to_contain_text('1/1 providers finished',timeout=15000)
        expect(self.page.locator('#provider-progress')).to_contain_text('TLS certificate verification failed')
        self.assertNotIn('rate limit',self.page.locator('#provider-progress').inner_text().lower())
        self.assertEqual(len(self.fixture.transport.calls),1)
        from corpustrail._internal.pipeline import events
        records=events(self.fixture.project,kind='request_result')
        self.assertEqual(records[-1]['payload']['error'],'ProviderCertificateError')
        self.assertIsNone(records[-1]['payload']['http_status'])
        self.layout();self.snapshot('discovery-transport-error')
        self.reload()
        self.page.locator('#history button').click()
        expect(self.page.locator('#provider-progress')).to_contain_text('TLS certificate verification failed')
        self.assertEqual(len(self.fixture.transport.calls),1)
        for pid in self.fixture.papers:
            self.assertEqual(self.fixture.project.reviews.history(pid),initial[pid])
            self.assertEqual(self.fixture.project.reviews.membership(pid)['state'],'not_reviewed')

    def test_evidence_table_footnotes_persist(self):
        self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click()
        self.fixture.transport.footnotes=True
        self.assertEqual(self.fixture.transport.calls,[])
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-history')).to_contain_text('Exact document identity verified',timeout=15000)
        def read_notes():
            self.page.get_by_role('button',name='Read verified structured text').click()
            expect(self.page.locator('#document-text')).to_contain_text(FOOTNOTE.strip())
            reader=self.page.locator('#document-text').inner_text()
            self.assertEqual(reader.count('Second distinct footnote paragraph.'),1)
            self.assertEqual(reader.count('Independent footnote.'),1)
            self.assertIn('a\n\n'+FOOTNOTE.strip()+'\n\nSecond distinct footnote paragraph.\n\nb\n\nIndependent footnote.',reader)
            self.layout()
        read_notes()
        self.snapshot('evidence-footnotes',subject='#document-text')
        reachable=self.page.locator('#document-text').evaluate('''element => {
          element.scrollTop=element.scrollHeight;
          return element.scrollTop+element.clientHeight>=element.scrollHeight-1;
        }''')
        self.assertTrue(reachable,'Long footnotes must remain reachable by reader scrolling')
        self.reload();read_notes()
        before=fingerprint(self.fixture.root)
        self.restart();self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click();read_notes()
        expect(self.page.locator('#evidence-operations button')).to_have_count(1)
        self.assertEqual(len(self.fixture.transport.calls),1)
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.project.reviews.history(self.fixture.papers[0]),[])
        self.assertEqual(self.fixture.project.reviews.membership(self.fixture.papers[0])['state'],'not_reviewed')

    def start_guided_review(self,reviewer='fixture_reviewer'):
        self.visit('/review')
        expect(self.page.locator('#reviewer')).to_have_value('')
        expect(self.page.locator('#review-population')).to_have_value('')
        self.snapshot('review-session-selection');self.layout()
        self.page.locator('#reviewer').fill(reviewer)
        self.page.locator('#review-population').select_option('all')
        self.page.get_by_role('button',name='Start Guided Review',exact=True).click()
        expect(self.page.locator('#review-workspace')).to_be_visible()
        expect(self.page.locator('#review-definition')).to_have_text(SCOPE)

    def test_population_freeze_combine_review_and_restart(self):
        import hashlib
        import uuid
        from corpustrail._internal.pipeline import preserve
        from corpustrail.identity import BibliographicRecord,Identifier,SourceReference
        from corpustrail.populations import ImportedSource
        from corpustrail.providers import metadata_provider
        project=self.fixture.project
        initial_reviews={p:project.reviews.history(p) for p in self.fixture.papers}
        self.open_project()
        before=fingerprint(self.fixture.root)
        self.page.get_by_role('link',name='Candidate Populations',exact=True).click()
        expect(self.page.locator('#population-list-status')).to_contain_text('No saved population versions')
        self.assertEqual(before,fingerprint(self.fixture.root));self.assertEqual(self.fixture.transport.calls,[])
        self.assertEqual(self.page.locator('input[type=file]').count(),0)
        self.layout();self.snapshot('population-empty')
        self.page.get_by_label('Population name',exact=True).fill('Initial collected candidates')
        self.page.get_by_label('Created by',exact=True).fill('fixture_reviewer')
        self.page.locator('#population-all').check()
        before=fingerprint(self.fixture.root)
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        expect(self.page.locator('#population-preview-counts')).to_contain_text('5')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.layout();self.snapshot('population-preview')
        self.page.get_by_role('button',name='Freeze Population',exact=True).evaluate('b=>{b.click();b.click();}')
        expect(self.page.locator('#population-message')).to_contain_text('Candidate population frozen')
        expect(self.page.locator('#population-detail-counts')).to_contain_text('5')
        self.assertEqual(project.populations.versions()['total'],1)
        first=project.populations.versions()['items'][0]
        self.layout();self.snapshot('population-frozen')
        # Controlled future-adapter contract: real enrollment + preserved source,
        # no production format parser or HTTP import endpoint.
        body=b'{"synthetic_export":["known publication","new publication"]}'
        sha=preserve(project,body,'application/json','2026-01-01T00:00:00+00:00')
        observations=[]
        for i,doi in enumerate(('10.1234/evidence.1','10.1234/population-import.6')):
            record=BibliographicRecord('Synthetic adapter candidate '+str(i),identifiers=(Identifier('doi',doi),))
            source=SourceReference('fixture://population-adapter',str(i),sha,len(body),'synthetic-adapter',
                '2026-01-01T00:00:00+00:00',identity_status='verified')
            plan=project.identities.plan(record,source)
            pid=project.identities.apply(plan,approve_new_identity=True,approve_aliases=True)
            observations.extend(x['observation_id'] for x in project.identities.observations(pid) if x['source']['source_uri']=='fixture://population-adapter')
        imported=project.populations.freeze_import_source(ImportedSource('synthetic-source-v1','synthetic-adapter','v1',sha,tuple(observations)),
            request_id=uuid.uuid4().hex,name='Synthetic source interface',actor='fixture')
        provider=metadata_provider('openalex')
        plan=project.discovery.plan(provider,run_id='population-discovery',query='synthetic porous materials',max_pages=1,max_attempts=1)
        project.discovery.execute(plan,provider,transport=self.fixture.transport,confirm_external=True)
        project.discovery.canonicalize(plan.run_id,approve_new_identities=True,approve_aliases=True)
        calls=len(self.fixture.transport.calls)
        self.assertEqual(len(project.identities.papers()),7)
        self.reload()
        self.page.get_by_label('Population name',exact=True).fill('Combined origin candidates')
        self.page.get_by_label('Created by',exact=True).fill('fixture_reviewer')
        for name in ('Initial collected candidates','Synthetic source interface'):
            self.page.get_by_role('checkbox',name='Use '+name+' · Version 1 in a combination',exact=True).check()
        self.page.locator('#population-form details').filter(has=self.page.get_by_text('Completed discovery sources',exact=True)).locator('summary').click()
        self.page.get_by_role('checkbox',name=re.compile('openalex · synthetic porous materials')).check()
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        expect(self.page.locator('#population-preview')).to_be_visible()
        self.page.get_by_role('button',name='Freeze Population',exact=True).click()
        expect(self.page.locator('#population-detail-heading')).to_have_text('Combined origin candidates · Version 1')
        combined=project.populations.versions()['items'][0]
        self.assertEqual(combined['member_count'],7);self.assertEqual(combined['unresolved_count'],0)
        expect(self.page.locator('#population-detail-sources')).to_contain_text('Initial collected candidates')
        expect(self.page.locator('#population-detail-sources')).to_contain_text('Synthetic source interface')
        expect(self.page.locator('#population-detail-sources')).to_contain_text('openalex')
        self.page.get_by_role('button',name='Verify Stored Integrity',exact=True).click()
        expect(self.page.locator('#population-verify-result')).to_contain_text('integrity verified')
        self.layout();self.snapshot('population-combined')
        self.page.locator('#population-provenance summary').click()
        expect(self.page.locator('#population-lineage')).to_contain_text('fixture')
        self.snapshot('population-lineage',subject='#population-detail');self.layout()
        self.assertEqual({p:project.reviews.history(p) for p in self.fixture.papers},initial_reviews)
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in project.identities.papers()))
        self.page.get_by_role('link',name='Review This Frozen Version',exact=True).click()
        expect(self.page.locator('#review-population')).to_have_value(combined['version_id'])
        expect(self.page.locator('#reviewer')).to_have_value('')
        self.snapshot('population-review-selection');self.layout()
        self.page.locator('#reviewer').fill('fixture_reviewer')
        self.page.get_by_role('button',name='Start Guided Review',exact=True).click()
        expect(self.page.locator('#review-progress')).to_contain_text('of 7')
        expect(self.page.locator('#review-population-version')).to_contain_text('Version 1')
        self.snapshot('population-review');self.layout()
        review_handle=self.page.url.split('#')[1]
        # An addition and explicit successor cannot expand the earlier session.
        raw=b'new candidate after the frozen review'
        record=BibliographicRecord('Later candidate outside frozen population',identifiers=(Identifier('doi','10.1234/population-later.8'),))
        source=SourceReference('fixture://later-population','later','sha256:'+hashlib.sha256(raw).hexdigest(),len(raw),'fixture',
            '2026-01-01T00:00:00+00:00',identity_status='verified')
        project.identities.apply(project.identities.plan(record,source),approve_new_identity=True,approve_aliases=True)
        self.visit('/populations')
        card=self.page.locator('#population-versions article').filter(has=self.page.get_by_role('heading',name='Combined origin candidates · Version 1 · Frozen',exact=True))
        card.get_by_role('button',name='Create Successor Version',exact=True).click()
        self.page.get_by_label('Created by',exact=True).fill('fixture_reviewer');self.page.locator('#population-all').check()
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        self.page.get_by_role('button',name='Freeze Population',exact=True).click()
        expect(self.page.locator('#population-detail-heading')).to_have_text('Combined origin candidates · Version 2')
        self.assertEqual(project.populations.versions()['items'][0]['member_count'],8)
        self.snapshot('population-successor');self.layout()
        self.assertEqual(project.populations.inspect(first['version_id'])['member_count'],5)
        self.assertEqual(project.populations.inspect(combined['version_id'])['member_count'],7)
        self.snapshot('population-history');self.layout()
        before=fingerprint(self.fixture.root);self.restart();self.open_project()
        self.visit('/review#'+review_handle)
        expect(self.page.locator('#review-progress')).to_contain_text('of 7')
        expect(self.page.locator('#review-population-version')).to_contain_text('Version 1')
        self.visit('/populations#'+combined['version_id'].split(':')[1])
        expect(self.page.locator('#population-detail-heading')).to_have_text('Combined origin candidates · Version 1')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.assertEqual(calls,len(self.fixture.transport.calls))
        self.assertTrue(project.populations.verify(combined['version_id'])['verified'])
        self.visit('/review#'+review_handle)
        self.page.get_by_role('button',name='Finish Review',exact=True).click()
        expect(self.page).to_have_url(re.compile('/dashboard#review-completed-'))
        self.visit('/review#'+review_handle)
        expect(self.page.locator('#review-completion-heading')).to_contain_text('Review completed')
        self.snapshot('population-review-completed');self.layout()
        self.assertEqual({pid:project.reviews.history(pid) for pid in self.fixture.papers},initial_reviews)
        self.assertTrue(all(project.reviews.membership(pid)['state']=='not_reviewed' for pid in project.identities.papers()))
        self.assertEqual(imported['member_count'],2)

    def test_population_selection_stale_preview_and_legacy_upgrade(self):
        from unittest.mock import patch
        from corpustrail._internal.database import migrations
        from corpustrail.project import Project,ProjectConfig,ReviewPolicy
        self.open_project();self.visit('/populations')
        self.page.locator('#population-name').fill('Explicit selected candidate')
        self.page.locator('#population-actor').fill('fixture')
        self.page.get_by_text('Select individual publications',exact=True).click()
        self.page.locator('#population-search').fill('without a PMCID')
        self.page.get_by_role('button',name='Find Publications',exact=True).click()
        self.page.get_by_role('checkbox',name='Publication without a PMCID',exact=True).check()
        # Delay the REAL controller response, not its scientific result. Editing
        # during a pending preview must not let its late response reappear.
        from corpustrail.application.populations import PopulationController
        entered,released=threading.Event(),threading.Event()
        original=PopulationController.command
        def delayed(controller,project,action,body):
            value=original(controller,project,action,body)
            if action=='preview':
                entered.set()
                if not released.wait(10):raise AssertionError('Preview gate timed out')
            return value
        try:
            with patch.object(PopulationController,'command',new=delayed):
                self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
                self.assertTrue(entered.wait(5))
                self.page.locator('#population-name').fill('Edited selection invalidates preview')
                with self.page.expect_response(lambda response:response.url.endswith('/api/v1/populations/preview')):released.set()
        finally:released.set()
        expect(self.page.locator('#population-preview')).to_be_hidden()
        self.page.get_by_role('button',name='Preview Candidate Population',exact=True).click()
        expect(self.page.locator('#population-preview')).to_be_visible()
        expect(self.page.get_by_role('button',name='Freeze Population',exact=True)).to_be_enabled()
        # Real configuration revision invalidates a stale prepared population.
        from dataclasses import replace
        project=self.fixture.project
        project.configure(replace(project.config,config_version=2,name='Renamed fixture'),
            expected_event_id=project.configuration_history()[-1]['event_id'],created_by='fixture')
        self.expected_http_errors.add(409)
        self.expected_console_errors.append('Failed to load resource: the server responded with a status of 409 (Conflict)')
        self.page.get_by_role('button',name='Freeze Population',exact=True).click()
        expect(self.page.locator('#population-message')).to_contain_text('preview again')
        self.assertEqual(project.populations.versions()['total'],0)
        self.snapshot('population-conflict');self.layout()
        with patch('corpustrail._internal.database.migrations',return_value=migrations()[:37]):
            legacy=Project.create(self.fixture.root/'legacy-population',ProjectConfig('legacy-population','Legacy population fixture',
                'Synthetic older project',review=ReviewPolicy(scope=SCOPE)),created_by='fixture')
        self.visit('/projects')
        self.page.locator('#project-list article').filter(has=self.page.get_by_role('heading',name='Legacy population fixture',exact=True)).get_by_role('button',name='Open Project').click()
        expect(self.page.locator('#project-name')).to_have_text('Legacy population fixture')
        self.visit('/populations');expect(self.page.locator('#population-upgrade')).to_be_visible()
        self.assertFalse(legacy.populations.ready());self.snapshot('population-upgrade');self.layout()
        self.page.get_by_role('button',name='Back Up and Enable Populations',exact=True).click()
        expect(self.page.locator('#population-message')).to_contain_text('Population storage enabled')
        self.assertTrue(legacy.populations.ready());self.assertEqual(len(list((legacy.root/legacy.config.data_directory/'population-upgrades').glob('*.sqlite3'))),1)
        self.snapshot('population-upgraded');self.layout()
        self.assertEqual(self.fixture.transport.calls,[])

    def test_review_guided_save_finish_publish_and_resume(self):
        from dataclasses import replace
        from .fixtures import XML
        project=self.fixture.project
        project.configure(replace(project.config,config_version=project.config.config_version+1,
            review=replace(project.config.review,authorized_reviewers=('fixture_reviewer',))),
            expected_event_id=project.configuration_history()[-1]['event_id'],created_by='fixture')
        project.evidence.preserve_document(self.fixture.papers[0],XML,representation='jats_xml',media_type='application/xml',
            source_uri='fixture://verified-review-evidence',legitimate_basis='synthetic_fixture',resolver='fixture',resolver_version='v1')
        initial={p:project.reviews.history(p) for p in self.fixture.papers}
        self.open_project();self.start_guided_review()
        self.snapshot('review-active');self.layout()
        outcomes=['included','excluded','insufficient_evidence','included','excluded']
        captured_missing=False
        for i,outcome in enumerate(outcomes):
            expect(self.page.locator('#review-progress')).to_contain_text('Paper '+str(i+1)+' of 5')
            title=self.page.locator('#review-paper-title').inner_text()
            if title==TITLE:
                expect(self.page.locator('#review-abstract')).to_have_text(ABSTRACT)
                self.page.get_by_role('button',name='Read verified structured text',exact=True).click()
                expect(self.page.locator('#review-document')).to_contain_text('Invented structured scientific fixture text')
                expect(self.page.locator('#review-extent')).to_have_value('')
                expect(self.page.locator('#review-extent option[value=""]')).to_be_disabled()
                expect(self.page.locator('#review-extent option[value="full_document"]')).to_have_text('Verified structured text — full document')
                self.assertFalse(project.reviews.history(self.fixture.papers[0]))
                self.snapshot('review-verified-text')
            elif 'Long scientific title' in title:self.snapshot('review-long-title')
            else:
                expect(self.page.locator('#review-evidence-status')).to_contain_text('No abstract available')
                expect(self.page.locator('#review-extent option[value="full_document"]')).to_have_count(0)
                expect(self.page.locator('#review-extent option[value="sections"]')).to_have_count(0)
                if not captured_missing:
                    self.snapshot('review-missing-evidence');captured_missing=True
            self.page.locator('input[name="assessment"][value="'+outcome+'"]').check()
            self.page.locator('#review-extent').select_option('full_document' if title==TITLE else 'metadata')
            self.page.locator('#review-rationale').fill('Invented human assessment '+str(i+1))
            expect(self.page.locator('#review-save-state')).to_contain_text('Draft saved')
            if i==0:
                self.snapshot('review-assessment')
                # A transport interruption, not a mocked scientific/API success.
                self.expected_transport_failure=True
                self.page.route('**/api/v1/review/command',lambda route: route.abort('failed'))
                self.page.locator('#review-save-next').click()
                expect(self.page.locator('#review-message')).to_contain_text('current input is retained')
                expect(self.page.locator('#review-progress')).to_contain_text('Paper 1 of 5')
                expect(self.page.locator('#review-rationale')).to_have_value('Invented human assessment 1')
                self.assertEqual({p:project.reviews.history(p) for p in self.fixture.papers},initial)
                self.page.unroute('**/api/v1/review/command');self.expected_transport_failure=False
            self.page.locator('#review-save-next').evaluate('button=>{button.click();button.click();}')
            expect(self.page.locator('#review-message')).to_contain_text('Human observation saved')
            expect(self.page.locator('#review-recover')).to_be_hidden()
            expect(self.page.locator('#review-progress')).to_contain_text(str(i+1)+' with saved observations')
        self.assertEqual(sum(len(project.reviews.history(p))-len(initial[p]) for p in self.fixture.papers),5)
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        handle=self.page.url.split('#')[1]
        self.reload()
        expect(self.page.locator('#review-progress')).to_contain_text('5 with saved observations')
        before=fingerprint(self.fixture.root);self.restart();self.open_project();self.visit('/review')
        self.page.get_by_role('button',name='Open review session',exact=True).click()
        expect(self.page.locator('#review-progress')).to_contain_text('5 with saved observations')
        self.assertEqual(before,fingerprint(self.fixture.root))
        self.page.locator('#review-show-summary').click()
        expect(self.page.locator('#review-summary')).to_be_visible();self.snapshot('review-summary')
        self.page.get_by_role('button',name='Finish Review',exact=True).evaluate('button=>{button.click();button.click();}')
        expect(self.page).to_have_url(self.fixture.origin+'/dashboard#review-completed-'+handle)
        expect(self.page.locator('#dashboard-review-result')).to_contain_text('Finishing did not change corpus membership')
        self.snapshot('review-finished-dashboard');self.layout()
        self.page.locator('#dashboard-review-summary').click()
        expect(self.page.locator('#review-completion-heading')).to_have_text('Review completed — read only')
        expect(self.page.locator('#assessment-form')).to_be_hidden()
        expect(self.page.locator('#review-finish')).to_be_hidden()
        expect(self.page.locator('#review-summary-papers')).to_contain_text('Invented human assessment 1')
        self.assertTrue(all(project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        self.snapshot('review-completed',subject='main')
        observations={p:project.reviews.history(p) for p in self.fixture.papers}
        self.page.get_by_role('button',name='Preview corpus updates',exact=True).click()
        expect(self.page.locator('#review-publication')).to_be_visible()
        expect(self.page.locator('#review-prepare-publication')).to_be_hidden()
        expect(self.page.locator('#review-summary-counts')).to_contain_text('Proposed included publications')
        self.assertEqual(observations,{p:project.reviews.history(p) for p in self.fixture.papers})
        self.snapshot('review-publication',subject='main');self.layout()
        self.page.get_by_role('button',name='Back to Review Summary',exact=True).click()
        expect(self.page.locator('#review-publication')).to_be_hidden()
        expect(self.page.locator('#review-prepare-publication')).to_be_visible()
        self.reload()
        expect(self.page.locator('#review-publication')).to_be_hidden()
        expect(self.page.locator('#assessment-form')).to_be_hidden()
        self.page.get_by_role('button',name='Preview corpus updates',exact=True).click()
        self.page.get_by_role('button',name='Confirm corpus updates',exact=True).click()
        expect(self.page.locator('#review-message')).to_contain_text('confirmed decisions updated')
        self.snapshot('review-confirmed',subject='main')
        states=[project.reviews.membership(p)['state'] for p in self.fixture.papers]
        self.assertEqual(states.count('included'),2);self.assertEqual(states.count('excluded'),2)
        self.assertEqual(states.count('insufficient_evidence'),1)
        self.assertEqual(self.fixture.transport.calls,[])
        self.visit('/dashboard');expect(self.page.locator('#summaries')).to_contain_text('In corpus: 2')
        self.assertTrue(handle)

    def test_review_skip_frozen_population_and_draft_resume(self):
        from corpustrail.identity import BibliographicRecord,Identifier,SourceReference
        import hashlib
        project=self.fixture.project
        before={p:project.reviews.history(p) for p in self.fixture.papers}
        self.open_project();self.start_guided_review()
        # A newly collected canonical publication must not enter this snapshot.
        raw=b'new canonical fixture outside frozen review'
        source=SourceReference('fixture://later-collection','later','sha256:'+hashlib.sha256(raw).hexdigest(),
            len(raw),'fixture_discovery','2026-01-01T00:00:00+00:00',identity_status='verified')
        project.identities.apply(project.identities.plan(BibliographicRecord('Later collected publication',
            identifiers=(Identifier('doi','10.1234/later.6'),)),source),approve_new_identity=True,approve_aliases=True)
        self.page.locator('#review-rationale').fill('Incomplete draft retained without a judgment')
        expect(self.page.locator('#review-save-state')).to_contain_text('Draft saved')
        self.page.get_by_role('button',name='Skip for now',exact=True).click()
        expect(self.page.locator('#review-progress')).to_contain_text('Paper 2 of 5')
        self.page.get_by_role('button',name='Previous',exact=True).click()
        expect(self.page.locator('#review-rationale')).to_have_value('Incomplete draft retained without a judgment')
        self.reload()
        expect(self.page.locator('#review-rationale')).to_have_value('Incomplete draft retained without a judgment')
        expect(self.page.locator('#review-progress')).to_contain_text('0 with saved observations')
        self.assertEqual(before,{p:project.reviews.history(p) for p in self.fixture.papers})
        # Failure must leave the draft/session in place, never redirect early.
        self.expected_transport_failure=True
        self.page.route('**/api/v1/review/command',lambda route:route.abort('failed'))
        self.page.locator('#review-finish').click()
        expect(self.page.locator('#review-message')).to_contain_text('current input is retained')
        expect(self.page.locator('#review-rationale')).to_have_value('Incomplete draft retained without a judgment')
        self.assertIn('/review#',self.page.url)
        self.page.unroute('**/api/v1/review/command');self.expected_transport_failure=False
        self.page.locator('#review-finish').click()
        expect(self.page.locator('#dashboard-review-result')).to_contain_text('Unassessed papers remain undecided')
        self.page.locator('#dashboard-review-summary').click()
        expect(self.page.locator('#review-summary-counts')).to_contain_text('5')
        expect(self.page.locator('#review-summary-counts')).to_contain_text('Incomplete drafts')
        self.assertEqual(before,{p:project.reviews.history(p) for p in self.fixture.papers})
        self.assertEqual(self.fixture.transport.calls,[]);self.layout()

    def test_review_unauthorized_and_empty_project(self):
        self.open_project();self.start_guided_review(reviewer='configuration_author')
        self.page.locator('input[name="assessment"][value="included"]').check()
        self.page.locator('#review-extent').select_option('metadata')
        self.page.locator('#review-rationale').fill('Invented non-authoritative observation')
        self.page.locator('#review-save-next').click()
        expect(self.page.locator('#review-message')).to_contain_text('Human observation saved')
        self.page.locator('#review-show-summary').click()
        self.page.locator('#review-finish').click()
        expect(self.page.locator('#dashboard-review-result')).to_contain_text('Finishing did not change corpus membership')
        self.page.locator('#dashboard-review-summary').click()
        expect(self.page.locator('#review-authority-status')).to_contain_text('not authorized')
        expect(self.page.locator('#review-prepare-publication')).to_be_hidden()
        # Capture the real content bounds, not Chromium's transient old scroll
        # extent after the taller assessment panel has collapsed. Nothing in
        # main is hidden/masked for this screenshot; page overflow is still checked.
        self.snapshot('review-unauthorized',subject='main');self.layout()
        expect(self.page.locator('#assessment-form')).to_be_hidden()
        expect(self.page.locator('#review-save-next')).to_be_hidden()
        token=self.page.locator('meta[name="corpustrail-session"]').get_attribute('content')
        handle=self.page.url.split('#')[1]
        headers={'X-CorpusTrail-Session':token,'X-CorpusTrail-CSRF':token,'Origin':self.fixture.origin}
        current=self.context.request.get(self.fixture.origin+'/api/v1/review/sessions/'+handle,headers=headers).json()
        import uuid
        refused=self.context.request.post(self.fixture.origin+'/api/v1/review/command',headers=headers,
            data={'schema':'corpustrail-guided-review/v1','handle':handle,'command_id':uuid.uuid4().hex,
                  'expected_revision':current['revision'],'action':'prepare_publication','value':None})
        self.assertEqual(refused.status,409)
        self.assertTrue(all(self.fixture.project.reviews.membership(p)['state']=='not_reviewed' for p in self.fixture.papers))
        self.page.get_by_role('button',name='Back to Review Overview',exact=True).click()
        expect(self.page.locator('#review-overview')).to_be_visible()
        self.snapshot('review-completed-overview');self.layout()
        self.page.get_by_role('button',name='View Review Summary',exact=True).click()
        expect(self.page.locator('#review-summary')).to_be_visible()
        self.page.get_by_role('link',name='Back to Project Dashboard',exact=True).click()
        expect(self.page.locator('#project-name')).to_have_text('Synthetic materials')
        from corpustrail.project import Project,ProjectConfig,ReviewPolicy
        empty=Project.create(self.fixture.root/'empty',ProjectConfig('empty-review','Empty review project','Invented empty fixture',review=ReviewPolicy(scope=SCOPE)),created_by='fixture')
        self.visit('/projects')
        self.page.locator('#project-list article').filter(has=self.page.get_by_role('heading',name='Empty review project',exact=True)).get_by_role('button',name='Open Project').click()
        expect(self.page).to_have_url(self.fixture.origin+'/dashboard')
        expect(self.page.locator('#project-name')).to_have_text('Empty review project')
        self.visit('/review');expect(self.page.locator('#review-empty')).to_contain_text('No publications')
        self.snapshot('review-empty');self.layout()
        self.assertEqual(empty.identities.papers(),[])
        self.assertEqual(self.fixture.transport.calls,[])

    def test_evidence_verification_mismatch_and_refresh(self):
        self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click()
        expect(self.page.locator('#abstract')).to_have_text(ABSTRACT)
        expect(self.page.locator('#abstract-source')).to_contain_text('Bibliographic/discovery metadata abstract')
        self.assertEqual(self.fixture.transport.calls,[])
        expect(self.page.locator('#evidence-eligibility')).to_contain_text('PMC123')
        self.snapshot('evidence-availability');self.layout()
        self.fixture.transport.gate=threading.Event()
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-result')).to_contain_text(re.compile('running|queued'))
        self.fixture.transport.gate.set()
        expect(self.page.locator('#evidence-history')).to_contain_text('Exact document identity verified',timeout=15000)
        expect(self.page.get_by_role('button',name='Read verified structured text')).to_be_visible()
        self.page.get_by_role('button',name='Read verified structured text').click()
        expect(self.page.locator('#document-text')).to_contain_text('Invented structured scientific fixture text')
        self.snapshot('evidence-result');self.layout()
        self.page.locator('#advanced-evidence summary').click()
        self.page.get_by_role('button',name='Show complete provenance records').click()
        expect(self.page.locator('#evidence-raw')).to_contain_text('representation')
        expect(self.page.locator('#evidence-raw')).to_contain_text('bounded-inert-jats/v2')
        expect(self.page.locator('#evidence-raw')).to_contain_text('xml_parse_input_sha256')
        self.snapshot('evidence-provenance')
        valid=self.fixture.project.evidence.representations(self.fixture.papers[0],trusted_only=True)
        self.fixture.transport.mismatch=True
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-history')).to_contain_text('Document identity mismatch — not trusted',timeout=15000)
        self.assertEqual(valid,self.fixture.project.evidence.representations(self.fixture.papers[0],trusted_only=True))
        self.snapshot('evidence-mismatch')
        self.fixture.transport.mismatch=False;self.fixture.transport.invalid=True
        self.page.get_by_role('button',name='Retrieve structured text from Europe PMC',exact=True).click()
        expect(self.page.locator('#evidence-history')).to_contain_text('Invalid document — not trusted',timeout=15000)
        self.assertEqual(valid,self.fixture.project.evidence.representations(self.fixture.papers[0],trusted_only=True))
        self.layout()
        self.reload()
        expect(self.page.locator('#evidence-history')).to_contain_text('Document identity mismatch — not trusted')
        expect(self.page.locator('#evidence-operations button')).to_have_count(3)
        self.assertEqual(len(self.fixture.transport.calls),3)
        self.assertEqual(self.fixture.project.reviews.history(self.fixture.papers[0]),[])
        self.assertEqual(self.fixture.project.reviews.membership(self.fixture.papers[0])['state'],'not_reviewed')
        self.page.get_by_role('button',name='Read verified structured text').click()
        expect(self.page.locator('#document-text')).to_contain_text('Invented structured scientific fixture text')
        before_restart=fingerprint(self.fixture.root)
        self.restart()
        self.open_project();self.visit('/papers')
        self.page.get_by_role('link',name=TITLE,exact=True).click()
        expect(self.page.locator('#evidence-operations button')).to_have_count(3)
        expect(self.page.locator('#evidence-history')).to_contain_text('Exact document identity verified')
        expect(self.page.locator('#evidence-history')).to_contain_text('Document identity mismatch — not trusted')
        expect(self.page.locator('#evidence-history')).to_contain_text('Invalid document — not trusted')
        self.page.get_by_role('button',name='Read verified structured text').click()
        expect(self.page.locator('#document-text')).to_contain_text('Invented structured scientific fixture text')
        self.assertEqual(len(self.fixture.transport.calls),3)
        self.assertEqual(before_restart,fingerprint(self.fixture.root))
        self.assertEqual(self.fixture.project.reviews.history(self.fixture.papers[0]),[])
        self.assertEqual(self.fixture.project.reviews.membership(self.fixture.papers[0])['state'],'not_reviewed')
