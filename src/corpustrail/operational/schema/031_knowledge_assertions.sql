-- Additive storage only. No historical backfill or production projection.
CREATE TABLE knowledge_concepts (
    predicate TEXT NOT NULL,
    vocabulary_version TEXT NOT NULL,
    definition TEXT NOT NULL,
    definition_sha256 TEXT NOT NULL,
    PRIMARY KEY (predicate, vocabulary_version)
);

CREATE TABLE knowledge_assertions (
    assertion_id TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    paper_id TEXT REFERENCES paper_entities(paper_id),
    predicate TEXT NOT NULL,
    vocabulary_version TEXT NOT NULL,
    raw_value_json TEXT NOT NULL CHECK (json_valid(raw_value_json)),
    normalized_value_json TEXT NOT NULL CHECK (json_valid(normalized_value_json)),
    value_datatype TEXT NOT NULL,
    producer_type TEXT NOT NULL CHECK (producer_type IN ('human','model','deterministic','parser/document','imported/external')),
    producer_id TEXT NOT NULL,
    producer_version TEXT,
    created_at TEXT NOT NULL,
    evidence_representation TEXT NOT NULL,
    document_artifact_id TEXT REFERENCES document_artifacts(document_artifact_id),
    text_artifact_id TEXT REFERENCES text_artifacts(text_artifact_id),
    passage_id TEXT REFERENCES evidence_passages(passage_id),
    initial_validation TEXT NOT NULL CHECK (initial_validation = 'unvalidated'),
    initial_authority TEXT NOT NULL CHECK (initial_authority = 'non_authoritative'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    FOREIGN KEY (predicate, vocabulary_version) REFERENCES knowledge_concepts(predicate, vocabulary_version)
);
CREATE INDEX knowledge_assertions_subject ON knowledge_assertions(subject_type, subject_id, predicate);
CREATE INDEX knowledge_assertions_paper ON knowledge_assertions(paper_id, predicate, vocabulary_version);
CREATE INDEX knowledge_assertions_value ON knowledge_assertions(predicate, raw_value_json);

CREATE TABLE knowledge_events (
    event_id TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL UNIQUE,
    target_assertion_id TEXT NOT NULL REFERENCES knowledge_assertions(assertion_id),
    source_assertion_id TEXT REFERENCES knowledge_assertions(assertion_id),
    target_event_id TEXT REFERENCES knowledge_events(event_id),
    relation TEXT NOT NULL CHECK (relation IN ('validates','disputes','supersedes','retracts','duplicates','derived_from','rejects','grants_authority','revokes_authority')),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human','model','deterministic','parser/document','imported/external')),
    actor_id TEXT NOT NULL,
    purpose TEXT,
    policy_id TEXT,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    CHECK (source_assertion_id IS NULL OR source_assertion_id != target_assertion_id),
    CHECK (relation NOT IN ('validates','grants_authority','revokes_authority') OR
        (actor_type = 'human' AND purpose IS NOT NULL AND purpose GLOB 'knowledge.*' AND policy_id IS NOT NULL)),
    CHECK (relation != 'revokes_authority' OR target_event_id IS NOT NULL),
    CHECK (relation = 'revokes_authority' OR target_event_id IS NULL),
    CHECK (relation NOT IN ('supersedes','duplicates','derived_from') OR source_assertion_id IS NOT NULL)
);
CREATE INDEX knowledge_events_target ON knowledge_events(target_assertion_id, relation, purpose);
CREATE INDEX knowledge_events_source ON knowledge_events(source_assertion_id);

CREATE TRIGGER knowledge_concepts_no_update BEFORE UPDATE ON knowledge_concepts BEGIN
    SELECT RAISE(ABORT, 'knowledge concepts are immutable'); END;
CREATE TRIGGER knowledge_concepts_no_delete BEFORE DELETE ON knowledge_concepts BEGIN
    SELECT RAISE(ABORT, 'knowledge concepts are immutable'); END;
CREATE TRIGGER knowledge_concepts_no_replace BEFORE INSERT ON knowledge_concepts
WHEN EXISTS (SELECT 1 FROM knowledge_concepts WHERE predicate=NEW.predicate AND vocabulary_version=NEW.vocabulary_version)
BEGIN SELECT RAISE(ABORT, 'knowledge concepts cannot be replaced'); END;
CREATE TRIGGER knowledge_assertions_no_update BEFORE UPDATE ON knowledge_assertions BEGIN
    SELECT RAISE(ABORT, 'knowledge assertions are immutable'); END;
CREATE TRIGGER knowledge_assertions_no_delete BEFORE DELETE ON knowledge_assertions BEGIN
    SELECT RAISE(ABORT, 'knowledge assertions are immutable'); END;
CREATE TRIGGER knowledge_assertions_no_replace BEFORE INSERT ON knowledge_assertions
WHEN EXISTS (SELECT 1 FROM knowledge_assertions WHERE assertion_id=NEW.assertion_id OR content_sha256=NEW.content_sha256)
BEGIN SELECT RAISE(ABORT, 'knowledge assertions cannot be replaced'); END;
CREATE TRIGGER knowledge_events_no_update BEFORE UPDATE ON knowledge_events BEGIN
    SELECT RAISE(ABORT, 'knowledge events are immutable'); END;
CREATE TRIGGER knowledge_events_no_delete BEFORE DELETE ON knowledge_events BEGIN
    SELECT RAISE(ABORT, 'knowledge events are immutable'); END;
CREATE TRIGGER knowledge_events_no_replace BEFORE INSERT ON knowledge_events
WHEN EXISTS (SELECT 1 FROM knowledge_events WHERE event_id=NEW.event_id OR content_sha256=NEW.content_sha256)
BEGIN SELECT RAISE(ABORT, 'knowledge events cannot be replaced'); END;
