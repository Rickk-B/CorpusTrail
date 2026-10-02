CREATE TABLE relevance_signal_batches (
    batch_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    batch_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE candidate_relevance_signals (
    signal_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES relevance_signal_batches(batch_id),
    observation_id TEXT REFERENCES candidate_observations(observation_id),
    paper_id TEXT REFERENCES paper_entities(paper_id),
    text_artifact_id TEXT REFERENCES text_artifacts(text_artifact_id),
    stage TEXT NOT NULL CHECK (stage IN ('title_metadata', 'abstract', 'full_text')),
    outcome TEXT NOT NULL CHECK (outcome IN (
        'likely_relevant', 'uncertain', 'likely_irrelevant', 'insufficient_evidence'
    )),
    assessor_kind TEXT NOT NULL CHECK (assessor_kind IN (
        'deterministic_rule', 'screening_model', 'human_review'
    )),
    method TEXT NOT NULL,
    method_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL CHECK (evidence_sha256 GLOB 'sha256:*'),
    previous_signal_id TEXT UNIQUE REFERENCES candidate_relevance_signals(signal_id),
    rationale TEXT NOT NULL,
    cost_json TEXT NOT NULL CHECK (json_valid(cost_json)),
    CHECK (
        (stage = 'full_text' AND paper_id IS NOT NULL AND text_artifact_id IS NOT NULL) OR
        (stage != 'full_text' AND observation_id IS NOT NULL AND paper_id IS NULL
         AND text_artifact_id IS NULL)
    )
);

CREATE INDEX relevance_signals_by_observation
    ON candidate_relevance_signals(observation_id, stage, created_at);
CREATE INDEX relevance_signals_by_paper
    ON candidate_relevance_signals(paper_id, stage, created_at);

CREATE TRIGGER relevance_signal_batches_immutable_update
BEFORE UPDATE ON relevance_signal_batches BEGIN
    SELECT RAISE(ABORT, 'relevance_signal_batches are immutable');
END;
CREATE TRIGGER relevance_signal_batches_immutable_delete
BEFORE DELETE ON relevance_signal_batches BEGIN
    SELECT RAISE(ABORT, 'relevance_signal_batches are immutable');
END;
CREATE TRIGGER candidate_relevance_signals_immutable_update
BEFORE UPDATE ON candidate_relevance_signals BEGIN
    SELECT RAISE(ABORT, 'candidate_relevance_signals are immutable');
END;
CREATE TRIGGER candidate_relevance_signals_immutable_delete
BEFORE DELETE ON candidate_relevance_signals BEGIN
    SELECT RAISE(ABORT, 'candidate_relevance_signals are immutable');
END;
