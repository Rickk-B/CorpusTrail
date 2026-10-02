ALTER TABLE parse_attempts ADD COLUMN parse_run_id TEXT;

CREATE UNIQUE INDEX parse_attempts_by_execution_run
    ON parse_attempts(parse_run_id, parse_request_id, parser)
    WHERE parse_run_id IS NOT NULL;

CREATE TABLE text_parse_reuses (
    parse_attempt_id TEXT PRIMARY KEY REFERENCES parse_attempts(parse_attempt_id),
    text_artifact_id TEXT NOT NULL REFERENCES text_artifacts(text_artifact_id),
    linked_at TEXT NOT NULL,
    reason TEXT NOT NULL
);

CREATE TRIGGER text_parse_reuses_immutable_update
BEFORE UPDATE ON text_parse_reuses BEGIN
    SELECT RAISE(ABORT, 'text_parse_reuses are immutable');
END;
CREATE TRIGGER text_parse_reuses_immutable_delete
BEFORE DELETE ON text_parse_reuses BEGIN
    SELECT RAISE(ABORT, 'text_parse_reuses are immutable');
END;
