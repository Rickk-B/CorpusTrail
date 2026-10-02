CREATE TABLE taxonomies (
    taxonomy_version TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    definition_artifact_sha256 TEXT NOT NULL UNIQUE REFERENCES raw_artifacts(sha256)
);

CREATE TABLE taxonomy_nodes (
    taxonomy_version TEXT NOT NULL REFERENCES taxonomies(taxonomy_version),
    dimension TEXT NOT NULL,
    category_code TEXT NOT NULL,
    parent_code TEXT,
    label TEXT NOT NULL,
    definition TEXT NOT NULL,
    PRIMARY KEY (taxonomy_version, dimension, category_code),
    FOREIGN KEY (taxonomy_version, dimension, parent_code)
        REFERENCES taxonomy_nodes(taxonomy_version, dimension, category_code)
);

CREATE TABLE category_assertion_batches (
    batch_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL REFERENCES taxonomies(taxonomy_version),
    artifact_sha256 TEXT NOT NULL UNIQUE REFERENCES raw_artifacts(sha256),
    registered_at TEXT NOT NULL
);

CREATE TABLE category_assertions (
    assertion_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES category_assertion_batches(batch_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    taxonomy_version TEXT NOT NULL,
    dimension TEXT NOT NULL,
    category_code TEXT NOT NULL,
    assertion TEXT NOT NULL CHECK (assertion IN ('present', 'absent', 'uncertain')),
    workflow_status TEXT NOT NULL CHECK (workflow_status IN ('proposed', 'approved', 'rejected')),
    authority_class TEXT NOT NULL CHECK (authority_class IN (
        'screening_signal', 'narrow_deterministic_rule',
        'approved_model_decision', 'human_review', 'protected_human'
    )),
    screening_event_id TEXT REFERENCES screening_events(screening_event_id),
    method_run_id TEXT REFERENCES screening_runs(run_id),
    evidence_representation TEXT NOT NULL CHECK (evidence_representation IN (
        'none', 'metadata', 'abstract', 'citation_context', 'structured_text',
        'pdf_text', 'ocr_text', 'image_only'
    )),
    artifact_validity TEXT NOT NULL CHECK (artifact_validity IN (
        'not_applicable', 'pending', 'verified', 'identity_rejected', 'unreadable'
    )),
    review_extent TEXT NOT NULL CHECK (review_extent IN (
        'none', 'metadata', 'abstract', 'passages', 'sections', 'full_document'
    )),
    confidence_kind TEXT NOT NULL CHECK (confidence_kind IN ('none', 'descriptive', 'probability')),
    confidence_value REAL CHECK (
        (confidence_kind = 'probability' AND confidence_value BETWEEN 0.0 AND 1.0)
        OR (confidence_kind != 'probability' AND confidence_value IS NULL)
    ),
    confidence_label TEXT,
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    evidence_sha256 TEXT NOT NULL CHECK (evidence_sha256 GLOB 'sha256:*'),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    assertion_payload_sha256 TEXT NOT NULL UNIQUE CHECK (assertion_payload_sha256 GLOB 'sha256:*'),
    FOREIGN KEY (taxonomy_version, dimension, category_code)
        REFERENCES taxonomy_nodes(taxonomy_version, dimension, category_code),
    CHECK (screening_event_id IS NOT NULL OR method_run_id IS NOT NULL),
    CHECK (workflow_status != 'approved' OR authority_class IN ('human_review', 'protected_human'))
);

CREATE TABLE category_assertion_evidence (
    assertion_id TEXT NOT NULL REFERENCES category_assertions(assertion_id),
    passage_id TEXT NOT NULL REFERENCES evidence_passages(passage_id),
    evidence_role TEXT NOT NULL CHECK (evidence_role IN ('supports', 'contradicts', 'context')),
    PRIMARY KEY (assertion_id, passage_id, evidence_role)
);

CREATE INDEX category_assertions_by_paper
    ON category_assertions(paper_id, taxonomy_version, dimension, category_code);

CREATE TRIGGER taxonomies_immutable_update BEFORE UPDATE ON taxonomies BEGIN
    SELECT RAISE(ABORT, 'taxonomies are immutable');
END;
CREATE TRIGGER taxonomies_immutable_delete BEFORE DELETE ON taxonomies BEGIN
    SELECT RAISE(ABORT, 'taxonomies are immutable');
END;
CREATE TRIGGER taxonomy_nodes_immutable_update BEFORE UPDATE ON taxonomy_nodes BEGIN
    SELECT RAISE(ABORT, 'taxonomy_nodes are immutable');
END;
CREATE TRIGGER taxonomy_nodes_immutable_delete BEFORE DELETE ON taxonomy_nodes BEGIN
    SELECT RAISE(ABORT, 'taxonomy_nodes are immutable');
END;
CREATE TRIGGER category_assertion_batches_immutable_update BEFORE UPDATE ON category_assertion_batches BEGIN
    SELECT RAISE(ABORT, 'category_assertion_batches are immutable');
END;
CREATE TRIGGER category_assertion_batches_immutable_delete BEFORE DELETE ON category_assertion_batches BEGIN
    SELECT RAISE(ABORT, 'category_assertion_batches are immutable');
END;
CREATE TRIGGER category_assertions_immutable_update BEFORE UPDATE ON category_assertions BEGIN
    SELECT RAISE(ABORT, 'category_assertions are immutable');
END;
CREATE TRIGGER category_assertions_immutable_delete BEFORE DELETE ON category_assertions BEGIN
    SELECT RAISE(ABORT, 'category_assertions are immutable');
END;
CREATE TRIGGER category_assertion_evidence_immutable_update BEFORE UPDATE ON category_assertion_evidence BEGIN
    SELECT RAISE(ABORT, 'category_assertion_evidence is immutable');
END;
CREATE TRIGGER category_assertion_evidence_immutable_delete BEFORE DELETE ON category_assertion_evidence BEGIN
    SELECT RAISE(ABORT, 'category_assertion_evidence is immutable');
END;
