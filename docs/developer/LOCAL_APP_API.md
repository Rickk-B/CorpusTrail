# Checkpoint 1 application/read boundary

`application.ProjectReads` is an experimental operational read service. It returns
researcher-facing DTOs using one read-only SQLite transaction per operation.
`local_app` is a thin loopback transport and packaged frontend. No CLI subprocess,
HTTP-supplied SQL/path, plugin initialization, network execution or write capability
is used by a read. Core still has no runtime dependencies.

## Read functions

- `dashboard()` — aggregate overview, scope origin and separate status dimensions.
- `papers(limit=25, cursor=None, q='', sort='title', membership='', evidence='', review='')`.
- `paper(handle)` — bibliographic/evidence information, not raw provenance.
- `provenance(handle, section='bibliography', limit=25, cursor=None)` — explicit
  paginated technical access.
- `document(handle, representation_handle, offset=0, limit=16000)` — checked,
  bounded verified structured-body text. No pending/PDF/path-serving capability.

These DTOs deliberately expose operational sources/current membership. They are
**not** the response contract for method-blind review. That continues through
`review_sessions.view()` and the separate legacy server. No universal rich object
is shared with review packets; the existing review server source is unchanged.

## HTTP v1

An explicitly opened project is bound server-side. There is no project-path URL
parameter or browser filesystem chooser in this checkpoint.

| GET endpoint | Response |
|---|---|
| `/api/v1/dashboard` | Project summary |
| `/api/v1/papers` | Catalogue page |
| `/api/v1/papers/{handle}` | Normal detail DTO |
| `/api/v1/papers/{handle}/provenance` | Explicit advanced page |
| `/api/v1/papers/{handle}/evidence/{representation_handle}` | Trusted text segment |

Page routes are `/dashboard`, `/papers` and `/papers/{handle}`. Opaque link handles
are reversible components of already-minted canonical IDs, not recomputed title
or identifier hashes. Technical `ct-paper:` IDs appear only in advanced provenance.

Catalogue parameters: `limit` 1–100, `cursor`, `q` at most 300 characters,
`sort` title/year_newest/year_oldest, membership state, evidence band or pending/
mismatch flag, and human-review/draft-history filter. Unknown/repeated parameters
fail closed. Page order uses a canonical-ID tie-breaker; missing metadata sorts
last. Unicode case folding and literal substring matching avoid ASCII-only joins
and wildcard interpretation.

Cursor contents bind offset, filters/page size and a revision derived from config
and append-only relevant store heads/counts. Relevant changes return HTTP 409;
the client restarts. This is live read pagination, not candidate-population
persistence. Counts, filters and records are read in a consistent transaction.
Queries only materialize requested page DTOs into Python/browser memory. Aggregate
SQL may scan existing stores; this does not promise sublinear cost or production
throughput. Cursor tokens confer no write or filesystem authority.

## Scientific projection reuse

`discovery.service._catalogue_field_sql()` is the constrained internal bulk-query
equivalent of first-supported-nonempty metadata selection. Page/detail values and
canonical provenance come from the existing `_metadata()` selector.
`curation.service._catalogue_membership_sql()` selects latest human-authorized heads
for read filtering/counts; page histories/membership use `membership_in_connection()`.
`EvidenceService._status()` is the shared pure status projection, with unchanged
legacy `status()` output. Regression tests compare the bulk views to those services.

No HTTP handler constructs scientific SQL or interprets membership. Read repository
SQL is isolated in the application layer and uses fixed selectors, allowlisted sort
expressions and parameters. Draft-history summaries indicate existence of saved
draft updates, not complete/current drafts or new scientific outcomes.

## Security

Loopback only, exact single Host/Origin, Fetch-Metadata restriction, same-origin
resource policy, no-store, nosniff, no-referrer and restrictive CSP. HTML contains
only a static shell plus an ephemeral per-server session capability. API GETs
require that capability in a header; nothing goes into local/session storage.

There are no mutation routes. POST/PUT/PATCH/DELETE/OPTIONS/HEAD/TRACE/CONNECT are
rejected, even with a valid token; no write-CSRF endpoint exists. Existing review
write routes retain their own CSRF protections. Static asset names are allowlisted;
project artifacts are never served by caller-supplied path. Text enters DOM through
`textContent`, never provider/model HTML or eval. No CORS grant or automatic network
operation. Local privacy/security guarantees are bounded, not formal certification.

## Development and packaging

`corpustrail app PROJECT [--port 8766] [--open-browser]` starts the read browser.
Only explicit `--open-browser` invokes the standard browser launcher. No schema or
dependency changes. Assets are included declaratively in wheel/sdist and release
population allowlisting. The exact approved plan remains in
`docs/v0.1.0a3-implementation-plan.md`.

Run focused tests: `python -m unittest discover -s tests -p 'test_local_app.py'`.
The Node DOM test is optional test tooling already present in development; it is
not a runtime dependency or a native-browser visual test. All service/HTTP tests
are offline, using synthetic records and loopback sockets only.
