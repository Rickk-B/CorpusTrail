# External Model Adapter v0.1 — bounded interoperability validation

Date: 2026-10-03. Version: unreleased `0.1.0a2.dev0`.
Branch: `development/external-model-adapter-v0`.

## Freeze before validation

- Implementation commit: `5c5c634d4298e4a463616282bd28ce05a0f08559`.
- Annotated checkpoint: `checkpoint-external-model-adapter-v01-20261003`.
- Neutral repository-local author/committer identity; no global identity change.
- Prior [offline verification report](MODEL_ADAPTER_V01_VERIFICATION.md) preserved
  byte-identically, including its original test results and source/build hashes.
- Published `v0.1.0a1` remains at
  `e756744f57589ec1a103cf84e746bc7b05ff3713`; no retag, release or push.

The commit/tag were reported before endpoint discovery or interoperability work.
Runtime source, dependencies, migrations and model protocol remain identical to
the checkpoint. Follow-up changes are one CLI acceptance test, user-guide
clarifications and this report. No generic compatibility fix was needed/applied.

## Real endpoint availability: no usable endpoint identified

Bounded, read-only checks found:

- No non-secret endpoint hints in the five checked conventional base-URL variables.
- No `corpustrail.project.json` model configuration in the standalone checkout.
- No detected `ollama`, `lms`, `llama-server` or `vllm` command on PATH.
- Five existing loopback TCP listeners received one credential-free
  `GET /v1/models` catalog probe each. Two returned HTTP 401, one HTTP 403, and
  two returned no identifiable compatible model catalog. No valid model list
  or model identifiers were exposed. Redirects/proxies were disabled; response
  size and timeout were bounded. No response bodies were logged.

An access denial does **not** identify a listener as a model server. Other
locations, custom API base paths and authenticated services were not searched.
This is not proof that no model server exists anywhere on the machine.
No secrets files, credential values or remote account credentials were searched.
No real endpoint was configured, authenticated or POSTed to. No local runtime
was installed or launched; no external catalog/provider request was made.

The real-endpoint portion stopped cleanly. **Real model invocations: 0. Paid
model usage: 0.** A future real test needs an explicitly identified, already
available endpoint and user-supplied configuration. None was inferred from
unrelated discovery accounts or development-tool access.

## User workflow acceptance: offline mock only

An additional acceptance test exercises the existing CLI against a loopback mock,
once with explicit local declaration and once with conservative remote declaration:

1. `models configure`: user-selected endpoint/model and credential ENV NAME.
2. `models status`: configured model, local/remote, credential presence/requirement,
   adapter availability and disabled external scientific transfer.
3. Explicit synthetic `models test-connection`; separate synthetic confirmation
   for remote declaration. No scientific assertions or scientific consent.
4. `candidates`: obtain the canonical ID of an invented software-fixture record.
5. `models plan`: a user-supplied versioned JSON task, existing `ct.report_role`
   predicate, exact dummy metadata/abstract and a no-clobber plan file/hash.
6. Remote invocation without consent fails before another HTTP request.
7. `models authorize`: approve the exact inspected plan/hash; then explicit
   `models execute` succeeds. Local invocation needs no external consent.
8. `models inspect` and `knowledge show`: complete provenance, evidence-linked
   immutable assertions with producer=model and non-authoritative authority.

Each declared mode sends one connection request and one task request to the mock
only. The evidence is precisely `Dummy software fixture` and
`TEST_ONLY. This record is a software fixture.` No real paper, scientific labels,
research corpus, model relevance judgments or evaluation truth is used.
The existing predicate is not extended or promoted. No model accuracy is measured.

No custom Python adapter or manual database editing is required in the user-facing
workflow. Automated fixture setup creates the invented record through the public
identity service. Users must still provide a JSON task, select available evidence,
copy printed IDs/hashes and inspect the plan file before authorization. These are
explicit provenance steps, not hidden database requirements.

## Contract observations and limits

