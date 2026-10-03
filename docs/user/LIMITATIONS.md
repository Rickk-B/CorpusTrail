# Alpha limitations and troubleshooting

- No additional provider, advanced model, unattended LLM extractor, stopping rule,
  automatic ASReview seeds, remote collaboration or cloud deployment is included.
- Built-in discovery is keyword search; built-in acquisition is Europe PMC XML
  with verified PMCID. No complete PDF/OCR/paywall/full-text coverage guarantee.
- Missing configured credential: inspect provider/env name in the failure receipt,
  set the private variable and choose a new run ID. No credential is needed offline.
- Empty resolver/reviewer/provider config is intentionally inert. Configure it
  explicitly; editing bootstrap/history is not configuration management.
- For required IDs use candidates JSON, project configuration history and returned
  train/prepare/plan outputs. Keep IDs rather than matching titles or row positions.
- Insufficient evidence is separate from non-membership. Missing abstracts do not
  prevent metadata-based human decisions. Pending documents are not trusted.
- Interrupted discovery/acquisition/export may leave a partial reserved directory.
  Preserve/inspect it and use a new ID; no automatic repair/deletion. Multi-file
  publication is not a single crash-atomic transaction.
- Native XML accepts valid UTF-8/UTF-16/ASCII/Latin-1, refuses DTD/entities and
  bounds bytes/nodes/depth/text. Compressed XML and UTF-32 are unsupported.
  Large local JSON/CSV imports are trusted-local operations and not uniformly
  bounded; do not expose them as an untrusted remote endpoint.
- Optional ML needs both human binary classes and compatible recorded libraries.
  A low score never means excluded; no tested signal justifies automatic cessation.
- ASReview SDK 2.2 smoke is temporary import/writer/identity mapping, not full LAB
  browser testing or 3.x certification. Preserve original custom IDs/full population.
- Linux is the alpha target. Other OS behavior/hard links and later Python versions
  need verification before a support claim. No public service/index is provided.
- Experimental model adapters are offline/mock-tested, not yet tested against a
  real OpenAI-compatible server, OpenAI hosted API, Ollama, LM Studio, vLLM or
  another real provider/runtime. Connection tests and structured-task checks are
  necessary for a chosen endpoint; neither establishes scientific accuracy.
- Code/docs/invented fixtures use the MIT license. Version 0.1.0a2 is an alpha;
  APIs and schema expectations may change. No PyPI distribution is provided.
