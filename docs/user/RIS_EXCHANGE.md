# Offline demonstration and RIS exchange

This separately authorized module extends the accepted CP1–10 alpha. It adds one
production bibliographic format and a fresh, scoped offline example. It is not a
beta/public release, full library backup, PDF importer or model integration.
The [current development record](../developer/DEVELOPMENT_BUILDS.md#current-handover)
identifies the exact validated wheel/run; the shared `0.1.0a3.dev0` version alone
cannot identify a build. Keep the accompanying source receipt and `SHA256SUMS`.

## Install and open on macOS

Download the module's validated development bundle linked in the current record.
Unzip into a new `~/CorpusTrailDemo/RIS-build` folder, with the wheel and receipt
directly inside it. Preserve any older downloaded builds. Stop running CorpusTrail
servers with Ctrl+C and wait for the shell prompt before updating software.

```bash
cd ~/CorpusTrailDemo
source .venv/bin/activate
python --version
python -m pip --version
shasum -a 256 RIS-build/corpus_trail-0.1.0a3.dev0-py3-none-any.whl
```

Expect your existing Python 3.13.16 and a pip path inside `CorpusTrailDemo/.venv`.
Compare the wheel checksum and source/run identity with the new bundle receipt,
not the earlier CP10 wheel. Stop on an error, wrong environment or mismatched hash.

```bash
python -m pip install --no-index --no-deps --force-reinstall RIS-build/corpus_trail-0.1.0a3.dev0-py3-none-any.whl
corpustrail demo ~/CorpusTrailDemo/RIS-offline-demo
corpustrail app ~/CorpusTrailDemo/RIS-offline-demo --open-browser
```

The demonstration destination must not exist; creation refuses to overwrite even
an empty directory. If it already exists, preserve it and choose another unused
demo directory consistently. No account, network or optional ML dependency is
needed. The old `python -m corpustrail.tutorial` remains unchanged with its older
historical semantics; use the new `corpustrail demo` command for Guided Review.

## Five-to-ten-minute demonstration

All publications, abstracts and document text here are invented software fixtures,
not scientific judgments or a model-performance demonstration.

1. **Starting candidates** (one minute). The new dashboard has three unreviewed
   candidates and no human observations or membership decisions. `demo_reviewer`
   is explicitly configured for publication authority. The corpus definition is
   explicitly synthetic. In Corpus inspect an abstract and the synthetic verified
   structured document. Another candidate has no abstract and a pending PDF;
   pending is not trusted evidence. The unrelated bookkeeping paper has source
   metadata only. Reading a document does not attest a reading extent.
2. **Collect the supplied sample** (one minute). Open **Research tools → RIS
   exchange → Use supplied synthetic RIS sample**. Enter `demo_reviewer` as actor
   and preview. No manual file preparation is needed; a download is also offered.
   Four source records propose one exact DOI link, two new canonical candidates
   and one deliberately malformed DOI record. Existing and alternative metadata
   remain preserved; an incoming abstract does not silently replace higher-priority
   existing metadata. Explicitly accept the partial source, then **Confirm RIS
   Import**. The project now has five canonical candidates. The failed source
   record remains visible and preserved; it is not an exclusion or a candidate.
3. **Inspect evidence** (one minute). Open the new multilingual sensor publication
   from the import results. Its supplied N2 abstract has two lines and Unicode.
   Inspect the evidence-gap record too: a missing abstract stays missing. The
   import history links to the frozen candidate population and original source
   identity; imports confer no corpus/reference/document authority.
4. **Review manually** (two to four minutes). Go to **Guided Review**, explicitly
   enter `demo_reviewer`, choose all five currently collected publications and
   start. **Skip for now**, then **Previous**, to demonstrate navigation without
   judgment. Assess the fictional sensor/methods examples as Include, bookkeeping
   as Exclude, and the evidence-gap example as Insufficient evidence. Choose only
   the evidence actually used and give a short rationale. Use **Save & Next**;
   the last paper uses **Save assessment**. These are illustrative demo choices,
   not a rule that missing abstracts imply irrelevance.
5. **Confirm separately** (one minute). View the summary, then **Finish Review**.
   Saved observations persist and unassessed papers remain undecided; membership
   is unchanged. From the dashboard's completed-review link open the summary,
   **Preview corpus updates**, inspect the proposed decisions, then explicitly
   **Confirm corpus updates**. With all five demo judgments above, expect three
   included, one excluded and one insufficient. Finishing or previewing alone
   never publishes them.
6. **Export and round trip** (one minute). In RIS exchange choose **Confirmed
   corpus members only**, enter an actor, preview and confirm. Download RIS and
   its provenance receipt. Expect three bibliographic records, with available
   abstracts; no CorpusTrail inclusion/exclusion decisions or model scores are exported. Source notes can preserve external annotations as plain metadata only. Reimport
   that downloaded file using the file selector. The direct supported round trip
   links existing identities, including the source-origin token for ID-less
   records; it does not create extra canonical papers or transfer authority.
   All-candidate or frozen-population export is available only as an explicitly
   different selection. It must not be mistaken for confirmed membership.

Import confirmation executes bounded chunks. If interrupted, inspect the saved
import and deliberately confirm continuation. Earlier committed chunks remain;
opening the page or restarting does not resume them. A changed configuration or
identity state can require a fresh preview. Do not alter stored workflow files.

To reopen: wait for active work/saves, close the tab, press Ctrl+C in the serving
Terminal and wait for the shell prompt. Closing a browser tab alone leaves the
server running. Later run:

```bash
cd ~/CorpusTrailDemo
source .venv/bin/activate
corpustrail app ~/CorpusTrailDemo/RIS-offline-demo --open-browser
```

Do not recreate the demo. If port 8766 is occupied, use the same command with
`--port 0`; use the printed loopback URL. Research projects and external originals
remain separate from the installed software. Do not reuse this fictional scope
or its labels for real research. No project deletion is part of this tour.

## Initial compatibility profile: `corpustrail-ris/v1`

UTF-8 with optional BOM; LF, CRLF and CR line endings. Records need nonempty `TY`
and terminating `ER` tags. The standard two-space delimiter and a one-space/tab
variant are explicitly supported. Untagged continuation lines belong to the
preceding field; six-space continuation indentation is removed once. Outer field
whitespace is normalized; original bytes remain unchanged. Unicode is retained.

| Fields | Supported tags and handling |
|---|---|
| Title | TI, then T1, then CT. |
| Abstract | AB preferred, then N2; multiline and blank paragraphs supported. Missing stays missing. Different alternatives remain in original source with a warning. |
| Authors | Repeated AU followed by A1, retaining order within each tag group and Unicode; identical entries deduplicated. |
| Publication year | PY, then Y1, then DA; an exact four-digit year or its date prefix. Unrecognized dates remain raw with a warning. |
| Journal/source | JF, JO, T2, JA in that preference order; no provider/journal conflation. |
| DOI | DO; UR only for `http://doi.org/` or `https://doi.org/` links. Existing DOI normalization/validation only; other URL forms remain raw metadata. |
| PMID / PMCID | Explicit PM PMID; AN only with `PMID:` prefix; C2 only with explicit `PMC` form. A bare accession number is not guessed to be PMID. |
| Other supported exact IDs | C1 `OpenAlex: …`, `SemanticScholar: …` use existing normalizers. |
| Source-origin token | C1 `CorpusTrail-Origin: ` plus 64 hex characters is an opaque namespaced source identity, not a DOI/PMID or human assertion. It preserves direct RIS round trips without title matching. |
| Publication type and additional source metadata | TY plus ID, VL, IS, SP, EP, SN, LA, KW, N1 and non-DOI UR remain source metadata; export preserves the first supported RIS values with observation lineage. Non-RIS publications without a retained type export as GEN. Notes never become human labels. |
| Attachments / unknown tags | Original source only. No L1/L2 retrieval, file opening, URL following, DOI lookup, OCR or unsupported-field interpretation. Unknown fields are not promised in a newly rendered export. |

Import follows the native canonical metadata selector; source alternatives are
inspectable and not overwritten. Exact duplicate identifiers link one canonical
paper while retaining independent source records. Conflicting verified owners or
multiple distinct DOI/PMID assertions stay unresolved; no fuzzy title merge or
silent repair occurs. Failed records do not become review candidates. Correct a
source through a new explicit import rather than rewriting original history.

ID is a source record ID, not a globally unique publication ID. For records without
global identifiers, origin keys bind exact original file bytes and record locators.
Independently prepared ID-less sources can remain separate works; title similarity
is not enough to merge them. Other software may discard the C1 origin extension:
no ID-less deduplication guarantee applies after that transformation. RIS dialects
vary; this profile does not promise universal Zotero/database interoperability.
For a paper originally collected through a non-RIS route without a supported exact identifier or an existing RIS origin token, export/reimport may propose a separate source-origin candidate. The preview reports it as new rather than guessing a title match; cancel if that is not intended. Round-trip identity guarantees require a supported identifier or retained existing token.

A file export is not a project or reference-library backup or ongoing sync.

## Persistence, limits and safety

- Per operation: up to 4 MiB, 2,000 records and 200,000 characters per field (normalized record budget 1 MiB); imports
  execute at most 20 records per confirmed request. These are resource limits,
  not limits on the total project population. Split larger sources deliberately.
- The source file is copied from an explicit selection into confined project-owned
  storage; its original is not modified. Original bytes, parser version/hash,
  stable locators, outcomes and immutable export/selection receipts are retained.
- Import preview simulates the native enrollment service in an isolated database
  copy. It creates no publication, reference label, review or membership event.
- Invalid encoding/NUL sources report a whole-file parsing failure with unknown
  source-record count; no fake publication count is inferred. Normalized parsing
  results are frozen separately, so history is not silently re-parsed on upgrade.
- Exact operation retries reuse receipts. Independently confirmed imports retain
  source provenance without reminting exact known identities. Committed chunks
  survive later failure; interrupted SQL transactions roll back. Continuation
  needs explicit confirmation and matching identity/configuration revision.
- Exports freeze actual selected metadata/abstracts, exact IDs, membership heads
  and source lineage; changes later do not rewrite existing exports. Original RIS
  bytes remain downloadable through their verified immutable artifact.
- No new database migration is required. Import needs existing population storage;
  an older project requires its established explicit backed-up population upgrade
  before import. Opening/browsing alone never upgrades it.
- Source bytes, imported observations, populations, evidence, reviews and exports
  are researcher-owned material. Software removal does not delete them. See
  [data ownership](REMOVAL_STORAGE.md). No model or external service is invoked.

The native MacBook Europe PMC transport cause remains a separate unresolved issue.
Nothing in this offline workflow establishes its resolution or real-model validity.
