"""Bounded read-only evidence diagnostics for an explicitly supplied project.

Run with an existing standalone CorpusTrail Python installation. No downloads,
acquisition calls, database writes, migrations or document-text exports occur.
The structural inventory is diagnostic only: it never bypasses scientific trust.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
from xml.parsers import expat

from corpustrail._internal.database import connection
from corpustrail._internal.values import ContractError, confined, digest_bytes, sha256
from corpustrail._internal.xml_safety import MAX_BYTES, MAX_DEPTH, MAX_NODES, MAX_TEXT, POLICY_VERSION, XmlPolicyError, parse_xml
from corpustrail.application.project_use import acquire_project_use
from corpustrail.evidence.service import _document_ids
from corpustrail.identity import Identifier
from corpustrail.project import Project

SCHEMA = 'corpustrail-evidence-diagnostic/v1'
XML_ERRORS = {
    'XML requires bytes within the byte limit': 'byte_limit',
    'XML DTD/entity declarations and external references are refused': 'dtd_or_entity_refused',
    'XML exceeds depth/node limit': 'depth_or_node_limit',
    'XML exceeds character limit': 'text_limit',
    'invalid or unsupported XML': 'malformed_or_unsupported_xml',
}


class InventoryLimit(ValueError):
    pass


def inventory(raw, expected):
    """Expat token inventory: no tree, DTD loading or entity declarations.

    A DOCTYPE can be *observed*, without fetching/validating its external subset.
    Entity declarations/references and excessive resources abort the inventory.
    This is NOT the authoritative parser, never strips XML, and confers no trust.
    """
    result = {'well_formed_without_external_loading': None, 'doctype_present': False,
              'doctype_external_subset': False, 'entity_declaration_present': False,
              'external_entity_reference': False, 'unresolved_entity_reference': False, 'root_is_article': False,
              'root_kind': None, 'article_body_elements_any_depth': 0, 'article_body_text_characters_any_depth': 0,
              'front_elements': 0, 'body_elements': 0, 'body_text_characters': 0,
              'expected_identifiers_present': [], 'inventory_complete': False}
    parser = expat.ParserCreate(namespace_separator='|')
    stack, identifier_text, count, characters = [], [], 0, 0
    current_scheme, body_nesting = None, 0

    def start(name, attrs):
        nonlocal count, current_scheme, body_nesting
        stack.append(name.rsplit('|', 1)[-1]); count += 1
        if len(stack) > MAX_DEPTH or count > MAX_NODES:
            raise InventoryLimit()
        if len(stack) == 1:
            result['root_is_article'] = stack[0] == 'article'
            result['root_kind'] = stack[0] if stack[0] in {'article','article-set','pmc-articleset','error','html','collection','TEI'} else 'other'
        if stack == ['article', 'front']: result['front_elements'] += 1
        if stack == ['article', 'body']: result['body_elements'] += 1
        if stack[-2:] == ['article','body']:
            result['article_body_elements_any_depth'] += 1
            body_nesting += 1
        if stack == ['article', 'front', 'article-meta', 'article-id']:
            current_scheme = {'doi': 'doi', 'pmid': 'pmid', 'pmc': 'pmcid', 'pmcid': 'pmcid'}.get(attrs.get('pub-id-type'))
            identifier_text.clear()

    def end(name):
        nonlocal current_scheme, body_nesting
        if stack == ['article', 'front', 'article-meta', 'article-id'] and current_scheme:
            value = ''.join(identifier_text).strip()
            if current_scheme == 'pmcid' and value.isdigit(): value = 'PMC' + value
            try: item = Identifier(current_scheme, value).normalized()
            except ContractError: item = None
            if item in expected and item not in result['expected_identifiers_present']:
                result['expected_identifiers_present'].append(item)
            current_scheme = None
        if stack[-2:] == ['article','body']: body_nesting -= 1
        stack.pop()

    def text(value):
        nonlocal characters
        characters += len(value)
        if characters > MAX_TEXT: raise InventoryLimit()
        if stack[:2] == ['article', 'body']:
            result['body_text_characters'] += len(value.strip())
        if body_nesting:
            result['article_body_text_characters_any_depth'] += len(value.strip())
        if current_scheme:
            identifier_text.append(value)
            if sum(map(len, identifier_text)) > 300: raise InventoryLimit()

    def doctype(name, system, public, internal):
        result['doctype_present'] = True
        result['doctype_external_subset'] = bool(system or public)

    def entity(*args):
        result['entity_declaration_present'] = True
        raise InventoryLimit()

    def external(*args):
        result['external_entity_reference'] = True
        raise InventoryLimit()

    def skipped(*args):
        result['unresolved_entity_reference'] = True
        raise InventoryLimit()

    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler, parser.StartDoctypeDeclHandler = text, doctype
    parser.EntityDeclHandler, parser.ExternalEntityRefHandler = entity, external
    parser.SkippedEntityHandler = skipped
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        result['inventory_error'] = 'byte_limit'; return result
    try:
        parser.Parse(raw, True)
        result['well_formed_without_external_loading'] = True
        result['inventory_complete'] = True
    except InventoryLimit:
        result['inventory_error'] = 'refused_entity_or_resource_limit'
    except (expat.ExpatError, ValueError, LookupError):
        result['well_formed_without_external_loading'] = False
        result['inventory_error'] = 'malformed_or_unsupported_xml'
    return result


def analyze_bytes(raw, *, public_identifiers=()):
    """Only explicitly public expected IDs can appear in the sanitized output."""
    expected = {Identifier(s, v).normalized() for s, v in public_identifiers}
    hint = 'unclassified'
    for prefix, label in ((b'\x1f\x8b', 'gzip'), (b'PK\x03\x04', 'zip'), (b'%PDF', 'pdf'),
                          (b'\xff\xfe\x00\x00', 'utf32_le_bom'), (b'\x00\x00\xfe\xff', 'utf32_be_bom'),
                          (b'\xff\xfe', 'utf16_le_bom'), (b'\xfe\xff', 'utf16_be_bom'), (b'\xef\xbb\xbf', 'utf8_bom')):
        if raw.startswith(prefix): hint = label; break
    result = {'response_bytes': len(raw), 'response_sha256': hashlib.sha256(raw).hexdigest(),
              'byte_signature_hint': hint,  # Signature only; no decoding/decompression or trust claim.
              'xml_policy': POLICY_VERSION, 'structure': inventory(raw, expected)}
    try:
        parse_xml(raw)
    except XmlPolicyError as exc:
        result['content_validation'] = {'passed': False, 'stage': 'xml_policy',
                                        'reason': XML_ERRORS.get(str(exc), 'xml_policy_refusal')}
        cause = exc.__cause__
        if type(getattr(cause, 'code', None)) is int:
            result['content_validation']['parser_error_code'] = cause.code
            # Numeric location, not exception text containing scientific content.
            for name in ('lineno', 'offset'):
                value = getattr(cause, name, None)
                if type(value) is int: result['content_validation'][name] = value
        return result
    try:
        identifiers = _document_ids(raw)
        result['content_validation'] = {'passed': True, 'stage': 'article_identifiers',
            'identifier_counts': {s: sum(s == scheme for scheme, _ in identifiers) for s in ('doi', 'pmid', 'pmcid')}}
    except ContractError as exc:
        result['content_validation'] = {'passed': False, 'stage': 'article_identifiers',
            'reason': 'not_an_article' if str(exc) == 'structured source is not an article' else 'invalid_article_identifier'}
    return result


def inspect_project(project_root, pmcid):
    _, pmcid = Identifier('pmcid', pmcid).normalized()
    # Shared lease protects cooperating processes; no claim about external writers.
    with acquire_project_use(Path(project_root)):
        project = Project.open(project_root)
        paper = project.identities.exact_owner(Identifier('pmcid', pmcid))
        if paper is None: raise ContractError('no verified PMCID owner')
        records, offset = [], 0
        while offset is not None and offset < 1000:
            page = project.evidence.acquisition_page(paper, offset=offset, limit=100)
            records.extend(page['items']); offset = page['next_offset']
        failures = [r for r in records if r['kind'] == 'representation'
            and r['payload'].get('artifact_validity') == 'invalid'
            and r['payload'].get('resolver') == 'europepmc']
        result = {'schema': SCHEMA, 'pmcid': pmcid, 'read_only': True, 'network_requests': 0,
            'runtime': {'python': platform.python_version(), 'system': platform.system(),
                        'machine': platform.machine(), 'expat': expat.EXPAT_VERSION,
                        'corpustrail': importlib.metadata.version('corpus-trail')},
            'history_scan_limit': 1000, 'history_scan_truncated': offset is not None,
            'failed_representations_in_scanned_history': len(failures),
            'attempts_reported': min(len(failures), 5), 'attempts_truncated': len(failures) > 5, 'attempts': [],
            'notice': 'Stored trust/history are unchanged. This diagnostic does not acquire or verify new evidence.'}
        for record in failures[:5]:
            payload = record['payload']; sha = payload['artifact_sha256']; sha256(sha)
            # Fixed read-only registry query, confinement and bounded hash verification.
            with connection(project.database_path) as db:
                row = db.execute('SELECT f.relative_path,a.byte_size FROM ct_artifact_files f JOIN raw_artifacts a ON a.sha256=f.sha256 WHERE f.sha256=?', (sha,)).fetchone()
            if row is None or not 0 <= row['byte_size'] <= MAX_BYTES:
                raise ContractError('missing or oversized preserved artifact')
            path = confined(project.root, row['relative_path'])
            with path.open('rb') as handle: raw = handle.read(MAX_BYTES + 1)
            if len(raw) != row['byte_size'] or digest_bytes(raw) != sha:
                raise ContractError('artifact integrity differs')
            attempt = {'stored_artifact_validity': 'invalid', 'stored_trusted': payload.get('trusted') is True,
                'observed_content_type': 'not preserved by original acquisition records',
                **analyze_bytes(raw, public_identifiers=(('pmcid', pmcid),))}
            network = next((r for r in records if r['kind'] == 'acquisition_result'
                and r['scope_id'] == payload.get('resolution_id') and r['source_sha256'] == sha), None)
            status = network['payload'].get('http_status') if network else None
            attempt['http_status'] = status if type(status) is int and 100 <= status <= 599 else None
            result['attempts'].append(attempt)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--pmcid', required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_project(args.project, args.pmcid)
    except Exception:
        # Never emit exceptions that might contain paths, config values or content.
        print(json.dumps({'schema': SCHEMA, 'read_only': True, 'network_requests': 0,
                          'error': 'Project, verified identifier, provenance or artifact could not be safely inspected.'}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
