CREATE TABLE resolution_provider_attempts (
    resolution_attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    request_id TEXT NOT NULL REFERENCES resolution_requests(request_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    provider TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN (
        'located', 'not_found', 'not_applicable', 'requires_configuration',
        'requires_user_action',
        'retryable_error', 'permanent_error'
    )),
    request_url TEXT,
    http_status INTEGER,
    response_media_type TEXT,
    response_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    error_code TEXT,
    error_detail TEXT,
    result_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    UNIQUE (run_id, request_id, provider)
);

CREATE INDEX resolution_provider_attempts_by_request
    ON resolution_provider_attempts(request_id, provider, completed_at);

CREATE TABLE resolution_locations (
    location_id TEXT PRIMARY KEY,
    resolution_attempt_id TEXT NOT NULL
        REFERENCES resolution_provider_attempts(resolution_attempt_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    provider TEXT NOT NULL,
    provider_record_id TEXT NOT NULL,
    url TEXT NOT NULL,
    representation_kind TEXT NOT NULL,
    version_kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    license TEXT,
    direct_content INTEGER NOT NULL CHECK (direct_content IN (0, 1)),
    content_in_response INTEGER NOT NULL CHECK (content_in_response IN (0, 1)),
    oa_evidence_json TEXT NOT NULL CHECK (json_valid(oa_evidence_json)),
    UNIQUE (resolution_attempt_id, ordinal)
);

CREATE INDEX resolution_locations_by_attempt
    ON resolution_locations(resolution_attempt_id, representation_kind);

CREATE TRIGGER resolution_provider_attempts_immutable_update
BEFORE UPDATE ON resolution_provider_attempts BEGIN
    SELECT RAISE(ABORT, 'resolution_provider_attempts are immutable');
END;
CREATE TRIGGER resolution_provider_attempts_immutable_delete
BEFORE DELETE ON resolution_provider_attempts BEGIN
    SELECT RAISE(ABORT, 'resolution_provider_attempts are immutable');
END;
CREATE TRIGGER resolution_locations_immutable_update
BEFORE UPDATE ON resolution_locations BEGIN
    SELECT RAISE(ABORT, 'resolution_locations are immutable');
END;
CREATE TRIGGER resolution_locations_immutable_delete
BEFORE DELETE ON resolution_locations BEGIN
    SELECT RAISE(ABORT, 'resolution_locations are immutable');
END;
