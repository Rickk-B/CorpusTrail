# Operating CorpusTrail

CorpusTrail maintains a broad topic corpus. ASReview later applies the eligibility
criteria of a particular review question. Keep those label spaces separate.

## Installation

Use a dedicated venv with `python -m pip install -e .` from a supplied or cloned
source tree, or install a supplied wheel/sdist. Core needs no ML, ASReview, model
SDK or credentials. `.[dev]` adds build/Ruff; `.[prioritization]` adds sklearn.
No public package index is assumed. Linux/Python 3.11–3.13 is the tested matrix.

## Configuration and initialization

```bash
corpustrail project init /tmp/my-materials --config /absolute/path/to/project.example.json --created-by project_owner
corpustrail project status /tmp/my-materials
```

Use the [complete credential-free example](project.example.json). Initialization
refuses existing targets. Commands take an explicit project root; internal paths
are normalized project-relative paths, not working-directory lookups. Default
projects have no provider/resolver/authorized reviewer. The example authorizes a
stable pseudonymous role but makes no external provider a default.

`Project.open(path).config.to_dict()` returns the current serializable config;
`configuration_history()[-1]['event_id']` gives its revision guard. To change it,
prepare a complete replacement JSON with config_version incremented by exactly one:

```bash
corpustrail project configure /tmp/my-materials --config /absolute/path/to/new-config.json --expected-event-id CURRENT_CONFIG_EVENT_ID --created-by project_owner
```

This appends an event; never edit bootstrap/history manually. Identity/storage
paths are immutable. Scope changes after authoritative review need a future
explicit policy migration. Older schemas use `project upgrade PATH --backup NEW_PATH`;
backup path is project-relative and must not already exist. Open/status never
upgrade implicitly. Config carries env-variable names, not secrets; unknown
token/password fields are rejected. Do not put secrets into topic/query free text.

## Discovery and providers

Built-in optional keyword adapters: openalex, crossref, europepmc, semantic_scholar.
Configure provider_id equal to adapter, for example
`{"provider_id":"openalex","adapter":"openalex","credential_env":"CORPUSTRAIL_OPENALEX_TOKEN"}`.
The token is set privately in that environment variable, never in the JSON.
Credential headers are supported only for OpenAlex/Semantic Scholar; omitting a
credential_env does not imply the remote provider permits unauthenticated calls.
Offline/core use never needs credentials. No graph or recommendation default exists.

```bash
corpustrail discover /tmp/my-materials --provider openalex --run-id search-01 --query 'porous ceramic' --max-pages 1
```

This plans only. Repeat with `--execute --confirm-external` after approving transfer.
Max-pages counts logical pages including failures; max-attempts is at most three
physical tries per page. Typed failures/429/Retry-After/raw responses persist.
Excessive retry wait stops rather than being shortened. No silent provider switch.
Concept labels supply queries; aliases do not auto-expand. An interrupted run is
retained and fails closed, not silently retried. Use a new inspected run ID.

```bash
corpustrail candidates /tmp/my-materials --run-id search-01
corpustrail candidates /tmp/my-materials --run-id search-01 --canonicalize --approve-identities --approve-aliases
```

Identity approval is not corpus inclusion. Exact identifiers/aliases join records;
all contributing observations stay visible. Similar titles alone never merge works.
DOI-missing papers keep origin-minted IDs after later DOI recovery. Candidate JSON
contains canonical IDs; retain returned run/model/session/export IDs. Canonical
metadata preserves selected-field sources/alternatives; missing stays missing.

## Evidence and document trust

```bash
corpustrail evidence /tmp/my-materials --paper-id CANONICAL_ID
```

The built-in Europe PMC resolver requires verified PMCID and explicit ordered
evidence.resolvers configuration. `--resolve --confirm-external` attempts legitimate
acquisition. No paywall bypass/PDF/OCR fallback is implied. Metadata, abstract,
structured text and original documents are distinct. Pending/mismatched artifacts
are not trusted through review/knowledge/export. XML article identifiers establish
identity, not scientific validity. Missing evidence never implies exclusion.

## Broad-corpus human review

