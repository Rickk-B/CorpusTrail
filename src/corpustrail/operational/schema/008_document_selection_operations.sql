CREATE TABLE document_selection_operations (
    operation_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    input_revision TEXT NOT NULL,
    plan_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

ALTER TABLE document_selection_events
    ADD COLUMN operation_id TEXT
    REFERENCES document_selection_operations(operation_id);

CREATE INDEX document_selection_events_by_operation
    ON document_selection_events(operation_id, purpose);

CREATE TRIGGER document_selection_operations_immutable_update
BEFORE UPDATE ON document_selection_operations BEGIN
    SELECT RAISE(ABORT, 'document_selection_operations are immutable');
END;
CREATE TRIGGER document_selection_operations_immutable_delete
BEFORE DELETE ON document_selection_operations BEGIN
    SELECT RAISE(ABORT, 'document_selection_operations are immutable');
END;
