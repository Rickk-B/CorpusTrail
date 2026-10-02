CREATE TABLE screening_approval_invalidations (
    approval_id TEXT PRIMARY KEY REFERENCES screening_approvals(approval_id),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    identified_at TEXT NOT NULL,
    identified_by TEXT NOT NULL,
    invalidation_payload_sha256 TEXT NOT NULL UNIQUE
        CHECK (invalidation_payload_sha256 GLOB 'sha256:*')
);

CREATE TRIGGER screening_approval_invalidations_immutable_update
BEFORE UPDATE ON screening_approval_invalidations BEGIN
    SELECT RAISE(ABORT, 'screening_approval_invalidations are immutable');
END;

CREATE TRIGGER screening_approval_invalidations_immutable_delete
BEFORE DELETE ON screening_approval_invalidations BEGIN
    SELECT RAISE(ABORT, 'screening_approval_invalidations are immutable');
END;

CREATE TABLE screening_relation_invalidations (
    relation_id TEXT PRIMARY KEY REFERENCES screening_event_relations(relation_id),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    identified_at TEXT NOT NULL,
    identified_by TEXT NOT NULL,
    invalidation_payload_sha256 TEXT NOT NULL UNIQUE
        CHECK (invalidation_payload_sha256 GLOB 'sha256:*')
);

CREATE TRIGGER screening_relation_invalidations_immutable_update
BEFORE UPDATE ON screening_relation_invalidations BEGIN
    SELECT RAISE(ABORT, 'screening_relation_invalidations are immutable');
END;

CREATE TRIGGER screening_relation_invalidations_immutable_delete
BEFORE DELETE ON screening_relation_invalidations BEGIN
    SELECT RAISE(ABORT, 'screening_relation_invalidations are immutable');
END;
