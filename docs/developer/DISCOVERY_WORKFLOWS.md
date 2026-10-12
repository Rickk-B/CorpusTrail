# Checkpoint 3 exact discovery / local jobs

`corpustrail-discovery-workflow/v1` HTTP DTOs and
`corpustrail-local-workflow-record/v1` durable receipts are application contracts,
not a second scientific discovery engine. No migration, new database or runtime
dependency is introduced. Existing 001–037 resources remain byte-identical; old
projects open without upgrade. Only pure read/preview helpers are added to the
discovery/metadata modules. Planning, normalization, execution, retry, enrollment
and scientific reservation implementations are unchanged.

## Immutable prepared plans and explicit approval

Application preparation calls `DiscoveryService.plan` once per selected adapter
and saves the exact dataclass/plan ID, project/configuration revision, timestamp,
software version, adapter module hash and actual adapter-derived request preview.
The manifest's content hash is its handle. Initial and cursor-template requests
come from `provider.request`, not a separate translation. Every execution request
must match the frozen template. Actual cursor/request/response lineage stays in
the existing pipeline. No future token/total or exhaustive coverage is fabricated.

Preview POST issues a launcher-held random 15-minute nonce bound to that project
and exact manifest (maximum 256 pending previews). Approval requires this nonce,
session/CSRF, explicit external-query consent and explicit exact-identity/source
organization approval. A bare plan ID/hash is insufficient. Approval is an immutable
event, not a review authority event. Run is a separate POST and checks approval,
invalidation, configuration revision and adapter/request equality again. Edit
appends invalidation; no old plan/event is overwritten. Changed settings require
new planning, not narrowed/reinterpreted revision guards.

Command receipts bind request IDs to exact body hashes. The queued event reserves
one execution per manifest. Identical retries return that job; a different command
cannot rerun an already reserved manifest. New repeats get new provider run IDs
and require new consent. Scientific `request_started` reservations and interrupted
replay refusal remain authoritative and unchanged.

## File publication and lifecycle

Records live in the configured project data directory under
`discovery-workflows/v1/{plans,events,commands}`. They are researcher-owned provenance,
not global preferences/cache. Reads never mkdir, migrate, append events or reconcile.
Records use canonical JSON plus content hashes. Event sequence/previous hashes
form an append-only chain. Complete, fsynced bytes are published by same-filesystem
hard link with no overwrite; unsupported local filesystems fail closed. Only the
uniquely created staging file is cleaned up. Interrupted staging files are not
treated as published receipts. Original science and all other projects are untouched.

Short journal publication uses the existing OS anchor/lease implementation with
named application-operation keys. A worker holds its own shared project lease,
an exclusive one-worker-per-project key and a job-specific liveness key. These
anchors are outside research directories, including after movement. Journal/network
work never holds a scientific DB transaction open. Startup reserves durably before
launching the worker. Locks remain held until the worker actually stops, not until
the browser or current project context closes. Identity is revalidated before
worker events. Same-user/machine cooperating versions only; unrelated/older programs
and hostile filesystem mutation are not covered.

Worker threads run selected providers sequentially through the existing executor
and, after explicit approval, its canonicalization service. A failed provider does
not substitute another or erase successful records. Bounded provider work completes
before cooperative cancellation is checked; this is not immediate request/page
cancellation. There is no distributed framework or crash-resume. Daemon workers
may be interrupted by host exit; receipt status without a live job key projects
Interrupted without any read-side write or implicit resend. A parent terminal
receipt is required to claim completion even if a child scientific run completed.

## Read models, privacy and HTTP

Indexed run-scope scientific projections provide request/observation counts,
canonical-link counts and distinct create/attach identities. Polls do not load the
whole catalogue, raw response payloads or paper-ID arrays. Linked publication and
technical request pages are bounded and have deterministic ordering. Search-history
pages sort by immutable creation time/handle. Identity failures/unlinked observations
are not membership judgments. Dynamic provider totals are not recorded by the old
executor and are not invented by the UI.

The application calls only the four installed metadata adapters, with no arbitrary
URL/provider plugin from a browser. Existing approved-host HTTPS/no-redirect and
retry bounds remain in force. Credential values are passed through the existing
environment/header mechanism; a transport guard rejects echoed known credentials
before raw bytes/rate headers can be preserved. Errors record types/codes, not remote
messages. Credentials are never configuration/form/provenance fields.

`/api/v1/discovery/{configuration,history}` and plan/detail/papers/provenance reads
are operational, not method-blind review endpoints. Protected POSTs are prepare,
approve, start, invalidate and cancel. Existing loopback/Host/Origin/CSRF/CSP, 64-KiB
strict JSON body limits, safe rendering and filesystem confinement remain. No HTTP
SQL, shelling to CLI, remote frontend assets or network on opening pages.

Publication history remains auditable, but current linked-paper metadata is a live
canonical read view, not a new immutable candidate-population contract. Evidence,
review, classifier, import, model, Knowledge and ASReview workflows are out of scope.
