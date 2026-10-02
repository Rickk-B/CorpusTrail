CREATE TABLE adaptive_search_campaigns (
    campaign_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    starting_manifest_revision TEXT NOT NULL REFERENCES manifest_snapshots(revision),
    required_clusters_json TEXT NOT NULL CHECK (json_valid(required_clusters_json)),
    max_rounds INTEGER NOT NULL CHECK (max_rounds > 0),
    max_experiments INTEGER NOT NULL CHECK (max_experiments > 0),
    max_api_calls INTEGER NOT NULL CHECK (max_api_calls > 0),
    max_api_usd REAL NOT NULL CHECK (max_api_usd >= 0),
    max_llm_tokens INTEGER NOT NULL CHECK (max_llm_tokens >= 0),
    minimum_reviewed_novel_fraction REAL NOT NULL CHECK (
        minimum_reviewed_novel_fraction BETWEEN 0 AND 1
    ),
    maximum_low_yield_novel_relevant INTEGER NOT NULL CHECK (
        maximum_low_yield_novel_relevant >= 0
    ),
    consecutive_low_yield_rounds INTEGER NOT NULL CHECK (
        consecutive_low_yield_rounds > 0 AND consecutive_low_yield_rounds <= max_rounds
    ),
    campaign_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256)
);

CREATE TABLE adaptive_search_rounds (
    round_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES adaptive_search_campaigns(campaign_id),
    round_number INTEGER NOT NULL CHECK (round_number > 0),
    previous_round_id TEXT UNIQUE REFERENCES adaptive_search_rounds(round_id),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    open_gaps_json TEXT NOT NULL CHECK (json_valid(open_gaps_json)),
    provider_failures_json TEXT NOT NULL CHECK (json_valid(provider_failures_json)),
    notes TEXT NOT NULL,
    round_artifact_sha256 TEXT NOT NULL REFERENCES raw_artifacts(sha256),
    UNIQUE (campaign_id, round_number),
    CHECK ((round_number = 1) = (previous_round_id IS NULL))
);

CREATE TABLE adaptive_search_round_proposals (
    round_id TEXT NOT NULL REFERENCES adaptive_search_rounds(round_id),
    campaign_id TEXT NOT NULL REFERENCES adaptive_search_campaigns(campaign_id),
    proposal_id TEXT NOT NULL REFERENCES search_proposals(proposal_id),
    PRIMARY KEY (round_id, proposal_id),
    UNIQUE (campaign_id, proposal_id)
);

CREATE TABLE adaptive_search_round_experiments (
    round_id TEXT NOT NULL REFERENCES adaptive_search_rounds(round_id),
    campaign_id TEXT NOT NULL REFERENCES adaptive_search_campaigns(campaign_id),
    experiment_id TEXT NOT NULL REFERENCES search_experiments(experiment_id),
    PRIMARY KEY (round_id, experiment_id),
    UNIQUE (campaign_id, experiment_id)
);

CREATE INDEX adaptive_rounds_by_campaign
    ON adaptive_search_rounds(campaign_id, round_number);

CREATE TRIGGER adaptive_search_campaigns_immutable_update
BEFORE UPDATE ON adaptive_search_campaigns BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_campaigns are immutable');
END;
CREATE TRIGGER adaptive_search_campaigns_immutable_delete
BEFORE DELETE ON adaptive_search_campaigns BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_campaigns are immutable');
END;
CREATE TRIGGER adaptive_search_rounds_immutable_update
BEFORE UPDATE ON adaptive_search_rounds BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_rounds are immutable');
END;
CREATE TRIGGER adaptive_search_rounds_immutable_delete
BEFORE DELETE ON adaptive_search_rounds BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_rounds are immutable');
END;
CREATE TRIGGER adaptive_search_round_proposals_immutable_update
BEFORE UPDATE ON adaptive_search_round_proposals BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_round_proposals are immutable');
END;
CREATE TRIGGER adaptive_search_round_proposals_immutable_delete
BEFORE DELETE ON adaptive_search_round_proposals BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_round_proposals are immutable');
END;
CREATE TRIGGER adaptive_search_round_experiments_immutable_update
BEFORE UPDATE ON adaptive_search_round_experiments BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_round_experiments are immutable');
END;
CREATE TRIGGER adaptive_search_round_experiments_immutable_delete
BEFORE DELETE ON adaptive_search_round_experiments BEGIN
    SELECT RAISE(ABORT, 'adaptive_search_round_experiments are immutable');
END;
