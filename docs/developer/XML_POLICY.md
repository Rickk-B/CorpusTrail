# XML ingestion policy: bounded-no-dtd/v1

All native JATS, publisher XML, GROBID TEI rendering, article identifier
inspection and recovered-abstract parsing use `_internal.xml_safety.parse_xml`.
There are no other direct ElementTree parse entry points outside that boundary.

Before Phase 3B1 the native parsers and document identity helper searched raw
bytes for ASCII DOCTYPE/ENTITY tokens. UTF-16 inserts zero bytes, bypassing that
scan. Regression fixtures reproduced expansion for both endian orders, with
and without BOM. This was a declaration-policy bypass, not demonstrated file
disclosure or network access.

The new boundary validates immutable bytes with Expat callbacks before building
the same input with ElementTree. DTD declarations (even empty or external),
entity declarations and external entity references fail closed. Parameter-entity
parsing is disabled. Predefined XML entities and numeric character references
remain valid. No entity loader, XInclude execution, stylesheet processing or
network access is installed. Markup in comments is not an active declaration.

Valid UTF-8 (optional BOM), UTF-16LE/BE (BOM and declared no-BOM variants), ASCII
and Latin-1 use Expat's encoding detection. UTF-32 and unsupported encodings
are typed invalid inputs, not decoded/rewritten speculatively. Compressed gzip,
ZIP or other binary inputs are not unwrapped by the acquisition or native-parser
interfaces: callers must supply XML bytes. A provider wrapper that delivers XML
bytes reaches this same boundary; no compressed acquisition adapter exists.

Limits: 50,000,000 bytes, 100,000 elements, depth 128, 20,000,000 decoded text
characters. File reads are bounded before allocation. Node/depth/text bounds are
checked before building the tree. The renderer tracks offsets incrementally to
avoid repeatedly summing all preceding blocks. Safe article content and offsets
retain the existing rendering semantics; native parser versions advance to v2.

Invalid evidence is retained with provenance but is not trusted. Exact article
identifiers, not cited-reference IDs or fuzzy titles, establish document identity.
Matching identity does not validate scientific claims or establish membership.

Use patched supported Python/Expat builds. Resource bounds are not a formal XML
security certification or a guarantee against every resource-exhaustion input.
See [Python's Expat API](https://docs.python.org/3/library/pyexpat.html) and
[XML security guidance](https://docs.python.org/3/library/xml.html#xml-vulnerabilities).
