# External Model Adapter v0.1 (experimental)

This infrastructure is included in `0.1.0a2`; it does not modify or retag the
published `v0.1.0a1` release. It has no model SDK or runtime dependency and no
default provider/model. No live model was called to implement or test it.
It is not scientific validation of extraction accuracy or a production extractor.
Real OpenAI-compatible server/provider interoperability has not yet been validated;
see the [offline validation report](MODEL_ADAPTER_V01_INTEROPERABILITY.md).

## Architecture and authority

Stable CorpusTrail contracts are canonical identity, evidence, review state,
prioritization interfaces, Knowledge Layer assertions, lineage and explicit
validation/authority. Provider, model, algorithm, task instructions and settings
are replaceable implementations. A commercial, institutional, compatible-endpoint
or local implementation uses the same `ModelAdapter` contract. No particular
provider is endorsed or required. A project without `models` works normally.

`TaskSpec` is provider-independent: ID/version, instructions, scoped predicates,
allowed evidence modes and a bounded versioned output contract. Its hash binds
the exact specification. Each plan separately freezes adapter/provider version,
configured model/settings, software version, registry definitions and the exact
evidence. Changing any of these requires a new plan and run ID.

Outputs enter the existing KnowledgeStore plan/apply machinery as immutable
`producer_type=model`, `unvalidated`, `non_authoritative` assertions. The caller,
not the response, fixes subject, producer, timestamp, evidence and run lineage.
There is no membership, review-authority, identity, trust, prioritization or
ASReview writer in this service. Only later explicit human validation/authority
events may establish knowledge authority; the original producer remains model.

## Configuration and user credentials

For a ready-to-configure reference protocol, see [use your own model](../user/MODELS.md).
The optional `models.integrations.compatible_endpoint` module implements a small
OpenAI-compatible chat/completions contract without a vendor SDK. It is selected
only by explicit configuration, not a provider default. No commercial call is
made by installation, configuration, status or project opening.

Configure optional workflows through `ProjectConfig.models` or existing
`project configure` (full configuration, next version, expected config event ID):

```json
{"models": [{"workflow_id": "extraction", "adapter": "institution-model",
             "model": "institution-model-version", "endpoint_id": "institution-endpoint",
             "credential_env": "CORPUSTRAIL_MODEL_KEY",
             "settings": {"temperature": 0, "max_output_tokens": 1000}}]}
```

This is a fragment, not a complete project configuration. `endpoint_id` is an
opaque non-secret identifier; the trusted adapter resolves endpoint routing.
It is not an arbitrary model-selected URL. Omit `credential_env` for an
uncredentialed local implementation. Users supply their own accounts/credentials
through environment variables in v0. CorpusTrail supplies no shared API access
and ships no API keys; no bespoke secret manager is introduced.
Do not commit credentials or put them in prompts, settings or evidence.

Configuration rejects credential-like keys/signatures and active configured
environment secret values. Runtime inputs/outputs/provenance are checked against
configured discovery and model secrets. Only the chosen workflow credential is
passed separately to its adapter, never in the recorded request. Exception
messages, provider headers and credential-bearing responses are not persisted.
These safeguards are not a general PII/opaque-secret detector. Arbitrary secrets
disguised as scientific text cannot be recognized universally; users and trusted
adapters remain responsible for their data. Do not log credentials inside adapters.

## Local versus remote and exact-plan consent

An adapter declares `data_leaves_machine`. A genuinely offline local implementation
declares false and needs no external-transfer consent. A hosted/proxy implementation
declares true. Locality is a trusted-code contract, not an operating-system network
sandbox: an adapter calling a remote service cannot honestly declare itself local.

Planning is read-only and shows provider, configured model, locality, evidence
mode and the notice that third-party privacy/retention terms apply. Core makes no
third-party retention/training/privacy promises. A remote call fails before any
invocation unless a human explicitly authorizes that exact plan hash. Consent is
scoped to a run/request, stricter than a blanket workflow opt-in. It cannot be
reused after changing model, settings, task, registry or evidence. Authorization
records a stable/pseudonymous actor; it is not identity authentication.

