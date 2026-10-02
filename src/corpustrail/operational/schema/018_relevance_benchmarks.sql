CREATE TABLE relevance_benchmarks (
    benchmark_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    input_manifest_revision TEXT NOT NULL REFERENCES manifest_snapshots(revision),
    selection_policy TEXT NOT NULL,
    intended_size INTEGER NOT NULL CHECK (intended_size BETWEEN 50 AND 100),
    human_label_count INTEGER NOT NULL CHECK (
        human_label_count >= 0 AND human_label_count <= intended_size
    ),
    benchmark_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE relevance_benchmark_items (
    benchmark_id TEXT NOT NULL REFERENCES relevance_benchmarks(benchmark_id),
    position INTEGER NOT NULL CHECK (position > 0),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    expected_decision TEXT NOT NULL CHECK (expected_decision IN ('include', 'exclude')),
    label_authority TEXT NOT NULL CHECK (
        label_authority IN ('manifest_curated_snapshot', 'human_review')
    ),
    evidence_mode TEXT NOT NULL CHECK (
        evidence_mode IN ('metadata', 'full_text_available')
    ),
    strata_json TEXT NOT NULL CHECK (json_valid(strata_json)),
    source_row_sha256 TEXT NOT NULL CHECK (source_row_sha256 GLOB 'sha256:*'),
    PRIMARY KEY (benchmark_id, paper_id),
    UNIQUE (benchmark_id, position)
);

CREATE INDEX relevance_benchmark_items_by_paper
    ON relevance_benchmark_items(paper_id, benchmark_id);

CREATE TRIGGER relevance_benchmarks_immutable_update
BEFORE UPDATE ON relevance_benchmarks BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmarks are immutable');
END;
CREATE TRIGGER relevance_benchmarks_immutable_delete
BEFORE DELETE ON relevance_benchmarks BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmarks are immutable');
END;
CREATE TRIGGER relevance_benchmark_items_immutable_update
BEFORE UPDATE ON relevance_benchmark_items BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_items are immutable');
END;
CREATE TRIGGER relevance_benchmark_items_immutable_delete
BEFORE DELETE ON relevance_benchmark_items BEGIN
    SELECT RAISE(ABORT, 'relevance_benchmark_items are immutable');
END;
