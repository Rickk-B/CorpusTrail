CREATE TABLE legacy_knowledge_batches (
    batch_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    plan_sha256 TEXT NOT NULL UNIQUE CHECK (plan_sha256 GLOB 'sha256:*'),
    manifest_revision TEXT NOT NULL REFERENCES manifest_snapshots(revision),
    manifest_sha256 TEXT NOT NULL CHECK (manifest_sha256 GLOB 'sha256:*'),
    model_audit_sha256 TEXT NOT NULL CHECK (model_audit_sha256 GLOB 'sha256:*'),
    non_llm_audit_sha256 TEXT NOT NULL CHECK (non_llm_audit_sha256 GLOB 'sha256:*'),
    import_scope TEXT NOT NULL CHECK (import_scope = 'high_value_low_risk_v1'),
    activation_state TEXT NOT NULL CHECK (activation_state = 'inert'),
    observation_set_sha256 TEXT NOT NULL CHECK (observation_set_sha256 GLOB 'sha256:*'),
    applied_at TEXT NOT NULL,
    applied_by TEXT NOT NULL
);

CREATE TABLE legacy_source_artifacts (
    source_artifact_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES legacy_knowledge_batches(batch_id),
    raw_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    relative_path TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('current_file', 'git_blob')),
    originating_commit TEXT,
    artifact_role TEXT NOT NULL,
    UNIQUE (batch_id, relative_path, raw_artifact_sha256)
);

CREATE TABLE legacy_observations (
    observation_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    batch_id TEXT NOT NULL REFERENCES legacy_knowledge_batches(batch_id),
    paper_id TEXT REFERENCES paper_entities(paper_id),
    external_subject_id TEXT,
    observation_type TEXT NOT NULL CHECK (observation_type IN (
        'authoritative_human_judgment',
        'historical_human_annotation',
        'deterministic_rule_observation',
        'provider_metadata',
        'parser_document_observation',
        'model_llm_observation',
        'identity_merge_assertion',
        'citation_reference_observation',
        'terminology_search_observation',
        'inferred_relationship'
    )),
    predicate TEXT NOT NULL CHECK (length(trim(predicate)) > 0),
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    source_artifact_id TEXT NOT NULL REFERENCES legacy_source_artifacts(source_artifact_id),
    source_record_locator TEXT,
    source_record_sha256 TEXT CHECK (
        source_record_sha256 IS NULL OR source_record_sha256 GLOB 'sha256:*'
    ),
    provenance_class TEXT NOT NULL CHECK (provenance_class IN (
        'authoritative_human_judgment',
        'historical_human_annotation',
        'deterministic_rule_derived',
        'provider_derived',
        'parser_document_derived',
        'model_llm_derived',
        'inferred'
    )),
    producer_kind TEXT NOT NULL,
    producer_name TEXT,
    producer_version TEXT,
    workflow_name TEXT,
    workflow_version TEXT,
    source_timestamp TEXT,
    evidence_mode TEXT NOT NULL CHECK (evidence_mode IN (
        'none', 'metadata', 'abstract', 'citation_context', 'structured_text',
        'pdf_text', 'ocr_text', 'image_only', 'source_record'
    )),
    confidence_kind TEXT NOT NULL CHECK (confidence_kind IN (
        'none', 'descriptive', 'probability'
    )),
    confidence_value REAL CHECK (
        (confidence_kind = 'probability' AND confidence_value BETWEEN 0.0 AND 1.0)
        OR (confidence_kind != 'probability' AND confidence_value IS NULL)
    ),
    confidence_label TEXT,
    validation_state TEXT NOT NULL CHECK (validation_state IN (
        'unvalidated', 'validated', 'conflicted', 'rejected',
        'pending_supersession_review'
    )),
    supersession_status TEXT NOT NULL CHECK (supersession_status IN (
        'current_observation', 'superseded', 'disputed', 'not_applicable'
    )),
    supersedes_observation_id TEXT REFERENCES legacy_observations(observation_id),
    activation_state TEXT NOT NULL CHECK (activation_state = 'inert'),
    payload_sha256 TEXT NOT NULL UNIQUE CHECK (payload_sha256 GLOB 'sha256:*'),
    recorded_at TEXT NOT NULL,
    CHECK (paper_id IS NOT NULL OR external_subject_id IS NOT NULL),
    CHECK (
        observation_type != 'authoritative_human_judgment'
        OR provenance_class = 'authoritative_human_judgment'
    )
);

