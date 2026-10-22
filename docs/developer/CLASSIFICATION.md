# CP8 assessment infrastructure

Checkpoint 8 implements optional engine contracts and scientific storage. CP9's
assessment-result, audit and assisted-curation UI is documented in [CURATION.md](CURATION.md). Manual
review remains usable without an engine. The default registry is empty; no real
classifier, model runtime, embedding index or provider is installed or selected.
Deterministic engines in tests and development tools are software fixtures only.

## Boundaries

`AssessmentEngine.describe()` declares immutable implementation/version hashes,
the adapter/provider/configured model, input modes, score types and locality.
`prepare(EngineRequest)` returns a typed `AssessmentPlan` bound to the exact
request, engine and settings hashes. `assess(plan, chunk)` receives bounded
`ExecutionUnit` objects and returns one typed `Assessment` or `AssessmentFailure`
per candidate. There is no engine-directed tool, URL, shell or file operation.

Installed Python engines are trusted code, as with existing model adapters. This
interface minimizes capabilities; it does not sandbox a malicious installed plugin.
Core performs no plugin discovery, network dispatch, model download, retraining,
hybrid routing or fallback. Only explicitly registered **offline** engines are
executable in CP8. `remote_declared_mock` tests consent while remaining offline;
it is not a supported remote model connection.

Engine outputs never update identity, trust, reviews, ranking, Knowledge truth,
membership or ASReview. Unknown schemas/fields, another paper, unsupported scores,
out-of-plan evidence and authority claims are refused as execution failures.
Failures have no scientific outcome. Missing abstracts/full text never trigger an
exclude: the default explicit evidence rule falls back to metadata, and engines
must report sufficiency/uncertainty independently. An exclude claiming insufficient
or unknown evidence is rejected. Metadata itself can be an explicitly sufficient
basis; this service does not invent scientific relevance rules.

## Frozen requests and persistence

`ClassificationService.prepare(...)` is a read-only preview with no engine
assessment or scientific write. `commit_plan(expected_preview_sha256=..., ...)`
rechecks configuration, exact population/identity, reference eligibility and input
hashes atomically. Changed input requires a new plan. Completed identical commands
replay their original record even after later evidence/reference changes.

Every plan preserves the population and reference version/manifests, actual corpus
definition/configuration revision, evidence selection, software/implementation,
engine/model declarations, settings, policy, budgets, calibration state and exact
request artifact. Candidate input rows link frozen evidence snapshots and hashes.

- `full_set` uses the complete eligible human-attested, unconflicted reference
  version after explicit calibration/held-out/self exclusions. Shared reference
  text is stored once by content hash and streamed in exact recorded order. Per
  target manifests preserve the actual selected hash sequence; no reference text
  is copied into each candidate row.
- `bounded_context` requires an existing immutable CP7 context for every candidate
  and `evidence_basis='frozen_context'`. Its exact original text, passages, ranks,
  omissions, derived dependencies and hashes remain the input. Later evidence or
  reference versions never expand it. A context violating a split, scope,
  eligibility or self-match policy is rejected.

`exact_request`, `exact_input`, `reference_inputs`, `validation_protocol`,
`verify_plan` and `verify_run` support explicit provenance inspection. Normal plan,
input, run and result lists are server-side pages (1–100 records), ordered by frozen
identity/position or append sequence. Reference text pages stop at a one-MB soft
budget, allowing one explicitly bounded record; no text is silently truncated.
These library services are operational views, never reused as blinded-review DTOs.

The large synthetic probe exposed a SQLite reader/writer lock when CP8 tried to
verify a selected context through a second connection after inserting plan rows.
The CP7 context integrity checks now also have a connection-aware entry point;
both the existing inspector and CP8 use the same checks within their transaction.
No context schema, selection rule, evidence or historical record is changed.

Migration **040** is additive after frozen migrations 001–039. Immutable SQL
triggers protect plans, blobs, inputs, attempts, lifecycle events, assessments,
failures, validation and calibration records. No second Knowledge truth store is
created. A reserved authority-link table accommodates later explicit human events;
CP8 exposes no membership-publication or authority-creation action.

Schema-37/38/39 projects open without migration. Existing workflows remain readable.
New classifier writes require an explicit upgrade with a new project-relative
backup, through the existing `Project.upgrade`/`corpustrail project upgrade PATH
--backup backups/before-classification.sqlite3` operation. An upgrade retains the
pre-upgrade database before the additive transaction; stale configuration and
interrupted migration fail closed. Downgrading software does not undo a migration.
All these stores and artifacts are researcher-owned scientific data under plan
Section 19; application removal/cache cleanup does not delete them.

## Explicit execution and recovery

Register an approved installed implementation in an `EngineRegistry`, then supply
it to `ClassificationService(project, registry=registry)`. `Project.classification`
provides read/inspection services with an empty registry by default. Plan arguments
use exact service-returned version IDs, a fresh 32-hex command ID, actor/timestamp
and current configuration event. Example protocol execution:

```python
preview = service.prepare(**fields)
plan = service.commit_plan(**fields, expected_preview_sha256=preview['preview_sha256'])
run = service.start_run(plan['plan_id'], request_id=fresh_command_id,
                        actor=actor, created_at=timestamp)
state = service.inspect_run(run['run_id'])
state = service.execute(run['run_id'], expected_revision=state['revision'])
```

