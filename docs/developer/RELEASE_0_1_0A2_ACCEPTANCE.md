# CorpusTrail 0.1.0a2 local release acceptance

Date: 2026-10-03. Feature: experimental External Model Adapter v0.1.
Public predecessor: `v0.1.0a1`, target
`e756744f57589ec1a103cf84e746bc7b05ff3713`; its tag/release are preserved.

## Scope and lineage

The development branch descends directly from the public predecessor. Reviewed
checkpoints: generic core `7377a681d20ba94566b7f117f42fd4c9e3edf6b4`, endpoint
implementation `5c5c634d4298e4a463616282bd28ce05a0f08559`, and offline validation
`203dd091be05df122a542dad7fb26d419ff36214`. Only model-adapter infrastructure,
associated migrations/configuration/CLI, tests/docs and release tooling changed.
Release preparation changes version and documentation only, not model behavior.
Historical compatibility schema/provenance resources remain preserved. No research
data, private runtime, credentials, installed-model state or generated files are
part of the release. All commit identities remain project-neutral.

## Local acceptance (Python 3.12)

All tests used synthetic/offline inputs, local mock servers and cached dependency
wheels. No real model, paid API or literature-provider request was made.

| Surface | Result |
|---|---|
| Clean wheel core install, outside checkout | 305 tests; 259 passed, 46 expected ML skips |
| Clean wheel optional-ML install | 305 passed |
| Actual sdist build → wheel → clean core install | 305 tests; 259 passed, 46 expected ML skips |
| Actual sdist build → wheel → clean optional-ML install | 305 passed |
| Sdist uninstall/reinstall and deterministic reopen | Passed in both environments |
| Focused generic/compatible model tests | All 52 included and passed in each full suite |
| Installed CLI/version/config/status/help | Passed; `0.1.0a2` |
| Core/ML offline tutorial and coupling/isolation | Passed |
| Ruff and diff whitespace | Passed |
| Installed-wheel ASReview 2.2 temporary import/writer/exact-ID mapping | Passed; 3 unlabelled records, corpus unchanged |

The tutorial preserves 9 observations, 8 canonical papers, 1 pending document and
3 exact mapped records for each of two independent downstream questions.
The ASReview browser/LAB interactive workflow was not tested.

Temporary acceptance-build identities (not PyPI uploads; this report is a later
documentation-only addition):

- Wheel: `sha256:8c6b09b3ef2a1b5484c1d27dc06322d908933b1babf37665ac3c5227aafdfd06`.
- Sdist: `sha256:1ac048ad1a5892ac1e3d98285c447cea198fdfa8bab81b1945c113f8b2b6842a`.
- Wheel from sdist: `sha256:8f52f5801e3e25f4476a6782fa2af6b860deb3149e761996b37a4e0e4b479a2a`.

## Privacy and security checks

Tracked source population, changed commit identities and both distribution
contents were inspected. No blocking owner identity, credential/contact, private
path, forbidden binary or research-data finding was detected. The sole URL-with-
credential match is an intentionally fake unsafe-URL rejection fixture. Legacy
scope markers exist only in already-preserved compatibility SQL and semantic
protection/audit tests, not project defaults or scientific datasets.

Wheel and sdist metadata report `0.1.0a2`/MIT, omit personal author/maintainer/contact
fields and require no core runtime/model SDK dependency. CITATION.cff remains absent;
the MIT notice remains `Copyright (c) 2026 CorpusTrail contributors`.

Tests verify environment-owned credentials are absent from project configuration,
status, provenance and error artifacts; exact remote-plan consent blocks unauthorized
requests; local declarations need no remote-transfer consent; model responses are
untrusted and schema/evidence-validated before immutable non-authoritative writes.
Corpus membership, human authority, canonical identity, document trust,
prioritization and downstream label spaces remain separate. Practical checks are
not a formal security/privacy certification or an opaque-secret guarantee.

## Exact interoperability limitation

**No real OpenAI-compatible model server was tested.** OpenAI hosted API, Ollama,
LM Studio, vLLM and all other named real providers/runtimes remain unvalidated.
Offline/mock validation establishes the implemented contract and infrastructure,
not real-provider compatibility or scientific extraction accuracy. Use the built-in
synthetic connection test and a bounded structured-task check for a chosen endpoint.
No predicate is approved for unattended extraction.

The [earlier interoperability report](MODEL_ADAPTER_V01_INTEROPERABILITY.md) retains
the bounded endpoint-discovery result and optional future real-test checklist.
Hosted Python 3.11–3.13 CI and public-clone acceptance are separate release gates
after merging; this document records local acceptance, not their eventual results.
