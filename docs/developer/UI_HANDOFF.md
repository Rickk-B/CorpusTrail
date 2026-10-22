# CP10 UI handoff contracts

`application.handoff.HandoffController` composes existing Prioritization,
Knowledge, ModelService and ASReview services. It adds no scientific schema,
engine, ontology, document trust or membership authority. Schema 001–041 and
their integrity manifests are unchanged. Older projects are not upgraded on open.

Packaged `handoff.html`/`handoff.js` serve Review order, Knowledge, Models and
Export. Explore is a presentation alias of Discovery, not a renamed scientific
plan/API or a rewrite of historical queries. Shared server-rendered navigation
shows available capabilities; the legacy read-only server does not advertise
unavailable writers. Primary navigation stays small; operational tools remain
separate from method-blind Review/Curation packet APIs.

## Protected versioned local API

`/api/v1/tools/` uses `corpustrail-local-handoff/v1`, the existing loopback,
Host/Origin, session/CSRF, CSP and no-CORS policies. There are no arbitrary path,
URL-fetch or generic upload/download endpoints. JSON commands have the existing
64 KiB body ceiling and explicit field allowlists. Errors are sanitized; no raw
stack trace, credential value, request header or environment dump is returned.

- GET `configuration`, `export-summary`; `knowledge`, `rankings`, `exports`,
  `operations`, `connections`, `extractions`, `mappings`: bounded pages, no writes.
- Knowledge detail, exact-record segments, related observations and history:
  exact existing identity, never a title/row join. Selected read support retains
  native hash/authority verification; default Knowledge views are unchanged.
- Native model/connection histories include saved CLI records. Record excerpts
  are labelled; they do not claim to replace the native exact plan/provenance.
- Ranking scores are paginated; frozen training/model/ranking source records can
  be inspected in exact, hash-identified segments. No low-ranked tail is hidden.
- POST `prepare`: explicit form to immutable, hash-bound preview; `execute`:
  matching preview plus explicit confirmation and exact remote-transfer consent
  where required. Inspection never invokes a registered adapter.
- `results-upload`: only selected returned ASReview CSV bytes, 32 KiB chunks,
  exact offsets/retry checks and final SHA-256, explicit 128 MiB resource budget.
  No literature import or automatic parsing/publication. Native exact mapping
  and supported-version rules still decide whether the explicit mapping succeeds.
- `download/{export}/{filename}`: session-protected verified native export only;
  fixed three-file allowlist and 128 MiB response budget. Symlinks, incomplete
  output and hash mismatch are not verified downloads.

## State, concurrency and ownership

Prepared/started/completed receipts and native plans live in the project's
configured data directory under `handoff-workflows/v1`. They are researcher-owned
provenance, not application cache. Project/configuration revisions bind previews.
Native plans retain their own hashes/guards. Separate cooperative operation and
project-use leases prevent cross-process duplicate writers or project removal.
Workers retain a project lease until their native operation finishes, including
failure. Shutdown joins them instead of silently abandoning scientific writes.

Exact completed retries return stored results. A reservation without completion
is interrupted, not automatically resent. Native operations decide their own
atomicity. Ordering has snapshot/train/rank stages: earlier successful stages
remain if a later stage fails, with stage receipts; there is no invented rollback.
An export's snapshot/CSV/receipt are verified by the existing service. Partial
exports remain visible as incomplete, not repaired or silently deleted.

List pages are limited to 100 rows; exact text segments to 32,000 characters.
Live Knowledge/history pagination carries a revision and rejects stale continuation.
Native immutable ordering artifacts are still loaded by the existing service;
UI paging bounds the response, not a claim of streaming its legacy algorithm.
File-backed operation inventories enumerate receipt names, not an independent
scientific index. Very deep native histories may still be expensive.

Model configuration is separate from installed capability, credential presence,
connection success and scientific validity. Workflow/model names retain the
existing non-secret identifier contract. Remote services may charge; no paid
service is required. Existing compatible-endpoint code remains experimental;
offline wire fixtures do not validate any real service or classifier.

## Acceptance and preservation

Tests use actual services, disposable stores and packaged assets. The only fake
wire/ranking adapters are injected below authoritative services and visibly
labelled synthetic. No scientific API response is mocked. The five-paper review
fixture now contains six source observations, exact overlap, a DOI-missing paper,
similar-looking distinct records, two abstract-best papers, verified structured
text and pending material. It continues through separate membership confirmation,
two-member unlabelled export and exact downstream mapping without changing corpus
decisions. Negative tests cover tampering, foreign IDs, unsafe input, stale
revisions, runtime-secret rejection, concurrency and restart preservation.

Browser review retains renderer namespaces, unique capture paths, privacy masks,
strict thresholds, bounded failure diagnostics and the separately approved CP7
macOS path-only exception. Shared navigation/footer changes require deliberate
review of affected existing references, not just new workspace screenshots.
The alpha receipt describes technical checks, not researcher acceptance or
real-model performance. Section 19 uninstall/reinstall checks preserve project
and independent synthetic external-original bytes, not merely status counts.
