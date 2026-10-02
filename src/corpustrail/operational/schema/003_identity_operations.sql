CREATE TABLE identity_operations (
    operation_id TEXT PRIMARY KEY,
    plan_schema TEXT NOT NULL,
    plan_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    base_manifest_revision TEXT NOT NULL REFERENCES manifest_snapshots(revision),
    policy_sha256 TEXT NOT NULL CHECK (policy_sha256 GLOB 'sha256:*'),
    applied_at TEXT NOT NULL,
    result_json TEXT NOT NULL CHECK (json_valid(result_json))
);

CREATE TABLE identity_operation_decisions (
    operation_id TEXT NOT NULL REFERENCES identity_operations(operation_id)
        DEFERRABLE INITIALLY DEFERRED,
    observation_id TEXT NOT NULL REFERENCES candidate_observations(observation_id),
    outcome TEXT NOT NULL
        CHECK (outcome IN ('link', 'review', 'unresolved', 'already_linked')),
    paper_id TEXT REFERENCES paper_entities(paper_id),
    decision_json TEXT NOT NULL CHECK (json_valid(decision_json)),
    PRIMARY KEY (operation_id, observation_id)
);

CREATE TRIGGER identity_operations_immutable_update
BEFORE UPDATE ON identity_operations BEGIN
    SELECT RAISE(ABORT, 'identity_operations are immutable');
END;
CREATE TRIGGER identity_operations_immutable_delete
BEFORE DELETE ON identity_operations BEGIN
    SELECT RAISE(ABORT, 'identity_operations are immutable');
END;
CREATE TRIGGER identity_operation_decisions_immutable_update
BEFORE UPDATE ON identity_operation_decisions BEGIN
    SELECT RAISE(ABORT, 'identity_operation_decisions are immutable');
END;
CREATE TRIGGER identity_operation_decisions_immutable_delete
BEFORE DELETE ON identity_operation_decisions BEGIN
    SELECT RAISE(ABORT, 'identity_operation_decisions are immutable');
END;
