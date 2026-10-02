"""Read-only adapters over current generic records and stored immutable assertions."""
from copy import deepcopy
import json

from corpustrail._internal.database import connection
from corpustrail._internal.values import canonical
from .registry import CHARACTERIZATION, Registry
from .storage import identified, KnowledgeStore, verify_connection
from .evidence import resolve_reference


def observation(ref, paper_id, predicate, raw_value, *, source, producer,
                subject_type='paper', subject_id=None, normalized_value=None, evidence=None,
                timestamp=None, authority=None, validation=None, confidence=None, relations=(),
                vocabulary_version=None, origin='adapted', context=None):
    return deepcopy({'schema_version':'corpustrail-knowledge-view/v0a',
        'observation_ref':ref, 'subject_type':subject_type, 'subject_id':subject_id or paper_id,
        'paper_id':paper_id, 'predicate':predicate, 'raw_value':raw_value,
        'normalized_value':normalized_value, 'vocabulary_version':vocabulary_version,
        'source':source, 'producer':producer, 'evidence':evidence, 'timestamp':timestamp,
        'authority':authority or {'source_status':'non_authoritative','purposes':[]},
        'validation':validation, 'confidence':confidence, 'lineage_identifier':ref,
        'relations':list(relations), 'origin':origin, 'context':context,
        'scientific_state_effect':'none'})


