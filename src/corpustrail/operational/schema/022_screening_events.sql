CREATE TABLE screening_policies (
    policy_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    scope_version TEXT NOT NULL,
    scope_sha256 TEXT NOT NULL CHECK (scope_sha256 GLOB 'sha256:*'),
    authority_rules_json TEXT NOT NULL CHECK (json_valid(authority_rules_json)),
    protected_tasks_json TEXT NOT NULL CHECK (json_valid(protected_tasks_json)),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    policy_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE screening_runs (
    run_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    adapter TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    model_version TEXT,
    prompt_version TEXT,
    prompt_sha256 TEXT,
    configuration_json TEXT NOT NULL CHECK (json_valid(configuration_json)),
    input_population_sha256 TEXT NOT NULL CHECK (input_population_sha256 GLOB 'sha256:*'),
    source_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    recorded_at TEXT NOT NULL,
    recorded_by TEXT NOT NULL
);

CREATE TABLE screening_run_artifacts (
    run_id TEXT NOT NULL REFERENCES screening_runs(run_id),
    artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    role TEXT NOT NULL,
    PRIMARY KEY (run_id, artifact_sha256, role)
);

CREATE TABLE screening_attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES screening_runs(run_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    source_record_key TEXT NOT NULL,
    task_type TEXT NOT NULL CHECK (task_type IN (
        'relevance', 'is_human', 'is_human_invivo_skin'
    )),
    outcome TEXT NOT NULL CHECK (outcome IN (
        'completed', 'model_failed', 'invalid_response', 'evidence_unavailable',
        'parse_failed', 'language_unsupported', 'identity_unverified',
        'artifact_rejected'
    )),
    error_code TEXT,
    error_detail TEXT,
    input_sha256 TEXT NOT NULL CHECK (input_sha256 GLOB 'sha256:*'),
    output_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    recorded_at TEXT NOT NULL,
    UNIQUE (run_id, source_record_key, task_type)
);

CREATE TABLE screening_events (
    screening_event_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES screening_attempts(attempt_id),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    task_type TEXT NOT NULL CHECK (task_type IN (
        'relevance', 'is_human', 'is_human_invivo_skin'
    )),
    assessment TEXT NOT NULL CHECK (assessment IN (
        'relevant', 'irrelevant', 'indeterminate', 'yes', 'no'
    )),
    indeterminate_reason TEXT CHECK (
        (assessment = 'indeterminate' AND indeterminate_reason IN (
            'uncertain_interpretation', 'insufficient_evidence',
            'conflicting_assessments', 'pending_human_review'
        )) OR (assessment != 'indeterminate' AND indeterminate_reason IS NULL)
    ),
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
    observation_id TEXT REFERENCES candidate_observations(observation_id),
    document_artifact_id TEXT REFERENCES document_artifacts(document_artifact_id),
    text_artifact_id TEXT REFERENCES text_artifacts(text_artifact_id),
    evidence_sha256 TEXT NOT NULL CHECK (evidence_sha256 GLOB 'sha256:*'),
    authority_class TEXT NOT NULL CHECK (authority_class IN (
        'screening_signal', 'narrow_deterministic_rule',
        'approved_model_decision', 'human_review', 'protected_human'
    )),
    confidence_kind TEXT NOT NULL CHECK (confidence_kind IN (
        'none', 'descriptive', 'probability'
    )),
    confidence_value REAL CHECK (
        (confidence_kind = 'probability' AND confidence_value BETWEEN 0.0 AND 1.0)
        OR (confidence_kind != 'probability' AND confidence_value IS NULL)
    ),
    confidence_label TEXT,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    source_decided_at TEXT,
    source_sequence TEXT NOT NULL,
    policy_id TEXT NOT NULL REFERENCES screening_policies(policy_id),
    protected_status TEXT NOT NULL CHECK (protected_status IN (
        'not_protected', 'candidate_only', 'protected'
    )),
    event_payload_sha256 TEXT NOT NULL UNIQUE CHECK (event_payload_sha256 GLOB 'sha256:*'),
    recorded_at TEXT NOT NULL,
    CHECK (
        (task_type = 'relevance' AND assessment IN (
            'relevant', 'irrelevant', 'indeterminate'
        )) OR (task_type != 'relevance' AND assessment IN ('yes', 'no', 'indeterminate'))
    ),
    CHECK (authority_class != 'protected_human' OR protected_status = 'protected'),
    CHECK (protected_status != 'protected' OR authority_class = 'protected_human')
);

CREATE INDEX screening_events_by_paper
    ON screening_events(paper_id, task_type, authority_class, source_sequence);
CREATE INDEX screening_attempts_by_run
    ON screening_attempts(run_id, paper_id, task_type);

CREATE TABLE screening_event_evidence (
    screening_event_id TEXT NOT NULL REFERENCES screening_events(screening_event_id),
    passage_id TEXT NOT NULL REFERENCES evidence_passages(passage_id),
    evidence_role TEXT NOT NULL CHECK (evidence_role IN ('supports', 'contradicts', 'context')),
    PRIMARY KEY (screening_event_id, passage_id, evidence_role)
);

CREATE TABLE screening_event_relations (
    relation_id TEXT PRIMARY KEY,
    source_event_id TEXT NOT NULL REFERENCES screening_events(screening_event_id),
    target_event_id TEXT NOT NULL REFERENCES screening_events(screening_event_id),
    relation TEXT NOT NULL CHECK (relation IN (
        'reviews', 'supersedes', 'contradicts', 'confirms', 'derived_from'
    )),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    CHECK (source_event_id != target_event_id),
    UNIQUE (source_event_id, target_event_id, relation)
);

CREATE TABLE screening_approvals (
    approval_id TEXT PRIMARY KEY,
    screening_event_id TEXT NOT NULL REFERENCES screening_events(screening_event_id),
    decision TEXT NOT NULL CHECK (decision IN (
        'approve', 'reject', 'request_adjudication'
    )),
    decided_by TEXT NOT NULL,
    source_decided_at TEXT,
    source_sequence TEXT NOT NULL,
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    policy_id TEXT NOT NULL REFERENCES screening_policies(policy_id),
    source_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    approval_payload_sha256 TEXT NOT NULL UNIQUE CHECK (approval_payload_sha256 GLOB 'sha256:*'),
    recorded_at TEXT NOT NULL
);

CREATE INDEX screening_approvals_by_event
    ON screening_approvals(screening_event_id, source_sequence, approval_id);

CREATE TABLE screening_equivalence_reports (
    report_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    policy_id TEXT NOT NULL REFERENCES screening_policies(policy_id),
    manifest_revision TEXT NOT NULL REFERENCES manifest_snapshots(revision),
    scientific_state_sha256 TEXT NOT NULL CHECK (scientific_state_sha256 GLOB 'sha256:*'),
    equivalent INTEGER NOT NULL CHECK (equivalent IN (0, 1)),
    report_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    recorded_at TEXT NOT NULL
);

CREATE TRIGGER screening_policies_immutable_update
BEFORE UPDATE ON screening_policies BEGIN
    SELECT RAISE(ABORT, 'screening_policies are immutable');
END;
CREATE TRIGGER screening_policies_immutable_delete
BEFORE DELETE ON screening_policies BEGIN
    SELECT RAISE(ABORT, 'screening_policies are immutable');
END;
CREATE TRIGGER screening_runs_immutable_update
BEFORE UPDATE ON screening_runs BEGIN
    SELECT RAISE(ABORT, 'screening_runs are immutable');
END;
CREATE TRIGGER screening_runs_immutable_delete
BEFORE DELETE ON screening_runs BEGIN
    SELECT RAISE(ABORT, 'screening_runs are immutable');
END;
CREATE TRIGGER screening_run_artifacts_immutable_update
BEFORE UPDATE ON screening_run_artifacts BEGIN
    SELECT RAISE(ABORT, 'screening_run_artifacts are immutable');
END;
CREATE TRIGGER screening_run_artifacts_immutable_delete
BEFORE DELETE ON screening_run_artifacts BEGIN
    SELECT RAISE(ABORT, 'screening_run_artifacts are immutable');
END;
CREATE TRIGGER screening_attempts_immutable_update
BEFORE UPDATE ON screening_attempts BEGIN
    SELECT RAISE(ABORT, 'screening_attempts are immutable');
END;
CREATE TRIGGER screening_attempts_immutable_delete
BEFORE DELETE ON screening_attempts BEGIN
    SELECT RAISE(ABORT, 'screening_attempts are immutable');
END;
CREATE TRIGGER screening_events_immutable_update
BEFORE UPDATE ON screening_events BEGIN
    SELECT RAISE(ABORT, 'screening_events are immutable');
END;
CREATE TRIGGER screening_events_immutable_delete
BEFORE DELETE ON screening_events BEGIN
    SELECT RAISE(ABORT, 'screening_events are immutable');
END;
CREATE TRIGGER screening_event_evidence_immutable_update
BEFORE UPDATE ON screening_event_evidence BEGIN
    SELECT RAISE(ABORT, 'screening_event_evidence is immutable');
END;
CREATE TRIGGER screening_event_evidence_immutable_delete
BEFORE DELETE ON screening_event_evidence BEGIN
    SELECT RAISE(ABORT, 'screening_event_evidence is immutable');
END;
CREATE TRIGGER screening_event_relations_immutable_update
BEFORE UPDATE ON screening_event_relations BEGIN
    SELECT RAISE(ABORT, 'screening_event_relations are immutable');
END;
CREATE TRIGGER screening_event_relations_immutable_delete
BEFORE DELETE ON screening_event_relations BEGIN
    SELECT RAISE(ABORT, 'screening_event_relations are immutable');
END;
CREATE TRIGGER screening_approvals_immutable_update
BEFORE UPDATE ON screening_approvals BEGIN
    SELECT RAISE(ABORT, 'screening_approvals are immutable');
END;
CREATE TRIGGER screening_approvals_immutable_delete
BEFORE DELETE ON screening_approvals BEGIN
    SELECT RAISE(ABORT, 'screening_approvals are immutable');
END;
CREATE TRIGGER screening_equivalence_reports_immutable_update
BEFORE UPDATE ON screening_equivalence_reports BEGIN
    SELECT RAISE(ABORT, 'screening_equivalence_reports are immutable');
END;
CREATE TRIGGER screening_equivalence_reports_immutable_delete
BEFORE DELETE ON screening_equivalence_reports BEGIN
    SELECT RAISE(ABORT, 'screening_equivalence_reports are immutable');
END;
