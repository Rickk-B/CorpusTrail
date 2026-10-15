# Local projects, settings and read-only paper browser

This development build includes Checkpoints 1–4 of `0.1.0a3.dev0`, not a public a3
release. The project wizard and settings have explicit configuration writes.
The [Discovery workflow](DISCOVERY.md) prepares, approves and executes exact frozen
searches as separate actions, with local background progress and search history.
Publication details support [explicit eligible evidence retrieval](EVIDENCE.md).
Dashboard, catalogue, details and provenance browsing remain read-only. No page
automatically discovers papers, acquires evidence, records reviews or invokes
models. No migrations or new dependencies are required for a current a2 project.

## Launch

Activate the environment containing this development build, then run:

```bash
corpustrail --version
corpustrail app --open-browser
# Alternatively, open an existing project directly:
corpustrail app "/path/to/existing/project" --open-browser
```

The expected version is `0.1.0a3.dev0`. The default URL is
`http://127.0.0.1:8766`. Keep the terminal open while browsing. Stop with Ctrl+C.
Without a project, the starting page is **Welcome to CorpusTrail**. It explains
the research workflow and provides Create New Project / Open Existing Project.
**Home** remains accessible in every navigation bar; when a project is active,
Project dashboard, Corpus and Project Settings are also shown. Direct project
launches still open their dashboard. No project-specific links are shown on Home
before a project is selected.

The terminal is the temporary launch bridge; paper navigation is entirely in the
browser. A desktop installer is not included.

If the port is occupied:

```bash
corpustrail app "/path/to/existing/project" --port 0 --open-browser
```

This chooses an available port and prints its exact URL. Use that `127.0.0.1` URL,
not a hostname alias. Omit `--open-browser` to open it yourself. Launching does not
contact any external provider or test any configured account.

## Mac installation from a development artifact

Public `0.1.0a2` does not include this UI. Installing public main will not obtain it.
Download and unzip the approved [GitHub development artifact](../developer/DEVELOPMENT_BUILDS.md).
Keep its commit receipt: successive checkpoints share the development version.

1. Open Terminal and activate your existing CorpusTrail environment. Substitute
   your actual environment directory:

   ```bash
   source "/path/to/corpustrail-environment/bin/activate"
   python --version
   ```

   Use Python 3.11–3.13. Check that `python` is the interpreter belonging to the
   environment you intend to update.

2. Install the transferred wheel, substituting its actual location:

   ```bash
   python -m pip install --no-deps --force-reinstall "/path/to/corpus_trail-0.1.0a3.dev0-py3-none-any.whl"
   corpustrail --version
   ```

   Expect `0.1.0a3.dev0`. This changes the installed software, not the project or
   public Git tags. Optional numerical packages already installed remain optional.
   Keep your old software/environment available if you want to return to a2.

3. Launch with your actual **project directory**, the directory containing
   `corpustrail.project.json`, not the source checkout or database filename:

   ```bash
   corpustrail app "/path/to/your/project" --open-browser
   ```

4. Use Project dashboard → Corpus → a paper title → optional Advanced
   provenance. These browsing actions remain read-only. Projects and Project
   Settings now support explicit configuration operations as described below.

5. Stop with Ctrl+C. The separate legacy review UI still uses:

   ```bash
   corpustrail review serve "/path/to/your/project" --session-id YOUR_EXISTING_SESSION
   ```

   That review interface retains its original write/authority behavior. Do not
   confuse it with the new read-only browser.

Checkpoint 1 received user-performed macOS visual acceptance. New Checkpoint 2
tests run on Linux; native macOS wizard acceptance remains for the tester.
No desktop installer is claimed. The product uses standard-library Python and
packaged local assets.

## New Project / Open Existing Project

Run `corpustrail app --open-browser` for Home, then choose New/Open Project. The default
allowed projects root is `~/CorpusTrailProjects`. To explicitly choose a different
root at launch, use `corpustrail app --projects-root "/path/to/projects" --open-browser`.
Opening pages does not even create a missing projects-root directory.

Choose **New Project**, then follow six steps:

1. Enter a project name and topic description. Check the proposed folder/location.
2. Enter an explicit broad-corpus definition. Topical inclusion/exclusion criteria
   may be written in this existing scope field; they are not new independent fields.
