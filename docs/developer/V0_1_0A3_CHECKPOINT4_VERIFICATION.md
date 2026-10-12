# v0.1.0a3 Checkpoint 4 — evidence verification report

Baseline: `eb044c557c9b04df68b361ab691cb46bcd365159`; development branch
`development/v0.1.0a3-read-only-local-ui`; version `0.1.0a3.dev0`.
This is not a public release, native graphical acceptance or Checkpoint 5 approval.
No live resolver/provider/model request was made for mandatory acceptance.

## Implemented architecture and scope

Existing publication detail → packaged evidence client → protected `/api/v1/evidence/`
→ application EvidenceController → existing EvidenceService / identity / XML /
artifact / document-read services. The scientific acquisition, verification,
parsing and evidence-status methods are byte-identical to the baseline. One bounded,
integrity-checked provenance read method is appended. No migration or dependency
was added. Config revisions, membership, review, Knowledge, models and ASReview
semantics remain unchanged.

Only installed, configured Europe PMC structured XML retrieval is exposed. It
requires one known PMCID with verified ownership, explicit network action and a
current configuration/identifier snapshot. Ambiguous, absent or unverified PMCIDs
and unsupported resolver combinations fail closed. There is no DOI/PMID-to-PMCID
enrichment implementation; the limitation is explicit, not a speculative lookup.
No fuzzy matching, identifier assignment, provider expansion or corpus decision
is introduced.

## States, provenance and content

Metadata abstracts and recovered document abstracts retain actual selected-source
attribution. Network success, document identity, parser result and document-body
readability are distinct. Invalid/mismatched/unresolved documents are not readable
trusted evidence. Verified front matter can supply an abstract without being
advertised as document-body availability. Prior valid evidence is never deleted by
a later failed retrieval. Scientific attempts/response hashes/representations and
parser lineage remain in the original pipeline/artifact store. Normal histories
are bounded readable summaries; explicit advanced pages retain full envelopes.
The existing reader checks trust, depth, integrity and confinement and returns
plain text segments, never executable XML/HTML or arbitrary files.

## Lifecycle and safety

Existing immutable workflow-file publication accepts an internal evidence family,
leaving discovery's default paths/receipts unchanged. New application receipts live
inside the configured data directory at `evidence-workflows/v1/`; no global registry
or second scientific database exists. These files are researcher-owned provenance.
Command identities bind exact content; duplicate starts inspect the original job.
Queued reservation precedes thread startup. Startup/host interruption cannot be
silently replayed. Liveness probes refresh terminal history to avoid a false race
claim. GETs never append/reconcile state or contact providers.

Worker lifetime holds its own shared project lease and the project-wide scientific
worker key shared with discovery. Evidence-specific liveness/journal keys reuse
existing external OS anchors. Closing a project/browser does not release the worker
lease; other cooperating processes still block removal. Location is revalidated
under the lease. Crash releases kernel locks; no crash-resume or immediate
cancellation is promised. Older/unrelated programs and hostile external filesystem
mutation are not protected.

Loopback/Host/Origin/CSRF/CSP, bounded strict JSON, no CORS, safe text and confined
paths remain. Browser requests cannot supply URLs, filenames, identifiers, resolver
code or secrets. Existing host/no-redirect restrictions, 20-MB response cap, socket
timeout, bounded retries and XML resource/entity policy apply. Known credential
echoes are rejected before preservation. No remote frontend assets or paywall
bypass are added. Model calls, reference labels and membership writes are absent.

## Local acceptance

Linux / Python 3.12.3, optional ML installed, disposable synthetic projects only.

