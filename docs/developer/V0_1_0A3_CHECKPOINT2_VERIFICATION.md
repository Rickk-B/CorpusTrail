# v0.1.0a3 Checkpoint 2 — guided project/configuration verification

Development version: `0.1.0a3.dev0`. Branch:
`development/v0.1.0a3-read-only-local-ui`. Accepted Checkpoint 1 baseline:
`88fd3b9e787de869187d72bb7e0c3d634bacf53f`.
This is not a release or authorization for Checkpoint 3.

## Implemented boundary

Packaged wizard/settings → `/api/v1/` → `application.projects.ProjectController`
→ existing `Project.create/open/configure`, typed configuration and revision guards.
No scientific service, database schema/migration, production dependency, model,
provider, evidence resolver or review-session implementation changed. No approved
specification text was shortened or rewritten.

New Project uses six readable steps: information/location; explicit broad-topic
scope; installed discovery providers/search concepts; evidence resolver; reviewer
pseudonym and independently optional authority; final summary/explicit creation.
Project Settings reuses these sections, shows saved/unsaved state, a change summary,
explicit authority confirmations, session-impact acknowledgment where applicable,
and an explicit save. Successful saves append existing configuration events.
Legacy absent scope is preserved, not inferred from project name. Separate
inclusion/exclusion fields are not invented: narrative criteria use existing scope.

Reviewer pseudonym records configuration authorship. It is not a new implicit
administrator/default-reviewer field. Initial authority is opt-in and confirmed.
Settings saves never publish membership or reinterpret historical packets.

The old paper browser remains read-only. `make_server(project)` retains a read-only
compatibility mode. `corpustrail review serve` and method-blind DTOs are unchanged.

## Local tests and acceptance

Local platform: Linux / Python 3.12.3. Existing validation constraints used for
build tools and clean optional-ML dependencies; no product dependencies added.

| Surface | Result |
|---|---|
| New project/controller/HTTP/packaged-JS tests | 33 passed |
| Existing local-app/read/pagination/provenance/security tests | 29 passed |
| Complete standalone source suite including installed optional ML | 379 passed, no skips |
| Independent wheel core full suite | 379 run; passed, 46 optional-ML skips |
| Independent wheel + ML full suite | 379 passed, no skips |
| Independent sdist→wheel core full suite | 379 run; passed, 46 optional-ML skips |
| Independent sdist→wheel + ML full suite | 379 passed, no skips |
| Core/ML wheel/sdist offline tutorials, explicit CLI initialization/version | Passed |
| Sdist uninstall/reinstall and project reopen | Passed; project status preserved |
| Existing review, method-blind, Knowledge, model, identity, evidence, ASReview regressions | Passed in complete suites |
| Existing 20,000-record bounded catalogue test | Passed; no throughput claim |
| Ruff correctness gate; JavaScript syntax; Git whitespace check | Passed |
| Actual temporary ASReview 2.2 import/exact-ID mapping | 3 records; corpus database unchanged; no network |

The browser-flow acceptance uses actual packaged JavaScript, a small Node DOM
contract harness and the real loopback API. It completes the six-step wizard,
selects a real installed provider/resolver, creates the project, simulates a lost
creation response, retries the identical receipt without duplication, opens
settings and saves version 2 without editing JSON or copying scientific IDs.
This tests actions/data, not native browser layout. Changes persist on reopening.

Separate five-paper preservation fixture: duplicate-looking titles, one missing
abstract, a pending document, five recorded non-authoritative human reviews and
zero published corpus decisions. Entry/open/dashboard/catalogue/detail/provenance
leave before/after file SHA-256 maps identical. Explicit permitted configuration
updates leave all scientific tables unchanged; only configuration lineage and
SQLite's configuration sequence bookkeeping change. Bootstrap and review packets
remain unchanged. Earlier session updates correctly reject the new config revision.
Scope changes after authority remain rejected with identical file fingerprints.

Native macOS wizard visual acceptance has **not** been performed here; the tester
will use the hosted development artifact. Accepted Checkpoint 1 Mac results are
not represented as native validation of the new wizard.

## Security/privacy

Verified: loopback binding, Host/Origin/session/CSRF rejection, bounded JSON,
duplicate-key/unknown-version rejection, no permissive CORS, retained CSP, safe
text rendering, no remote frontend assets/storage, strict registered handles,
portable child-folder names, traversal/reserved-name/symlink rejection, permission
error redaction, existing-folder no-overwrite, partial-creation preservation,
concurrent/replayed-create deduplication, stale writes/no-op saves, no implicit
authority, no network on setup/settings/open, and credential non-persistence.
Credential environment-variable names only are accepted. Known configured runtime
secrets and credential-like signatures/fields are rejected without echoing values.
These safeguards are not a general PII detector or formal security certification.

Changed product files pass the existing privacy heuristics with no findings.
MIT project attribution, omitted personal package author/maintainer fields and
absent CITATION metadata remain unchanged. Commit identity is verified separately
as `CorpusTrail <noreply@corpustrail.invalid>`, repository-local only.

## Storage and limitations

Default root: `~/CorpusTrailProjects`, shown before creation. A different root or
outside-root existing project must be explicitly enrolled at launch. No arbitrary
browser filesystem picker, automatic migration, project deletion or uninstall
operation is provided. Missing roots are not created by GET/navigation.

Project registry, one active-project selection and 256 successful retry receipts
are memory-only. No new persistent application settings/cache/log location is
introduced. A restart loses those receipts; durable exclusive directory creation
and config CAS still prevent overwriting/replaying stale changes. Partial creation
is retained for inspection, not automatically repaired/deleted. Same-user hostile
filesystem races are outside this confinement guarantee; this is not an OS sandbox.

Unedited model/extension/policy/retry/custom-adapter fields are preserved. New guided
keywords default to the existing English-language convention; advanced language
and alias editing remain API/CLI work. Existing language/aliases/identifiers are
preserved for unchanged labels. UI command bodies are limited to 64 KiB.

One running launcher has one active project. Configuration writes carry explicit
enrolled project handles/revisions; avoid unrelated project tabs in that launcher.
API contracts are experimental/versioned, not a 1.0 stability promise.

No discovery execution, evidence acquisition/enrichment, new review lifecycle,
population/reference/classifier/import/model/MCP/desktop functionality is included.
No real model-server interoperability or scientific validation claim is made.

## Hosted receipt boundary

The approved workflow validates Python 3.11, 3.12 and 3.13 before building/uploading
the development artifact. Its receipt records original implementation
`6e116118f05e53ec3694c60e9171cb873a437bf8`, earlier distribution
`7086456aabd4c4edd124bddc12d6fb93ecf5017e`, accepted Checkpoint 1
`88fd3b9e787de869187d72bb7e0c3d634bacf53f`, and the **actual source/build SHA**.
It does not describe this Checkpoint 2 wheel as built from those earlier commits.
Hosted run ID, exact artifact name/checksum and matrix conclusions are provided
by the run/receipt and completion report, not guessed into this pre-push document.
No tag, release, main merge or PyPI publication is part of this checkpoint.
