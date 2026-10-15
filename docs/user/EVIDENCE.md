# Inspect and retrieve evidence

Open a project → **Corpus** → a publication title → **Evidence**. Opening the page,
reading an abstract, inspecting history or viewing trusted text is read-only and
does not contact external sources, record a review or change corpus membership.

The abstract is the actual stored selected text. Its attribution distinguishes
bibliographic/discovery metadata from an abstract derived from a verified retrieved
document. Discovery abstracts are not verified full text. Earlier and alternative
evidence remains in provenance; retrieval never rewrites a frozen review packet.

## Supported additional evidence

The installed reference resolver is **Europe PMC**, requesting structured XML
through its legitimate open-access route. Enable it in Project Settings. Retrieval
requires a single known PMCID with verified ownership for this publication. DOI,
PMID and PMCID are distinct. Multiple or unverified PMCIDs require identity
inspection; the application does not choose or guess an identifier.

There is no installed standalone DOI/PMID-to-PMCID enrichment adapter. No fuzzy
title match, discovery ranking or model prediction establishes a PMCID. A missing
PMCID honestly makes this retrieval route unavailable, not the publication excluded.
Discovery providers are not automatically full-text resolvers. Unsupported resolver
combinations fail closed without provider substitution.

The panel explains the resolver, identifier, evidence type and configured attempt /
retry-wait bounds before **Retrieve structured text from Europe PMC**. That button
explicitly authorizes the displayed external request; it does not automatically
run after discovery or page opening. Only the PMCID goes to this endpoint, not
your corpus decisions or paper contents. Source terms apply. No account/key is
provided, no credential is collected in the browser and no paywall bypass exists.

## Understand the result

- **Network request succeeded:** a response was returned. This alone is not trust.
- **Exact document identity verified:** the existing service checked article-front
  identifiers against the publication, rejecting conflicts. This establishes
  identity, not relevance, scientific correctness or complete document coverage.
- **Verified structured text:** the existing parser produced trusted document-body
  text. Use **Read verified structured text** and **Read next text segment**. This
  renders plain scientific text, never active XML/HTML, scripts or external images.
  Structure/section provenance remains preserved. It is not a general PDF reader.
  New native-parser v4 results include supported table footnotes and labels.
  This remains a structured-text projection, not a complete facsimile of every
  JATS element. Earlier stored text is not silently re-rendered by an update.
- **Front matter only:** title/abstract may be preserved, but this is not verified
  document-body availability. A recovered abstract can still be read normally.
- **Identity mismatch:** returned identifiers conflict; the document is not trusted.
- **Identity unresolved:** insufficient exact document identifiers; not trusted.
- **Invalid:** content failed validation, including malformed or prohibited XML.
- **Unsuccessful retrieval:** the resolver failed, timed out, rate-limited or did
  not return eligible content. This is not proof that no legitimate evidence exists
  elsewhere. Configured retries remain bounded; no provider is substituted.

Evidence history shows dated resolver attempts, representations and verification
states. **Advanced evidence details** exposes complete paginated scientific records,
request identities, source URLs, hashes and diagnostics. It is operational provenance,
not a method-blind review. Older CLI acquisition records remain visible too.

Supported JATS documents may declare a recognized article DTD, but CorpusTrail
never downloads or processes that DTD. Internal declarations, external entities
and documents requiring DTD-defined entities remain unsupported. Safe XML parsing
still precedes exact publication-identity and document-body checks. Original bytes
and hashes remain preserved; advanced records identify the parsing policy and any
temporary parse-buffer transformation. Updating the software does not reclassify
previously rejected evidence or change historical review packets.

## Refresh, interruptions and explicit retry

Browser refresh never repeats retrieval. Open the recorded operation from its
history to inspect progress. A running worker retains its project-use lease even
if you close the browser or switch/close the project; cooperating processes cannot
move the project to Trash during retrieval. Other/older programs are not protected.

Stopping/crashing the host may interrupt work. An unfinished operation without a
live worker is shown as **Interrupted**, without read-side writes or automatic
replay. Inspect preserved attempts first. No crash-resume or immediate cancellation
is provided. Existing valid evidence remains intact when later requests fail.

Duplicate submissions with the same command identity return the original operation.
An uncertain HTTP response retains that identity for safe reinspection/retry. A
new deliberate retrieval after a known outcome is a new operation with provenance.
Refresh if project settings/identifier ownership changed. Nothing retries merely
because you inspect history.

Workflow receipts live inside the configured project data directory at
`evidence-workflows/v1/`. They are researcher-owned provenance, not cache. Pip
uninstall and software updates do not remove them or your research projects.

Mandatory acceptance uses disposable synthetic projects and offline resolver
fixtures. It does not establish live resolver access or native macOS visual
acceptance. No import, classifier, model extraction or guided review is introduced.

Missing evidence never implies exclusion. Verified evidence never implies inclusion.
CorpusTrail builds broad-topic collections; ASReview remains optional downstream
question-specific screening.
