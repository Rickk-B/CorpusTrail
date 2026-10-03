"""Experimental, provider-neutral extraction and adapter contracts (v0).

Adapters are trusted installed code. Responses are untrusted data, never tools.
"""
from dataclasses import asdict, dataclass, field
import os
import re
from typing import Protocol

from corpustrail._internal.values import ContractError, canonical, content_hash, text

CAPABILITY = 'structured_assertions/v1'
MODES = ('metadata', 'abstract', 'selected_passages', 'full_text')
_SECRET_KEYS = {'apikey', 'token', 'accesstoken', 'refreshtoken', 'password', 'secret',
                'authorization', 'credentials', 'credential', 'headers', 'privatekey'}
_SECRET_PATTERN = re.compile(r'(?:-----BEGIN .*PRIVATE KEY-----|\bBearer\s+\S+|'
                             r'\bsk-[A-Za-z0-9_-]{12,}|\bgh[pousr]_[A-Za-z0-9]{20,}|'
                             r'https?://[^\s/]+@)', re.I)


def safe_data(value, *, secrets=()):
    """Reject credential-like keys/signatures and exact runtime secrets; redact errors.

    This is a guard, not a general PII detector or a sandbox for plugin code.
    """
    body = canonical(value)
    if _SECRET_PATTERN.search(body) or any(secret and secret in body for secret in secrets):
        raise ContractError('sensitive configuration/output rejected; value not logged')
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or re.sub(r'[^a-z]', '', key.casefold()) in _SECRET_KEYS:
                raise ContractError('secret fields are not allowed in persisted data')
            safe_data(item, secrets=secrets)
    elif isinstance(value, (list, tuple)):
        for item in value:
            safe_data(item, secrets=secrets)
    return value


def name(value):
    if not isinstance(value, str) or '://' in value or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,199}', value):
        raise ContractError('expected a non-secret identifier, not a URL or credential')
    safe_data(value)


@dataclass(frozen=True)
class ModelConfig:
    workflow_id: str
    adapter: str
    model: str
    endpoint_id: str | None = None
    credential_env: str | None = None
    settings: dict = field(default_factory=dict)
    adapter_configuration: dict = field(default_factory=dict)

    def validate(self):
        for value in (self.workflow_id, self.adapter, self.model):
            name(value)
        if self.endpoint_id is not None:
            name(self.endpoint_id)
        if self.credential_env is not None and (not isinstance(self.credential_env, str) or
                not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', self.credential_env)):
            raise ContractError('credential_env must name an environment variable')
        if not isinstance(self.settings, dict):
            raise ContractError('settings must be non-secret JSON configuration')
        if not isinstance(self.adapter_configuration, dict):
            raise ContractError('adapter_configuration must be non-secret JSON configuration')
        safe_data(asdict(self), secrets=(os.environ.get(self.credential_env, '')
                                        if self.credential_env else '',))


@dataclass(frozen=True)
class AdapterInfo:
    adapter_id: str
    provider_id: str
    version: str
    data_leaves_machine: bool
    capabilities: tuple[str, ...] = (CAPABILITY,)
    credentials_required: bool = False

    def validate(self):
        for value in (self.adapter_id, self.provider_id, self.version):
            name(value)
        if type(self.data_leaves_machine) is not bool or type(self.credentials_required) is not bool:
            raise ContractError('adapter must explicitly declare execution/credential policy')
        if not isinstance(self.capabilities, tuple) or not self.capabilities:
            raise ContractError('immutable capabilities required')
        for value in self.capabilities:
            name(value)
        safe_data(asdict(self))


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    version: str
    instructions: str
    predicates: tuple[str, ...]
    evidence_modes: tuple[str, ...] = MODES
    max_claims: int = 64
    output_schema: str = CAPABILITY

    def to_dict(self):
        name(self.task_id); name(self.version); text(self.instructions, 'task instructions')
        if (not isinstance(self.predicates, tuple) or not self.predicates or
                len(set(self.predicates)) != len(self.predicates)):
            raise ContractError('unique explicit predicates required')
        for predicate in self.predicates:
            name(predicate)
        if not isinstance(self.evidence_modes, tuple) or not set(self.evidence_modes) <= set(MODES):
            raise ContractError('unknown evidence mode')
        if type(self.max_claims) is not int or not 1 <= self.max_claims <= 128:
            raise ContractError('bounded assertion output required')
        if self.output_schema != CAPABILITY:
            raise ContractError('unsupported structured output schema')
        result = asdict(self)
        safe_data(result)
        return result

    @property
    def sha256(self):
        return content_hash(self.to_dict())

    @classmethod
    def from_dict(cls, raw):
        try:
            result = cls(**{**raw, 'predicates': tuple(raw['predicates']),
                            'evidence_modes': tuple(raw.get('evidence_modes', MODES))})
            result.to_dict()
            return result
        except (TypeError, KeyError) as exc:
            raise ContractError('invalid task specification') from exc


@dataclass(frozen=True)
class ModelResponse:
    """JSON-only response envelope; no arbitrary provider headers/error messages."""
    output: dict
    reported_model: str | None = None
    observed_models: tuple[str, ...] = ()
    model_usage_ambiguity: bool = True
    response_id: str | None = None
    usage: dict = field(default_factory=dict)
    failure: str | None = None
    reported_model_version: str | None = None
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self):
        if self.failure not in (None, 'unavailable', 'rate_limited', 'rejected', 'provider_error'):
            raise ContractError('unknown provider failure code')
        if not isinstance(self.output, dict) or not isinstance(self.usage, dict) or not isinstance(self.diagnostics, dict):
            raise ContractError('response must contain JSON output/usage objects')
        if not isinstance(self.observed_models, tuple) or type(self.model_usage_ambiguity) is not bool:
            raise ContractError('explicit observed model/ambiguity metadata required')
        for value in (*self.observed_models, self.reported_model, self.response_id, self.reported_model_version):
            if value is not None:
                name(value)
        if self.reported_model is not None and self.reported_model not in self.observed_models:
            raise ContractError('reported model must appear in observed models')
        if not self.observed_models and not self.model_usage_ambiguity:
            raise ContractError('unobserved model use cannot be reported as certain')
        result = asdict(self)
        safe_data(result)
        return result


class ModelAdapter(Protocol):
    info: AdapterInfo

    def invoke(self, request: dict, *, credential: str | None) -> ModelResponse:
        """One explicit invocation; no project handle, paths, tools or automatic retries."""
        ...
