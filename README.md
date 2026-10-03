# CorpusTrail

CorpusTrail is an open-source tool for building, curating, maintaining and
organizing broad scientific literature corpora with strong provenance.

```text
discover → canonicalize → acquire evidence → curate → prioritize
         → organize knowledge → export to ASReview
```

CorpusTrail asks **“Does this paper belong in my broad scientific topic corpus?”**
ASReview screens **“Does this paper satisfy the criteria for this particular review?”**
Broad-corpus membership is not systematic-review eligibility.

This is **0.1.0a2**, an early research alpha. APIs and schemas may change before 1.0.
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

## Boundaries

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
- [Offline tutorial](docs/user/TUTORIAL.md)
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
