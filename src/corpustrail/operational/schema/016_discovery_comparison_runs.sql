CREATE TABLE discovery_comparison_runs (
    run_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES discovery_comparison_plans(plan_id),
    started_at TEXT NOT NULL
);

CREATE TABLE discovery_method_runs (
    method_run_id TEXT PRIMARY KEY,
    comparison_run_id TEXT NOT NULL REFERENCES discovery_comparison_runs(run_id),
    method TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('complete', 'partial', 'failed')),
    stop_reasons_json TEXT NOT NULL CHECK (json_valid(stop_reasons_json)),
    candidate_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    search_import_id TEXT REFERENCES search_imports(import_id),
    candidates_returned INTEGER NOT NULL CHECK (candidates_returned >= 0),
    api_calls INTEGER NOT NULL CHECK (api_calls >= 0),
    UNIQUE (comparison_run_id, method)
);

CREATE TABLE discovery_api_attempts (
    attempt_id TEXT PRIMARY KEY,
    method_run_id TEXT NOT NULL REFERENCES discovery_method_runs(method_run_id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    cluster TEXT NOT NULL,
    provider TEXT NOT NULL,
    http_method TEXT NOT NULL CHECK (http_method IN ('GET', 'POST')),
    endpoint TEXT NOT NULL,
    request_json TEXT NOT NULL CHECK (json_valid(request_json)),
    outcome TEXT NOT NULL CHECK (outcome IN (
        'success', 'not_found', 'retryable_error', 'permanent_error',
        'malformed_response'
    )),
    http_status INTEGER,
    response_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    returned_count INTEGER NOT NULL CHECK (returned_count >= 0),
    error TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    UNIQUE (method_run_id, sequence)
);

CREATE TABLE discovery_method_candidates (
    method_run_id TEXT NOT NULL REFERENCES discovery_method_runs(method_run_id),
    candidate_key TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank > 0),
    previously_known INTEGER NOT NULL CHECK (previously_known IN (0, 1)),
    known_paper_ids_json TEXT NOT NULL CHECK (json_valid(known_paper_ids_json)),
    identifiers_json TEXT NOT NULL CHECK (json_valid(identifiers_json)),
    clusters_json TEXT NOT NULL CHECK (json_valid(clusters_json)),
    PRIMARY KEY (method_run_id, candidate_key),
    UNIQUE (method_run_id, rank)
);

CREATE INDEX discovery_method_runs_by_comparison
    ON discovery_method_runs(comparison_run_id, method);
CREATE INDEX discovery_candidates_by_key
    ON discovery_method_candidates(candidate_key, previously_known);
CREATE INDEX discovery_attempts_by_provider
    ON discovery_api_attempts(provider, outcome, attempted_at);

CREATE TRIGGER discovery_comparison_runs_immutable_update
BEFORE UPDATE ON discovery_comparison_runs BEGIN
    SELECT RAISE(ABORT, 'discovery_comparison_runs are immutable');
END;
CREATE TRIGGER discovery_comparison_runs_immutable_delete
BEFORE DELETE ON discovery_comparison_runs BEGIN
    SELECT RAISE(ABORT, 'discovery_comparison_runs are immutable');
END;
CREATE TRIGGER discovery_method_runs_immutable_update
BEFORE UPDATE ON discovery_method_runs BEGIN
    SELECT RAISE(ABORT, 'discovery_method_runs are immutable');
END;
CREATE TRIGGER discovery_method_runs_immutable_delete
BEFORE DELETE ON discovery_method_runs BEGIN
    SELECT RAISE(ABORT, 'discovery_method_runs are immutable');
END;
CREATE TRIGGER discovery_api_attempts_immutable_update
BEFORE UPDATE ON discovery_api_attempts BEGIN
    SELECT RAISE(ABORT, 'discovery_api_attempts are immutable');
END;
CREATE TRIGGER discovery_api_attempts_immutable_delete
BEFORE DELETE ON discovery_api_attempts BEGIN
    SELECT RAISE(ABORT, 'discovery_api_attempts are immutable');
END;
CREATE TRIGGER discovery_method_candidates_immutable_update
BEFORE UPDATE ON discovery_method_candidates BEGIN
    SELECT RAISE(ABORT, 'discovery_method_candidates are immutable');
END;
CREATE TRIGGER discovery_method_candidates_immutable_delete
BEFORE DELETE ON discovery_method_candidates BEGIN
    SELECT RAISE(ABORT, 'discovery_method_candidates are immutable');
END;
