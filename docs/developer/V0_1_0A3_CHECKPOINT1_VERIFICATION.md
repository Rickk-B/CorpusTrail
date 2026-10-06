# v0.1.0a3 Checkpoint 1 — read-only project browser

## Scope and lineage

Development branch: `development/v0.1.0a3-read-only-local-ui`.
Development version: `0.1.0a3.dev0`; not a release.
Base public a2 commit: `ffd657fcc92a683722cf052cfc01695c66056b24`.
The approved complete specification was committed separately as `43be6fd` and
retained byte-for-byte in `docs/v0.1.0a3-implementation-plan.md`:

```text
bytes: 90761
lines: 1251
SHA-256: d6dff111f033d8c858a98963a16376eb92b630dae4f2a74be11505b269b1b668
```

Only Checkpoint 1 is implemented. No project/configuration editing, discovery or
acquisition actions, review lifecycle redesign, classifier, reference collection,
population persistence, import, model call or later checkpoint has been started.
No migrations or dependency requirements were added. Published a1/a2 tags remain
unchanged. There is no new tag, push or release.

## Implementation boundary

```text
packaged HTML/CSS/JavaScript
  → loopback local_app /api/v1 transport
  → application.ProjectReads / internal catalogue read repository
  → existing canonical metadata, identity, membership and evidence stores/services
```

Dashboard, paginated/filterable catalogue, paper detail, trusted structured-body
text segments and explicitly expanded paginated provenance are read operations.
They do not initialize/upgrade databases, invoke providers/plugins, shell out to
the CLI, or cache/store derived scientific state. Connections use SQLite `mode=ro`
and `query_only`. Metadata selection and evidence projections remain shared with
existing scientific services; bulk membership filtering ignores non-authoritative
events and individual page histories are validated through the current projector.

The browser identifies papers by readable titles; reversible opaque link handles
are internal exact keys. Default responses omit raw observations, source locations,
queries, rationales, technical canonical IDs and model judgments. Operational DTOs
are deliberately separate from existing method-blind review responses.

The existing review server source and scientific session semantics are unchanged.
Draft summaries explicitly mean historical draft updates, not completed forms or
recorded decisions. Recorded identity warnings are not labelled current unresolved
issues when the store does not establish that conclusion.

## Verification results

All runs below used synthetic inputs and local loopback fixtures, with no live
discovery/evidence/model requests. Python available locally: **3.12.3 on Linux**.

| Surface | Exact result |
|---|---|
| Focused application/HTTP/frontend tests | 25 tests, 8.554 seconds, OK |
| Complete source-checkout standalone suite | 330 tests, 81.447 seconds, OK |
| Clean wheel, core only | 330 tests, 62.287 seconds, OK, 46 optional-ML skips |
| Clean wheel, optional ML | 330 tests, 74.293 seconds, OK, no skips |
| Clean sdist-built wheel, core only | 330 tests, 55.979 seconds, OK, 46 optional-ML skips |
| Clean sdist-built wheel, optional ML | 330 tests, 71.427 seconds, OK, no skips |
| Core and ML offline tutorial/examples | Passed, including knowledge and exact-ID downstream mappings |
| sdist uninstall/reinstall and deterministic project reopen | Passed in core and ML environments |
| Actual installed CLI launch outside repository | Passed, ephemeral loopback port, clean Ctrl+C exit |
| Installed five-paper HTTP acceptance | Passed; pending/mismatch not readable; project bytes unchanged |
| Five-paper JavaScript DOM walkthrough | Passed using existing optional Node test tooling |
| Python 3.11 grammar compatibility | 75 Python files parsed successfully; not runtime execution |
| Ruff configured correctness gate | All checks passed |
| JavaScript syntax / git diff whitespace | Passed |
| Existing review and method-blind regressions | Passed within complete suites |
| Package/frontend resource inclusion | HTML, CSS and JavaScript present in wheel and sdist |

Core installs have no numerical/model/ASReview dependencies. The ML runs used
already-cached wheels: scikit-learn 1.8.0, NumPy 2.4.2, SciPy 1.17.0, joblib 1.6.0
and threadpoolctl 3.7.0. Neither credentials nor a commercial API were needed.

