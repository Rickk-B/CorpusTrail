# Security decision: inert JATS DOCTYPE compatibility

## Requirement and decision

The 2026-10-14 authorized Europe PMC response for PMC13558126 was well-formed
article XML with an external DOCTYPE and matching diagnostic identifiers. The
`bounded-no-dtd/v1` boundary correctly refused it before scientific verification.
Its original bytes were discarded with the disposable project; the sanitized
417,134-byte / SHA-256 record is not a substitute for those bytes. No new live
request is authorized by this implementation task.

Extend the existing stdlib boundary, not a new parser/dependency. Expat
recognizes the encoded XML syntax, checks limits and permits **only** an `article`
PUBLIC declaration identifying NLM JATS 1.0–1.4 publishing, archiving or authoring,
with the corresponding canonical JATS filename (including supported MathML
variants). Its system identifier is either that bare filename or the exact
corresponding HTTPS `jats.nlm.nih.gov` location. These identifiers are textual
eligibility checks, not fetch destinations or evidence of publication identity.
All other DOCTYPE forms remain refused. Even an empty internal subset is refused.

Parameter-entity parsing remains NEVER; foreign DTD use is disabled. Declaration,
external-reference and skipped-entity callbacks fail closed. No external parser,
resolver, catalog, network/file loader or XInclude/stylesheet executor is created.
The full Expat pass must succeed before a second Expat token pass locates the
actual DOCTYPE opening token and closing-delimiter byte offset. Comments, processing
instructions, CDATA and element text are handled separately, never searched as raw
markup. Only that validated declaration is elided in a temporary parsing buffer.
Supported encodings use one/two bytes for its closing delimiter; tests cover BOM,
no-BOM, UTF-8/16 and Latin-1 with declaration-like comments/CDATA. The unchanged XML
declaration, BOM and article bytes are retained. Malformed/multiple/misplaced or
internal-subset declarations fail before this transformation.

ElementTree strictly parses the temporary buffer without an external declaration.
This is necessary: an unread external DTD can cause Expat/ElementTree to silently
omit an undeclared entity in an attribute. The original pass rejects skipped body
entities; the final no-DTD pass rejects undefined attribute entities as well. No
fragile regex, whole-document decoding/re-encoding, DTD loading or persistent
normalized-source artifact is introduced. New provenance distinguishes the temporary
parse-input hash/transformation from the preserved original document hash.

## Boundaries, versions and alternatives

The policy becomes `bounded-inert-jats/v2`. Existing byte/node/depth/text limits
remain; bounded attribute count/value totals, namespace URI lengths and expanded
name totals strengthen pre-tree resource checks.
DOCTYPE acceptance requires Expat >=2.6.0, with reparse deferral never disabled.
Patched Python/Expat remain prerequisites, not a formal denial-of-service guarantee.
Supported XML encodings are unchanged. This is non-validating parsing: no DTD
defaults, schema validation, external entities or DTD-dependent named entities.
Use numeric character references or XML's predefined entities instead.

New XML representation records identify the policy and verification version;
derived text identifies the advanced native parser version. JSON provenance
already supports additive payload metadata: no schema or migration is needed.
Original bytes/hashes remain authoritative source artifacts. Existing records,
trusted evidence, reviews, identities and membership are never rewritten or
reclassified. Ordinary reads do not invoke fresh document verification.

Alternatives rejected: broad DTD acceptance, DTD loading/validation, internal entity
support, regex prolog removal, external resolver replacement and new dependencies.
A safe declaration does not establish article structure, exact identity or body
availability; all existing scientific checks remain authoritative.

## Verification plan

Keep every existing negative fixture. Add instrumented no-I/O tests for accepted
JATS and malformed/duplicate/misplaced declarations, internal subsets, file/network
general/parameter entities, skipped/recursive entities, encodings, wrong roots and
resource bounds. Exercise original hashes/provenance, identifier conflicts,
front-matter-only articles and prior valid/rejected evidence in disposable projects.
Run the actual packaged browser retrieval/read/provenance/refresh/restart workflow
with synthetic inert-JATS bytes. Never publish a complete real article as a fixture.

Python documents the relevant [Expat controls and callbacks](https://docs.python.org/3.11/library/pyexpat.html)
and [XML security limitations](https://docs.python.org/3.11/library/xml.html#xml-vulnerabilities).
The [NLM JATS tag sets](https://jats.nlm.nih.gov/) identify the scientific vocabulary;
allowlisting their identifiers does not validate a document against those DTDs.

## Development artifact scope receipt

The artifact tool retains the old scientific-execution restrictions for discovery
and all unrelated modules. XML compatibility is bound to the exact five source
digests in implementation `f234cad157fb4de4739aaff1bc11ddf441352edf`, plus ancestor
validation. A later unreviewed edit fails closed. The receipt explicitly reports
changed XML execution, rather than claiming it remained unchanged. Implementation
lineage is distinct from the final wheel's source/build SHA and researcher acceptance.
