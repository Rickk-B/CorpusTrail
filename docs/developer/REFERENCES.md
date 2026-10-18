# CP7 reference and context boundary

The approved implementation plan remains authoritative and unchanged. CP7 adds
`ReferenceService`, typed `ContextStrategy` / `DerivedDependency` contracts, a
thin `ReferenceController`, protected `/api/v1/references/` resources and the
packaged References workspace. It does not add CP8 engine/run infrastructure,
CP9 general audit, production importers, dependencies or scientific model calls.

## Persistence decision and measured resources

Additive migration **039**, after frozen 001–038, stores content-addressed
append-only assignments, immutable version headers, 256 hash buckets of shared
membership chunks (at most 256 assignment IDs per chunk), normalized chunk
memberships and explicit correction records. Each version directly references
its resolved chunks. Reads need no recursive delta replay. Unchanged chunks are
shared; full document text is not copied per reference version. Original evidence
bytes/hashes and prior review/population/authority tables are not rewritten.

Before choosing this layout, `tools/reference_storage_benchmark.py` compared
full membership rows with shared chunks across 12 synthetic versions and seven
corrections per successor (Linux/Python 3.12.3/SQLite 3.45.1, 18 October 2026):

| Papers | Full-row database bytes | Chunked bytes | Full memberships | Shared memberships |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 2,805,760 | 782,336 | 12,000 | 1,387 |
| 5,000 | 13,942,784 | 2,379,776 | 60,000 | 6,551 |
| 10,000 | 27,934,720 | 4,407,296 | 120,000 | 13,006 |

This is a **layout prototype**, not product throughput. Actual service acceptance,
using `tools/reference_acceptance.py`, separately enrolled **2,000** distinct
canonical publications through the existing exact identity service, committed
four growing reference versions and one correction, reconstructed all 20
100-entry pages, checked deterministic manifests, frozen contexts, held-out/self
guards, old-version integrity and restart persistence. Observed results:

- 2,001 append-only assignments; 890 shared chunks / 4,610 physical chunk items.
- Whole disposable project database: 26,251,264 bytes, including original identity
  and bibliography/provenance tables, not just reference memberships.
- Maximum 100-entry response: 60,659 UTF-8 bytes.
- Identity enrollment: 75.54 s; reference creation: 1.76 s; all pages: 0.32 s;
  correction/context/integrity: 0.94 s; process peak RSS: 75,648 KiB on Linux.

These dated synthetic engineering observations are not performance guarantees,
collection caps or scientific classifier measurements. Repeat on a NEW disposable
target using an installed development wheel:

```bash
python tools/reference_storage_benchmark.py
python tools/reference_acceptance.py --project /path/to/new/synthetic-project --papers 2000
```

The scale tool is developer acceptance, not a runtime importer. It performs no
direct identity-table inserts or network requests. Typical reads return pages of
at most 100 entries. Explicit preparation/integrity operations may scan a full
version; large-scale evidence I/O still has practical costs. Hash-bucket manifests
are deterministic for exact assignments, independent of input iteration order.
An assignment's deliberate operation identity/order/time is scientific provenance:
separately attested operations need not have identical assignment IDs.

## Scientific service contracts

`Project.references.preview` / `commit` take an explicit operation UUID, collection
name, actor, parent, configuration event, timestamp and 1–500 structured changes.
The browser uses a smaller 20-change/64-KiB HTTP bound. Preview is read only.
Commit recomputes under `BEGIN IMMEDIATE`, checks the preview hash, current family
head, corpus-definition hash and configuration revision. Receipts survive restart;
an identical committed UUID replays without writes, changed content is refused.
Concurrent successors cannot silently overwrite each other. Interrupted inserts
roll back atomically. Update/delete triggers protect all new scientific tables.
Version/context provenance freezes installed scientific source hashes, independently
of a Git checkout. Changed selector source invalidates an unsaved preview; it never
rewrites committed history. Inherited-assignment inspection links its original
version and producer/source receipt, rather than attributing it to the successor.

Labels use existing producer types and exact canonical IDs. Human attestation
requires explicit `True`, human producer identity equal to the acting human, and
the same supported policy. Nonhuman/import proposals require preserved source
artifact/event lineage and cannot retire earlier labels. Exact source observation,
document representation and assignment hashes remain inspectable. A bibliographic
snapshot has a 64-KiB per-assignment bound; no silent metadata truncation occurs.
Document text is referenced by verified existing evidence IDs/hashes. Successor
corrections do not expand older evidence snapshots or populations/review sessions.

`versions`, `members`, `provenance`, `assignment` and `verify` support bounded
inspection or explicit complete integrity checking. Normal header DTOs omit large
membership/hash arrays; provenance on inherited active assignments is explicit.
Known counts exclude contradictory papers and unattested-only proposals. The
default context eligibility policy is **explicit-human-unconflicted/v1**.

## Selected context is an immutable input, not an engine run

`prepare_context` / `commit_context` freeze the exact reference version, strategy
**canonical-reference-order/v1**, configuration, target evidence, held-out IDs
and optional immutable population version, quotas, character budgets, explicit
self-match/truncation policy, derived dependencies, candidate decisions and exact
assembled UTF-8 input. A hash alone or algorithm name is not the saved context.
The original reference text is not overwritten; exact chosen passages and Unicode
offsets, omitted/truncated character counts and hashes are preserved in a bounded
input blob. It has a one-MB byte bound and at most 50,000 text characters (not
invented model-token estimates). Target overflow fails closed. Omissions retain
individual reasons. Default self/held-out labels cannot enter the selected input.
No hidden review judgment is fetched into method-blind APIs.

`register_dependency` accepts already-produced UTF-8 bytes (at most 16 kB), exact
nonempty source-assignment IDs from one version, producer/version, settings and
**unvalidated** state. `index` and `profile` are provenance interfaces only; no
embedding engine, summary generation or index builder is installed or invoked.
Their bytes are non-authoritative, default context use is refused, and explicit
experimental use rejects declared held-out/self/conflicting/unattested sources.
Such use is marked **not independent evaluation**. Declared dependencies cannot
prove an arbitrary producer omitted no undeclared information; registration does
not claim independent validation. The browser intentionally does not expose
derived-artifact registration/experimental inclusion in this checkpoint.

## Application, security and upgrades

GET resources: `configuration`, paginated `versions` / `contexts`, a version's
`members` / `provenance` / `assignments/{exact-handle}`, explicit selected-context
inspection and integrity inspection. POST operations: `preview`, `commit`,
`verify`, `context_preview`, `context_commit`, `upgrade`; schema is
**corpustrail-local-references/v1**. Exact context input is exposed only by explicit
preview/detail inspection, not list pages. Version and context pages replace prior
pages rather than retaining an entire collection in browser memory.

Existing loopback Host/Origin/session/CSRF/CSP/body bounds and project-use leases
apply. Handles are not paths/URLs. Imported text is rendered with `textContent`.
No new filesystem-read/download or URL-fetch endpoint exists. No reference action
contacts a scholarly provider, remote model, telemetry or a cloud service.

Schema 37 and 38 remain read-compatible; ordinary open never migrates. Explicit
upgrade makes a unique database backup before additive DDL, under the existing
writer lock. The new optional `expected_config_event` is checked inside that lock,
not merely in the controller. Interrupted DDL rolls back and the pre-upgrade backup
remains. Invalid/incomplete history fails closed before backup/migration. Existing
real researcher projects are never development fixtures.

CP8 still needs approved engine/run work; CP9 general audit remains later. CP7
must not be described as providing calibrated classification or model performance.