| Contract area | Offline result | Real endpoint result |
|---|---|---|
| API style/path | Non-streaming POST base + `/chat/completions` passed | Not tested |
| Structured JSON | Claims validated; malformed/extra fields rejected | Not tested |
| Model identifiers | Configured/reported IDs and exposed auxiliaries preserved | No catalog exposed; no invocation |
| Usage metadata | Mock token fields preserved; unknown internal roles remain ambiguous | Not tested |
| Timeout/error behavior | Timeouts, HTTP 401/429/500, malformed replies and redirects tested | Catalog denials only; server contract unknown |
| Locality and consent | Explicit local loopback policy; remote exact-plan gate passed | No model locality established |
| Knowledge authority | Model outputs stayed non-authoritative; scientific tables unchanged | Not tested |

Validated offline: generic model-adapter architecture; configuration → status →
connection-test → explicit-task workflow; local/remote declaration; external-transfer
consent enforcement; credential non-persistence; Knowledge Layer integration;
immutable non-authoritative assertions; wheel/sdist installation and mock-server
compatibility. These are infrastructure/contract checks, not scientific validation.

Not yet validated: interoperability with **any real OpenAI-compatible model server**,
any specific hosted provider, or named runtimes such as Ollama, LM Studio and vLLM.
No real-server deviations can be assessed without a real invocation. There were
no vendor-specific workarounds, alternate protocols, default-model selection,
retry/fallback changes, new providers, MCP, bulk extraction or prioritization work.

## Credentials, transfer and status UX

User-owned credentials are passed transiently to the selected endpoint only.
Tests verify header construction and absence from project files, status, stderr,
diagnostic/scientific provenance and output artifacts. Only fake test credentials
are used. Connection-test approval never authorizes paper-content transfer.
The exact scientific plan records the evidence fields/modes/hashes and provider,
endpoint/model identity before remote authorization.

Local declaration means `data_leaves_machine=false` only with explicit local
configuration and literal loopback routing. CorpusTrail cannot prove a loopback
server does not proxy content elsewhere; such a proxy must be declared remote.
Non-loopback connections require TLS; no third-party privacy promises are made.

Model and discovery configuration/credentials remain distinct. The CLI acceptance
test confirms that configuring a model leaves discovery providers unconfigured and
does not enable `discover --provider crossref`. `models status` does not grant or
claim discovery-provider access. A unified discovery-and-model status dashboard
is not present and was not added in this validation phase.

`available` in model status means registered adapter, not a reachable server.
Credential `present` means environment variable set, not accepted authentication.
The guide now makes this distinction, supported installed/configured adapters,
user credentials, local/remote behavior, server compatibility variation, consent
and non-authority explicit. A successful synthetic connection test alone does
not validate scientific structured output.

## Verification

Focused results: 30 generic model-adapter tests and 22 endpoint/CLI-workflow tests
passed. Ruff correctness checks and diff whitespace checks passed. Runtime code
and the frozen v0.1 verification report are byte-identical to the checkpoint.

| Final acceptance surface | Result |
|---|---|
| Clean wheel, core only | 305 run; 259 passed, 46 expected ML skips |
| Clean wheel, optional ML | 305 passed |
| Actual sdist → wheel → clean core install | 305 run; 259 passed, 46 expected ML skips |
| Actual sdist → wheel → clean optional-ML install | 305 passed |
| Installed CLI/config/status/help and offline tutorial | Passed outside checkout |
| Sdist uninstall/reinstall and deterministic project reopen | Passed in core and ML environments |
| Coupling/isolation and required package/provenance resources | Passed |
| Ruff and diff whitespace checks | Passed |
| Known-owner identity, credential-pattern and documentation-link scan | No blocking findings |

Testing used Python 3.12 and cached offline build/numerical packages. No live
provider/model request is required by CI. The invented tutorial retained
9 raw observations, 8 canonical papers, 1 pending document and exact-ID mappings
of 3 records for each of two downstream questions; membership remained unchanged.
Core wheel metadata has no author/maintainer/contact fields and introduces no
required model, ML or ASReview dependency. Hosted CI was not triggered/pushed.

Acceptance-build hashes (temporary, not published; final report/status wording
are documentation-only follow-ups):

- Wheel: `sha256:aded2a54b0dbd28e08af79b72a9060dc082c7a858785a2f000afe4935cdc4b20`.
- Sdist: `sha256:f1b90280f44bd12e32907bbed20c3742317583fa01c92d073211f9d0b4e18eff`.