Planning/starting does not execute an engine. A remote-declared offline mock also
requires `transfer_sha256=plan['transfer_sha256']`, which covers the exact candidate,
reference/context, definition, settings and engine inputs. Connection-test consent
is insufficient, and changed payloads need a new plan/consent.

Execution holds the existing shared project-use lease plus a per-run OS lease.
Different runs may proceed independently. Each bounded chunk is reserved before
the callback, with no scientific write transaction held during engine execution.
Results commit atomically per chunk. Configuration, engine and lifecycle guards
are checked before each new chunk. A completed retry returns preserved results;
independent run commands remain distinct even when outcomes agree.

Item/byte/reference budgets are explicit. A cooperative wall-time budget is checked
between safe chunks; it cannot forcibly interrupt arbitrary installed Python code.
A real adapter must additionally honor its declared invocation bounds. Budget or
user cancellation leaves not-attempted candidates visible for explicit continuation.
Counts distinguish include/exclude/uncertain/failed/not-assessed without hiding the
tail. Sufficiency overlays are separate. No stopping-rule claim is made.

Process death releases the OS lease but preserves outstanding invocation
reservations. `recover(run_id, expected_revision=..., actor=..., created_at=...)`
requires explicit inspection, records `interrupted_no_response` for those attempted
items and never resends them. A subsequent explicit execution handles untouched
items. Failure replay requires a new linked run, not overwriting earlier results.
Parent runs link same-paper original assessment IDs while preserving independent
producers; this is lineage, not an implemented hybrid classifier graph.

Safe bounded rejected JSON is retained as untrusted response evidence. Sensitive,
non-JSON or excessive output is not persisted; a sanitized retention reason remains.
Raw exceptions, stack traces, credentials and arbitrary object representations are
not written into scientific records.

## Scores, calibration and audit hooks

`Score` distinguishes similarity, engine-reported classifier probability,
model-reported confidence and calibrated probability. There is no implicit 0.5
threshold. Optional explicit score bands must be non-overlapping, finite and
consistent with their direction. Scores cannot establish corpus authority.

`ValidationProtocol` freezes operational/calibration/held-out roles, exact versioned
populations, human assignment/event sources and availability cutoff. Calibration
and held-out populations must be disjoint; both are excluded from reference input.
Independent evaluation also requires self exclusion, complete candidate-role
coverage and uncontaminated context. Answers are in a separate immutable snapshot
that is never passed to engines. No ASReview labels or insufficient judgments are
converted to negatives.

`validate(run_id)` records immutable denominators, confusion counts, abstentions,
failures and missing cases against that frozen protocol. Training/operational
agreement cannot masquerade as independent validation. A tiny/synthetic or repeatedly
corrected test set does not establish scientific recall or reliable exclusion.

`CalibrationBinding` preserves exact calibration-run/protocol, score, settings,
producer and JSON artifact lineage with **unvalidated** state. CP8 does not fit a
calibrator or grant statistical validation. Such a binding never licenses a
`calibrated_probability` claim; a real validated calibrator remains a separate
integration decision. Other typed scores retain their explicit uncalibrated meaning.

`AuditProtocol` and the read-only `audit_preview` hook preserve run/population,
filters/strata, seed and actual selected paper/result IDs. Overlap and denominators
are explicit. CP9 will provide persistence of audit outcomes and human correction
UI; CP8 does not implement that workflow or claim a biased sample is unbiased.

## Verification and limits

Focused tests cover interchangeable fixtures, both input modes, exact identities,
source/context lineage, conflicting observations, replay, restart/concurrency,
partial failures, corruption, validation leakage, consent and backed-up migration.
`tools/classification_acceptance.py` also runs the existing CP7 2,000-reference
acceptance and measures paginated candidate inputs, shared storage, streaming
full-set inputs and bounded contexts. Measurements describe the recorded synthetic
environment; they are not a throughput guarantee or scientific model validation.

The WSL2/Python 3.12.3 development measurement enrolled 2,000 exact synthetic
publications and references, froze a 2,000-input plan, and inspected all 20 pages
of 100 inputs. The largest page was 192,151 bytes. Two interchangeable full-set
fixtures and one bounded-context fixture each executed seven candidates in chunks
of at most three. CP8 planning/execution/inspection took 24.18 seconds after the
CP7 fixture setup. The combined project database was 65,925,120 bytes, including
the original CP7 history; 4,026 shared classifier blobs occupied 2,900,358 bytes.
These are measured synthetic workloads, not 2,000 scientific predictions.

An earlier probe copied every eligible reference evidence hash into each target
row: a 100-input page reached 14,984,851 bytes and the database 362,979,328 bytes.
The final representation instead resolves allowed reference evidence through the
exact shared selection manifest, retaining identical citation validation without
quadratic per-target hash duplication. Failed/intermediate probes are retained in
the development evidence, rather than silently replaced by the final measurement.

No new UI assets or visual references are required by CP8. Browser acceptance
adds actual offline service execution after the existing reference-context workflow,
then verifies the actual method-blind API and restart. Existing strict comparisons
and the earlier separately approved path-only exception retain their meaning.
