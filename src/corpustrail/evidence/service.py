"""Evidence acquisition and identity are independent of corpus membership."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol

from corpustrail._internal.pipeline import append, artifact, events, preserve
from corpustrail._internal.values import ContractError, identifier, now, text, timestamp
from corpustrail.identity import Identifier
from corpustrail._internal.xml_safety import parse_xml, XmlPolicyError


@dataclass(frozen=True)
class ResolutionRequest:
    project_id: str
    paper_id: str
    resolvers: tuple[str, ...]
    config_event_id: str
    created_at: str
    identifiers: tuple[tuple[str, str], ...]
    max_attempts: int = 1
    max_retry_wait_seconds: int = 30

    @property
    def request_id(self):
        return identifier("resolution", asdict(self))


class EvidenceResolver(Protocol):
    name: str
    version: str
    network: bool
    hosts: tuple[str, ...]

    def request(self, request: ResolutionRequest): ...
    def representation(self, response) -> dict: ...


class EuropePmcResolver:
    name = "europepmc"
    version = "jats/v1"
    network = True
    hosts = ("www.ebi.ac.uk",)

    def request(self, request):
        pmcid = dict(request.identifiers).get("pmcid")
        if not pmcid:
            return None
        from corpustrail.discovery.contracts import RequestSpec
        return RequestSpec("https://www.ebi.ac.uk/europepmc/webservices/rest/" + pmcid + "/fullTextXML")

    def representation(self, response):
        return {"representation": "jats_xml", "media_type": "application/xml",
                "legitimate_basis": "europepmc_open_access_api", "version_kind": "unknown"}


def _front_elements(root, name):
    return [node for front in root if front.tag.rsplit("}", 1)[-1] == "front"
            for meta in front if meta.tag.rsplit("}", 1)[-1] == "article-meta"
            for node in meta if node.tag.rsplit("}", 1)[-1] == name]


def _document_ids(body):
    try:
        root = parse_xml(body)
    except XmlPolicyError as exc:
        raise ContractError(str(exc)) from exc
    if root.tag.rsplit("}", 1)[-1] != "article":
        raise ContractError("structured source is not an article")
    values = []
    # Only article front matter, never IDs of cited references.
    for node in _front_elements(root, "article-id"):
        scheme = {"doi": "doi", "pmid": "pmid", "pmc": "pmcid", "pmcid": "pmcid"}.get(node.get("pub-id-type"))
        if scheme and node.text:
            raw = node.text.strip()
            if scheme == "pmcid" and raw.isdigit():
                raw = "PMC" + raw
            values.append(Identifier(scheme, raw).normalized())
    return tuple(values)


class EvidenceService:
    def __init__(self, project):
        self.project = project

    def plan(self, paper_id, *, created_at=None):
        metadata = self.project.discovery.metadata(paper_id)
        policy = self.project.config.evidence
        return ResolutionRequest(self.project.config.project_id, paper_id, policy.resolvers,
            self.project.configuration_history()[-1]["event_id"], created_at or now(),
            tuple((x["scheme"], x["value"]) for x in metadata["identifiers"]),
            policy.max_attempts, policy.max_retry_wait_seconds)

    def _validate(self, request):
        timestamp(request.created_at)
        if request != self.plan(request.paper_id, created_at=request.created_at):
            raise ContractError("stale or altered resolution request")

    def acquire(self, request, *, resolvers=None, transport=None, confirm_external=False, clock=now, sleeper=None):
        from corpustrail.providers.network import UrlLibTransport, outcome, rate_headers, retry_after, safe_url, sleep
        self._validate(request)
        supplied = resolvers if resolvers is not None else {"europepmc": EuropePmcResolver()}
        if any(name not in supplied for name in request.resolvers):
            raise ContractError("configured resolver unavailable; no provider substitution")
        if any(supplied[name].name != name for name in request.resolvers):
            raise ContractError("resolver registration differs")
        transport = transport or UrlLibTransport()
        if request.resolvers and (transport.network or any(supplied[x].network for x in request.resolvers)) and confirm_external is not True:
            raise ContractError("external evidence transfer requires confirmation")
        prior = events(self.project, scope_id=request.request_id, kind="acquisition_result")
        if prior:
            # Exact completed request is idempotent; failed requests are not silently re-run.
            if prior[-1]["payload"].get("run_complete"):
                return self.status(request.paper_id)
            raise ContractError("interrupted acquisition requires inspection")
        if events(self.project, scope_id=request.request_id, kind="acquisition_started"):
            raise ContractError("interrupted acquisition requires inspection")
        append(self.project, "resolution_plan", request.request_id, asdict(request), paper_id=request.paper_id,
               config_event_id=request.config_event_id)
        for name in request.resolvers:
            resolver = supplied[name]
            spec = resolver.request(request)
            if spec is None:
                append(self.project, "acquisition_result", request.request_id, {"resolver": name,
                    "outcome": "not_applicable", "timestamp": clock()}, paper_id=request.paper_id,
                    config_event_id=request.config_event_id)
                continue
            safe_url(spec.url, resolver.hosts)
            for attempt in range(1, request.max_attempts + 1):
                at = clock()
                append(self.project, "acquisition_started", request.request_id, {"resolver": name,
                    "version": resolver.version, "request": asdict(spec), "attempt": attempt, "timestamp": at},
                    paper_id=request.paper_id, config_event_id=request.config_event_id, exclusive=True)
                sha, status, delay, response = None, None, None, None
                try:
                    response = transport.request(spec.url, method=spec.method, headers={"Accept": "application/xml"}, body=None)
                    safe_url(response.final_url, resolver.hosts)
                    status, delay = outcome(response.status), retry_after(response.headers, clock=datetime.fromisoformat(at))
                    sha = preserve(self.project, response.body, "application/xml", at)
                    error = None
                except Exception as exc:
                    status = "permanent_error" if isinstance(exc, ContractError) else "retryable_error"
                    error = type(exc).__name__
                wait = delay if delay is not None else 1
                retry = status == "retryable_error" and attempt < request.max_attempts and wait <= request.max_retry_wait_seconds
                append(self.project, "acquisition_result", request.request_id, {"resolver": name,
                    "version": resolver.version, "request": asdict(spec), "attempt": attempt, "timestamp": at,
                    "outcome": status, "http_status": response.status if response else None, "error": error,
                    "rate_limit": rate_headers(response.headers) if response else {},
                    "retry_after_seconds": delay, "will_retry": retry, "retry_blocked": wait > request.max_retry_wait_seconds},
                    paper_id=request.paper_id, source_sha256=sha, config_event_id=request.config_event_id)
                if status == "success":
                    declaration = resolver.representation(response)
                    self.preserve_document(request.paper_id, response.body, source_uri=spec.url,
                        resolver=name, resolver_version=resolver.version, created_at=at,
                        resolution_id=request.request_id, **declaration)
                if not retry:
                    break
                (sleeper or sleep)(wait)
        append(self.project, "acquisition_result", request.request_id, {"run_complete": True, "timestamp": clock()},
               paper_id=request.paper_id, config_event_id=request.config_event_id)
        return self.status(request.paper_id)

    def preserve_document(self, paper_id, body, *, representation, media_type, source_uri,
                          legitimate_basis, resolver, resolver_version, created_at=None,
                          version_kind="unknown", resolution_id=None):
        """Explicit legitimate-source import; PDFs never auto-verify from title similarity."""
        metadata = self.project.discovery.metadata(paper_id)
        created_at = created_at or now()
        for key, value in (("source_uri", source_uri), ("legitimate_basis", legitimate_basis),
                           ("resolver", resolver), ("resolver_version", resolver_version)):
            text(value, key)
        if representation not in {"jats_xml", "publisher_xml", "bioc_json", "pdf", "ocr_text", "external_document"}:
            raise ContractError("unsupported document representation")
        sha = preserve(self.project, body, media_type, created_at)
        known = {(x["scheme"], x["value"]) for x in metadata["identifiers"]}
        validity, exact, error = "pending_identity", (), None
        if representation in {"jats_xml", "publisher_xml"}:
            try:
                exact = _document_ids(body)
                if any(s in {key for key, _ in known} and (s, v) not in known for s, v in exact):
                    validity = "mismatch"
                elif known.intersection(exact):
                    validity = "verified"
            except ContractError as exc:
                validity, error = "invalid", type(exc).__name__
        payload = {"paper_id": paper_id, "representation": representation, "artifact_sha256": sha,
            "media_type": media_type, "source_uri": source_uri, "legitimate_basis": legitimate_basis,
            "resolver": resolver, "resolver_version": resolver_version, "created_at": created_at,
            "version_kind": version_kind, "resolution_id": resolution_id,
            "artifact_validity": validity, "identity_identifiers": exact, "error": error,
            "trusted": validity == "verified", "authority": "non_authoritative"}
        rep_id = append(self.project, "representation", paper_id, payload, paper_id=paper_id, source_sha256=sha)
        if validity == "verified" and representation in {"jats_xml", "publisher_xml"}:
            from .native_parsers import NativeJatsParser, NativePublisherXmlParser
            from .parsing import ParsingError
            try:
                root = parse_xml(body)
                abstracts = _front_elements(root, "abstract")
                abstract = "\n\n".join(" ".join("".join(x.itertext()).split()) for x in abstracts).strip()
                if abstract:
                    abstract_sha = preserve(self.project, abstract.encode("utf-8"), "text/plain", created_at)
                    append(self.project, "representation", paper_id, {**payload, "representation": "abstract",
                        "artifact_sha256": abstract_sha, "media_type": "text/plain", "derived_from": rep_id,
                        "parser": "native_jats_abstract", "parser_version": "v1", "evidence_depth": "abstract"},
                        paper_id=paper_id, source_sha256=abstract_sha)
                parser = NativeJatsParser() if representation == "jats_xml" else NativePublisherXmlParser()
                parsed = parser.parse(artifact(self.project, sha))
                text_sha = preserve(self.project, parsed.body.encode("utf-8"), "text/plain", created_at)
                depth = "document_body" if any("".join(node.itertext()).strip() for node in root
                    if node.tag.rsplit("}", 1)[-1] == "body") else "front_matter_only"
                append(self.project, "representation", paper_id, {**payload, "representation": "structured_text",
                    "artifact_sha256": text_sha, "media_type": "text/plain", "derived_from": rep_id,
                    "parser": parser.name, "parser_version": parser.version, "quality": parsed.quality,
                    "evidence_depth": depth},
                    paper_id=paper_id, source_sha256=text_sha)
            except (ParsingError, XmlPolicyError) as exc:
                append(self.project, "acquisition_result", resolution_id or rep_id, {
                    "outcome": "parsing_failed", "error": type(exc).__name__, "representation_id": rep_id}, paper_id=paper_id)
        return rep_id

    def representations(self, paper_id, *, trusted_only=False):
        self.project.discovery.metadata(paper_id)  # Reject unknown identity without initializing anything.
        rows = events(self.project, kind="representation", paper_id=paper_id)
        return [x for x in rows if not trusted_only or x["payload"]["trusted"]]

    def status(self, paper_id):
        metadata = self.project.discovery.metadata(paper_id)
        reps = self.representations(paper_id)
        return self._status(metadata, reps)

    @staticmethod
    def _status(metadata, reps):
        """Shared pure status projection for existing services and snapshot reads."""
        paper_id = metadata['paper_id']
        readable = [x for x in reps if x["payload"]["trusted"] and x["payload"]["representation"] == "structured_text"
                    and x["payload"].get("evidence_depth") == "document_body"]
        return {"paper_id": paper_id, "best_available": "structured_text" if readable else (
            "abstract" if metadata["fields"]["abstract"] else "metadata"),
            "abstract_available": bool(metadata["fields"]["abstract"]),
            "verified_structured_text": len(readable), "representations": len(reps),
            "pending_identity": sum(x["payload"]["artifact_validity"] == "pending_identity" for x in reps),
            "mismatch_or_invalid": sum(x["payload"]["artifact_validity"] in {"mismatch", "invalid"} for x in reps),
            "membership_implication": None}
