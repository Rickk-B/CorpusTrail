-- Additive candidate-only capability. Earlier migrations retain their bytes.
CREATE TABLE ct_project_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_family TEXT NOT NULL CHECK (schema_family = 'corpustrail-standalone/v2'),
    project_id TEXT NOT NULL,
    bootstrap_sha256 TEXT NOT NULL
);
CREATE TABLE ct_project_config_events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    previous_event_id TEXT REFERENCES ct_project_config_events(event_id),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);
CREATE TABLE ct_enrollment_operations (
    plan_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id)
);
CREATE TABLE ct_source_bindings (
    source_uri TEXT NOT NULL,
    record_locator TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    plan_id TEXT NOT NULL REFERENCES ct_enrollment_operations(plan_id),
    PRIMARY KEY (source_uri, record_locator)
);
CREATE TABLE ct_paper_observations (
    observation_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    plan_id TEXT NOT NULL UNIQUE REFERENCES ct_enrollment_operations(plan_id),
    source_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
);
CREATE INDEX ct_observations_by_paper ON ct_paper_observations(paper_id);
CREATE TABLE ct_review_events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    membership_state TEXT NOT NULL CHECK (membership_state IN
        ('included', 'excluded', 'unresolved', 'insufficient_evidence')),
    producer_type TEXT NOT NULL CHECK (producer_type IN
        ('human', 'model', 'deterministic', 'parser', 'imported')),
    authority_state TEXT NOT NULL CHECK (authority_state IN
        ('non_authoritative', 'human_authorized')),
    supersedes TEXT REFERENCES ct_review_events(event_id),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL UNIQUE,
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    CHECK (authority_state != 'human_authorized' OR producer_type = 'human')
);
CREATE INDEX ct_review_by_paper ON ct_review_events(paper_id, sequence);

CREATE TRIGGER ct_project_identity_no_update BEFORE UPDATE ON ct_project_identity
BEGIN SELECT RAISE(ABORT, 'project identity is immutable'); END;
CREATE TRIGGER ct_project_identity_no_delete BEFORE DELETE ON ct_project_identity
BEGIN SELECT RAISE(ABORT, 'project identity is immutable'); END;
CREATE TRIGGER ct_config_no_update BEFORE UPDATE ON ct_project_config_events
BEGIN SELECT RAISE(ABORT, 'configuration events are immutable'); END;
CREATE TRIGGER ct_config_no_delete BEFORE DELETE ON ct_project_config_events
BEGIN SELECT RAISE(ABORT, 'configuration events are immutable'); END;
CREATE TRIGGER ct_enrollment_no_update BEFORE UPDATE ON ct_enrollment_operations
BEGIN SELECT RAISE(ABORT, 'enrollment operations are immutable'); END;
CREATE TRIGGER ct_enrollment_no_delete BEFORE DELETE ON ct_enrollment_operations
BEGIN SELECT RAISE(ABORT, 'enrollment operations are immutable'); END;
CREATE TRIGGER ct_binding_no_update BEFORE UPDATE ON ct_source_bindings
BEGIN SELECT RAISE(ABORT, 'source bindings are immutable'); END;
CREATE TRIGGER ct_binding_no_delete BEFORE DELETE ON ct_source_bindings
BEGIN SELECT RAISE(ABORT, 'source bindings are immutable'); END;
CREATE TRIGGER ct_observation_no_update BEFORE UPDATE ON ct_paper_observations
BEGIN SELECT RAISE(ABORT, 'bibliographic observations are immutable'); END;
CREATE TRIGGER ct_observation_no_delete BEFORE DELETE ON ct_paper_observations
BEGIN SELECT RAISE(ABORT, 'bibliographic observations are immutable'); END;
CREATE TRIGGER ct_review_no_update BEFORE UPDATE ON ct_review_events
BEGIN SELECT RAISE(ABORT, 'review events are immutable'); END;
CREATE TRIGGER ct_review_no_delete BEFORE DELETE ON ct_review_events
BEGIN SELECT RAISE(ABORT, 'review events are immutable'); END;
CREATE TRIGGER ct_entity_no_update BEFORE UPDATE ON paper_entities
BEGIN SELECT RAISE(ABORT, 'candidate identities are immutable in this capability'); END;
CREATE TRIGGER ct_entity_no_delete BEFORE DELETE ON paper_entities
BEGIN SELECT RAISE(ABORT, 'candidate identities are immutable in this capability'); END;
CREATE TRIGGER ct_alias_no_update BEFORE UPDATE ON paper_identifiers
BEGIN SELECT RAISE(ABORT, 'candidate aliases are immutable in this capability'); END;
CREATE TRIGGER ct_alias_no_delete BEFORE DELETE ON paper_identifiers
BEGIN SELECT RAISE(ABORT, 'candidate aliases are immutable in this capability'); END;
