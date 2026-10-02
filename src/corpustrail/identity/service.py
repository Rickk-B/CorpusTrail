"""Mint once from an explicit origin; exact aliases are separately approved."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import (
    ContractError, canonical, content_hash, identifier, sha256, text, timestamp,
)


@dataclass(frozen=True)
class Identifier:
    scheme: str
    value: str

    def normalized(self) -> tuple[str, str]:
        text(self.scheme, "identifier scheme")
        text(self.value, "identifier value")
        scheme = self.scheme.casefold()
        value = self.value.strip()
        if scheme == "doi":
            for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
                if value.casefold().startswith(prefix):
                    value = value[len(prefix):]
                    break
            value = value.strip().casefold()
            if not re.fullmatch(r"10\.\d{4,9}/\S+", value):
                raise ContractError("invalid exact DOI")
        elif scheme == "pmid":
            if not re.fullmatch(r"[0-9]+", value):
                raise ContractError("invalid PMID")
        elif scheme == "pmcid":
            value = value.upper()
            if not re.fullmatch(r"PMC[0-9]+", value):
                raise ContractError("invalid PMCID")
        elif scheme == "openalex":
            value = value.rsplit("/", 1)[-1].upper()
            if not re.fullmatch(r"W[0-9]+", value):
                raise ContractError("invalid OpenAlex work identifier")
        elif scheme == "semantic_scholar":
            value = value.casefold()
            if not re.fullmatch(r"[0-9a-f]{40}", value):
                raise ContractError("invalid Semantic Scholar paper identifier")
        elif not re.fullmatch(r"[a-z][a-z0-9_-]*\.[a-z0-9_.-]+", scheme):
            raise ContractError("opaque identifiers need a namespaced scheme")
        return scheme, value


@dataclass(frozen=True)
class BibliographicRecord:
    title: str | None = None
    abstract: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    source: str | None = None
    identifiers: tuple[Identifier, ...] = ()

    def validate(self) -> None:
        for key in ("title", "abstract", "source"):
            if getattr(self, key) is not None:
                text(getattr(self, key), key)
        if self.year is not None and (type(self.year) is not int or not 1 <= self.year <= 9999):
            raise ContractError("year must be a year or missing")
        if not isinstance(self.authors, tuple) or not isinstance(self.identifiers, tuple):
            raise ContractError("bibliographic collections must be immutable tuples")
        for author in self.authors:
            text(author, "author")
        normalized = [item.normalized() for item in self.identifiers]
        if len(normalized) != len(set(normalized)):
            raise ContractError("identifiers must not repeat")


@dataclass(frozen=True)
class SourceReference:
    source_uri: str
    record_locator: str
    source_sha256: str
    byte_size: int
    producer_id: str
    observed_at: str
    producer_type: str = "imported"
    media_type: str = "application/json"
    identity_status: str = "unverified"

    def validate(self) -> None:
        for key in ("source_uri", "record_locator", "producer_id", "media_type"):
            text(getattr(self, key), key)
        sha256(self.source_sha256)
        timestamp(self.observed_at)
        if type(self.byte_size) is not int or self.byte_size < 0:
            raise ContractError("source byte size must be nonnegative")
        if self.producer_type not in {"human", "deterministic", "parser", "imported"}:
            raise ContractError("this enrollment capability does not trust model-generated identity")
        if self.identity_status not in {"verified", "unverified"}:
            raise ContractError("invalid source identity status")


@dataclass(frozen=True)
class EnrollmentPlan:
    record: BibliographicRecord
    source: SourceReference
    paper_id: str
    action: str
    new_aliases: tuple[tuple[str, str], ...]
    state_sha256: str
    config_event_id: str

    def to_dict(self) -> dict:
        return json.loads(canonical(asdict(self)))

    @property
    def plan_id(self) -> str:
        return identifier("enroll", self.to_dict())


def _from_plan(raw):
    record = raw["record"]
    return EnrollmentPlan(
        BibliographicRecord(**{**record, "authors": tuple(record["authors"]),
                               "identifiers": tuple(Identifier(**x) for x in record["identifiers"])}),
        SourceReference(**raw["source"]), raw["paper_id"], raw["action"],
        tuple(tuple(x) for x in raw["new_aliases"]), raw["state_sha256"], raw["config_event_id"])


def _identity_snapshot(db):
    return content_hash({table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
                         for table in ("paper_entities", "paper_identifiers", "ct_source_bindings")})


class IdentityService:
    def __init__(self, project):
        self.project = project

    def _plan(self, db, record, source) -> EnrollmentPlan:
        record.validate()
        source.validate()
        request = json.loads(canonical({"record": asdict(record), "source": asdict(source)}))
        # Exact replay retains the previous receipt, even after unrelated enrollments.
        for row in db.execute("SELECT payload_json FROM ct_enrollment_operations ORDER BY plan_id"):
            raw = json.loads(row[0])
            if all(raw[key] == request[key] for key in request):
                return _from_plan(raw)
        binding = db.execute("SELECT paper_id FROM ct_source_bindings WHERE source_uri=? AND record_locator=?",
                             (source.source_uri, source.record_locator)).fetchone()
        owners = {binding[0]} if binding else set()
        new_aliases = []
        for scheme, value in sorted(item.normalized() for item in record.identifiers):
            row = db.execute("SELECT paper_id FROM paper_identifiers WHERE scheme=? AND normalized_value=? "
                             "AND status='verified'", (scheme, value)).fetchone()
            if row:
                if source.identity_status != "verified" and binding is None:
                    raise ContractError("unverified identity evidence requires explicit review")
                owners.add(row[0])
            elif source.identity_status == "verified":
                new_aliases.append((scheme, value))
        if len(owners) > 1:
            raise ContractError("exact identifiers/origin disagree; manual identity review required")
        config_id, config = latest_config(db)
        paper_id = next(iter(owners)) if owners else identifier("ct-paper", {
            "project_id": config["project_id"], "origin": source.source_uri,
            "record_locator": source.record_locator})
        return EnrollmentPlan(record, source, paper_id, "attach" if owners else "create",
                              tuple(new_aliases), _identity_snapshot(db), config_id)

    def plan(self, record: BibliographicRecord, source: SourceReference) -> EnrollmentPlan:
        with connection(self.project.database_path) as db:
            return self._plan(db, record, source)

    def apply(self, plan: EnrollmentPlan, *, approve_new_identity: bool = False,
              approve_aliases: bool = False) -> str:
        """Explicit operational enrollment; never a corpus inclusion decision."""
        with connection(self.project.database_path, write=True) as db:
            existing = db.execute("SELECT payload_json FROM ct_enrollment_operations WHERE plan_id=?",
                                  (plan.plan_id,)).fetchone()
            if existing:
                if existing[0] != canonical(plan.to_dict()):
                    raise ContractError("enrollment receipt differs")
                return plan.paper_id
            if self._plan(db, plan.record, plan.source) != plan:
                raise ContractError("stale or altered enrollment plan")
            if plan.action == "create" and approve_new_identity is not True:
                raise ContractError("new identity needs explicit approval")
            if plan.new_aliases and approve_aliases is not True:
                raise ContractError("new exact aliases need explicit source approval")
            source = plan.source
            prior = db.execute("SELECT media_type,byte_size FROM raw_artifacts WHERE sha256=?",
                               (source.source_sha256,)).fetchone()
            if prior and tuple(prior) != (source.media_type, source.byte_size):
                raise ContractError("source hash has incompatible artifact metadata")
            db.execute("INSERT OR IGNORE INTO raw_artifacts VALUES (?,?,?,?)",
                       (source.source_sha256, source.media_type, source.byte_size, source.observed_at))
            if plan.action == "create":
                db.execute("INSERT INTO paper_entities VALUES (?,?,?,'active',NULL)",
                           (plan.paper_id, source.observed_at, source.producer_id))
            db.execute("INSERT INTO ct_enrollment_operations VALUES (?,?,?,?)",
                       (plan.plan_id, plan.paper_id, canonical(plan.to_dict()), plan.config_event_id))
            db.execute("INSERT OR IGNORE INTO ct_source_bindings VALUES (?,?,?,?)",
                       (source.source_uri, source.record_locator, plan.paper_id, plan.plan_id))
            db.execute("INSERT INTO ct_paper_observations VALUES (?,?,?,?,?)",
                       (identifier("bibliography", plan.to_dict()), plan.paper_id, plan.plan_id,
                        source.source_sha256, canonical({"record": asdict(plan.record), "source": asdict(source)})))
            for item in plan.record.identifiers:
                scheme, value = item.normalized()
                assertion_id = identifier("id-assertion", {"plan": plan.plan_id, "scheme": scheme, "value": value})
                db.execute("INSERT INTO identifier_assertions VALUES (?,?,?,?,?,?,?,?)",
                           (assertion_id, scheme, item.value, value, source.producer_id,
                            source.record_locator, source.source_sha256, source.observed_at))
                if (scheme, value) in plan.new_aliases:
                    db.execute("INSERT INTO paper_identifiers VALUES (?,?,?,?,'verified',?,?,?,?)",
                               (identifier("alias", [plan.paper_id, scheme, value]), plan.paper_id, scheme, value,
                                "explicit_source_approval/v1", assertion_id, source.observed_at, source.observed_at))
        return plan.paper_id

    def papers(self) -> list[str]:
        with connection(self.project.database_path) as db:
            return [row[0] for row in db.execute("SELECT paper_id FROM paper_entities ORDER BY paper_id")]

    def observations(self, paper_id: str) -> list[dict]:
        with connection(self.project.database_path) as db:
            return self._observations(db, paper_id)

    @staticmethod
    def _observations(db, paper_id):
        if db.execute("SELECT 1 FROM paper_entities WHERE paper_id=?", (paper_id,)).fetchone() is None:
            raise KeyError(paper_id)
        return [{"observation_id": row[0], **json.loads(row[1])} for row in db.execute(
            "SELECT observation_id,payload_json FROM ct_paper_observations WHERE paper_id=? "
            "ORDER BY observation_id", (paper_id,))]

    def exact_owner(self, item: Identifier) -> str | None:
        with connection(self.project.database_path) as db:
            row = db.execute("SELECT paper_id FROM paper_identifiers WHERE scheme=? AND normalized_value=? "
                             "AND status='verified'", item.normalized()).fetchone()
            return row[0] if row else None
