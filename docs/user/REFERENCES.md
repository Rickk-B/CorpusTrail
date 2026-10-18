# Reference collections and frozen selected contexts

From **Project dashboard → Reference Collections**, maintain logical **Known
in-scope** and optional **Known out-of-scope** examples. These are not filesystem
folders or authoritative corpus-membership decisions. Opening the workspace is
read only and contacts no external service. Existing membership is not copied.

## Add or correct examples

1. Give the collection a name and explicitly identify the acting human reviewer.
   This attribution is not a login and grants no membership-publication authority.
2. Find already collected publications. Inspect their publication/evidence pages
   as needed. Choose the evidence **actually used**, then stage an in-scope or
   out-of-scope label. Available evidence, displayed evidence and evidence used
   are distinct. Merely opening a document attests nothing.
3. Supply any rationale and explicitly attest the staged human labels.
4. **Preview Reference Batch** is read only. Inspect counts and definition;
   **Commit Reference Version** is the separate durable action.

Each browser batch holds up to 20 changes (the scientific API permits 500).
These are execution bounds, not collection-size caps. Lists and assignments are
server-paginated; the browser replaces pages rather than accumulating a collection.

Inspect saved immutable versions by name/version. **Prepare Successor Version**
keeps earlier versions unchanged. Stage a removal with a reason, or a corrected
label naming the prior assignment. Corrections require an explicit new evidence
choice; the UI never re-attests old evidence use automatically. Metadata-only
and no-evidence-claim label corrections are supported; for a reassessment using
new abstract/full text, explicitly stage that evidence through publication search.
Contradictory source labels stay visible and are ineligible by default until
explicit corrections/removals resolve them. Inspect an individual assignment's
frozen evidence and lineage, including inherited assignments, or page through
version correction history. No operation here saves a Guided Review observation,
completes a session, publishes membership or retrains anything.

The operational current-corpus-decision action, where offered, requires a separate
human attestation and preserves the exact source event. Imported/model proposals
are scientific-interface records only: they remain visibly unattested and cannot
claim human establishment. No production import parser or model is implemented.

## Inspect exactly selected context

Within a saved version, expand **Prepare a bounded context**. Explicitly choose
the target and its representation, an optional frozen held-out population,
per-label quotas and Unicode-character budgets. The deterministic local strategy
uses canonical identity order, **not** relevance scores, similarity or calibrated
probability. Target self-match is excluded by default. An explicitly enabled
operational self-match is not independent evaluation.

Only unconflicted, human-attested assignments under the frozen definition are
eligible by default. Only their attested evidence basis can supply text. Missing
evidence, conflicts, held-out labels, self-matches, duplicate canonical papers,
quotas and exhausted budgets have recorded omission reasons. Oversized examples
are omitted unless prefix truncation was explicitly enabled; ranges/hashes and
omitted-character counts then remain visible. Oversized target text is refused,
not silently shortened. Character budgets do not purport to count model tokens.

Preview is read only and exposes the precise proposed input in an explicit
details section. **Freeze Selected Context** preserves exact input bytes, selected
labels/passages, source hashes, traversal decisions, strategy and budgets. The
saved reader and provenance remain available after refresh/restart. This is a
local input artifact, not an assessment run, model invocation or scientific
performance result. Preparing context never authorizes remote transfer.

## Existing projects and data ownership

Accepted schema-37/38 projects open without automatic migration. To save
references/contexts, **Back Up and Enable References** explicitly upgrades the
selected project to additive schema 039 after a new project-local database backup.
Older publications, evidence, review sessions, populations and membership remain
unchanged. Close older software before upgrading; keep the backup and compatible
old software for rollback. Do not open an upgraded database in older software.

Frozen versions and selected inputs belong to the researcher and may contain
sensitive article text or judgments. They remain in the confined project database
and existing evidence artifacts, not public build artifacts or model services.
Existing saved contexts are never rewritten when references/evidence change.
