"""Project-bound human training eligibility and immutable provenance artifacts."""

from datetime import datetime
import json

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, now, text, timestamp
from corpustrail.curation.service import _history
from . import _algorithm as algorithm


def _time(value):
    timestamp(value)
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _get(db, artifact_id, kind=None):
    row = db.execute('SELECT * FROM ct_priority_artifacts WHERE artifact_id=?', (artifact_id,)).fetchone()
    if row is None:
        raise KeyError(artifact_id)
    value = json.loads(row['payload_json'])
    algorithm.check(value, kind or row['kind'])
    if content_hash(value) != row['content_sha256'] or value['artifact_id'] != row['artifact_id'] or value['kind'] != row['kind']:
        raise ContractError('priority artifact hash mismatch')
    return value


def _put(db, value, created_at, config_id):
    algorithm.check(value, value['kind'])
    existing = db.execute('SELECT 1 FROM ct_priority_artifacts WHERE artifact_id=?', (value['artifact_id'],)).fetchone()
    if existing:
        if _get(db, value['artifact_id']) != value:
            raise ContractError('priority artifact collision')
    else:
        db.execute('INSERT INTO ct_priority_artifacts VALUES (?,?,?,?,?,?)',
                   (value['artifact_id'], value['kind'], canonical(value), content_hash(value), config_id, created_at))
    return value['artifact_id']


