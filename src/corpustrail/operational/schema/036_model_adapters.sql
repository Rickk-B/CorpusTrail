-- Model infrastructure only. No modification to scientific authority tables.
CREATE TABLE ct_model_events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('model_transfer_consent','model_request_started',
        'model_response','model_assertion_plan','model_complete')),
    scope_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    source_sha256 TEXT REFERENCES raw_artifacts(sha256),
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL
);
CREATE INDEX ct_model_scope ON ct_model_events(scope_id,kind,sequence);
CREATE UNIQUE INDEX ct_model_once ON ct_model_events(scope_id,kind)
    WHERE kind IN ('model_request_started','model_response','model_complete');
CREATE TRIGGER ct_model_no_update BEFORE UPDATE ON ct_model_events
BEGIN SELECT RAISE(ABORT,'model events are immutable'); END;
CREATE TRIGGER ct_model_no_delete BEFORE DELETE ON ct_model_events
BEGIN SELECT RAISE(ABORT,'model events are immutable'); END;
CREATE TRIGGER ct_model_no_replace BEFORE INSERT ON ct_model_events
WHEN EXISTS (SELECT 1 FROM ct_model_events WHERE event_id=NEW.event_id)
BEGIN SELECT RAISE(ABORT,'model events cannot be replaced'); END;
