"""Actual Chromium / packaged HTTP end-to-end tests; no frontend API mocks."""
import json
import re
import queue
import subprocess
import sys
import threading
import unittest

from playwright.sync_api import expect
from .fixtures import ApplicationFixture, ABSTRACT, SCOPE, TITLE, fingerprint


class BrowserAcceptance(unittest.TestCase):
    runtime = None  # Explicit runner-owned browser/report; never auto-discovered.

    def setUp(self):
        self.fixture = ApplicationFixture()
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
        self.local_requests=0
        self.external_requests=0
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
        self.page.on('console', lambda msg: self.diagnostics.append('Console: '+msg.text) if msg.type=='error' else None)
        self.page.on('requestfailed', lambda req: self.diagnostics.append('Failed local request: '+req.method+' '+req.url.split('?')[0]))
        self.page.on('response', lambda response: self.diagnostics.append('HTTP '+str(response.status)+' '+response.url.split('?')[0])
            if response.status>=400 and response.status not in self.expected_http_errors else None)
        self.visit('/')

    def tearDown(self):
        errors = self.diagnostics+self.fixture.errors+self.fixture.transport.errors
        self.runtime.finish_case(self, errors)
        self.assertEqual(errors, [], 'Browser/backend diagnostics must be clean')

    def visit(self, path):
        self.page.goto(self.fixture.origin+path, wait_until='networkidle')
        token=self.page.locator('meta[name="corpustrail-session"]').get_attribute('content')
        if token: self.tokens.add(token)
        expect(self.page.locator('main h1:visible')).to_have_count(1)

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
        self.assertEqual(self.fixture.transport.calls,[])
        self.visit('/papers')
        expect(self.page.locator('#paper-list article')).to_have_count(5)
        self.layout();self.snapshot('catalogue')
        # Existing macOS filter-box regression: compare actual boxes, not labels.
        if self.runtime.viewport['width']>=1000:
            boxes=[self.page.locator(s).bounding_box() for s in ('#sort','#page-size','#filters button')]
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
        self.page.keyboard.press('Tab')
        focus=self.page.evaluate('''() => {const e=document.activeElement,c=getComputedStyle(e);return {tag:e.tagName,outline:c.outlineStyle,width:parseFloat(c.outlineWidth)};}''')
        self.assertNotEqual(focus['tag'],'BODY');self.assertNotEqual(focus['outline'],'none');self.assertGreater(focus['width'],0)

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
        self.page.reload(wait_until='networkidle')
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
        self.page.reload(wait_until='networkidle')
        expect(self.page.locator('#history button')).to_have_count(2)
        self.assertEqual(len(self.fixture.transport.calls),8)

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
        self.page.reload(wait_until='networkidle')
        expect(self.page.locator('#evidence-history')).to_contain_text('Document identity mismatch — not trusted')
        expect(self.page.locator('#evidence-operations button')).to_have_count(3)
        self.assertEqual(len(self.fixture.transport.calls),3)
        self.assertEqual(self.fixture.project.reviews.history(self.fixture.papers[0]),[])
        self.assertEqual(self.fixture.project.reviews.membership(self.fixture.papers[0])['state'],'not_reviewed')
        self.page.get_by_role('button',name='Read verified structured text').click()
        expect(self.page.locator('#document-text')).to_contain_text('Invented structured scientific fixture text')
        before_restart=fingerprint(self.fixture.root)
        self.fixture.restart()
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
