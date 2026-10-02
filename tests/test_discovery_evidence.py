"""Offline discovery → exact identity → legitimate representations, without labels."""

import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from corpustrail._internal.database import connection, create_database, migrations
from corpustrail._internal.pipeline import append, artifact, events
from corpustrail._internal.values import ContractError, canonical, digest_bytes
from corpustrail.cli import main
from corpustrail.evidence import EuropePmcResolver
from corpustrail.identity import Identifier
from corpustrail.project import EvidencePolicy, Project, ProjectConfig, ProviderConfig, SearchConcept
from corpustrail.providers.metadata import MetadataProvider, _abstract_from_index
from corpustrail.providers.network import HttpResponse, ProviderTransportError, retry_after


AT = "2026-01-01T00:00:00+00:00"
OA = {"results": [{"id": "https://openalex.org/W123", "doi": "https://doi.org/10.1234/materials.1",
    "title": "Synthetic porous ceramic", "publication_year": 2020,
    "abstract_inverted_index": {"Porosity": [0], "was": [1], "measured.": [2]},
    "authorships": [{"author": {"display_name": "Example Researcher"}}],
    "primary_location": {"source": {"display_name": "Fixture Journal"}}, "ids": {"pmcid": "PMC123"}},
    {"id": "https://openalex.org/W124", "title": "Synthetic glass without an abstract"}],
    "meta": {"count": 2, "next_cursor": None}}
CR = {"message": {"items": [{"DOI": "10.1234/materials.1", "title": ["Conflicting provider title"],
    "published": {"date-parts": [[2021]]}, "author": [{"given": "Example", "family": "Researcher"}],
    "container-title": ["Fixture Journal"]}], "total-results": 1}}
JATS = b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/materials.1</article-id><article-id pub-id-type="pmc">PMC123</article-id><title-group><article-title>Synthetic porous ceramic</article-title></title-group></article-meta></front><body><sec><title>Methods</title><p>Porosity was measured using a synthetic fixture instrument.</p></sec></body></article>'


class RecordedTransport:
    network = False
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, url, *, method, headers, body):
        self.calls.append((url, method, dict(headers), body))
        if not self.responses:
            raise AssertionError("unexpected request")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        status, payload, response_headers = value
        content = payload if isinstance(payload, bytes) else canonical(payload).encode()
        return HttpResponse(status, response_headers, content, url)


class DiscoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "materials"
        self.config = ProjectConfig("materials", "Synthetic materials", "Invented portable fixture",
            providers=tuple(ProviderConfig(x, x) for x in ("openalex", "crossref", "europepmc", "semantic_scholar")),
            search=(SearchConcept("porosity", "porous ceramic"),), evidence=EvidencePolicy(("europepmc",)))
        self.project = Project.create(self.root, self.config, created_by="fixture", created_at=AT)
        self.addCleanup(self.temp.cleanup)

    def discover(self, name="openalex", data=None, run=None, **bounds):
        provider = MetadataProvider(name)
        provider.network = False  # Offline adapter invocation, same normalization/request dialect.
        plan = self.project.discovery.plan(provider, run_id=run or name, concept_id="porosity", created_at=AT, **bounds)
        transport = RecordedTransport([(200, data or (OA if name == "openalex" else CR), {})])
        result = self.project.discovery.execute(plan, provider, transport=transport, clock=lambda: AT)
        return plan, provider, transport, result

    def canonicalize(self, run):
        return self.project.discovery.canonicalize(run, approve_new_identities=True, approve_aliases=True)

    def paper(self):
        self.discover()
        self.canonicalize("openalex")
        return self.project.identities.exact_owner(Identifier("doi", "10.1234/materials.1"))

    def test_multi_provider_observations_deduplicate_without_metadata_loss(self):
        self.discover()
        self.discover("crossref")
        self.canonicalize("openalex")
        self.canonicalize("crossref")
        self.assertEqual(len(self.project.discovery.observations()), 3)
        self.assertEqual(len(self.project.identities.papers()), 2)
        pid = self.project.identities.exact_owner(Identifier("openalex", "w123"))
        metadata = self.project.discovery.metadata(pid)
        self.assertEqual(len(metadata["alternatives"]["title"]), 2)
        self.assertIsNotNone(metadata["fields"]["abstract"])
        self.assertEqual(len(events(self.project, kind="canonical_link", paper_id=pid)), 2)
        self.assertEqual(self.project.reviews.membership(pid)["state"], "not_reviewed")
        self.assertEqual(Project.open(self.root).discovery.metadata(pid), metadata)

    def test_raw_bytes_and_source_lineage(self):
        self.discover()
        observation = self.project.discovery.observations()[0]
        self.assertEqual(json.loads(artifact(self.project, observation["source_sha256"]).read_bytes()), OA)
        self.assertEqual(observation["payload"]["raw_record"], OA["results"][0])
        self.assertEqual(observation["payload"]["query"], "porous ceramic")
        self.assertIn("cursor=%2A", observation["payload"]["source_uri"])

    def test_metadata_only_and_doi_missing_stable_identity(self):
        self.discover()
        links = self.canonicalize("openalex")
        before = self.project.identities.papers()
        self.assertEqual(self.canonicalize("openalex"), links)
        self.assertEqual(self.project.identities.papers(), before)
        pid = self.project.identities.exact_owner(Identifier("openalex", "W124"))
        self.assertEqual(self.project.evidence.status(pid)["best_available"], "metadata")
        self.assertNotIn("doi", {x["scheme"] for x in self.project.discovery.metadata(pid)["identifiers"]})

    def test_exact_identifier_conflict_preserves_all_observations(self):
        self.discover()
        self.canonicalize("openalex")
        conflict = {"results": [{"id": "https://openalex.org/W124", "doi": "10.1234/materials.1", "title": "Conflict"}],
                    "meta": {"count": 1}}
        self.discover(data=conflict, run="conflict")
        results = self.canonicalize("conflict")
        self.assertEqual(results[0]["status"], "unresolved")
        self.assertEqual(len(self.project.identities.papers()), 2)
        self.assertEqual(len(self.project.discovery.observations()), 3)

    def test_invalid_id_is_review_issue_not_lost_candidate(self):
        data = {"results": [{"id": "bad", "title": "Still a lead", "doi": "bad DOI"}], "meta": {"count": 1}}
        self.discover(data=data)
        self.assertEqual(self.canonicalize("openalex")[0]["status"], "unresolved")
        self.assertEqual(len(self.project.discovery.observations()), 1)

    def test_planning_and_reads_are_side_effect_free(self):
        before = self.project.database_path.read_bytes()
        self.project.discovery.plan(MetadataProvider("openalex"), run_id="plan", query="ceramic", created_at=AT)
        self.project.discovery.observations()
        self.assertEqual(before, self.project.database_path.read_bytes())

    def test_external_confirmation_before_any_request(self):
        provider = MetadataProvider("openalex")
        plan = self.project.discovery.plan(provider, run_id="external", query="fixture", created_at=AT)
        transport = RecordedTransport([])
        with self.assertRaises(ContractError):
            self.project.discovery.execute(plan, provider, transport=transport)
        self.assertEqual(transport.calls, [])
        self.assertEqual(events(self.project), [])

    def test_provider_failure_retry_and_retry_after_are_preserved(self):
        provider = MetadataProvider("openalex")
        provider.network = False
        plan = self.project.discovery.plan(provider, run_id="retry", query="fixture", created_at=AT, max_attempts=3)
        transport = RecordedTransport([(429, {"error": "rate limited"}, {"Retry-After": "2"}),
                                       (503, {}, {}), (200, OA, {})])
        waits = []
        result = self.project.discovery.execute(plan, provider, transport=transport, clock=lambda: AT, sleeper=waits.append)
        self.assertEqual((result["logical_requests"], result["physical_attempts"]), (1, 3))
        self.assertEqual(waits, [2, 1])
        self.assertEqual([x["payload"]["http_status"] for x in events(self.project, kind="request_result")], [429, 503, 200])
        self.assertEqual(len(self.project.discovery.observations()), 2)
        self.assertEqual(self.project.discovery.execute(plan, provider, transport=transport), result)
        self.assertEqual(len(transport.calls), 3)

    def test_retry_after_larger_than_bound_stops_without_substitution(self):
        provider = MetadataProvider("openalex")
        provider.network = False
        plan = self.project.discovery.plan(provider, run_id="blocked", query="fixture", created_at=AT, max_attempts=3)
        transport = RecordedTransport([(429, {}, {"Retry-After": "3600"})])
        result = self.project.discovery.execute(plan, provider, transport=transport, clock=lambda: AT)
        self.assertEqual(result["outcome"], "retryable_error")
        self.assertEqual(result["physical_attempts"], 1)
        self.assertTrue(events(self.project, kind="request_result")[0]["payload"]["retry_blocked"])

    def test_malformed_response_and_transport_failure_retained(self):
        _, _, _, result = self.discover(data={"wrong": []})
        self.assertEqual(result["outcome"], "malformed_response")
        self.assertEqual(len(events(self.project, kind="request_result")), 2)
        provider = MetadataProvider("crossref")
        provider.network = False
        plan = self.project.discovery.plan(provider, run_id="failure", query="fixture", created_at=AT)
        self.project.discovery.execute(plan, provider, transport=RecordedTransport([ProviderTransportError("private")]), clock=lambda: AT)
        serialized = canonical(events(self.project))
        self.assertNotIn("private", serialized)
        self.assertIn("ProviderTransportError", serialized)

    def test_page_limit_and_cursor_explicit(self):
        data = {"results": OA["results"][:1], "meta": {"count": 10, "next_cursor": "next"}}
        _, _, _, result = self.discover(data=data, page_size=1)
        self.assertEqual(result["outcome"], "truncated_page_limit")
        self.assertEqual(result["next_cursor"], "next")

    def test_schema_and_events_are_immutable(self):
        self.discover()
        with self.assertRaises(sqlite3.IntegrityError), connection(self.project.database_path, write=True) as db:
            db.execute("DELETE FROM ct_pipeline_events")

    def test_verified_xml_and_native_parse_preserve_provenance(self):
        pid = self.paper()
        resolver = EuropePmcResolver()
        resolver.network = False
        request = self.project.evidence.plan(pid, created_at=AT)
        result = self.project.evidence.acquire(request, resolvers={"europepmc": resolver},
            transport=RecordedTransport([(200, JATS, {})]), clock=lambda: AT)
        self.assertEqual(result["best_available"], "structured_text")
        reps = self.project.evidence.representations(pid, trusted_only=True)
        self.assertEqual(len(reps), 2)
        self.assertIn("derived_from", reps[1]["payload"])
        self.assertIn("sections", reps[1]["payload"]["quality"])
        self.assertEqual(self.project.evidence.acquire(request, resolvers={"europepmc": resolver},
            transport=RecordedTransport([])), result)
        self.assertEqual(self.project.reviews.membership(pid)["state"], "not_reviewed")

    def document(self, pid, body, representation="jats_xml"):
        return self.project.evidence.preserve_document(pid, body, representation=representation,
            media_type="application/xml" if representation == "jats_xml" else "application/pdf",
            source_uri="fixture://legitimate-document", legitimate_basis="invented_fixture",
            resolver="fixture", resolver_version="v1", created_at=AT)

    def test_wrong_xml_and_pending_pdf_never_trusted(self):
        pid = self.paper()
        self.document(pid, JATS.replace(b"materials.1", b"other.9"))
        self.document(pid, b"%PDF-1.4\nSynthetic unverified document", "pdf")
        status = self.project.evidence.status(pid)
        self.assertEqual(status["best_available"], "abstract")
        self.assertEqual(status["pending_identity"], 1)
        self.assertEqual(status["mismatch_or_invalid"], 1)
        self.assertEqual(self.project.evidence.representations(pid, trusted_only=True), [])

    def test_cited_reference_id_cannot_verify_document(self):
        pid = self.paper()
        body = b'<article><body><p>Unknown work</p></body><back><ref-list><ref><article-id pub-id-type="doi">10.1234/materials.1</article-id></ref></ref-list></back></article>'
        self.document(pid, body)
        self.assertEqual(self.project.evidence.status(pid)["pending_identity"], 1)

    def test_invalid_xml_and_external_entities_fail_closed(self):
        pid = self.paper()
        self.document(pid, b'<!DOCTYPE article SYSTEM "file:///etc/passwd"><article/>')
        self.assertEqual(self.project.evidence.status(pid)["mismatch_or_invalid"], 1)

    def test_document_idempotency_and_absence_do_not_create_review(self):
        pid = self.paper()
        one = self.document(pid, JATS)
        self.assertEqual(one, self.document(pid, JATS))
        self.assertEqual(len(self.project.evidence.representations(pid)), 2)
        self.assertEqual(events(self.project, kind="identity_assessment"), [])
        self.assertEqual(self.project.status()["membership"]["not_reviewed"], 2)

    def test_configuration_and_plan_guards(self):
        provider = MetadataProvider("openalex")
        provider.network = False
        plan = self.project.discovery.plan(provider, run_id="guard", query="fixture", created_at=AT)
        for changed in (replace(plan, project_id="other"), replace(plan, adapter_version="changed"),
                        replace(plan, max_attempts=4)):
            with self.assertRaises(ContractError):
                self.project.discovery.execute(changed, provider, transport=RecordedTransport([]))
        with self.assertRaises(ContractError):
            self.project.discovery.plan(MetadataProvider("crossref"), run_id="guard", concept_id="unknown")

    def test_credentials_are_not_persisted(self):
        config = replace(self.config, config_version=2,
            providers=(ProviderConfig("openalex", "openalex", "FIXTURE_API_KEY"),))
        self.project.configure(config, expected_event_id=self.project.configuration_history()[-1]["event_id"], created_by="fixture", created_at=AT)
        with patch.dict("os.environ", {"FIXTURE_API_KEY": "secret-value-not-to-log"}):
            _, _, transport, _ = self.discover()
        self.assertIn("Authorization", transport.calls[0][2])
        self.assertNotIn("secret-value-not-to-log", canonical(events(self.project)))

    def test_crossref_europepmc_semantic_dialects(self):
        epmc = {"resultList": {"result": [{"id": "345", "source": "MED", "pmcid": "PMC345", "doi": "10.1234/other",
            "title": "Synthetic material", "abstractText": "Fixture abstract", "pubYear": "2023"}]}, "hitCount": 1}
        s2 = {"data": [{"paperId": "a" * 40, "externalIds": {"DOI": "10.1234/other", "PubMed": "345"},
                       "title": "Same fixture work", "year": 2023}], "total": 1}
        for provider, data in (("europepmc", epmc), ("semantic_scholar", s2)):
            self.discover(provider, data)
            self.canonicalize(provider)
        self.assertEqual(len(self.project.identities.papers()), 1)
        self.assertEqual(len(self.project.discovery.observations()), 2)
        self.assertEqual(_abstract_from_index({"世界": [1], "Hello": [0]}), "Hello 世界")

    def test_cli_plans_candidates_and_evidence_without_network(self):
        pid = self.paper()
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(main(["discover", str(self.root), "--provider", "openalex", "--run-id", "planned", "--concept-id", "porosity"]), 0)
            self.assertEqual(main(["candidates", str(self.root)]), 0)
            self.assertEqual(main(["evidence", str(self.root), "--paper-id", pid]), 0)

    def test_explicit_phase2a_upgrade_preserves_bootstrap_and_old_rows(self):
        target = Path(self.temp.name) / "old-project"
        target.mkdir()
        raw = self.config.to_dict()
        raw.pop("evidence")  # Exact legacy configuration shape, not a rewritten bootstrap.
        body = (canonical(raw) + "\n").encode("utf-8")
        with patch("corpustrail._internal.database.migrations", return_value=migrations()[:32]):
            create_database(target / self.config.database, raw, AT, "fixture")
            (target / "corpustrail.project.json").write_bytes(body)
            old = Project.open(target)
            self.assertEqual(old.identities.papers(), [])
        before = (target / self.config.database).read_bytes()
        with self.assertRaises(ContractError):
            Project.open(target)
        self.assertEqual((target / self.config.database).read_bytes(), before)
        project = Project.upgrade(target, backup="data/backups/before-033.sqlite3", created_at=AT)
        self.assertEqual((target / "corpustrail.project.json").read_bytes(), body)
        self.assertEqual(project.status()["checks"]["migrations"], 35)
        with closing(sqlite3.connect(target / "data/backups/before-033.sqlite3")) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 32)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM paper_entities").fetchone()[0], 0)
        with self.assertRaises(ContractError):
            Project.upgrade(target, backup="data/backups/before-033.sqlite3", created_at=AT)

    def test_upgrade_refuses_clobber_and_wrong_schema(self):
        target = Path(self.temp.name) / "old-clobber"
        target.mkdir()
        raw = self.config.to_dict()
        with patch("corpustrail._internal.database.migrations", return_value=migrations()[:32]):
            create_database(target / self.config.database, raw, AT, "fixture")
        (target / "corpustrail.project.json").write_text(canonical(raw) + "\n", encoding="utf-8")
        destination = target / "backup.sqlite3"
        destination.write_bytes(b"existing")
        before = (target / self.config.database).read_bytes()
        with self.assertRaises(FileExistsError):
            Project.upgrade(target, backup="backup.sqlite3", created_at=AT)
        self.assertEqual(destination.read_bytes(), b"existing")
        self.assertEqual((target / self.config.database).read_bytes(), before)
        with closing(sqlite3.connect(target / self.config.database)) as db, db:
            db.execute("UPDATE schema_migrations SET code_sha256='changed' WHERE version=1")
        with self.assertRaises(ContractError):
            Project.upgrade(target, backup="new-backup.sqlite3", created_at=AT)
        self.assertFalse((target / "new-backup.sqlite3").exists())

    def test_attempt_reservation_prevents_replay_and_concurrent_duplicate(self):
        provider = MetadataProvider("openalex")
        provider.network = False
        plan = self.project.discovery.plan(provider, run_id="interrupted", query="fixture", created_at=AT)
        payload = {"attempt_id": "reserved", "timestamp": AT}
        append(self.project, "request_started", plan.run_id, payload, exclusive=True)
        with self.assertRaises(ContractError):
            append(self.project, "request_started", plan.run_id, payload, exclusive=True)
        with self.assertRaises(sqlite3.IntegrityError):
            append(self.project, "request_started", plan.run_id, {**payload, "timestamp": "2026-01-02T00:00:00+00:00"}, exclusive=True)
        transport = RecordedTransport([])
        with self.assertRaises(ContractError):
            self.project.discovery.execute(plan, provider, transport=transport)
        self.assertEqual(transport.calls, [])

    def test_acquisition_failure_and_retry_retained(self):
        pid = self.paper()
        resolver = EuropePmcResolver()
        resolver.network = False
        request = replace(self.project.evidence.plan(pid, created_at=AT), max_attempts=3)
        # Altered requests fail closed; use a real project policy change instead.
        with self.assertRaises(ContractError):
            self.project.evidence.acquire(request, resolvers={"europepmc": resolver}, transport=RecordedTransport([]))
        config = replace(self.config, config_version=2, evidence=EvidencePolicy(("europepmc",), 3))
        self.project.configure(config, expected_event_id=self.project.configuration_history()[-1]["event_id"], created_by="fixture", created_at=AT)
        request = self.project.evidence.plan(pid, created_at=AT)
        waits = []
        result = self.project.evidence.acquire(request, resolvers={"europepmc": resolver},
            transport=RecordedTransport([(429, b"rate-limited", {"Retry-After": "2"}), (404, b"not found", {})]),
            clock=lambda: AT, sleeper=waits.append)
        self.assertEqual(waits, [2])
        self.assertEqual(result["best_available"], "abstract")
        self.assertEqual([x["payload"].get("http_status") for x in events(self.project, kind="acquisition_result")], [429, 404, None])
        self.assertEqual(self.project.reviews.membership(pid)["state"], "not_reviewed")

    def test_abstract_only_article_is_not_claimed_as_full_text(self):
        pid = self.paper()
        body = b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/materials.1</article-id><abstract><p>Only an abstract.</p></abstract></article-meta></front></article>'
        self.document(pid, body)
        self.assertEqual(self.project.evidence.status(pid)["best_available"], "abstract")
        self.assertEqual(self.project.evidence.status(pid)["verified_structured_text"], 0)

    def test_artifact_tamper_is_detected_without_repairing(self):
        self.discover()
        sha = self.project.discovery.observations()[0]["source_sha256"]
        path = artifact(self.project, sha)
        path.write_bytes(b"tampered fixture")
        with self.assertRaises(ContractError):
            artifact(self.project, sha)
        self.assertEqual(self.canonicalize("openalex")[0]["status"], "unresolved")
        self.assertEqual(path.read_bytes(), b"tampered fixture")

    def test_malformed_individual_record_does_not_erase_other_results(self):
        data = {"results": [OA["results"][0], {"authorships": ["wrong-shape"], "title": "Invalid record"}], "meta": {"count": 2}}
        self.discover(data=data)
        results = self.canonicalize("openalex")
        self.assertEqual(len(self.project.discovery.observations()), 2)
        self.assertEqual(results[1]["status"], "unresolved")
        self.assertEqual(len(self.project.identities.papers()), 1)

    def test_deterministic_fixed_offline_inputs_and_pure_views(self):
        self.discover()
        self.canonicalize("openalex")
        before = self.project.database_path.read_bytes()
        values = [self.project.discovery.metadata(x) for x in self.project.identities.papers()]
        [self.project.evidence.status(x) for x in self.project.identities.papers()]
        self.assertEqual(self.project.database_path.read_bytes(), before)
        another = Project.create(Path(self.temp.name) / "another", self.config, created_by="fixture", created_at=AT)
        provider = MetadataProvider("openalex")
        provider.network = False
        plan = another.discovery.plan(provider, run_id="openalex", concept_id="porosity", created_at=AT)
        another.discovery.execute(plan, provider, transport=RecordedTransport([(200, OA, {})]), clock=lambda: AT)
        another.discovery.canonicalize(plan.run_id, approve_new_identities=True, approve_aliases=True)
        self.assertEqual([another.discovery.metadata(x) for x in another.identities.papers()], values)
        self.assertEqual(another.database_path.read_bytes(), before)

    def test_native_bioc_and_tei_renderers_preserved(self):
        from corpustrail.evidence.native_parsers import NativeBiocParser, render_grobid_tei
        path = Path(self.temp.name) / "bioc.json"
        path.write_text(json.dumps({"documents": [{"passages": [{"text": "Fixture methods", "offset": 0, "infons": {"section_type": "Methods"}}]}]}), encoding="utf-8")
        parsed = NativeBiocParser().parse(path)
        self.assertIn("Fixture methods", parsed.body)
        tei = render_grobid_tei(b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div><head>Methods</head><p>Fixture procedure.</p></div></body></text></TEI>')
        self.assertIn("Fixture procedure", tei.body)

    def test_pending_artifact_cannot_bypass_review_provenance(self):
        from corpustrail.curation import EvidenceBasis, ReviewEvent
        pid = self.paper()
        self.document(pid, b"%PDF-1.4\nUnverified fixture", "pdf")
        rep = self.project.evidence.representations(pid)[0]["payload"]
        event = ReviewEvent(pid, "included", "sufficient", "full_document", "Fixture rationale",
            "fixture", AT, (EvidenceBasis("full_text", rep["artifact_sha256"], rep["source_uri"], artifact_validity="verified"),))
        with self.assertRaises(ContractError):
            self.project.reviews.plan(event)

    def test_verified_acquired_abstract_fills_missing_view_without_overwrite(self):
        from corpustrail.curation import EvidenceBasis, ReviewEvent
        self.discover(data={"results": [{"id": "https://openalex.org/W900", "doi": "10.1234/materials.1", "title": "Fixture without abstract"}], "meta": {"count": 1}})
        self.canonicalize("openalex")
        pid = self.project.identities.papers()[0]
        body = b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/materials.1</article-id><abstract><p>Explicit fixture abstract.</p></abstract></article-meta></front></article>'
        self.document(pid, body)
        self.assertIsNone(self.project.identities.observations(pid)[0]["record"]["abstract"])
        metadata = self.project.discovery.metadata(pid)
        self.assertEqual(metadata["fields"]["abstract"], "Explicit fixture abstract.")
        self.assertEqual(self.project.evidence.status(pid)["best_available"], "abstract")
        rep = next(x["payload"] for x in self.project.evidence.representations(pid) if x["payload"]["representation"] == "abstract")
        event = ReviewEvent(pid, "included", "sufficient", "abstract", "Fixture rationale", "fixture", AT,
            (EvidenceBasis("abstract", rep["artifact_sha256"], rep["source_uri"], artifact_validity="verified"),))
        self.assertIsNotNone(self.project.reviews.plan(event))

    def test_openalex_short_page_with_cursor_does_not_lose_later_records(self):
        provider = MetadataProvider("openalex")
        provider.network = False
        plan = self.project.discovery.plan(provider, run_id="pages", query="fixture", created_at=AT, max_pages=2)
        first = {"results": OA["results"][:1], "meta": {"count": 2, "next_cursor": "second"}}
        second = {"results": OA["results"][1:], "meta": {"count": 2, "next_cursor": None}}
        transport = RecordedTransport([(200, first, {}), (200, second, {})])
        result = self.project.discovery.execute(plan, provider, transport=transport, clock=lambda: AT)
        self.assertEqual((result["observations"], result["logical_requests"]), (2, 2))
        self.assertIn("cursor=second", transport.calls[1][0])

    def test_recovered_doi_adds_alias_without_reminting_paper(self):
        self.discover()
        self.canonicalize("openalex")
        pid = self.project.identities.exact_owner(Identifier("openalex", "W124"))
        self.discover(data={"results": [{"id": "https://openalex.org/W124", "doi": "10.1234/recovered", "title": "Recovered metadata"}], "meta": {"count": 1}}, run="recovered")
        self.canonicalize("recovered")
        self.assertEqual(self.project.identities.exact_owner(Identifier("doi", "10.1234/recovered")), pid)
        self.assertEqual(len(self.project.identities.papers()), 2)

    def test_retry_after_http_date_uses_recorded_attempt_time(self):
        from datetime import datetime
        self.assertEqual(retry_after({"Retry-After": "Thu, 01 Jan 2026 00:00:05 GMT"}, clock=datetime.fromisoformat(AT)), 5)

    def test_redirect_response_is_not_followed_or_normalized(self):
        class Redirected(RecordedTransport):
            def request(self, url, *, method, headers, body):
                return HttpResponse(200, {}, canonical(OA).encode(), "https://unapproved.example/works")
        provider = MetadataProvider("openalex")
        provider.network = False
        plan = self.project.discovery.plan(provider, run_id="redirect", query="fixture", created_at=AT)
        result = self.project.discovery.execute(plan, provider, transport=Redirected([]), clock=lambda: AT)
        self.assertEqual(result["outcome"], "permanent_error")
        self.assertEqual(len(self.project.discovery.observations()), 0)

    def test_namespaced_article_identity_is_exactly_verified(self):
        pid = self.paper()
        self.document(pid, JATS.replace(b"<article>", b'<article xmlns="urn:synthetic-jats">'))
        self.assertEqual(self.project.evidence.status(pid)["best_available"], "structured_text")

    def test_repository_route_does_not_infer_publication_version(self):
        declaration = EuropePmcResolver().representation(HttpResponse(200, {}, JATS, "https://www.ebi.ac.uk/fixture"))
        self.assertEqual(declaration["version_kind"], "unknown")


if __name__ == "__main__":
    unittest.main()
