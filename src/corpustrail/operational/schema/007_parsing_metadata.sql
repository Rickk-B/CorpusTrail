ALTER TABLE text_artifacts
    ADD COLUMN text_metadata_artifact_sha256 TEXT
    REFERENCES raw_artifacts(sha256);

ALTER TABLE evidence_passages
    ADD COLUMN passage_metadata_artifact_sha256 TEXT
    REFERENCES raw_artifacts(sha256);

CREATE INDEX text_artifacts_by_metadata
    ON text_artifacts(text_metadata_artifact_sha256);

CREATE INDEX evidence_passages_by_metadata
    ON evidence_passages(passage_metadata_artifact_sha256);
