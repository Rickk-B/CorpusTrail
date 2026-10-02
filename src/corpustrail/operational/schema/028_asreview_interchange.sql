CREATE TABLE asreview_exports (
    export_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    benchmark_id TEXT NOT NULL REFERENCES relevance_benchmarks(benchmark_id),
    benchmark_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    screening_policy_id TEXT NOT NULL REFERENCES screening_policies(policy_id),
    label_policy TEXT NOT NULL CHECK (label_policy = 'none'),
    asreview_version_spec TEXT NOT NULL,
    candidate_population_sha256 TEXT NOT NULL CHECK (
        candidate_population_sha256 GLOB 'sha256:*'
    ),
    row_count INTEGER NOT NULL CHECK (row_count > 0),
    dataset_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    sidecar_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);

CREATE TABLE asreview_imports (
    import_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    export_id TEXT NOT NULL REFERENCES asreview_exports(export_id),
    asreview_version TEXT NOT NULL,
    project_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    results_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    import_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    labelled_count INTEGER NOT NULL CHECK (labelled_count >= 0),
    unlabelled_count INTEGER NOT NULL CHECK (unlabelled_count >= 0),
    imported_at TEXT NOT NULL,
    imported_by TEXT NOT NULL,
    CHECK (labelled_count + unlabelled_count > 0)
);

CREATE TABLE asreview_import_records (
    import_id TEXT NOT NULL REFERENCES asreview_imports(import_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    result_position INTEGER NOT NULL CHECK (result_position > 0),
    label TEXT CHECK (label IS NULL OR label IN ('include', 'exclude')),
    decided_at TEXT,
    note TEXT,
    reviewer_name TEXT,
    reviewer_email TEXT,
    screening_event_id TEXT REFERENCES screening_events(screening_event_id),
    PRIMARY KEY (import_id, paper_id),
    UNIQUE (import_id, result_position),
    CHECK (screening_event_id IS NULL)
);

CREATE INDEX asreview_import_records_by_paper
    ON asreview_import_records(paper_id, import_id);

CREATE TRIGGER asreview_exports_immutable_update
BEFORE UPDATE ON asreview_exports BEGIN
    SELECT RAISE(ABORT, 'asreview_exports are immutable');
END;
CREATE TRIGGER asreview_exports_immutable_delete
BEFORE DELETE ON asreview_exports BEGIN
    SELECT RAISE(ABORT, 'asreview_exports are immutable');
END;
CREATE TRIGGER asreview_imports_immutable_update
BEFORE UPDATE ON asreview_imports BEGIN
    SELECT RAISE(ABORT, 'asreview_imports are immutable');
END;
CREATE TRIGGER asreview_imports_immutable_delete
BEFORE DELETE ON asreview_imports BEGIN
    SELECT RAISE(ABORT, 'asreview_imports are immutable');
END;
CREATE TRIGGER asreview_import_records_immutable_update
BEFORE UPDATE ON asreview_import_records BEGIN
    SELECT RAISE(ABORT, 'asreview_import_records are immutable');
END;
CREATE TRIGGER asreview_import_records_immutable_delete
BEFORE DELETE ON asreview_import_records BEGIN
    SELECT RAISE(ABORT, 'asreview_import_records are immutable');
END;
