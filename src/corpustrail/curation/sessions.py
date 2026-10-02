"""Immutable evidence populations and append-only autosaved review drafts.

Drafts are not scientific decisions. Only explicit commit calls the shared review
ledger. Browser views use a bibliographic/evidence allowlist, never raw provenance.
"""

from copy import deepcopy
import json

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.pipeline import artifact
from corpustrail._internal.values import ContractError, canonical, content_hash, identifier, now, text, timestamp
from .service import EvidenceBasis, ReviewEvent, ReviewPlan, _history


def _load(db, session_id):
    row = db.execute('SELECT * FROM ct_review_sessions WHERE session_id=?', (session_id,)).fetchone()
    if row is None:
        raise KeyError(session_id)
    packet = json.loads(row['payload_json'])
    if content_hash(packet) != row['content_sha256'] or packet['session_id'] != session_id:
        raise ContractError('session population hash mismatch')
    state = {'index': 0, 'order': [x['paper_id'] for x in packet['papers']], 'ordering': 'original',
             'ranking_run_id': None, 'drafts': {}, 'opened': [], 'committed': {},
             'heads': deepcopy(packet['history_hashes'])}
    revision = None
    for event in db.execute('SELECT * FROM ct_review_session_events WHERE session_id=? ORDER BY sequence', (session_id,)):
        payload = json.loads(event['payload_json'])
        if (content_hash(payload) != event['content_sha256'] or identifier('session-event', payload) != event['event_id']
                or event['previous_event_id'] != revision or payload['previous_event_id'] != revision
                or payload['session_id'] != session_id):
            raise ContractError('session event lineage mismatch')
        if 'state' in payload:  # Early development snapshots remain readable.
            state = payload['state']
        else:
            for key,value in payload['delta'].items():
                if key in {'drafts','committed','heads'}:
                    state[key].update(value)
                elif key == 'opened_add':
                    state['opened'].extend(x for x in value if x not in state['opened'])
                elif key in {'index','order','ordering','ranking_run_id'}:
                    state[key] = value
                else:
                    raise ContractError('unsupported session delta field')
        revision = event['event_id']
    if set(state['order']) != {x['paper_id'] for x in packet['papers']} or len(state['order']) != len(packet['papers']):
        raise ContractError('session must preserve the entire population')
    return packet, deepcopy(state), revision, row['config_event_id']


def _append(db, session_id, state, previous, kind, prior_state):
    delta={}
    for key,value in state.items():
        if value == prior_state[key]:
            continue
        if key in {'drafts','committed','heads'}:
            delta[key]={k:v for k,v in value.items() if k not in prior_state[key] or prior_state[key][k]!=v}
        elif key == 'opened':
            delta['opened_add']=[x for x in value if x not in prior_state[key]]
        else:
            delta[key]=value
    payload = {'schema':'corpustrail-review-session-event/v1','session_id': session_id,
               'previous_event_id': previous, 'kind': kind, 'created_at': now(), 'delta': delta}
    event_id = identifier('session-event', payload)
    db.execute('INSERT INTO ct_review_session_events '
               '(event_id,session_id,previous_event_id,payload_json,content_sha256) VALUES (?,?,?,?,?)',
               (event_id, session_id, previous, canonical(payload), content_hash(payload)))
    return event_id


def _paper(packet, paper_id):
    return next(x for x in packet['papers'] if x['paper_id'] == paper_id)


def _draft(value):
    if not isinstance(value, dict) or set(value) - {'sufficiency', 'decision', 'review_extent', 'rationale', 'location'}:
        raise ContractError('invalid draft fields')
    result = {**{'sufficiency': None, 'decision': None, 'review_extent': None, 'rationale': '', 'location': None}, **value}
    for field, values in {'sufficiency': {None, 'sufficient', 'insufficient', 'undetermined'},
                          'decision': {None, 'included', 'excluded'},
                          'review_extent': {None, 'metadata', 'abstract', 'sections', 'full_document', 'none'}}.items():
        if result[field] not in values:
            raise ContractError('invalid ' + field)
    if result['sufficiency'] != 'sufficient' and result['decision'] is not None:
        raise ContractError('insufficient/undetermined evidence cannot have an inclusion/exclusion decision')
    if not isinstance(result['rationale'], str) or len(result['rationale']) > 20000:
        raise ContractError('invalid rationale')
    if result['location'] is not None:
        text(result['location'], 'evidence location')
    return result


