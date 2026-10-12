# v0.1.0a3 Checkpoint 3 — discovery verification

Development version: `0.1.0a3.dev0`. This is development checkpoint acceptance,
not approval for a public release or for Checkpoint 4. Native macOS graphical
acceptance remains with the researcher. No live scholarly-provider or model
request was made during implementation or mandatory acceptance.

## Implemented boundary

Packaged Discovery HTML/JavaScript → versioned protected local API → application
controller and immutable workflow receipts → existing scientific discovery,
canonicalization and stores. Only the four existing metadata adapters are used:
OpenAlex, Crossref, Europe PMC and Semantic Scholar. Configuration readiness is
not a successful connectivity test or a guarantee of unauthenticated access.

Each selected provider is planned once. Its exact `SearchPlan`, plan identity,
configuration revision, actual request parameters/cursor template, timestamp and
adapter code hash are frozen. A launcher-held expiring preview nonce is required
for explicit approval. Approval and execution are separate protected POSTs.
Queries/settings and exact-identity/source organization are explicitly approved;
approval does not send requests or grant corpus-membership authority.

Existing scientific planning, execution, normalization, retries, reservation and
canonicalization methods remain unchanged. Additive helpers expose actual request
previews and bounded scientific run reads. The development-artifact source gate
checks unchanged original method bodies/prefixes and rejects method replacement.
No scientific migration, configuration schema change or runtime dependency was
introduced. Existing schema resources, evidence, reviews, models, Knowledge and
ASReview implementations remain unchanged.

## Durability and safety

Versioned, hash-verified immutable local workflow files are stored inside the
configured project data directory at `discovery-workflows/v1/`. No separate
database or persistent global registry was added. These are researcher-owned
provenance, not disposable cache. Reads never initialize or reconcile files.
Same-filesystem no-overwrite publication is required; unsupported filesystems
fail closed. The existing scientific database/artifacts preserve actual request,
response, observation and canonical-link lineage.

Command receipts bind request identities to exact content. Each frozen plan has
at most one execution. A repeat requires a new plan and explicit approval. A
scientific child run reserved for different content is rejected rather than
attributing foreign results to the displayed plan.

Workers hold independent shared project-use leases for their complete lifetime,
plus project/job operation locks through the existing external kernel anchors.
Closing a browser or project does not release those worker leases. Removal remains
blocked. No external/older-program protection is claimed.

Browser refresh reads existing history. Host termination can interrupt a daemon
worker; without its live lock an unfinished job projects Interrupted, with no GET
mutation or automatic resend. There is no crash-resume. Cooperative cancellation
is checked between whole bounded provider operations, not immediate request/page
cancellation. Successful observations are retained when other providers fail.
Partial, failed, interrupted and bounded-complete states remain distinct.

Loopback/Host/Origin/session/CSRF/CSP/body-size/path safeguards are preserved.
No generic URL-fetch capability, remote frontend assets or browser secret storage
was added. Known credential echoes are rejected before response preservation;
errors do not persist remote exception messages. Operational discovery DTOs and
provenance are separate from method-blind review endpoints.

## Local verification

Environment: Linux, Python 3.12.3. Tests use only disposable synthetic projects,
fixture transports, actual installed adapter request/normalization code, local
HTTP servers and independent cooperating processes.