`metadata` transmits selected bibliographic fields only. `abstract` adds the
available abstract. `selected_passages` adds only explicit character ranges from
an explicitly chosen verified structured document body. `full_text` adds that
whole verified body. No mode automatically reads unrelated files, historical
judgments, reviewer labels, model observations, discovery methods or ranks.
Full document support is currently limited to verified structured text; pending
PDFs, unverified OCR and mismatched documents are rejected. No automatic evidence
fallback occurs: missing abstracts require explicitly selecting metadata mode.

## Python API and custom adapters

These APIs are experimental. Installed adapters are trusted executable code,
not untrusted model responses. Install only extensions you trust. Import and
construction must be side-effect free; networking belongs exclusively in `invoke`.

```python
from corpustrail.models import (
    AdapterInfo, AdapterRegistry, ModelResponse, ModelService, TaskSpec,
)

class InstitutionAdapter:
    info = AdapterInfo("institution-model", "institution", "adapter-v1",
                       data_leaves_machine=True, credentials_required=True)

    def __init__(self, client):
        self.client = client  # user-selected implementation, not a core SDK

    def invoke(self, request, *, credential):
        # request is JSON-only. It contains the frozen task, settings, allowed
        # predicate definitions and supplied evidence, not a Project or file paths.
        result = self.client.extract(request, credential=credential)
        return ModelResponse(
            output=result["output"], reported_model=result.get("model"),
            observed_models=tuple(result.get("observed_models", ())),
            model_usage_ambiguity=result.get("model_usage_ambiguity", True),
            response_id=result.get("response_id"), usage=result.get("usage", {}),
            reported_model_version=result.get("model_version"),
        )

registry = AdapterRegistry([InstitutionAdapter(user_client)])
service = ModelService(project, registry=registry)
spec = TaskSpec("organisms", "v1", "Extract only explicit organisms; abstain otherwise.",
                ("ct.organism_population",))
plan = service.plan("extraction", spec, run_id="extract-001", paper_id=paper_id)
print(plan)  # inspect provider/model, notice and evidence before approval
consent = service.authorize(plan, actor_id="project_reviewer_01", confirm_external=True)
result = service.execute(plan, consent_event_id=consent)
```

`user_client`, `project`, `paper_id` are application-supplied objects/identifiers,
not bundled credentials or a preconfigured scientific extractor. A local adapter
implements the same method with `data_leaves_machine=False`; omit authorization.
`FixtureAdapter` is an offline deterministic test reference, not a real model.

For CLI discovery, an optional independently installed distribution may declare:

```toml
[project.entry-points."corpustrail.model_adapters"]
institution-model = "my_adapter:factory"
```

The no-argument factory must return an adapter with the matching identifier.
Status lists entry points without loading them; only explicitly selected adapters
are loaded at planning/execution. Duplicate registrations fail closed. No SDK is
installed automatically. The built-in compatible endpoint is a protocol adapter,
not a configured commercial account/client.

`AdapterRegistry.register_factory(adapter_id, factory)` additionally supports
config-bound integrations: `factory(ModelConfig)` returns a fresh adapter for
the selected workflow. `resolve(adapter_id, configuration=config)` binds model,
endpoint/locality/settings without sharing mutable endpoint state across workflows.
`ModelConfig.adapter_configuration` is non-secret provider-neutral JSON; each
integration validates its own options. The Knowledge Layer schema does not encode
any endpoint protocol. Status may construct the trusted built-in config factory
but never makes network calls or loads installed third-party entry points.

## CLI (explicit, no background extraction)

```bash
corpustrail models status /path/to/project
corpustrail models plan /path/to/project --workflow extraction --spec task.json \
  --run-id extract-001 --paper-id CANONICAL_ID --mode abstract --out plans/extract-001.json
corpustrail models authorize /path/to/project --plan plans/extract-001.json \
  --actor project_reviewer_01 --expected-plan-sha256 SHA256_FROM_PLAN --confirm-external
corpustrail models execute /path/to/project --plan plans/extract-001.json \
  --consent-event-id CONSENT_EVENT_ID --execute
corpustrail models inspect /path/to/project --run-id extract-001
```