The privacy scan uses 20 locally supplied owner-identity variants without copying
them into product artifacts. Its only credential-URL match is an invented
negative-test fixture; no owner identity or real credential finding was detected.
The historical/private research repository, authority, datasets and runtime were
not modified. The reviewed follow-up test/docs/report are preserved in the separate
`checkpoint-external-model-adapter-v01-offline-validation-20261003` checkpoint;
the original v0.1 implementation checkpoint remains unchanged. No runtime changes,
merge to main, push or release are part of this follow-up.

Follow-up checkpoint acceptance: the complete standalone core suite was rerun
(305 tests, 46 expected optional-ML skips), and Ruff/diff-whitespace checks passed.
The sandbox initially blocked local HTTP socket binding; rerunning with permission
for loopback fixture servers passed, without real provider calls. A targeted scan
of all three follow-up files found no owner-identity/contact/private-path findings;
the existing fake credential-URL rejection fixture was reviewed and retained.
The earlier wheel/sdist/core/ML results above are preserved, not claimed as newly
rerun builds for this documentation-only checkpoint follow-up.

## Bounded future interoperability checklist

This is an optional, explicitly initiated manual acceptance check, **not a CI
requirement**. No model/runtime installation, new adapter, architecture change or
bulk extraction is required. Stop on unsupported behavior and record the failure;
do not add vendor-specific workarounds merely to pass.

1. Select **one** already available real local compatible endpoint, or one
   user-authorized remote compatible endpoint. Record adapter/version, API base/path,
   configured model and local/remote declaration without credentials. Use a temporary
   synthetic project. Declare local only for on-device inference, not a cloud proxy.
2. Configure through the existing CLI; inspect `models status`. Supply any required
   credential only through the configured environment-variable mechanism. Do not
   search for credentials or print their values.
3. Run one `models test-connection` with its fixed non-scientific payload; explicitly
   confirm that synthetic transfer if remote. Inspect `models connection-history`
   for success/failure, returned model identity and usage when exposed. Connection
   consent does not authorize the structured task.
4. Create one invented software-fixture record and versioned task using an existing
   predicate. Run `models plan` for synthetic metadata/abstract only; inspect the
   exact payload and input hashes. Never include real paper text, reference answers
   or human labels. For remote execution, verify missing consent blocks transmission,
   then explicitly authorize the exact plan/hash with `models authorize`.
5. Execute **one** structured task with `models execute`. Check the recorded status
   and schema validation rather than assuming CLI exit alone means success. Inspect
   `models inspect` and `knowledge show`: producer=model, non-authoritative,
   evidence-linked assertions, actual reported model/usage where available and run
   provenance. Verify corpus membership/review authority are unchanged.
6. Verify the configured credential is absent from status, project files, output and
   provenance without exposing it in the report. Record JSON/model/usage contract
   deviations, exact endpoint tested and limitations. One successful task is enough;
   failures do not justify paid retries or additional endpoints automatically.

Only that recorded endpoint/workflow would become real-server-tested. Such a result
would not validate other servers, scientific accuracy or unattended extraction.
Feature development is paused pending a real compatible endpoint or external alpha
feedback; the optional checklist can run without changing scientific architecture.

## Readiness decision

The mock-validated reference adapter is suitable for **opt-in, experimental alpha
use with per-endpoint synthetic connection and structured-task checks**. It is
not yet real-server-validated on this machine; do not claim general compatibility
or scientific extraction reliability. Real-endpoint interoperability remains an
unexecuted validation step, not a reason to fabricate a successful test or install
a model automatically. Ordinary users can configure the supported protocol and
run the explicit CLI workflow without writing an adapter.

Remaining limitations: small chat-only contract; no streaming, tools, Responses-only
support or automatic retries; server-dependent JSON/model/usage behavior; manual
task JSON/plan inspection; no unified discovery status; semantic correctness still
requires independent validation. Structured-output failures may be recorded in
JSON while the CLI returns normally, so automation must inspect the result status.
No output becomes authoritative automatically. No unattended scientific extraction
or new alpha release is approved by these results.

Initial acceptance testing caught a test-only false positive: the word `review`
appeared in the registry definition “not review eligibility.” The check was replaced
with an explicit allowed-request-field and exact-synthetic-evidence check; no
prompt, model implementation or scientific reference was changed.