| Check | Result |
|---|---|
| Final focused evidence suite | 16 tests, OK; 13.775 seconds |
| Final full standalone suite | 454 tests, OK; 1 native macOS opt-in skip; 114.127 seconds |
| Artifact tooling suite | 12 tests, OK |
| Ruff, JavaScript syntax and whitespace | Passed |
| Changed-source privacy scan | No blocking findings |
| Independent wheel/core full suite | 454 tests, OK; 47 optional/native skips; 105.738 seconds |
| Independent wheel/ML full suite | 454 tests, OK; 1 native skip; 113.771 seconds |
| Independent sdist→wheel/core full suite | 454 tests, OK; 47 skips; 98.962 seconds |
| Independent sdist→wheel/ML full suite | 454 tests, OK; 1 skip; 113.595 seconds |
| Installed CLI / offline tutorials / reinstall preservation | Passed, `network_used=false`, version `0.1.0a3.dev0` |
| Final wheel/core focused evidence suite | 16 tests, OK; 13.044 seconds; tutorial/CLI passed |
| Final sdist→wheel/core focused evidence suite | 16 tests, OK; 13.183 seconds; tutorial/CLI passed |

Clean installed core/ML wheel and sdist acceptance and hosted Python 3.11–3.13 /
macOS / Windows checks are gates for the exact downloadable artifact. The receipt
records its source SHA, not this earlier baseline. Final hosted run/artifact/hash
belong in the completion report and generated receipt, not a self-referential
commit declaration here.

The four local full clean-install results precede final queued-state and manifest /
reservation binding hardening. Final source/installed focused acceptance reruns
those affected checks; the exact-source hosted gates rerun complete clean-install
matrices before uploading any development artifact. These are application read /
lifecycle integrity checks, not changes to scientific verification or acquisition.

### Offline end-to-end scenarios

A. A known-PMCID publication displays its metadata abstract; an explicit request
uses the actual Europe PMC resolver URL and existing verifier/parser, writes
verified structured text/provenance, and is readable through the existing safe
reader. No review/membership event is created. Duplicate commands make one request.

B. A wrong DOI/PMCID document produces mismatch. Malformed/empty/DTD content is
invalid; a document lacking exact front identifiers remains unresolved. None is
trusted/readable. Earlier valid evidence remains byte/provenance-identical.

C. Missing, unverified, multiple or unsupported identifiers/configuration prevent
retrieval without network activity or fabricated PMCID. Recovered abstract-only
front matter remains abstract evidence, not verified full document-body evidence.

D. Five-paper fixtures with an authorized human event and frozen session preserve
configuration, review history, membership and frozen state across acquisition.
Read-only views use complete before/after project fingerprints. Original imported
research files and actual user projects are not used or removed.

Failure fixtures include 404, empty/malformed XML, timeouts, 429/Retry-After above
the bound and successful bounded retry. Additional tests exercise stale config
during a request, startup failure, deterministic completion/liveness race, symlink
targets, paginated history, command collisions, credential echo, response size,
Host/Origin/CSRF/body/path checks, project-close lifetime and a real independent
process killed during acquisition with crash-safe exclusive-lock recovery.

Packaged browser JavaScript runs against the real local API in a developer-only
DOM harness: opening performs only reads, clicking retrieves explicitly, normal
history shows verification, and raw provenance requires an explicit advanced action.
This is not native browser layout validation or a production-throughput claim.

## Limits and stop boundary

- One known-PMCID Europe PMC route; no enrichment, other resolver, generic file
  upload/download, PDF reader, crawling or paywall bypass.
- A completed network operation can still produce invalid/unresolved evidence.
  Document identity is not completeness, relevance or scientific authority.
- Retry policy is existing and bounded. There is no crash-resume or cancellation
  UI. The socket timeout is not an absolute whole-operation deadline.
- Local operation history currently scans manifests; responses and scientific
  provenance pages are bounded. No new persistent index/registry is introduced.
- Final native macOS graphical and live-resolver acceptance remains with the user.
- No Checkpoint 5, guided review, membership redesign, import, classifier, model,
  Knowledge/ASReview redesign, MCP, main merge, release tag, Release or PyPI work.

See [user guide](../user/EVIDENCE.md) and [workflow contract](EVIDENCE_WORKFLOWS.md).
