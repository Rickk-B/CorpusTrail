CREATE TABLE document_identity_assessments (
    assessment_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    document_artifact_id TEXT NOT NULL REFERENCES document_artifacts(document_artifact_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    document_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    previous_assessment_id TEXT REFERENCES document_identity_assessments(assessment_id),
    decision TEXT NOT NULL CHECK (decision IN ('verified', 'rejected', 'pending')),
    authority TEXT NOT NULL CHECK (
        authority IN ('human_review', 'deterministic_exact_identifier')
    ),
    method TEXT NOT NULL,
    assessed_at TEXT NOT NULL,
    assessed_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    recorded_at TEXT NOT NULL,
    assessment_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE UNIQUE INDEX document_identity_one_successor
    ON document_identity_assessments(previous_assessment_id)
    WHERE previous_assessment_id IS NOT NULL;
CREATE INDEX document_identity_assessments_by_document
    ON document_identity_assessments(document_artifact_id, recorded_at);

CREATE TABLE location_rights_assessments (
    assessment_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    resolution_location_id TEXT NOT NULL REFERENCES resolution_locations(location_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    location_revision TEXT NOT NULL,
    previous_assessment_id TEXT REFERENCES location_rights_assessments(assessment_id),
    status TEXT NOT NULL CHECK (status IN ('verified', 'rejected', 'pending')),
    basis TEXT NOT NULL,
    license TEXT,
    authority TEXT NOT NULL CHECK (
        authority IN ('human_review', 'deterministic_provider_evidence')
    ),
    method TEXT NOT NULL,
    assessed_at TEXT NOT NULL,
    assessed_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    recorded_at TEXT NOT NULL,
    assessment_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE UNIQUE INDEX location_rights_one_successor
    ON location_rights_assessments(previous_assessment_id)
    WHERE previous_assessment_id IS NOT NULL;
CREATE INDEX location_rights_assessments_by_location
    ON location_rights_assessments(resolution_location_id, recorded_at);

ALTER TABLE document_selection_events
    ADD COLUMN document_identity_revision TEXT NOT NULL DEFAULT 'legacy:document-artifact';
ALTER TABLE parse_requests
    ADD COLUMN document_identity_revision TEXT NOT NULL DEFAULT 'legacy:document-artifact';

CREATE TRIGGER document_identity_assessments_immutable_update
BEFORE UPDATE ON document_identity_assessments BEGIN
    SELECT RAISE(ABORT, 'document_identity_assessments are immutable');
END;
CREATE TRIGGER document_identity_assessments_immutable_delete
BEFORE DELETE ON document_identity_assessments BEGIN
    SELECT RAISE(ABORT, 'document_identity_assessments are immutable');
END;
CREATE TRIGGER location_rights_assessments_immutable_update
BEFORE UPDATE ON location_rights_assessments BEGIN
    SELECT RAISE(ABORT, 'location_rights_assessments are immutable');
END;
CREATE TRIGGER location_rights_assessments_immutable_delete
BEFORE DELETE ON location_rights_assessments BEGIN
    SELECT RAISE(ABORT, 'location_rights_assessments are immutable');
END;
