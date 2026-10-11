# Checkpoint 2 UX and onboarding follow-up

Branch: `development/v0.1.0a3-read-only-local-ui`. Version: `0.1.0a3.dev0`.
Base: `7f566ba7702f12bec174911cd187722124d0a590`, the user-tested Checkpoint 2
implementation. This follow-up is not a release or authorization for Checkpoint 3.
The complete approved implementation specification is unchanged.

## Researcher-facing changes

- Static, packaged **Welcome to CorpusTrail** at `/home`, also `/` when no project
  is active. Direct project launch still opens the dashboard. Home has no script
  or API calls; only local CSS is loaded. No application state is persisted.
- Seven numbered, connected workflow cards: four columns on wider screens, two
  on medium screens, one on narrow screens. Short capability captions distinguish
  current local UI, existing commands/separate review UI, and planned guided UI.
  ASReview is optional downstream question-specific screening, not corpus membership.
- Home/New/Open actions reuse existing project routes. Project-specific navigation
  is hidden without an active project. All normal collection navigation says
  **Corpus**, while keeping awaiting/excluded/insufficient records accessible.
- Six-step creation remains guided. Existing settings instead displays all sections
  with a top save/discard bar (sticky on wider screens), change summary, unsaved
  indication, return-to-dashboard link and collapsed configuration history/details.
- Description-only saves require no step navigation. Discard writes nothing;
  no-op saves do not submit configuration. Sensitive scope, authority and frozen
  session changes retain explicit confirmations and the existing scientific guards.
- Wizard headings are inside named fieldsets rather than border-straddling focused
  legends. Programmatic step focus moves to a noninteractive heading; input/button/
  textarea/link keyboard focus remains visible. Creation summary uses a compact
  responsive definition list, with complete values rendered as text.
- Frontend projection preserves existing provider instance IDs/adapter aliases,
  unchanged credential-variable names, custom entries and resolver order. It does
  not manufacture scientific metadata or introduce configuration fields.

## Unchanged boundaries

No scientific/configuration service, application read model or project controller
changed. HTTP changes only select packaged pages and navigation from launcher
state. POST allowlists, CSRF/session/Host/Origin/CSP protections and versioned form
contracts are unchanged. No new migration, schema or production dependency.

Existing `Project.configure` remains the only scientific configuration enforcement
point. Revisions, stale-write rejection, authority checks, post-authority scope/topic
restrictions and frozen-session guards remain unchanged. Historical bootstrap,
review packets/events, membership, identity, evidence, ranking, Knowledge/model
and ASReview state are not rewritten. Definition confirmation is a UI disclosure,
not a new authority policy or a replacement for server-side guards.

The pseudonym is configuration authorship, not a new default-reviewer field. Editing
only that pseudonym cannot create a configuration revision; the UI explains this.
Actual scientific configuration changes may record the selected pseudonym.

## Local verification

Linux / Python 3.12.3, with the existing validation constraints and optional-ML
extra in an isolated environment. No commercial keys or external scientific calls.

| Surface | Result |
|---|---|
| Project/controller/HTTP/packaged-JS suite | 38 passed |
| Existing browser/security/pagination/identifier/provenance suite | 29 passed |
| Complete standalone suite including optional ML | 384 passed, no skips |
| Clean wheel core suite | 384 run; passed, 46 optional-ML skips |
| Clean wheel optional-ML suite | 384 passed, no skips |
| Clean sdist-built wheel core suite | 384 run; passed, 46 optional-ML skips |
| Clean sdist-built wheel optional-ML suite | 384 passed, no skips |
| Core/ML offline tutorials and installed CLI examples | Passed |
| Sdist uninstall/reinstall and project reopen | Passed; project status preserved |
| Packaged Home/wizard assets and metadata | Passed; MIT, development version, no personal author/contact fields |
| Ruff correctness checks, JavaScript syntax, whitespace checks | Passed |
| Existing review/method-blind, identity, evidence, Knowledge, model and ASReview regressions | Passed in complete suites |
| Existing 20,000-record bounded catalogue regression | Passed; not a production performance claim |

The actual packaged JavaScript and a small Node DOM contract harness exercise a
real loopback server: creation through all six steps, response-loss retry without
duplication, direct description-only save, exact preservation of unrelated fields,
discard/no-op/pseudonym-only edits, reopening through the project selector, sensitive
confirmations and stale-tab rejection. Provider-alias/custom-entry/order preservation
is separately exercised within that frontend contract. The harness checks behavior,
not browser layout, CSS rendering or assistive-technology certification.

The five-paper fixture has five recorded non-authoritative reviews, no published
corpus decisions, a pending document and a frozen session. Home/entry/settings/
dashboard/catalogue/detail/provenance navigation preserves its file hashes. Existing
tests also prove explicit permitted settings edits affect configuration history
only, with scientific tables, bootstrap and old review packets unchanged.

## Privacy, storage and limitations

Changed files have no findings under existing bounded privacy heuristics. The
repository-wide credential-URL match is the existing synthetic invalid-URL rejection
fixture, not a real credential. Legacy terminology matches remain unchanged test/
schema/specification contexts, not imported private research data. No privacy or
security certification is claimed. MIT attribution and omitted personal package
metadata remain unchanged; Git commit identity is verified separately before commit.

No new persistent state, registry, logs, cache, browser storage or project locations.
Existing root/enrollment/symlink/no-overwrite rules remain in force. Removing the
package does not remove researcher projects. There is no deletion/uninstall UI.

No discovery/evidence execution, new review lifecycle, reference/population/import/
classifier/model/MCP/desktop functionality was started. Real model-server
interoperability remains unvalidated. Existing session invalidation on every saved
configuration revision is unchanged and explained, not relaxed for convenience.

Native macOS visual acceptance of this follow-up is pending the user's artifact
test. Their accepted native Checkpoint 2 results are not represented as validation
of the new Home, settings layout or responsive diagram.

## Hosted artifact boundary

The existing Actions workflow gates the development artifact on Python 3.11–3.13
acceptance. Build receipt records the exact new source SHA, original Checkpoint 1,
earlier distribution follow-up and accepted Checkpoint 1 lineage separately. It
does not claim the new wheel was built from this document's earlier base commit.
The completion report supplies hosted run/results, artifact name/checksum and expiry.
No main merge, tag, GitHub Release or PyPI publication is authorized here.
