"""Reference existing evidence; assertion or validation never changes document trust."""
import json
from corpustrail._internal.values import ContractError, content_hash, identifier, confined, digest_bytes


def resolve_reference(project, con, payload):
    p = payload
    if p['paper_id'] is not None and not con.execute('SELECT 1 FROM paper_entities WHERE paper_id=?', (p['paper_id'],)).fetchone():
        raise ContractError('unknown canonical paper')
    if any(p.get(k) is not None for k in ('document_artifact_id','text_artifact_id','passage_id')):
        raise ContractError('historical artifact IDs need an explicit adapter; use standalone evidence_reference')
    ref = p.get('evidence_reference')
    if ref is None:
        return {'reference_available':False, 'trusted':False, 'reason':'precise evidence unavailable'}
    if not isinstance(ref, dict):
        raise ContractError('evidence_reference must be a structured reference')
    kind = ref.get('kind')
    if kind == 'unavailable':
        if not ref.get('reason'):
            raise ContractError('unavailable evidence requires a reason')
        return {'reference_available':False, 'trusted':False, 'reason':ref['reason']}
    if kind == 'external':
        if not ref.get('uri') or p['evidence_representation'] not in ('imported_metadata','source_record'):
            raise ContractError('external references must explicitly identify imported/source metadata')
        return {'reference_available':True, 'trusted':False, 'validity':'unverified_external', 'reference':ref}
    if kind == 'bibliographic_observation':
        row = con.execute('SELECT * FROM ct_paper_observations WHERE observation_id=?', (ref.get('observation_id'),)).fetchone()
        if not row or row['paper_id'] != p['paper_id']:
            raise ContractError('bibliographic evidence/paper mismatch')
        body = json.loads(row['payload_json'])
        field = ref.get('field')
        if field is not None and not body['record'].get(field):
            raise ContractError('missing evidence field remains unavailable')
        if p['evidence_representation'] == 'abstract' and not body['record'].get('abstract'):
            raise ContractError('abstract evidence absent')
        if p['evidence_representation'] not in ('metadata','abstract','source_record'):
            raise ContractError('bibliographic record is not full-text evidence')
        source = body['source']
        sha = source['source_sha256']
        trusted = source['identity_status'] == 'verified'
        validity = 'verified' if trusted else 'unverified'
        depth = p['evidence_representation']
    elif kind == 'representation':
        row = con.execute("SELECT * FROM ct_pipeline_events WHERE event_id=? AND kind='representation'", (ref.get('event_id'),)).fetchone()
        if not row or row['paper_id'] != p['paper_id']:
            raise ContractError('representation/paper mismatch')
        envelope = json.loads(row['payload_json'])
        if (identifier('pipeline',envelope)!=row['event_id'] or content_hash(envelope)!=row['content_sha256']
                or envelope['paper_id']!=p['paper_id']):
            raise ContractError('representation provenance corrupt')
        body = envelope['payload']
        if p['evidence_representation'] != body['representation']:
            raise ContractError('evidence representation mismatch')
        sha = body['artifact_sha256']
        trusted = bool(body['trusted'])
        validity = body['artifact_validity']
        depth = body.get('evidence_depth')
        file = con.execute('SELECT relative_path FROM ct_artifact_files WHERE sha256=?', (sha,)).fetchone()
        if file is None or digest_bytes(confined(project.root,file[0]).read_bytes())!=sha:
            raise ContractError('referenced representation bytes unavailable or changed')
    else:
        raise ContractError('unknown evidence reference kind')
    if p['source'].get('artifact_sha256') not in (None, sha):
        raise ContractError('source/evidence hash mismatch')
    return {'reference_available':True, 'trusted':trusted, 'artifact_validity':validity,
            'artifact_sha256':sha, 'reference':ref, 'evidence_depth':depth}