```bash
corpustrail review prepare /tmp/my-materials --session-id curation-01 --reviewer project_reviewer_01 --authoritative --mode operational
corpustrail review serve /tmp/my-materials --session-id curation-01 --port 8765
```

Open http://127.0.0.1:8765; restart the same serve command to resume. Drafts autosave;
Record human decision explicitly appends immutable history. Without authoritative,
a human event is non-authoritative. Authorized role IDs are configured explicitly.
Enough evidence? If yes, include/exclude broad corpus with reviewed evidence and
rationale. If no, record insufficient, never forced exclusion. Metadata-only
decisions are allowed. Opening a source does not automatically mean reading it fully.

Method-blind is the default mode: no method/query, prior model scores or experimental
arm is shown. Operational priority is an ordering aid only. All candidates remain
accessible; no automatic cessation/exclusion exists. `corpus PATH` and
`review status PATH --session-id curation-01` report progress. Current states are
included, excluded, insufficient_evidence, unresolved and not_reviewed.

## Optional prioritization

```bash
corpustrail prioritize train /tmp/my-materials --label-cutoff 2026-10-02T00:00:00+00:00
corpustrail prioritize rank /tmp/my-materials --model-id RETURNED_MODEL_ID --run-id ordering-01
corpustrail prioritize inspect /tmp/my-materials --run-id ordering-01
corpustrail review bind-ranking /tmp/my-materials --session-id curation-01 --run-id ordering-01
```

Choose a project-appropriate cutoff. Both eligible human classes are required;
insufficient/model/downstream labels are not automatic negatives. Training snapshot
contains exact event IDs, features, parameters/versions. Later rankings use new IDs;
order changes only on explicit selection. Low-priority candidates are never hidden.

## Knowledge Layer

```bash
corpustrail knowledge show /tmp/my-materials --paper-id CANONICAL_ID
corpustrail knowledge vocabulary /tmp/my-materials
corpustrail knowledge conflicts /tmp/my-materials
corpustrail knowledge verify /tmp/my-materials
```

Scoped/versioned predicates organize observations, not universal truth. Producers,
evidence, uncertainty, authority and lineage stay separate. Model/parser assertions
are non-authoritative by default; human validation is an explicit later event.
Unknown is not inferred and conflicting observations coexist. Project predicates
need distinct namespaces. Field-name similarity never establishes legacy semantics.
`knowledge assert --input FILE` plans one assertion; `knowledge plan --input FILE`
plans a batch. Inspect/save the returned plan, then `knowledge apply --plan FILE --apply`
for an explicit additive write. No unattended model extraction is shipped.

## ASReview handoff

```bash
corpustrail export asreview preview /tmp/my-materials
corpustrail export asreview plan /tmp/my-materials --export-id corpus-01 --out data/plans/corpus-01.json
corpustrail export asreview create /tmp/my-materials --snapshot data/plans/corpus-01.json
corpustrail export asreview inspect /tmp/my-materials --export-id corpus-01
```

Default population is authoritative broad-corpus members only. Export contains
unlabelled bibliography and stable custom IDs, not corpus labels, ranking scores,
knowledge assertions or generated seeds. Neither title nor abstract available
fails export rather than silently dropping the member. Import dataset.csv into a
new downstream question. No SDK is needed; optional SDK 2.2 was tested, not 3.x.

```bash
corpustrail export asreview map /tmp/my-materials --export-id corpus-01 --results /absolute/path/to/results.csv --review-id review-A --question-id question-A --mapping-id results-01 --asreview-version 2.2
```

Requires complete original-input-aware results retaining corpustrail_paper_id and
asreview_label. SDK Record projections or selected-only exports may lose necessary
fields/population. No title/row fallback. Multiple downstream questions remain
isolated; their labels cannot change broad membership or generate seeds automatically.

## Provenance/reproducibility

Every source, alias, decision, ranking and assertion retains history. Hashes are
integrity identities, not signatures. Same frozen snapshot reproduces scientific
contents, not necessarily zip/tar bytes across build times. Export snapshot is a
consistent SQLite transaction, not a historical state inferred from a supplied
timestamp. Keep original snapshots/backups. Library versions are model provenance.
