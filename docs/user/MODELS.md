# Can I use my own LLM with CorpusTrail?

Yes, if your model is supported by an installed/configured adapter. Experimental
model adapters let you choose a local server, institutional
endpoint or hosted service. **You supply your own endpoint, account and credentials.**
CorpusTrail does not provide, proxy or share API access. It does not endorse or
require any particular model. All normal corpus workflows work without a model.
This experimental feature is included in `0.1.0a2`, not `0.1.0a1`.

You can configure your own model through CorpusTrail's model-adapter interface.
The first built-in reference adapter targets OpenAI-compatible endpoints.
Compatible endpoints can be local or remote. Real-server compatibility may vary
and should be checked using the built-in connection test before scientific use.

## Compatible endpoint

The first reference adapter supports **OpenAI-compatible, non-streaming
chat/completions**: an API base URL plus `/chat/completions`, JSON `model`/`messages`,
and a text completion at `choices[0].message.content`. This is a protocol, not a
requirement to use OpenAI. No SDK or optional model dependency is needed.
Responses-only endpoints, tool calling, streaming and arbitrary extension fields
are not supported by this first adapter. Compatibility varies between servers
implementing “OpenAI-compatible” APIs; use the connection test before scientific runs.
Passing that synthetic test does not itself prove structured-extraction compatibility
or scientific accuracy. Real-server validation depends on your chosen endpoint.
Wire shape was checked against the [official chat reference](https://developers.openai.com/api/reference/resources/chat).

## Validation status

Offline validation covers the generic adapter architecture, configuration → status
→ connection test → explicit task workflow, local/remote distinction, external-transfer
consent, credential non-persistence, Knowledge Layer integration and non-authoritative
assertions. Mock-server compatibility tests and clean wheel/sdist installations passed.

**No real compatible model server was tested.** Interoperability with a specific
hosted provider, Ollama, LM Studio, vLLM or any other real server is not yet validated.
The examples below are configuration examples, not claims of tested provider support.
See the [bounded future interoperability checklist](../developer/MODEL_ADAPTER_V01_INTEROPERABILITY.md#bounded-future-interoperability-checklist)
before using a real endpoint. It requires only a connection test and one structured
task using synthetic/non-scientific content, not corpus extraction or new architecture.

If opening an older project reports a schema mismatch, explicitly upgrade once
with a new backup path:

```bash
corpustrail project upgrade /path/to/project --backup data/backups/pre-model-v01.sqlite3
```

## Local example — no key required

Start your own compatible server separately. CorpusTrail does not install or
launch a model runtime. Substitute your server's actual model identifier:

```bash
corpustrail models configure /path/to/project --workflow extraction \
  --endpoint-id local-server --base-url http://127.0.0.1:8000/v1 \
  --model your-local-model --execution local --timeout 60 \
  --settings '{"temperature":0,"max_tokens":1000}' --created-by project_operator
corpustrail models status /path/to/project
corpustrail models test-connection /path/to/project --workflow extraction \
  --run-id connection-001 --execute
```

Local declaration requires a **literal loopback IP** (such as `127.0.0.1` or
`[::1]`), not merely a name like `localhost`, a LAN address or an arbitrary
hostname. CorpusTrail disables environment proxies and redirects for this adapter.
Declare local only if the server performs inference on-device and does not relay
content elsewhere. CorpusTrail cannot inspect your server's implementation: a
loopback cloud proxy must be declared `remote` and requires consent. These are
connection safeguards, not a network sandbox or a guarantee about server behavior.
Local endpoints that require authentication may also use `--credential-env`.

## Remote example — your own credentials

The following endpoint and model are placeholders, not a usable hosted account.
Privately set the `MY_MODEL_API_KEY` environment variable using your own account's
key; do not put its value in commands, JSON, project files or version control.

```bash
corpustrail models configure /path/to/project --workflow extraction \
  --endpoint-id institutional-service --base-url https://models.example.test/v1 \
  --model chosen-model-version --execution remote --credential-env MY_MODEL_API_KEY \
  --timeout 60 --settings '{"temperature":0,"max_tokens":1000}' \
  --created-by project_operator
corpustrail models status /path/to/project
corpustrail models test-connection /path/to/project --workflow extraction \
  --run-id connection-remote-001 --confirm-external --execute
```

Non-loopback addresses require HTTPS with normal certificate verification.
URLs must not contain credentials/userinfo, query parameters, fragments or path
traversal. The configuration stores the URL/provider identity, env-variable NAME,
execution declaration, timeout and generation settings, never the API key.
Use a shareable endpoint URL, not a secret or identifying private path.
Authentication sends a Bearer header only when you configured a credential variable;
an unset variable fails without a request. If the chosen service requires a key,
you must configure that variable. No credential is required by the protocol itself.

Status shows adapter, configured model, endpoint, local/remote, credential
present/missing/not configured, and **external evidence transfer disabled without
exact-plan authorization**. It never prints the key, invokes a model or grants
consent. `available` means the adapter is registered, not that a server/model is
reachable. Credential `present` means the named environment variable is set,
not that the server has accepted it; use an explicit connection test to check.
Changing configuration appends a versioned project event and invalidates
older unexecuted scientific plans. No background connection tests occur.

## Connection tests are not scientific extraction

The explicit test sends only a fixed non-scientific instruction to reply `OK`,
the configured model and `stream=false`. No paper metadata, documents, reference
answers, configured extraction prompts or review labels are read or transmitted.
It may incur provider charges. Remote tests need their own explicit synthetic
transfer confirmation; **this never authorizes paper evidence transfer**.

Diagnostics preserve request hash, config snapshot, adapter version, timestamps,
reported model/usage where returned, HTTP status and redacted failure category.
Arbitrary response/error text, headers and keys are not logged. Observed model
use remains ambiguous when auxiliary model details are unavailable. Inspect with:

```bash
corpustrail models connection-history /path/to/project --run-id connection-001
```

Exact completed run-ID replay is cached; a new test requires a new run ID.
Failures remain recorded. There is no automatic retry, provider fallback or
silent model substitution. Interrupted tests require a new explicit run ID.

## Scientific tasks remain separate, explicit and non-authoritative

You must independently supply a versioned extraction specification, choose a
canonical paper and exact evidence depth, inspect the frozen plan and authorize
external transfer before a remote scientific call. See [task/plan workflow](../developer/MODEL_ADAPTERS.md#cli-explicit-no-background-extraction).
The plan shows provider/model, metadata/abstract/selected-passage/full-text mode
and exact input hashes. No depth expands silently; pending or mismatched documents
are rejected. Remote content is subject to third-party privacy/retention terms;
CorpusTrail makes no promises about them.

Models must return a JSON claims object with allowed predicates and exact evidence
quotes. Output is untrusted data, never executable code or file/tool instructions.
Validated claims become immutable, evidence-linked **model/non-authoritative**
Knowledge Layer observations. They never change identity, document trust, human
review authority, corpus membership, prioritization or ASReview eligibility.
Quote/schema checks are not scientific accuracy validation. No predicate is
approved for unattended extraction; no bulk or automatic extraction is activated.

No custom Python adapter or manual database editing is required for the built-in
protocol. Supply a versioned task JSON file, obtain paper IDs with
`corpustrail candidates /path/to/project`, and use `models plan`, `models authorize`
(remote only), `models execute`, `models inspect` and
`knowledge show /path/to/project --paper-id CANONICAL_ID`. Inspect the JSON plan
file before authorizing its printed hash. If an operation reports a failed status
in JSON, inspect its failure/provenance even when the CLI itself returned normally.

## Discovery accounts and model accounts are separate

`models status` describes **model** workflows/adapters, their configured model,
locality, declared credential requirement, credential present/missing state and
external-evidence-transfer policy. It does not authenticate discovery providers.
Discovery adapters are independently configured under `ProjectConfig.providers`
and invoked through `discover --provider ...`; see [discovery configuration](GUIDE.md#discovery-and-providers).
Configuring a model gives no automatic access to Crossref, OpenAlex, Europe PMC
or Semantic Scholar, and configuring a discovery provider supplies no model account.
Each operation uses only its independently named user credential variable.
There is not yet a unified discovery-and-model status dashboard; model status
must not be interpreted as a discovery-provider availability check.

Supported generation settings: `temperature`, `top_p`, `max_tokens` OR
`max_completion_tokens`, `seed`, `frequency_penalty`, `presence_penalty`, `stop`.
Unsupported settings fail rather than being ignored. Connection tests intentionally
do not send scientific generation settings. Scientific wire request/response hashes
are preserved in the response diagnostics alongside the generic run provenance.

## Other protocols and extensions

The stable core remains provider/model agnostic. Another adapter can implement an
unrelated API or local algorithm without changing Knowledge Layer semantics.
See [custom adapter contracts](../developer/MODEL_ADAPTERS.md#python-api-and-custom-adapters).
MCP is a separate optional future tool-access protocol, not required for model use
and not implemented here. No commercial API call is needed by the offline tests.
