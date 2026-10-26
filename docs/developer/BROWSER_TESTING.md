# Real browser acceptance (Checkpoint 4 testing follow-up)

## Explicit CP7 path-only visual debt

The researcher's 19 October 2026 amendment permits the fixed macOS fixture-path
family documented in `DEVELOPMENT_BUILDS.md`, only with per-image proof. The
macOS workflow enables `--allow-cp7-path-reflow`. Originals and strict comparison
failures remain visible in `report.json`; no baseline, mask, crop, tolerance or
timeout changes. The proof accounts for repeated rows through the existing path
mask and resulting reflow; all other pixels retain the original noise budgets.
DOM checks require actual expected paths, readable contained text and accessible
controls; the separate long-path keyboard scenario remains mandatory.

`functional_passed`, `strict_visual_passed` and `path_only_exceptions` are separate
outcomes. `passed` means the explicitly amended gate, not universal strict success.
Only a verified exception allows subsequent assertions/captures to continue.
`ACCEPTED_WITH_PATH_EXCEPTION` is reported explicitly; unrelated failures remain
blocking. Linux never enables this exception. The exact-source per-engine report
and exception/image hashes are carried into any delivered wheel receipt.

This opt-in suite uses Python Playwright's synchronous library with the existing
`unittest` framework. There is no second JavaScript test stack, production browser
dependency, browser binary in a wheel, database migration or test HTTP endpoint.
Ordinary `unittest discover -s tests` remains independent of browser installation.
The official [Python library](https://playwright.dev/python/docs/library) and
[browser installation](https://playwright.dev/python/docs/browsers) documentation
describe the underlying developer tools.

## Install and run

Use a developer checkout and isolated Python 3.11+ environment, not a research
project or researcher installation. The application must be installed from the
current built wheel: the runner imports its scientific services and packaged
assets, not an HTML mock or source `PYTHONPATH` override.

```bash
python -m venv .venv-browser
source .venv-browser/bin/activate
python -m pip install '.[dev]' -r tools/browser-requirements.txt
python -m build --wheel --no-isolation
python -m pip install --no-deps --force-reinstall dist/*.whl
python -m playwright install chromium webkit
# Linux system libraries, if needed (requires administrator privileges):
python -m playwright install-deps chromium
# Linux baseline font: fonts-dejavu-core, supplied by Ubuntu 24.04.

python tools/browser_acceptance.py --suite smoke --viewports laptop --output /tmp/ct-browser-smoke
python tools/browser_acceptance.py --suite evidence --viewports desktop --output /tmp/ct-browser-evidence
python tools/browser_acceptance.py --suite discovery --viewports desktop --output /tmp/ct-browser-discovery
python tools/browser_acceptance.py --suite review --viewports desktop --output /tmp/ct-browser-review
python tools/browser_acceptance.py --suite population --viewports desktop --output /tmp/ct-browser-population
python tools/browser_acceptance.py --suite reference --viewports desktop --output /tmp/ct-browser-reference
python tools/browser_acceptance.py --suite project --viewports desktop --output /tmp/ct-browser-project
python tools/browser_acceptance.py --output /tmp/ct-browser-full
python tools/browser_acceptance.py --visual compare --output /tmp/ct-browser-compare
python tools/browser_acceptance.py --browser webkit --output /tmp/ct-browser-webkit
python -m unittest browser_tests.test_infrastructure -v
```

Output directories must be new: previous reports are never overwritten. Open
`index.html` directly in a browser (`open /tmp/ct-browser-full/index.html` on macOS).
`report.json` identifies browser/version, OS, viewports, scenario outcomes, pixel
comparisons, controlled provider-call counts and unexpected-network errors.
`summary.txt` contains unittest results. Screenshots, diagnostics and sanitized
failure traces are separate. Open a failure trace with `playwright show-trace`.
Traces have screenshots/actions, not DOM/network snapshots; session values are
redacted before publication. No real projects, article files or credentials are
uploaded. Successful runs do not keep traces. Failure artifacts are synthetic.

Navigation retains its ten-second request-completion limit and continuous quiet
interval. Request lifecycle diagnostics record only fixed route vocabulary,
sequence numbers, response status and event timings, not query values, bodies,
headers or opaque path components. Pending state is saved before failure capture.
Teardown does not repeat a navigation wait that has already failed. Screenshot,
trace finalization and sanitization are independently attempted, with three-second
screenshot and five-second diagnostic/close bounds on the Linux/macOS runners.
Collection failures are reported separately from the original test exception;
they never turn a failed test into a pass. Raw traces remain outside the uploaded
report until sanitization succeeds. A pending request is an observation, not proof
of a production navigation defect or stale bookkeeping.

## Isolation and scientific coverage

Each test has its own private temporary project root, external lock anchors,
controller, ephemeral loopback port and browser context. The registered project
root is explicit: the default `~/CorpusTrailProjects` is never read or written.
Existing Project/identity/configuration/discovery/evidence services and ordinary
Host/Origin/session/CSRF/CSP checks run unchanged. Application startup binds before
navigation and the browser waits for readiness. Worker threads, servers, browsers
and process leases are closed in cleanup, including assertion failures.
Guided-review visual fixtures use a fixed synthetic project identifier so their
canonical-ID order is reproducible. Their temporary project roots and external
lock directories remain unique per case/run, including concurrent runs; no project
state or lease anchor is shared. Other fixtures retain generated identifiers.
Test-driven navigation, refresh and graceful restart wait for the preceding
page's local reads to settle. Cancelled/failed requests remain errors rather
than being filtered out. This observes actual request events and a continuous
quiet interval, with a ten-second bound, rather than a possibly stale load-state
flag. Progress screenshots wait for the factual first provider attempt, not
merely the parent operation's earlier running state. Auxiliary project controllers are explicitly closed;
fixtures do not depend on garbage-collection timing to release leases.

Only the provider transport is injected. OpenAlex, Crossref, Europe PMC and Semantic
Scholar responses use their actual normalizers, exact identity pipeline, persisted
frozen plans and scientific provenance. A real transport and nonloopback Python
socket guard fail unexpected backend network use. Browser routing permits only the
actual local origin, including new tabs. DOI links are inspected, never followed.
No API response is mocked in the browser. Fixtures with the wrong identifier format
are errors in tests, not grounds to relax scientific identifier contracts.

Scenarios cover Welcome, six-step creation/validation/summary, settings edit/discard/
unchanged-save/history/reopen, active-card close, exact Trash confirmation/cancel and
a real other-process busy lease. The browser disposal adapter permits confirmation
only and raises if disposal executes. Native macOS Trash remains a separate existing
test. Discovery covers all four providers, exact preview, both mandatory consents
explicitly disclosed and recorded through one deliberate approval action,
separate approval/start, running/results/history/refresh, exact deduplication and a
partial repeated search. Evidence covers actual stored abstract attribution, explicit
known-PMCID acquisition, verified plaintext, provenance, mismatch rejection, earlier
valid evidence preservation and refresh without replay. Missing-PMCID retrieval is
unavailable; no identifier enrichment is introduced.
Guided Review exercises real frozen sessions, autosaved drafts, skip/resume,
five canonical publications, missing evidence, verified text, non-authoritative
Save & Next, injected transport failure/input retention, double-click protection,
graceful restart, completion without membership, separately confirmed atomic
publication and backend refusal for an unauthorized identity. A newly collected
publication stays outside the frozen set. Review services/API successes are never
mocked. Empty projects create no phantom sessions. All three viewports are covered;
the complete hosted macOS Chromium and WebKit selections include these scenarios.
Review refinement coverage includes disabled extent placeholders, explicit existing
full-document attestation, completed read-only observations/provenance, failure
before Finish acknowledgement, the completion dashboard link, summary/preview/back/
refresh transitions and separately confirmed publication. Local journal tests
compare actual browser requests, HTTP responses, rendered titles and ProjectReads
for exact/partial/case/trimmed/punctuation/empty/unmatched queries, missing metadata,
combined filters and clear/reset. No search or authoritative review response is
mocked. Both hosted macOS engines include local journal search as well.
The evidence scenario also restarts the actual HTTP server/controllers, reopens the
same disposable project, and verifies persisted history/text without new requests
or scientific-file changes. This is graceful restart testing, not crash-resume.
For original-response inspection, see [read-only diagnostics](EVIDENCE_DIAGNOSTICS.md).

Population scenarios exercise actual immutable versions, preview invalidation,
explicit backed-up schema-37 upgrade, independent synthetic source-adapter enrollment,
offline discovery, overlapping canonical IDs, deterministic union, frozen Review
selection and persistence after graceful restart. They create no membership or
review observations. Source ordering/integrity, process races/crashes and historical
scientific-table preservation are also covered by the standalone scientific suite.
Production format importers are absent. Complete population coverage runs in
both hosted macOS engines. Pixel comparison infrastructure separates Linux
Chromium, macOS Chromium and macOS WebKit, never comparing cross-platform pixels.
Linux Chromium, macOS Chromium and macOS WebKit have separate reviewed baselines.
All three use strict comparison for delivery. The [CP7 visual review](CP7_VISUAL_REVIEW.md)
records the complete new capture inventory, direct inspection and retained older
images. Capture-only output never substitutes for the final strict delivery gate.

## Visual baselines and review

Ordinary reference captures use an explicit resting pointer state, established
after capture scrolling by normal mouse movement to the canvas origin. The runner
waits until no visible interactive control is hovered and verifies that keyboard
focus and its visible feedback are unchanged. Full-page driver viewport changes
must not select an incidental hover state. Real hover feedback is tested separately
in the existing three-viewport application scenario; it is not disabled in CSS or
removed from the product. Each screenshot record identifies this capture policy.

Playwright **1.63.0** pins Chromium/WebKit and Pillow **12.3.0** performs comparisons. Linux
CI is Ubuntu 24.04. A test-process Fontconfig file selects installed DejaVu Sans;
production CSS and CSP are not bypassed. Strong test-process family binding and a
Chromium platform-font probe prevent silent serif fallback even when installed
font hashes match. The manifest records browser version, font SHA, architecture,
locale, timezone, device scale and comparison policy. A
different renderer fails comparison with instructions to capture separately; macOS
never compares against Linux pixel baselines.

Baselines are namespaced as `linux-chromium`, `darwin-chromium` and
`darwin-webkit`. A macOS manifest additionally freezes the OS version; rendering
changes require a new explicit review, not relaxed pixel thresholds. Capture a
complete passing run on the intended hosted platform/engine, download its report,
inspect representative images directly, then use the same `--approve-baselines
REPORT --reviewed` command locally. It chooses the destination from the report's
validated platform/engine and records the capture report SHA-256/source identity.
The approval command does not need to run on macOS and does not launch a browser.
CI contains no baseline approval or automatic fallback from compare to capture.
Initial platform bring-up deliberately uses capture; comparisons are enabled only
after those first hosted screenshots have actually been inspected and approved.

### WebKit and strict CSP

The first full WebKit run exposed a Playwright 1.63 screenshot helper that inserts
an inert `body {}` inline stylesheet to synchronize animations. CorpusTrail's
unchanged production CSP correctly refuses it. The test-only
`browser_tests/webkit_screenshots.py` / `.cjs` adapter disables exactly that one
driver synchronization instruction **in memory**, before the pinned Node driver
loads. Both the Python guard and Node loader check the complete reviewed driver
SHA-256; an unknown version/hash fails setup. Linux and published Apple Silicon
wheel driver bytes were checked identical. Installed files are never modified.
`NODE_OPTIONS` is process-scoped/restored; pre-existing options fail closed.

This is not `bypass_csp`, a response-header change or a console-error allowlist.
The actual application, stylesheet, scripts and security policy are unchanged.
Each WebKit capture asserts no running animations under reduced-motion settings;
the application's current CSS has no animations to synchronize. Arbitrary inline
CSS is explicitly tested as still blocked, with that deliberate negative check
counted in the report. All unexpected console/CSP/runtime errors still fail.
The adapter policy is recorded in the renderer manifest. Review/remove this
narrow workaround when updating Playwright; do not blindly patch new versions.

Mac WebKit keyboard tests use native Option+Tab for all-control traversal rather
than changing macOS keyboard settings. Navigation waits for the actual dashboard
and loaded controls before leaving a page; aborted unfinished requests are not
silently ignored. A deliberately delayed *real* population-controller response
tests edits during a pending preview. Late previews are discarded by request
identity; the existing backend stale/hash/revision guards remain unchanged.
Tests wait for the actual dashboard URL/content after asynchronous project opening
before starting another navigation. The completed unauthorized-review snapshot
uses the full `main` content bounds: Chromium's earlier scroll extent can outlive
a collapsed assessment panel and otherwise add variable blank screenshot canvas.
Reviewer, counts, decisions and authority controls stay visible; page-level
overflow/label checks still run. Pixel tolerances are not relaxed for this case.

Viewports: desktop **1440×900**, laptop **1280×800**, narrow **390×844**, scale 1.
Representative full-page and viewport images cover project setup, catalogue/detail,
discovery preview/progress/results and evidence availability/result/provenance.
Laptop/narrow captures select representative screens rather than duplicate every
desktop image. Dates/elapsed text are normalized only for screenshots; disposable
paths and opaque raw payloads/hashes are masked. Real values and path wrapping are
tested separately. No scientific records or API values are rewritten. Masking
never hides consent controls, scientific statuses, counts or ordinary abstracts.
The completed-results image targets the actual count table. Result links remain
fully tested through the browser; their canonical-ID order can differ between
independent projects with unique identities and is not a pixel invariant.

Pixels differing by more than 16 in any RGB channel count as changed. Both a global
0.05% budget and a 2% per-100px-tile budget apply. Dimension changes fail. Difference
images accompany failures. Local tile checks catch concentrated small-control
regressions; geometry checks independently test filter-box and consent alignment,
horizontal overflow, accessible labels/names and keyboard-visible focus. This is
not a general usability assessor, complete accessibility audit or WCAG certification.

Never approve a baseline merely to make CI green. Generate a **passing complete**
three-viewport capture, open representative images directly, inspect alignment,
wrapping, clipping and spacing, and obtain review for material UX changes. Only then:

```bash
python tools/browser_acceptance.py --approve-baselines /tmp/ct-browser-full --reviewed
python tools/browser_acceptance.py --visual compare --output /tmp/ct-browser-approved-check
git diff --stat -- browser_tests/baselines
```

The approval command is separate from running tests, rejects failed/partial/
comparison/unsupported-renderer reports, and records hashes in the dedicated manifest. CI has
no approval step. Baselines are small developer resources in Git; browser reports,
baselines, browsers and tooling are excluded from wheels/sdists. The normal wheel
does not even declare a Playwright optional dependency.

## CI and checkpoint policy

`Offline Chromium / reviewed Linux visual baselines` blocks the development wheel
on interaction, runtime/network, layout or reviewed screenshot failures. A separate
macOS Python 3.13 job runs the complete suite in both Chromium and WebKit, sharing
one wheel/tool installation. Playwright WebKit is compatibility coverage, not an
assertion that every Safari version behaves identically. No self-hosted runners
or personal devices are used. Both upload bounded synthetic reports even after
failures (seven-day retention). The runtime report records Python, OpenSSL, Expat,
Playwright, browser, macOS version and architecture; it never dumps environment values.
If installation fails before the runner starts, CI logs report that failure; no
screenshots are claimed. A failed browser/renderer setup is never a passing skip.
Existing Python 3.11–3.13 core/ML/wheel/sdist, Windows/macOS lifecycle, native Trash
and cross-process jobs remain required and unchanged.

For every subsequent approved checkpoint: run a quick relevant browser scenario
during development; run the full three-viewport suite and inspect representative
images before pushing; keep reviewed visual comparisons as an artifact gate. Add
cases through the same Python fixtures/runner. A browser pass does not authorize
later checkpoints or establish live-provider interoperability. Native researcher
acceptance remains important for subjective UX and platform-specific differences.

Current limitations: headless Chromium/WebKit, no Windows browser job,
no axe/WCAG certification, no live providers, no native-browser Trash execution,
and no assertion that screenshots establish scientific validity or perfect UX.

## CP7 reference/context acceptance

The existing fixture/runner now covers explicit human reference batches,
current-membership source-event lineage without implicit reference population,
successor corrections, historical versions, conflicts, exact selected passages,
held-out labels, restart, bounded version/member/provenance pages, stale batch
refusal and explicit schema-38 backups/upgrades. Actual services/stores are used;
no reference or membership API result is mocked. The separate installed-service
scale tool exercises 2,000 distinct canonical papers; browser paging uses a smaller
synthetic collection to assert that pages replace rather than accumulate records.

Synthetic reference form timestamps are fixed only at `application.references.now`.
Those tests also replace operation UUID generation with a tab-local deterministic
counter; the script is test-only and never enters packaged assets. This stabilizes
same-paper contradictory assignment ordering without repainting scientific data.
Search helpers await the actual completed search and requested title, not a prior
single-row result. All clock patches restore through fixture cleanup. Raw technical
reference/context provenance panels follow the existing privacy-mask policy;
human labels, rationale, counts, warnings and exact displayed passages are unmasked
and checked against real stored records.

The explicit CI capture-review phase cannot produce a development wheel. Baseline
approval still requires a passing complete three-viewport capture, distinct paths,
matching environment/source provenance and direct visual inspection. Restore strict
`compare` before final delivery. No tolerance, diagnostic deadline, navigation
timeout, unique-path safeguard or failure-preservation rule is relaxed by CP7.

### Preserve existing reference bytes during a scoped review

An optional `--reviewed-change-list PATH` on the existing approval command accepts
an explicitly reviewed JSON map of image filenames to their actual captured
SHA-256 values. It still requires `--reviewed`, a passing complete three-viewport
capture, correct platform/engine namespace and the existing path/duplicate guards.
Every new image must be selected. Unselected existing references retain their
previously approved bytes, hashes and renderer provenance; their previous
manifest hash is recorded. Selecting an image does not follow from generation or
a green functional result: inspect old/new/full-size differences and record the
rationale first. No runtime comparison, tolerance or delivery gate changes.

Preserving an old reference is not a claim that the current capture matches it.
The final strict run compares **all** captures and rejects unexplained differences;
only the separately documented pre-existing path-only exception remains eligible.
This avoids regenerating unrelated PNGs merely because their encoded bytes differ.
