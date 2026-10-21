"""Append-only assessment records and content-addressed input/output bytes."""
import json

from corpustrail._internal.values import ContractError, canonical, content_hash, digest_bytes, identifier, timestamp
from corpustrail.references.contracts import exact_id


def ready(db):
    return db.execute("SELECT 1 FROM schema_migrations WHERE version=40").fetchone() is not None


def require(db):
    if not ready(db): raise ContractError('classification requires an explicit backed-up project upgrade')


def put_blob(db, body):
    digest = digest_bytes(body)
    existing = db.execute('SELECT body FROM ct_classifier_blobs WHERE sha256=?', (digest,)).fetchone()
    if existing is None: db.execute('INSERT INTO ct_classifier_blobs VALUES (?,?)', (digest, body))
    elif bytes(existing[0]) != body: raise ContractError('assessment artifact integrity changed')
    return digest


def blob(db, digest):
    row = db.execute('SELECT body FROM ct_classifier_blobs WHERE sha256=?', (digest,)).fetchone()
    if row is None or digest_bytes(bytes(row[0])) != digest:
        raise ContractError('frozen assessment input/output integrity changed')
    return bytes(row[0])


def plan(db, pid):
    require(db); exact_id(pid, 'assessment-plan')
    row = db.execute('SELECT * FROM ct_classifier_plans WHERE plan_id=?', (pid,)).fetchone()
    if row is None: raise ContractError('assessment plan is not in this project')
    data = json.loads(row['payload_json'])
    if (identifier('assessment-plan', data) != pid or row['request_id'] != data['request_id'] or row['request_sha256'] != data['command_sha256']
            or any(row[k] != data[k] for k in ('population_version_id', 'reference_version_id', 'config_event_id'))):
        raise ContractError('assessment plan integrity changed')
    return data


def run(db, rid):
    require(db); exact_id(rid, 'assessment-run')
    row = db.execute('SELECT * FROM ct_classifier_runs WHERE run_id=?', (rid,)).fetchone()
    if row is None: raise ContractError('assessment run is not in this project')
    data = json.loads(row['payload_json'])
    if identifier('assessment-run', data) != rid or row['plan_id'] != data['plan_id'] or row['request_id'] != data['request_id'] or row['parent_run_id'] != data['parent_run_id']:
        raise ContractError('assessment run integrity changed')
    return data


def event(db, rid):
    row = db.execute('SELECT * FROM ct_classifier_run_events WHERE run_id=? ORDER BY revision DESC LIMIT 1', (rid,)).fetchone()
    if row is None: raise ContractError('assessment run lifecycle is missing')
    data = json.loads(row['payload_json'])
    if content_hash(data) != row['content_sha256'] or data['revision'] != row['revision'] or data['run_id'] != rid:
        raise ContractError('assessment lifecycle integrity changed')
    return data, row['content_sha256']


def append_event(db, rid, status, at, *, expected=None, actor=None):
    timestamp(at)
    if status not in {'planned', 'running', 'completed', 'partial', 'failed', 'interrupted'}:
        raise ContractError('unknown classifier lifecycle state')
    prior = db.execute('SELECT 1 FROM ct_classifier_run_events WHERE run_id=?', (rid,)).fetchone()
    old, old_sha = event(db, rid) if prior else (None, None)
    if old_sha != expected: raise ContractError('stale assessment lifecycle revision; inspect before continuing')
    data = {'run_id': rid, 'revision': old['revision'] + 1 if old else 1,
            'previous_sha256': old_sha, 'status': status, 'created_at': at, 'actor': actor}
    digest = content_hash(data)
    db.execute('INSERT INTO ct_classifier_run_events VALUES (?,?,?,?)', (rid, data['revision'], canonical(data), digest))
    return digest


def items(db, pid, *, offset=0, limit=20):
    head = plan(db, pid)
    rows = db.execute('SELECT * FROM ct_classifier_inputs WHERE plan_id=? AND position>=? AND position<? ORDER BY position',
                      (pid, offset, offset + limit)).fetchall()
    values = []
    for row in rows:
        value = json.loads(row['payload_json'])
        if content_hash(value) != row['content_sha256'] or value['paper_id'] != row['paper_id'] or value['input_blob_sha256'] != row['input_blob_sha256']:
            raise ContractError('assessment candidate input integrity changed')
        values.append(value)
    for chunk in range(offset // 100, (min(offset + limit, head['candidate_count']) + 99) // 100):
        frozen = [r[0] for r in db.execute('SELECT content_sha256 FROM ct_classifier_inputs WHERE plan_id=? AND position>=? AND position<? ORDER BY position',
                  (pid, chunk * 100, (chunk + 1) * 100))]
        if content_hash(frozen) != head['input_chunk_hashes'][chunk]: raise ContractError('assessment candidate manifest changed')
    return values


def result(db, rid, position):
    row = db.execute('SELECT * FROM ct_classifier_results WHERE run_id=? AND position=?', (rid, position)).fetchone()
    if row is None: return None
    data = json.loads(row['payload_json'])
    if (identifier('assessment' if row['kind'] == 'assessment' else 'assessment-failure', data) != row['result_id']
            or data['run_id'] != rid or data['position'] != position or data['kind'] != row['kind']
            or data['paper_id'] != row['paper_id'] or data.get('assessment', {}).get('outcome') != row['outcome']):
        raise ContractError('immutable assessment/failure integrity changed')
    blob(db, data['response_blob_sha256'])
    return {'result_id': row['result_id'], **data}
