"""Encoding-aware bounded XML; inert allowlisted JATS declarations, never DTD I/O.

Expat validates immutable bytes before parser-delimited inert prolog elision in
a temporary buffer. ElementTree strictly parses that buffer. No source is changed.
This is a local parser policy, not a general XML security certification.
"""
from pathlib import Path
import hashlib
import re
from xml.parsers import expat
import xml.etree.ElementTree as ET

MAX_BYTES = 50_000_000
MAX_NODES = 100_000
MAX_DEPTH = 128
MAX_TEXT = 20_000_000
MAX_ATTRIBUTES = 256
MAX_ATTRIBUTE_TEXT = 2_000_000
MAX_NAME_TEXT = 2_000_000
MAX_NAMESPACE_URI = 4096
POLICY_VERSION = 'bounded-inert-jats/v2'

_JATS_PUBLIC = re.compile(
    r'-//NLM//DTD JATS \(Z39\.96\) Journal '
    r'(Archiving and Interchange|Publishing|Article Authoring) DTD'
    r'(?: with MathML([23]))? v(1\.[0-4]) [0-9]{8}//EN')
_JATS_FAMILIES = {'Archiving and Interchange': ('archivearticle', 'archiving'),
                  'Publishing': ('journalpublishing', 'publishing'),
                  'Article Authoring': ('articleauthoring', 'articleauthoring')}


def _inert_jats(name, system, public, internal):
    """Validate parser-decoded identifiers, never normalize or fetch a prolog."""
    if name != 'article' or internal or not isinstance(public, str) or len(public) > 256:
        return False
    match = _JATS_PUBLIC.fullmatch(public)
    if not match:
        return False
    family, mathml, version = match.groups()
    basename, directory = _JATS_FAMILIES[family]
    filename = 'JATS-' + basename + version.replace('.', '-') + (('-mathml' + mathml) if mathml else '') + '.dtd'
    return system in {filename, 'https://jats.nlm.nih.gov/' + directory + '/' + version + '/' + filename}


class XmlPolicyError(ValueError):
    pass


def read_xml(path: Path) -> bytes:
    with path.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise XmlPolicyError('XML exceeds byte limit')
    return raw


def _parse_buffer(raw, forbidden):
    """Called only after complete validation; obtain syntax spans from Expat.

    The default handler reports the actual DOCTYPE opening token, not comment,
    PI or CDATA text. EndDoctype reports its closing delimiter's byte offset.
    Supported encodings use one or two bytes for that delimiter. This removes
    exactly one validated declaration without decoding/re-encoding any content.
    """
    parser = expat.ParserCreate()
    span = [None, None]

    def token(value):
        if value == '<!DOCTYPE':
            if span[0] is not None:
                forbidden()
            span[0] = parser.CurrentByteIndex

    def finish():
        index = parser.CurrentByteIndex
        unit = 2 if raw[index:index+2] in (b'>\x00', b'\x00>') else 1
        if raw[index:index+unit] not in (b'>', b'>\x00', b'\x00>'):
            forbidden()
        span[1] = index + unit

    parser.DefaultHandler, parser.EndDoctypeDeclHandler = token, finish
    parser.StartElementHandler = lambda *args: None
    parser.EndElementHandler = lambda *args: None
    parser.CharacterDataHandler = lambda *args: None
    parser.CommentHandler = lambda *args: None
    parser.ProcessingInstructionHandler = lambda *args: None
    parser.EntityDeclHandler = parser.ExternalEntityRefHandler = parser.SkippedEntityHandler = forbidden
    parser.UseForeignDTD(False)
    if not parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER):
        forbidden()
    parser.Parse(raw, True)
    start, end = span
    if start is None or end is None or not 0 <= start < end <= len(raw):
        forbidden()
    return raw[:start] + raw[end:]


def parse_xml(raw: bytes, *, with_provenance=False):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise XmlPolicyError('XML requires bytes within the byte limit')
    parser = expat.ParserCreate(namespace_separator='}')
    depth = nodes = characters = attributes = names = 0
    has_doctype = False

    def forbidden(*args):
        raise XmlPolicyError('XML DTD/entity declarations and external references are refused')

    def doctype(name, system, public, internal):
        nonlocal has_doctype
        if (has_doctype or not _inert_jats(name, system, public, internal)
                or expat.version_info < (2, 6, 0)):
            forbidden()
        has_doctype = True

    def start(name, attrs):
        nonlocal depth, nodes, attributes, names
        depth += 1
        nodes += 1
        if has_doctype and depth == 1 and name.rsplit('}', 1)[-1] != 'article':
            forbidden()
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise XmlPolicyError('XML exceeds depth/node limit')
        attributes += sum(len(key) + len(value) for key, value in attrs.items())
        if len(attrs) > MAX_ATTRIBUTES or attributes > MAX_ATTRIBUTE_TEXT:
            raise XmlPolicyError('XML exceeds attribute limit')
        names += len(name) + sum(map(len, attrs))
        if names > MAX_NAME_TEXT:
            raise XmlPolicyError('XML exceeds expanded-name limit')

    def namespace(prefix, uri):
        if uri is not None and len(uri) > MAX_NAMESPACE_URI:
            raise XmlPolicyError('XML exceeds namespace limit')

    def end(name):
        nonlocal depth
        depth -= 1

    def data(value):
        nonlocal characters
        characters += len(value)
        if characters > MAX_TEXT:
            raise XmlPolicyError('XML exceeds character limit')

    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.SkippedEntityHandler = forbidden
    parser.ElementDeclHandler = forbidden
    parser.AttlistDeclHandler = forbidden
    parser.NotationDeclHandler = forbidden
    parser.UnparsedEntityDeclHandler = forbidden
    parser.UseForeignDTD(False)
    if not parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER):
        raise XmlPolicyError('XML parameter-entity processing cannot be disabled')
    parser.StartElementHandler = start
    parser.StartNamespaceDeclHandler = namespace
    parser.EndElementHandler = end
    parser.CharacterDataHandler = data
    try:
        parser.Parse(raw, True)
        buffer = _parse_buffer(raw, forbidden) if has_doctype else raw
        # No external declaration remains: undefined entities in attributes
        # cannot be silently omitted by either parser's unread-DTD behavior.
        root = ET.fromstring(buffer)
        if with_provenance:
            return root, {'xml_parse_input_sha256': 'sha256:' + hashlib.sha256(buffer).hexdigest(),
                          'xml_parse_transformation': 'expat-delimited-inert-doctype-elision/v1' if has_doctype else 'none'}
        return root
    except (expat.ExpatError, ET.ParseError, LookupError, ValueError) as exc:
        if isinstance(exc, XmlPolicyError):
            raise
        # No source text, remote URI or arbitrary exception payload in errors.
        raise XmlPolicyError('invalid or unsupported XML') from exc
