# Read-only local project browser

This is Checkpoint 1 of the `0.1.0a3.dev0` development branch, not a public a3
release. It opens an **existing** standalone project. It does not create projects,
change configuration, discover papers, acquire evidence, record reviews, invoke
models or alter scientific/workflow state. No migrations or new dependencies are
required for a current a2 project.

## Launch

Activate the environment containing this development build, then run:

```bash
corpustrail --version
corpustrail app "/path/to/existing/project" --open-browser
```

The expected version is `0.1.0a3.dev0`. The default URL is
`http://127.0.0.1:8766`. Keep the terminal open while browsing. Stop with Ctrl+C.
The terminal is the temporary launch bridge; paper navigation is entirely in the
browser. A desktop installer is not included.

If the port is occupied:

```bash
corpustrail app "/path/to/existing/project" --port 0 --open-browser
```

This chooses an available port and prints its exact URL. Use that `127.0.0.1` URL,
not a hostname alias. Omit `--open-browser` to open it yourself. Launching does not
contact any external provider or test any configured account.

## Mac installation from an unpushed local checkpoint

Public `0.1.0a2` does not include this UI. Since this development checkpoint has not
been pushed or released, `git pull` or reinstalling public main will not obtain it.
Transfer the supplied pure-Python development wheel to your Mac first.

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

4. Use Project dashboard → Papers / Corpus → a paper title → optional Advanced
   provenance. All actions in this application are read-only.

5. Stop with Ctrl+C. The separate legacy review UI still uses:

   ```bash
   corpustrail review serve "/path/to/your/project" --session-id YOUR_EXISTING_SESSION
   ```

   That review interface retains its original write/authority behavior. Do not
   confuse it with the new read-only browser.

The checkpoint was tested on Linux/Python 3.12. macOS native browser/installer
validation has not been performed here; no Mac installer is claimed. The code is
standard-library Python with packaged local assets and avoids OS-specific paths.

## Dashboard and papers

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

## Limits and troubleshooting

- No write actions, new review lifecycle, classifier, references or import UI.
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
