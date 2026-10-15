-- Explicit Checkpoint 6 upgrade. Candidate populations confer no corpus authority.
CREATE TABLE ct_population_versions (
    sequence INTEGER PRIMARY KEY,
    version_id TEXT NOT NULL UNIQUE,
    population_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version > 0),
    request_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    UNIQUE(population_id,version)
);
CREATE TABLE ct_population_members (
    version_id TEXT NOT NULL REFERENCES ct_population_versions(version_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    identity_json TEXT NOT NULL,
    identity_sha256 TEXT NOT NULL,
    PRIMARY KEY(version_id,paper_id)
);
CREATE TABLE ct_population_lineage (
    version_id TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    origin_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(version_id,paper_id,origin_key),
    FOREIGN KEY(version_id,paper_id) REFERENCES ct_population_members(version_id,paper_id)
);
CREATE TABLE ct_population_issues (
    version_id TEXT NOT NULL REFERENCES ct_population_versions(version_id),
    issue_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(version_id,issue_key)
);
CREATE TABLE ct_population_parents (
    version_id TEXT NOT NULL REFERENCES ct_population_versions(version_id),
    parent_id TEXT NOT NULL REFERENCES ct_population_versions(version_id),
    PRIMARY KEY(version_id,parent_id)
);
CREATE TABLE ct_population_review_links (
    session_id TEXT PRIMARY KEY REFERENCES ct_review_sessions(session_id),
    version_id TEXT NOT NULL REFERENCES ct_population_versions(version_id),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL
);
CREATE INDEX ct_population_family ON ct_population_versions(population_id,version);
CREATE INDEX ct_population_paper ON ct_population_members(paper_id,version_id);
CREATE TRIGGER ct_population_versions_no_update BEFORE UPDATE ON ct_population_versions BEGIN SELECT RAISE(ABORT,'immutable population version'); END;
CREATE TRIGGER ct_population_versions_no_delete BEFORE DELETE ON ct_population_versions BEGIN SELECT RAISE(ABORT,'immutable population version'); END;
CREATE TRIGGER ct_population_members_no_update BEFORE UPDATE ON ct_population_members BEGIN SELECT RAISE(ABORT,'immutable candidate membership'); END;
CREATE TRIGGER ct_population_members_no_delete BEFORE DELETE ON ct_population_members BEGIN SELECT RAISE(ABORT,'immutable candidate membership'); END;
CREATE TRIGGER ct_population_lineage_no_update BEFORE UPDATE ON ct_population_lineage BEGIN SELECT RAISE(ABORT,'immutable source lineage'); END;
CREATE TRIGGER ct_population_lineage_no_delete BEFORE DELETE ON ct_population_lineage BEGIN SELECT RAISE(ABORT,'immutable source lineage'); END;
CREATE TRIGGER ct_population_issues_no_update BEFORE UPDATE ON ct_population_issues BEGIN SELECT RAISE(ABORT,'immutable population issue'); END;
CREATE TRIGGER ct_population_issues_no_delete BEFORE DELETE ON ct_population_issues BEGIN SELECT RAISE(ABORT,'immutable population issue'); END;
CREATE TRIGGER ct_population_parents_no_update BEFORE UPDATE ON ct_population_parents BEGIN SELECT RAISE(ABORT,'immutable population parent'); END;
CREATE TRIGGER ct_population_parents_no_delete BEFORE DELETE ON ct_population_parents BEGIN SELECT RAISE(ABORT,'immutable population parent'); END;
CREATE TRIGGER ct_population_review_links_no_update BEFORE UPDATE ON ct_population_review_links BEGIN SELECT RAISE(ABORT,'immutable review population link'); END;
CREATE TRIGGER ct_population_review_links_no_delete BEFORE DELETE ON ct_population_review_links BEGIN SELECT RAISE(ABORT,'immutable review population link'); END;