3. Select installed discovery providers and optional search concepts, one per line.
   Optional credential configuration accepts an environment-variable name only.
4. Select evidence resolvers separately. Europe PMC currently requires an already
   known PMCID; this wizard does not add DOI/PMID enrichment.
5. Enter a configuration-author pseudonym (not a default reviewer for future
   sessions). **No publication authority** is selected by default. To grant initial
   corpus-decision authority, deliberately choose **Authorize corpus decisions**.
   The final summary shows that choice; **Create Project** confirms it. Creation
   is not an implicit administrator grant and creates no review session/decision.
6. Review the summary and press **Create Project**. This is the first action that
   creates files. The new dashboard confirms success; its paper counts start empty.

The pseudonym is the author of the configuration event. It is not a separate new
default-reviewer field: existing review sessions retain their explicit identities.
Configuring authority does not record reviews or change corpus membership.

**Open Existing Project** lists valid standalone projects immediately beneath the
allowed root, plus any project explicitly supplied on the launch command line.
Click the project name's **Open project** button. Outside-root projects require
an explicit launch path or a different allowed root; there is no unrestricted
HTTP filesystem picker. Symlink paths and existing target folders are rejected.
Project folder names use portable letters/numbers/hyphens/underscores/dots, while
project display names and scientific descriptions retain Unicode.

One launcher has one active project; opening another changes its browsing context.
Avoid keeping unrelated project tabs open in the same launcher. Settings writes
are pinned to their enrolled project handle and revision, not a guessed active ID.

## Project Settings — direct editing

The approved follow-up adds optional macOS **Move to Trash…** for confirmed,
inactive projects. See [safe removal](PROJECT_REMOVAL.md) before testing:
`--no-deps` does not install the native extra. Windows/Linux removal is unavailable.

Use **Project Settings** from the dashboard. All editable sections are directly
accessible on one page: project information, corpus definition, discovery,
evidence and reviewers. Change just the topic description and click **Save
Changes**—no wizard navigation is required. Edits remain in browser memory until
that explicit action; a change list and unsaved indicator show what will be saved.
The save/discard actions appear above the editable sections and stay in view on
wider screens; narrow screens use normal flow to avoid covering form controls.
**Discard Changes** restores the loaded saved values without writing anything.
Unchanged settings create no revision. A return link leads to the dashboard.

New project creation still uses six guided steps with a compact final summary.
Settings and creation are different interfaces over the same existing services.
Configuration version, update authors/times, definition hash and location remain
available under **Configuration information and history**. Technical details are
collapsed by default.

Saving uses the existing append-only configuration event/revision service. The
bootstrap is never rewritten. A stale revision is rejected: reload and reapply
your intended changes rather than overwrite newer settings. No-op saves add no
event. Duplicate clicks or exact retries within the running application's bounded
receipt cache return the original successful result. After restart, exclusive
project reservation and configuration revision checks still prevent overwrite;
reload/inspect persisted state rather than force a retry. Receipts are not a
durable job/recovery system.

The existing service freezes review sessions against **every** configuration
revision. The form requires acknowledgment that saved changes make existing
sessions stale; historical packets and saved work stay intact. Definition changes
also require an explicit confirmation, separate from authority/session warnings.
It never restarts sessions automatically. Scope/topic changes after authoritative review remain
prohibited. The error explains the restriction; no scope-migration policy is added.

The form preserves model configuration, concept extensions, retry settings,
policy identifiers and custom adapters it cannot edit. Existing concept language,
aliases and identifiers are retained for unchanged labels. New guided keywords
use `en`; language/alias editing remains advanced API/CLI work. An absent legacy
scope stays absent unless explicitly supplied, not derived from the project name.

The saved configuration version and its scope provenance remain available via
the existing configuration history/API. Secret values are never accepted, shown
or logged. Configuration does not imply successful connectivity.

## Storage, failures and removal

Projects stay in the location shown before creation. No persistent application
registry, browser storage, cache or new log directory is introduced. Enrolled
locations and retry receipts are temporary server memory. The HTTP server refuses
arbitrary paths, symlinks and overwriting existing project folders.

Interrupted creation preserves any reserved folder/partial database and does not
offer it as a valid project until initialization is complete. Inspect that folder
and use a fresh location; this checkpoint does not automatically repair or delete
partial projects. Filesystem checks are confinement safeguards, not a sandbox
against a malicious process already running with your own filesystem permissions.

