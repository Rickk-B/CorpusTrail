# Checkpoint 6 population contracts

`corpustrail-candidate-population/v1`, `exact-canonical-union/v1` reuse identity,
enrollment, pipeline integrity and membership projections; no new identity engine.
Migration 038 adds immutable version/member/lineage/issue/parent/review-link tables
to the scientific SQLite database. Migrations 001–037 remain unchanged. Schema-37
reads remain compatible without writes; explicit backed-up `Project.upgrade` enables
new functionality. Prefix history with existing population tables fails closed.
Older builds cannot open schema 38. Nothing historically backfills/reclassifies.

Content-addressed headers, row hashes and manifests bind exact identity/lineage.
UPDATE/DELETE triggers prohibit ordinary mutation; hashes detect corruption, not a
hostile rewrite of the entire user-controlled database. Sorted canonical IDs,
origins, issues and parents give source-order-independent unions. Version identity
also binds attribution/time/request. Source rules freeze observation and source
hashes, discovery plan/completion hashes and membership-selection heads. Unlinked
records stay separate with explicit acknowledgment, including through unions.

Preview is read-only; creation recomputes under BEGIN IMMEDIATE, checks preview
hash/config/family head, and commits all rows atomically. Durable request IDs reject
changed input and replay identical committed requests after restart/source changes.
Crashes roll back; no automatic retry/resume. Controllers hold existing project-use
leases throughout. Read pages are indexed/bounded with stable list cutoffs. Explicit
verify/union/review creation validate full manifests and use O(selected content)
memory; preparation can inspect historical discovery links. Pagination is not an
unbounded-ingestion or performance-benchmark claim.

`ImportedSource` references an already preserved hash-verified artifact and already
enrolled observations tied to it. `freeze_import_source` shares the common path.
No format parser, ingestion executor, upload or file browser ships. Future adapters
must preserve raw records/normalization failures before using this interface.

Guided Review additionally accepts `population-version:<sha256>` as its existing
selection field. Active exact IDs/member digest are checked, then unchanged
SessionService freezes evidence. A normalized immutable link and append-only
creation receipt both bind the opaque population reference in one transaction.
Views/commands validate both. Legacy/all/awaiting sessions retain their semantics.
Blinded DTOs contain only opaque version ID, number and hash, not names/methods.
Operational population browsing remains outside the blinded workspace.

GET `/api/v1/populations/configuration`, `/versions`, `/versions/<64hex>` and its
`/members`, `/lineage`, `/issues` use bounded offset/limit and list cutoffs.
POST `/api/v1/populations/preview`, `/create`, `/verify`, `/upgrade` are strict
allowlisted JSON commands under existing Host/Origin/CSRF/session/body-size,
confinement and lease checks. Import-interface sources cannot be submitted over
HTTP. No file-read/upload/URL-fetch endpoint is added. Metadata is rendered as text.
Upgrade requests must repeat the project ID and configuration event returned by
the displayed configuration; stale project selections/revisions are refused before
backup or migration. A stale tab cannot upgrade another active project.

Acceptance: `test_populations.py`, `test_population_app.py`, and
`tools/browser_acceptance.py --suite population` use actual services, offline
providers and synthetic adapters. Existing review/evidence/discovery/lifecycle
coverage remains mandatory; CI never approves screenshot baselines.
