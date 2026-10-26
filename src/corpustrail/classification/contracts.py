"""Engine contracts: installed adapters are code, their responses untrusted data.

No project, path, network client or scientific write capability is passed to an
engine. This minimizes capabilities; it is not a sandbox for installed Python.
"""
from dataclasses import asdict, dataclass, field
import math
from typing import Callable, Iterator, Protocol

from corpustrail._internal.values import ContractError, canonical, sha256, timestamp
from corpustrail.models.contracts import name, safe_data
from corpustrail.references.contracts import bounded_text

SCHEMA = 'corpustrail-assessment-plan/v1'
CAPABILITY = 'broad-corpus-assessment/v1'
OUTCOMES = {'include', 'exclude', 'uncertain'}
SUFFICIENCY = {'sufficient', 'insufficient', 'unknown'}
SCORE_TYPES = {'similarity', 'classifier_probability', 'model_confidence', 'calibrated_probability'}


def json_value(value, maximum=65536):
    try:
        body = canonical(value)
        safe_data(value)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContractError('bounded non-secret JSON data required') from exc
    if len(body.encode('utf-8')) > maximum:
        raise ContractError('JSON value exceeds its declared per-record resource bound')
    return body


@dataclass(frozen=True)
class Budgets:
    chunk_size: int = 20
    max_input_bytes: int = 1_000_000
    max_output_bytes: int = 65536
    max_items_per_execution: int = 100
    max_reference_bytes: int = 64_000_000
    max_seconds_per_execution: int = 60

    def to_dict(self):
        for key, low, high in (('chunk_size', 1, 100), ('max_input_bytes', 1024, 4_000_000),
                               ('max_output_bytes', 1024, 1_000_000), ('max_items_per_execution', 1, 10000),
                               ('max_reference_bytes', 1024, 4_000_000_000), ('max_seconds_per_execution', 1, 3600)):
            if type(getattr(self, key)) is not int or not low <= getattr(self, key) <= high:
                raise ContractError('invalid explicit execution budget: ' + key)
        return asdict(self)


@dataclass(frozen=True)
class EngineDescription:
    engine_id: str
    version: str
    implementation_sha256: str
    provider_id: str
    adapter_id: str
    adapter_version: str
    configured_model: str
    input_modes: tuple[str, ...] = ('full_set', 'bounded_context')
    score_types: tuple[str, ...] = ()
    locality: str = 'local'
    execution: str = 'offline'
    capability: str = CAPABILITY

    def to_dict(self):
        for value in (self.engine_id, self.version, self.provider_id, self.adapter_id,
                      self.adapter_version, self.configured_model): name(value)
        sha256(self.implementation_sha256)
        expected = 'broad-corpus-assessment/v2' if self.execution == 'network' else CAPABILITY
        if self.capability != expected or self.execution not in {'offline', 'network'}:
            raise ContractError('explicit versioned installed assessment capability required')
        if self.locality not in {'local', 'remote_declared_mock', 'remote'} or (self.execution == 'network') != (self.locality == 'remote'):
            raise ContractError('network execution requires remote locality and exact transmitted-payload consent')
        if not isinstance(self.input_modes, tuple) or not self.input_modes or not set(self.input_modes) <= {'full_set', 'bounded_context'}:
            raise ContractError('explicit supported input modes required')
        if not isinstance(self.score_types, tuple) or not set(self.score_types) <= SCORE_TYPES:
            raise ContractError('unknown engine score semantics')
        if len(set(self.input_modes)) != len(self.input_modes) or len(set(self.score_types)) != len(self.score_types):
            raise ContractError('engine capabilities cannot repeat')
        result = asdict(self); json_value(result)
        return result


