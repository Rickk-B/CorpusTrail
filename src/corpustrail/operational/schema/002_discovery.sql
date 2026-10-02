CREATE TABLE search_imports (
    import_id TEXT PRIMARY KEY,
    import_schema TEXT NOT NULL,
    all_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    selected_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    provenance_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    provider_run_id TEXT,
    imported_at TEXT NOT NULL,
    source_date TEXT,
    state TEXT NOT NULL CHECK (state IN ('complete', 'partial')),
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE search_queries (
    query_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES search_imports(import_id),
    provider_run_id TEXT,
    provider TEXT NOT NULL,
    executable_query TEXT NOT NULL,
    dialect_version TEXT NOT NULL,
    pages INTEGER,
    reported_total INTEGER,
    raw_hits INTEGER,
    stop_reason TEXT NOT NULL,
    next_cursor TEXT,
    error TEXT,
    UNIQUE(import_id, provider, executable_query)
);

CREATE INDEX search_queries_by_run
    ON search_queries(provider_run_id, provider);

CREATE TABLE legacy_candidate_records (
    candidate_record_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES search_imports(import_id),
    candidate_set TEXT NOT NULL CHECK (candidate_set IN ('all', 'selected')),
    candidate_key TEXT NOT NULL,
    doi TEXT,
    disposition TEXT,
    normalized_json TEXT NOT NULL CHECK (json_valid(normalized_json)),
    source_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    UNIQUE(import_id, candidate_set, candidate_key)
);

CREATE INDEX legacy_candidates_by_set
    ON legacy_candidate_records(import_id, candidate_set);

CREATE TABLE candidate_observations (
    observation_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    import_id TEXT NOT NULL REFERENCES search_imports(import_id),
    candidate_record_id TEXT REFERENCES legacy_candidate_records(candidate_record_id),
    search_run_id TEXT NOT NULL,
    query_id TEXT NOT NULL REFERENCES search_queries(query_id),
    provider TEXT NOT NULL,
    provider_record_id TEXT NOT NULL,
    rank INTEGER CHECK (rank IS NULL OR rank > 0),
    source_relation TEXT NOT NULL,
    source_paper_id TEXT REFERENCES paper_entities(paper_id),
    title TEXT NOT NULL,
    authors_json TEXT NOT NULL CHECK (json_valid(authors_json)),
    publication_year INTEGER,
    container_title TEXT NOT NULL,
    abstract TEXT,
    language TEXT,
    normalized_json TEXT NOT NULL CHECK (json_valid(normalized_json)),
    raw_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    observed_at TEXT NOT NULL,
    evidence_mode TEXT NOT NULL,
    UNIQUE(search_run_id, provider, query_id, provider_record_id, rank)
);

CREATE INDEX observations_by_provider_record
    ON candidate_observations(provider, provider_record_id);
CREATE INDEX observations_by_import
    ON candidate_observations(import_id);

CREATE TABLE observation_identifier_assertions (
    observation_id TEXT NOT NULL REFERENCES candidate_observations(observation_id),
    assertion_id TEXT NOT NULL UNIQUE REFERENCES identifier_assertions(assertion_id),
    PRIMARY KEY (observation_id, assertion_id)
);

CREATE INDEX observation_assertions_by_assertion
    ON observation_identifier_assertions(assertion_id);

CREATE TABLE observation_paper_links (
    link_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES candidate_observations(observation_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    state TEXT NOT NULL CHECK (state IN ('active', 'rejected', 'superseded')),
    method TEXT NOT NULL,
    authority TEXT NOT NULL CHECK (authority IN ('automatic_exact', 'reviewed')),
    created_at TEXT NOT NULL,
    reviewed_by TEXT
);

CREATE UNIQUE INDEX one_active_observation_link
    ON observation_paper_links(observation_id)
    WHERE state = 'active';

CREATE TRIGGER search_imports_immutable_update
BEFORE UPDATE ON search_imports BEGIN
    SELECT RAISE(ABORT, 'search_imports are immutable');
END;
CREATE TRIGGER search_imports_immutable_delete
BEFORE DELETE ON search_imports BEGIN
    SELECT RAISE(ABORT, 'search_imports are immutable');
END;
CREATE TRIGGER search_queries_immutable_update
BEFORE UPDATE ON search_queries BEGIN
    SELECT RAISE(ABORT, 'search_queries are immutable');
END;
CREATE TRIGGER search_queries_immutable_delete
BEFORE DELETE ON search_queries BEGIN
    SELECT RAISE(ABORT, 'search_queries are immutable');
END;
CREATE TRIGGER legacy_candidate_records_immutable_update
BEFORE UPDATE ON legacy_candidate_records BEGIN
    SELECT RAISE(ABORT, 'legacy_candidate_records are immutable');
END;
CREATE TRIGGER legacy_candidate_records_immutable_delete
BEFORE DELETE ON legacy_candidate_records BEGIN
    SELECT RAISE(ABORT, 'legacy_candidate_records are immutable');
END;
CREATE TRIGGER candidate_observations_immutable_update
BEFORE UPDATE ON candidate_observations BEGIN
    SELECT RAISE(ABORT, 'candidate_observations are immutable');
END;
CREATE TRIGGER candidate_observations_immutable_delete
BEFORE DELETE ON candidate_observations BEGIN
    SELECT RAISE(ABORT, 'candidate_observations are immutable');
END;
CREATE TRIGGER observation_identifier_assertions_immutable_update
BEFORE UPDATE ON observation_identifier_assertions BEGIN
    SELECT RAISE(ABORT, 'observation_identifier_assertions are immutable');
END;
CREATE TRIGGER observation_identifier_assertions_immutable_delete
BEFORE DELETE ON observation_identifier_assertions BEGIN
    SELECT RAISE(ABORT, 'observation_identifier_assertions are immutable');
END;
