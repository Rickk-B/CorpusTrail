-- Standalone-only additive curation sessions and immutable ranking provenance.
CREATE TABLE ct_review_availability (
    event_id TEXT PRIMARY KEY REFERENCES ct_review_events(event_id),
    recorded_at TEXT NOT NULL
);
CREATE TABLE ct_priority_artifacts (
    artifact_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('training_snapshot','model','ranking')),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    created_at TEXT NOT NULL
);
CREATE TABLE ct_priority_runs (
    run_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES ct_priority_artifacts(artifact_id),
    model_id TEXT NOT NULL REFERENCES ct_priority_artifacts(artifact_id),
    previous_run_id TEXT REFERENCES ct_priority_runs(run_id),
    provenance_json TEXT NOT NULL,
    provenance_sha256 TEXT NOT NULL
);
CREATE TABLE ct_review_sessions (
    session_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id)
);
CREATE TABLE ct_review_session_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    session_id TEXT NOT NULL REFERENCES ct_review_sessions(session_id),
    previous_event_id TEXT REFERENCES ct_review_session_events(event_id),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL
);
CREATE INDEX ct_review_session_history ON ct_review_session_events(session_id,sequence);
CREATE TRIGGER ct_review_availability_no_update BEFORE UPDATE ON ct_review_availability BEGIN SELECT RAISE(ABORT,'immutable availability receipt'); END;
CREATE TRIGGER ct_review_availability_no_delete BEFORE DELETE ON ct_review_availability BEGIN SELECT RAISE(ABORT,'immutable availability receipt'); END;
CREATE TRIGGER ct_priority_artifacts_no_update BEFORE UPDATE ON ct_priority_artifacts BEGIN SELECT RAISE(ABORT,'immutable priority artifact'); END;
CREATE TRIGGER ct_priority_artifacts_no_delete BEFORE DELETE ON ct_priority_artifacts BEGIN SELECT RAISE(ABORT,'immutable priority artifact'); END;
CREATE TRIGGER ct_priority_runs_no_update BEFORE UPDATE ON ct_priority_runs BEGIN SELECT RAISE(ABORT,'immutable ranking run'); END;
CREATE TRIGGER ct_priority_runs_no_delete BEFORE DELETE ON ct_priority_runs BEGIN SELECT RAISE(ABORT,'immutable ranking run'); END;
CREATE TRIGGER ct_review_sessions_no_update BEFORE UPDATE ON ct_review_sessions BEGIN SELECT RAISE(ABORT,'immutable session population'); END;
CREATE TRIGGER ct_review_sessions_no_delete BEFORE DELETE ON ct_review_sessions BEGIN SELECT RAISE(ABORT,'immutable session population'); END;
CREATE TRIGGER ct_review_session_events_no_update BEFORE UPDATE ON ct_review_session_events BEGIN SELECT RAISE(ABORT,'append-only session history'); END;
CREATE TRIGGER ct_review_session_events_no_delete BEFORE DELETE ON ct_review_session_events BEGIN SELECT RAISE(ABORT,'append-only session history'); END;