@dataclass(frozen=True)
class ClassifierPolicy:
    policy_id: str = 'explicit-engine-observation'
    version: str = 'v1'
    score_type: str | None = None
    score_direction: str | None = None
    include_band: tuple[float, float] | None = None
    exclude_band: tuple[float, float] | None = None
    uncertainty_rule: str = 'engine_explicit; missing evidence is not exclusion'

    def to_dict(self):
        name(self.policy_id); name(self.version)
        bounded_text(self.uncertainty_rule, 'uncertainty policy', 1000)
        if self.score_type is not None and self.score_type not in SCORE_TYPES:
            raise ContractError('unknown classifier score type')
        if self.score_direction not in {None, 'higher_more_in_scope', 'lower_more_in_scope'}:
            raise ContractError('explicit score direction required')
        if (self.include_band is None) != (self.exclude_band is None):
            raise ContractError('both explicit score bands required; no implicit 0.5 threshold')
        if self.include_band is not None:
            if self.score_type is None or self.score_direction is None:
                raise ContractError('score bands require named semantics and direction')
            for band in (self.include_band, self.exclude_band):
                if not isinstance(band, tuple) or len(band) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in band) or band[0] > band[1]:
                    raise ContractError('finite ordered score bands required')
            if max(self.include_band[0], self.exclude_band[0]) <= min(self.include_band[1], self.exclude_band[1]):
                raise ContractError('include/exclude bands cannot overlap')
            if self.score_direction == 'higher_more_in_scope' and self.include_band[0] <= self.exclude_band[1] or self.score_direction == 'lower_more_in_scope' and self.exclude_band[0] <= self.include_band[1]:
                raise ContractError('score bands contradict their direction')
        return asdict(self)


@dataclass(frozen=True)
class ValidationProtocol:
    protocol_id: str = 'explicit-roles'
    version: str = 'v1'
    purpose: str = 'operational'
    calibration_population_version: str | None = None
    held_out_population_version: str | None = None
    label_cutoff: str | None = None
    self_match: str = 'exclude'

    def to_dict(self):
        from corpustrail.populations.contracts import version_id
        name(self.protocol_id); name(self.version)
        if self.purpose not in {'operational', 'calibration', 'held_out_evaluation'}:
            raise ContractError('choose explicit training/calibration/evaluation roles')
        for value in (self.calibration_population_version, self.held_out_population_version):
            if value is not None: version_id(value)
        if self.label_cutoff is not None: timestamp(self.label_cutoff)
        if self.self_match not in {'exclude', 'include_operational'}:
            raise ContractError('explicit self-match policy required')
        if self.purpose != 'operational' and (self.self_match != 'exclude' or self.label_cutoff is None):
            raise ContractError('independent validation requires self exclusion and an explicit label cutoff')
        if self.purpose == 'calibration' and self.calibration_population_version is None or self.purpose == 'held_out_evaluation' and self.held_out_population_version is None:
            raise ContractError('validation purpose requires its frozen population')
        return asdict(self)


@dataclass(frozen=True)
class CalibrationBinding:
    """Provenance hook, not a calibrator or proof of scientific validation."""
    calibration_id: str
    version: str
    source_run_id: str
    protocol_sha256: str
    score_type: str
    artifact_sha256: str
    validation_state: str = 'unvalidated'

    def to_dict(self):
        from corpustrail.references.contracts import exact_id
        name(self.calibration_id); name(self.version)
        exact_id(self.source_run_id, 'assessment-run')
        sha256(self.protocol_sha256); sha256(self.artifact_sha256)
        if self.score_type not in SCORE_TYPES or self.validation_state != 'unvalidated':
            raise ContractError('CP8 records calibration provenance, not invented validated calibration')
        return asdict(self)


@dataclass(frozen=True)
class AuditProtocol:
    protocol_id: str
    version: str
    seed: int
    per_group: int
    groups: tuple[str, ...] = ('exclude', 'uncertain', 'include', 'disagreement')

    def to_dict(self):
        name(self.protocol_id); name(self.version)
        if type(self.seed) is not int or type(self.per_group) is not int or not 1 <= self.per_group <= 100:
            raise ContractError('bounded audit sample and explicit integer seed required')
        if not isinstance(self.groups, tuple) or not self.groups or len(set(self.groups)) != len(self.groups) or not set(self.groups) <= {'include', 'exclude', 'uncertain', 'disagreement', 'failure', 'insufficient'}:
            raise ContractError('explicit non-repeating audit strata required')
        return asdict(self)


@dataclass(frozen=True)
class Score:
    value: float
    score_type: str
    meaning: str
    calibration_id: str | None = None

    def to_dict(self):
        if type(self.value) not in (int, float) or not math.isfinite(self.value) or self.score_type not in SCORE_TYPES:
            raise ContractError('finite typed score required')
        bounded_text(self.meaning, 'score meaning', 1000)
        if self.score_type in {'classifier_probability', 'calibrated_probability', 'model_confidence'} and not 0 <= self.value <= 1:
            raise ContractError('probability/confidence fractions must be within [0,1]')
        if self.calibration_id is not None: name(self.calibration_id)
        return asdict(self)