def _event(packet, state, paper_id, draft, created_at):
    paper = _paper(packet, paper_id)
    extent = draft['review_extent'] or 'none'
    if extent not in paper['bases'] and extent != 'none':
        raise ContractError('requested evidence is unavailable in the frozen session')
    if extent in {'sections', 'full_document'} and paper_id not in state['opened']:
        raise ContractError('open the trusted document before attesting sections/full-paper review')
    sufficiency = draft['sufficiency']
    decision = draft['decision'] if sufficiency == 'sufficient' else {
        'insufficient': 'insufficient_evidence', 'undetermined': 'unresolved'}.get(sufficiency)
    bases = (EvidenceBasis(**{**paper['bases'][extent], 'location': draft['location']}),) if extent in paper['bases'] else ()
    return ReviewEvent(paper_id, decision, sufficiency, extent, draft['rationale'], packet['reviewer_id'],
                       created_at, bases, policy_id=packet['policy_id'], authority_state=packet['authority_state'],
                       supersedes=state['committed'].get(paper_id, packet['current_events'][paper_id])
                       if packet['authority_state'] == 'human_authorized' else None)


def _status(packet, state, paper_id):
    draft = state['drafts'].get(paper_id)
    if not draft or not any(x for x in draft.values()):
        return 'blank'
    try:
        _event(packet, state, paper_id, draft, packet['created_at']).validate()
    except (ContractError, TypeError):
        return 'partial'
    return 'insufficient' if draft['sufficiency'] == 'insufficient' else 'complete'


