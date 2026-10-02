CREATE TABLE screening_experiments (
    experiment_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    method_family TEXT NOT NULL CHECK (method_family IN (
        'deterministic_rule', 'simple_baseline', 'staged_llm',
        'candidate_cascade', 'asreview'
    )),
    method_name TEXT NOT NULL,
    method_version TEXT NOT NULL,
    method_config_json TEXT NOT NULL CHECK (json_valid(method_config_json)),
    candidate_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    candidate_population_sha256 TEXT NOT NULL CHECK (
        candidate_population_sha256 GLOB 'sha256:*'
    ),
    prediction_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    benchmark_id TEXT REFERENCES relevance_benchmarks(benchmark_id),
    evidence_policy_id TEXT REFERENCES screening_policies(policy_id),
    mode TEXT NOT NULL CHECK (mode IN ('offline', 'shadow', 'prospective')),
    decision TEXT NOT NULL CHECK (
        decision IN ('pending', 'shadow', 'adopt', 'modify', 'retire')
    ),
    decision_rationale TEXT NOT NULL,
    known_failure_modes_json TEXT NOT NULL CHECK (
        json_valid(known_failure_modes_json)
    ),
    cost_summary_json TEXT NOT NULL CHECK (json_valid(cost_summary_json)),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    definition_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE screening_predictions (
    experiment_id TEXT NOT NULL REFERENCES screening_experiments(experiment_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    score REAL,
    predicted_assessment TEXT NOT NULL CHECK (
        predicted_assessment IN ('include', 'exclude', 'indeterminate', 'unranked')
    ),
    uncertainty REAL CHECK (
        uncertainty IS NULL OR (uncertainty >= 0.0 AND uncertainty <= 1.0)
    ),
    evidence_representation TEXT NOT NULL CHECK (
        evidence_representation IN (
            'none', 'metadata', 'abstract', 'citation_context',
            'structured_text', 'pdf_text', 'ocr_text', 'image_only'
        )
    ),
    rank INTEGER CHECK (rank IS NULL OR rank > 0),
    cost_json TEXT NOT NULL CHECK (json_valid(cost_json)),
    output_sha256 TEXT NOT NULL CHECK (output_sha256 GLOB 'sha256:*'),
    PRIMARY KEY (experiment_id, paper_id),
    UNIQUE (experiment_id, rank)
);

CREATE INDEX screening_experiments_by_benchmark
    ON screening_experiments(benchmark_id, method_family, mode);
CREATE INDEX screening_predictions_by_paper
    ON screening_predictions(paper_id, experiment_id);

CREATE TRIGGER screening_experiments_immutable_update
BEFORE UPDATE ON screening_experiments BEGIN
    SELECT RAISE(ABORT, 'screening_experiments are immutable');
END;
CREATE TRIGGER screening_experiments_immutable_delete
BEFORE DELETE ON screening_experiments BEGIN
    SELECT RAISE(ABORT, 'screening_experiments are immutable');
END;
CREATE TRIGGER screening_predictions_immutable_update
BEFORE UPDATE ON screening_predictions BEGIN
    SELECT RAISE(ABORT, 'screening_predictions are immutable');
END;
CREATE TRIGGER screening_predictions_immutable_delete
BEFORE DELETE ON screening_predictions BEGIN
    SELECT RAISE(ABORT, 'screening_predictions are immutable');
END;
