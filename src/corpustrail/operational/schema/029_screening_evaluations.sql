CREATE TABLE screening_experiment_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    experiment_id TEXT NOT NULL REFERENCES screening_experiments(experiment_id),
    benchmark_id TEXT NOT NULL REFERENCES relevance_benchmarks(benchmark_id),
    benchmark_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    label_policy TEXT NOT NULL CHECK (label_policy = 'independent_human_only'),
    evaluation_partition TEXT NOT NULL CHECK (
        evaluation_partition IN ('development', 'evaluation', 'prospective_holdout')
    ),
    evaluated_at TEXT NOT NULL,
    evaluated_by TEXT NOT NULL,
    report_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE screening_metrics (
    evaluation_id TEXT NOT NULL REFERENCES screening_experiment_evaluations(evaluation_id),
    metric_name TEXT NOT NULL,
    subgroup_dimension TEXT NOT NULL,
    subgroup_value TEXT NOT NULL,
    value REAL NOT NULL,
    numerator INTEGER,
    denominator INTEGER,
    PRIMARY KEY (
        evaluation_id, metric_name, subgroup_dimension, subgroup_value
    )
);

CREATE INDEX screening_evaluations_by_experiment
    ON screening_experiment_evaluations(experiment_id, benchmark_id);

CREATE TRIGGER screening_experiment_evaluations_immutable_update
BEFORE UPDATE ON screening_experiment_evaluations BEGIN
    SELECT RAISE(ABORT, 'screening_experiment_evaluations are immutable');
END;
CREATE TRIGGER screening_experiment_evaluations_immutable_delete
BEFORE DELETE ON screening_experiment_evaluations BEGIN
    SELECT RAISE(ABORT, 'screening_experiment_evaluations are immutable');
END;
CREATE TRIGGER screening_metrics_immutable_update
BEFORE UPDATE ON screening_metrics BEGIN
    SELECT RAISE(ABORT, 'screening_metrics are immutable');
END;
CREATE TRIGGER screening_metrics_immutable_delete
BEFORE DELETE ON screening_metrics BEGIN
    SELECT RAISE(ABORT, 'screening_metrics are immutable');
END;
