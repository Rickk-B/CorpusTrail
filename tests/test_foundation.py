"""Portable synthetic tests; never import the historical runtime or real labels."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from corpustrail._internal.database import connection, migrations
from corpustrail._internal.values import ContractError, digest_bytes
from corpustrail.curation import EvidenceBasis, ReviewEvent
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.project import ConceptExtension, Project, ProjectConfig, ProviderConfig, ReviewPolicy, SearchConcept


AT = "2026-10-01T00:00:00+00:00"
BODY = b'{"fixture":"synthetic bibliographic evidence"}'


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = ProjectConfig("materials-test", "Materials sensors", "Synthetic broad-topic software fixture",
                                    review=ReviewPolicy(authorized_reviewers=("reviewer_one",)))
        self.project = Project.create(self.root / "project", self.config, created_by="fixture", created_at=AT)

    def source(self, key="one", **kwargs):
        return SourceReference("fixture://bibliography/v1", key, digest_bytes(BODY), len(BODY), "fixture", AT,
                               **{"identity_status": "verified", **kwargs})

    def record(self, key="one", abstract=None):
        return BibliographicRecord("A synthetic sensor", abstract, ("Example Author",), 2020,
                                   "Invented Journal", (Identifier("fixture.record", key),))

    def enroll(self, key="one", abstract=None):
        plan = self.project.identities.plan(self.record(key, abstract), self.source(key))
        return self.project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)

    def event(self, paper_id, state="included", **kwargs):
        sufficient = {"included": "sufficient", "excluded": "sufficient",
                      "insufficient_evidence": "insufficient", "unresolved": "undetermined"}.get(state, "undetermined")
        defaults = dict(paper_id=paper_id, state=state, sufficiency=sufficient, review_extent="metadata",
                        rationale="Synthetic rationale", producer_id="reviewer_one", created_at=AT,
                        evidence=(EvidenceBasis("metadata", digest_bytes(BODY), "fixture://bibliography/v1",
                                                artifact_validity="verified"),))
        return ReviewEvent(**{**defaults, **kwargs})

    def fingerprint(self):
        return digest_bytes(self.project.database_path.read_bytes())

    def test_empty_initialization_and_no_scientific_seed_data(self):
        status = self.project.status()
        self.assertEqual(status["papers"], 0)
        self.assertEqual(status["checks"], {"integrity": "ok", "foreign_key_errors": 0, "migrations": 37})
        with connection(self.project.database_path) as db:
            populated = {r[0]: db.execute(f'SELECT COUNT(*) FROM "{r[0]}"').fetchone()[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual({key for key, count in populated.items() if count},
                         {"schema_migrations", "ct_project_identity", "ct_project_config_events"})
        self.assertIn('ct_model_events', populated)
        self.assertEqual(populated['ct_model_events'], 0)

    def test_defaults_and_public_output_are_topic_neutral(self):
        body = json.dumps(self.config.to_dict()) + json.dumps(self.project.status())
        for prohibited in ("is_human", "upe_scope", "biophoton", "mitogenetic", "UPE_Library"):
            self.assertNotIn(prohibited, body)
        self.assertEqual(self.config.search, ())
        self.assertEqual(self.config.providers, ())
        self.assertEqual(self.config.concept_extensions, ())

    def test_reopen_and_reads_are_byte_preserving(self):
        before = self.fingerprint()
        status = self.project.status()
        self.assertEqual(Project.open(self.project.root).status(), status)
        self.project.configuration_history()
        self.assertEqual(self.fingerprint(), before)
        self.assertFalse(Path(str(self.project.database_path) + "-wal").exists())

    def test_fixed_inputs_reproduce_database_and_schema(self):
        second = Project.create(self.root / "second", self.config, created_by="fixture", created_at=AT)
        self.assertEqual(second.database_path.read_bytes(), self.project.database_path.read_bytes())
        self.assertEqual(second.status(), self.project.status())

    def test_init_never_clobbers_an_existing_directory(self):
        target = self.root / "occupied"
        target.mkdir()
        original = target / "sentinel"
        original.write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            Project.create(target, self.config, created_by="fixture")
        self.assertEqual(original.read_text(encoding="utf-8"), "keep")

    def test_read_missing_database_does_not_create_it(self):
        self.project.database_path.unlink()
        with self.assertRaises(ContractError):
            Project.open(self.project.root)
        self.assertFalse(self.project.database_path.exists())

    def test_read_missing_bootstrap_does_not_initialize(self):
        target = self.root / "missing"
        with self.assertRaises(FileNotFoundError):
            Project.open(target)
        self.assertFalse(target.exists())

    def test_confined_paths_and_symlink_escape(self):
        for path in ("../outside", "/absolute", "data/../outside", "data\\outside", ".", "data//nested"):
            with self.subTest(path=path), self.assertRaises(ContractError):
                replace(self.config, database=path).validate()
        with self.assertRaises(ContractError):
            replace(self.config, database="other/db.sqlite3").validate()
        moved = self.root / "outside"
        self.project.database_path.parent.rename(moved)
        self.project.database_path.parent.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ContractError):
            Project.open(self.project.root)

    def test_generic_project_can_be_relocated(self):
        target = self.root / "relocated"
        before = self.project.status()
        self.project.root.rename(target)
        self.assertEqual(Project.open(target).status(), before)

    def test_configuration_roundtrip_with_explicit_optional_sections(self):
        config = replace(self.config, search=(SearchConcept("sensor", "material sensors", aliases=("material probes",)),),
                         providers=(ProviderConfig("fixture", "fixture", "FIXTURE_PROVIDER_TOKEN"),),
                         concept_extensions=(ConceptExtension("materials", "draft-v1", ("materials.sensor_type",)),))
        self.assertEqual(ProjectConfig.from_dict(config.to_dict()), config)
        self.assertEqual(config.providers[0].credential_env, "FIXTURE_PROVIDER_TOKEN")

    def test_plaintext_credentials_and_overloaded_fields_are_not_schema(self):
        for field in ("api_key", "is_human", "is_human_invivo_skin"):
            with self.assertRaises(ContractError):
                ProjectConfig.from_dict({**self.config.to_dict(), field: "not allowed"})
        raw = self.config.to_dict()
        raw["providers"] = [{"provider_id": "fixture", "adapter": "fixture", "api_key": "not a real secret"}]
        with self.assertRaises(ContractError):
            ProjectConfig.from_dict(raw)

    def test_extensions_cannot_redefine_core_namespace(self):
        with self.assertRaises(ContractError):
            ConceptExtension("ct", "v1", ("ct.organism",)).validate()
        with self.assertRaises(ContractError):
            ConceptExtension("materials", "v1", ("organism",)).validate()

    def test_configuration_changes_are_append_only_and_revision_guarded(self):
        original_bytes = (self.project.root / "corpustrail.project.json").read_bytes()
        prior = self.project.configuration_history()[0]["event_id"]
        config = replace(self.config, name="Updated sensors", config_version=2)
        new = self.project.configure(config, expected_event_id=prior, created_by="fixture", created_at=AT)
        self.assertEqual(Project.open(self.project.root).config, config)
        self.assertEqual(len(self.project.configuration_history()), 2)
        self.assertEqual(self.project.configuration_history()[-1]["previous_event_id"], prior)
        self.assertNotEqual(new, prior)
        self.assertEqual((self.project.root / "corpustrail.project.json").read_bytes(), original_bytes)
        with self.assertRaises(ContractError):
                self.project.configure(replace(config, config_version=3), expected_event_id=prior, created_by="fixture")

    def test_configuration_cannot_silently_reinterpret_established_human_scope(self):
        paper = self.enroll()
        self.project.reviews.apply(self.project.reviews.plan(self.event(paper, authority_state="human_authorized")))
        prior = self.project.configuration_history()[0]["event_id"]
        with self.assertRaises(ContractError):
            self.project.configure(replace(self.config, config_version=2, description="A different scientific scope"),
                                   expected_event_id=prior, created_by="fixture")
        self.assertEqual(self.project.reviews.membership(paper)["state"], "included")

    def test_identity_and_storage_paths_cannot_be_reconfigured(self):
        prior = self.project.configuration_history()[0]["event_id"]
        for change in ({"project_id": "different"}, {"database": "data/different.sqlite3"},
                       {"database": "more/db.sqlite3", "data_directory": "more"}):
            with self.assertRaises(ContractError):
                self.project.configure(replace(self.config, config_version=2, **change),
                                       expected_event_id=prior, created_by="fixture")

    def test_bootstrap_edit_fails_closed(self):
        bootstrap = self.project.root / "corpustrail.project.json"
        bootstrap.write_text(json.dumps(replace(self.config, name="Changed outside history").to_dict()), encoding="utf-8")
        with self.assertRaises(ContractError):
            Project.open(self.project.root)

    def test_historical_only_database_is_rejected_without_migration(self):
        target = self.root / "historical"
        target.mkdir()
        bootstrap = target / "corpustrail.project.json"
        bootstrap.write_bytes((self.project.root / "corpustrail.project.json").read_bytes())
        database = target / self.config.database
        database.parent.mkdir()
        with closing(sqlite3.connect(database)) as db, db:
            for meta, body in migrations()[:31]:
                db.executescript(body)
                db.execute("INSERT INTO schema_migrations VALUES (?,?,?,?)",
                           (meta["version"], meta["name"], AT, meta["sha256"]))
                db.commit()
        before = database.read_bytes()
        with self.assertRaises(ContractError):
            Project.open(target)
        self.assertEqual(database.read_bytes(), before)

    def test_migration_hash_tampering_is_rejected(self):
        with connection(self.project.database_path, write=True) as db:
            db.execute("UPDATE schema_migrations SET code_sha256='changed' WHERE version=1")
        with self.assertRaises(ContractError):
            Project.open(self.project.root)

    def test_explicit_enrollment_approval_and_read_only_plan(self):
        before = self.fingerprint()
        plan = self.project.identities.plan(self.record(), self.source())
        self.assertEqual(self.fingerprint(), before)
        with self.assertRaises(ContractError):
            self.project.identities.apply(plan)
        with self.assertRaises(ContractError):
            self.project.identities.apply(plan, approve_new_identity=True)
        self.assertEqual(self.project.identities.papers(), [])

    def test_identifier_present_and_missing_enrollment_is_stable(self):
        a = self.enroll()
        record = replace(self.record("empty"), identifiers=(), title=None, year=None)
        plan = self.project.identities.plan(record, self.source("empty"))
        b = self.project.identities.apply(plan, approve_new_identity=True)
        self.assertNotEqual(a, b)
        self.assertEqual(self.project.reviews.membership(b)["state"], "not_reviewed")
        self.assertIsNone(self.project.identities.observations(b)[0]["record"]["title"])

    def test_title_similarity_is_never_authoritative(self):
        a, b = self.enroll("first"), self.enroll("second")
        self.assertNotEqual(a, b)
        self.assertEqual(len(self.project.identities.papers()), 2)

    def test_exact_alias_attachment_and_independent_source_preservation(self):
        a = self.enroll()
        record = replace(self.record(), identifiers=self.record().identifiers + (Identifier("fixture.alternate", "alternate"),))
        plan = self.project.identities.plan(record, self.source("alternate"))
        self.assertEqual(plan.action, "attach")
        self.assertEqual(self.project.identities.apply(plan, approve_aliases=True), a)
        self.assertEqual(self.project.identities.exact_owner(Identifier("fixture.alternate", "alternate")), a)
        self.assertEqual(len(self.project.identities.observations(a)), 2)

    def test_metadata_correction_never_remints_a_paper_id(self):
        a = self.enroll()
        record = replace(self.record(), title="A corrected synthetic title", identifiers=(Identifier("fixture.record", "one"),
                                                                                      Identifier("doi", "10.5555/fixture-only")))
        plan = self.project.identities.plan(record, self.source())
        self.assertEqual(self.project.identities.apply(plan, approve_aliases=True), a)
        self.assertEqual(len(self.project.identities.observations(a)), 2)

    def test_exact_identifier_conflicts_preserve_the_database(self):
        self.enroll("one")
        self.enroll("two")
        before = self.fingerprint()
        record = replace(self.record(), identifiers=(Identifier("fixture.record", "one"), Identifier("fixture.record", "two")))
        with self.assertRaises(ContractError):
            self.project.identities.plan(record, self.source("conflict"))
        self.assertEqual(self.fingerprint(), before)

    def test_unverified_identity_never_creates_an_exact_alias(self):
        source = self.source(identity_status="unverified")
        plan = self.project.identities.plan(self.record(), source)
        self.project.identities.apply(plan, approve_new_identity=True)
        self.assertIsNone(self.project.identities.exact_owner(Identifier("fixture.record", "one")))
        self.assertEqual(len(self.project.identities.observations(plan.paper_id)), 1)

    def test_model_identity_sources_are_not_trusted(self):
        with self.assertRaises(ContractError):
            self.project.identities.plan(self.record(), self.source(producer_type="model"))

    def test_identity_rerun_is_idempotent_after_other_enrollments(self):
        plan = self.project.identities.plan(self.record(), self.source())
        self.project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)
        self.enroll("two")
        replay = self.project.identities.plan(self.record(), self.source())
        self.assertEqual(replay, plan)
        before = self.fingerprint()
        self.project.identities.apply(replay)
        self.assertEqual(self.fingerprint(), before)

    def test_stale_and_forged_identity_plans_fail_closed(self):
        plan = self.project.identities.plan(self.record(), self.source())
        with self.assertRaises(ContractError):
            self.project.identities.apply(replace(plan, paper_id="invented-forgery"), approve_new_identity=True, approve_aliases=True)
        self.enroll("two")
        with self.assertRaises(ContractError):
            self.project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)

    def test_mid_enrollment_failure_rolls_back_every_written_record(self):
        with connection(self.project.database_path, write=True) as db:
            db.execute("CREATE TRIGGER fixture_abort BEFORE INSERT ON ct_paper_observations "
                       "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        plan = self.project.identities.plan(self.record(), self.source())
        with self.assertRaises(sqlite3.IntegrityError):
            self.project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)
        with connection(self.project.database_path) as db:
            for table in ("paper_entities", "raw_artifacts", "ct_enrollment_operations", "ct_source_bindings",
                          "ct_paper_observations", "paper_identifiers", "identifier_assertions"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_exact_normalizers_and_unicode_preservation(self):
        self.assertEqual(Identifier("doi", "https://doi.org/10.5555/FIXTURE").normalized(), ("doi", "10.5555/fixture"))
        self.assertEqual(Identifier("pmcid", "pmc123").normalized(), ("pmcid", "PMC123"))
        record = replace(self.record(), title="Калибровка Kristallprüfer 日本語")
        plan = self.project.identities.plan(record, self.source())
        self.project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)
        self.assertEqual(self.project.identities.observations(plan.paper_id)[0]["record"]["title"], record.title)

    def test_default_human_observation_does_not_grant_authority(self):
        paper = self.enroll()
        event = self.event(paper)
        self.project.reviews.apply(self.project.reviews.plan(event))
        state = self.project.reviews.membership(paper)
        self.assertTrue(state["reviewed"])
        self.assertEqual(state["state"], "not_reviewed")

    def test_explicit_human_authority_and_full_lineage(self):
        paper = self.enroll()
        event = self.event(paper, authority_state="human_authorized")
        event_id = self.project.reviews.apply(self.project.reviews.plan(event))
        state = self.project.reviews.membership(paper)
        self.assertEqual(state["state"], "included")
        self.assertEqual(state["decision_provenance"]["producer_id"], "reviewer_one")
        self.assertEqual(state["decision_provenance"]["evidence"][0]["source_sha256"], digest_bytes(BODY))
        self.assertEqual(state["current_event_id"], event_id)

    def test_non_human_producers_never_acquire_human_authority(self):
        paper = self.enroll()
        for producer in ("model", "parser", "deterministic", "imported"):
            with self.subTest(producer=producer), self.assertRaises(ContractError):
                self.project.reviews.plan(self.event(paper, producer_type=producer, authority_state="human_authorized"))

    def test_contract_enums_and_sql_constraints_do_not_drift(self):
        from corpustrail.curation.service import _STATE_SUFFICIENCY, _PRODUCER_TYPES, _AUTHORITY_STATES
        with connection(self.project.database_path) as db:
            sql = db.execute("SELECT sql FROM sqlite_master WHERE name='ct_review_events'").fetchone()[0]
        for field, expected in (("membership_state", set(_STATE_SUFFICIENCY)),
                                ("producer_type", _PRODUCER_TYPES), ("authority_state", _AUTHORITY_STATES)):
            matched = re.search(field + r" IN\s*\(([^)]+)\)", sql)
            self.assertIsNotNone(matched)
            self.assertEqual(set(re.findall(r"'([^']+)'", matched.group(1))), expected)
        self.assertEqual(set(self.project.status()["membership"]), set(_STATE_SUFFICIENCY) | {"not_reviewed"})

    def test_all_non_human_observations_can_coexist_without_authority(self):
        paper = self.enroll()
        for producer in ("model", "parser", "deterministic", "imported"):
            self.project.reviews.apply(self.project.reviews.plan(self.event(
                paper, producer_type=producer, producer_id="fixture_" + producer)))
        self.assertEqual(len(self.project.reviews.history(paper)), 4)
        self.assertEqual(self.project.reviews.membership(paper)["state"], "not_reviewed")

    def test_unapproved_human_cannot_set_membership(self):
        paper = self.enroll()
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(paper, producer_id="unapproved", authority_state="human_authorized"))

    def test_insufficient_and_unresolved_are_not_irrelevant(self):
        a, b = self.enroll("one"), self.enroll("two")
        for paper, state in ((a, "insufficient_evidence"), (b, "unresolved")):
            self.project.reviews.apply(self.project.reviews.plan(self.event(paper, state, authority_state="human_authorized")))
            self.assertEqual(self.project.reviews.membership(paper)["state"], state)
        self.assertEqual(self.project.status()["membership"]["excluded"], 0)
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(a, "excluded", sufficiency="insufficient"))

    def test_completed_decisions_require_rationale_and_evidence(self):
        paper = self.enroll()
        for change in ({"rationale": " "}, {"evidence": ()}, {"review_extent": "none"}, {"state": "not_reviewed"}):
            with self.assertRaises(ContractError):
                self.project.reviews.plan(self.event(paper, **change))

    def test_title_metadata_only_can_support_an_explicit_human_decision(self):
        paper = self.enroll(abstract=None)
        self.project.reviews.apply(self.project.reviews.plan(self.event(paper, authority_state="human_authorized")))
        self.assertEqual(self.project.reviews.membership(paper)["state"], "included")

    def test_abstract_review_requires_an_abstract_for_this_paper(self):
        paper = self.enroll()
        evidence = (EvidenceBasis("abstract", digest_bytes(BODY), "fixture://bibliography/v1", artifact_validity="verified"),)
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(paper, review_extent="abstract", evidence=evidence))
        second = self.enroll("abstract", "An invented sensor experiment.")
        self.project.reviews.apply(self.project.reviews.plan(self.event(second, review_extent="abstract", evidence=evidence)))

    def test_pending_wrong_and_unverified_documents_are_not_completed_evidence(self):
        paper = self.enroll()
        for validity in ("pending_identity", "wrong_document", "unverified", "unknown"):
            evidence = (EvidenceBasis("full_text", digest_bytes(BODY), "fixture://document", artifact_validity=validity),)
            with self.assertRaises(ContractError):
                self.project.reviews.plan(self.event(paper, review_extent="full_document", evidence=evidence))
            self.project.reviews.apply(self.project.reviews.plan(self.event(
                paper, "insufficient_evidence", evidence=evidence)))

    def test_metadata_is_not_full_document_review(self):
        paper = self.enroll()
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(paper, review_extent="full_document"))

    def test_evidence_hash_must_be_registered(self):
        paper = self.enroll()
        evidence = (EvidenceBasis("metadata", "sha256:" + "a" * 64, "fixture://missing", artifact_validity="verified"),)
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(paper, evidence=evidence))

    def test_conflicting_observations_coexist_without_overwriting_human_state(self):
        paper = self.enroll()
        human = self.event(paper, authority_state="human_authorized")
        self.project.reviews.apply(self.project.reviews.plan(human))
        model = self.event(paper, "excluded", producer_type="model", producer_id="fixture_model")
        self.project.reviews.apply(self.project.reviews.plan(model))
        self.assertEqual(len(self.project.reviews.history(paper)), 2)
        self.assertEqual(self.project.reviews.membership(paper)["state"], "included")

    def test_corrections_require_explicit_same_paper_supersession(self):
        paper = self.enroll()
        event = self.event(paper, authority_state="human_authorized")
        old_id = self.project.reviews.apply(self.project.reviews.plan(event))
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(paper, "excluded", authority_state="human_authorized"))
        corrected = self.event(paper, "excluded", authority_state="human_authorized", supersedes=old_id)
        new_id = self.project.reviews.apply(self.project.reviews.plan(corrected))
        self.assertEqual(self.project.reviews.history(paper)[0]["event_id"], old_id)
        self.assertEqual(self.project.reviews.membership(paper)["current_event_id"], new_id)
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(paper, producer_type="model", supersedes=new_id))

    def test_cross_paper_supersession_is_rejected(self):
        a, b = self.enroll("one"), self.enroll("two")
        event = self.event(a, authority_state="human_authorized")
        old_id = self.project.reviews.apply(self.project.reviews.plan(event))
        with self.assertRaises(ContractError):
            self.project.reviews.plan(self.event(b, authority_state="human_authorized", supersedes=old_id))

    def test_review_reruns_are_idempotent(self):
        paper = self.enroll()
        event = self.event(paper, authority_state="human_authorized")
        event_id = self.project.reviews.apply(self.project.reviews.plan(event))
        before = self.fingerprint()
        self.assertEqual(self.project.reviews.apply(self.project.reviews.plan(event)), event_id)
        self.assertEqual(self.fingerprint(), before)

    def test_corrupted_review_provenance_fails_closed_on_read(self):
        paper = self.enroll()
        self.project.reviews.apply(self.project.reviews.plan(self.event(paper)))
        with connection(self.project.database_path, write=True) as db:
            db.execute("DROP TRIGGER ct_review_no_update")
            db.execute("UPDATE ct_review_events SET content_sha256='corrupted'")
        with self.assertRaises(ContractError):
            self.project.reviews.membership(paper)

    def test_review_plan_rejects_concurrent_change(self):
        paper = self.enroll()
        plan = self.project.reviews.plan(self.event(paper, "included"))
        self.project.reviews.apply(self.project.reviews.plan(self.event(paper, "excluded")))
        with self.assertRaises(ContractError):
            self.project.reviews.apply(plan)

    def test_sql_immutability_and_authority_check(self):
        paper = self.enroll()
        self.project.reviews.apply(self.project.reviews.plan(self.event(paper)))
        for table in ("ct_project_identity", "ct_project_config_events", "ct_source_bindings",
                      "ct_enrollment_operations", "ct_paper_observations", "ct_review_events",
                      "paper_entities", "paper_identifiers"):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                with connection(self.project.database_path, write=True) as db:
                    db.execute(f"DELETE FROM {table}")
        with self.assertRaises(sqlite3.IntegrityError):
            with connection(self.project.database_path, write=True) as db:
                db.execute("UPDATE ct_review_events SET membership_state='excluded'")

    def test_no_historical_scientific_tables_are_populated(self):
        paper = self.enroll()
        self.project.reviews.apply(self.project.reviews.plan(self.event(paper, authority_state="human_authorized")))
        with connection(self.project.database_path) as db:
            for table in ("screening_events", "screening_approvals", "knowledge_assertions", "legacy_observations",
                          "taxonomies", "manifest_snapshots", "asreview_exports", "asreview_imports"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_low_priority_tail_is_not_a_filter_or_stopping_rule(self):
        papers = [self.enroll(str(x)) for x in range(4)]
        self.project.reviews.apply(self.project.reviews.plan(self.event(papers[0], "excluded", authority_state="human_authorized")))
        self.assertEqual(set(self.project.identities.papers()), set(papers))
        self.assertEqual(self.project.status()["membership"]["not_reviewed"], 3)


if __name__ == "__main__":
    unittest.main()