class KnowledgeView:
    """Each query is one SQLite read transaction; absent values are never filled."""
    def __init__(self, project):
        self.project = project

    def observations(self, paper_id=None, *, producer=None, predicate=None):
        with connection(self.project.database_path) as db:
            result = self._observations(db)
        return [o for o in result if (paper_id is None or o['paper_id']==paper_id) and
                (predicate is None or o['predicate']==predicate) and
                (producer is None or o['producer']['type']==producer)]

    def _observations(self, db):
        verify_connection(db, KnowledgeStore(self.project,registry=Registry.from_connection(db)))
        result = []
        for row in db.execute('SELECT * FROM ct_paper_observations ORDER BY observation_id'):
            p = json.loads(row['payload_json']); source = p['source']
            result.append(observation(row['observation_id'],row['paper_id'],'bibliography.record',p['record'],
                source={'table':'ct_paper_observations','record_id':row['observation_id'], **source},
                producer={'type':{'imported':'imported/external','parser':'parser/document'}.get(source['producer_type'],source['producer_type']),
                          'name':source['producer_id'],'version':None},
                evidence={'representation':'metadata','artifact_sha256':source['source_sha256'],
                          'trusted':source['identity_status']=='verified'}, timestamp=source['observed_at']))
        reviews = list(db.execute('SELECT * FROM ct_review_events ORDER BY sequence'))
        current = {}
        for row in reviews:
            if row['authority_state']=='human_authorized':
                current[row['paper_id']]=row['event_id']
        for row in reviews:
            p = json.loads(row['payload_json'])
            relations = [{'relation':'supersedes','target':p['supersedes']}] if p['supersedes'] else []
            relations += [{'relation':'superseded_by','source':r['event_id']} for r in reviews if r['supersedes']==row['event_id']]
            result.append(observation(row['event_id'],row['paper_id'],'ct.broad_corpus_membership',p['state'],
                source={'table':'ct_review_events','record_id':row['event_id'], 'content_sha256':row['content_sha256'],
                        'original_review':p}, producer={'type':{'parser':'parser/document','imported':'imported/external'}.get(p['producer_type'],p['producer_type']),
                        'name':p['producer_id'],'version':None}, evidence={'review_extent':p['review_extent'],'bases':p['evidence']},
                timestamp=p['created_at'],authority={'source_status':row['authority_state'],
                    'purpose':'broad_corpus_membership','current':current.get(row['paper_id'])==row['event_id']},
                relations=relations))
        for row in db.execute("SELECT * FROM ct_pipeline_events WHERE kind='representation' ORDER BY event_id"):
            p = json.loads(row['payload_json'])['payload']
            result.append(observation(row['event_id'],row['paper_id'],'ct.evidence_availability',p['representation'],
                source={'table':'ct_pipeline_events','record_id':row['event_id'],'content_sha256':row['content_sha256'],
                        'source_uri':p['source_uri']}, producer={'type':'parser/document' if p.get('parser') else 'imported/external',
                        'name':p.get('parser',p['resolver']),'version':p.get('parser_version',p['resolver_version'])},
                evidence={'representation':p['representation'],'artifact_sha256':p['artifact_sha256'],
                          'trusted':p['trusted'],'artifact_validity':p['artifact_validity'],
                          'evidence_depth':p.get('evidence_depth')}, timestamp=p['created_at']))
        events = [identified(json.loads(r['payload_json']),'event') for r in db.execute('SELECT * FROM knowledge_events ORDER BY event_id')]
        for row in db.execute('SELECT * FROM knowledge_assertions ORDER BY assertion_id'):
            p = json.loads(row['payload_json'])
            relations = [e for e in events if row['assertion_id'] in (e['payload']['target_assertion_id'],e['payload']['source_assertion_id'])]
            grants = [e for e in events if e['payload']['target_assertion_id']==row['assertion_id'] and
                      e['payload']['relation']=='grants_authority' and not any(
                          r['payload']['relation']=='revokes_authority' and r['payload']['target_event_id']==e['id'] for r in events)]
            result.append(observation(row['assertion_id'],p['paper_id'],p['predicate'],p['raw_value'],
                subject_type=p['subject_type'],subject_id=p['subject_id'],normalized_value=p['normalized_value'],
                vocabulary_version=p['vocabulary_version'],source={'table':'knowledge_assertions','record_id':row['assertion_id'],
                    'content_sha256':row['content_sha256'],'original_source':p['source'],'lineage_ref':p['lineage_ref']},
                producer={'type':p['producer_type'],'name':p['producer_id'],'version':p['producer_version']},
                evidence={'representation':p['evidence_representation'],'location':p['evidence_location'],
                    'reference':p['evidence_reference'], **resolve_reference(self.project,db,p)},
                confidence=p['confidence'],timestamp=p['created_at'],relations=relations,
                authority={'source_status':p['initial_authority'],'purposes':sorted({e['payload']['purpose'] for e in grants}),
                           'grant_ids':[e['id'] for e in grants]},
                validation={'initial':p['initial_validation'],'history':[e for e in relations if e['payload']['target_assertion_id']==row['assertion_id']]},
                origin='stored',context=p['context']))
        return sorted(result,key=lambda o:o['observation_ref'])

    def query(self, predicate, value):
        return [o for o in self.observations(predicate=predicate) if canonical(o['raw_value'])==canonical(value) or
                (o['normalized_value'] is not None and canonical(o['normalized_value'])==canonical(value))]

    def lineage(self, paper_id):
        return [{k:o[k] for k in ('observation_ref','source','producer','evidence','authority','validation','relations')}
                for o in self.observations(paper_id)]

    def conflicts(self, paper_id=None):
        return self._conflicts(self.observations(paper_id))

    @staticmethod
    def _conflicts(records):
        groups = {}
        for o in records:
            if o['predicate'] not in CHARACTERIZATION and o['origin']!='stored':
                continue
            key = (o['subject_type'],o['subject_id'],o['predicate'],o['vocabulary_version'],canonical(o['context']))
            groups.setdefault(key,[]).append(o)
        return [{'subject_type':k[0],'subject_id':k[1],'predicate':k[2],'vocabulary_version':k[3],
                 'observations':v,'kind':'candidate_value_difference','resolution':'not_inferred'}
                for k,v in sorted(groups.items(), key=lambda item:canonical(item[0])) if len({canonical(o['raw_value']) for o in v if o['raw_value'] is not None})>1]

    def paper_sets(self):
        with connection(self.project.database_path) as db:
            papers = {r[0] for r in db.execute('SELECT paper_id FROM paper_entities')}
            records = self._observations(db)
        structured = [o for o in records if o['predicate'] in CHARACTERIZATION or
                      (o['origin']=='stored' and o['predicate'] not in ('ct.evidence_availability','ct.broad_corpus_membership','bibliography.record'))]
        represented = {o['paper_id'] for o in structured if o['raw_value'] is not None and o['paper_id']}
        authoritative = {o['paper_id'] for o in structured if o['authority'].get('purposes')}
        validated = {o['paper_id'] for o in structured if any(e['payload']['relation']=='validates' for e in (o.get('validation') or {}).get('history',[]))}
        full = {o['paper_id'] for o in structured if (o['evidence'] or {}).get('trusted') and
                (o['evidence'] or {}).get('evidence_depth')=='document_body' and
                (o['evidence'] or {}).get('representation') in ('structured_text','ocr_text','pdf_text','jats_xml','publisher_xml')}
        model_parser = {pid for pid in represented if all(o['producer']['type'] in ('model','parser/document') for o in structured if o['paper_id']==pid)}
        conflicts = {o['paper_id'] for group in self._conflicts(records) for o in group['observations'] if o['paper_id']}
        return {'human_validated':sorted(validated & papers),'knowledge_authoritative':sorted(authoritative & papers),
                'full_text_supported':sorted(full & papers),'only_non_authoritative':sorted((represented-authoritative)&papers),
                'only_model_parser':sorted(model_parser & papers),'unresolved_candidate_conflicts':sorted(conflicts & papers),
                'lacking_characterization':sorted(papers-represented)}

    def vocabulary(self):
        with connection(self.project.database_path) as db:
            records = [json.loads(r[0]) for r in db.execute('SELECT payload_json FROM ct_knowledge_registry_records ORDER BY sequence')]
        return {'registry':Registry.for_project(self.project).definitions(), 'project_vocabularies':records,
                'automatic_crosswalks':[], 'promotion_performed':False}
