-- Candidate-only immutable operational ledger. No scientific authority writes.
CREATE TABLE ct_pipeline_events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('discovery_plan','request_started','request_result',
      'candidate_observation','discovery_complete','canonical_link','identity_issue',
      'resolution_plan','acquisition_started','acquisition_result','representation','identity_assessment')),
    scope_id TEXT NOT NULL,
    paper_id TEXT REFERENCES paper_entities(paper_id),
    source_sha256 TEXT REFERENCES raw_artifacts(sha256),
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL
);
CREATE INDEX ct_pipeline_scope ON ct_pipeline_events(scope_id,kind,sequence);
CREATE INDEX ct_pipeline_paper ON ct_pipeline_events(paper_id,kind,sequence);
CREATE UNIQUE INDEX ct_pipeline_singleton ON ct_pipeline_events(scope_id,kind)
 WHERE kind IN ('discovery_plan','discovery_complete','canonical_link','resolution_plan');
CREATE UNIQUE INDEX ct_request_reservation ON ct_pipeline_events(scope_id,
 json_extract(payload_json,'$.payload.attempt_id')) WHERE kind='request_started';
CREATE UNIQUE INDEX ct_acquisition_reservation ON ct_pipeline_events(scope_id,
 json_extract(payload_json,'$.payload.resolver'),json_extract(payload_json,'$.payload.attempt'))
 WHERE kind='acquisition_started';
CREATE TABLE ct_artifact_files (
    sha256 TEXT PRIMARY KEY REFERENCES raw_artifacts(sha256),
    relative_path TEXT NOT NULL UNIQUE
);
CREATE TRIGGER ct_pipeline_no_update BEFORE UPDATE ON ct_pipeline_events
BEGIN SELECT RAISE(ABORT,'pipeline events are immutable'); END;
CREATE TRIGGER ct_pipeline_no_delete BEFORE DELETE ON ct_pipeline_events
BEGIN SELECT RAISE(ABORT,'pipeline events are immutable'); END;
CREATE TRIGGER ct_artifact_no_update BEFORE UPDATE ON ct_artifact_files
BEGIN SELECT RAISE(ABORT,'artifact files are immutable'); END;
CREATE TRIGGER ct_artifact_no_delete BEFORE DELETE ON ct_artifact_files
BEGIN SELECT RAISE(ABORT,'artifact files are immutable'); END;
