"""Versioned topic-independent project configuration (experimental)."""

from __future__ import annotations

import re
import os
from dataclasses import asdict, dataclass, field

from corpustrail._internal.values import ContractError, canonical, relative_path, text


CONFIG_SCHEMA = "corpustrail-workspace/v2"


@dataclass(frozen=True)
class SearchConcept:
    concept_id: str
    label: str
    language: str = "en"
    aliases: tuple[str, ...] = ()

    def validate(self) -> None:
        for key in ("concept_id", "label", "language"):
            text(getattr(self, key), key)
        if not isinstance(self.aliases, tuple):
            raise ContractError("search aliases must be immutable tuples")
        for alias in self.aliases:
            text(alias, "search alias")


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    adapter: str
    credential_env: str | None = None

    def validate(self) -> None:
        text(self.provider_id, "provider_id")
        text(self.adapter, "adapter")
        if self.adapter in {'openalex', 'crossref', 'europepmc', 'semantic_scholar'} and self.provider_id != self.adapter:
            raise ContractError('built-in provider_id must equal its adapter name')
        if self.credential_env is not None and self.adapter in {'crossref', 'europepmc'}:
            raise ContractError(f'{self.adapter} does not support credential headers; omit credential_env')
        if self.credential_env is not None and not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", self.credential_env):
            raise ContractError("credential_env names an environment variable, not a secret")


@dataclass(frozen=True)
class ReviewPolicy:
    policy_id: str = "broad-corpus/v1"
    authorized_reviewers: tuple[str, ...] = ()
    scope: str | None = None

    def validate(self) -> None:
        text(self.policy_id, "review policy")
        if not isinstance(self.authorized_reviewers, tuple):
            raise ContractError("reviewer identifiers must be an immutable tuple")
        for reviewer in self.authorized_reviewers:
            text(reviewer, "reviewer identifier")
        if len(set(self.authorized_reviewers)) != len(self.authorized_reviewers):
            raise ContractError("reviewer identifiers must not repeat")
        if self.scope is not None:
            text(self.scope, "scope")


@dataclass(frozen=True)
class ConceptExtension:
    namespace: str
    version: str
    predicates: tuple[str, ...] = ()

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.namespace) or self.namespace == "ct":
            raise ContractError("extensions need a project namespace; ct is reserved")
        text(self.version, "vocabulary version")
        if not isinstance(self.predicates, tuple):
            raise ContractError("extension predicates must be an immutable tuple")
        for predicate in self.predicates:
            if not predicate.startswith(self.namespace + "."):
                raise ContractError("extension predicates must retain their namespace")
            text(predicate, "predicate")


@dataclass(frozen=True)
class EvidencePolicy:
    resolvers: tuple[str, ...] = ()
    max_attempts: int = 1
    max_retry_wait_seconds: int = 30

    def validate(self):
        if not isinstance(self.resolvers, tuple) or len(set(self.resolvers)) != len(self.resolvers):
            raise ContractError("resolvers must be a unique immutable ordered tuple")
        for name in self.resolvers:
            text(name, "resolver")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 3:
            raise ContractError("evidence retries bounded to at most three attempts")
        if type(self.max_retry_wait_seconds) is not int or not 0 <= self.max_retry_wait_seconds <= 60:
            raise ContractError("evidence retry wait bounded to sixty seconds")


@dataclass(frozen=True)
class ProjectConfig:
    project_id: str
    name: str
    description: str
    data_directory: str = "data"
    database: str = "data/operations.sqlite3"
    schema_version: str = CONFIG_SCHEMA
    config_version: int = 1
    search: tuple[SearchConcept, ...] = ()
    providers: tuple[ProviderConfig, ...] = ()
    review: ReviewPolicy = field(default_factory=ReviewPolicy)
    concept_extensions: tuple[ConceptExtension, ...] = ()
    evidence: EvidencePolicy = field(default_factory=EvidencePolicy)
    models: tuple = ()

    def validate(self) -> None:
        if self.schema_version != CONFIG_SCHEMA:
            raise ContractError("unsupported project configuration version")
        for key in ("project_id", "name", "description"):
            text(getattr(self, key), key)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.project_id):
            raise ContractError("project_id must be a stable machine identifier")
        if type(self.config_version) is not int or self.config_version < 1:
            raise ContractError("config_version must be a positive integer")
        relative_path(self.data_directory)
        relative_path(self.database)
        if not self.database.startswith(self.data_directory + "/"):
            raise ContractError("database must reside inside data_directory")
        for values, expected in ((self.search, SearchConcept), (self.providers, ProviderConfig),
                                 (self.concept_extensions, ConceptExtension)):
            if not isinstance(values, tuple) or any(not isinstance(x, expected) for x in values):
                raise ContractError("configuration collections must be typed immutable tuples")
            for value in values:
                value.validate()
        if not isinstance(self.review, ReviewPolicy):
            raise ContractError("review must be a ReviewPolicy")
        self.review.validate()
        if not isinstance(self.evidence, EvidencePolicy):
            raise ContractError("evidence must be an EvidencePolicy")
        self.evidence.validate()
        from corpustrail.models.contracts import ModelConfig, safe_data
        if not isinstance(self.models, tuple) or any(not isinstance(x, ModelConfig) for x in self.models):
            raise ContractError('models must be an immutable tuple of ModelConfig')
        for model in self.models:
            model.validate()
        safe_data([asdict(model) for model in self.models], secrets=tuple(
            os.environ.get(c.credential_env, '') for c in (*self.providers, *self.models) if c.credential_env))
        if len({x.workflow_id for x in self.models}) != len(self.models):
            raise ContractError('model workflow IDs must not repeat')
        for values, key in ((self.search, "concept_id"), (self.providers, "provider_id"),
                            (self.concept_extensions, "namespace")):
            if len({getattr(x, key) for x in values}) != len(values):
                raise ContractError(f"{key} must not repeat")

    def to_dict(self) -> dict:
        self.validate()
        # JSON round-trip also gives consumers independent lists, not live tuples.
        import json
        return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, value: dict) -> ProjectConfig:
        try:
            raw = dict(value)
            raw["search"] = tuple(SearchConcept(**{**x, "aliases": tuple(x.get("aliases", ()))})
                                  for x in raw.get("search", ()))
            raw["providers"] = tuple(ProviderConfig(**x) for x in raw.get("providers", ()))
            from corpustrail.models.contracts import ModelConfig
            raw['models'] = tuple(ModelConfig(**x) for x in raw.get('models', ()))
            evidence = raw.get("evidence", {})
            raw["evidence"] = EvidencePolicy(**{**evidence, "resolvers": tuple(evidence.get("resolvers", ()))})
            review = raw.get("review", {})
            raw["review"] = ReviewPolicy(**{**review, "authorized_reviewers":
                                              tuple(review.get("authorized_reviewers", ()))})
            raw["concept_extensions"] = tuple(ConceptExtension(
                **{**x, "predicates": tuple(x.get("predicates", ()))})
                for x in raw.get("concept_extensions", ()))
            result = cls(**raw)
            result.validate()
            return result
        except (TypeError, KeyError, AttributeError) as exc:
            raise ContractError("invalid configuration shape or unsupported field") from exc
