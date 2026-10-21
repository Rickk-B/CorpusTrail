-- CP8: engine observations never establish review or corpus-membership authority.
CREATE TABLE ct_classifier_blobs (
    sha256 TEXT PRIMARY KEY,
    body BLOB NOT NULL
);
CREATE TABLE ct_classifier_plans (
    sequence INTEGER PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL,
    population_version_id TEXT NOT NULL REFERENCES ct_population_versions(version_id),
    reference_version_id TEXT NOT NULL REFERENCES ct_reference_versions(version_id),
    config_event_id TEXT NOT NULL REFERENCES ct_project_config_events(event_id),
    payload_json TEXT NOT NULL
);
CREATE TABLE ct_classifier_references (
    plan_id TEXT NOT NULL REFERENCES ct_classifier_plans(plan_id) DEFERRABLE INITIALLY DEFERRED,
    position INTEGER NOT NULL CHECK(position>=0),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    decision TEXT NOT NULL CHECK(decision IN ('eligible','omitted')),
    input_blob_sha256 TEXT REFERENCES ct_classifier_blobs(sha256),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(plan_id,position)
);
CREATE INDEX ct_classifier_reference_paper ON ct_classifier_references(plan_id,paper_id,position);
CREATE TABLE ct_classifier_inputs (
    plan_id TEXT NOT NULL REFERENCES ct_classifier_plans(plan_id) DEFERRABLE INITIALLY DEFERRED,
    position INTEGER NOT NULL CHECK(position>=0),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    input_blob_sha256 TEXT NOT NULL REFERENCES ct_classifier_blobs(sha256),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(plan_id,position),
    UNIQUE(plan_id,paper_id)
);
CREATE TABLE ct_classifier_runs (
    sequence INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    plan_id TEXT NOT NULL REFERENCES ct_classifier_plans(plan_id),
    parent_run_id TEXT REFERENCES ct_classifier_runs(run_id),
    request_id TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
);
CREATE TABLE ct_classifier_run_events (
    run_id TEXT NOT NULL REFERENCES ct_classifier_runs(run_id),
    revision INTEGER NOT NULL CHECK(revision>0),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL UNIQUE,
    PRIMARY KEY(run_id,revision)
);
CREATE TABLE ct_classifier_attempts (
    run_id TEXT NOT NULL REFERENCES ct_classifier_runs(run_id),
    position INTEGER NOT NULL CHECK(position>=0),
    payload_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(run_id,position)
);
CREATE TABLE ct_classifier_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES ct_classifier_runs(run_id),
    position INTEGER NOT NULL CHECK(position>=0),
    paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
    kind TEXT NOT NULL CHECK(kind IN ('assessment','failure')),
    outcome TEXT CHECK(outcome IN ('include','exclude','uncertain')),
    payload_json TEXT NOT NULL,
    UNIQUE(run_id,position),
    FOREIGN KEY(run_id,position) REFERENCES ct_classifier_attempts(run_id,position),
    CHECK((kind='assessment' AND outcome IS NOT NULL) OR (kind='failure' AND outcome IS NULL))
);
CREATE INDEX ct_classifier_result_paper ON ct_classifier_results(paper_id,run_id);
CREATE INDEX ct_classifier_result_counts ON ct_classifier_results(run_id,kind,outcome);
CREATE TABLE ct_classifier_validations (
    validation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES ct_classifier_runs(run_id),
    payload_json TEXT NOT NULL
);
CREATE TABLE ct_classifier_calibrations (
    binding_id TEXT PRIMARY KEY,
    source_run_id TEXT NOT NULL REFERENCES ct_classifier_runs(run_id),
    artifact_sha256 TEXT NOT NULL REFERENCES ct_classifier_blobs(sha256),
    payload_json TEXT NOT NULL
);
-- Future explicit human workflow links reference existing events. This table
-- neither creates an authority event nor changes an engine's original producer.
CREATE TABLE ct_classifier_authority_links (
    link_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL REFERENCES ct_classifier_results(result_id),
    review_event_id TEXT NOT NULL REFERENCES ct_review_events(event_id),
    payload_json TEXT NOT NULL
);
CREATE TRIGGER ct_classifier_blobs_no_update BEFORE UPDATE ON ct_classifier_blobs BEGIN SELECT RAISE(ABORT,'immutable classifier input/output'); END;
CREATE TRIGGER ct_classifier_blobs_no_delete BEFORE DELETE ON ct_classifier_blobs BEGIN SELECT RAISE(ABORT,'immutable classifier input/output'); END;
CREATE TRIGGER ct_classifier_plans_no_update BEFORE UPDATE ON ct_classifier_plans BEGIN SELECT RAISE(ABORT,'immutable classifier plan'); END;
CREATE TRIGGER ct_classifier_plans_no_delete BEFORE DELETE ON ct_classifier_plans BEGIN SELECT RAISE(ABORT,'immutable classifier plan'); END;
CREATE TRIGGER ct_classifier_references_no_update BEFORE UPDATE ON ct_classifier_references BEGIN SELECT RAISE(ABORT,'immutable classifier references'); END;
CREATE TRIGGER ct_classifier_references_no_delete BEFORE DELETE ON ct_classifier_references BEGIN SELECT RAISE(ABORT,'immutable classifier references'); END;
CREATE TRIGGER ct_classifier_inputs_no_update BEFORE UPDATE ON ct_classifier_inputs BEGIN SELECT RAISE(ABORT,'immutable classifier evidence'); END;
CREATE TRIGGER ct_classifier_inputs_no_delete BEFORE DELETE ON ct_classifier_inputs BEGIN SELECT RAISE(ABORT,'immutable classifier evidence'); END;
CREATE TRIGGER ct_classifier_runs_no_update BEFORE UPDATE ON ct_classifier_runs BEGIN SELECT RAISE(ABORT,'immutable classifier run'); END;
CREATE TRIGGER ct_classifier_runs_no_delete BEFORE DELETE ON ct_classifier_runs BEGIN SELECT RAISE(ABORT,'immutable classifier run'); END;
CREATE TRIGGER ct_classifier_events_no_update BEFORE UPDATE ON ct_classifier_run_events BEGIN SELECT RAISE(ABORT,'immutable classifier lifecycle'); END;
CREATE TRIGGER ct_classifier_events_no_delete BEFORE DELETE ON ct_classifier_run_events BEGIN SELECT RAISE(ABORT,'immutable classifier lifecycle'); END;
CREATE TRIGGER ct_classifier_attempts_no_update BEFORE UPDATE ON ct_classifier_attempts BEGIN SELECT RAISE(ABORT,'immutable classifier attempt'); END;
CREATE TRIGGER ct_classifier_attempts_no_delete BEFORE DELETE ON ct_classifier_attempts BEGIN SELECT RAISE(ABORT,'immutable classifier attempt'); END;
CREATE TRIGGER ct_classifier_results_no_update BEFORE UPDATE ON ct_classifier_results BEGIN SELECT RAISE(ABORT,'immutable non-authoritative assessment'); END;
CREATE TRIGGER ct_classifier_results_no_delete BEFORE DELETE ON ct_classifier_results BEGIN SELECT RAISE(ABORT,'immutable non-authoritative assessment'); END;
CREATE TRIGGER ct_classifier_validations_no_update BEFORE UPDATE ON ct_classifier_validations BEGIN SELECT RAISE(ABORT,'immutable classifier validation'); END;
CREATE TRIGGER ct_classifier_validations_no_delete BEFORE DELETE ON ct_classifier_validations BEGIN SELECT RAISE(ABORT,'immutable classifier validation'); END;
CREATE TRIGGER ct_classifier_calibrations_no_update BEFORE UPDATE ON ct_classifier_calibrations BEGIN SELECT RAISE(ABORT,'immutable classifier calibration provenance'); END;
CREATE TRIGGER ct_classifier_calibrations_no_delete BEFORE DELETE ON ct_classifier_calibrations BEGIN SELECT RAISE(ABORT,'immutable classifier calibration provenance'); END;
CREATE TRIGGER ct_classifier_authority_no_update BEFORE UPDATE ON ct_classifier_authority_links BEGIN SELECT RAISE(ABORT,'immutable classifier authority lineage'); END;
CREATE TRIGGER ct_classifier_authority_no_delete BEFORE DELETE ON ct_classifier_authority_links BEGIN SELECT RAISE(ABORT,'immutable classifier authority lineage'); END;
