# Explore publications through the local app

Open a project, then choose **Explore**. No database is contacted by opening
this page, reading history or preparing a preview.

1. Enter one exact search query, or start from a saved search idea. This does
   not edit Project Settings. The chooser copies one label into the standalone
   query; it does not run all concepts. Aliases are not automatically expanded. Providers
   interpret their own query syntax; separate language/date filters are not
   implemented. The preview shows the actual adapter parameters.
2. Select the configured databases you want. Installed adapters are OpenAlex,
   Crossref, Europe PMC and Semantic Scholar. Disabled/missing configuration is
   explained. A configured credential environment variable must be set before
   launch; never paste its value into the browser. Unauthenticated adapter mode
   does not guarantee access or indicate that connectivity has been tested.
3. Optionally adjust bounded page size, page count and retries. These limit the
   request, not the scientific corpus. A bounded search is not exhaustive coverage,
   automatic exclusion or a stopping rule.
4. Click **Preview Search Plan**. Review every database's exact query/parameters
   and cursor policy. Advanced details preserve initial URL, runtime-cursor rule,
   adapter identity/code hash, configuration revision and provider plan identities.
   Future response cursor values cannot be known before running.
5. Review the disclosed external queries and selected databases, and exact-identity/
   source-provenance organization. **Approve Search Plan** explicitly authorizes
   both operations together for this exact plan. Approval itself sends nothing and
   makes no corpus-membership decisions; both authorizations remain recorded.
6. Click **Run Search**. Only the approved frozen plan is executed. Editing
   invalidates that preview/approval; configuration changes require a new preview.
   Queries/settings go to the selected services, with your credential header if
   configured. Paper text, review labels and membership decisions are not sent.
   Third-party terms apply; CorpusTrail supplies no shared account or key.
7. Inspect factual progress, provider outcomes, linked publications and provenance.
   **View Corpus** opens the existing catalogue, including undecided candidates.

## Interpret counts and outcomes

- **Provider observations preserved:** source records saved by the existing
  executor. Records returned by different databases may describe one publication.
- **Unique publications linked:** distinct canonical identities linked to this
  search, not the size of the whole project.
- **Publications created by this search:** identities whose preserved enrollment
  action was create. Previously known publications are linked identities not
  created by this search. Repeating a search can add observations without adding
  duplicate identities.
- **Observations not linked:** organization may still be pending, or identifiers/
  normalization may require inspection. This is not exclusion.
- **Completed bounded search:** the selected work finished. Page/provider limits
  remain visible; completion is not proof that the literature has been exhausted.
- **Partial / failed:** inspect each provider's outcome and any preserved work.
  Successful results are not erased when another database fails. Missing evidence,
  errors and provider ranking never establish corpus membership.

Exact DOI/provider/source identity is used by existing canonicalization; similar
titles do not authorize a merge. Discovery never records human review or publishes
membership. CorpusTrail's broad collection remains separate from ASReview's
downstream question-specific screening.

## Refresh, stopping, repetition and interruption

Browser refresh/navigation does not stop a running job or resend a search. Open
**Previous searches** to inspect it again. Only the owning launcher offers **Stop
after current provider**: the current provider's entire bounded operation and
organization may finish before stopping. Another launcher's operation is not killed.

Closing/switching the active project does not release the worker's own project-use
lease. Removal remains blocked while cooperating processes use the project.

Stopping/crashing the host can interrupt work. On a later launch, unfinished parent
jobs without a live worker are shown as **Interrupted**, without writing on page
load, claiming success or automatically resending requests. Partial scientific
records remain inspectable. There is no crash-resume or automatic reconciliation.
Prepare a new explicitly approved search if you choose to repeat; inspect earlier
uncertain work first. A completed command retry returns the original execution,
not another network job.

Prepared plans, approvals and job receipts are researcher-owned files under the
project's configured data directory, in `discovery-workflows/v1/`. They travel with
the project and are not disposable cache. Pip uninstall does not remove them.
Historical publication cards show current canonical metadata; immutable candidate
population snapshots are a later checkpoint.

## Validation limitation

Mandatory acceptance uses deterministic offline mocked transports with the actual
installed adapter query/normalization contracts. This checkpoint does not claim
live-provider access, native browser layout acceptance or new model interoperability.
