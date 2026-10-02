"""Provider-neutral discovery plans; observations are never canonical records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from corpustrail._internal.values import ContractError, canonical, identifier, text, timestamp
from corpustrail.identity import BibliographicRecord


@dataclass(frozen=True)
class SearchPlan:
    project_id: str
    run_id: str
    provider: str
    adapter_version: str
    query: str
    config_event_id: str
    created_at: str
    concept_id: str | None = None
    page_size: int = 20
    max_pages: int = 1
    max_attempts: int = 1
    retry_delay_seconds: int = 1
    max_retry_wait_seconds: int = 30

    def validate(self):
        for key in ("project_id", "run_id", "provider", "adapter_version", "query", "config_event_id"):
            text(getattr(self, key), key)
        timestamp(self.created_at)
        for key, lower, upper in (("page_size", 1, 100), ("max_pages", 1, 100),
                                  ("max_attempts", 1, 3), ("retry_delay_seconds", 0, 30),
                                  ("max_retry_wait_seconds", 0, 60)):
            value = getattr(self, key)
            if type(value) is not int or not lower <= value <= upper:
                raise ContractError("invalid bounded discovery setting: " + key)
        if self.concept_id is not None:
            text(self.concept_id, "concept_id")

    @property
    def plan_id(self):
        return identifier("search", asdict(self))


@dataclass(frozen=True)
class RequestSpec:
    url: str
    method: str = "GET"


@dataclass(frozen=True)
class CandidateObservation:
    provider_record_id: str | None
    record: BibliographicRecord
    raw_record: dict
    identity_evidence: str = "provider_record"


@dataclass(frozen=True)
class DiscoveryPage:
    observations: tuple[CandidateObservation, ...]
    next_cursor: str | None = None
    reported_total: int | None = None
    provider_limit: bool = False


class DiscoveryProvider(Protocol):
    name: str
    version: str
    network: bool
    hosts: tuple[str, ...]

    def request(self, plan: SearchPlan, cursor: str | None) -> RequestSpec: ...
    def normalize(self, body: bytes, plan: SearchPlan, cursor: str | None) -> DiscoveryPage: ...


def record_from_dict(raw):
    from corpustrail.identity import Identifier
    record = BibliographicRecord(**{**raw, "authors": tuple(raw.get("authors", ())),
        "identifiers": tuple(Identifier(**x) for x in raw.get("identifiers", ()))})
    record.validate()
    return record
