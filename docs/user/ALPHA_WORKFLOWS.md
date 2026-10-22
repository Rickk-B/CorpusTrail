# Research tools in the local alpha

Launch `corpustrail app --open-browser`, open a project and use **Research tools**
in the navigation. Everything below wraps existing scientific services. Opening
a workspace is read-only: no search, training, model call, export or approval runs.
No account or model is required for manual review. This is a development alpha,
not a promise of beta stability, real-model validity or a native desktop installer.

## A useful path through the application

1. **Projects**: choose a project location and scientific corpus definition.
   The topic description explains the project; the corpus definition fixes broad
   scientific scope; an exact query is a separately approved search input. Editing
   one does not silently edit the others or rewrite a saved plan.
2. **Explore**: choose a search service, write the exact query, preview and approve
   its bounded transfer. Search finds candidates; evidence retrieval obtains an
   eligible document for a known publication. Neither publishes membership.
3. **Corpus**: read metadata/abstracts and explicitly retrieve eligible structured
   text. Pending, failed or missing evidence is not automatic exclusion.
4. **Review**: choose your reviewer identity and freeze a candidate/evidence set.
   Save & Next records human observations. Finish Review does not publish them.
   An authorized person separately previews and confirms corpus decisions.
5. **Export**: preview and create an unlabelled bibliography of confirmed members.
   Download the CSV, receipt and frozen source snapshot. New decisions do not
   rewrite existing exports. Export contains no question-specific screening labels.

The dashboard links to the next action and shows observations separately from
membership. Method-blind Review intentionally excludes operational suggestions.
Knowledge, ordering and Curation are operational views, not blinded interfaces.

## Review order: optional, local and non-authoritative

This wraps the existing TF-IDF ordering service when its numerical extra is
installed. Without it the page explains the limitation and manual review still
works. Preview explicitly freezes the intended label cutoff. After confirmation,
the existing service snapshots current features, trains and ranks current
candidates. It is not retroactive evidence reconstruction at the label cutoff.
Insufficient-evidence judgments are not negative labels.

Inspect the saved ordering and its frozen training provenance. All ranks remain
accessible through server-side pages, including the low-scoring tail. Scores
are operational ordering values, not calibrated inclusion probabilities. There
is no stopping rule, hidden tail or automatic membership publication. A failed
stage preserves its native artifacts; inspection/restart never retrains it.

## Knowledge: observe, inspect, correct and validate explicitly

Browse source metadata, human review, verified representations and stored
assertions; filter by field or find a publication by title/author/journal.
Inspect evidence, producer, uncertainty, purpose-specific authority and history.
Exact records are available in bounded segments rather than giant initial payloads.

Choose **Use this publication** to record a human characterization. Select a
registered field and the evidence actually used, give a rationale, and preview.
Unknown is an explicit value, not a negative answer. Confirmation appends an
unvalidated, non-authoritative assertion. It does not change bibliography,
document trust, reference truth or corpus membership.

An existing stored assertion offers explicit validation, dispute/rejection,
retraction, successor/source/duplicate links and purpose-specific authority.
Browse related observations or grants instead of copying identifiers. Validation
and authority require a configured authorized reviewer and explicit purpose/policy;
a typed pseudonym cannot grant itself rights. Contradictory original assertions
and events remain inspectable. A successor link does not erase history.

## Models: experimental structured Knowledge, not an assessment engine

The page distinguishes configured workflow, installed adapter, credential presence,
declared locality and actual task history. No real server interoperability or
scientific performance is established by this alpha's offline fixtures.

Optional endpoint setup accepts an endpoint, configured model identifier and an
**environment-variable name**, never a secret value. Configuration is not a
connection or extraction. It creates a configuration revision; existing review
sessions retain their original snapshots and may become stale. Stop and inspect
that consequence before saving. A declared-local server can itself relay data.

A synthetic connection test sends a fixed message only, never paper evidence.
It needs its own preview/confirmation and, when declared external, transfer
permission. Success does not validate scientific extraction or membership.

For an exact structured task, find a publication, select a configured workflow,
registered field, instructions and available evidence. Metadata, an available
abstract, a verified document body or an exact verified-text range are distinct
inputs. Inspect the frozen input before explicitly running it. External transfer
requires separate exact-input consent and may have provider costs/privacy terms;
paid service use is not required by CorpusTrail. The task can only propose
non-authoritative Knowledge assertions, not corpus decisions or a CP8 engine.

Native task and connection histories include earlier CLI work. Interrupted tasks
are not automatically resent. Where an actual saved response exists, explicit
resume finishes that response only. Configuration, connectivity, capability and
scientific validation remain different states.

## ASReview results stay downstream

After a saved export, choose **Use this export for returned results**, select the
complete returned CSV and give stable question/review names and its ASReview
version. Preserve `corpustrail_paper_id` and `asreview_label`. Preview and confirm
exact mapping. The native service refuses missing, foreign, conflicting or
unsupported identifiers/versions; it does not guess from titles or row positions.
The mapping is question-specific and does not change broad-corpus membership,
references or ASReview itself. This narrowly supported result upload is not a
production literature importer. RIS export is not implemented.
Treat downloaded metadata as untrusted data if opening CSV in other software;
CorpusTrail does not execute formulas, macros or links in imported metadata.

## Failures, history and ownership

Each command has a preview and separate confirmation, guarded by project/config
revision and immutable receipts. Exact repeats return saved results; changed or
interrupted requests fail closed rather than silently rerun. A completed page
offers corpus/project/workspace next actions. A failure is not a scientific
judgment. Inspect saved work and prepare a fresh operation where appropriate.

Projects, raw evidence, reviews, reference/population versions, model outputs,
rankings, snapshots and exports are researcher-owned material, not disposable
cache. [Install/update/remove](REMOVAL_STORAGE.md) software independently. No page
scans unrelated folders, upgrades old projects automatically or runs on startup.
Production bibliographic/PDF import, real assessment engines, institutional adapters,
automatic queries, native installers and standalone phone support are future tracks.
