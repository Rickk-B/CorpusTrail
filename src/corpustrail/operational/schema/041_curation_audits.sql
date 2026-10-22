-- CP9: researcher-owned immutable selections and explicit workflow lineage.
CREATE TABLE ct_curation_audits (
 sequence INTEGER PRIMARY KEY, audit_id TEXT NOT NULL UNIQUE,
 request_id TEXT NOT NULL UNIQUE, command_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE ct_curation_audit_members (
 audit_id TEXT NOT NULL REFERENCES ct_curation_audits(audit_id),
 position INTEGER NOT NULL CHECK(position>=0), paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
 payload_json TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 PRIMARY KEY(audit_id,position), UNIQUE(audit_id,paper_id)
);
CREATE TABLE ct_curation_sessions (
 session_id TEXT PRIMARY KEY REFERENCES ct_review_sessions(session_id),
 request_id TEXT NOT NULL UNIQUE, command_sha256 TEXT NOT NULL,
 audit_id TEXT NOT NULL REFERENCES ct_curation_audits(audit_id), payload_json TEXT NOT NULL
);
CREATE TABLE ct_curation_session_sources (
 session_id TEXT NOT NULL REFERENCES ct_curation_sessions(session_id),
 paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id), payload_json TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, PRIMARY KEY(session_id,paper_id)
);
CREATE TABLE ct_curation_workflow_events (
 sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, request_id TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL CHECK(kind IN ('reference_correction','reassessment')), payload_json TEXT NOT NULL
);
CREATE TABLE ct_curation_outcomes (
 link_id TEXT PRIMARY KEY, audit_id TEXT NOT NULL REFERENCES ct_curation_audits(audit_id),
 session_id TEXT NOT NULL REFERENCES ct_curation_sessions(session_id),
 paper_id TEXT NOT NULL REFERENCES paper_entities(paper_id),
 review_event_id TEXT NOT NULL REFERENCES ct_review_events(event_id),
 kind TEXT NOT NULL CHECK(kind IN ('observation','authorization')), payload_json TEXT NOT NULL
);
CREATE INDEX ct_curation_outcome_audit ON ct_curation_outcomes(audit_id,paper_id,review_event_id);
CREATE INDEX ct_curation_workflow_kind ON ct_curation_workflow_events(kind,sequence);
CREATE INDEX ct_curation_result_filter ON ct_classifier_results(run_id,kind,outcome,position);
CREATE TRIGGER ct_curation_audits_no_update BEFORE UPDATE ON ct_curation_audits BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
CREATE TRIGGER ct_curation_audits_no_delete BEFORE DELETE ON ct_curation_audits BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
CREATE TRIGGER ct_curation_audit_members_no_update BEFORE UPDATE ON ct_curation_audit_members BEGIN SELECT RAISE(ABORT,'immutable audit selection'); END;
CREATE TRIGGER ct_curation_audit_members_no_delete BEFORE DELETE ON ct_curation_audit_members BEGIN SELECT RAISE(ABORT,'immutable audit selection'); END;
CREATE TRIGGER ct_curation_sessions_no_update BEFORE UPDATE ON ct_curation_sessions BEGIN SELECT RAISE(ABORT,'immutable assisted session'); END;
CREATE TRIGGER ct_curation_sessions_no_delete BEFORE DELETE ON ct_curation_sessions BEGIN SELECT RAISE(ABORT,'immutable assisted session'); END;
CREATE TRIGGER ct_curation_session_sources_no_update BEFORE UPDATE ON ct_curation_session_sources BEGIN SELECT RAISE(ABORT,'immutable assisted source'); END;
CREATE TRIGGER ct_curation_session_sources_no_delete BEFORE DELETE ON ct_curation_session_sources BEGIN SELECT RAISE(ABORT,'immutable assisted source'); END;
CREATE TRIGGER ct_curation_workflow_events_no_update BEFORE UPDATE ON ct_curation_workflow_events BEGIN SELECT RAISE(ABORT,'immutable curation lineage'); END;
CREATE TRIGGER ct_curation_workflow_events_no_delete BEFORE DELETE ON ct_curation_workflow_events BEGIN SELECT RAISE(ABORT,'immutable curation lineage'); END;
CREATE TRIGGER ct_curation_outcomes_no_update BEFORE UPDATE ON ct_curation_outcomes BEGIN SELECT RAISE(ABORT,'immutable audit outcome'); END;
CREATE TRIGGER ct_curation_outcomes_no_delete BEFORE DELETE ON ct_curation_outcomes BEGIN SELECT RAISE(ABORT,'immutable audit outcome'); END;
