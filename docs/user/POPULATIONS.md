# Candidate populations

Choose **Populations** from an open project's navigation or dashboard. This page
is read-only on opening and contacts no external services. A candidate population
is not authoritative corpus membership.

Enter a name and explicit creator attribution (which grants no reviewer authority).
Choose collected papers, current corpus members, awaiting-decision papers,
completed discovery sources, individual canonical papers or saved versions.
**Preview Candidate Population** shows counts without saving. Edits invalidate it;
changed sources/configuration require another preview. **Freeze Population** is a
separate explicit save. No enrollment, review or membership is performed.

One canonical paper may have several observations; all origins survive without
counting as additional papers. Lineage counts include source associations, not just
provider records. Unlinked discovery records are kept separately and require an
explicit acknowledgment; they are not resolved review candidates. Titles never
establish identity.

Completed discovery sources means runs with a recorded outcome, not proof of a
successful or exhaustive search. Inspect Discovery history for request failures
and coverage. The population freezes preserved, canonically linked observations,
not all publications potentially available from that provider.

Saved cards show version, creator and counts. **Inspect Frozen Version** shows
sources and paginated candidates. Expand **Population provenance and source
lineage** for exact identity snapshots, references and hashes. **Verify Stored
Integrity** validates the full manifest, not document trust or corpus membership.

Select saved-version checkboxes to combine populations. Source order does not
change the canonical set/content manifest, but independently created versions
retain distinct request identities and timestamps. **Create Successor Version**
starts a new explicit selection in the same family. Choose its sources again;
earlier versions never grow automatically. Current Corpus bibliography may develop
while the frozen IDs/lineage remain unchanged. Inactive identities cannot silently
remap into a review; prepare a successor using valid exact identities.

**Review This Frozen Version** opens Review without starting a session. Explicitly
enter the reviewer, then start. Review freezes its own current evidence/configuration;
candidate identity is not an attestation of reading. Existing sessions never expand.
Method-blind review receives opaque version/hash references, not origin labels or
methods. The Populations page itself is operational, not blinded.
Population creation, Save & Next and Finish Review never publish membership.

## Existing projects and limitations

Schema-37 projects work without automatic migration. **Back Up and Enable
Populations** explicitly creates a new project-local backup and adds the tables.
Close older app versions first; keep the backup. Configuration, evidence, reviews,
decisions and sessions are preserved. Older builds cannot open upgraded databases.

The separately approved [RIS exchange](RIS_EXCHANGE.md) imports bibliographic
records through this existing source interface. Other formats, PDF ingestion,
folder scanning and direct library synchronization remain unimplemented. Earlier
synthetic interface tests alone did not implement that production importer. Cross-project combinations are not supported.

Read pages contain at most 100 entries; individual selection units accept up to
500 IDs. Larger sources can be frozen directly or combined from versions. No fixed
collection cap is imposed, but freezing, union, verification and review creation
inspect the whole selected set and cost proportionally more. They are synchronous
transactions, not resumable background jobs. Interrupted writes roll back; identical
explicit requests replay committed receipts without duplication. History never
recreates versions or reruns discovery.
