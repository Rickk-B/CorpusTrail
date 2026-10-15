"""Versioned population boundary, including an adapter-facing import interface.

ImportedSource references observations ALREADY enrolled through IdentityService
and an ALREADY preserved source artifact. It neither parses files nor establishes
identity, evidence trust, review labels or membership. No format adapter ships.
"""
from dataclasses import dataclass
import re

from corpustrail._internal.values import ContractError, sha256, text

SCHEMA = 'corpustrail-candidate-population/v1'
POLICY = 'exact-canonical-union/v1'


def command_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise ContractError('invalid population request identity')


def version_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'population-version:[0-9a-f]{64}', value):
        raise ContractError('choose a population version from this project')
    return value


def page(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ContractError('choose a valid population page')


@dataclass(frozen=True)
class ImportedSource:
    source_id: str
    adapter_id: str
    adapter_version: str
    artifact_sha256: str
    observation_ids: tuple[str, ...]
    schema: str = 'corpustrail-imported-population-source/v1'

    def validate(self):
        if self.schema != 'corpustrail-imported-population-source/v1':
            raise ContractError('unsupported imported-source interface')
        for key in ('source_id', 'adapter_id', 'adapter_version'):
            text(getattr(self, key), key)
            if len(getattr(self, key)) > 200:
                raise ContractError('source description is too long')
        sha256(self.artifact_sha256)
        if not isinstance(self.observation_ids, tuple) or any(not isinstance(x, str) for x in self.observation_ids):
            raise ContractError('source observations must be immutable exact references')
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ContractError('source observations must not repeat')