class SessionService:
    def __init__(self, project):
        self.project = project

    def prepare(self, session_id, *, reviewer_id, paper_ids=None, mode='method-blind',
                authority_state='non_authoritative', created_at=None):
        with connection(self.project.database_path, write=True) as db:
            self._prepare(db, session_id, reviewer_id=reviewer_id, paper_ids=paper_ids, mode=mode,
                          authority_state=authority_state, created_at=created_at)
        return self.view(session_id)

    def _prepare(self, db, session_id, *, reviewer_id, paper_ids=None, mode='method-blind',
                authority_state='non_authoritative', created_at=None):
        text(session_id, 'session ID')
        text(reviewer_id, 'reviewer pseudonymous ID')
        if mode not in {'method-blind', 'operational'} or authority_state not in {'non_authoritative', 'human_authorized'}:
            raise ContractError('invalid review mode/authority')
        created_at = created_at or now()
        timestamp(created_at)
        config = self.project.config
        if authority_state == 'human_authorized' and reviewer_id not in config.review.authorized_reviewers:
            raise ContractError('reviewer is not authorized by project policy')
        ids = list(paper_ids if paper_ids is not None else self.project.identities.papers())
        if not ids or len(ids) != len(set(ids)):
            raise ContractError('review population must be nonempty with unique IDs')
        papers, histories, current = [], {}, {}
        for paper_id in ids:
            metadata = self.project.discovery.metadata(paper_id)
            observations = {x['observation_id']: x for x in self.project.identities.observations(paper_id)}
            title_origin = metadata['field_provenance'].get('title')
            origin = observations.get(title_origin) or next(iter(observations.values()))
            source = origin['source']
            bases = {'metadata': {'representation': 'metadata', 'source_sha256': source['source_sha256'],
                                   'source_uri': source['source_uri'], 'artifact_validity': 'verified'}}
            representations = self.project.evidence.representations(paper_id)
            document = None
            if metadata['fields']['abstract']:
                abstract_origin = observations.get(metadata['field_provenance'].get('abstract'))
                if abstract_origin:
                    src = abstract_origin['source']
                    bases['abstract'] = {**bases['metadata'], 'representation': 'abstract',
                        'source_sha256': src['source_sha256'], 'source_uri': src['source_uri']}
                else:
                    abstracts = [x['payload'] for x in representations
                        if x['event_id']==metadata['field_provenance'].get('abstract')
                        and x['payload']['representation']=='abstract' and x['payload']['trusted']]
                    if abstracts:
                        src = abstracts[0]
                        bases['abstract'] = {'representation': 'abstract', 'source_sha256': src['artifact_sha256'],
                            'source_uri': src['source_uri'], 'artifact_validity': 'verified'}
            trusted = [x['payload'] for x in representations if x['payload']['trusted']
                       and x['payload']['artifact_validity']=='verified'
                       and x['payload'].get('evidence_depth')=='document_body'
                       and x['payload']['representation']=='structured_text']
            if trusted:
                doc = trusted[0]
                # Verify artifact bytes before a frozen packet may expose the document.
                artifact(self.project, doc['artifact_sha256'])
                document = {'sha256': doc['artifact_sha256'], 'representation': 'structured_text'}
                basis = {'representation': 'structured_text', 'source_sha256': doc['artifact_sha256'],
                         'source_uri': doc['source_uri'], 'artifact_validity': 'verified'}
                bases.update(sections=basis, full_document=basis)
            papers.append({'paper_id': paper_id,
                'bibliography': {key: metadata['fields'][key] for key in ('title','abstract','authors','year','source')},
                'canonical_metadata_provenance': {'selection_rule':metadata['selection_rule'],
                    'field_provenance':metadata['field_provenance'],
                    'source_observations':{key:value['source'] for key,value in observations.items()
                        if key in metadata['field_provenance'].values()}},
                'identifiers': [x for x in metadata['identifiers'] if x['scheme'] in {'doi','pmid','pmcid'}],
                'bases': bases, 'document': document,
                'pending_documents': sum(x['payload']['artifact_validity']=='pending_identity' for x in representations)})
            histories[paper_id] = content_hash(self.project.reviews.history(paper_id))
            current[paper_id] = self.project.reviews.membership(paper_id)['current_event_id']
        config_id, raw = latest_config(db)
        if raw != config.to_dict():
            raise ContractError('configuration changed during packet preparation')
        packet = {'schema': 'corpustrail-review-session/v1', 'session_id': session_id,
            'project_id': config.project_id, 'reviewer_id': reviewer_id, 'mode': mode,
            'authority_state': authority_state, 'policy_id': config.review.policy_id, 'created_at': created_at,
            'question': 'Does this paper belong in the broad scientific topic corpus: '+config.name+'?',
            'papers': papers, 'history_hashes': histories, 'current_events': current}
        for pid in ids:
            if content_hash(_history(db, pid)) != histories[pid]:
                raise ContractError('review history changed during preparation')
        if db.execute('SELECT 1 FROM ct_review_sessions WHERE session_id=?', (session_id,)).fetchone():
            raise FileExistsError('session already exists; reopen it instead')
        db.execute('INSERT INTO ct_review_sessions VALUES (?,?,?,?)',
                   (session_id, canonical(packet), content_hash(packet), config_id))
        return None

    def view(self, session_id):
        """Label-blind browser allowlist: only own drafts, bibliography, trusted evidence."""
        with connection(self.project.database_path) as db:
            packet, state, revision, _ = _load(db, session_id)
        pid = state['order'][state['index']]
        paper = _paper(packet, pid)
        statuses = [_status(packet, state, x) for x in state['order']]
        result = {'revision': revision, 'question': packet['question'],
            'mode': packet['mode'], 'number': state['index']+1, 'total': len(state['order']),
            'paper_id': pid, **paper['bibliography'], 'identifiers': paper['identifiers'],
            'review': state['drafts'].get(pid, _draft({})),
            'review_options': [x for x in ('metadata','abstract','sections','full_document') if x in paper['bases']],
            'document_available': paper['document'] is not None,
            'document_opened': pid in state['opened'], 'pending_documents': paper['pending_documents'],
            'overview': statuses, 'counts': {x: statuses.count(x) for x in ('complete','blank','insufficient','partial')},
            'recorded': pid in state['committed'], 'recorded_count': len(state['committed']),
            'recording_notice': 'Explicit commits append authorized human corpus decisions.'
                if packet['authority_state']=='human_authorized' else
                'Explicit commits append non-authoritative human observations; corpus membership is unchanged.',
            'remaining_count': len(state['order'])-len(state['committed']),
            'ordering': 'assigned' if packet['mode']=='method-blind' and state['ordering']=='priority' else state['ordering'],
            'assigned_order_available': state['ranking_run_id'] is not None}
        if packet['mode']=='operational' and state['ranking_run_id']:
            ranking = self.project.prioritization.run(state['ranking_run_id'])
            result['priority'] = next(x for x in ranking['scores'] if x['paper_id']==pid)['rank']
            result['priority_notice'] = 'Review-ordering aid only; not an eligibility judgment.'
        return result

    def update(self, session_id, *, expected_revision, action, value=None):
        """CAS guards autosave/resume; explicit commit is the only authority write."""
        with connection(self.project.database_path, write=True) as db:
            packet, state, revision, config_id = _load(db, session_id)
            prior_state=deepcopy(state)
            if revision != expected_revision:
                raise ContractError('stale session revision; reload before saving')
            if latest_config(db)[0] != config_id:
                raise ContractError('project configuration changed; prepare a new session')
            pid = state['order'][state['index']]
            if action == 'draft':
                draft = _draft(value)
                if draft['review_extent'] not in (*_paper(packet,pid)['bases'],None,'none'):
                    raise ContractError('evidence selection is unavailable')
                if draft['review_extent'] in {'sections','full_document'} and pid not in state['opened']:
                    raise ContractError('document must be opened before sections/full-paper attestation')
                state['drafts'][pid] = draft
            elif action == 'open':
                if not _paper(packet,pid)['document']:
                    raise ContractError('no trusted document is available')
                doc = _paper(packet,pid)['document']
                artifact(self.project, doc['sha256'])
                if pid not in state['opened']:
                    state['opened'].append(pid)
            elif action == 'commit':
                draft = _draft(state['drafts'].get(pid, {}))
                event = _event(packet,state,pid,draft,now())
                event.validate()
                history_hash=content_hash(_history(db,pid))
                if packet['authority_state']=='human_authorized' and history_hash != state['heads'][pid]:
                    raise ContractError('paper decision history changed; administrative review required')
                # Independent non-authoritative reviews may coexist. They never supersede
                # another reviewer or affect membership, and use a fresh transactional plan.
                plan = ReviewPlan(event, history_hash, config_id)
                event_id = self.project.reviews._apply(db, plan, event.created_at)
                state['heads'][pid] = content_hash(_history(db,pid))
                state['committed'][pid] = event_id
            elif action == 'navigate':
                n = len(state['order'])
                if type(value) is int:
                    if not 1 <= value <= n:
                        raise ContractError('paper number is out of range')
                    state['index'] = value-1
                elif value in {'first','last','previous','next'}:
                    state['index'] = {'first':0, 'last':n-1, 'previous':max(0,state['index']-1),
                                      'next':min(n-1,state['index']+1)}[value]
                elif value in {'next_partial','next_incomplete','previous_incomplete'}:
                    direction = -1 if value=='previous_incomplete' else 1
                    wanted = {'partial'} if value=='next_partial' else {'partial','blank'}
                    for offset in range(1,n+1):
                        index = (state['index']+direction*offset)%n
                        if _status(packet,state,state['order'][index]) in wanted:
                            state['index'] = index
                            break
                else:
                    raise ContractError('invalid navigation')
            elif action == 'ordering':
                if value == 'original':
                    state['order'] = [x['paper_id'] for x in packet['papers']]
                elif value == 'paper_id':
                    state['order'] = sorted(state['order'])
                elif value in {'priority','assigned'} and state['ranking_run_id']:
                    row = db.execute('SELECT artifact_id FROM ct_priority_runs WHERE run_id=?',
                                     (state['ranking_run_id'],)).fetchone()
                    from corpustrail.prioritization.service import _get
                    ranking = _get(db,row[0],'ranking')
                    state['order'] = [x['paper_id'] for x in ranking['scores']]
                    value = 'priority'
                else:
                    raise ContractError('ordering requires an explicitly bound ranking run')
                state['ordering'] = value
                state['index'] = state['order'].index(pid)
            elif action == 'bind_ranking':
                from corpustrail.prioritization.service import _get
                row = db.execute('SELECT artifact_id FROM ct_priority_runs WHERE run_id=?', (value,)).fetchone()
                if row is None:
                    raise KeyError(value)
                ranking = _get(db,row[0],'ranking')
                if {x['paper_id'] for x in ranking['scores']} != set(state['order']):
                    raise ContractError('ranking must preserve the entire frozen session population')
                frozen = {x['paper_id']: x['bibliography'] for x in packet['papers']}
                for x in ranking['candidate_population']:
                    if any((frozen[x['paper_id']][key] or '') != x[key] for key in ('title','abstract')):
                        raise ContractError('ranking text differs from frozen review evidence')
                    paper=_paper(packet,x['paper_id'])
                    available={'abstract_available':bool(paper['bibliography']['abstract']),
                        'verified_full_text_available':paper['document'] is not None,
                        'representation':'structured_text' if paper['document'] else
                            ('abstract' if paper['bibliography']['abstract'] else 'metadata')}
                    if x['evidence_availability'] != available:
                        raise ContractError('ranking evidence availability differs from the frozen session')
                state['ranking_run_id'] = value
                # Binding records a new provenance event, but does not silently reorder.
            else:
                raise ContractError('invalid session action')
            _append(db, session_id, state, revision, action, prior_state)
        return self.view(session_id)

    def document(self, session_id, paper_id):
        """Side-effect-free artifact read, confined to this session's trusted evidence."""
        with connection(self.project.database_path) as db:
            packet, state, _, _ = _load(db,session_id)
        if paper_id not in state['order'] or paper_id not in state['opened']:
            raise ContractError('document is not available/opened in this session')
        doc = _paper(packet,paper_id)['document']
        if not doc:
            raise ContractError('no trusted document')
        return artifact(self.project,doc['sha256'])
