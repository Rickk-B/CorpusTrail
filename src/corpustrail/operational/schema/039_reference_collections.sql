-- CP7 only: reference labels/context are not reviews or corpus decisions.
CREATE TABLE ct_reference_assignments (
    sequence INTEGER PRIMARY KEY,
    assignment_id TEXT NOT NULL UNIQUE,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    label TEXT NOT NULL CHECK(label IN ('in_scope','out_of_scope')),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL
);
CREATE INDEX ct_reference_assignment_paper ON ct_reference_assignments(paper_id,sequence);
CREATE TABLE ct_reference_chunks (
    chunk_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    item_count INTEGER NOT NULL CHECK(item_count BETWEEN 1 AND 256)
);
CREATE TABLE ct_reference_chunk_items (
    chunk_id TEXT NOT NULL REFERENCES ct_reference_chunks(chunk_id),
    position INTEGER NOT NULL CHECK(position >= 0 AND position < 256),
    assignment_id TEXT NOT NULL REFERENCES ct_reference_assignments(assignment_id),
    PRIMARY KEY(chunk_id,position),
    UNIQUE(chunk_id,assignment_id)
);
CREATE TABLE ct_reference_versions (
    sequence INTEGER PRIMARY KEY,
    version_id TEXT NOT NULL UNIQUE,
    collection_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version > 0),
    parent_id TEXT REFERENCES ct_reference_versions(version_id),
    request_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL,
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    payload_json TEXT NOT NULL,
    UNIQUE(collection_id,version)
);
CREATE INDEX ct_reference_chunk_assignment ON ct_reference_chunk_items(assignment_id,chunk_id);
CREATE INDEX ct_reference_family ON ct_reference_versions(collection_id,version);
CREATE TABLE ct_reference_version_chunks (
    version_id TEXT NOT NULL REFERENCES ct_reference_versions(version_id),
    bucket INTEGER NOT NULL CHECK(bucket BETWEEN 0 AND 255),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    chunk_id TEXT NOT NULL REFERENCES ct_reference_chunks(chunk_id),
    PRIMARY KEY(version_id,bucket,ordinal)
);
CREATE TABLE ct_reference_changes (
    version_id TEXT NOT NULL REFERENCES ct_reference_versions(version_id),
    position INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(version_id,position)
);
CREATE UNIQUE INDEX ct_reference_version_chunk ON ct_reference_version_chunks(version_id,chunk_id);
CREATE TABLE ct_reference_dependencies (
    dependency_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES ct_reference_versions(version_id),
    payload_json TEXT NOT NULL,
    body BLOB NOT NULL,
    body_sha256 TEXT NOT NULL
);
CREATE TABLE ct_reference_contexts (
    sequence INTEGER PRIMARY KEY,
    context_id TEXT NOT NULL UNIQUE,
    version_id TEXT NOT NULL REFERENCES ct_reference_versions(version_id),
    request_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    input_bytes BLOB NOT NULL,
    input_sha256 TEXT NOT NULL
);
CREATE TABLE ct_reference_context_items (
    context_id TEXT NOT NULL REFERENCES ct_reference_contexts(context_id),
    position INTEGER NOT NULL,
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    assignment_id TEXT NOT NULL REFERENCES ct_reference_assignments(assignment_id),
    decision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(context_id,position)
);
CREATE INDEX ct_reference_context_version ON ct_reference_contexts(version_id,sequence);
CREATE TRIGGER ct_reference_assignments_no_update BEFORE UPDATE ON ct_reference_assignments BEGIN SELECT RAISE(ABORT,'immutable reference assignment'); END;
CREATE TRIGGER ct_reference_assignments_no_delete BEFORE DELETE ON ct_reference_assignments BEGIN SELECT RAISE(ABORT,'immutable reference assignment'); END;
CREATE TRIGGER ct_reference_chunks_no_update BEFORE UPDATE ON ct_reference_chunks BEGIN SELECT RAISE(ABORT,'immutable reference chunk'); END;
CREATE TRIGGER ct_reference_chunks_no_delete BEFORE DELETE ON ct_reference_chunks BEGIN SELECT RAISE(ABORT,'immutable reference chunk'); END;
CREATE TRIGGER ct_reference_chunk_items_no_update BEFORE UPDATE ON ct_reference_chunk_items BEGIN SELECT RAISE(ABORT,'immutable reference chunk'); END;
CREATE TRIGGER ct_reference_chunk_items_no_delete BEFORE DELETE ON ct_reference_chunk_items BEGIN SELECT RAISE(ABORT,'immutable reference chunk'); END;
CREATE TRIGGER ct_reference_versions_no_update BEFORE UPDATE ON ct_reference_versions BEGIN SELECT RAISE(ABORT,'immutable reference version'); END;
CREATE TRIGGER ct_reference_versions_no_delete BEFORE DELETE ON ct_reference_versions BEGIN SELECT RAISE(ABORT,'immutable reference version'); END;
CREATE TRIGGER ct_reference_version_chunks_no_update BEFORE UPDATE ON ct_reference_version_chunks BEGIN SELECT RAISE(ABORT,'immutable reference membership'); END;
CREATE TRIGGER ct_reference_version_chunks_no_delete BEFORE DELETE ON ct_reference_version_chunks BEGIN SELECT RAISE(ABORT,'immutable reference membership'); END;
CREATE TRIGGER ct_reference_changes_no_update BEFORE UPDATE ON ct_reference_changes BEGIN SELECT RAISE(ABORT,'immutable reference correction'); END;
CREATE TRIGGER ct_reference_changes_no_delete BEFORE DELETE ON ct_reference_changes BEGIN SELECT RAISE(ABORT,'immutable reference correction'); END;
CREATE TRIGGER ct_reference_dependencies_no_update BEFORE UPDATE ON ct_reference_dependencies BEGIN SELECT RAISE(ABORT,'immutable context dependency'); END;
CREATE TRIGGER ct_reference_dependencies_no_delete BEFORE DELETE ON ct_reference_dependencies BEGIN SELECT RAISE(ABORT,'immutable context dependency'); END;
CREATE TRIGGER ct_reference_contexts_no_update BEFORE UPDATE ON ct_reference_contexts BEGIN SELECT RAISE(ABORT,'immutable selected context'); END;
CREATE TRIGGER ct_reference_contexts_no_delete BEFORE DELETE ON ct_reference_contexts BEGIN SELECT RAISE(ABORT,'immutable selected context'); END;
CREATE TRIGGER ct_reference_context_items_no_update BEFORE UPDATE ON ct_reference_context_items BEGIN SELECT RAISE(ABORT,'immutable context decision'); END;
CREATE TRIGGER ct_reference_context_items_no_delete BEFORE DELETE ON ct_reference_context_items BEGIN SELECT RAISE(ABORT,'immutable context decision'); END;
