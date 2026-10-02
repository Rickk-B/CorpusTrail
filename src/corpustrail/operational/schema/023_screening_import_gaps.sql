CREATE TABLE screening_import_gaps (
    gap_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES screening_runs(run_id),
    source_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    source_record_key TEXT NOT NULL,
    claimed_paper_id TEXT,
    reason TEXT NOT NULL CHECK (reason IN (
        'paper_identity_no_longer_present', 'identity_mapping_unresolved',
        'source_record_invalid'
    )),
    detail TEXT NOT NULL,
    gap_payload_sha256 TEXT NOT NULL UNIQUE CHECK (gap_payload_sha256 GLOB 'sha256:*'),
    recorded_at TEXT NOT NULL,
    UNIQUE (run_id, source_record_key, reason)
);

CREATE INDEX screening_import_gaps_by_claimed_paper
    ON screening_import_gaps(claimed_paper_id, reason);

CREATE TRIGGER screening_import_gaps_immutable_update
BEFORE UPDATE ON screening_import_gaps BEGIN
    SELECT RAISE(ABORT, 'screening_import_gaps are immutable');
END;
CREATE TRIGGER screening_import_gaps_immutable_delete
BEFORE DELETE ON screening_import_gaps BEGIN
    SELECT RAISE(ABORT, 'screening_import_gaps are immutable');
END;
