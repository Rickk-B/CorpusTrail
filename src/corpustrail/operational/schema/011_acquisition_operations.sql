CREATE TABLE acquisition_operations (
    operation_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    request_id TEXT NOT NULL REFERENCES resolution_requests(request_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    resolution_location_id TEXT NOT NULL REFERENCES resolution_locations(location_id),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    location_revision TEXT NOT NULL,
    plan_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    attempt_id TEXT NOT NULL UNIQUE
);

ALTER TABLE acquisition_attempts
    ADD COLUMN acquisition_operation_id TEXT REFERENCES acquisition_operations(operation_id);
ALTER TABLE acquisition_attempts
    ADD COLUMN resolution_location_id TEXT REFERENCES resolution_locations(location_id);

CREATE TABLE document_acquisition_reuses (
    attempt_id TEXT PRIMARY KEY REFERENCES acquisition_attempts(attempt_id),
    document_artifact_id TEXT NOT NULL
        REFERENCES document_artifacts(document_artifact_id),
    linked_at TEXT NOT NULL,
    reason TEXT NOT NULL
);

CREATE INDEX acquisition_operations_by_location
    ON acquisition_operations(resolution_location_id, applied_at);

CREATE TRIGGER acquisition_operations_immutable_update
BEFORE UPDATE ON acquisition_operations BEGIN
    SELECT RAISE(ABORT, 'acquisition_operations are immutable');
END;
CREATE TRIGGER acquisition_operations_immutable_delete
BEFORE DELETE ON acquisition_operations BEGIN
    SELECT RAISE(ABORT, 'acquisition_operations are immutable');
END;
CREATE TRIGGER document_acquisition_reuses_immutable_update
BEFORE UPDATE ON document_acquisition_reuses BEGIN
    SELECT RAISE(ABORT, 'document_acquisition_reuses are immutable');
END;
CREATE TRIGGER document_acquisition_reuses_immutable_delete
BEFORE DELETE ON document_acquisition_reuses BEGIN
    SELECT RAISE(ABORT, 'document_acquisition_reuses are immutable');
END;