CREATE INDEX legacy_observations_by_paper
    ON legacy_observations(paper_id, observation_type, predicate);
CREATE INDEX legacy_observations_by_source
    ON legacy_observations(source_artifact_id, source_record_locator);
CREATE INDEX legacy_observations_by_provenance
    ON legacy_observations(provenance_class, validation_state);

CREATE TABLE legacy_observation_relations (
    relation_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES legacy_knowledge_batches(batch_id),
    source_observation_id TEXT NOT NULL REFERENCES legacy_observations(observation_id),
    target_observation_id TEXT NOT NULL REFERENCES legacy_observations(observation_id),
    relation TEXT NOT NULL CHECK (relation IN (
        'supports', 'contradicts', 'supersedes', 'derived_from',
        'same_subject_as', 'version_of'
    )),
    provenance_class TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL UNIQUE CHECK (payload_sha256 GLOB 'sha256:*'),
    recorded_at TEXT NOT NULL,
    CHECK (source_observation_id != target_observation_id),
    UNIQUE (source_observation_id, target_observation_id, relation)
);

CREATE TABLE legacy_supersession_review_queue (
    review_item_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES legacy_knowledge_batches(batch_id),
    historical_observation_id TEXT NOT NULL UNIQUE REFERENCES legacy_observations(observation_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    conflict_snapshot_json TEXT NOT NULL CHECK (json_valid(conflict_snapshot_json)),
    source_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    source_record_sha256 TEXT NOT NULL CHECK (source_record_sha256 GLOB 'sha256:*'),
    state TEXT NOT NULL CHECK (state = 'pending_human_review'),
    created_at TEXT NOT NULL
);

CREATE TRIGGER legacy_knowledge_batches_immutable_update
BEFORE UPDATE ON legacy_knowledge_batches BEGIN
    SELECT RAISE(ABORT, 'legacy knowledge batches are immutable');
END;
CREATE TRIGGER legacy_knowledge_batches_immutable_delete
BEFORE DELETE ON legacy_knowledge_batches BEGIN
    SELECT RAISE(ABORT, 'legacy knowledge batches are immutable');
END;
CREATE TRIGGER legacy_source_artifacts_immutable_update
BEFORE UPDATE ON legacy_source_artifacts BEGIN
    SELECT RAISE(ABORT, 'legacy source artifacts are immutable');
END;
CREATE TRIGGER legacy_source_artifacts_immutable_delete
BEFORE DELETE ON legacy_source_artifacts BEGIN
    SELECT RAISE(ABORT, 'legacy source artifacts are immutable');
END;
CREATE TRIGGER legacy_observations_immutable_update
BEFORE UPDATE ON legacy_observations BEGIN
    SELECT RAISE(ABORT, 'legacy observations are immutable');
END;
CREATE TRIGGER legacy_observations_immutable_delete
BEFORE DELETE ON legacy_observations BEGIN
    SELECT RAISE(ABORT, 'legacy observations are immutable');
END;
CREATE TRIGGER legacy_observation_relations_immutable_update
BEFORE UPDATE ON legacy_observation_relations BEGIN
    SELECT RAISE(ABORT, 'legacy observation relations are immutable');
END;
CREATE TRIGGER legacy_observation_relations_immutable_delete
BEFORE DELETE ON legacy_observation_relations BEGIN
    SELECT RAISE(ABORT, 'legacy observation relations are immutable');
END;
CREATE TRIGGER legacy_supersession_review_queue_immutable_update
BEFORE UPDATE ON legacy_supersession_review_queue BEGIN
    SELECT RAISE(ABORT, 'legacy supersession reviews are immutable');
END;
CREATE TRIGGER legacy_supersession_review_queue_immutable_delete
BEFORE DELETE ON legacy_supersession_review_queue BEGIN
    SELECT RAISE(ABORT, 'legacy supersession reviews are immutable');
END;
