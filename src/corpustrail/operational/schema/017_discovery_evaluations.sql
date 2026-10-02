CREATE TABLE discovery_comparison_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    comparison_run_id TEXT NOT NULL REFERENCES discovery_comparison_runs(run_id),
    evaluated_at TEXT NOT NULL,
    evaluated_by TEXT NOT NULL,
    labels_source_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    labels_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    report_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    experiment_ids_json TEXT NOT NULL CHECK (json_valid(experiment_ids_json))
);

CREATE INDEX discovery_evaluations_by_run
    ON discovery_comparison_evaluations(comparison_run_id, evaluated_at);

CREATE TRIGGER discovery_comparison_evaluations_immutable_update
BEFORE UPDATE ON discovery_comparison_evaluations BEGIN
    SELECT RAISE(ABORT, 'discovery_comparison_evaluations are immutable');
END;
CREATE TRIGGER discovery_comparison_evaluations_immutable_delete
BEFORE DELETE ON discovery_comparison_evaluations BEGIN
    SELECT RAISE(ABORT, 'discovery_comparison_evaluations are immutable');
END;
