# Real browser acceptance (Checkpoint 4 testing follow-up)

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
python -m playwright install chromium
# Linux system libraries, if needed (requires administrator privileges):
python -m playwright install-deps chromium
# Linux baseline font: fonts-dejavu-core, supplied by Ubuntu 24.04.

python tools/browser_acceptance.py --suite smoke --viewports laptop --output /tmp/ct-browser-smoke
python tools/browser_acceptance.py --suite evidence --viewports desktop --output /tmp/ct-browser-evidence
python tools/browser_acceptance.py --suite discovery --viewports desktop --output /tmp/ct-browser-discovery
python tools/browser_acceptance.py --output /tmp/ct-browser-full
python tools/browser_acceptance.py --visual compare --output /tmp/ct-browser-compare
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

## Isolation and scientific coverage

Each test has its own private temporary project root, external lock anchors,
controller, ephemeral loopback port and browser context. The registered project
root is explicit: the default `~/CorpusTrailProjects` is never read or written.
Existing Project/identity/configuration/discovery/evidence services and ordinary
Host/Origin/session/CSRF/CSP checks run unchanged. Application startup binds before
navigation and the browser waits for readiness. Worker threads, servers, browsers
and process leases are closed in cleanup, including assertion failures.

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
unavailable; no identifier enrichment/review/membership action is introduced.

## Visual baselines and review

Playwright **1.63.0** pins Chromium and Pillow **12.0.0** performs comparisons. Linux
CI is Ubuntu 24.04. A test-process Fontconfig file selects installed DejaVu Sans;
production CSS and CSP are not bypassed. Strong test-process family binding and a
Chromium platform-font probe prevent silent serif fallback even when installed
font hashes match. The manifest records browser version, font SHA, architecture,
locale, timezone, device scale and comparison policy. A
different renderer fails comparison with instructions to capture separately; macOS
never compares against Linux pixel baselines.

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
comparison/non-Linux reports, and records hashes in the dedicated manifest. CI has
no approval step. Baselines are small developer resources in Git; browser reports,
baselines, browsers and tooling are excluded from wheels/sdists. The normal wheel
does not even declare a Playwright optional dependency.

## CI and checkpoint policy

`Offline Chromium / reviewed Linux visual baselines` blocks the development wheel
on interaction, runtime/network, layout or reviewed screenshot failures. A separate
macOS Chromium smoke job exercises interactions without cross-OS pixel comparison.
Both upload bounded synthetic reports even after failures (30-day retention).
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

Current limitations: Chromium only; limited macOS smoke, no Windows browser job,
no axe/WCAG certification, no live providers, no native-browser Trash execution,
and no assertion that screenshots establish scientific validity or perfect UX.
