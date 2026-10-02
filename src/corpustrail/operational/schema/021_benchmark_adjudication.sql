CREATE TABLE relevance_benchmark_adjudications (
    adjudication_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    source_benchmark_id TEXT NOT NULL REFERENCES relevance_benchmarks(benchmark_id),
    source_benchmark_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    output_benchmark_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    policy TEXT NOT NULL CHECK (policy = 'independent_human_review/v1'),
    label_count INTEGER NOT NULL CHECK (label_count > 0),
    adjudication_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE relevance_benchmark_adjudication_labels (
    adjudication_id TEXT NOT NULL REFERENCES relevance_benchmark_adjudications(adjudication_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    source_row_sha256 TEXT NOT NULL CHECK (source_row_sha256 GLOB 'sha256:*'),
    decision TEXT NOT NULL CHECK (decision IN ('include', 'exclude')),
    reviewed_at TEXT NOT NULL,
    reviewed_by TEXT NOT NULL,
    evidence_mode TEXT NOT NULL CHECK (evidence_mode IN ('metadata', 'full_text_available')),
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    evidence_refs_json TEXT NOT NULL CHECK (json_valid(evidence_refs_json)),
    PRIMARY KEY (adjudication_id, paper_id)
);

CREATE TABLE relevance_benchmark_derivations (
    output_benchmark_id TEXT PRIMARY KEY REFERENCES relevance_benchmarks(benchmark_id),
    source_benchmark_id TEXT NOT NULL REFERENCES relevance_benchmarks(benchmark_id),
    adjudication_id TEXT NOT NULL UNIQUE REFERENCES relevance_benchmark_adjudications(adjudication_id)
);

CREATE INDEX relevance_benchmark_adjudications_by_source
    ON relevance_benchmark_adjudications(source_benchmark_id, created_at);

CREATE TRIGGER relevance_benchmark_adjudications_immutable_update
BEFORE UPDATE ON relevance_benchmark_adjudications BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_adjudications are immutable');
END;
CREATE TRIGGER relevance_benchmark_adjudications_immutable_delete
BEFORE DELETE ON relevance_benchmark_adjudications BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_adjudications are immutable');
END;
CREATE TRIGGER relevance_benchmark_adjudication_labels_immutable_update
BEFORE UPDATE ON relevance_benchmark_adjudication_labels BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_adjudication_labels are immutable');
END;
CREATE TRIGGER relevance_benchmark_adjudication_labels_immutable_delete
BEFORE DELETE ON relevance_benchmark_adjudication_labels BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_adjudication_labels are immutable');
END;
CREATE TRIGGER relevance_benchmark_derivations_immutable_update
BEFORE UPDATE ON relevance_benchmark_derivations BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_derivations are immutable');
END;
CREATE TRIGGER relevance_benchmark_derivations_immutable_delete
BEFORE DELETE ON relevance_benchmark_derivations BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_derivations are immutable');
END;
