CREATE TABLE parse_requests (
    parse_request_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    document_artifact_id TEXT NOT NULL REFERENCES document_artifacts(document_artifact_id),
    input_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    requested_at TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    parser_order_json TEXT NOT NULL CHECK (json_valid(parser_order_json)),
    request_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE INDEX parse_requests_by_document
    ON parse_requests(document_artifact_id, requested_at);

CREATE TABLE parse_attempts (
    parse_attempt_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    parse_request_id TEXT NOT NULL REFERENCES parse_requests(parse_request_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    document_artifact_id TEXT NOT NULL REFERENCES document_artifacts(document_artifact_id),
    parser TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN (
        'succeeded', 'unavailable', 'unsupported', 'insufficient_quality',
        'retryable_error', 'permanent_error'
    )),
    text_artifact_id TEXT,
    error_code TEXT,
    error_detail TEXT,
    attempt_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE INDEX parse_attempts_by_request
    ON parse_attempts(parse_request_id, parser, completed_at);

ALTER TABLE text_artifacts
    ADD COLUMN parse_attempt_id TEXT REFERENCES parse_attempts(parse_attempt_id);

CREATE UNIQUE INDEX text_artifacts_by_parse_attempt
    ON text_artifacts(parse_attempt_id) WHERE parse_attempt_id IS NOT NULL;

CREATE TRIGGER parse_requests_immutable_update
BEFORE UPDATE ON parse_requests BEGIN
    SELECT RAISE(ABORT, 'parse_requests are immutable');
END;
CREATE TRIGGER parse_requests_immutable_delete
BEFORE DELETE ON parse_requests BEGIN
    SELECT RAISE(ABORT, 'parse_requests are immutable');
END;
CREATE TRIGGER parse_attempts_immutable_update
BEFORE UPDATE ON parse_attempts BEGIN
    SELECT RAISE(ABORT, 'parse_attempts are immutable');
END;
CREATE TRIGGER parse_attempts_immutable_delete
BEFORE DELETE ON parse_attempts BEGIN
    SELECT RAISE(ABORT, 'parse_attempts are immutable');
END;
