# External Model Adapter v0 verification

Date: 2026-10-03. Local development branch: `development/external-model-adapter-v0`.
Version: `0.1.0a2.dev0` (unreleased). No branch push, new release or PyPI upload
was performed. The published `v0.1.0a1` tag still targets
`e756744f57589ec1a103cf84e746bc7b05ff3713`.

## Scope and implementation

- Provider-neutral adapter/capability contracts and explicit registry/optional
  installed entry points; no required SDK, runtime model dependency or vendor default.
- Versioned, hash-bound tasks separate from model/provider configuration.
- User-owned environment credentials; rejected secret fields, known configured
  secret values and sensitive response/exception material.
- Read-only plan/status; explicit exact-plan consent for remote evidence calls.
- Declared local execution without external-transfer consent. Installed adapters
  are trusted code, not a network sandbox; status does not load plugins.
- Explicit invocation, preserved response/failure/usage/model provenance and
  transactional non-authoritative KnowledgeStore assertions.
- No retries, provider fallback, bulk extraction, relevance writer, stopping rule
  or MCP server. MCP boundary/future design is documented separately.

Documentation: [contracts, custom adapters, CLI, consent, provenance and MCP](MODEL_ADAPTERS.md).

Migration 036 adds `ct_model_events`. Existing discovery ledger types and all
migrations 001–035 remain byte-identical. Upgrades are explicit and backup-backed;
the published configuration shape without `models` was tested. Existing bootstrap,
canonical observations and normalized knowledge views remain unchanged after upgrade.
The frozen alpha release manifest is also byte-identical; it is an archived alpha
snapshot, not a manifest of this development branch.

## Verification results

| Surface | Result |
|---|---|
| Focused model-adapter tests | 30 passed |
| Clean installed wheel, core | 283 run; 237 passed, 46 optional-ML skips |
| Clean installed wheel, ML extra | 283 passed |
| Actual sdist → wheel → clean core install | 283 run; 237 passed, 46 optional-ML skips |
| Actual sdist → wheel → clean ML install | 283 passed |
| Installed CLI, tutorial, uninstall/reinstall and deterministic reopen | Passed |
| Ruff configured correctness checks | Passed |
| `git diff --check` | Passed |
| Changed user/developer documentation links | 17 relative links resolved |
| Owner-identity/credential-pattern scan | No blocking findings |
| Published tag, old migrations, frozen alpha manifest | Unchanged |

Tests include registration/lazy plugins, no-model operation, local/remote consent,
secret/config/status protection, request/model/spec provenance, auxiliary model
observations, immutable/non-authoritative assertions, unknown values, malformed
outputs, exact evidence references, pending-PDF rejection, explicit metadata choice,
verified full text/selected passages, conflicts, independent supporting runs,
immutable event history, exact replay, provider failures and interrupted-run
recovery without model retransmission. Protected identity, review/screening,
prioritization, discovery/evidence and ASReview tables were compared unchanged
around model assertion writes.

The installed offline tutorial retained 9 observations, 8 canonical papers,
1 pending document and exact-ID downstream mappings of 3 records for each of two
questions. Membership stayed unchanged. These are invented software fixtures,
not human scientific validation or model-performance results.

Final tested Python/SQL source snapshot, canonical JSON mapping of relative file
paths to UTF-8 content:

`sha256:b18962fe676518b52e60f476f46839911ee93c13d506d4e0760921ce6ec0cbfe`

Verification-build hashes (temporary artifacts, not published distributions):

- Wheel: `sha256:f75145b9517431f131354e6ead2b21958e5524bf5a0476f386f36c8775cd13ed`.
- Sdist: `sha256:e439870c67325916bb2536fcfaead020f8dc1115cc4c353e45281d3783583b7f`.

## Limitations and transparent corrections

Initial integration testing showed that the discovery/evidence ledger deliberately
rejects model event types. A separate additive model ledger was introduced rather
than changing that schema or weakening its policy. Two old schema-count assertions
were updated to reflect/test the additive migration. A sandbox-only localhost
socket failure was rerun with local-server permission. Final artifact tests passed.

Verification used local Python 3.12 and offline public software wheel caches; the
new branch has not been pushed for hosted Python 3.11/3.13 CI. No actual commercial,
institutional or local inference model was invoked. Remote-consent tests use
offline mocks. A real model requires an explicitly installed/registered custom
adapter and its own user credentials/configuration.

Quote/type validation establishes structural/evidence-link integrity, not factual
accuracy. No predicate is approved for unattended scientific extraction. Locality
depends on the truthful adapter declaration. Secret guards are not universal PII
or opaque-secret detection; trusted adapters must not log or expose credentials.
Interrupted invocations without a preserved response cannot be safely retried
implicitly. None of these limitations changes scientific authority.

Historical/private research runtime, frozen scientific datasets and model
observations were not accessed or modified. No actual human review or model
scientific extraction was performed. The result is infrastructure only.
