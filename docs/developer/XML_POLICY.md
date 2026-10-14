# XML ingestion policy: bounded-inert-jats/v2

All native JATS, publisher XML, GROBID TEI rendering, article identifier
inspection and recovered-abstract parsing use `_internal.xml_safety.parse_xml`.
There are no other direct ElementTree parse entry points outside that boundary.

Before Phase 3B1 the native parsers and document identity helper searched raw
bytes for ASCII DOCTYPE/ENTITY tokens. UTF-16 inserts zero bytes, bypassing that
scan. Regression fixtures reproduced expansion for both endian orders, with
and without BOM. This was a declaration-policy bypass, not demonstrated file
disclosure or network access.

The boundary first validates immutable bytes with encoding-aware Expat callbacks.
Only a PUBLIC `article` declaration identifying NLM JATS 1.0–1.4 archiving,
publishing or authoring with the corresponding canonical filename (optionally
MathML2/3) is accepted. Its system identifier is that bare filename or the exact
corresponding HTTPS `jats.nlm.nih.gov` location. None is opened. SYSTEM-only, empty,
unrelated, file/traversal and every internal-subset declaration remain rejected.
Entity/attribute/element/notation declarations, external references and skipped
entities fail closed. Parameter parsing is NEVER; foreign DTD use is disabled.
Accepted inert declarations require Expat >=2.6.0; reparse deferral is never disabled.

After the full validation pass, a second Expat token pass supplies the declaration's
opening and closing-delimiter byte offsets. Only that syntax-delimited declaration
is elided in a temporary parse buffer. Comments, PI and CDATA are handled separately.
No regex stripping or document decoding/re-encoding occurs. ElementTree strictly
parses the no-DTD buffer, rejecting undefined attribute entities that an unread-DTD
parser could otherwise silently omit. Original source bytes are never rewritten.

No loader, catalog, external child parser, XInclude executor, stylesheet processor
or network/file fetch is installed. Predefined XML entities and numeric references
remain valid; DTD-dependent named entities remain unsupported. This is not DTD/schema
validation or scientific identity verification. See the [security decision](JATS_COMPATIBILITY.md).

Valid UTF-8 (optional BOM), UTF-16LE/BE (BOM and declared no-BOM variants), ASCII
and Latin-1 use Expat's encoding detection. UTF-32 and unsupported encodings
are typed invalid inputs, not decoded/rewritten speculatively. Compressed gzip,
ZIP or other binary inputs are not unwrapped by the acquisition or native-parser
interfaces: callers must supply XML bytes. A provider wrapper that delivers XML
bytes reaches this same boundary; no compressed acquisition adapter exists.

Limits: 50,000,000 bytes, 100,000 elements, depth 128, 20,000,000 decoded text
characters. File reads are bounded before allocation. Node/depth/text bounds are
checked before building the tree. Attribute checks additionally limit 256 attributes
per element and 2,000,000 total attribute-name/value characters. The renderer tracks offsets incrementally to
avoid repeatedly summing all preceding blocks. Safe article content and offsets
retain the existing rendering semantics; native JATS/publisher parser versions
advance to v3 and Europe PMC resolver version to `jats/v2`.

Namespace-aware validation also limits namespace URIs to 4,096 characters and
total expanded element/attribute names to 2,000,000 characters, preventing a short
repeated namespace prefix from amplifying tree allocation beyond those bounds.

New XML representation records retain the original artifact hash and separately
identify this policy, document-verification version, temporary parse-input SHA-256
and transformation (`none` or `expat-delimited-inert-doctype-elision/v1`). Graphical
evidence eligibility binds resolver, native-parser and XML-boundary source hashes.
Historical `bounded-no-dtd/v1` records are not rewritten or reclassified by reads.
No automatic reconsideration operation is added; no schema/migration is required.

Invalid evidence is retained with provenance but is not trusted. Exact article
identifiers, not cited-reference IDs or fuzzy titles, establish document identity.
Matching identity does not validate scientific claims or establish membership.

Use patched supported Python/Expat builds. Resource bounds are not a formal XML
security certification or a guarantee against every resource-exhaustion input.
See [Python's Expat API](https://docs.python.org/3/library/pyexpat.html) and
[XML security guidance](https://docs.python.org/3/library/xml.html#xml-vulnerabilities).
