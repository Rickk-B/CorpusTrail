# JATS text-preservation correction (Checkpoint 4)

## Defect and bounded correction

The 2026-10-15 single authorized Europe PMC capture for PMC13558126 passed
`bounded-inert-jats/v2` and exact article identity verification. Its 417,134 bytes
have SHA-256 `0a9f6b9202435e3074865506ba516c5c9456f55945125341e2a4adbfcf5ecdec`.
An offline rendering comparison found five `table-wrap/table-wrap-foot/fn/p`
paragraphs (1,847 normalized characters) missing from derived text. The original
XML was intact. No additional live request is part of this correction.

The existing renderer now handles table-footnote paragraphs and labels as
separate text blocks in their source order. Inline text retains the existing
whitespace normalization and plain-text markup semantics. Distinct notes are
not merged, and repeated source text is not content-deduplicated. Section paths
and character offsets retain their existing representation; parent sections may
have multiple contiguous segments when a child section interrupts them.

A bounded audit found the same omission for explicit figure/section footnotes,
direct figure/boxed explanatory paragraphs, and supported blocks directly under
the article body. These use the same helper. Parent continuations and direct body
paragraphs now stay in source order rather than moving ahead of nested sections.
Existing table captions, figure captions, table cells (including alternatives)
and non-footnote paragraph content remain supported.

## Scientific boundaries and provenance

Both native JATS and publisher-XML parsers advance to **v4**, because they share
the corrected renderer. XML policy remains **bounded-inert-jats/v2**. No change
to XML validation, entity/DTD refusal, resource limits, exact publication identity,
trust decisions, acquisition retries, review or membership authority is made.
No schema, production dependency, automatic re-render or historical rewrite is
introduced. New derived records identify v4; historical records retain their
original bytes, versions and outcomes. The additive code-origin receipt chains
from the preserved v3 receipt. Frozen evidence eligibility already hashes the
native renderer, scientific service and XML boundary; an old eligibility hash
cannot silently authorize the changed renderer.

## Remaining limitations

This is a bounded scientific text projection, not complete JATS/schema support
or a facsimile. Media, mathematical layout and arbitrary unsupported block
wrappers are not interpreted. Back-matter bibliographies and footnote groups
are outside the current title/abstract/body projection. Inline formatting is
flattened as before; scientific claims are not evaluated. Do not claim all
possible JATS structures are covered. Future additions require focused tests
and a new renderer/provenance identity where behavior changes.

## Acceptance

Minimal invented fixtures cover labelled/unlabelled and multiple notes,
multi-paragraph notes, inline formatting, references, Unicode, captions,
distinct tables, parent/child ordering, exact offsets/reconstruction, and history
preservation. Browser fixtures exercise a long note through actual acquisition,
reader, refresh and application restart in all three viewports. Native macOS
visual acceptance is separate from Linux headless Chromium checks.
