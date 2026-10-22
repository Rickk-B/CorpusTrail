"""Versioned guided lifecycle over existing frozen packets and review authority.

Commands, completion and publication/source-event links share the append-only
session ledger. BEGIN IMMEDIATE, revision CAS and durable scoped command receipts
make observation+navigation and multi-paper publication atomic and replay-safe.
Legacy sessions/recording semantics are not reinterpreted. No new database/schema.
"""
from copy import deepcopy
from contextlib import nullcontext
import json
import re

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.pipeline import artifact
from corpustrail._internal.values import ContractError, content_hash, identifier, now, text
from .sessions import SessionService, GUIDED_SCHEMA, _load, _append, _draft, _event, _status, _paper
from .service import ReviewEvent, ReviewPlan, EvidenceBasis, _history, membership_in_connection

SCHEMA = 'corpustrail-guided-review/v1'
OUTCOMES = ('included', 'excluded', 'insufficient_evidence')


def _command_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise ContractError('invalid review command identity')


def _replay(db, session, command):
    # Indexed by session; all writes are serialized by the project transaction.
    for row in db.execute('SELECT event_id,payload_json FROM ct_review_session_events WHERE session_id=? ORDER BY sequence', (session,)):
        payload = json.loads(row['payload_json'])
        previous = payload.get('command')
        if previous and previous['id'] == command['id']:
            if previous != command:
                raise ContractError('review command was already used with different input')
            return {'schema':SCHEMA, 'session_id':session, 'revision':row['event_id'], 'result':payload['result']}
    return None


def _selected(packet, state):
    return {pid:eid for pid,eid in state['committed'].items()
            if state['drafts'].get(pid) == state['saved_drafts'].get(pid)}


