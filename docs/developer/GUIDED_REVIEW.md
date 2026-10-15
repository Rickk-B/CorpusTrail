# Guided review contract (Checkpoint 5)

The authoritative implementation plan §9 is unchanged. `curation.guided` adds
`deferred-human-publication/v1` over the established `SessionService` frozen packet,
draft validator, evidence allowlist and `ReviewService._apply` validator/projection.
It introduces `corpustrail-review-session/v2`, guided completion/publication/receipt
v1 payloads and versioned command receipts in the existing append-only
`ct_review_sessions` / `ct_review_session_events` ledger. No table, schema migration,
database, production dependency, provider or review taxonomy is added.

Legacy v1 sessions retain immediate per-paper authority according to their existing
policy. The legacy updater refuses v2 packets. Older software must not mutate v2
projects: older binaries cannot enforce a policy they do not know.

## Atomicity, identity and concurrency

Creation requires explicit reviewer, population choice/hash, configuration event
and mode. Packet v2 freezes population/evidence hashes and the actual corpus
definition. Canonical publication IDs, not provider rows, compose the population.
Command identities are 32 lowercase hexadecimal characters, scoped to the session;
creation derives a deterministic session ID from project identity and command.
Each command binds action, payload and expected session revision. A replay returns
the original receipt; changed input under the same identity fails. Successful
receipts survive restart. `BEGIN IMMEDIATE` serializes independent processes.

Save validates the existing evidence extent, draft and ReviewEvent, writes a
non-authoritative human observation, selected-draft association, navigation and
receipt in one transaction. No-ops for unchanged saved assessments do not duplicate
observations. Completion freezes exact selected observation IDs and explicitly
preserves undecided drafts. Completed sessions reject editing/navigation writes.

Publication preview freezes completion, selected events, reviewer, definition,
configuration/policy, evidence/population hashes, membership heads and complete
paper-history hashes. Confirmation strictly requires the plan hash and explicit
authority boolean. Authority, revision, evidence and history are revalidated. Each
new authoritative event uses the current membership head as `supersedes`, NOT the
non-authoritative source observation. Explicit observation-to-authority links and
all projections/receipts commit atomically. Any failure rolls back the entire batch.
There is no automatic membership, exclusion, retry or cloud operation.

## Application boundary

`application.review.ReviewController` supplies bounded allowlisted DTOs. Versioned
loopback routes use the unchanged Host/Origin/session/CSRF/CSP/body-size protections:

- GET `/api/v1/review/configuration?offset=0&limit=20`: populations and session list.
- GET `/api/v1/review/sessions/<opaque handle>`: frozen current paper and own draft.
- GET `.../<handle>/summary?offset=0&limit=20`: paginated own saved judgments;
  prior membership heads only after explicit operational publication preview.
- GET `.../<handle>/document?offset=0&limit=16000`: confined hash-verified plain text.
- POST `/api/v1/review/create`: explicit frozen session creation.
- POST `/api/v1/review/command`: `draft`, `save_next`, `navigate`, `skip`, `open`,
  `finish`, `prepare_publication`, `publish` with revision and command identity.

No filesystem paths, generic fetches or operational method-rich paper DTOs enter
the method-blind workspace. Summary and session lists are paginated; document
segments are bounded. Ledger replay/packet loading still scales with session size;
this checkpoint does not add a job system or large-import population architecture.
Each HTTP project operation holds `ProjectController.use()` and its shared lease
until the transaction/response work completes. Close waits; another cooperating
process still blocks exclusive Trash. Browser closure cannot truncate an accepted
transaction. The UI autosaves drafts, serializes commands, retains failed input,
prevents double-click submissions and retries uncertain requests using the same ID.

The refinement changes presentation only: disabled native extent placeholder;
friendly labels for the existing `sections`/`full_document` values; completed
sessions open the existing summary DTO rather than disabled assessment forms.
Finish redirects only after a `completed` receipt to a dashboard fragment binding
the session handle. The dashboard validates that handle/status through the existing
protected read API before showing feedback. There is no redirect-side command.
Publication confirmation is visible only following explicit preview preparation
in that page, not merely because a stored plan hash exists. Back/refresh hide it;
the existing nonce, revision, atomicity and authorization contracts are unchanged.
No review service, DTO, schema, migration or scientific source hash changes.

Read-only APIs never mutate scientific files. The browser keeps only temporary
form state, never authoritative scientific state in localStorage. Scientific unit
tests cover rollback, full-history CAS, real independent-process saves, source
links, legacy authority, method blindness, security and active operation leases.
Playwright uses real controllers/services with disposable fixtures and no providers.
