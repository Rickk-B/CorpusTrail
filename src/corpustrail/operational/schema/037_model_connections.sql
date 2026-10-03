-- Synthetic diagnostics only. No paper evidence or scientific-state writes.
CREATE TABLE ct_model_connection_events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('started','complete')),
    run_id TEXT NOT NULL,
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL,
    UNIQUE(run_id,kind)
);
CREATE TRIGGER ct_model_connection_no_update BEFORE UPDATE ON ct_model_connection_events
BEGIN SELECT RAISE(ABORT,'connection events are immutable'); END;
CREATE TRIGGER ct_model_connection_no_delete BEFORE DELETE ON ct_model_connection_events
BEGIN SELECT RAISE(ABORT,'connection events are immutable'); END;
CREATE TRIGGER ct_model_connection_no_replace BEFORE INSERT ON ct_model_connection_events
WHEN EXISTS (SELECT 1 FROM ct_model_connection_events WHERE event_id=NEW.event_id)
BEGIN SELECT RAISE(ABORT,'connection events cannot be replaced'); END;
