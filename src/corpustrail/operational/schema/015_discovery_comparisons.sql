CREATE TABLE discovery_comparison_plans (
    plan_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    input_manifest_revision TEXT NOT NULL REFERENCES manifest_snapshots(revision),
    policy_version TEXT NOT NULL,
    methods_json TEXT NOT NULL CHECK (json_valid(methods_json)),
    seed_clusters_json TEXT NOT NULL CHECK (json_valid(seed_clusters_json)),
    baseline_import_ids_json TEXT NOT NULL CHECK (json_valid(baseline_import_ids_json)),
    known_identifiers_json TEXT NOT NULL CHECK (json_valid(known_identifiers_json)),
    max_results_per_method_cluster INTEGER NOT NULL
        CHECK (max_results_per_method_cluster BETWEEN 1 AND 500),
    max_api_calls INTEGER NOT NULL CHECK (max_api_calls > 0),
    max_pages_per_query INTEGER NOT NULL CHECK (max_pages_per_query > 0),
    stop_rule_json TEXT NOT NULL CHECK (json_valid(stop_rule_json)),
    plan_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE INDEX discovery_comparison_plans_by_manifest
    ON discovery_comparison_plans(input_manifest_revision, created_at);

CREATE TRIGGER discovery_comparison_plans_immutable_update
BEFORE UPDATE ON discovery_comparison_plans BEGIN
    SELECT RAISE(ABORT, 'discovery_comparison_plans are immutable');
END;
CREATE TRIGGER discovery_comparison_plans_immutable_delete
BEFORE DELETE ON discovery_comparison_plans BEGIN
    SELECT RAISE(ABORT, 'discovery_comparison_plans are immutable');
END;
