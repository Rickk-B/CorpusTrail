# Checkpoint 4 evidence application contract

`corpustrail-evidence-workflow/v1` uses the existing `EvidenceService.plan/acquire`,
`ResolutionRequest`, `EuropePmcResolver`, identity `exact_owner`, XML policy,
document verifier/parser, artifact store and `ProjectReads.document`. There is no
second trust/identity/enrichment algorithm or scientific database. Existing methods
remain byte-identical; one bounded provenance read method is appended. No migration
or production dependency is added.

## Boundaries

GET `/api/v1/evidence/papers/{paper-handle}` inspects current evidence/eligibility.
`/history` pages local operations and existing scientific attempts. `/provenance`
is an explicitly operational, complete paginated scientific surface, separate from
method-blind review. GET `/api/v1/evidence/operations/{operation-handle}` inspects
frozen request/status, not a network action. No GET creates project/workflow files.

POST `/api/v1/evidence/start` requires the versioned schema, paper handle, command
identity, eligibility hash and explicit `confirm_external=true`. Existing session,
Host/Origin/CSRF, 64-KiB strict JSON and path protections apply. The browser cannot
provide URLs, paths, resolver code, identifiers, credentials or scientific outcomes.

Eligibility is derived from the existing request/configuration and verified exact
ownership. Only the installed configured single Europe PMC route with one verified
PMCID is exposed. An immutable frozen request is revalidated before the worker and
each bounded network attempt. Changed configuration/identifiers fail closed.
No PMCID lookup is installed; its unavailable state is explicit. Future reviewed
lookup adapters must retain exact input/returned relationship, versions, request /
response hashes, conflict handling, accepted alias provenance and explicit consent,
as specified in the approved plan. No placeholder scientific enrichment records
or fake lookup capability are implemented here.

## Lifecycle and storage

The existing immutable workflow-file publisher now accepts only internal allowlisted
families: discovery (unchanged default) and evidence. Evidence plans and hash-chained
queued/running/terminal receipts reside in `evidence-workflows/v1/`. Request identities
bind exact command content. Replays inspect the original operation; new attempts
require a new explicit command. The queued reservation is written before launching
the daemon worker. Failed startup cannot become implicit resend. A free liveness
probe refreshes history before declaring interruption to avoid the prior discovery
completion race. Reads never reconcile or append state.

Workers use existing external kernel anchors: shared project lease, project-wide
scientific worker key shared with Discovery, evidence-specific liveness key and
short evidence journal key. Network execution never holds the journal lease or a
scientific DB transaction. Project location is revalidated under the independent
lease. Closing one launcher/project does not release the worker lease or terminate
other processes. Host exit releases kernel locks and unfinished receipts project
Interrupted. No crash-resume, cancellation framework or distributed coordinator is
claimed; unrelated/older programs and hostile filesystem mutation are not covered.

Scientific resolution plans, requests, results, bytes, representations and parser
lineage remain in the existing pipeline/artifact store. Operation completion and
network outcome are separate from document trust and readability. A failed later
attempt never deletes prior valid evidence. No review, membership, model, Knowledge
or ASReview event is written by this workflow.

## Bounds and untrusted input

The existing HTTPS/no-redirect/approved-host rules remain. Transport responses are
bounded to 20 MB; timeout is the existing 30-second socket timeout, not a claimed
whole-operation deadline. The configured policy permits 1–3 attempts and at most
60 seconds retry wait. Existing XML byte/depth/node/text and DTD/entity restrictions
and native parser apply. Known credential echoes/signatures are refused before
artifact preservation. No remote exception message is persisted.

Normal DTOs project readable, bounded attempt/representation summaries. Raw envelopes
are only on explicit advanced inspection. Full raw bytes remain content-addressed
locally; no generic download/file-serving endpoint exists. The existing reader
verifies enrollment, trust, document-body depth, artifact hash and path confinement
before returning bounded plain-text segments. Raw XML/HTML is never executed.

The frontend only renders authoritative states and initiates explicit operations.
It does not independently verify identity, infer scientific authority or construct
SQL/CLI commands. Tests remain offline, with real-process leases and disposable
projects; hosted native macOS guard/Trash acceptance remains required independently
of final researcher-performed graphical/resolver acceptance.
