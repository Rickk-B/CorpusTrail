-- Reuse generic immutable assertion tables from frozen 031, no backfill.
CREATE TABLE ct_knowledge_registry_records (
    sequence INTEGER PRIMARY KEY,
    record_id TEXT NOT NULL UNIQUE,
    content_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id)
);
CREATE TRIGGER ct_knowledge_registry_no_update BEFORE UPDATE ON ct_knowledge_registry_records BEGIN
    SELECT RAISE(ABORT, 'knowledge vocabularies are immutable'); END;
CREATE TRIGGER ct_knowledge_registry_no_delete BEFORE DELETE ON ct_knowledge_registry_records BEGIN
    SELECT RAISE(ABORT, 'knowledge vocabularies are immutable'); END;
CREATE TRIGGER ct_knowledge_registry_no_replace BEFORE INSERT ON ct_knowledge_registry_records
WHEN EXISTS (SELECT 1 FROM ct_knowledge_registry_records WHERE record_id=NEW.record_id OR content_sha256=NEW.content_sha256)
BEGIN SELECT RAISE(ABORT, 'knowledge vocabularies cannot be replaced'); END;