@dataclass(frozen=True)
class Assessment:
    paper_id: str
    outcome: str
    evidence_sufficiency: str
    rationale: str
    evidence_hashes: tuple[str, ...]
    uncertainty: str
    limitations: tuple[str, ...]
    reported_model: str | None = None
    model_usage_ambiguity: bool = True
    score: Score | None = None
    usage: dict = field(default_factory=dict)

    def to_dict(self):
        from corpustrail.references.contracts import exact_id
        exact_id(self.paper_id, 'ct-paper')
        if self.outcome not in OUTCOMES or self.evidence_sufficiency not in SUFFICIENCY:
            raise ContractError('unknown assessment outcome or evidence sufficiency')
        if self.evidence_sufficiency != 'sufficient' and self.outcome == 'exclude':
            raise ContractError('insufficient/unknown evidence cannot establish an exclude assessment')
        bounded_text(self.rationale, 'assessment rationale', 8000)
        bounded_text(self.uncertainty, 'explicit uncertainty', 2000)
        if not isinstance(self.evidence_hashes, tuple) or len(set(self.evidence_hashes)) != len(self.evidence_hashes):
            raise ContractError('exact non-repeating evidence hashes required')
        for value in self.evidence_hashes: sha256(value)
        if not isinstance(self.limitations, tuple) or len(self.limitations) > 32:
            raise ContractError('bounded explicit limitations required')
        for value in self.limitations: bounded_text(value, 'assessment limitation', 1000)
        if type(self.model_usage_ambiguity) is not bool: raise ContractError('explicit model ambiguity required')
        if self.reported_model is not None: name(self.reported_model)
        elif not self.model_usage_ambiguity: raise ContractError('unreported model cannot claim certain identity')
        if self.score is not None and not isinstance(self.score, Score): raise ContractError('typed score required')
        if not isinstance(self.usage, dict): raise ContractError('bounded JSON usage metadata required')
        result = asdict(self)
        if self.score is not None: result['score'] = self.score.to_dict()
        json_value(result)
        return result


@dataclass(frozen=True)
class AssessmentFailure:
    paper_id: str
    reason: str
    retryable: bool = False
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self):
        from corpustrail.references.contracts import exact_id
        exact_id(self.paper_id, 'ct-paper')
        if self.reason not in {'unavailable', 'resource_exhausted', 'unsupported_evidence', 'engine_error', 'invalid_output', 'interrupted_no_response'} or type(self.retryable) is not bool:
            raise ContractError('sanitized typed execution failure required')
        if not isinstance(self.diagnostics, dict): raise ContractError('bounded non-secret failure diagnostics required')
        result = asdict(self)
        if self.diagnostics:
            json_value(self.diagnostics, 60000)
            result['diagnostic_schema'] = 'corpustrail-assessment-diagnostics/v1'
        else: result.pop('diagnostics')  # Preserve the exact legacy v1 failure shape.
        return result


@dataclass(frozen=True)
class AssessmentPlan:
    request_sha256: str
    engine_sha256: str
    settings_sha256: str
    preparation: dict = field(default_factory=dict)

    def to_dict(self):
        for value in (self.request_sha256, self.engine_sha256, self.settings_sha256): sha256(value)
        if not isinstance(self.preparation, dict): raise ContractError('bounded engine preparation object required')
        json_value(self.preparation, 8000)
        return asdict(self)


@dataclass(frozen=True)
class EngineRequest:
    """Detached request descriptor; no target answers or project capability."""
    request_sha256: str
    descriptor_json: str
    engine_sha256: str
    settings_json: str

    def descriptor(self):
        import json
        return json.loads(self.descriptor_json)


@dataclass(frozen=True)
class ExecutionUnit:
    plan_id: str
    input_sha256: str
    input_json: str
    reference_count: int
    _references: Callable[[], Iterator[str]] = field(repr=False, compare=False)

    def input(self):
        import json
        return json.loads(self.input_json)

    def references(self):
        """Fresh detached rows streamed in frozen order, without a collection cap."""
        import json
        for value in self._references(): yield json.loads(value)


class AssessmentEngine(Protocol):
    def describe(self) -> EngineDescription: ...
    def prepare(self, request: EngineRequest) -> AssessmentPlan: ...
    def assess(self, plan: AssessmentPlan, chunk: tuple[ExecutionUnit, ...]) -> tuple[Assessment | AssessmentFailure, ...]: ...