class GuidedReviewService:
    def __init__(self, project, *, _db=None):
        self.project = project
        self._db = _db

    def _connection(self, *, write=False):
        # Internal CP9 composition preserves the original scientific rules and
        # links observations/publications atomically. No HTTP connection input.
        return nullcontext(self._db) if self._db is not None else connection(self.project.database_path, write=write)

    def population(self, selection, *, db=None):
        if isinstance(selection, str) and selection.startswith('population-version:'):
            if db is None:
                with connection(self.project.database_path) as current:
                    return self.project.populations.review_ids(current, selection)
            return self.project.populations.review_ids(db, selection)
        ids = self.project.identities.papers()
        if selection == 'awaiting':
            ids = [pid for pid in ids if self.project.reviews.membership(pid)['state'] in {'not_reviewed','unresolved'}]
        elif selection != 'all':
            raise ContractError('choose an explicit supported review population')
        return ids

    def create(self, *, command_id, reviewer_id, selection, population_sha256, config_event_id, mode):
        _command_id(command_id); text(reviewer_id,'reviewer pseudonym')
        if len(reviewer_id)>200: raise ContractError('reviewer pseudonym is too long')
        session = identifier('guided-session', {'project':self.project.config.project_id,'command':command_id})
        value = dict(reviewer_id=reviewer_id,selection=selection,population_sha256=population_sha256,
                     config_event_id=config_event_id,mode=mode)
        command = {'id':command_id,'sha256':content_hash({'action':'create','value':value})}
        with self._connection(write=True) as db:
            if db.execute('SELECT 1 FROM ct_review_sessions WHERE session_id=?',(session,)).fetchone():
                _load(db,session)
                self.project.populations.review_link(db, session)
                result = _replay(db,session,command)
                if result: return result
                raise ContractError('session creation differs from its original command')
            if latest_config(db)[0]!=config_event_id: raise ContractError('project configuration changed')
            ids = self.population(selection, db=db)
            if content_hash(ids)!=population_sha256: raise ContractError('candidate population changed; refresh the review setup')
            SessionService(self.project)._prepare(db,session,reviewer_id=reviewer_id,paper_ids=ids,mode=mode,guided=True)
            if selection.startswith('population-version:'):
                population_link = self.project.populations.bind_review(db, selection, session)
            else:
                population_link = None
            _,state,revision,_ = _load(db,session)
            result = {'action':'create','status':'active'}
            if population_link is not None:
                result['candidate_population'] = population_link
            revision = _append(db,session,state,revision,'created',deepcopy(state),command=command,result=result)
            return {'schema':SCHEMA,'session_id':session,'revision':revision,'result':result}

    def summary(self, packet, state, db):
        selected = _selected(packet,state)
        counts = {x:0 for x in OUTCOMES}
        for pid,eid in selected.items():
            event = next((x for x in _history(db,pid) if x['event_id']==eid),None)
            if not event or event['producer_id']!=packet['reviewer_id'] or event['authority_state']!='non_authoritative':
                raise ContractError('saved observation provenance differs')
            expected = _event(packet,state,pid,state['saved_drafts'][pid],event['created_at'])
            if expected.event_id!=eid: raise ContractError('saved observation differs from its frozen evidence and draft')
            counts[event['state']]+=1
        return {'counts':counts,'total':len(state['order']),'saved_observations':len(state['committed']),
            'selected_observations':len(selected),'undecided':len(state['order'])-len(selected),
            'changed_drafts':sum(pid in state['committed'] and pid not in selected for pid in state['drafts']),
            'incomplete_drafts':sum(_status(packet,state,pid)=='partial' for pid in state['order']),
            'skipped':sum(bool(v) and pid not in selected for pid,v in state['skipped'].items())}

    def command(self, session, *, command_id, expected_revision, action, value=None):
        _command_id(command_id)
        if action not in {'draft','save_next','navigate','skip','open','finish','prepare_publication','publish'}:
            raise ContractError('unsupported guided review action')
        command = {'id':command_id,'sha256':content_hash({'action':action,'value':value,'revision':expected_revision})}
        with self._connection(write=True) as db:
            packet,state,revision,config = _load(db,session)
            if self._db is None and db.execute("SELECT 1 FROM sqlite_master WHERE name='ct_curation_sessions'").fetchone():
                if db.execute('SELECT 1 FROM ct_curation_sessions WHERE session_id=?',(session,)).fetchone():
                    raise ContractError('Use the operational assisted workflow so assessment and audit links remain atomic.')
            self.project.populations.review_link(db, session)
            if packet['schema']!=GUIDED_SCHEMA: raise ContractError('legacy sessions retain their original recording contract')
            replay = _replay(db,session,command)
            if replay: return replay
            if revision!=expected_revision: raise ContractError('stale review session; reload before retrying')
            if latest_config(db)[0]!=config: raise ContractError('project configuration changed; start a new frozen session')
            before = deepcopy(state)
            if state['lifecycle']!='active' and action not in {'prepare_publication','publish'}:
                raise ContractError('completed sessions preserve their observations; start a new session for corrections')
            pid = state['order'][state['index']]
            result = {'action':action,'paper_id':pid}
            if action in {'draft','save_next'}:
                draft = _draft(value)
                if draft['sufficiency']=='undetermined': raise ContractError('use Skip for now instead of an unresolved scientific judgment')
                paper = _paper(packet,pid)
                extent = draft['review_extent']
                if extent not in (*paper['bases'],None,'none'): raise ContractError('evidence is unavailable in the frozen session')
                if extent in {'sections','full_document'} and pid not in state['opened']:
                    raise ContractError('open the trusted text before attesting document review')
                state['drafts'][pid]=draft
                if action=='save_next':
                    event = _event(packet,state,pid,draft,now()); event.validate()
                    if event.state not in OUTCOMES: raise ContractError('choose Include, Exclude or Insufficient evidence')
                    # Saving an unchanged already-recorded assessment is a no-op.
                    if state['saved_drafts'].get(pid)!=draft:
                        plan = ReviewPlan(event,content_hash(_history(db,pid)),config)
                        eid = self.project.reviews._apply(db,plan,event.created_at)
                        state['committed'][pid]=eid; state['saved_drafts'][pid]=deepcopy(draft)
                    state['skipped'][pid]=False
                    result['observation_event_id']=state['committed'][pid]
                    state['index']=min(state['index']+1,len(state['order'])-1)
            elif action in {'navigate','skip'}:
                if action=='skip': state['skipped'][pid]=True; value='next'
                if value not in {'next','previous'}: raise ContractError('invalid review navigation')
                state['index']=max(0,min(len(state['order'])-1,state['index']+(1 if value=='next' else -1)))
            elif action=='open':
                document = _paper(packet,pid)['document']
                if not document: raise ContractError('no trusted document in this frozen session')
                artifact(self.project,document['sha256'])
                if pid not in state['opened']: state['opened'].append(pid)
            elif action=='finish':
                if not isinstance(value,dict) or set(value)!={'preserve_undecided'} or value['preserve_undecided'] is not True:
                    raise ContractError('explicitly preserve unassessed and incomplete drafts as undecided')
                summary = self.summary(packet,state,db)
                state['lifecycle']='completed'
                state['completion']={'schema':'corpustrail-guided-completion/v1','reviewer_id':packet['reviewer_id'],
                    'completed_at':now(),'config_event_id':config,'session_revision':revision,
                    'population_sha256':packet['population_sha256'],'evidence_snapshot_sha256':packet['evidence_snapshot_sha256'],
                    'saved_events':_selected(packet,state),'summary':summary,'publication_outcome':'not_published'}
                result.update(status='completed',membership_changed=False)
            elif action=='prepare_publication':
                if state['lifecycle']!='completed' or state['publication']: raise ContractError('finish the review before a new publication plan')
                if packet['reviewer_id'] not in self.project.config.review.authorized_reviewers:
                    raise ContractError('this reviewer has no corpus-publication authority')
                selected = state['completion']['saved_events']
                self.summary(packet,state,db)
                if not selected: raise ContractError('no saved judgments were selected for publication')
                heads = {p:content_hash(_history(db,p)) for p in selected}
                plan = {'schema':'corpustrail-guided-publication/v1','session_revision':revision,
                    'completion_sha256':content_hash(state['completion']),'saved_events':selected,
                    'population_sha256':packet['population_sha256'],'evidence_snapshot_sha256':packet['evidence_snapshot_sha256'],
                    'definition':packet['question'],'config_event_id':config,'reviewer_id':packet['reviewer_id'],
                    'policy_id':packet['policy_id'],'history_hashes':heads,
                    'membership_heads':{p:membership_in_connection(db,p)['current_event_id'] for p in selected}}
                state['publication_plan']={'plan':plan,'sha256':content_hash(plan)}
                result['plan_sha256']=content_hash(plan)
            elif action=='publish':
                prepared = state['publication_plan']
                if (state['lifecycle']!='completed' or state['publication'] or not prepared or
                    not isinstance(value,dict) or set(value)!={'plan_sha256','confirm_authority'} or
                    value.get('plan_sha256')!=prepared['sha256'] or value.get('confirm_authority') is not True):
                    raise ContractError('inspect and explicitly confirm the exact publication plan')
                plan = prepared['plan']
                if (content_hash(plan)!=prepared['sha256'] or plan['completion_sha256']!=content_hash(state['completion'])
                        or plan['config_event_id']!=config or plan['saved_events']!=state['completion']['saved_events']):
                    raise ContractError('publication inputs changed')
                if packet['reviewer_id'] not in self.project.config.review.authorized_reviewers:
                    raise ContractError('this reviewer has no corpus-publication authority')
                for p,sha in plan['history_hashes'].items():
                    if content_hash(_history(db,p))!=sha: raise ContractError('paper decision history changed; inspect and prepare a new confirmation')
                links=[]
                for p,eid in plan['saved_events'].items():
                    observation = next(x for x in _history(db,p) if x['event_id']==eid)
                    bases=tuple(EvidenceBasis(**x) for x in observation['evidence'])
                    # Metadata sources need enrollment, not a locally downloaded
                    # document. Reuse ReviewService's distinct evidence checks.
                    for basis in bases:
                        if basis.representation=='structured_text': artifact(self.project,basis.source_sha256)
                    event=ReviewEvent(p,observation['state'],observation['sufficiency'],observation['review_extent'],
                        observation['rationale'],packet['reviewer_id'],now(),bases,policy_id=packet['policy_id'],
                        authority_state='human_authorized',supersedes=plan['membership_heads'][p])
                    authority=self.project.reviews._apply(db,ReviewPlan(event,plan['history_hashes'][p],config),event.created_at)
                    links.append({'paper_id':p,'observation_event_id':eid,'authority_event_id':authority})
                state['publication']={'schema':'corpustrail-guided-publication-receipt/v1',
                    'plan_sha256':prepared['sha256'],'published_at':now(),'reviewer_id':packet['reviewer_id'],'links':links}
                result.update(status='published',membership_changed=True,links=links)
            revision=_append(db,session,state,revision,action,before,command=command,result=result)
            return {'schema':SCHEMA,'session_id':session,'revision':revision,'result':result}