`python -m pip uninstall corpus-trail` removes software from that environment, not
projects. Downloaded wheels are independently removable. See [storage ownership](REMOVAL_STORAGE.md).

## Dashboard and papers

**Corpus** means the publication collection, not that every listed paper has been
authoritatively included. In corpus, Out of corpus, Insufficient evidence and
Awaiting corpus decision remain separate; likely or unreviewed records are not hidden.

Home describes which workflow steps are available here, through existing commands
or the separate review UI, and which guided interfaces are planned. Its diagram
is explanatory, not an action that runs a search or retrieves evidence.
The **Review** navigation and dashboard action open [Guided Review](GUIDED_REVIEW.md):
explicit frozen sessions, draft autosave, non-authoritative Save & Next, Finish
Review and separate authorized corpus publication. Merely opening it is read-only.

The dashboard shows project description/scope, canonical count, authoritative
membership states, human-review/draft-history summaries, evidence availability,
recorded identity warnings and configured provider/resolver names.

Configured services are not automatically tested. Identity warning counts are
historical recorded warnings, not an inference that all remain unresolved. Session
completion is not invented from draft/event counts.

Catalogue pages are limited to 25, 50 or 100 records. Filtering and ordering run on
the server. Search matches title, authors or journal/source, including Unicode.
Order by title or year, with canonical identity as a deterministic internal
tie-breaker. Titles are navigation links; you do not copy canonical IDs.

The dashboard separates **Review activity** from **Corpus**. A recorded human
review can coexist with **Awaiting corpus decision**: only an explicit
authority-bearing decision changes corpus membership. Cards use **In corpus**,
**Out of corpus**, **Insufficient evidence** and **Awaiting corpus decision** as
presentation labels; the precise underlying states remain unchanged. Draft and
session-event counts are secondary activity details, never completed-review counts.
Configured services and historical identity warnings are available in disclosures.
The project description is not repeated as a fabricated corpus definition.

Membership is separate from review status. A saved non-authoritative human
observation can coexist with Not reviewed for membership. Draft history does not
claim a form is complete, current or recorded. Other non-human observations do not
become human decisions.

Evidence distinguishes abstract, verified structured document body, pending
identity and mismatch/invalid artifacts. Missing evidence never implies exclusion.
Only enrolled verified document-body text is offered for reading; it is paginated
and its artifact hash/path is checked. Viewing does not record a review or an
attestation that the full paper was read.

Advanced provenance is explicitly opened and paginated. It exposes technical IDs,
canonical field-selection lineage, bibliography, raw discovery observations,
review history, evidence records and identifier assertions. It is an operational
view and may contain prior judgments/methods; **it is not method-blind review**.
Existing method-blind sessions continue to use their separate allowlisted API.

DOI/PMID/PMCID are shown in normal bibliography where available. Operational
provider identifiers, including OpenAlex IDs, remain in Advanced provenance.
That view starts with technical identifiers (with Copy controls), source names
and a canonical-selection summary. **Show detailed lineage** and **Show raw JSON**
are separate, initially collapsed disclosures. Raw JSON preserves the complete
selected category/page; use its pagination for further records. Copying an ID
does not change project state. If clipboard access is unavailable, the read-only
identifier field can be selected and copied manually.

## Limits and troubleshooting

For updating/uninstalling the software without deleting your projects, see
[removal and storage ownership](REMOVAL_STORAGE.md).

- Only explicit creation/configuration, confirmed macOS Trash and approved
  discovery actions write state. No new review lifecycle, classifier, references,
  evidence acquisition or import UI.
- Catalogue cursors refer to a live revision, not a persisted population. If
  another process changes relevant project records, Refresh/reapply filters to
  restart pagination. The browser does not silently mix revisions.
- Read queries use existing schema/indexes and no persisted cache. Offset paging
  is bounded in response size, but deep pages and very large histories can be
  expensive. Synthetic tests are not production throughput claims.
- A metadata-only paper remains accessible, including a paper missing title or DOI.
- Raw provenance is never loaded by the normal dashboard/catalogue/detail screen.
- No browser credential storage, remote frontend assets or automatic model calls.
- Older schema errors require your normal explicit backup/upgrade workflow; this
  UI never upgrades a project or creates backups automatically.
