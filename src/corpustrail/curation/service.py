"""Immutable generic reviews; only explicit human authority projects membership."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, identifier, sha256, text, timestamp, now
from corpustrail.project.config import ProjectConfig


_STATE_SUFFICIENCY = {"included": "sufficient", "excluded": "sufficient",
                      "insufficient_evidence": "insufficient", "unresolved": "undetermined"}
_PRODUCER_TYPES = {"human", "model", "deterministic", "parser", "imported"}
_AUTHORITY_STATES = {"non_authoritative", "human_authorized"}

@dataclass(frozen=True)
class EvidenceBasis:
    representation: str
    source_sha256: str
    source_uri: str
    location: str | None = None
    artifact_validity: str = "unknown"

    def validate(self) -> None:
        if self.representation not in {"metadata", "abstract", "structured_text", "full_text",
                                       "ocr", "external_document", "unknown"}:
            raise ContractError("invalid evidence representation")
        if self.artifact_validity not in {"verified", "unverified", "pending_identity", "wrong_document", "unknown"}:
            raise ContractError("invalid artifact validity")
        sha256(self.source_sha256)
        text(self.source_uri, "evidence source")
        if self.location is not None:
            text(self.location, "evidence location")


@dataclass(frozen=True)
class ReviewEvent:
    paper_id: str
    state: str
    sufficiency: str
    review_extent: str
    rationale: str
    producer_id: str
    created_at: str
    evidence: tuple[EvidenceBasis, ...]
    policy_id: str = "broad-corpus/v1"
    producer_type: str = "human"
    authority_state: str = "non_authoritative"
    supersedes: str | None = None
    schema_version: str = "corpustrail-broad-corpus-review/v1"

    def validate(self) -> None:
        if self.schema_version != "corpustrail-broad-corpus-review/v1":
            raise ContractError("unsupported review contract")
        for key in ("paper_id", "rationale", "producer_id", "policy_id"):
            text(getattr(self, key), key)
        timestamp(self.created_at)
        if self.supersedes is not None:
            text(self.supersedes, "supersession identifier")
        required = _STATE_SUFFICIENCY
        if self.state not in required or self.sufficiency != required[self.state]:
            raise ContractError("decision and sufficiency disagree; insufficient is not exclusion")
        if self.review_extent not in {"metadata", "abstract", "sections", "full_document", "none"}:
            raise ContractError("invalid review extent")
        if self.producer_type not in _PRODUCER_TYPES:
            raise ContractError("invalid producer type")
        if self.authority_state not in _AUTHORITY_STATES:
            raise ContractError("invalid authority state")
        if self.authority_state == "human_authorized" and self.producer_type != "human":
            raise ContractError("producer is not human authority")
        if not isinstance(self.evidence, tuple):
            raise ContractError("evidence must be an immutable tuple")
        for basis in self.evidence:
            basis.validate()
        if self.sufficiency == "sufficient":
            if not self.evidence or self.review_extent == "none":
                raise ContractError("completed decisions need an evidence basis and review extent")
            if any(x.artifact_validity != "verified" for x in self.evidence):
                raise ContractError("pending/unverified/wrong documents cannot support completed decisions")
            representations = {x.representation for x in self.evidence}
            if self.review_extent == "abstract" and not representations & {"abstract", "structured_text", "full_text", "ocr", "external_document"}:
                raise ContractError("abstract review needs available abstract/document evidence")
            if self.review_extent in {"sections", "full_document"} and not representations & {
                    "structured_text", "full_text", "ocr", "external_document"}:
                raise ContractError("paper review extent needs verified document evidence")

    def to_dict(self) -> dict:
        self.validate()
        return json.loads(canonical(asdict(self)))

    @property
    def event_id(self) -> str:
        return identifier("review", self.to_dict())


@dataclass(frozen=True)
class ReviewPlan:
    event: ReviewEvent
    history_sha256: str
    config_event_id: str


def _history(db, paper_id):
    result = []
    for row in db.execute("SELECT * FROM ct_review_events WHERE paper_id=? ORDER BY sequence", (paper_id,)):
        payload = json.loads(row["payload_json"])
        if identifier("review", payload) != row["event_id"] or content_hash(payload) != row["content_sha256"]:
            raise ContractError("immutable review-event hash mismatch")
        for column, key in (("paper_id", "paper_id"), ("membership_state", "state"),
                            ("producer_type", "producer_type"), ("authority_state", "authority_state"),
                            ("supersedes", "supersedes")):
            if row[column] != payload[key]:
                raise ContractError("review provenance columns disagree with immutable payload")
        result.append({"event_id": row["event_id"], **payload})
    return result


def membership_in_connection(db, paper_id):
    history = _history(db, paper_id)
    authority = [event for event in history if event["authority_state"] == "human_authorized"]
    current = authority[-1] if authority else None
    return {"schema_version": "corpustrail-corpus/v2", "paper_id": paper_id,
            "state": current["state"] if current else "not_reviewed",
            "reviewed": bool(history), "current_event_id": current["event_id"] if current else None,
            "authority_state": "human_authorized" if current else "none",
            "decision_provenance": current}


class ReviewService:
    def __init__(self, project):
        self.project = project

    def plan(self, event: ReviewEvent) -> ReviewPlan:
        event.validate()
        with connection(self.project.database_path) as db:
            if db.execute("SELECT 1 FROM ct_review_events WHERE event_id=?", (event.event_id,)).fetchone() is None:
                self._validate(db, event)
            config_id, _ = latest_config(db)
            return ReviewPlan(event, content_hash(_history(db, event.paper_id)), config_id)

    @staticmethod
    def _validate(db, event):
        event.validate()
        if db.execute("SELECT 1 FROM paper_entities WHERE paper_id=?", (event.paper_id,)).fetchone() is None:
            raise ContractError("review subject is not an enrolled canonical paper")
        _, config_raw = latest_config(db)
        config = ProjectConfig.from_dict(config_raw)
        if event.policy_id != config.review.policy_id:
            raise ContractError("review policy differs from project policy")
        if event.authority_state == "human_authorized":
            if event.producer_id not in config.review.authorized_reviewers:
                raise ContractError("reviewer has not been explicitly authorized by project policy")
            current = membership_in_connection(db, event.paper_id)
            if event.supersedes != current["current_event_id"]:
                raise ContractError("a changed human judgment needs explicit current-event supersession")
        if event.supersedes is not None:
            prior = db.execute("SELECT paper_id,authority_state FROM ct_review_events WHERE event_id=?",
                               (event.supersedes,)).fetchone()
            if prior is None or prior["paper_id"] != event.paper_id:
                raise ContractError("supersession must name an existing same-paper event")
            if prior["authority_state"] == "human_authorized" and event.authority_state != "human_authorized":
                raise ContractError("non-authoritative observations cannot supersede human authority")
        for basis in event.evidence:
            if db.execute("SELECT 1 FROM raw_artifacts WHERE sha256=?", (basis.source_sha256,)).fetchone() is None:
                raise ContractError("evidence hash must reference an enrolled source artifact")
            if basis.representation in {"metadata", "abstract"}:
                observations = [json.loads(row[0]) for row in db.execute(
                    "SELECT payload_json FROM ct_paper_observations WHERE paper_id=? AND source_sha256=?",
                    (event.paper_id, basis.source_sha256))]
                matching = [x for x in observations if x["source"]["source_uri"] == basis.source_uri]
                available = bool(matching) and (basis.representation == "metadata" or any(x["record"]["abstract"] for x in matching))
                if not available and basis.representation == "abstract":
                    representations = [json.loads(row[0])["payload"] for row in db.execute(
                        "SELECT payload_json FROM ct_pipeline_events WHERE kind='representation' AND paper_id=? AND source_sha256=?",
                        (event.paper_id, basis.source_sha256))]
                    available = any(x["representation"] == "abstract" and x["trusted"] and x["source_uri"] == basis.source_uri
                                    for x in representations)
                if not available:
                    raise ContractError("requested metadata/abstract evidence is not available for this paper")
            elif event.sufficiency == "sufficient" and basis.representation in {"structured_text", "full_text", "ocr", "external_document"}:
                representations = [json.loads(row[0])["payload"] for row in db.execute(
                    "SELECT payload_json FROM ct_pipeline_events WHERE kind='representation' AND paper_id=? AND source_sha256=?",
                    (event.paper_id, basis.source_sha256))]
                valid = [x for x in representations if x["trusted"] and x["artifact_validity"] == "verified"
                         and x["source_uri"] == basis.source_uri]
                if basis.representation in {"structured_text", "full_text"}:
                    valid = [x for x in valid if x.get("evidence_depth") == "document_body"]
                if not valid:
                    raise ContractError("document evidence is not verified and available for this paper")

    def apply(self, plan: ReviewPlan, *, recorded_at: str | None = None) -> str:
        with connection(self.project.database_path, write=True) as db:
            return self._apply(db, plan, recorded_at or now())

    def _apply(self, db, plan, recorded_at):
        """Shared transaction path for explicit session commits; never draft saves."""
        from datetime import datetime
        timestamp(recorded_at)
        event = plan.event
        event.validate()
        existing = db.execute("SELECT payload_json FROM ct_review_events WHERE event_id=?", (event.event_id,)).fetchone()
        if existing:
            if existing[0] != canonical(event.to_dict()):
                raise ContractError("review receipt differs")
            return event.event_id
        if datetime.fromisoformat(event.created_at.replace('Z', '+00:00')) > datetime.fromisoformat(recorded_at.replace('Z', '+00:00')):
            raise ContractError("record availability cannot predate the judgment")
        config_id, _ = latest_config(db)
        if config_id != plan.config_event_id or content_hash(_history(db, event.paper_id)) != plan.history_sha256:
            raise ContractError("stale review plan")
        self._validate(db, event)
        db.execute("INSERT INTO ct_review_events "
                   "(event_id,paper_id,membership_state,producer_type,authority_state,supersedes,"
                   "payload_json,content_sha256,config_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
                   (event.event_id, event.paper_id, event.state, event.producer_type, event.authority_state,
                    event.supersedes, canonical(event.to_dict()), content_hash(event.to_dict()), config_id))
        db.execute("INSERT INTO ct_review_availability VALUES (?,?)", (event.event_id, recorded_at))
        return event.event_id

    def membership(self, paper_id: str) -> dict:
        with connection(self.project.database_path) as db:
            if db.execute("SELECT 1 FROM paper_entities WHERE paper_id=?", (paper_id,)).fetchone() is None:
                raise KeyError(paper_id)
            return membership_in_connection(db, paper_id)

    def history(self, paper_id: str) -> list[dict]:
        with connection(self.project.database_path) as db:
            return _history(db, paper_id)

    def corpus(self, *, states=None) -> list[dict]:
        """Read-only broad-membership projection; ranking is not consulted."""
        if states is not None and set(states) - {*_STATE_SUFFICIENCY, 'not_reviewed'}:
            raise ContractError("invalid membership filter")
        with connection(self.project.database_path) as db:
            result = [membership_in_connection(db, row[0]) for row in
                      db.execute("SELECT paper_id FROM paper_entities ORDER BY paper_id")]
        return [x for x in result if states is None or x['state'] in states]