Focused tests cover shared canonical selectors, duplicate titles, missing metadata,
Unicode search, literal query matching, implemented filters/year ordering, stable
and stale pagination, evidence/membership/review separation, explicit advanced
lineage, read-only fingerprints, artifact confinement, escaping, session/Host/Origin
gates, restrictive CSP, rejected write methods and packaged assets.

A 20,000-record synthetic catalogue verifies that a request builds only its page
of 25 DTOs and returns a bounded response, with stable subsequent pages. This is an
architecture/memory-boundary test, **not measured production throughput**. Deep
offset pages, aggregate scans and unusually large per-paper histories may remain
expensive; no persistent index/cache or migration was introduced.

Initial test-development issues (a mock missing its declared hosts and a new
identifier-provenance query using the wrong existing column name) were corrected
before these final runs. Sandbox loopback restrictions required approved local
socket execution. An interrupted verification run was restarted; incomplete runs
are not represented as successes.

## Five-paper acceptance and visual limitation

Synthetic project: five canonical papers, two identical titles, a DOI-missing
paper, included/excluded/insufficient judgments, unreviewed membership, a verified
structured body, pending artifact and mismatched document. The walkthrough opens
dashboard → catalogue → readable title/detail → optional advanced provenance,
then verifies that the complete project file fingerprint has not changed.

The installed launcher was exercised from an unrelated working directory in a
clean core environment. The JavaScript DOM test exercises navigation/data rendering,
lazy provenance and malicious-title escaping. No native browser automation or Mac
runtime is available here. Therefore **native visual/browser and macOS acceptance
remain for the user**; a visual/manual Mac pass is not claimed.

## Privacy, security and preservation

- Loopback-only address, exact single Host/Origin, Fetch Metadata checks, ephemeral
  in-memory API capability, no CORS grant, no-store and restrictive CSP.
- No credential/configuration payloads in normal read DTOs or browser storage.
  Text is rendered through `textContent`; no remotely loaded assets or executable
  provider/model content. Static names are allowlisted and artifacts are enrolled,
  confined and hash-checked before trusted text access.
- All mutation verbs are rejected. No write-CSRF surface exists in this app;
  legacy review write routes retain their existing protections.
- Product-source and distribution text scans found no new private identity,
  credentials, private home paths, contact metadata, PDFs or databases. The only
  heuristic credential-URL finding is the existing fake `example.test` input in
  a URL-rejection test. Legacy-scope mentions in frozen schema/tests and the
  approved specification are semantic warnings, not migrated scientific content.
- Wheel/sdist metadata retains MIT and omits personal author/maintainer/contact
  fields. The copyright notice remains `2026 CorpusTrail contributors`.
- No changes were made in the private historical research repository or its
  scientific artifacts. Its pre-existing untracked work was left untouched.
- The existing schema manifest, migration files and legacy review HTTP source
  are unchanged from the a2 base.

Scans and these tests are bounded practical checks, not formal privacy/security
certification. Only locally known identity variants were checked; arbitrary
previously unknown identifying free text cannot be ruled out by heuristics alone.

## Remaining limitations and next action

- Only an already-configured project can be opened. Terminal launch remains the
  bridge; desktop installers, wizards and workflow actions are later checkpoints.
- The page cursor detects relevant immutable-store revision changes; it is not a
  frozen candidate-population snapshot. Changed revisions require a list refresh.
- Trusted structured body text is available; this checkpoint does not serve PDFs
  or add identifier enrichment/retrieval capabilities. Full artifact hashing still
  reads the enrolled artifact even though the HTTP text response is segmented.
- Native Python 3.11/3.13 and macOS runs were not available. Their existing CI
  matrix remains, but hosted CI has not been invoked because no push is authorized.
- No new real-model compatibility claim is made; the a2 experimental adapter's
  offline/mock-only validation limitation remains intact.

Next: user inspects this checkpoint and performs the native Mac visual walkthrough.
Checkpoint 2 requires separate explicit approval and has not begun.
