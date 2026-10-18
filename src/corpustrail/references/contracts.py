"""CP7 contracts, independent of any classifier engine or provider."""
import re
from dataclasses import dataclass, asdict

from corpustrail._internal.values import ContractError, text, content_hash, sha256

SCHEMA = 'corpustrail-reference-set/v1'
POLICY = 'explicit-human-unconflicted/v1'
CONTEXT_SCHEMA = 'corpustrail-selected-reference-context/v1'
STRATEGY = 'canonical-reference-order/v1'
LABELS = {'in_scope', 'out_of_scope'}


def implementation_hash():
    """Installed scientific selector bytes, independent of any Git checkout."""
    from importlib import resources
    from corpustrail._internal.values import digest_bytes
    package=resources.files('corpustrail.references')
    return content_hash({name:digest_bytes(package.joinpath(name).read_bytes())
        for name in ('__init__.py','contracts.py','service.py','storage.py','evidence.py','context.py')})


def bounded_text(value, name, maximum=2000, *, empty=False):
    if empty and value == '':return
    text(value, name)
    if len(value) > maximum:raise ContractError(name+' exceeds the per-record bound')


def exact_id(value, namespace):
    if not isinstance(value,str) or not re.fullmatch(re.escape(namespace)+r':[0-9a-f]{64}',value):
        raise ContractError('choose an exact '+namespace+' identity from this project')
    return value


@dataclass(frozen=True)
class ContextStrategy:
    """A deterministic local selector, not a relevance classifier.

    Character limits are explicit Unicode-codepoint budgets, not invented model
    token counts. Exhausted candidates have recorded reasons, never disappear.
    """
    in_scope: int = 6
    out_of_scope: int = 3
    max_characters: int = 12000
    max_per_reference: int = 2000
    allow_truncation: bool = False
    self_match: str = 'exclude'
    include_unvalidated_derived: bool = False
    strategy_id: str = STRATEGY

    def validate(self):
        if self.strategy_id != STRATEGY:raise ContractError('unsupported reference-selection strategy')
        for name,maximum in (('in_scope',100),('out_of_scope',100),('max_characters',50000),('max_per_reference',10000)):
            value=getattr(self,name)
            if type(value) is not int or not 0 <= value <= maximum:raise ContractError('invalid bounded context '+name)
        if self.max_characters == 0 or self.max_per_reference == 0:raise ContractError('context budgets must be positive')
        if self.self_match not in {'exclude','include_operational'}:raise ContractError('choose an explicit self-match policy')
        if type(self.allow_truncation) is not bool or type(self.include_unvalidated_derived) is not bool:
            raise ContractError('context policy requires explicit boolean choices')

    def to_dict(self):
        self.validate()
        return {**asdict(self),'score_semantics':'none; deterministic identity order, not relevance or probability',
            'character_unit':'Unicode codepoints','eligibility_policy':POLICY}


@dataclass(frozen=True)
class DerivedDependency:
    """Already produced bytes only; no engine, index construction or generation.

    Registration never attests a derived artifact as reference truth. Exact
    complete source assignment IDs must be declared; use in a context requires
    explicit inclusion of unvalidated derived material and leakage checks.
    """
    kind: str
    producer: dict
    source_assignment_ids: tuple[str,...]
    settings: dict
    validation_state: str = 'unvalidated'

    def validate(self):
        from corpustrail.curation.service import _PRODUCER_TYPES
        from corpustrail.models.contracts import safe_data
        if self.kind not in {'index','profile'} or self.validation_state != 'unvalidated':
            raise ContractError('CP7 registers unvalidated derived artifacts, not independent scientific validation')
        if not isinstance(self.producer,dict) or set(self.producer) != {'type','id','version'} or self.producer['type'] not in _PRODUCER_TYPES:raise ContractError('derived producer identity/version required')
        for key,value in self.producer.items():bounded_text(value,'derived producer '+key,200)
        if not isinstance(self.source_assignment_ids,tuple) or not self.source_assignment_ids or len(set(self.source_assignment_ids)) != len(self.source_assignment_ids):
            raise ContractError('derived source assignments must be exact unique immutable IDs')
        for aid in self.source_assignment_ids:exact_id(aid,'reference-assignment')
        if not isinstance(self.settings,dict) or len(str(self.settings))>8000:raise ContractError('bounded derived settings required')
        sha256(content_hash(self.settings))
        safe_data(asdict(self))
