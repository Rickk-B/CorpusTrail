# CP9 curation workflow and boundary

The approved implementation plan is unchanged. CP8 infrastructure is researcher-
accepted at d2ade7e3840236d4fdb3dba672380efe1dcac632 / run 39612709296/1.
CP9 technical completion does not grant researcher acceptance.

`classification.curation_views` supplies bounded SQL primary/overlay views over
the existing immutable input/result stores. `classification.curation` freezes
audit protocols/members, records explicit correction/reassessment lineage and
composes existing Guided Review and ReferenceService operations. It does not
introduce another review taxonomy, classifier, membership store or truth source.

Migration 041 is additive after frozen 001–040. Existing schema-37 through -40
projects open read-only-compatible without migration. Explicit Project.upgrade
checks configuration, creates a SQLite backup before migration and applies the
pending migration atomically. Backup preservation means identical scientific
schema/data, not identical SQLite file-header counters. All CP9 event/selection
tables are append-only; normalized audit rows hash into immutable chunk manifests.
No full evidence copy is stored. Results remain CP8-owned; evidence remains in
existing content-addressed storage. New tables and artifacts are researcher-owned.

## Transactions, concurrency and reproducibility

Audit preview is read-only. Commit compares the exact source revision/preview
and binds a command ID to its immutable input. Random selection uses SHA-256 over
the recorded integer seed, stratum and exact canonical paper ID, choosing smallest
hashes with deterministic ties. Strata are applied after explicit filters, and
their denominators/fractions/overlap and selected result IDs are preserved.
Heap selection is bounded per sampling unit; it does not load the entire result
collection into Python or the browser. There is no scientific collection cap.

Assisted session creation first creates a reproducible selected-candidate version
through PopulationService, then binds Guided Review in one database transaction.
Interruption between those stages can leave a named frozen population, not a
partial observation or decision. Same command replay uses that population and
session. Source assessments and the fresh human evidence snapshot are explicitly
different, never silently reconciled. Save/authorization plus CP8 authority links
commit in the same transaction; a link failure rolls back the human operation.
The original engine producer remains immutable. Failed/not-assessed sources are
not promoted into engine judgments. Existing Guided authorization/replay guards
remain authoritative. Generic Guided writes refuse attached assisted sessions.

Reference correction uses ReferenceService's existing preview/commit validation
inside the workflow transaction. Same-paper active labels are explicitly
superseded, with human attestation and exact immutable run/result/audit source
lineage. Reassessment records parent/new run and old/new reference/population
versions atomically with CP8.start_run; execution is a separate request. The UI
inherits policy, settings, budgets and validation roles from the selected parent,
not a trained model or a fresh independent validation claim.

## Local API

`corpustrail-local-curation/v1` uses existing loopback authentication, CSRF,
Origin/Host/CSP, project confinement and lease guards. GET configuration, runs,
run/results, exact run/paper target/reference/provenance, audits/members, outcomes,
sessions and workflow history are read-only. Lists use at most 100 rows; text
segments use at most 32,000 Unicode characters. Append histories have immutable
cutoffs; live result pagination requires a matching revision. Technical source
IDs remain secondary. POST commands use strict allowlisted fields and explicit
preview hashes/command identities. No arbitrary code, file or URL endpoint exists.

`/api/v1/curation/review/` is the operational assisted boundary. Existing
`/api/v1/review/` listing/detail/document/summary routes refuse attached assisted
sessions. The assisted boundary similarly refuses ordinary method-blind sessions.
No proposal is prefilled as a human answer or evidence-reading attestation.
Only the existing authorized Guided publication command can publish membership.

Bounded offline execution is explicit, cancellable, lease-protected and never
silently restarted. The production registry stays empty. Tests inject synthetic
engines below the application API, never mock scientific responses. All browser
requests are loopback-only; backend provider transports are separately blocked.
The existing two-thousand-reference acceptance tool now measures CP9 SQL/result
pagination, deterministic frozen audit storage and restart without judgments.
An initial WSL/Linux Python 3.12.3 measurement used 2,000 candidates/references:
20 result pages of 100, maximum response 94,895 bytes, 100 selected audit rows,
1,105,923 Python-traced peak bytes and 0.914 seconds for the CP9 stage (not the
whole CP7/8 fixture build). Shared project database: 66,117,632 bytes. This is a
dated synthetic observation, not a production capacity/performance guarantee.
The executable tool regenerates measurements and fails bounds/invariants in CI;
the collection has no corresponding 2,000-paper cap.
Fixtures establish architecture only. CP10 and real model/import tracks remain
separately gated; native Europe PMC causation remains unresolved.