class PrioritizationService:
    def __init__(self, project):
        self.project = project

    def inputs(self, paper_ids=None):
        ids = list(self.project.identities.papers() if paper_ids is None else paper_ids)
        if len(ids) != len(set(ids)) or not ids:
            raise ContractError('population must be nonempty and unique')
        result = []
        for paper_id in ids:
            metadata = self.project.discovery.metadata(paper_id)
            status = self.project.evidence.status(paper_id)
            result.append(algorithm.candidate({**metadata['fields'], 'paper_id': paper_id,
                'evidence_availability': {'abstract_available': bool(metadata['fields']['abstract']),
                    'verified_full_text_available': bool(status['verified_structured_text']),
                    'representation': status['best_available']}}))
        return result

    def snapshot(self, *, label_cutoff, created_at=None, parent_snapshot_id=None):
        # Reserve a consistent feature/label snapshot; nested service reads are read-only.
        with connection(self.project.database_path, write=True) as db:
            return self._snapshot(db, label_cutoff=label_cutoff, created_at=created_at,
                                  parent_snapshot_id=parent_snapshot_id)

    def _snapshot(self, db, *, label_cutoff, created_at=None, parent_snapshot_id=None):
        """Only scoped, explicitly authorized human decisions available by cutoff.

        Features are frozen NOW, not retroactively assumed available at label cutoff.
        Snapshot provenance explicitly records this distinction.
        """
        created_at = created_at or now()
        if _time(label_cutoff) > _time(created_at):
            raise ContractError('label cutoff cannot be in the future of snapshot creation')
        inputs = {x['paper_id']: x for x in self.inputs()}
        from corpustrail import __version__
        feature_sources = {pid: {
            'bibliographic_selection': self.project.discovery.metadata(pid),
            'evidence_representations': self.project.evidence.representations(pid)} for pid in inputs}
        rows = []
        excluded = []
        config_id, config = latest_config(db)
        if parent_snapshot_id:
            _get(db, parent_snapshot_id, 'training_snapshot')
        for paper_id in sorted(inputs):
            eligible = []
            for event in _history(db, paper_id):
                receipt = db.execute('SELECT recorded_at FROM ct_review_availability WHERE event_id=?',
                                     (event['event_id'],)).fetchone()
                if (event['producer_type'] == 'human' and event['authority_state'] == 'human_authorized'
                        and event['policy_id'] == config['review']['policy_id']
                        and receipt and _time(receipt[0]) <= _time(label_cutoff)
                        and _time(event['created_at']) <= _time(label_cutoff)):
                    eligible.append((event, receipt[0]))
            if not eligible or eligible[-1][0]['state'] == 'unresolved':
                excluded.append({'paper_id': paper_id, 'reason': 'no eligible resolved human state at cutoff'})
                continue
            event, available = eligible[-1]
            rows.append({**inputs[paper_id], 'label': {'included': 'include', 'excluded': 'exclude',
                'insufficient_evidence': 'insufficient_evidence'}[event['state']],
                'labelled_at': event['created_at'], 'label_available_by': available,
                'timestamp_basis': 'immutable database availability receipt',
                'provenance_class': 'authoritative_human_judgment', 'relevance_concept': algorithm.CONCEPT,
                'source_artifact': 'ct_review_events', 'source_sha256': content_hash({k:v for k,v in event.items() if k!='event_id'}),
                'source_record': event['event_id']})
        value = algorithm.training_snapshot(project_id=config['project_id'], rows=rows,
            label_cutoff=label_cutoff, eligibility_policy=config['review']['policy_id'],
            parent_snapshot_id=parent_snapshot_id,
            input_provenance={'features_frozen_at': created_at, 'feature_population': inputs,
                'feature_sources': feature_sources, 'software_version': __version__,
                'feature_policy': 'canonical title and abstract at snapshot creation, not historical reconstruction',
                'config_event_id': config_id, 'excluded': excluded})
        if latest_config(db)[0] != config_id:
            raise ContractError('configuration changed during snapshot preparation')
        _put(db, value, created_at, config_id)
        return value

    def artifact(self, artifact_id):
        with connection(self.project.database_path) as db:
            return _get(db, artifact_id)

    def train(self, snapshot_id, *, adapter=None, parent_model_id=None, created_at=None):
        created_at = created_at or now()
        adapter = adapter or algorithm.TfidfLogistic()
        snapshot = self.artifact(snapshot_id)
        algorithm.check(snapshot, 'training_snapshot')
        if _time(created_at) < _time(snapshot['input_provenance']['features_frozen_at']):
            raise ContractError('model creation cannot predate its training feature snapshot')
        if parent_model_id:
            algorithm.check(self.artifact(parent_model_id), 'model')
        value = adapter.fit(snapshot, purpose='operational', parent_model_id=parent_model_id)
        algorithm.check(value, 'model')
        if (value.get('non_authoritative') is not True or value['training_snapshot_id'] != snapshot_id
                or value['training_snapshot'] != snapshot or value['purpose'] != 'operational'
                or value['parent_model_id'] != parent_model_id
                or (value['method'],value['method_version']) != (adapter.method,adapter.version)):
            raise ContractError('adapter must preserve non-authority and exact training lineage')
        with connection(self.project.database_path, write=True) as db:
            _put(db, value, created_at, latest_config(db)[0])
        return value

    def rank(self, model_id, *, run_id, paper_ids=None, adapter=None, created_at=None, previous_run_id=None):
        text(run_id, 'ranking run ID')
        created_at = created_at or now()
        adapter = adapter or algorithm.TfidfLogistic()
        model = self.artifact(model_id)
        from corpustrail import __version__
        with connection(self.project.database_path, write=True) as db:
            config_id, _ = latest_config(db)
            model_time = db.execute('SELECT created_at FROM ct_priority_artifacts WHERE artifact_id=?',(model_id,)).fetchone()[0]
            if _time(created_at) < _time(model_time):
                raise ContractError('ranking cannot predate its registered model')
            rows = self.inputs(paper_ids)
            provenance = {'created_at':created_at,'config_event_id':config_id,'software_version':__version__,
                'selection_rule':'all canonical papers' if paper_ids is None else 'explicit canonical paper ID population',
                'paper_ids':[x['paper_id'] for x in rows],
                'feature_sources':{x['paper_id']:{'metadata':self.project.discovery.metadata(x['paper_id']),
                    'representations':self.project.evidence.representations(x['paper_id'])} for x in rows}}
        value = algorithm.rank(adapter, model, rows, created_at=created_at,
            population_source_sha256=content_hash(rows), previous_run_id=previous_run_id)
        with connection(self.project.database_path, write=True) as db:
            if latest_config(db)[0] != config_id:
                raise ContractError('configuration changed during ranking')
            if previous_run_id:
                if not db.execute('SELECT 1 FROM ct_priority_runs WHERE run_id=?', (previous_run_id,)).fetchone():
                    raise ContractError('previous ranking run is not registered')
            existing = db.execute('SELECT artifact_id FROM ct_priority_runs WHERE run_id=?', (run_id,)).fetchone()
            if existing and existing[0] != value['artifact_id']:
                raise ContractError('ranking run exists; reranking requires a new run ID')
            _put(db, value, created_at, config_id)
            if not existing:
                db.execute('INSERT INTO ct_priority_runs VALUES (?,?,?,?,?,?)',
                           (run_id, value['artifact_id'], model_id, previous_run_id,
                            canonical(provenance),content_hash(provenance)))
        return value

    def run(self, run_id):
        with connection(self.project.database_path) as db:
            row = db.execute('SELECT artifact_id FROM ct_priority_runs WHERE run_id=?', (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return _get(db, row[0], 'ranking')

    def run_provenance(self, run_id):
        with connection(self.project.database_path) as db:
            row=db.execute('SELECT provenance_json,provenance_sha256 FROM ct_priority_runs WHERE run_id=?',(run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            value=json.loads(row[0])
            if content_hash(value)!=row[1]:
                raise ContractError('ranking provenance hash mismatch')
            return value
