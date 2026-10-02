CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL,
    code_sha256 TEXT NOT NULL
);

CREATE TABLE paper_entities (
    paper_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    identity_state TEXT NOT NULL
        CHECK (identity_state IN ('active', 'review', 'merged')),
    merged_into TEXT REFERENCES paper_entities(paper_id),
    CHECK (
        (identity_state = 'merged' AND merged_into IS NOT NULL) OR
        (identity_state != 'merged' AND merged_into IS NULL)
    )
);

CREATE INDEX paper_entities_merged_into ON paper_entities(merged_into);

CREATE TABLE raw_artifacts (
    sha256 TEXT PRIMARY KEY CHECK (sha256 GLOB 'sha256:*'),
    media_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE artifact_locations (
    relative_path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    artifact_kind TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    legacy_source INTEGER NOT NULL DEFAULT 0 CHECK (legacy_source IN (0, 1))
);

CREATE INDEX artifact_locations_by_hash ON artifact_locations(sha256);

CREATE TABLE manifest_snapshots (
    revision TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    manifest_sha256 TEXT NOT NULL CHECK (manifest_sha256 GLOB 'sha256:*')
);

CREATE TABLE identifier_assertions (
    assertion_id TEXT PRIMARY KEY,
    scheme TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_record_id TEXT,
    raw_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    asserted_at TEXT NOT NULL
);

CREATE INDEX identifier_assertion_lookup
    ON identifier_assertions(scheme, normalized_value);

CREATE TABLE paper_identifiers (
    identifier_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    scheme TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified', 'provisional', 'retired')),
    verification_method TEXT NOT NULL,
    supporting_assertion TEXT REFERENCES identifier_assertions(assertion_id),
    created_at TEXT NOT NULL,
    verified_at TEXT
);

CREATE UNIQUE INDEX verified_identifier_owner
    ON paper_identifiers(scheme, normalized_value)
    WHERE status = 'verified';

CREATE UNIQUE INDEX paper_identifier_once
    ON paper_identifiers(paper_id, scheme, normalized_value)
    WHERE status != 'retired';

CREATE TABLE identity_reviews (
    review_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('open', 'resolved', 'superseded')),
    reason_code TEXT NOT NULL,
    proposed_paper_ids_json TEXT NOT NULL CHECK (json_valid(proposed_paper_ids_json)),
    assertion_ids_json TEXT NOT NULL CHECK (json_valid(assertion_ids_json)),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    resolution_json TEXT CHECK (resolution_json IS NULL OR json_valid(resolution_json))
);

CREATE TRIGGER raw_artifacts_immutable_update
BEFORE UPDATE ON raw_artifacts BEGIN
    SELECT RAISE(ABORT, 'raw_artifacts are immutable');
END;
CREATE TRIGGER raw_artifacts_immutable_delete
BEFORE DELETE ON raw_artifacts BEGIN
    SELECT RAISE(ABORT, 'raw_artifacts are immutable');
END;
CREATE TRIGGER artifact_locations_immutable_update
BEFORE UPDATE ON artifact_locations BEGIN
    SELECT RAISE(ABORT, 'artifact_locations are immutable');
END;
CREATE TRIGGER artifact_locations_immutable_delete
BEFORE DELETE ON artifact_locations BEGIN
    SELECT RAISE(ABORT, 'artifact_locations are immutable');
END;
CREATE TRIGGER manifest_snapshots_immutable_update
BEFORE UPDATE ON manifest_snapshots BEGIN
    SELECT RAISE(ABORT, 'manifest_snapshots are immutable');
END;
CREATE TRIGGER manifest_snapshots_immutable_delete
BEFORE DELETE ON manifest_snapshots BEGIN
    SELECT RAISE(ABORT, 'manifest_snapshots are immutable');
END;
CREATE TRIGGER identifier_assertions_immutable_update
BEFORE UPDATE ON identifier_assertions BEGIN
    SELECT RAISE(ABORT, 'identifier_assertions are immutable');
END;
CREATE TRIGGER identifier_assertions_immutable_delete
BEFORE DELETE ON identifier_assertions BEGIN
    SELECT RAISE(ABORT, 'identifier_assertions are immutable');
END;
