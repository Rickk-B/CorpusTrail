CREATE TABLE resolution_requests (
    request_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    requested_at TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    base_manifest_revision TEXT NOT NULL REFERENCES manifest_snapshots(revision),
    provider_order_json TEXT NOT NULL CHECK (json_valid(provider_order_json)),
    acceptable_representations_json TEXT NOT NULL
        CHECK (json_valid(acceptable_representations_json)),
    identifiers_json TEXT NOT NULL CHECK (json_valid(identifiers_json)),
    legitimate_open_access_only INTEGER NOT NULL CHECK (legitimate_open_access_only = 1),
    request_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE acquisition_attempts (
    attempt_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    request_id TEXT NOT NULL REFERENCES resolution_requests(request_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    provider TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN (
        'acquired', 'not_found', 'retryable_error', 'permanent_error',
        'requires_user_action', 'rejected_policy', 'identity_mismatch'
    )),
    source_url TEXT,
    http_status INTEGER,
    license TEXT,
    oa_evidence_json TEXT NOT NULL CHECK (json_valid(oa_evidence_json)),
    response_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    error_code TEXT,
    error_detail TEXT,
    attempt_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE INDEX acquisition_attempts_by_request
    ON acquisition_attempts(request_id, provider, completed_at);

CREATE TABLE document_artifacts (
    document_artifact_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    acquisition_attempt_id TEXT NOT NULL UNIQUE REFERENCES acquisition_attempts(attempt_id),
    artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    representation_kind TEXT NOT NULL,
    version_kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    source_provider TEXT NOT NULL,
    source_url TEXT,
    retrieved_at TEXT NOT NULL,
    license TEXT,
    identity_status TEXT NOT NULL CHECK (identity_status IN ('verified', 'pending', 'rejected')),
    identity_evidence_json TEXT NOT NULL CHECK (json_valid(identity_evidence_json)),
    document_metadata_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    UNIQUE (paper_id, artifact_sha256, representation_kind)
);

CREATE INDEX document_artifacts_by_paper
    ON document_artifacts(paper_id, identity_status, representation_kind);

CREATE TABLE document_selection_events (
    selection_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    purpose TEXT NOT NULL CHECK (purpose IN (
        'best_readable', 'best_structured', 'best_citation', 'best_preserved_original'
    )),
    document_artifact_id TEXT NOT NULL REFERENCES document_artifacts(document_artifact_id),
    selected_at TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    rationale TEXT NOT NULL
);

CREATE INDEX document_selections_by_paper
    ON document_selection_events(paper_id, purpose, selected_at);

CREATE TABLE text_artifacts (
    text_artifact_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    document_artifact_id TEXT NOT NULL REFERENCES document_artifacts(document_artifact_id),
    artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    representation_kind TEXT NOT NULL,
    parser TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    structured INTEGER NOT NULL CHECK (structured IN (0, 1)),
    quality_json TEXT NOT NULL CHECK (json_valid(quality_json)),
    UNIQUE (document_artifact_id, artifact_sha256, parser, parser_version)
);

CREATE TABLE evidence_passages (
    passage_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    text_artifact_id TEXT NOT NULL REFERENCES text_artifacts(text_artifact_id),
    section_path_json TEXT NOT NULL CHECK (json_valid(section_path_json)),
    page_number INTEGER CHECK (page_number IS NULL OR page_number > 0),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    quotation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    extraction_method TEXT NOT NULL
);

CREATE INDEX evidence_passages_by_paper
    ON evidence_passages(paper_id, text_artifact_id);

CREATE TRIGGER resolution_requests_immutable_update
BEFORE UPDATE ON resolution_requests BEGIN
    SELECT RAISE(ABORT, 'resolution_requests are immutable');
END;
CREATE TRIGGER resolution_requests_immutable_delete
BEFORE DELETE ON resolution_requests BEGIN
    SELECT RAISE(ABORT, 'resolution_requests are immutable');
END;
CREATE TRIGGER acquisition_attempts_immutable_update
BEFORE UPDATE ON acquisition_attempts BEGIN
    SELECT RAISE(ABORT, 'acquisition_attempts are immutable');
END;
CREATE TRIGGER acquisition_attempts_immutable_delete
BEFORE DELETE ON acquisition_attempts BEGIN
    SELECT RAISE(ABORT, 'acquisition_attempts are immutable');
END;
CREATE TRIGGER document_artifacts_immutable_update
BEFORE UPDATE ON document_artifacts BEGIN
    SELECT RAISE(ABORT, 'document_artifacts are immutable');
END;
CREATE TRIGGER document_artifacts_immutable_delete
BEFORE DELETE ON document_artifacts BEGIN
    SELECT RAISE(ABORT, 'document_artifacts are immutable');
END;
CREATE TRIGGER document_selection_events_immutable_update
BEFORE UPDATE ON document_selection_events BEGIN
    SELECT RAISE(ABORT, 'document_selection_events are immutable');
END;
CREATE TRIGGER document_selection_events_immutable_delete
BEFORE DELETE ON document_selection_events BEGIN
    SELECT RAISE(ABORT, 'document_selection_events are immutable');
END;
CREATE TRIGGER text_artifacts_immutable_update
BEFORE UPDATE ON text_artifacts BEGIN
    SELECT RAISE(ABORT, 'text_artifacts are immutable');
END;
CREATE TRIGGER text_artifacts_immutable_delete
BEFORE DELETE ON text_artifacts BEGIN
    SELECT RAISE(ABORT, 'text_artifacts are immutable');
END;
CREATE TRIGGER evidence_passages_immutable_update
BEFORE UPDATE ON evidence_passages BEGIN
    SELECT RAISE(ABORT, 'evidence_passages are immutable');
END;
CREATE TRIGGER evidence_passages_immutable_delete
BEFORE DELETE ON evidence_passages BEGIN
    SELECT RAISE(ABORT, 'evidence_passages are immutable');
END;
