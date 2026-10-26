# Alpha API and development boundary

Generic development belongs in this package; project-specific scientific data is
separate. Use isolated environments rather than mixing distributions with the
same import/CLI names. No private source repository or project corpus is required.

## Alpha-supported

`corpustrail.project`: Project.create/open/configure/status/upgrade and typed
ProjectConfig components. Service accessors are identities, discovery, evidence,
reviews, review_sessions, prioritization, knowledge, knowledge_store and asreview.
`corpustrail.identity`: exact identifiers, bibliographic records, source references
and explicit enrollment plans. `corpustrail.discovery`: versioned SearchPlan and
CandidateObservation; plan/execute/canonicalize. `corpustrail.curation`: evidence
basis, review events/plans and deterministic broad-corpus state/history.
`corpustrail.export`: frozen unlabelled bibliography and exact-ID mapping.
`corpustrail.errors.ContractError`: input/contract failure.

Supported semantic invariants: explicit paths, mint-once identity, immutable
observations, insufficient != irrelevant, producer != authority, scores never
exclude or stop review. Alpha-supported does not promise permanent 1.0 signatures.
Serialized contracts/concepts/algorithms are separately versioned.

## Experimental

Checkpoints 1–2: `corpustrail.application.ProjectReads`,
`corpustrail.application.projects.ProjectController` and `corpustrail.local_app`
provide an operational read-only dashboard/catalogue plus explicit guided project
configuration. They are not method-blind review interfaces. See
[local API and isolation boundaries](LOCAL_APP_API.md) and
[guided configuration contract](PROJECT_SETUP_API.md).

Checkpoint 7 adds `Project.references`, `ContextStrategy` and `DerivedDependency`
as versioned scientific reference/context interfaces. The local controller and
operational UI remain separate from method-blind review. See
[reference storage, context and upgrade contracts](REFERENCES.md). This is not a
classifier engine or assessment-run API; CP8 remains separately gated.

Provider/resolver/parser/prioritizer plugins (explicit object injection); optional
TF-IDF/logistic implementation and fitted-model representation; advanced knowledge
queries, non-paper subjects and project vocabulary extensions. Model replacement
needs new provenance and validation, not promotion of old performance claims.

## Internal

`_internal`, HTTP handler classes, raw SQL connections/tables, built-in adapter
implementation classes, private algorithm helpers and test hooks. Importability
does not make these extension APIs. Use constrained KnowledgeStore plan/apply
operations, not arbitrary connection writes. Tutorial code is an explicitly
synthetic educational fixture, not a scientific extraction or screening service.

## Changes and upgrades

Do not modify frozen SQL migrations or old artifact hashes. Additive upgrades
require explicit backups; open/status never migrate implicitly. Alpha breaking
changes need release notes and, where cheap, transition aliases. Database rollback
means restoring a verified backup, not destructive downgrade migrations.

## Local developer checks

```bash
python -m pip install -c tools/validation-constraints.txt '.[dev,prioritization]' setuptools
python -m ruff check src tests tools
python -m unittest discover -s tests -p 'test_*.py'
python -m build --no-isolation
python tools/smoke_install.py
```

For an offline optional-ML smoke pass provide `--dependency-wheels DIRECTORY`.
No live provider/model calls are part of these tests. CI covers Python
3.11/3.12/3.13 on Linux; hosted runs require a separately approved repository.
The three-rule Ruff gate catches undefined exports/names and invalid local use,
without a formatting/type rewrite of historical algorithms. Origin tests remain
explicitly versioned when security fixes adapt copied code.

The constraints freeze validation/build libraries, not production requirements
or permanent model choices. No complete dependency vulnerability certification
is implied. The core remains standard-library-only. CI uses only this repository's
root layout and does not access another project or private fixtures.
# Experimental model adapter interface

`corpustrail.models` exposes `ModelConfig`, `TaskSpec`, `AdapterInfo`, `ModelAdapter`,
`ModelResponse`, `AdapterRegistry` and `ModelService`. These v0 APIs are experimental,
not scientifically validated extractors. See [adapter contracts, consent and
custom extensions](MODEL_ADAPTERS.md). No default model or required SDK is introduced.

## Optional ChatGPT assessment workspace

`/chatgpt` is a project-bound optional page reached from Models. Its protected
loopback API uses `corpustrail-local-chatgpt/v1`. Existing Host/Origin, session,
CSRF, CSP and bounded-JSON rules apply. Reads never initiate sign-in or model
requests. No endpoint accepts a credential, arbitrary URL or filesystem path.

- GET `/api/v1/chatgpt/configuration`: sanitized local connection and gate status.
- GET `/api/v1/chatgpt/populations` and `/references`: existing server-side version
  pagination (`offset`, `limit`, `cutoff`). No full collection browser loading.
- GET `/api/v1/chatgpt/previews/{32-hex}`: immutable actual transfer preview.
- POST `/connect`, `/cancel-connect`, `/models`, `/disconnect`, `/acknowledge-plan`
  under the same prefix: exact `{schema, confirmed:true}`. Connect returns an
  ephemeral browser authorization URL; never log, export or persist that URL.
- POST `/preview`: `request_id`, `actor`, `population_version_id`,
  `reference_version_id`, `model`. Explicitly freezes local inputs, not an
  assessment. Returns `preview_id` and `preview_sha256` with the actual manifest.
- POST `/confirm`: `request_id`, `preview_id`, `preview_sha256`, `confirmed:true`,
  `confirm_external:true`. Account eligibility, separate no-charge verification,
  current configuration and actual wire hashes are rechecked. The exact receipt
  links the new CP8 run. Repeated confirmation never resends completed requests.

Cancellation/results/history/proposal inspection use existing operational Curation
routes. The new fields and outputs are not added to method-blind review DTOs.
A dedicated OAuth callback listens only on a fresh `127.0.0.1` port, validates
state/PKCE/nonce and registration, and returns a non-secret link to the known app
origin. It is not a scientific API or an arbitrary redirect endpoint.