| Check | Result |
|---|---|
| Focused discovery/application/HTTP/packaged-JavaScript tests | 19 tests, OK, including deterministic completion/probe race |
| Complete standalone suite with optional ML installed | 436 tests, OK (1 native macOS opt-in test skipped), 102.172 seconds |
| Development-artifact regression tests | 12 tests, OK |
| Ruff (`src tests tools`) | Passed |
| JavaScript syntax (`app.js`, `projects.js`, `discovery.js`) | Passed |
| Diff whitespace checks | Passed |
| Wheel and sdist build | Passed; version `0.1.0a3.dev0` |
| Independent wheel/core full suite | 435 tests, OK (47 optional/native skips), 91.189 seconds |
| Independent wheel/optional-ML full suite | 435 tests, OK (1 native skip), 99.040 seconds |
| Independent sdist→wheel/core full suite | 435 tests, OK (47 optional/native skips), 86.345 seconds |
| Independent sdist→wheel/optional-ML full suite | 435 tests, OK (1 native skip), 99.441 seconds |
| Core/ML wheel/sdist tutorials, installed CLI and synthetic examples | Passed, `network_used=false` |
| Sdist uninstall/reinstall and project reopen | Passed in core and ML environments; project status preserved |
| Clean wheel/core focused suite after race fix | 19 tests, OK; offline tutorial and installed version passed |
| Clean sdist→wheel/core focused suite after race fix | 19 tests, OK; offline tutorial and installed version passed |

Clean installed-wheel/sdist core and optional-ML acceptance above is recorded by
`tools/smoke_install.py`; hosted acceptance and the exact downloadable wheel's
test receipt are authoritative for the artifact source commit. The artifact
includes exact build/source SHA and historical Checkpoint 1 implementation lineage;
it is not described as built from an earlier checkpoint.

The four 435-test full clean-install results above precede a narrowly scoped
read-projection follow-up. Hosted run `38252884592` detected a completion/liveness
race on Python 3.12: a worker could finish after history was read but before its
lock was probed, briefly projecting Interrupted despite a terminal receipt.
The reader now refreshes immutable history after observing the free worker lock.
A deterministic test reproduces that exact timing. No event write, execution,
scientific state or automatic retry was added. The implementation commit and
separate corrective commit remain in normal history; the final hosted run must
rerun the full clean-install matrix at the corrected exact source SHA before an
artifact is accepted. All six first-run macOS/Windows lifecycle jobs passed,
including native macOS guard/Trash acceptance; final-commit gates remain required.

The public-source privacy heuristic scan found no new blocking finding. Its one
credential-URL match is the existing deliberately fake URL rejection fixture in
`test_compatible_endpoint.py`. Legacy terminology matches are existing migration,
approved-plan or isolation-test context, not newly distributed research data.
Author/maintainer/contact fields remain absent; MIT project attribution and
development version remain unchanged. Heuristic checks are not a comprehensive
security/privacy certification.

## Offline researcher acceptance

The packaged JavaScript was executed against the actual local HTTP API using a
minimal developer-only DOM harness. It configured an exact query and two adapters,
previewed without requests, rejected missing consent, approved without requests,
ran explicitly, showed linked paper-title navigation and advanced provenance,
then repeated only after a new preview/approval. Six preserved observations
normalized to five exact publication identities; the repeat preserved twelve
observations in total and linked five known publications without new identities.
No membership decision was created. One-success/one-failure acceptance reports
Partial and preserves the successful provider's records. A real separate worker
process terminated during a synthetic request becomes Interrupted on read and
cannot silently replay.

A further existing-project acceptance seeded five publications, an authorized
human membership event, pending document evidence and a frozen method-blind session
with a draft. Rediscovery preserved configuration history, all review histories,
membership, evidence representations and the frozen session exactly. Read-only
Discovery views were also checked with before/after complete project fingerprints.
Existing Checkpoint 1/2, native Trash adapter, cross-process guard, scientific,
method-blind and optional-model/ML tests remain in the full suite.

This is synthetic interaction/contract acceptance, not a native browser rendering
test, live-provider validation or production throughput measurement. Dynamic
provider totals are not invented; displayed metrics distinguish observations,
linked identities, created identities and known identities, never accepted corpus
membership. Linked historical paper cards use current canonical metadata, not a
new candidate-population snapshot.

## Remaining limits and stop boundary

- No crash-resume, implicit rerun, immediate cancellation or background discovery
  on page load.
- One live local discovery worker per project; selected providers run sequentially.
- Search-history responses are paginated; local manifest ordering currently scans
  the saved plan catalogue. Large browser responses are not required, but very
  large search histories may need a reviewed indexing improvement later.
