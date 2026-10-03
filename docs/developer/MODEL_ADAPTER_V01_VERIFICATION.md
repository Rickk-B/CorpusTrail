# External Model Adapter v0.1 — reference endpoint verification

Date: 2026-10-03. Branch: `development/external-model-adapter-v0`.
Version remains unreleased `0.1.0a2.dev0`. No remote push, new release or package
publication was performed. No commercial, institutional or actual local model
was invoked. The HTTP tests use an invented loopback server only.

## Core checkpoint first

The verified generic v0 core was committed before reference-adapter work:

- Commit: `7377a681d20ba94566b7f117f42fd4c9e3edf6b4`.
- Annotated tag: `checkpoint-external-model-adapter-v0-core-20261003`.
- Author/committer: neutral CorpusTrail project identity.

The published `v0.1.0a1` target remains
`e756744f57589ec1a103cf84e746bc7b05ff3713`. The frozen alpha manifest,
core-v0 verification document and migrations 001–036 remain byte-identical.
The v0.1 implementation is a subsequent uncommitted development diff, not part
of that core checkpoint or a published release.

## Implementation and safety boundaries

- Optional stdlib-only `models.integrations.compatible_endpoint` implements
  non-streaming chat/completions. No hosted endpoint/model, SDK or shared key.
- Generic config-bound adapter factories avoid sharing local/remote or endpoint
  configuration across workflows. Task specifications remain provider-independent.
- `models configure` appends non-secret project configuration; status is local-only.
  Credentials are user-owned environment values, passed only as transient headers.
- Local declaration requires a literal loopback address. Non-loopback endpoints
  require HTTPS. Redirects and environment proxies are disabled. A loopback cloud
  relay must be declared remote; server internals cannot be verified by CorpusTrail.
- Explicit synthetic connection testing never reads papers, uses scientific task
  settings, creates assertions or grants scientific-transfer consent.
- Scientific remote invocations retain exact-plan approval, evidence selection,
  schema/quote validation and immutable non-authoritative Knowledge Layer writes.
- No retries, fallback, tool execution, automatic extraction, stopping rule,
  scientific authority change or MCP implementation.

Additive migration 037 introduces append-only `ct_model_connection_events` with
request reservations, config/request hashes, timestamped sanitized responses,
reported/observed models, usage and failures. Existing projects require an
explicit backup-backed upgrade; no implicit migration occurs on reads.
`ModelConfig.adapter_configuration` and response `diagnostics` are additive
experimental fields. Previously frozen artifacts are not rewritten; stale plans
must be inspected/replanned explicitly under a new run ID, never silently changed.

## Acceptance

| Surface | Result |
|---|---|
| Reference-adapter loopback tests | 21 passed |
| Complete source suite before final four additional endpoint cases | 300 passed |
| Clean installed wheel, core only | 304 run; 258 passed, 46 expected ML skips |
| Clean installed wheel, optional ML | 304 passed |
| Actual sdist → wheel → clean core install | 304 run; 258 passed, 46 expected ML skips |
| Actual sdist → wheel → clean optional-ML install | 304 passed |
| Installed model config/status/help outside checkout | Passed, no network |
| Offline tutorial, installed CLI, reinstall/reopen, coupling/isolation | Passed |
| Ruff correctness gate and diff whitespace check | Passed |
| Owner-identity/credential-pattern source scan | No blocking findings |
| Core checkpoint, old migrations, alpha tag/manifest | Unchanged |

The final Python/SQL source snapshot (canonical UTF-8 JSON mapping of paths to
contents) is:

`sha256:87ef54fdca44b248ea6a0bb64107074923445969046b69d459394a2c5f74a114`

Verification wheel hash (temporary, not published):

`sha256:07438ae502e018e940c843a4d61dffb74c5362842754d49c9cd9f1a74dc84528`

The 21 endpoint tests cover success, user env-key header construction, no secret
persistence/status exposure, absent credentials, explicit locality/TLS rules,
remote evidence consent separate from synthetic approval, timeouts, malformed
and invalid structured output, HTTP 401/429/500, rejected redirects/proxies,
reported and exposed auxiliary models, idempotent completion replay, immutable
diagnostics, disallowed tools/truncation/multiple choices, and CLI workflow.
Core tests additionally cover evidence modes/trust, task isolation, conflicts,
unknown values and protected scientific-table preservation.

The source scan used 20 privately supplied owner-identity variants; none occurred.
One credential-URL-pattern match is an explicitly invented rejection-test fixture,
not an account/key. No private identity terms or real credentials were copied into
the repository. Built metadata retained MIT licensing with author, maintainer and
contact fields omitted. The base installation remains dependency-free.

## Limitations and recorded corrections

Initial loopback tests were blocked by the execution sandbox and rerun with local
socket permission. One diagnostic replay test exposed tuple/list JSON differences;
results now normalize to canonical JSON before persistence/return. All final
artifact-install suites passed after that correction.

Compatibility tests do not establish scientific extraction accuracy or prove
compatibility with every server. Only this small chat protocol is supported;
Responses-only servers, streaming, tools, automatic retry/proxy configuration and
arbitrary vendor settings are intentionally absent. Usage/model reporting depends
on what the server exposes; unreported internal model roles remain unknown.
Timeout is an HTTP/socket timeout, not a provider-level cancellation guarantee.
Provider error bodies/headers and arbitrary synthetic reply text are not retained.
Secret checks are not universal PII/opaque-secret detection; do not put secrets
in URLs, prompts, evidence or generation settings. Quote/schema checks are not
scientific truth validation, and no predicate is promoted to unattended extraction.

Testing used Python 3.12 and cached offline numerical/build dependencies.
The development branch/tag have not been pushed for hosted CI. Historical/private
research data and runtime were neither modified nor used by this task.

See the [user workflow](../user/MODELS.md) and [generic API/MCP boundary](MODEL_ADAPTERS.md).
