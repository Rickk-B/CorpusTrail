"""Bounded CP7 path exception: never suppress unrelated pixels or assertions."""
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
from PIL import Image,ImageDraw
from .path_visual_debt import path_reflow_evidence
from .visual import compare


class PathVisualDebtTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ct-path-debt-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.before=self.root/'before.png';self.after=self.root/'after.png'
        self.environment={'platform':'darwin','browser':'chromium'}
        self.paths=[{'truthful':True,'contained':True,'overflow':0,'line_height':24,'height':48}]
        self.draw(self.before,24);self.draw(self.after,48)

    @staticmethod
    def draw(path,height):
        image=Image.new('RGB',(390,180+height),'white');draw=ImageDraw.Draw(image)
        draw.text((20,10),'Project setup',fill='black')
        draw.rectangle((20,80,369,80+height-1),fill='#e2ecee')
        draw.text((20,100+height),'Research projects belong to you.',fill='black')
        draw.rectangle((20,130+height,90,155+height),outline='black')
        draw.text((25,135+height),'Next',fill='black');image.save(path)

    def evidence(self,**changes):
        args={'environment':self.environment,'capture':'narrow-wizard.png','paths':self.paths,'viewport_height':100}
        args.update(changes)
        return path_reflow_evidence(self.before,self.after,**args)

    def test_path_reflow_is_evidenced_but_strict_comparison_still_fails(self):
        original=(self.before.read_bytes(),self.after.read_bytes())
        self.assertFalse(compare(self.before,self.after,self.root/'diff.png')['passed'])
        proof=self.evidence();self.assertTrue(proof['verified']);self.assertFalse(proof['strict_comparison_passed'])
        self.assertEqual(proof['actual_path_runs'][0]['rows'],48)
        self.assertTrue(proof['all_other_pixels_accounted'])
        self.assertEqual(original,(self.before.read_bytes(),self.after.read_bytes()))
        self.assertFalse((self.root/'diff.png').exists())  # No altered comparison image.

    def test_only_named_macos_family_and_truthful_contained_paths_qualify(self):
        for capture in ('narrow-reference-context.png','laptop-wizard.png','narrow-settings.png'):
            self.assertFalse(self.evidence(capture=capture)['verified'])
        self.assertFalse(self.evidence(environment={'platform':'linux','browser':'chromium'})['verified'])
        for change in ({'truthful':False},{'contained':False},{'overflow':2},{'height':72},{'line_height':12}):
            self.assertFalse(self.evidence(paths=[{**self.paths[0],**change}])['verified'])

    def test_unrelated_status_or_control_change_is_not_a_path_exception(self):
        for box in ((20,10,80,30),(20,178,80,198),(0,85,15,100)):
            self.draw(self.after,48)
            image=Image.open(self.after);ImageDraw.Draw(image).rectangle(box,fill='red');image.save(self.after)
            self.assertFalse(self.evidence()['verified'],box)

    def test_non_line_height_and_unexplained_blank_space_fail(self):
        self.draw(self.after,36)
        self.assertFalse(self.evidence(paths=[{**self.paths[0],'height':36}])['verified'])
        self.draw(self.after,48)
        image=Image.open(self.after);larger=Image.new('RGB',(390,image.height+24),'white');larger.paste(image,(0,0));larger.save(self.after)
        self.assertFalse(self.evidence()['verified'])

    def test_current_strict_noise_budgets_are_not_widened(self):
        image=Image.open(self.after);image.putpixel((19,100),(237,239,240));image.save(self.after)
        proof=self.evidence();self.assertTrue(proof['verified'])
        noise=proof['actual_path_runs'][0]['row_noise']
        self.assertEqual((noise['channel_tolerance'],noise['max_changed_ratio'],noise['max_tile_ratio_limit']),(16,.0005,.02))

    def runtime_capture(self,*,unrelated=False):
        from tools.browser_acceptance import Runtime
        output=self.root/'runtime';output.mkdir();(output/'screenshots').mkdir();(output/'failures').mkdir()
        baselines=self.root/'baseline';baselines.mkdir();target=baselines/'narrow-wizard.png';target.write_bytes(self.before.read_bytes())
        if unrelated:
            image=Image.open(self.after);ImageDraw.Draw(image).rectangle((20,10,90,30),fill='red');image.save(self.after)
        runtime=object.__new__(Runtime);runtime.output=output;runtime.mode='compare';runtime.environment=self.environment
        runtime.viewport_name='narrow';runtime.viewport={'width':390,'height':100};runtime.screenshots=[];runtime.comparisons=[]
        runtime.baseline_directory=baselines;runtime.baselines={'images_sha256':{'narrow-wizard.png':hashlib.sha256(target.read_bytes()).hexdigest()}}
        runtime.allow_path_reflow=True
        page=Mock()
        page.evaluate.side_effect=lambda script,*args: True if 'document.activeElement' in script else 0
        page.screenshot.side_effect=lambda **kw:Path(kw['path']).write_bytes(self.after.read_bytes())
        case=types.SimpleNamespace(page=page,settle_reads=Mock(),assertEqual=self.assertEqual,assertTrue=self.assertTrue,
            fixture_path_checks=lambda _:self.paths,_testMethodName='test_project_wizard_settings_and_confirmation')
        with patch('tools.browser_acceptance.sys.platform','darwin'),patch.object(runtime,'capture_geometry',return_value={'stable':True}):
            runtime.snapshot(case,'wizard')
        return runtime

    def test_verified_exception_preserves_failure_and_allows_next_assertion(self):
        runtime=self.runtime_capture()
        self.assertFalse(runtime.comparisons[0]['passed'])
        self.assertTrue(runtime.comparisons[0]['path_exception']['verified'])
        self.assertEqual(len(runtime.screenshots),1)  # Following functional code is reached.

    def test_unrelated_failure_still_raises_in_the_real_snapshot_method(self):
        with self.assertRaisesRegex(AssertionError,'Visual regression'):self.runtime_capture(unrelated=True)

    def test_report_separates_functional_strict_exception_and_failure(self):
        runtime=self.runtime_capture();runtime.suite='all';runtime.viewports=['desktop','laptop','narrow'];runtime.cases=[]
        with patch('tools.browser_acceptance.subprocess.check_output',side_effect=['a'*40+'\n','']):
            value=runtime.report(True,'Controlled successful remaining assertions')
        self.assertTrue(value['passed']);self.assertTrue(value['functional_passed']);self.assertFalse(value['strict_visual_passed'])
        self.assertEqual(len(value['path_only_exceptions']),1)
        self.assertTrue((runtime.output/'summary.txt').read_text().startswith('ACCEPTED_WITH_PATH_EXCEPTION'))
        with patch('tools.browser_acceptance.subprocess.check_output',side_effect=['a'*40+'\n','']):
            value=runtime.report(False,'A genuine functional assertion failed')
        self.assertFalse(value['passed']);self.assertFalse(value['functional_passed'])
        self.assertFalse(json.loads((runtime.output/'report.json').read_text())['passed'])