Plan paths are explicit/project-confined and no-clobber. The input TaskSpec JSON
contains `task_id`, `version`, `instructions`, `predicates`, and optional
`evidence_modes`/`max_claims`; the schema is `structured_assertions/v1`.
Local execution omits `authorize` and `--consent-event-id`. Status never performs
provider calls or prints secret values. An installed-but-unloaded adapter's
locality/credential policy remains unknown rather than inferred from its name.

## Structured response and evidence validation

```json
{"claims": [{"predicate": "ct.organism_population", "raw_value": "human",
  "value_datatype": "string", "evidence_id": "SUPPLIED_EVIDENCE_ID",
  "quote": "EXACT QUOTE FROM THAT INPUT"}]}
```

Positive claims require a supplied evidence ID and an exact supporting substring.
Unknown claims use null value/evidence/quote and datatype `unknown`. Multiple
claims and empty/unknown output are allowed. Vocabulary/type checks use the
existing Knowledge Layer. Core supplies evidence linkage and passage offsets;
models cannot supply arbitrary locators, file paths, producer or authority fields.
Extra fields/tool calls fail validation. Quoted support is syntactic evidence
linking, NOT proof that the model interpreted the passage correctly. Human
confirmation or separate predicate-specific validation remains necessary.

Responses are treated as JSON data: never evaluated, executed, followed as URLs
or used to choose files/credentials. Safe response envelopes, including malformed
scientific outputs, are preserved content-addressed for auditing. Sensitive or
oversized responses are not retained; the failure category is preserved instead.
Inputs and outputs are capped at 2 MiB; claims at 128 maximum. No automatic retry,
provider fallback, bulk extraction or unattended task is implemented.

## Provenance, replay and migration

Additive migration 036 creates immutable `ct_model_events`: consent, reservation,
response, KnowledgeStore plan and completion. Existing migrations/tables are
unchanged. New projects initialize it; existing alpha projects must explicitly
run `corpustrail project upgrade PROJECT --backup data/backups/pre36.sqlite3`.
Migration 037 adds an independent append-only `ct_model_connection_events` ledger
for explicit synthetic-only diagnostics. It has no paper/evidence reference and
does not create scientific assertions. Alpha/core-v0 projects require an explicit
backup-backed upgrade to the current schema; migrations 001–036 are unchanged.
The upgrade preserves bootstrap and existing observations and does not configure
a model. Status/open never implicitly migrate.

Each run preserves frozen task/version/hash, request hash, evidence IDs/hashes,
registry/configuration snapshot, configured and observed models, optional reported
model version, adapter/provider version, timestamps, local/remote declaration,
usage/per-model metadata, failure and assertion IDs. Exposed auxiliary models are
retained without inferring their roles. Unknown model use stays explicitly ambiguous.
An adapter must report all available model-use information rather than claiming
single-model performance from a composite workflow.

Run reservations serialize competing requests and never overwrite history.
Exact completed replay returns the prior result without another model call or
duplicate assertions. Independent runs remain independent observations. Interrupted
runs with a preserved response can explicitly use `models resume`; this is local
recovery, not retransmission. A reservation without a response requires inspection
and a new explicitly authorized run ID. Crashes after assertion commit are recovered
idempotently. Raw artifact integrity and event hashes are checked on reads/recovery.

## MCP boundary (future design only)

An external model adapter lets CorpusTrail call a user-selected model. MCP would
let another application call a restricted set of CorpusTrail tools. They are
different directions and neither requires the other. No standalone MCP server is
implemented or advertised here. A future server should expose read-only knowledge
tools first, use explicit authentication/scopes and exact approval for writes or
external transfer, and return data rather than scientific authority. An MCP
connection must never grant access to user discovery/model credentials. Provider
accounts and transfer authorization remain separately configured by the user.
