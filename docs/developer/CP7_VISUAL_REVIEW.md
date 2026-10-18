# CP7 explicit visual baseline review — 18 October 2026

This records agent visual inspection under the researcher's implementation
authorization, **not formal researcher acceptance**. The approved plan is unchanged.
No workflow approves baselines or changes a tolerance after a failure.

## Complete capture provenance

[Run 39145871684, attempt 1](https://github.com/Rickk-B/CorpusTrail/actions/runs/39145871684)
captured source **9a3d63cef751c64fd05f222cbae99a74ea77097e**, tree
**39759580fbb2b643d6afcd3f1566b015ce975d5d**, with clean checkouts. Each engine passed
**48 executions and 184 unique captures**, across 1440×900, 1280×800 and 390×844.
The screenshot inventory has no repeated path or overwritten distinct state.

The overall capture workflow failed: all three Python jobs' new historical-source
test required CP6 Git objects absent from the one-commit checkout. The same failure
was reproduced in an offline shallow clone. Full-history local checks passed.
The final candidate supplies full history to those jobs, without skipping or
weakening the assertion. Six lifecycle jobs and both browser jobs passed; the
capture-phase wheel job correctly stayed skipped. These captures validate visual
state only, not successful final scientific/package delivery.

Original artifacts, all members, CRC checks and original archive digests were
verified before review; full ZIPs/manifests remain in durable developer evidence.

| Artifact | ID | ZIP bytes | ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Linux browser report | 12143448261 | 25,962,743 | `0d370f566e38558a2237ec6d3e29aa0712021224d676e7b286f571b7857a8119` |
| macOS Chromium + WebKit | 12143748527 | 94,055,128 | `19d960e6343343e2a005a65fc3e5d3d3be986ebde1c02e639067823dcb97583f` |

Linux used Chromium 153.0.8010.12, Python 3.12.15 and the existing pinned DejaVu
renderer. macOS 15.7.9/arm64 used Python 3.13.15, OpenSSL 3.0.21, Expat 2.8.2,
Chromium 153.0.8010.12 and WebKit 26.6. Playwright stayed 1.63.0. Environment
dictionaries matched each existing platform/engine manifest exactly.

## Inventory and review decision

For each renderer, all 145 older states were compared using the unchanged rules:
channel tolerance 16, maximum changed ratio 0.0005, maximum tile ratio 0.02.
**138 still pass and their prior approved bytes are retained**, not refreshed for
harmless cursor/compression differences. Their originating manifest hash and names
are recorded in the successor manifest.

Only seven older states change deliberately: `desktop-dashboard`, and the desktop,
laptop and narrow variants of `empty-dashboard` and `review-finished-dashboard`.
Direct inspection of all seven on each renderer confirms the new References link
and explanatory paragraph account for the added height. Existing corpus/review/
evidence statistics, completion notices and authority distinctions remain readable.

The 39 new captures per renderer are the three viewports of these 13 states:

- `reference-empty`, `reference-preview`, `reference-frozen`.
- `reference-successor`, `reference-history`, `reference-pagination`.
- `reference-conflict`, `reference-stale`.
- `reference-context-preview`, `reference-context`, `reference-context-restarted`.
- `reference-upgrade`, `reference-upgraded`.

Representative direct inspections included Linux successor/history/stale, conflict,
pagination, preview, frozen version, exact context and upgrade; macOS Chromium frozen
version, context preview/input, narrow batch preview/history/stale, laptop pagination
and desktop upgrade; WebKit conflicts, history, persisted exact context, successor,
pagination and narrow empty state. Linux CP7 captures were additionally verified
byte-identical to the directly inspected local captures. Complete inventory checks
are distinct from representative visual inspection: this is not a claim that every
pixel of every scientific passage was manually read.

The reviewed controls wrap without overlap or clipping; labels separate reference
truth, human attestation, evidence use and corpus authority. Conflicts stay visible
and ineligible by default. Context inspection shows actual selected passages and
omission reasons, not an implied classifier result. The explicit legacy-upgrade
warning and stale-save input retention remain understandable. Expanded technical
JSON appears as gray privacy-masked rectangles in test images; it is not a blank
production panel. No new mask, crop, timeout or tolerance was introduced for approval.

Long paginated cards/provenance still require vertical scrolling. This is an
acknowledged usability characteristic, not full-collection browser loading or a
collection-size cap. Automated layout/keyboard checks supplement image inspection;
neither is WCAG certification. WebKit testing is not native Safari or MacBook testing.

## Frozen review identities

Each renderer now has 184 images: 138 retained + seven deliberate replacements +
39 new states. Manifests preserve both capture provenance and retained-image lineage.

| Renderer | Capture report SHA-256 | Approved manifest SHA-256 |
| --- | --- | --- |
| Linux Chromium | `9a2ac489dab30863c2a6bbba2748f854be8303edfd9c2ee2f69d50f46025f114` | `4b249c9fec9e7468b120e1b45ba47bfdcda2960227126b78f878a53d81046178` |
| macOS Chromium | `b42c8638c07e2dac0c5e7962f2d30e4fe3146a04115851289b74161a73d85dd7` | `ac674ff7939378cebdb9d527bfad04845577fe2d4402214cdff2bc0d93783966` |
| macOS WebKit | `3f376ccf089ec14c49fd8ac0f2f5f6c89f7ccc80dbcd9a5b572eba4cd9461626` | `10c72743f844715513eec9a7ef2ce52849f7952ced27f1ac62bb1a3acbcc7c61` |

The final workflow must compare strictly against these identities. Its outcome and
any delivered wheel belong to their exact final source/run receipt, not this capture
run. No native Europe PMC transport resolution, model performance or researcher
acceptance is inferred from fixtures or visual approval.