- Only the installed exact-query capabilities are exposed. No implicit concept
  alias expansion, independent date/language filters or new providers are added.
- No native macOS graphical or live-provider success is claimed. Hosted native
  guard/Trash tests remain enabled separately from mandatory offline discovery.
- No Checkpoint 4, evidence acquisition UI, new review lifecycle, membership
  publication redesign, import, classifier, model task or MCP was started.
- No main merge, tag creation/movement, GitHub Release or PyPI publication.

See [Discovery guide](../user/DISCOVERY.md) and
[workflow contract](DISCOVERY_WORKFLOWS.md). Hosted run/artifact identities and
checksums belong to the generated build receipt and completion report, avoiding a
self-referential source-commit identifier inside this document.

## Final Checkpoint 3 Discovery presentation refinement

Baseline: accepted commit `187b3f57bc74ace9c726d8cf1c0f5a09578ddff8`.
The researcher reports successful native macOS graphical discovery with real
OpenAlex and Europe PMC searches, including repeated-search identity recognition,
history across restart, separate approval/execution and unchanged membership
authority. That report does not establish live access for Crossref or Semantic
Scholar, exhaustive literature coverage, or real model-server interoperability.
No live provider/model request was made for this presentation follow-up.

Changes are restricted to Discovery HTML/CSS/JavaScript, focused tests and this
report. Both required approvals are grouped beneath a labelled approval heading,
with first-line checkbox alignment, wrapping labels and a nearby approval action.
Provider previews use dedicated responsive definition lists with readable labels,
exact adapter-derived values, visible page/retry bounds and runtime cursor rules.
All technical parameter names and the complete original plan remain available in
Advanced Details. The disclosure starts collapsed for a newly displayed plan and
retains its open state across approval/progress updates for the same plan.

No application controller, HTTP handler, scientific service, provider adapter,
project-use guard, configuration contract, storage, migration, dependency or CI
workflow changed. Approval and execution remain separate explicit actions. Both
consents remain mandatory on the frontend and backend. Search history, repeated
execution rules, immutable plans and all safety/authority semantics are unchanged.

Local Linux/Python 3.12.3 results:

- Focused Discovery suite: 21 tests, OK (16.061 seconds).
- Complete standalone suite with optional ML: 438 tests, OK, one native macOS
  opt-in skip (109.245 seconds).
- Ruff, syntax checks for all three local-app scripts, and diff whitespace checks
  passed.
- Changed-file privacy heuristics found no blocking result.
- Independent wheel/core: 438 tests, OK (47 optional/native skips), 93.301 seconds.
- Independent wheel/ML: 438 tests, OK (one native skip), 100.898 seconds.
- Independent sdist→wheel/core: 438 tests, OK (47 skips), 86.100 seconds.
- Independent sdist→wheel/ML: 438 tests, OK (one skip), 100.493 seconds.
- All four installed environments passed offline tutorials/CLI acceptance;
  `network_used=false`. Sdist core/ML uninstall/reinstall preserved project status.

New markup checks cover explicit checkbox-label associations, the approval region,
separate buttons and initially collapsed native disclosure. Packaged-JavaScript
tests verify all four actual adapter previews (including multi-provider OpenAlex /
Europe PMC), exact values and raw plan preservation, safe long Unicode/script-like
query text, each missing-consent combination, explicit execution and per-plan
disclosure state. Existing exact-plan, repeat, history, no-network-on-navigation,
fingerprint, security, cross-process and Trash tests remain required.

Clean wheel/sdist core/ML suites, installed CLI, tutorials and the hosted Linux /
Windows / native macOS matrix are additional gates for the exact artifact source
commit. Their receipts and final run/checksum are reported with the downloaded
artifact. DOM/markup and CSS contract checks are not browser rendering or native
macOS visual acceptance. No browser engine was installed for this follow-up;
the researcher will perform final graphical acceptance. No Checkpoint 4 or release
work was started.
