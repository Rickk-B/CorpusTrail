"""Explicit project roots, immutable bootstrap and append-only configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path

from corpustrail._internal.database import (
    append_config, connection, create_database, latest_config, validate_database,
)
from corpustrail._internal.values import ContractError, canonical, confined, now, text, timestamp
from .config import ProjectConfig


BOOTSTRAP = "corpustrail.project.json"


class Project:
    """One explicit root/database per topic; no historical workspace fallback."""

    def __init__(self, root: Path, bootstrap: ProjectConfig):
        self.root = root.resolve()
        self._bootstrap = bootstrap

    @classmethod
    def create(cls, root: str | Path, config: ProjectConfig, *,
               created_by: str, created_at: str | None = None) -> Project:
        config.validate()
        if config.config_version != 1:
            raise ContractError("fresh projects begin at configuration version 1")
        text(created_by, "creation producer")
        created_at = created_at or now()
        timestamp(created_at)
        target = Path(root).absolute()
        if target.exists() or target.is_symlink():
            raise FileExistsError("project initialization refuses any existing target")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir(mode=0o700)  # Exclusive reservation; never rename over a directory.
        project = cls(target, config)
        create_database(project.database_path, config.to_dict(), created_at, created_by)
        body = (canonical(config.to_dict()) + "\n").encode("utf-8")
        # Bootstrap is written last; interrupted initialization is not an open project.
        with (target / BOOTSTRAP).open("xb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        return cls.open(target)

    @classmethod
    def open(cls, root: str | Path) -> Project:
        target = Path(root).resolve()
        body = (target / BOOTSTRAP).read_bytes()
        config = ProjectConfig.from_dict(json.loads(body))
        project = cls(target, config)
        with connection(project.database_path) as db:
            validate_database(db, body, config.project_id)
        project.config  # Validate latest configuration, without creating files.
        return project

    @classmethod
    def upgrade(cls, root, *, backup, created_at=None):
        """Explicit candidate-only schema upgrade; open/status never migrate."""
        from corpustrail._internal.database import upgrade_database
        target = Path(root).resolve()
        body = (target / BOOTSTRAP).read_bytes()
        config = ProjectConfig.from_dict(json.loads(body))
        project = cls(target, config)
        destination = confined(target, backup)
        if destination == project.database_path or destination == target / BOOTSTRAP:
            raise ContractError("backup cannot replace a live project artifact")
        upgrade_database(project.database_path, body, config.project_id, destination, created_at or now())
        return cls.open(target)

    @property
    def database_path(self) -> Path:
        return confined(self.root, self._bootstrap.database)

    @property
    def config(self) -> ProjectConfig:
        with connection(self.database_path) as db:
            _, raw = latest_config(db)
        config = ProjectConfig.from_dict(raw)
        for key in ("project_id", "data_directory", "database", "schema_version"):
            if getattr(config, key) != getattr(self._bootstrap, key):
                raise ContractError("immutable project identity/path changed")
        return config

    def configuration_history(self) -> list[dict]:
        with connection(self.database_path) as db:
            return [{"event_id": row["event_id"], **json.loads(row["payload_json"])} for row in
                    db.execute("SELECT * FROM ct_project_config_events ORDER BY sequence")]

    def configure(self, config: ProjectConfig, *, expected_event_id: str,
                  created_by: str, created_at: str | None = None) -> str:
        """Explicit revision-guarded append; never edit the original configuration."""
        config.validate()
        text(created_by, "configuration producer")
        created_at = created_at or now()
        timestamp(created_at)
        with connection(self.database_path, write=True) as db:
            prior_id, prior_raw = latest_config(db)
            prior = ProjectConfig.from_dict(prior_raw)
            if prior_id != expected_event_id:
                raise ContractError("stale configuration revision")
            if config.config_version != prior.config_version + 1:
                raise ContractError("configuration versions advance by exactly one")
            for key in ("project_id", "data_directory", "database", "schema_version"):
                if getattr(prior, key) != getattr(config, key):
                    raise ContractError("project identity and storage paths are immutable")
            if (prior.description, prior.review.scope, prior.review.policy_id) != (
                    config.description, config.review.scope, config.review.policy_id):
                if db.execute("SELECT 1 FROM ct_review_events WHERE authority_state='human_authorized' LIMIT 1").fetchone():
                    raise ContractError("scope changes after human authority require a future explicit policy migration")
            return append_config(db, config.to_dict(), prior_id, created_at, created_by)

    @property
    def identities(self):
        from corpustrail.identity import IdentityService
        return IdentityService(self)

    @property
    def reviews(self):
        from corpustrail.curation import ReviewService
        return ReviewService(self)

    @property
    def discovery(self):
        from corpustrail.discovery import DiscoveryService
        return DiscoveryService(self)

    @property
    def evidence(self):
        from corpustrail.evidence import EvidenceService
        return EvidenceService(self)

    @property
    def prioritization(self):
        from corpustrail.prioritization import PrioritizationService
        return PrioritizationService(self)

    @property
    def review_sessions(self):
        from corpustrail.curation.sessions import SessionService
        return SessionService(self)

    @property
    def knowledge(self):
        from corpustrail.knowledge import KnowledgeView
        return KnowledgeView(self)

    @property
    def knowledge_store(self):
        from corpustrail.knowledge import KnowledgeStore
        return KnowledgeStore(self)

    @property
    def asreview(self):
        from corpustrail.export.asreview import ExportService
        return ExportService(self)

    def status(self) -> dict:
        with connection(self.database_path) as db:
            config_id, raw = latest_config(db)
            ids = [row[0] for row in db.execute("SELECT paper_id FROM paper_entities ORDER BY paper_id")]
            checks = {"integrity": db.execute("PRAGMA integrity_check").fetchone()[0],
                      "foreign_key_errors": len(db.execute("PRAGMA foreign_key_check").fetchall()),
                      "migrations": db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]}
            pipeline = {"observations": db.execute("SELECT COUNT(*) FROM ct_pipeline_events WHERE kind='candidate_observation'").fetchone()[0],
                        "identity_issues": db.execute("SELECT COUNT(*) FROM ct_pipeline_events WHERE kind='identity_issue'").fetchone()[0],
                        "representations": db.execute("SELECT COUNT(*) FROM ct_pipeline_events WHERE kind='representation'").fetchone()[0]}
            from corpustrail.curation.service import _STATE_SUFFICIENCY, membership_in_connection
            counts = {key: 0 for key in (*_STATE_SUFFICIENCY, "not_reviewed")}
            for paper_id in ids:
                counts[membership_in_connection(db, paper_id)["state"]] += 1
            return {"project_id": raw["project_id"], "name": raw["name"],
                    "description": raw["description"], "schema_version": raw["schema_version"],
                    "config_event_id": config_id, "papers": len(ids), "membership": counts,
                    "review_question": "Does this paper belong in the broad scientific topic corpus: "
                                       + raw["name"] + "?", "database": self._bootstrap.database,
                    "checks": checks, "pipeline": pipeline, "pending_capabilities": []}
