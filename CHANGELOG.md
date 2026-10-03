# Release notes

## 0.1.0a2 — experimental model adapters (2026-10-03)

**Real OpenAI-compatible model-server interoperability has not yet been validated
by the CorpusTrail project. The adapter has been validated through offline/mock-server
testing. Users should use the connection test and treat this feature as experimental.**
OpenAI hosted API, Ollama, LM Studio, vLLM and other named real providers/runtimes
have not been tested. No real model calls or scientific accuracy claim underpin
this release.

### Added: Experimental External Model Adapter support

- Generic provider-neutral model interface; no model/provider is required or endorsed.
- User-configurable OpenAI-compatible non-streaming chat/completions reference
  adapter, with explicit local/remote declarations and synthetic connection tests.
- User-owned credentials through environment variables; CorpusTrail supplies no
  shared keys or accounts. Model and discovery-provider credentials remain separate.
- Explicit versioned tasks and frozen evidence plans; remote evidence transfer
  requires exact-plan authorization. Local on-device execution needs no external
  transfer consent. Model setup never starts scientific extraction automatically.
- Structured-output validation, failure handling and immutable model/run provenance;
  evidence-linked Knowledge Layer assertions remain non-authoritative.

### Validated scope

Offline/mock tests cover architecture, endpoint contract, configuration/status,
local/remote handling, environment credentials and their non-persistence,
remote-transfer consent, synthetic connection testing, explicit task execution,
structured-output validation, provenance, non-authoritative writes and failures.
Clean wheel/sdist installations, core/optional-ML tests and offline workflows pass.
These results do not establish real-provider interoperability or scientific validity.

### Boundaries and limitations

CorpusTrail remains a broad scientific corpus-construction tool; ASReview remains
downstream question-specific screening. Prioritization changes review order only;
no automatic exclusion/stopping rule is provided. Model output cannot establish
corpus membership or human authority. Unattended LLM scientific extraction is not
a production feature. MCP is separate, not implemented and not required.
The reference wire contract is small: no streaming, tools, Responses-only endpoints,
automatic retries or vendor-specific extensions. Full interactive ASReview browser
use remains unvalidated; temporary ASReview 2.2 import/exact-ID mapping is tested.

This is an early research alpha; APIs, plugin contracts and schema expectations
may change before 1.0. GitHub is the distribution channel; no PyPI upload is made.
The `v0.1.0a1` tag and release remain unchanged.

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
