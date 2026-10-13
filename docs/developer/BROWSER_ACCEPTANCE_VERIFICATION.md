# Checkpoint 4 browser-testing infrastructure verification

Baseline: `843efb5da8abf62c7f3394a0076d71ad08761792` on
`development/v0.1.0a3-read-only-local-ui`, version `0.1.0a3.dev0`.
This is quality infrastructure during Checkpoint 4, not its final native acceptance
or permission to begin Checkpoint 5. Hosted run/source/artifact identities belong
in the generated receipts and completion report, not a self-referential commit.

## Architecture and preservation

Python Playwright 1.63.0 + unittest, Chromium 153.0.8010.12, and Pillow 12.0.0.
Developer requirements are separate from package extras. Core dependencies,
scientific services/schemas, project configuration, discovery/evidence contracts,
identity, authority, review history, Knowledge and ASReview are unchanged.
Only two production presentation strings changed: the footer now uses the
existing mode placeholder, and Welcome accurately includes eligible retrieval.
Legacy read-only server mode remains available and tested.

Each browser case runs the installed current package (source/resource bytes checked)
with its actual HTTP server, private temporary projects, unique project IDs, real
project leases and ordinary session/Host/Origin/CSRF/CSP protections. Test-only
transport injection supplies all four scholarly provider dialects and Europe PMC
XML to the original scientific executor/normalizer/verifier/parser. Browser API
responses are not mocked. Nonloopback backend sockets, real transports and external
browser requests are independently guarded. No live scholarly/model call occurs.

The disposal adapter permits actual confirmation/cancellation services but raises
if native movement is attempted. A real independent process holds a project lease
for the busy-project case. Native macOS Trash remains in its existing hosted suite.
No actual researcher projects/default project roots are used by browser tests.

## Coverage

- Home/workflow/navigation, readable five-paper catalogue, filters/dropdowns,
  scholarly links inspected without following, advanced provenance, focus/labels,
  missing-PMCID explanation, existing human observation distinct from membership,
  pending evidence and complete read-only project fingerprints.
- Six-step wizard validation, explicit creation, retained provider/resolver choices,
  compact summary, direct settings edit/discard/save/unchanged-save/history/reopen,
  active-card closing, exact Trash confirmation/cancel and other-process refusal.
- Four-provider exact previews, both mandatory approvals, separate start,
  factual held-running progress, eight observations/five linked publications/four
  new/one known, preserved source provenance, history/refresh without replay,
  partial repeat with no new identities or membership publication.
- Abstract/source attribution, eligible explicit retrieval, verified plaintext,
  evidence provenance, wrong-document rejection with earlier valid evidence
  unchanged, operation history/refresh and no review/membership write.

## Local results

Linux Ubuntu 24.04 userland / WSL2, Python 3.12. Developer Chromium dependencies
unavailable system-wide were extracted into isolated temporary library storage;
system/researcher installations were not changed. CI uses standard installation.

| Check | Result |
|---|---|
| Full browser interactions | 12 cases: four workflows × three viewports, passed |
| Reviewed visual checks | 30 representative images, strict comparison passed |
| Browser diagnostics/network guards | No runtime errors or unexpected requests |
| Infrastructure self-tests | 8 passed, including local-tile sensitivity, dimensions, approval rejection, trace/session redaction |
| Complete installed standalone + optional ML suite | 454 tests, OK; one native-macOS-only skip; 118.758 seconds |
| Clean wheel/core full suite | 454 tests, OK; 47 optional/native skips; 101.936 seconds |
| Clean wheel/ML full suite | 454 tests, OK; one native skip; 120.708 seconds |
| Clean sdist→wheel/core full suite | 454 tests, OK; 47 skips; 104.196 seconds |
| Clean sdist→wheel/ML full suite | 454 tests, OK; one native skip; 116.577 seconds |
| CLI/offline tutorials/reinstall preservation | Passed, version `0.1.0a3.dev0`, network false |
| Ruff / JavaScript syntax / whitespace | Passed |
| Browser tooling and baseline-manifest privacy checks | No blocking findings |
| Installed package dependency metadata | No Playwright/Pillow requirement; MIT unchanged |

Comparisons use the pinned Linux renderer, controlled installed fonts, scale 1,
1440×900, 1280×800 and 390×844 viewports. Scientific statuses/counts/abstracts and
consents remain visible; transient dates/elapsed times and opaque paths/raw data
are normalized or masked for captures only. The results image targets the actual
count table; canonical-ID ordering of result links is not a cross-project pixel
invariant. Those links and actual provenance remain tested through browser actions.

Early comparisons correctly rejected timing/scroll-coordinate variations. Capture
now waits for explicit completed UI handlers, stabilizes full-page coordinates and
uses held provider responses for progress. Tolerances were not loosened. Initial
baselines were approved only from a passing complete capture after direct image
inspection. CI has no approval/update step.
The first hosted comparison also detected an OS/generic-family serif fallback.
Test-only Fontconfig now strongly binds the intended family and Chromium's actual
platform-font data is checked before capture. Production CSS and tolerances were
not weakened; local and hosted reruns gate the final artifact.

Codex directly inspected representative Welcome, catalogue, wizard/summary,
settings, projects/closing, Trash confirmation, provider preview/approval/progress/
results, evidence availability/result/provenance and narrow screenshots. This is
not native MacBook acceptance or proof of complete usability/accessibility.

## Hosted gates and limits

New Linux Chromium comparison and macOS Chromium smoke jobs are mandatory before
the ordinary development wheel artifact. Existing Python 3.11–3.13 Linux core/ML/
wheel/sdist and Windows/macOS lifecycle/guard/native Trash jobs remain intact.
Reports identify exact source commit and dirty-local-checkout status, browser,
platform, viewports, cases, comparisons, requests and limitations. Failure traces
exclude DOM/network snapshots and redact session values and local source paths.
Screenshots/reports have a separate 30-day artifact; development wheel has 90 days.

No browser baselines/reports/binaries or Playwright dependency enter wheel/sdist.
The Git checkout contains only developer fixtures, scripts, reviewed synthetic
baseline PNGs/manifest and documentation. Missing dependencies/renderer mismatch
fail, never silently skip. Chromium only; limited macOS smoke, no Windows browser
suite, no axe/full WCAG assessment, no live-provider proof. Checkpoint 4 remains
open for final user acceptance. No Checkpoint 5, main merge, tag/release/PyPI work.

See [commands and review policy](BROWSER_TESTING.md).
