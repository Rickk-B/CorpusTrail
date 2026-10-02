CREATE TABLE parse_intermediate_artifacts (
    parse_attempt_id TEXT NOT NULL REFERENCES parse_attempts(parse_attempt_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    representation_kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    PRIMARY KEY (parse_attempt_id, ordinal),
    UNIQUE (parse_attempt_id, artifact_sha256, representation_kind)
);

CREATE TRIGGER parse_intermediate_artifacts_immutable_update
BEFORE UPDATE ON parse_intermediate_artifacts BEGIN
    SELECT RAISE(ABORT, 'parse_intermediate_artifacts are immutable');
END;
CREATE TRIGGER parse_intermediate_artifacts_immutable_delete
BEFORE DELETE ON parse_intermediate_artifacts BEGIN
    SELECT RAISE(ABORT, 'parse_intermediate_artifacts are immutable');
END;
