"""Bounded guided-review DTOs/commands; scientific rules remain in curation."""
import json
import re

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, content_hash
from corpustrail.curation.guided import GuidedReviewService, SCHEMA
from corpustrail.curation.sessions import SessionService, GUIDED_SCHEMA, _load, _paper, _status
from corpustrail.curation.service import _history, membership_in_connection
from .projects import ProjectCommandError


def _handle(session):
    return session.split(':')[1] if session.startswith('guided-session:') else content_hash({'legacy':session}).split(':')[1]


def _session(project, handle):
    if not isinstance(handle,str) or not re.fullmatch(r'[0-9a-f]{64}',handle):
        raise ProjectCommandError('Choose a review session from this project.')
    with connection(project.database_path) as db:
        for row in db.execute('SELECT session_id FROM ct_review_sessions'):
            if _handle(row[0])==handle: return row[0]
    raise KeyError(handle)


def _page(offset, limit):
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise ProjectCommandError('Choose a valid review page.')


class ReviewController:
    def configuration(self, project, *, offset=0, limit=20):
        _page(offset,limit)
        service = GuidedReviewService(project)
        populations=[]
        for key,name in (('all','All currently collected publications'),('awaiting','Publications awaiting a corpus decision')):
            ids=service.population(key)
            populations.append({'selection':key,'label':name,'count':len(ids),'sha256':content_hash(ids)})
        with connection(project.database_path) as db:
            revision,_=latest_config(db)
            assisted_table=db.execute("SELECT 1 FROM sqlite_master WHERE name='ct_curation_sessions'").fetchone()
            clause=' WHERE NOT EXISTS(SELECT 1 FROM ct_curation_sessions c WHERE c.session_id=ct_review_sessions.session_id)' if assisted_table else ''
            total=db.execute('SELECT COUNT(*) FROM ct_review_sessions'+clause).fetchone()[0]
            rows=db.execute('SELECT session_id FROM ct_review_sessions'+clause+' ORDER BY rowid DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
            sessions=[]
            for row in rows:
                packet,state,_,config=_load(db,row[0])
                sessions.append({'handle':_handle(row[0]),'reviewer':packet['reviewer_id'],'created_at':packet['created_at'],
                    'total':len(state['order']),'saved':len(state['committed']),
                    'status':state.get('lifecycle','legacy'),'published':bool(state.get('publication')),
                    'legacy':packet['schema']!=GUIDED_SCHEMA,'stale':config!=revision})
        return {'schema':SCHEMA,'config_event_id':revision,'definition':project.config.review.scope,
            'authorized_reviewers':list(project.config.review.authorized_reviewers),'populations':populations,
            'sessions':sessions,'total_sessions':total,'next_offset':offset+limit if offset+limit<total else None}

    def view(self, project, handle, *, assisted=False):
        session=_session(project,handle)
        self._boundary(project,session,assisted)
        # Reuse the established method-blind frozen evidence allowlist.
        frozen=SessionService(project).view(session)
        with connection(project.database_path) as db:
            packet,state,revision,config=_load(db,session)
            if revision!=frozen['revision']: raise ProjectCommandError('Review changed in another window. Reload this session.',status=409)
            legacy=packet['schema']!=GUIDED_SCHEMA
            keys=('revision','question','mode','number','total','paper_id','title','abstract','authors','year','source',
                'identifiers','review','review_options','document_available','document_opened','pending_documents','recorded','recorded_count')
            result={k:frozen[k] for k in keys}
            result.update(schema=SCHEMA,handle=handle,reviewer=packet['reviewer_id'],legacy=legacy,
                policy_id=packet['policy_id'],
                lifecycle=state.get('lifecycle','legacy'),stale=latest_config(db)[0]!=config,
                can_publish=packet['reviewer_id'] in project.config.review.authorized_reviewers,
                evidence=_paper(packet,result['paper_id']).get('evidence_summary',{}))
            result['candidate_population'] = project.populations.review_link(db, session)
            if not legacy:
                result.update(summary=GuidedReviewService(project).summary(packet,state,db),
                    completion=bool(state['completion']),published=bool(state['publication']),
                    publication_plan_sha256=state['publication_plan']['sha256'] if state['publication_plan'] else None,
                    population_sha256=packet['population_sha256'],evidence_snapshot_sha256=packet['evidence_snapshot_sha256'])
            if packet['mode']=='operational':
                result['source_provenance']=_paper(packet,result['paper_id'])['canonical_metadata_provenance']
            return result

    def command(self, project, action, body):
        service=GuidedReviewService(project)
        try:
            if action=='create':
                if set(body)!={'command_id','reviewer_id','selection','population_sha256','config_event_id','mode'}:
                    raise ContractError('unsupported session creation fields')
                result=service.create(**body)
            else:
                if action!='command' or set(body)!={'handle','command_id','expected_revision','action','value'}:
                    raise ContractError('unsupported review command fields')
                body=dict(body);session=_session(project,body.pop('handle'))
                result=service.command(session,**body)
            return {**result,'handle':_handle(result['session_id'])}
        except ContractError as exc:
            # Only controlled contract messages; do not return OS or DB diagnostics.
            raise ProjectCommandError(str(exc),code='review_conflict',status=409) from exc

    def _boundary(self, project, session, assisted):
        from corpustrail.classification.curation_views import is_assisted
        with connection(project.database_path) as db:
            if is_assisted(db,session) != assisted:
                raise ProjectCommandError('Use the separate operational assisted route for an assisted session; it is not method-blind review.',status=409)

    def summary_page(self, project, handle, *, offset=0, limit=20, assisted=False):
        _page(offset,limit);session=_session(project,handle)
        self._boundary(project,session,assisted)
        with connection(project.database_path) as db:
            packet,state,revision,_=_load(db,session)
            if packet['schema']!=GUIDED_SCHEMA: raise ProjectCommandError('Legacy sessions retain their original workflow.')
            selected=state['completion']['saved_events'] if state['completion'] else state['committed']
            rows=[]
            for pid in state['order'][offset:offset+limit]:
                event=next((x for x in _history(db,pid) if x['event_id']==selected.get(pid)),None)
                dirty=state['saved_drafts'].get(pid)!=state['drafts'].get(pid)
                row={'title':_paper(packet,pid)['bibliography']['title'],'state':event['state'] if event and not dirty else 'undecided',
                    'changed_draft':dirty and pid in state['committed'],'draft_status':_status(packet,state,pid),
                    'observation_event_id':event['event_id'] if event else None,
                    'review_extent':event['review_extent'] if event else None,'rationale':event['rationale'] if event else None}
                if state['publication']:
                    row['publication_link']=next((x for x in state['publication']['links'] if x['paper_id']==pid),None)
                # Publication confirmation is an explicitly requested operational view.
                if state['publication_plan']:
                    head=state['publication_plan']['plan']['membership_heads'].get(pid)
                    prior=next((x for x in _history(db,pid) if x['event_id']==head),None)
                    row['current_membership']=prior['state'] if prior else 'not_reviewed'
                rows.append(row)
            return {'schema':SCHEMA,'revision':revision,'items':rows,
                'population_sha256':packet['population_sha256'],'evidence_snapshot_sha256':packet['evidence_snapshot_sha256'],
                'completion_sha256':content_hash(state['completion']) if state['completion'] else None,
                'publication_plan_sha256':state['publication_plan']['sha256'] if state['publication_plan'] else None,
                'next_offset':offset+limit if offset+limit<len(state['order']) else None}

    def document(self, project, handle, *, offset=0, limit=16000, assisted=False):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=32000:
            raise ProjectCommandError('Choose a valid text segment.')
        session=_session(project,handle)
        self._boundary(project,session,assisted)
        with connection(project.database_path) as db:
            packet,state,_,_=_load(db,session)
            pid=state['order'][state['index']]
        # Same confined, hash-verifying frozen-document service as existing review.
        body=SessionService(project).document(session,pid).read_text(encoding='utf-8')
        if offset>len(body): raise ProjectCommandError('The text segment is outside this document.')
        return {'schema':SCHEMA,'text':body[offset:offset+limit],'offset':offset,'total_characters':len(body),
            'next_offset':offset+limit if offset+limit<len(body) else None,
            'notice':'Opening text does not attest that it has been read.'}
