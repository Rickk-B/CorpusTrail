"""Encoding-aware, bounded XML policy. No DTDs, entities or external loading.

Expat validates immutable bytes before ElementTree builds the same input. Its
markup callbacks operate after XML encoding detection, unlike ASCII byte scans.
This is a local parser policy, not a general XML security certification.
"""
from pathlib import Path
from xml.parsers import expat
import xml.etree.ElementTree as ET

MAX_BYTES = 50_000_000
MAX_NODES = 100_000
MAX_DEPTH = 128
MAX_TEXT = 20_000_000
POLICY_VERSION = 'bounded-no-dtd/v1'


class XmlPolicyError(ValueError):
    pass


def read_xml(path: Path) -> bytes:
    with path.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise XmlPolicyError('XML exceeds byte limit')
    return raw


def parse_xml(raw: bytes):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise XmlPolicyError('XML requires bytes within the byte limit')
    parser = expat.ParserCreate()
    depth = nodes = characters = 0

    def forbidden(*args):
        raise XmlPolicyError('XML DTD/entity declarations and external references are refused')

    def start(name, attrs):
        nonlocal depth, nodes
        depth += 1
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise XmlPolicyError('XML exceeds depth/node limit')

    def end(name):
        nonlocal depth
        depth -= 1

    def data(value):
        nonlocal characters
        characters += len(value)
        if characters > MAX_TEXT:
            raise XmlPolicyError('XML exceeds character limit')

    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = data
    try:
        parser.Parse(raw, True)
        return ET.fromstring(raw)
    except (expat.ExpatError, ET.ParseError, LookupError, ValueError) as exc:
        if isinstance(exc, XmlPolicyError):
            raise
        # No source text, remote URI or arbitrary exception payload in errors.
        raise XmlPolicyError('invalid or unsupported XML') from exc
