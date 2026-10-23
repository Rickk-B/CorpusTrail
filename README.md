# CorpusTrail

**From literature discovery to a curated research corpus.**

CorpusTrail helps researchers find, organize and evaluate scientific publications.
Build a collection around your research topic, keep track of available evidence,
and understand how publications became part of your corpus. A transparent research
trail helps you revisit decisions and explain or reproduce your work.

```text
discover → canonicalize → acquire evidence → curate → prioritize
         → organize knowledge → export to ASReview
```

CorpusTrail asks **“Does this paper belong in my broad scientific topic corpus?”**
ASReview screens **“Does this paper satisfy the criteria for this particular review?”**
Broad-corpus membership is not systematic-review eligibility.

This development branch is **0.1.0a3.dev0**, not a published release. The public
`0.1.0a1` and `0.1.0a2` releases remain frozen. APIs and schemas may change before 1.0.
Linux/Python 3.11–3.13 is the tested target.

## Install

From a cloned or supplied source tree:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
corpustrail --version
corpustrail --help
```

Core has **no runtime dependencies**. No credentials, ML libraries, model provider
or ASReview installation are required for local use and the offline tutorial.
Use an isolated environment; do not install conflicting implementations into it.

## Offline quick start

All tutorial records and scripted decisions are invented software fixtures:

```bash
python -I -m corpustrail.tutorial /tmp/materials-demo
corpustrail project status /tmp/materials-demo
corpustrail corpus /tmp/materials-demo
corpustrail export asreview inspect /tmp/materials-demo --export-id fixture-corpus
```

Use a new target path. Expected result: nine observations → eight canonical papers;
three members, two non-members, one insufficient, one unresolved and one unreviewed;
one pending document; three unlabelled exports with exact mappings for two questions.
No network is used. Follow the [tutorial](docs/user/TUTORIAL.md) to inspect each stage.

Optional learned ordering requires the numerical extra, installed separately:

```bash
python -m pip install -e '.[prioritization]'
python -I -m corpustrail.tutorial /tmp/materials-demo-ml --prioritize
```

## Local project setup and browser (development checkpoints)

After installing this development build into your existing environment:

```bash
corpustrail app --open-browser
# Or open an existing project directly:
corpustrail app /path/to/existing/project --open-browser
```

Start at **Welcome to CorpusTrail**, with a compact workflow and New/Open Project
actions. A direct project launch still opens its dashboard. Browse **Corpus**, paper
details, evidence status and optional advanced provenance. Browsing remains read-only.
New Project keeps a six-step wizard; Project Settings is a direct-edit page with
Save Changes and Discard Changes. Configuration saves preserve their history.
The [Explore page](docs/user/DISCOVERY.md) previews an exact saved search, requires
explicit approval, then runs a bounded background search with progress/history.
Discovery collects candidates, never membership decisions. Opening pages never
contacts external services. Publication details now support explicit eligible
[Europe PMC structured-text retrieval](docs/user/EVIDENCE.md), with verification
outcomes and evidence provenance. Missing PMCID prevents that retrieval; automatic
DOI/PMID enrichment is not implemented. [Guided Review](docs/user/GUIDED_REVIEW.md)
freezes a publication/evidence set, autosaves drafts and records non-authoritative
human observations through Save & Next. Finish Review preserves undecided papers;
only a separate authorized confirmation publishes corpus membership atomically.
The existing `corpustrail review serve` interface retains its legacy per-paper
contract. [Research tools](docs/user/ALPHA_WORKFLOWS.md) now expose existing local
review ordering, Knowledge observations and history, optional model configuration
and exact structured tasks, and unlabelled ASReview export/results mapping.
The [RIS exchange and scoped offline demo](docs/user/RIS_EXCHANGE.md) provide the
first explicitly approved file import/export route, including available abstracts.
Import creates candidates, never corpus decisions. Other formats remain gated.
The [Populations workspace](docs/user/POPULATIONS.md) freezes origin-independent
candidate versions, retains lineage, combines exact canonical sets and feeds
Guided Review. RIS is the implemented import format; other production import formats remain separately gated.
The [Reference Collections workspace](docs/user/REFERENCES.md) adds explicit
human-attested example versions, successor corrections and exact locally frozen
selected contexts. It does not run an assessment engine or publish corpus membership.
The [CP8 assessment infrastructure](docs/developer/CLASSIFICATION.md) freezes generic
engine plans, chunked runs, typed observations/failures and validation provenance.
Its interchangeable deterministic engines are offline test fixtures. No real model
is installed or selected. The [Curation and Audits workspace](docs/user/CURATION.md)
adds bounded result/disagreement views, frozen random or stratified audits,
explicit assisted human review, successor references and separately requested
reassessment. Manual review always works without an engine. Synthetic examples
demonstrate software contracts, not scientific performance.
Assessments never publish membership or change human authority.
See the [local UI guide](docs/user/LOCAL_UI.md) for installation and launch steps.
The one-command launcher is the installation bridge, not a native installer.
No model, account or optional numerical package is needed for manual curation.
Optional [macOS project removal](docs/user/PROJECT_REMOVAL.md) moves a confirmed,
inactive project to native Trash; it never falls back to permanent deletion.

## Scientific boundaries

- Prioritization changes review order, never inclusion authority; the low-ranked
  tail remains accessible. **No automatic stopping rule** is provided.
- Insufficient evidence is not irrelevance. Metadata-only human decisions are allowed.
- Knowledge assertions preserve producer, evidence, uncertainty, conflicts and lineage.
  Model-generated knowledge is **not automatically authoritative**.
- Unattended LLM extraction is **not a production alpha feature**.
- Experimental [model adapters](docs/developer/MODEL_ADAPTERS.md) require an
  explicit task and user-owned configuration/credentials; remote evidence calls
  require exact-plan consent. No model is required or selected by default.
  [Connect your own model](docs/user/MODELS.md) through a compatible endpoint;
  you supply the endpoint/account/credentials, never a shared CorpusTrail key.
  The experimental reference adapter is offline/mock-tested only; real-server
  interoperability has not yet been validated by the project.
- Provider/model adapters are replaceable; no model or discovery provider is mandatory.
- Pending/unverified documents are not trusted evidence.
- External discovery/acquisition requires explicit transfer confirmation.
  The review UI is localhost-only, not a multi-user service.
- ASReview exports are unlabelled bibliography; no broad-corpus labels, priorities
  or model assertions become question-specific review decisions.

## Documentation

- [User guide](docs/user/GUIDE.md) — configuration, providers, evidence, review,
  prioritization, knowledge, ASReview and reproducibility.
- [Ready-to-review offline demo and RIS exchange](docs/user/RIS_EXCHANGE.md)
- [Accepted CP10 alpha evaluation on macOS](docs/user/ALPHA_EVALUATION.md)
- [Offline tutorial](docs/user/TUTORIAL.md)
- [Development checkpoint downloads](docs/developer/DEVELOPMENT_BUILDS.md)
- [Developer browser and visual acceptance](docs/developer/BROWSER_TESTING.md)
- [Updating, removal and storage ownership](docs/user/REMOVAL_STORAGE.md)
- [Privacy and security](docs/user/PRIVACY_SECURITY.md)
- [Limitations and troubleshooting](docs/user/LIMITATIONS.md)
- [Alpha API](docs/developer/API.md)
- [XML policy](docs/developer/XML_POLICY.md)
- [Contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md)
- [Release notes](CHANGELOG.md) and [release preparation](docs/developer/RELEASING.md)

## License

[MIT](LICENSE), without additional use or citation conditions.
[Code/fixture provenance and separate dependency notices](NOTICE.md).
Formal citation metadata can be added later; none is fabricated for this alpha.
