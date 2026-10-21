"""Deterministic contract fixtures. No scientific engine or performance claim."""
import json

from corpustrail._internal.values import content_hash
from corpustrail.classification import Assessment, AssessmentFailure, AssessmentPlan, EngineDescription, Score


class OfflineEngine:
    def __init__(self, engine_id='synthetic.a', *, outcome='uncertain', score_type=None, locality='local', response=None):
        self.engine_id = engine_id; self.outcome = outcome; self.score_type = score_type
        self.locality = locality; self.response = response; self.calls = 0; self.seen = []

    def describe(self):
        return EngineDescription(self.engine_id, 'v1', content_hash({'fixture': self.engine_id, 'outcome': self.outcome, 'score_type': self.score_type}),
            'synthetic-provider', 'synthetic-adapter', 'v1', 'no-real-model',
            score_types=(self.score_type,) if self.score_type else (), locality=self.locality)

    def prepare(self, request):
        return AssessmentPlan(request.request_sha256, request.engine_sha256, content_hash(json.loads(request.settings_json)),
                              {'fixture_only': True})

    def assess(self, plan, chunk):
        self.calls += 1
        if self.response is not None: return self.response(plan, chunk)
        results = []
        for unit in chunk:
            value = unit.input(); references = list(unit.references())
            self.seen.append({'input': value, 'references': references, 'input_sha256': unit.input_sha256})
            target = value['target']
            results.append(Assessment(target['paper_id'], self.outcome,
                'unknown' if self.outcome == 'uncertain' else 'sufficient',
                'Invented deterministic contract result; no scientific inference.',
                (target['representation']['sha256'],), 'Fixture uncertainty only',
                ('Synthetic output is not scientific evidence or a validated model.',),
                score=Score(0.72, self.score_type, 'Synthetic typed value, not calibrated inclusion probability') if self.score_type else None))
        return tuple(results)


def fail_every_item(plan, chunk):
    return tuple(AssessmentFailure(unit.input()['target']['paper_id'], 'unavailable', retryable=True) for unit in chunk)
