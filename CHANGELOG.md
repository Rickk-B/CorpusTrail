# Release notes

## 0.1.0a1 — initial alpha candidate

Locally prepared on 2026-10-02; not yet published or uploaded to a package index.
Licensed under the standard MIT License. No citation or non-commercial condition.
Public attribution is project-level only; package author/contact fields are omitted.
Release preparation checks the staged tree and distributions for personal metadata.

### Supported workflow

- Explicit project configuration and safe initialization/upgrades.
- Replaceable discovery interfaces with OpenAlex, Crossref, Europe PMC and
  Semantic Scholar keyword adapters; preserved requests, failures and observations.
- Exact canonical identities, aliases, deduplication and metadata provenance.
- Evidence acquisition/trust states, Europe PMC structured evidence and safe XML parsing.
- Local human broad-corpus curation, immutable decision history, method-blind mode
  and resumable review sessions.
- Optional project-trained TF-IDF/logistic prioritization with immutable training
  and ranking snapshots; ordering only, with all candidates accessible.
- Scoped Knowledge Layer observations/assertions, evidence, validation, conflicts
  and lineage; producer does not establish scientific authority.
- Unlabelled bibliographic ASReview export and exact-ID downstream result mapping.
- Credential-free, installed offline tutorial with invented scientific records.

### Scientific boundaries

CorpusTrail constructs a broad topic corpus; ASReview applies question-specific
systematic/scoping-review eligibility. Their labels are not interchangeable.
No automatic stopping, silent low-score exclusion, production unattended LLM
extraction or automatic downstream seed generation is provided. The architecture
is provider/model-agnostic; no model is promoted as a permanent default.

### Alpha limits

Linux/Python 3.11–3.13 is the tested matrix. Core requires no runtime dependencies;
numerical prioritization is optional. ASReview need not be installed; optional
SDK interoperability was tested with 2.2, not every future version or the full
browser workflow. Built-in acquisition is not comprehensive PDF/OCR coverage.
Local review is not authenticated multi-user infrastructure. Interrupted operations
may retain partial reservations and require inspection/new IDs. Hashes are integrity
checks, not signatures. See the user limitations/security pages.

APIs, plugin contracts and schema expectations may change before 1.0. Changes will
be versioned/documented; preserve backups and immutable snapshots. No automatic
database downgrade is promised. No new extraction validation or scientific
performance claim is made by this release.
