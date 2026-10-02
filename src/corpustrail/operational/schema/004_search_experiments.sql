CREATE TABLE search_proposals (
    proposal_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    parent_proposal_id TEXT REFERENCES search_proposals(proposal_id),
    origin TEXT NOT NULL
        CHECK (origin IN ('corpus', 'citation_graph', 'pretrained_model', 'human')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    expected_concept_cluster TEXT NOT NULL,
    false_positive_risks_json TEXT NOT NULL
        CHECK (json_valid(false_positive_risks_json)),
    proposal_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    UNIQUE (proposal_id, revision)
);

CREATE TABLE search_proposal_support (
    support_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES search_proposals(proposal_id),
    paper_id TEXT REFERENCES paper_entities(paper_id),
    observation_id TEXT REFERENCES candidate_observations(observation_id),
    passage_locator TEXT,
    quoted_text TEXT,
    support_json TEXT NOT NULL CHECK (json_valid(support_json)),
    CHECK (paper_id IS NOT NULL OR observation_id IS NOT NULL OR quoted_text IS NOT NULL)
);

CREATE INDEX search_proposal_support_by_paper
    ON search_proposal_support(paper_id);

CREATE TABLE search_proposal_queries (
    proposal_query_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES search_proposals(proposal_id),
    provider TEXT NOT NULL,
    executable_query TEXT NOT NULL,
    dialect TEXT NOT NULL,
    UNIQUE (proposal_id, provider, executable_query, dialect)
);

CREATE TABLE search_proposal_decisions (
    decision_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES search_proposals(proposal_id),
    decision TEXT NOT NULL CHECK (decision IN ('accept', 'reject', 'modify')),
    rationale TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    replacement_proposal_id TEXT REFERENCES search_proposals(proposal_id),
    CHECK (
        (decision = 'modify' AND replacement_proposal_id IS NOT NULL) OR
        (decision != 'modify' AND replacement_proposal_id IS NULL)
    ),
    UNIQUE (proposal_id)
);

CREATE TABLE search_experiments (
    experiment_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    proposal_id TEXT REFERENCES search_proposals(proposal_id),
    method TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    candidate_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    labels_artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    candidates_returned INTEGER NOT NULL CHECK (candidates_returned >= 0),
    previously_known INTEGER NOT NULL CHECK (previously_known >= 0),
    novel_candidates INTEGER NOT NULL CHECK (novel_candidates >= 0),
    novel_relevant INTEGER NOT NULL CHECK (novel_relevant >= 0),
    novel_irrelevant INTEGER NOT NULL CHECK (novel_irrelevant >= 0),
    novel_unreviewed INTEGER NOT NULL CHECK (novel_unreviewed >= 0),
    api_calls INTEGER NOT NULL CHECK (api_calls >= 0),
    cost_json TEXT NOT NULL CHECK (json_valid(cost_json)),
    notes TEXT NOT NULL,
    experiment_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    CHECK (previously_known + novel_candidates = candidates_returned),
    CHECK (novel_relevant + novel_irrelevant + novel_unreviewed = novel_candidates)
);

CREATE INDEX search_experiments_by_method
    ON search_experiments(method, executed_at);

CREATE TRIGGER search_proposals_immutable_update
BEFORE UPDATE ON search_proposals BEGIN
    SELECT RAISE(ABORT, 'search_proposals are immutable');
END;
CREATE TRIGGER search_proposals_immutable_delete
BEFORE DELETE ON search_proposals BEGIN
    SELECT RAISE(ABORT, 'search_proposals are immutable');
END;
CREATE TRIGGER search_proposal_support_immutable_update
BEFORE UPDATE ON search_proposal_support BEGIN
    SELECT RAISE(ABORT, 'search_proposal_support is immutable');
END;
CREATE TRIGGER search_proposal_support_immutable_delete
BEFORE DELETE ON search_proposal_support BEGIN
    SELECT RAISE(ABORT, 'search_proposal_support is immutable');
END;
CREATE TRIGGER search_proposal_queries_immutable_update
BEFORE UPDATE ON search_proposal_queries BEGIN
    SELECT RAISE(ABORT, 'search_proposal_queries are immutable');
END;
CREATE TRIGGER search_proposal_queries_immutable_delete
BEFORE DELETE ON search_proposal_queries BEGIN
    SELECT RAISE(ABORT, 'search_proposal_queries are immutable');
END;
CREATE TRIGGER search_proposal_decisions_immutable_update
BEFORE UPDATE ON search_proposal_decisions BEGIN
    SELECT RAISE(ABORT, 'search_proposal_decisions are immutable');
END;
CREATE TRIGGER search_proposal_decisions_immutable_delete
BEFORE DELETE ON search_proposal_decisions BEGIN
    SELECT RAISE(ABORT, 'search_proposal_decisions are immutable');
END;
CREATE TRIGGER search_experiments_immutable_update
BEFORE UPDATE ON search_experiments BEGIN
    SELECT RAISE(ABORT, 'search_experiments are immutable');
END;
CREATE TRIGGER search_experiments_immutable_delete
BEFORE DELETE ON search_experiments BEGIN
    SELECT RAISE(ABORT, 'search_experiments are immutable');
END;
